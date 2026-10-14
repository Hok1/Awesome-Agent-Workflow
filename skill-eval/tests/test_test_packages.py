from __future__ import annotations

import base64
import io
import json
import time
import zipfile
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.schemas import CaseSpec, DimensionSpec, PackageFile, SuiteCreateRequest
from aaw_skill_eval.services.catalog.packages import (
    PackageImportRequest,
    example_package,
    import_package,
    standard_example_package,
)
from aaw_skill_eval.services.evaluation.dimensions import dimension_summary, dimension_total
from aaw_skill_eval.services.evaluation.graders import (
    ScoreComponent,
    merge_scores,
    parse_check_results,
)
from aaw_skill_eval.services.providers.base import JudgeOutcome
from aaw_skill_eval.standards import get_dimension


def imported(method="hybrid"):
    return import_package(
        PackageImportRequest(zip_base64=base64.b64encode(example_package(method)).decode())
    )


def suite_request(project, skill, method="hybrid"):
    skill_type, dim_id = {
        "hybrid": ("documents_analysis", "completeness"),
        "code": ("development", "correctness"),
        "llm": ("development", "maintainability"),
    }[method]
    cases = import_package(
        PackageImportRequest(
            catalog_version=1,
            skill_type=skill_type,
            dimension_id=dim_id,
            zip_base64=base64.b64encode(standard_example_package(skill_type, dim_id)).decode(),
        ),
        require_standard=True,
    )["cases"]
    for case in cases:
        for grader in case["graders"]:
            if grader["type"] == "command":
                checks = [
                    {"id": key, "score": 100, "weight": weight, "evidence": "result.md valid"}
                    for key, weight in grader["check_weights"].items()
                ]
                script = (
                    "import json, os\nfrom pathlib import Path\n"
                    + "assert (Path(os.environ['AAW_WORKSPACE']) / 'result.md').is_file()\n"
                    + "print("
                    + repr(json.dumps({"checks": checks}))
                    + ")\n"
                )
                grader["files"][0]["content_base64"] = base64.b64encode(script.encode()).decode()
    standard = get_dimension(skill_type, dim_id)
    return {
        "name": "Imported suite",
        "project_path": str(project),
        "skill_path": str(skill),
        "catalog_version": 1,
        "skill_type": skill_type,
        "dimensions": [
            {
                key: standard[key]
                for key in ["id", "name", "method", "weight", "hard_gate", "pass_score"]
            }
        ],
        "cases": cases,
    }


def wait_experiment(client, experiment_id):
    for _ in range(150):
        item = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if item["status"] not in {"queued", "preparing", "running"}:
            return item
        time.sleep(0.05)
    pytest.fail("experiment did not finish")


@pytest.mark.parametrize("method", ["code", "llm", "hybrid"])
def test_zip_and_directory_import_preserve_assets(method):
    raw = example_package(method)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = [
            PackageFile(
                path="bundle/" + name, content_base64=base64.b64encode(archive.read(name)).decode()
            )
            for name in archive.namelist()
        ]
    directory = import_package(PackageImportRequest(files=files))
    zipped = imported(method)
    assert directory["cases"] == zipped["cases"]
    case = zipped["cases"][0]
    assert case["files"][0]["path"] == "brief.md"
    assert all(file["path"] != "validate.py" for file in case["files"])
    if method != "llm":
        assert case["graders"][0]["files"][0]["path"] == "validate.py"


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/root/file",
        "C:/file",
        "a\\file",
        ".git/config",
        ".codex/config",
        "nul.txt",
        "a./file",
    ],
)
def test_import_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        PackageFile(path=path, content_base64="")


def test_import_rejects_duplicate_archive_entries():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("suite.json", "{}")
        archive.writestr("SUITE.JSON", "{}")
    with pytest.raises(EvalError, match="重复路径"):
        import_package(PackageImportRequest(zip_base64=base64.b64encode(raw.getvalue()).decode()))


