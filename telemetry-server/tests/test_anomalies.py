from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from conftest import message, sync
from sqlalchemy import select
from sqlalchemy.orm import Session

from aaw_telemetry.models import AnomalyArchiveRequest, AnomalyEvent, WorkflowRun
from aaw_telemetry.services.anomalies import DETECTOR_SPECS, AnomalyService


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/anomalies/admin/login", json={"password": "123456"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _owner(client) -> str:
    created = client.post("/api/v1/ai-masters", json={"name": "异常值守"})
    assert created.status_code == 201, created.text
    master_id = created.json()["id"]
    assigned = client.put(
        "/api/v1/ai-masters/repo-assignments/team/example-service",
        json={"ai_master_id": master_id},
    )
    assert assigned.status_code == 200, assigned.text
    return master_id


def _stalled_workflow(client) -> None:
    stale = datetime.now(UTC) - timedelta(days=3)
    payload = message(
        workflow_completed=False,
        status="start",
        with_file=False,
        started_at=int(stale.timestamp() * 1000),
        step_started_at=int(stale.timestamp() * 1000),
        step_completed_at=None,
        updated_at=int((stale + timedelta(minutes=5)).timestamp() * 1000),
    )
    response = sync(client, payload)
    assert response.status_code == 200, response.text


def _create_stalled_rule(client, headers) -> dict:
    # 启动时已为全部检测类型预置停用规则；测试复用预置规则并启用它。
    items = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    rule = next(item for item in items if item["detector_type"] == "workflow_stalled")
    updated = client.put(
        f"/api/v1/anomalies/rules/{rule['id']}",
        headers=headers,
        json={
            "name": "工作流超过一小时无活动",
            "category": "workflow",
            "detector_type": "workflow_stalled",
            "scope_type": "platform",
            "params": {"max_idle_hours": 1},
            "status": "enabled",
            "change_reason": "测试异常周期",
        },
    )
    assert updated.status_code == 200, updated.text
    return updated.json()


def _evaluate(client, headers):
    response = client.post("/api/v1/anomalies/rules/evaluate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_anomaly_ui_is_part_of_existing_admin_console(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert 'data-tab="anomalies"' in response.text
    assert 'id="tab-anomalies"' in response.text
    assert client.get("/anomalies").status_code == 404


def test_admin_session_requires_password_and_csrf(client):
    assert client.get("/api/v1/anomalies/rules").status_code == 401
    assert client.get("/api/v1/anomalies/events?admin_view=true").status_code == 401
    assert (
        client.post("/api/v1/anomalies/admin/login", json={"password": "wrong"}).status_code == 401
    )
    _admin(client)
    response = client.post(
        "/api/v1/anomalies/rules",
        json={
            "name": "缺少 CSRF",
            "category": "workflow",
            "detector_type": "workflow_stalled",
            "params": {},
        },
    )
    assert response.status_code == 403


def test_rule_edit_keeps_identity_and_new_occurrence_after_recovery(client):
    master_id = _owner(client)
    _stalled_workflow(client)
    headers = _admin(client)
    rule = _create_stalled_rule(client, headers)

    preview_payload = {
        "name": "试算工作流停滞",
        "category": "workflow",
        "detector_type": "workflow_stalled",
        "scope_type": "platform",
        "params": {"max_idle_hours": 1},
        "status": "draft",
        "change_reason": "只试算不保存",
    }
    rules_before = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    preview = client.post("/api/v1/anomalies/rules/preview", headers=headers, json=preview_payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["matches"] == 1
    assert len(preview.json()["samples"]) == 1
    saved_rules = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    assert len(saved_rules) == len(rules_before)
    assert next(item for item in saved_rules if item["id"] == rule["id"])["version"] == 2

    first_scan = _evaluate(client, headers)
    assert first_scan["matches"] == 1
    first = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]
    assert first["occurrence"] == 1

    _evaluate(client, headers)
    repeated = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]
    assert repeated["id"] == first["id"]
    assert repeated["hit_count"] == 2

    updated = {
        "name": rule["name"],
        "category": rule["category"],
        "detector_type": rule["detector_type"],
        "scope_type": rule["scope_type"],
        "scope_value": rule["scope_value"],
        "params": {"max_idle_hours": 1000},
        "status": "enabled",
        "change_reason": "提高阈值验证恢复",
    }
    response = client.put(f"/api/v1/anomalies/rules/{rule['id']}", headers=headers, json=updated)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == rule["id"]
    assert response.json()["version"] == 3
    detail = client.get(f"/api/v1/anomalies/rules/{rule['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert [audit["action"] for audit in detail.json()["audits"]] == [
        "updated",
        "updated",
        "created",
    ]
    _evaluate(client, headers)
    assert client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["total"] == 0

    updated["params"] = {"max_idle_hours": 1}
    updated["change_reason"] = "恢复阈值验证新周期"
    assert (
        client.put(
            f"/api/v1/anomalies/rules/{rule['id']}", headers=headers, json=updated
        ).status_code
        == 200
    )
    _evaluate(client, headers)
    second = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]
    assert second["id"] != first["id"]
    assert second["occurrence"] == 2

    global_view = client.get("/api/v1/anomalies/events?admin_view=true", headers=headers)
    assert global_view.status_code == 200, global_view.text
    assert global_view.json()["total"] == 1


