from __future__ import annotations

import threading
import time
from copy import deepcopy

from test_benchmark import draft_data

from aaw_skill_eval.modules.designer.planning import DesignUnavailable, normalize_plan

ROUTE = "/api/v1/benchmark/drafts"


def wait_for(client, key, predicate):
    for _ in range(250):
        item = client.get(f"{ROUTE}/{key}").json()
        if predicate(item):
            return item
        time.sleep(0.02)
    raise AssertionError(item)


def terminal(client, key):
    return wait_for(
        client,
        key,
        lambda item: item["status"] not in {"discussing", "analyzing", "generating", "validating"},
    )


def plan_data():
    return {
        "action": "generate",
        "message": "先展示任务草案",
        "cases": [
            {"id": "task", "name": "交付说明", "input": "交付 result.md", "expected": "描述实现"}
        ],
        "dimensions": [{"id": "maintainability"}, {"id": "correctness"}],
        "suggestions": [{"text": "补充截图"}],
    }


def create(client, project, skill):
    data = draft_data(project, skill)
    data["packages"] = {}
    return client.post(ROUTE, json={"data": data}).json()


def send(client, item, message="生成用例", mode="generate"):
    response = client.post(
        f"{ROUTE}/{item['id']}/messages",
        json={
            "revision": item["revision"],
            "message": message,
            "mode": mode,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def fixture_code(project, skill):
    from aaw_skill_eval.modules.designer.packages import documents_from_package

    doc = documents_from_package(
        draft_data(project, skill)["packages"]["correctness"], "correctness"
    )
    return {
        "cases": [{"id": "task", "graders": doc["manifest"]["cases"][0]["graders"]}],
        "assets": doc["assets"],
    }


def test_draft_visible_while_code_pending_and_chat_does_not_regenerate(
    client, project, skill, monkeypatch
):
    gate = threading.Event()
    calls = []
    code = fixture_code(project, skill)

    class Provider:
        def plan(self, *args, mode, **kwargs):
            return (
                plan_data()
                if mode == "generate"
                else {"action": "discuss", "message": "这里只解释维度"}
            )

        def dimension(self, *args, **kwargs):
            calls.append(args[4])
            assert gate.wait(5)
            return code

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    try:
        item = wait_for(
            client,
            item["id"],
            lambda x: (
                x.get("workflow", {}).get("dimensions", {}).get("correctness", {}).get("status")
                == "generating"
            ),
        )
        assert item["preview"]["cases"][0]["input"] == "交付 result.md"
        assert "补充截图" not in item["preview"]["cases"][0]["expected"]
        assert item["workflow"]["dimensions"]["maintainability"]["status"] == "ready"
        packages = deepcopy(item["data"]["packages"])
        send(client, item, "为什么选择这些维度？", "auto")
        item = wait_for(
            client, item["id"], lambda x: x["workflow"]["interaction"]["status"] == "completed"
        )
        assert item["data"]["packages"] == packages
        assert item["status"] == "generating"
    finally:
        gate.set()
    item = terminal(client, item["id"])
    assert item["status"] == "ready", item
    assert calls == ["correctness"]
    assert item["validation"]["scripts_runnable"]
    assert (
        client.post(f"{ROUTE}/{item['id']}/save", json={"revision": item["revision"]}).status_code
        == 201
    )


def test_failed_dimension_retries_locally_and_manual_retry_preserves_success(
    client, project, skill, monkeypatch
):
    calls = []
    code = fixture_code(project, skill)

    class Provider:
        def plan(self, *args, **kwargs):
            return plan_data()

        def dimension(self, *args, repair=None, **kwargs):
            calls.append(repair)
            if len(calls) < 3:
                return {"cases": [], "assets": {}}
            raise DesignUnavailable("模型暂不可用")

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    item = terminal(client, item["id"])
    assert item["status"] == "failed"
    assert len(calls) == 3
    assert calls[1]["error"]
    preserved = item["data"]["packages"]["maintainability"]

    class Repaired(Provider):
        def dimension(self, *args, **kwargs):
            return code

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Repaired)
    send(client, item, "重试", "retry")
    item = terminal(client, item["id"])
    assert item["status"] == "ready", item
    assert item["data"]["packages"]["maintainability"] == preserved


def test_stop_fences_late_model_output(client, project, skill, monkeypatch):
    gate = threading.Event()
    entered = threading.Event()

    class Provider:
        def plan(self, *args, **kwargs):
            entered.set()
            assert gate.wait(5)
            return plan_data()

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    assert entered.wait(5)
    stopped = client.post(f"{ROUTE}/{item['id']}/cancel", json={}).json()
    gate.set()
    time.sleep(0.1)
    current = client.get(f"{ROUTE}/{item['id']}").json()
    assert current["status"] == "draft"
    assert current["revision"] == stopped["revision"]
    assert not current.get("preview")


def test_transport_error_never_auto_retries(client, project, skill, monkeypatch):
    calls = []

    class Provider:
        def plan(self, *args, **kwargs):
            return plan_data()

        def dimension(self, *args, **kwargs):
            calls.append(1)
            raise DesignUnavailable("本阶段超时，可重试或切换模型")

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    item = terminal(client, item["id"])
    assert item["status"] == "failed"
    assert calls == [1]
    assert item["workflow"]["dimensions"]["maintainability"]["status"] == "ready"


def test_normalize_rejects_invented_dimension():
    import pytest

    plan = plan_data()
    plan["dimensions"] = [{"id": "invented"}]
    with pytest.raises(ValueError):
        normalize_plan(plan, {})


def test_new_task_supersedes_inflight_dimension(client, project, skill, monkeypatch):
    gate, entered = threading.Event(), threading.Event()
    code = fixture_code(project, skill)

    class Provider:
        def plan(self, settings, data, summary, previous, messages, *args, **kwargs):
            result = plan_data()
            if messages[-1]["content"] == "改为只交付设计说明":
                result["action"] = "update"
                result["cases"][0]["input"] = "只交付设计说明"
                result["dimensions"] = [{"id": "maintainability"}]
            return result

        def dimension(self, *args, **kwargs):
            entered.set()
            assert gate.wait(10)
            return code

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    assert entered.wait(5)
    try:
        item = client.get(f"{ROUTE}/{item['id']}").json()
        send(client, item, "改为只交付设计说明", "auto")
        changed = terminal(client, item["id"])
        assert changed["status"] == "ready", changed
    finally:
        gate.set()
    time.sleep(0.1)
    item = client.get(f"{ROUTE}/{item['id']}").json()
    assert item["preview"]["cases"][0]["input"] == "只交付设计说明"
    assert list(item["data"]["packages"]) == ["maintainability"]
    assert item["revision"] == changed["revision"]


def test_suggestion_requires_explicit_adoption(client, project, skill, monkeypatch):
    class Provider:
        def plan(self, settings, data, summary, previous, messages, *args, **kwargs):
            result = plan_data()
            result["dimensions"] = [{"id": "maintainability"}]
            if "采纳" in messages[-1]["content"]:
                result["cases"][0]["expected"] += "，补充截图"
            return result

    monkeypatch.setitem(FLOW_PROVIDERS, "chrys", Provider)
    item = create(client, project, skill)
    send(client, item)
    item = terminal(client, item["id"])
    assert "补充截图" not in item["preview"]["cases"][0]["expected"]
    response = client.post(
        f"{ROUTE}/{item['id']}/suggestions/suggestion-1",
        json={"action": "adopt", "revision": item["revision"]},
    )
    assert response.status_code == 200, response.text
    item = terminal(client, item["id"])
    assert item["status"] == "ready", item
    assert "补充截图" in item["preview"]["cases"][0]["expected"]
    assert item["workflow"]["plan"]["suggestions"][0]["status"] == "adopted"


from aaw_skill_eval.contracts.providers import DESIGNERS as FLOW_PROVIDERS
