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
from test_test_packages import wait_experiment

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.schemas import CaseSpec, EvalProfile, WorkflowSpec
from aaw_skill_eval.modules.suites.packages import (
    PackageImportRequest,
    import_package,
    standard_example_package,
)
from aaw_skill_eval.adapters.workflows.aaw.packages import build_workflow_adapter
from aaw_skill_eval.adapters.workflows.aaw.evidence import (
    collect_terminal_outputs,
    inspect_workflow,
    runner_case,
)
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