def test_archive_review_is_atomic_and_issue_creation_is_idempotent(client):
    master_id = _owner(client)
    _stalled_workflow(client)
    headers = _admin(client)
    _create_stalled_rule(client, headers)
    _evaluate(client, headers)
    event = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]

    requested = client.post(
        f"/api/v1/anomalies/events/{event['id']}/archive-requests",
        json={"reason": "测试工作流不应进入统计", "requested_by": "异常值守"},
    )
    assert requested.status_code == 201, requested.text
    request_id = uuid.UUID(requested.json()["id"])

    with Session(client.app.state.engine) as session:
        row = session.get(AnomalyArchiveRequest, request_id)
        row.target_id = "00000000-0000-0000-0000-000000000099"
        session.commit()
    failed = client.post(
        f"/api/v1/anomalies/archive-requests/{request_id}/review",
        headers=headers,
        json={"approved": True, "note": "验证事务回滚"},
    )
    assert failed.status_code == 404
    with Session(client.app.state.engine) as session:
        request_row = session.get(AnomalyArchiveRequest, request_id)
        event_row = session.get(AnomalyEvent, uuid.UUID(event["id"]))
        workflow = session.scalar(select(WorkflowRun))
        assert request_row.status == "pending"
        assert event_row.disposition == "archive_pending"
        assert workflow.deleted is False

    rejected = client.post(
        f"/api/v1/anomalies/archive-requests/{request_id}/review",
        headers=headers,
        json={"approved": False, "note": "目标范围有误"},
    )
    assert rejected.status_code == 200, rejected.text

    issue = client.post(
        f"/api/v1/anomalies/events/{event['id']}/issues",
        json={"suggestion": "改进工作流停滞提示", "reporter": "异常值守", "assignee": "张轶勃"},
    )
    assert issue.status_code == 201, issue.text
    duplicate = client.post(
        f"/api/v1/anomalies/events/{event['id']}/issues",
        json={"suggestion": "重复创建", "reporter": "异常值守", "assignee": "张轶勃"},
    )
    assert duplicate.status_code == 409
    assert client.get(f"/api/v1/issues/{issue.json()['issue_id']}").status_code == 200


