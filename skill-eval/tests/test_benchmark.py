from __future__ import annotations

import json
import sys
import threading
import time
from copy import deepcopy

from aaw_skill_eval.models import Experiment, Run, SuiteDraft
from aaw_skill_eval.schemas import EvalProfile, ExperimentCreateRequest
from aaw_skill_eval.services.catalog.designer import (
    DESIGNER_PROVIDERS,
    compile_draft,
    package_from_documents,
    validate_draft,
)
from aaw_skill_eval.services.orchestration import execution, prepare


def draft_data(project, skill):
    script = (
        "import json, os\nfrom pathlib import Path\n"
        "root = Path(os.environ['AAW_WORKSPACE'])\n"
        "assert root.is_dir()\n"
        "checks = [{'id': key, 'score': 100 if (root/'result.md').exists() else 0, "
        "'weight': 1, 'evidence': '检查实际交付 result.md'} "
        "for key in ['required-behavior','edge-cases']]\n"
        "print(json.dumps({'checks': checks}))\n"
    )
    scene = {
        "id": "joint-scene",
        "name": "代码与文档联合交付",
        "input": "交付 result.md",
        "expected": "与项目一致的实现与说明",
        "graders": [
            {
                "type": "command",
                "command": f'"{sys.executable}" validate.py',
                "result_format": "json",
                "checkpoint_ids": ["required-behavior", "edge-cases"],
                "files": ["validate.py"],
            }
        ],
    }
    llm_scene = {**scene, "graders": []}
    return {
        "name": "固定测试套",
        "project_path": str(project),
        "skill_path": str(skill),
        "requirement": "验证代码和文档交付",
        "generator_provider": "chrys",
        "generator_model": "fixture",
        "dimensions": [{"id": "correctness"}, {"id": "maintainability"}],
        "packages": {
            "correctness": package_from_documents(
                "correctness", {"cases": [scene]}, {"validate.py": script}
            ),
            "maintainability": package_from_documents(
                "maintainability", {"cases": [llm_scene]}, {}
            ),
        },
    }


def wait_draft(client, key):
    for _ in range(200):
        item = client.get(f"/api/v1/benchmark/drafts/{key}").json()
        if item["status"] not in {"analyzing", "generating", "validating"}:
            return item
        time.sleep(0.05)
    raise AssertionError("draft timed out")


def test_name_only_suite_stays_pending_until_configured(client):
    route = "/api/v1/benchmark/drafts"
    created = client.post(route, json={"data": {"name": "稍后配置"}})
    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "draft"
    assert item["created_at"]
    assert client.get(f"{route}/{item['id']}").json()["data"] == {"name": "稍后配置"}
    assert item["id"] in {entry["id"] for entry in client.get(route).json()["items"]}
    assert item["id"] not in {
        entry["id"] for entry in client.get("/api/v1/benchmark/suites").json()["items"]
    }
    assert (
        client.post(f"{route}/{item['id']}/save", json={"revision": item["revision"]}).status_code
        == 422
    )
    edited = client.put(
        f"{route}/{item['id']}",
        json={
            "data": {"name": "稍后配置", "requirement": "补充诉求"},
            "revision": item["revision"],
        },
    ).json()
    assert edited["created_at"] == item["created_at"]


def save_fixture(client, project, skill):
    created = client.post("/api/v1/benchmark/drafts", json={"data": draft_data(project, skill)})
    assert created.status_code == 201, created.text
    item = created.json()
    response = client.post(
        f"/api/v1/benchmark/drafts/{item['id']}/validate", json={"revision": item["revision"]}
    )
    assert response.status_code == 202, response.text
    checked = wait_draft(client, item["id"])
    assert checked["validation"].get("scripts_runnable"), checked
    response = client.post(
        f"/api/v1/benchmark/drafts/{item['id']}/save", json={"revision": checked["revision"]}
    )
    assert response.status_code == 201, response.text
    return response.json(), checked


def test_shared_scene_is_compiled_once_and_standards_cannot_be_overridden(project, skill):
    data = draft_data(project, skill)
    result = compile_draft(data)
    assert len(result.cases) == 1
    assert set(result.cases[0].dimension_weights) == {"correctness", "maintainability"}
    assert any(g.type == "llm_rubric" for g in result.cases[0].graders)
    changed = deepcopy(data)
    changed["dimensions"][0]["id"] = "custom"
    import pytest

    with pytest.raises(ValueError):
        compile_draft(changed)


