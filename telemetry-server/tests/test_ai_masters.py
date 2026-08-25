from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from conftest import message, sync, upload_diff
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from aaw_telemetry.config import (
    ComponentEntry,
    ComponentsDocument,
    ProjectEntry,
    ProjectRegistry,
)
from aaw_telemetry.database import Base
from aaw_telemetry.errors import ApiError
from aaw_telemetry.services.ai_masters import AiMasterService, tier_for
from aaw_telemetry.services.queries import make_filters


def _multi_project_registry() -> ProjectRegistry:
    return ProjectRegistry(
        ComponentsDocument(
            components={
                "comp-a": ComponentEntry(
                    name="组件A",
                    se="张三",
                    repos={"team/a": ProjectEntry(canonical_url="git@x/team/a.git")},
                ),
                "comp-b": ComponentEntry(
                    name="组件B",
                    se="李四",
                    repos={"team/b": ProjectEntry(canonical_url="git@x/team/b.git")},
                ),
                "comp-c": ComponentEntry(
                    name="组件C",
                    se=None,
                    repos={"team/c": ProjectEntry(canonical_url="git@x/team/c.git")},
                ),
            }
        )
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess
    engine.dispose()


@pytest.fixture
def service(session: Session) -> AiMasterService:
    return AiMasterService(session, _multi_project_registry())


def _filters():
    today = date.today()
    return make_filters(
        today - timedelta(days=29),
        today,
        [],
        [],
        [],
        [],
        [],
        "aaw",
    )


def test_tier_boundaries():
    assert tier_for(0.70) == "none"
    assert tier_for(0.65) == "none"   # >= 0.65 -> none
    assert tier_for(0.64) == "three"
    assert tier_for(0.50) == "three"  # 0.50 <= rate < 0.65 -> three
    assert tier_for(0.49) == "five"
    assert tier_for(0.0) == "five"
    assert tier_for(None) == "no_data"


def test_create_and_rename_and_delete(service: AiMasterService):
    created = service.create_ai_master("运营一")
    assert created["name"] == "运营一"

    renamed = service.rename_ai_master(uuid.UUID(created["id"]), "运营二")
    assert renamed["name"] == "运营二"

    masters = service.list_ai_masters()
    assert len(masters["items"]) == 1
    assert masters["items"][0]["name"] == "运营二"

    deleted = service.delete_ai_master(uuid.UUID(created["id"]))
    assert deleted["deleted"] is True
    assert service.list_ai_masters()["items"] == []


def test_create_duplicate_name_rejected(service: AiMasterService):
    service.create_ai_master("重复名")
    with pytest.raises(ApiError) as exc:
        service.create_ai_master("重复名")
    assert exc.value.status_code == 409


def test_assign_component(service: AiMasterService):
    master = service.create_ai_master("运营一")
    master_id = uuid.UUID(master["id"])

    result = service.assign_component("comp-a", master_id)
    assert result["ai_master_id"] == str(master_id)

    assignments = service.list_assignments()["assignments"]
    assert assignments == {"comp-a": str(master_id)}


def test_assign_unknown_component_rejected(service: AiMasterService):
    master = service.create_ai_master("运营一")
    with pytest.raises(ApiError) as exc:
        service.assign_component("does-not-exist", uuid.UUID(master["id"]))
    assert exc.value.status_code == 404


def test_reassign_moves_component(service: AiMasterService):
    m1 = service.create_ai_master("运营一")
    m2 = service.create_ai_master("运营二")
    service.assign_component("comp-a", uuid.UUID(m1["id"]))
    service.assign_component("comp-a", uuid.UUID(m2["id"]))
    assignments = service.list_assignments()["assignments"]
    assert assignments["comp-a"] == str(m2["id"])


def test_delete_master_unassigns_components(service: AiMasterService):
    m1 = service.create_ai_master("运营一")
    service.assign_component("comp-a", uuid.UUID(m1["id"]))
    service.assign_component("comp-b", uuid.UUID(m1["id"]))
    service.delete_ai_master(uuid.UUID(m1["id"]))
    assert service.list_assignments()["assignments"] == {}


def test_operations_groups_by_master_and_buckets_unassigned(service: AiMasterService):
    m1 = service.create_ai_master("运营一")
    service.create_ai_master("运营二")
    # comp-a, comp-b -> 运营一; comp-c remains unassigned.
    service.assign_component("comp-a", uuid.UUID(m1["id"]))
    service.assign_component("comp-b", uuid.UUID(m1["id"]))

    ops = service.operations(_filters())["items"]
    by_name = {c["name"]: c for c in ops}
    assert "运营一" in by_name
    assert "运营二" in by_name
    assert "未分配" in by_name

    # 运营一 owns two components; no adoption data -> both no_data.
    card = by_name["运营一"]
    assert card["total_components"] == 2
    assert card["tier_counts"] == {"none": 0, "three": 0, "five": 0, "no_data": 2}
    assert card["lowest_required_rate"] is None

    # 运营二 owns none.
    assert by_name["运营二"]["total_components"] == 0
    # 未分配 bucket holds the remaining component.
    assert by_name["未分配"]["total_components"] == 1


# ── API 路由层 ──────────────────────────────────────────


def test_ai_master_api_crud_and_assign(client):
    created = client.post("/api/v1/ai-masters", json={"name": "运营甲"})
    assert created.status_code == 201
    master_id = created.json()["id"]

    dup = client.post("/api/v1/ai-masters", json={"name": "运营甲"})
    assert dup.status_code == 409

    renamed = client.patch(f"/api/v1/ai-masters/{master_id}", json={"name": "运营甲改"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "运营甲改"

    listed = client.get("/api/v1/ai-masters").json()
    assert listed["items"][0]["name"] == "运营甲改"

    assigned = client.put(
        "/api/v1/ai-masters/assignments/example-component",
        json={"ai_master_id": master_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["ai_master_id"] == master_id

    assignments = client.get("/api/v1/ai-masters/assignments").json()
    assert assignments["assignments"]["example-component"] == master_id

    # 分配不存在的组件被拒绝
    bad = client.put(
        "/api/v1/ai-masters/assignments/no-such",
        json={"ai_master_id": master_id},
    )
    assert bad.status_code == 404


def test_ai_master_api_operations_and_delete(client):
    m1 = client.post("/api/v1/ai-masters", json={"name": "运营一"}).json()
    client.post("/api/v1/ai-masters", json={"name": "运营二"}).json()
    client.put(
        "/api/v1/ai-masters/assignments/example-component",
        json={"ai_master_id": m1["id"]},
    )

    ops = client.get("/api/v1/ai-masters/operations").json()["items"]
    by_name = {c["name"]: c for c in ops}
    assert by_name["运营一"]["total_components"] == 1
    assert by_name["运营二"]["total_components"] == 0
    assert "未分配" not in by_name  # 单组件已全部分配，无未分配桶

    detail = client.get(
        f"/api/v1/ai-masters/{m1['id']}/components"
    ).json()
    assert detail["name"] == "运营一"
    assert len(detail["items"]) == 1
    assert detail["items"][0]["component_id"] == "example-component"
    assert detail["items"][0]["tier"] == "no_data"

    deleted = client.delete(f"/api/v1/ai-masters/{m1['id']}")
    assert deleted.json()["deleted"] is True
    # 删除后归属清空（回未分配）
    assignments = client.get("/api/v1/ai-masters/assignments").json()
    assert assignments["assignments"] == {}


def test_operations_uses_real_adoption_rate_tier(client):
    # 通过真实遥测数据让组件产生高采纳率，验证档位按 rates 判定。
    dev = message(workflow_completed=False)
    sync(client, dev)
    upload_diff(client, dev)  # StubAttributionService -> attributed = total -> rate 1.0
    m1 = client.post("/api/v1/ai-masters", json={"name": "运营一"}).json()
    client.put(
        "/api/v1/ai-masters/assignments/example-component",
        json={"ai_master_id": m1["id"]},
    )
    ops = client.get("/api/v1/ai-masters/operations").json()["items"]
    card = next(c for c in ops if c["name"] == "运营一")
    # 采纳率为 1.0，归"无要求"档，且运营抓手不再有需处理组件。
    assert card["tier_counts"]["none"] == 1
    assert card["tier_counts"]["no_data"] == 0
    assert card["lowest_required_rate"] is None