def test_preview_never_executes_and_reports_invalid_manifest(client):
    response = client.post(
        "/api/v1/suite-packages/preview",
        json={
            "catalog_version": 1,
            "skill_type": "development",
            "dimension_id": "correctness",
            "files": [
                {
                    "path": "suite.json",
                    "content_base64": base64.b64encode(
                        b'{"schema_version":3,"catalog_version":1,"skill_type":"development","dimension_id":"correctness"}'
                    ).decode(),
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "场景" in response.json()["message"]
    download = client.get("/api/v1/suite-packages/example/documents_analysis/completeness")
    assert download.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(download.content))


@pytest.mark.parametrize(
    "checks",
    [
        [],
        [{"id": "a", "score": 101, "evidence": "x"}],
        [{"id": "a", "score": True, "evidence": "x"}],
        [{"id": "a", "score": 50, "weight": 0, "evidence": "x"}],
        [{"id": "a", "score": 50}],
        [{"id": "a", "score": 50, "evidence": "x"}] * 2,
    ],
)
def test_json_result_validation(checks):
    with pytest.raises(ValueError):
        parse_check_results(json.dumps({"checks": checks}))


def test_partial_scores_use_check_weights():
    score, checks = parse_check_results(
        json.dumps(
            {
                "checks": [
                    {"id": "a", "score": 100, "weight": 1, "evidence": "yes"},
                    {"id": "b", "score": 20, "weight": 3, "evidence": "partial"},
                ]
            }
        )
    )
    assert score == 40
    assert len(checks) == 2


def test_dimension_gate_excluded_from_quality_and_uses_configured_threshold():
    case = CaseSpec(
        id="scene",
        name="Scene",
        input="task",
        expected="output",
        graders=[
            {
                "id": "q",
                "name": "Quality",
                "type": "file_exists",
                "path": "result.md",
                "weight": 1,
                "dimension_id": "quality",
            },
            {
                "id": "g",
                "name": "Gate",
                "type": "file_exists",
                "path": "result.md",
                "weight": 1,
                "dimension_id": "gate",
            },
        ],
    )
    result = merge_scores(
        case,
        [
            ScoreComponent(
                "q", "Quality", "file_exists", 95, 1, False, True, "yes", dimension_id="quality"
            ),
            ScoreComponent(
                "g", "Gate", "file_exists", 70, 1, False, True, "partial", dimension_id="gate"
            ),
        ],
        JudgeOutcome(),
        dimensions=[
            DimensionSpec(id="quality", name="Quality", method="code"),
            DimensionSpec(id="gate", name="Gate", method="code", hard_gate=True, pass_score=90),
        ],
    )
    assert result["quality_score"] == 95
    assert result["hard_gates_total"] == 1
    assert result["hard_gates_passed"] == 0
    assert result["dimensions"][1]["score"] == 70
    assert result["invalid"] is False


def test_dimensions_reject_missing_cases_wrong_methods_and_unstructured_llm(project, skill):
    request = suite_request(project, skill)
    request["dimensions"].append({"id": "unused", "name": "unused", "method": "code"})
    with pytest.raises(ValidationError, match="no test cases"):
        SuiteCreateRequest.model_validate(request)
    request["dimensions"].pop()
    request["dimensions"][0]["method"] = "code"
    with pytest.raises(ValidationError, match="does not match"):
        SuiteCreateRequest.model_validate(request)
    request = suite_request(project, skill, "llm")
    request["cases"][0]["graders"][0]["criteria"] = []
    with pytest.raises(ValidationError, match="structured criteria"):
        SuiteCreateRequest.model_validate(request)


def test_dimension_aggregation_does_not_reward_case_count():
    definition = {
        "dimensions": [
            {"id": "a", "name": "A", "weight": 1, "hard_gate": False},
            {"id": "b", "name": "B", "weight": 3, "hard_gate": False},
        ],
        "cases": [],
    }
    runs = []
    for case_id, dimension, score, weight in [
        ("a1", "a", 100, 1),
        ("a2", "a", 0, 3),
        ("b1", "b", 80, 1),
    ]:
        definition["cases"].append(
            {
                "id": case_id,
                "weight": 1,
                "dimension_weights": {dimension: weight},
                "graders": [{"dimension_id": dimension}],
            }
        )
        for _trial in range(2):
            runs.append(
                SimpleNamespace(
                    case_id=case_id,
                    group_name="current",
                    status="completed",
                    score_json=json.dumps(
                        {
                            "dimensions": [
                                {"id": dimension, "score": score, "passed": True, "invalid": False}
                            ]
                        }
                    ),
                )
            )
    experiment = SimpleNamespace(runs=runs, trials=2)
    items = dimension_summary(experiment, definition, "current")
    assert [item["score"] for item in items] == [25, 80]
    assert dimension_total(items) == 66.25
    assert not any(item["incomplete"] for item in items)
    runs[0].status = "grader_invalid"
    assert dimension_summary(experiment, definition, "current")[0]["incomplete"]


def test_imported_hybrid_suite_executes_once_per_shared_scene_and_hides_judge_materials(
    client,
    project,
    skill,
):
    original = client.app.state.orchestrator.runner.run
    seen = []

    def runner(**kwargs):
        workspace, case = kwargs["workspace"], kwargs["case"]
        assert (workspace / "brief.md").is_file()
        assert not (workspace / "validate.py").exists()
        assert case.graders == [] and case.expected == "" and case.files == []
        seen.append(workspace)
        return original(**kwargs)

    client.app.state.orchestrator.runner.run = runner
    request = suite_request(project, skill)
    judge = client.app.state.orchestrator.judge.evaluate

    def fixed_judge(**kwargs):
        outcome = judge(**kwargs)
        for score in outcome.scores:
            score.score = 100 if score.score == 88 else 60
        return outcome

    client.app.state.orchestrator.judge.evaluate = fixed_judge
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    suite = response.json()
    saved = client.get(f"/api/v1/suites/{suite['id']}").json()["definition"]
    assert saved["schema_version"] == 3
    assert len(saved["cases"][0]["graders"]) == 2
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": suite["id"],
            "mode": "quick",
            "profile": {"runner_model": "fixture", "judge_model": "fixture"},
        },
    )
    assert response.status_code == 202, response.text
    item = wait_experiment(client, response.json()["id"])
    assert item["status"] == "completed", item
    assert len(seen) == 2
    assert item["scores"]["current"] == 100
    assert item["scores"]["no_skill"] == 80
    assert item["dimension_scores"]["current"][0]["incomplete"] is False
    for run in item["runs"]:
        assert len(run["scores"]["components"][0]["checks"]) == 1
        assert (
            "brief.md"
            not in json.loads(client.get(f"/api/v1/runs/{run['id']}/artifacts/run.json").text)[
                "changed_files"
            ]
        )


def test_json_script_error_is_incomplete_and_code_only_skips_judge(client, project, skill):
    request = suite_request(project, skill, "code")
    request["cases"][0]["graders"][0]["files"][0]["content_base64"] = base64.b64encode(
        b"raise RuntimeError('broken evaluator')\n"
    ).decode()
    client.app.state.orchestrator.judge.evaluate = lambda **kwargs: pytest.fail(
        "judge must be skipped"
    )
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    assert response.json()["needs_judge"] is False
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": response.json()["id"],
            "mode": "quick",
            "profile": {
                "runner_model": "fixture",
                "judge_model": "unused",
                "judge_provider": "chrys",
            },
        },
    )
    assert response.status_code == 202, response.text
    item = wait_experiment(client, response.json()["id"])
    assert all(run["status"] == "grader_invalid" for run in item["runs"])
    assert item["scores"]["current"] is None
    assert item["conclusion"]["groups"]["current"]["provisional"]