def test_disabling_rule_closes_open_event_with_explicit_reason(client):
    master_id = _owner(client)
    _stalled_workflow(client)
    headers = _admin(client)
    rule = _create_stalled_rule(client, headers)
    _evaluate(client, headers)

    response = client.post(
        f"/api/v1/anomalies/rules/{rule['id']}/status",
        headers=headers,
        json={"status": "disabled", "reason": "临时停用验证"},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["total"] == 0
    history = client.get(
        f"/api/v1/anomalies/events?ai_master_id={master_id}&include_closed=true",
        headers=headers,
    ).json()["items"]
    assert history[0]["detection_status"] == "recovered"
    assert history[0]["closed_reason"] == "rule_disabled"


def test_archive_approval_updates_data_and_event_together(client):
    master_id = _owner(client)
    _stalled_workflow(client)
    headers = _admin(client)
    _create_stalled_rule(client, headers)
    _evaluate(client, headers)
    event = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]
    requested = client.post(
        f"/api/v1/anomalies/events/{event['id']}/archive-requests",
        json={"reason": "确认是测试工作流", "requested_by": "异常值守"},
    ).json()
    approved = client.post(
        f"/api/v1/anomalies/archive-requests/{requested['id']}/review",
        headers=headers,
        json={"approved": True, "note": "同意归档"},
    )
    assert approved.status_code == 200, approved.text
    detail = client.get(f"/api/v1/anomalies/events/{event['id']}").json()
    assert detail["detection_status"] == "recovered"
    assert detail["disposition"] == "archived"
    assert detail["closed_reason"] == "data_archived"
    with Session(client.app.state.engine) as session:
        workflow = session.scalar(select(WorkflowRun))
        assert workflow.deleted is True
        assert workflow.deleted_reason_code == "anomaly_archive"


def test_every_detector_supports_default_dry_run(client):
    headers = _admin(client)
    # 启动时已经为全部内置检测类型预置规则，重复创建应被拒绝而不是产生第二条规则。
    first = client.post(
        "/api/v1/anomalies/rules",
        headers=headers,
        json={
            "name": "重复的工作流停滞",
            "category": "workflow",
            "detector_type": "workflow_stalled",
            "scope_type": "platform",
            "params": {},
            "status": "enabled",
            "change_reason": "验证检测类型唯一",
        },
    )
    assert first.status_code == 409, first.text
    assert first.json()["code"] == "RULE_DETECTOR_ALREADY_CONFIGURED"
    # 预置规则默认停用；启用全部后逐一试算，确保每个检测器都能跑默认参数。
    items = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    for item in items:
        toggled = client.post(
            f"/api/v1/anomalies/rules/{item['id']}/status",
            headers=headers,
            json={"status": "enabled", "reason": "试算默认参数"},
        )
        assert toggled.status_code == 200, toggled.text
    result = client.post("/api/v1/anomalies/rules/evaluate?dry_run=true", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["rules"] == len(DETECTOR_SPECS)


def test_startup_seeds_every_builtin_rule_once(client):
    headers = _admin(client)
    items = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    assert {item["detector_type"] for item in items} == set(DETECTOR_SPECS)
    assert all(item["allow_archive"] is True for item in items)
    # 新补齐的规则保持停用，管理员确认后才启用。
    assert all(item["status"] == "disabled" for item in items)

    # 再次执行幂等补齐（等价于服务重启），既不重建也不改动已有配置。
    with Session(client.app.state.engine) as session:
        created = AnomalyService(session, client.app.state.projects).ensure_builtin_rules()
    assert created == 0
    again = client.get("/api/v1/anomalies/rules", headers=headers).json()["items"]
    assert {item["id"] for item in again} == {item["id"] for item in items}


def test_archive_request_is_rejected_when_rule_disallows_it(client):
    master_id = _owner(client)
    _stalled_workflow(client)
    headers = _admin(client)
    rule = _create_stalled_rule(client, headers)
    _evaluate(client, headers)
    event = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"][0]
    assert event["archive_supported"] is True

    closed = client.put(
        f"/api/v1/anomalies/rules/{rule['id']}",
        headers=headers,
        json={
            "name": rule["name"],
            "category": rule["category"],
            "detector_type": rule["detector_type"],
            "scope_type": rule["scope_type"],
            "scope_value": rule["scope_value"],
            "params": rule["params"],
            "allow_archive": False,
            "status": "enabled",
            "change_reason": "关闭该类异常的屏蔽入口",
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["allow_archive"] is False

    listing = client.get(f"/api/v1/anomalies/events?ai_master_id={master_id}").json()["items"]
    assert listing[0]["id"] == event["id"]
    assert listing[0]["archive_supported"] is False

    denied = client.post(
        f"/api/v1/anomalies/events/{event['id']}/archive-requests",
        json={"reason": "规则已关闭屏蔽", "requested_by": "异常值守"},
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["code"] == "ARCHIVE_NOT_ALLOWED"
    detail = client.get(f"/api/v1/anomalies/events/{event['id']}").json()
    assert detail["disposition"] == "open"