def test_isolated_validation_checks_protocol_without_modifying_source(
    client, project, skill, tmp_path
):
    result = validate_draft(
        client.app.state.settings, draft_data(project, skill), tmp_path / "check", run_scripts=True
    )
    assert result["scripts_runnable"]
    assert result["checks"][0]["details"][0]["checks"][0]["score"] == 0
    assert not (project / "result.md").exists()
    assert not (project / "validate.py").exists()
    assert result["assertion_validity"] == "待人工确认"


def test_draft_lock_copy_and_archive_lifecycle(client, project, skill):
    suite, checked = save_fixture(client, project, skill)
    key = checked["id"]
    assert (
        client.put(
            f"/api/v1/benchmark/drafts/{key}",
            json={"data": checked["data"], "revision": checked["revision"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/benchmark/drafts/{key}/save", json={"revision": checked["revision"]}
        ).status_code
        == 409
    )
    copy = client.post(f"/api/v1/benchmark/suites/{suite['id']}/copy", json={}).json()
    assert copy["status"] == "draft"
    assert copy["data"]["packages"] == checked["data"]["packages"]
    assert client.post(
        f"/api/v1/benchmark/suites/{suite['id']}/archive", json={"archived": True}
    ).json()["archived"]
    assert not client.post(
        f"/api/v1/benchmark/suites/{suite['id']}/archive", json={"archived": False}
    ).json()["archived"]
    assert client.get(f"/api/v1/benchmark/suites/{suite['id']}").json()["locked"]


def test_save_requires_current_validation_and_edits_invalidate_it(client, project, skill):
    data = draft_data(project, skill)
    item = client.post("/api/v1/benchmark/drafts", json={"data": data}).json()
    route = f"/api/v1/benchmark/drafts/{item['id']}"
    assert client.post(route + "/save", json={"revision": item["revision"]}).status_code == 422
    checked = client.post(route + "/validate", json={"revision": item["revision"]})
    assert checked.status_code == 202
    checked = wait_draft(client, item["id"])
    edited = client.put(
        route, json={"revision": checked["revision"], "data": {**data, "name": "已修改"}}
    ).json()
    assert edited["validation"] == {}
    assert (
        client.put(route, json={"revision": checked["revision"], "data": data}).status_code == 409
    )
    assert client.post(route + "/save", json={"revision": edited["revision"]}).status_code == 422


def test_invalid_draft_returns_actionable_error(client):
    item = client.post("/api/v1/benchmark/drafts", json={"data": {}}).json()
    response = client.post(
        f"/api/v1/benchmark/drafts/{item['id']}/validate", json={"revision": item["revision"]}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_DRAFT"


def test_generating_draft_blocks_edits_and_persists_chat(client, project, skill, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    class FixtureDesigner:
        def generate(self, settings, data, messages, root, progress, cancelled):
            entered.set()
            release.wait(10)
            assert messages[-1]["content"] == "补充边界场景"
            progress("generating", "生成项目相关用例")
            return data, "已生成可编辑用例"

    monkeypatch.setitem(DESIGNER_PROVIDERS, "chrys", FixtureDesigner)
    item = client.post("/api/v1/benchmark/drafts", json={"data": draft_data(project, skill)}).json()
    route = f"/api/v1/benchmark/drafts/{item['id']}"
    next_item = client.post(
        route + "/generate", json={"revision": item["revision"], "message": "补充边界场景"}
    )
    assert next_item.status_code == 202
    assert entered.wait(5)
    try:
        assert (
            client.put(
                route, json={"revision": next_item.json()["revision"], "data": {}}
            ).status_code
            == 409
        )
        assert (
            client.post(
                route + "/generate",
                json={"revision": next_item.json()["revision"], "message": "重复"},
            ).status_code
            == 409
        )
    finally:
        release.set()
    result = wait_draft(client, item["id"])
    assert result["status"] == "ready"
    assert result["validation"]["structure_passed"]
    assert not result["validation"]["scripts_checked"]
    assert [entry["role"] for entry in result["messages"]] == ["user", "status", "assistant"]


def test_current_only_execution_and_historical_baseline(client, project, skill, monkeypatch):
    from test_test_packages import wait_experiment

    from aaw_skill_eval.services.providers.base import JudgeOutcome, JudgeScore

    class FixedJudge:
        def evaluate(self, *, graders, **kwargs):
            return JudgeOutcome(
                scores=[
                    JudgeScore(
                        grader_id=g.id,
                        score=100,
                        evidence="result.md 中的实际交付",
                        reasoning="满足固定标准",
                    )
                    for g in graders
                ]
            )

    client.app.state.orchestrator.judge = FixedJudge()

    monkeypatch.setattr(prepare, "enrich_profile", lambda settings, profile, **kwargs: profile)
    monkeypatch.setattr(prepare, "verify_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(execution, "verify_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(prepare, "prepare_experiment_chrys_template", lambda *args: None)
    suite, _ = save_fixture(client, project, skill)
    route = f"/api/v1/benchmark/suites/{suite['id']}"
    config = {
        "mode": "quick",
        "profile": {
            "runner_provider": "chrys",
            "judge_provider": "chrys",
            "runner_model": "fixture",
            "judge_model": "fixture",
        },
    }
    created = client.post(route + "/execute", json=config)
    assert created.status_code == 202, created.text
    first = wait_experiment(client, created.json()["id"])
    assert first["evaluation_mode"] == "current_only"
    assert {run["group"] for run in first["runs"]} == {"current"}
    assert first["status"] == "completed", first
    base = client.post(route + "/baseline", json={"experiment_id": first["id"]})
    assert base.status_code == 200, base.text
    second_id = client.post(route + "/execute", json=config).json()["id"]
    second = wait_experiment(client, second_id)
    assert client.get(route + f"/comparison/{second_id}").json()["formal"]
    # A group is selected explicitly; unavailable groups cannot silently fall back to current.
    assert (
        client.post(
            route + "/baseline",
            json={
                "experiment_id": first["id"],
                "group": "no_skill",
            },
        ).status_code
        == 422
    )
    with client.app.state.session_factory() as session:
        original = session.get(Experiment, first["id"]).runs[0]
        snapshot = json.loads(original.score_json)
        for dimension in snapshot["dimensions"]:
            dimension["score"] = 40
            dimension["passed"] = False
        no_skill = Run(
            experiment_id=first["id"],
            case_id=original.case_id,
            group_name="no_skill",
            trial_index=1,
            anonymous_id="no-skill-fixture",
            status="completed",
            quality_score=40,
            score_json=json.dumps(snapshot),
        )
        session.add(no_skill)
        # Eligibility belongs to the chosen group, even when the current group failed gates.
        original.hard_gates_total = 1
        original.hard_gates_passed = 0
        session.commit()
        no_skill_id = no_skill.id
    selected_base = client.post(
        route + "/baseline",
        json={
            "experiment_id": first["id"],
            "group": "no_skill",
        },
    )
    assert selected_base.status_code == 200, selected_base.text
    payload = client.get(route).json()
    assert payload["baseline_group"] == payload["baseline"]["selected_group"] == "no_skill"
    assert payload["baseline"]["scores"]["no_skill"] == 40
    assert client.get(route + f"/comparison/{second_id}").json() == {
        "formal": True,
        "reasons": [],
        "delta": 60,
    }
    assert (
        client.post(
            route + "/baseline",
            json={
                "experiment_id": first["id"],
                "group": "baseline",
            },
        ).status_code
        == 400
    )
    with client.app.state.session_factory() as session:
        invalid_base = session.get(Run, no_skill_id)
        invalid_base.hard_gates_total = 1
        invalid_base.hard_gates_passed = 0
        session.commit()
    assert not client.get(route + f"/comparison/{second_id}").json()["formal"]
    assert (
        client.post(
            route + "/baseline",
            json={
                "experiment_id": first["id"],
                "group": "no_skill",
            },
        ).status_code
        == 422
    )
    assert client.post(route + "/baseline", json={"experiment_id": None}).json()["baseline"] is None
    assert client.get(route + f"/comparison/{second_id}").json()["delta"] is None
    with client.app.state.session_factory() as session:
        session.get(Experiment, first["id"]).runs[0].hard_gates_total = 0
        session.commit()
    assert client.post(route + "/baseline", json={"experiment_id": first["id"]}).status_code == 200
    with client.app.state.session_factory() as session:
        exp = session.get(Experiment, second_id)
        exp.project_commit = "changed"
        session.commit()
    comparison = client.get(route + f"/comparison/{second_id}").json()
    assert not comparison["formal"] and "项目提交有变化" in comparison["reasons"]
    assert second["suite_snapshot"]["cases"] == first["suite_snapshot"]["cases"]


def test_archive_rejects_active_execution(client, project, skill, monkeypatch):
    monkeypatch.setattr(prepare, "enrich_profile", lambda settings, profile, **kwargs: profile)
    suite, _ = save_fixture(client, project, skill)
    exp = client.app.state.orchestrator.create(
        ExperimentCreateRequest(
            suite_id=suite["id"],
            evaluation_mode="current_only",
            mode="quick",
            profile=EvalProfile(runner_model="fixture", judge_model="fixture"),
        )
    )
    assert exp.status == "queued"
    assert (
        client.post(
            f"/api/v1/benchmark/suites/{suite['id']}/archive", json={"archived": True}
        ).status_code
        == 409
    )


def test_restart_recovers_designer_tasks(client):
    with client.app.state.session_factory() as session:
        item = SuiteDraft(status="generating")
        session.add(item)
        session.commit()
        key = item.id
    client.app.state.designer.recover()
    item = client.get(f"/api/v1/benchmark/drafts/{key}").json()
    assert item["status"] == "failed" and "服务重启" in item["error"]


def test_directory_picker_lists_local_directories(client, project):
    result = client.get(
        "/api/v1/benchmark/directories", params={"path": str(project.parent)}
    ).json()
    assert str(project) in {item["path"] for item in result["items"]}


def test_chrys_designer_repairs_invalid_generated_packages(
    client, project, skill, tmp_path, monkeypatch
):
    import json

    from aaw_skill_eval.services.catalog import designer
    from aaw_skill_eval.services.providers.base import RunOutcome

    calls = []

    class RepairRunner:
        def __init__(self, settings):
            pass

        def run(self, *, workspace, case, **kwargs):
            calls.append(case.input)
            scene = {
                "id": "scene",
                "name": "说明交付",
                "input": "生成说明",
                "expected": "准确清楚",
                "graders": [],
            }
            result = {
                "message": "已生成",
                "packages": [
                    {"dimension_id": "clarity", "manifest": {"cases": [scene]}, "assets": {}}
                ],
            }
            if len(calls) == 1:
                scene["workflow"] = {"entry": "sr", "sr": {}}
            (workspace / "draft-packages.json").write_text(json.dumps(result), encoding="utf-8")
            return RunOutcome(exit_code=0, final_response="已生成", events=[], duration_ms=1)

    monkeypatch.setattr(designer, "ChrysRunner", RepairRunner)
    monkeypatch.setattr(designer, "enrich_profile", lambda settings, profile, **kwargs: profile)
    monkeypatch.setattr(designer, "prepare_isolated_home", lambda settings, **kwargs: None)
    data = {
        "name": "修复测试",
        "project_path": str(project),
        "skill_path": str(skill),
        "generator_model": "fixture",
        "dimensions": [{"id": "clarity"}],
    }
    result, message = designer.ChrysDesigner().generate(
        client.app.state.settings,
        data,
        [
            {"role": "user", "content": "生成用例"},
            {"role": "status", "content": "内部状态不应进入提示词"},
        ],
        tmp_path / "designer",
        lambda *args: None,
        lambda: False,
    )
    assert len(calls) == 2 and "错误" in calls[1]
    assert "内部状态不应进入提示词" not in calls[0]
    assert str(project) not in calls[0] and str(skill) not in calls[0]
    assert compile_draft(result).cases[0].workflow is None
    assert message == "已生成"
    assert not (project / "draft-packages.json").exists()


def test_additional_agent_can_register_runtime_runner_and_judge(client, monkeypatch):
    from aaw_skill_eval.schemas import ProviderSnapshot
    from aaw_skill_eval.services import providers
    from aaw_skill_eval.services.providers.chrys.runtime import enrich_profile
    from aaw_skill_eval.services.providers.registry import RUNTIME_FACTORIES

    class Runtime:
        def __init__(self, settings):
            pass

        def snapshot(self, model, *, role):
            return ProviderSnapshot(provider="extra", model_profile_id=model)

    # Restore registries after the test; no changes to existing agent registrations.
    monkeypatch.setattr(providers, "_RUNNERS", dict(providers._RUNNERS))
    monkeypatch.setattr(providers, "_JUDGES", dict(providers._JUDGES))
    monkeypatch.setitem(RUNTIME_FACTORIES, "extra", Runtime)
    providers.register_provider("extra", runner=Runtime, judge=Runtime, runtime=Runtime)
    profile = enrich_profile(
        client.app.state.settings,
        EvalProfile(
            runner_provider="extra", judge_provider="extra", runner_model="m", judge_model="m"
        ),
    )
    assert profile.runner_snapshot.provider == "extra"
    assert isinstance(providers.build_runner(client.app.state.settings, "extra"), Runtime)
