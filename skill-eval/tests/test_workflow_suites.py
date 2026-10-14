from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from test_detail_page_structure import _run_scenario
from test_test_packages import wait_experiment

from aaw_skill_eval.config import Settings
from aaw_skill_eval.schemas import CaseSpec, EvalProfile, WorkflowSpec
from aaw_skill_eval.services.catalog.packages import (
    PackageImportRequest,
    import_package,
    standard_example_package,
)
from aaw_skill_eval.services.catalog.workflow_adapter import build_workflow_adapter
from aaw_skill_eval.services.evaluation.workflow import (
    collect_terminal_outputs,
    inspect_workflow,
    runner_case,
)
from aaw_skill_eval.services.providers.codex.runner import CodexRunner, _isolated_environment
from aaw_skill_eval.standards import get_dimension

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def workflow_adapter(tmp_path_factory):
    return build_workflow_adapter(ROOT, tmp_path_factory.mktemp("aaw-adapter") / "candidate")


def package(dimension, entry="dev"):
    return import_package(
        PackageImportRequest(
            catalog_version=1,
            skill_type="workflow",
            dimension_id=dimension,
            zip_base64=base64.b64encode(
                standard_example_package("workflow", dimension, entry)
            ).decode(),
        ),
        require_standard=True,
    )["cases"]


def joint_request(project, skill):
    code = package("correctness")[0]
    document = package("completeness")[0]
    code["graders"] += document["graders"]
    return {
        "name": "Joint workflow",
        "project_path": str(project),
        "skill_path": str(skill),
        "catalog_version": 1,
        "skill_type": "workflow",
        "dimensions": [get_dimension("workflow", dim) for dim in ("correctness", "completeness")],
        "cases": [code],
    }


def test_joint_suite_saves_both_groups_and_shared_workflow(client, project, skill):
    response = client.post("/api/v1/suites", json=joint_request(project, skill))
    assert response.status_code == 201, response.text
    definition = client.get(f"/api/v1/suites/{response.json()['id']}").json()["definition"]
    assert response.json()["has_workflow"] is True
    assert {d["group"] for d in definition["dimensions"]} == {"development", "documents_analysis"}
    assert len(definition["cases"]) == 1
    assert definition["cases"][0]["workflow"]["entry"] == "dev"


def test_frontend_merges_document_and_code_checks_in_one_execution(tmp_path):
    dimensions = [get_dimension("workflow", d) for d in ("correctness", "completeness")]
    result = _run_scenario(
        tmp_path,
        f"""
state.skillType = 'workflow'; state.catalogVersion = 1;
state.dimensions = {json.dumps(dimensions)};
const packages = {json.dumps([package("correctness"), package("completeness")])};
state.dimensions.forEach((d,i) => {{
  d.cases=packages[i]; d.editor=JSON.stringify(editableCases(d.cases));
}});
const suite = buildDimensionSuite();
console.log(JSON.stringify({{count:suite.cases.length, checks:suite.cases[0].graders.length,
    entry:suite.cases[0].workflow.entry, scope:suite.skill_type}}));
""",
    )
    assert result == {"count": 1, "checks": 3, "entry": "dev", "scope": "workflow"}


@pytest.mark.parametrize("entry", ["sr", "ar", "dev"])
def test_self_contained_adapter_starts_real_cli_at_each_entry(tmp_path, entry, workflow_adapter):
    script = workflow_adapter / "vendor/aaw-workflow/scripts/aaw.py"
    requirement = tmp_path / "requirement.md"
    requirement.write_text("Implement a documented calculator.", encoding="utf-8")
    command = [sys.executable, str(script), "start", "--entry", entry, "--sr", "SR-TEST", "--json"]
    if entry == "sr":
        command += ["--requirement-file", str(requirement)]
    if entry == "ar":
        command += ["--ar", "AR-001", "--title", "Calculator"]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "AAW_UPDATE_CHECK": "off", "AAW_TELEMETRY_ENABLED": "false"},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["entry"] == entry
    spec = WorkflowSpec(entry=entry, sr="SR-TEST", ar="AR-001" if entry == "ar" else None)
    assert not inspect_workflow(tmp_path, spec)["passed"]  # Starting is not completion.
    assert package("clarity", entry)[0]["workflow"]["entry"] == entry


def write_terminal(workspace, entry="dev"):
    root = workspace / ".sdd/SR-TEST"
    root.mkdir(parents=True, exist_ok=True)
    task_dir = root / ".aaw/task-dev/2/1"
    task_dir.mkdir(parents=True)
    reports = {}
    for name in ("implementation", "review", "revalidation", "codecheck", "delivery"):
        path = task_dir / f"{name}.json"
        content = (
            {
                "reviewers": [
                    {"role": role, "status": "completed", "report_ref": f"{role}.md"}
                    for role in ("reviewer-a", "reviewer-b")
                ]
            }
            if name == "review"
            else {"status": "passed"}
        )
        path.write_text(json.dumps(content), encoding="utf-8")
        reports[name] = str(path)
    (task_dir / "state.json").write_text(
        json.dumps({"status": "completed", "reports": reports}), encoding="utf-8"
    )
    (root / "design.md").write_text("Design evidence", encoding="utf-8")
    state = {
        "sr": "SR-TEST",
        "entry": entry,
        "status": "done",
        "steps": [
            {
                "id": 1,
                "type": "dev-design-gate",
                "finished": True,
                "output": [{"path": ".sdd/SR-TEST/design.md", "required": True}],
            },
            {"id": 2, "type": "dev-task-dev", "finished": True, "attempt": 1},
        ],
    }
    (root / "workflow.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    return root, state


@pytest.mark.parametrize("entry", ["sr", "ar", "dev"])
def test_terminal_requires_all_steps_outputs_gates_and_task_records(tmp_path, entry):
    root, state = write_terminal(tmp_path, entry)
    spec = WorkflowSpec(entry=entry, sr="SR-TEST", ar="AR-001" if entry == "ar" else None)
    result = inspect_workflow(tmp_path, spec)
    assert result["passed"]
    # gate 步骤与其它步骤同一判据（finished + 交付件）；gate_result 不由 CLI 序列化，仅留痕。
    assert result["remarks"]
    state["pending_user_confirm"] = {"step": 2}
    (root / "workflow.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    assert not inspect_workflow(tmp_path, spec)["passed"]
    state.pop("pending_user_confirm")
    state["steps"][0]["finished"] = False
    (root / "workflow.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    assert not inspect_workflow(tmp_path, spec)["passed"]
    state["steps"][0]["finished"] = True
    (root / "workflow.yaml").write_text(yaml.safe_dump(state), encoding="utf-8")
    (root / ".aaw/task-dev/2/1/review.json").unlink()
    assert not inspect_workflow(tmp_path, spec)["passed"]


def test_ignored_terminal_documents_are_archived_and_visible_to_judge(tmp_path):
    workspace, artifacts = tmp_path / "workspace", tmp_path / "artifacts"
    artifacts.mkdir()
    write_terminal(workspace)
    case = CaseSpec.model_validate(package("correctness")[0])
    result = collect_terminal_outputs(workspace, case, [], artifacts)
    assert ".sdd/SR-TEST/design.md" in result["output_files"]
    with zipfile.ZipFile(artifacts / "terminal-outputs.zip") as archive:
        assert ".sdd/SR-TEST/workflow.yaml" in archive.namelist()


def test_repeated_workflow_confirmations_resume_codex_and_enable_reviewers(tmp_path, monkeypatch):
    case = runner_case(CaseSpec.model_validate(package("correctness")[0]), with_skill=True)
    runner = CodexRunner(Settings(data_dir=tmp_path / "data"))
    calls = []

    def execute(arguments, **kwargs):
        calls.append(arguments)
        message = Path(arguments[arguments.index("--output-last-message") + 1])
        message.write_text("AWAITING_EVAL_CONFIRM" if len(calls) < 3 else "Done", encoding="utf-8")
        return 0, '{"type":"thread.started","thread_id":"test"}', "", 1, False, False, {}

    monkeypatch.setattr(runner, "_execute", execute)
    outcome = runner.run(
        workspace=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        case=case,
        profile=EvalProfile(runner_model="fake", judge_model="fake"),
        skill_name="aaw-workflow-eval",
    )
    assert outcome.turns == 3
    assert all("features.multi_agent=true" in command for command in calls)
    assert "--ephemeral" not in calls[0]
    env = _isolated_environment(tmp_path / "state")
    assert env["AAW_UPDATE_CHECK"] == "off"
    assert env["AAW_TELEMETRY_ENABLED"] == "false"
    assert not runner_case(
        CaseSpec.model_validate(package("correctness")[0]), with_skill=False
    ).followups


def test_runner_exit_zero_does_not_mark_unfinished_workflow_completed(client, project, skill):
    request = joint_request(project, skill)
    request["dimensions"] = request["dimensions"][:1]
    request["cases"][0]["graders"] = request["cases"][0]["graders"][:1]
    saved = client.post("/api/v1/suites", json=request).json()
    launched = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": saved["id"],
            "mode": "quick",
            "profile": {"runner_model": "fake", "judge_model": "fake"},
        },
    )
    assert launched.status_code == 202, launched.text
    detail = wait_experiment(client, launched.json()["id"])
    current = next(run for run in detail["runs"] if run["group"] == "current")
    control = next(run for run in detail["runs"] if run["group"] == "no_skill")
    assert current["status"] == "agent_error"
    assert current["error_kind"] == "workflow_incomplete"
    assert current["scores"]["workflow_completion"]["passed"] is False
    assert current["scores"]["hard_gates_total"] == 1
    assert control["status"] == "completed"


def test_workflow_rejects_seeded_completed_state():
    case = package("correctness")[0]
    case["files"].append(
        {
            "path": ".sdd/SR-EVAL-001/workflow.yaml",
            "content_base64": base64.b64encode(b"status: done").decode(),
        }
    )
    with pytest.raises(ValidationError, match="预置"):
        CaseSpec.model_validate(case)


def test_chrys_workflow_allowed_before_execution(client, project, skill, monkeypatch):
    """用户决策（2026-10-10）：workflow 套件允许 Chrys Runner（Reviewer 检查降级为备注）。"""
    from aaw_skill_eval.services.orchestration import prepare as prepare_module

    monkeypatch.setattr(prepare_module, "enrich_profile", lambda settings, profile, **kw: profile)
    monkeypatch.setattr(prepare_module, "verify_profile", lambda settings, profile, **kw: None)
    saved = client.post("/api/v1/suites", json=joint_request(project, skill)).json()
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": saved["id"],
            "mode": "quick",
            "profile": {"runner_provider": "chrys", "runner_model": "fake", "judge_model": "fake"},
        },
    )
    assert response.status_code == 202
    assert "WORKFLOW_RUNNER_UNSUPPORTED" not in response.text
