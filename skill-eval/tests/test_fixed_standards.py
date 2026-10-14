from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from copy import deepcopy

import pytest
from conftest import seed_legacy_suite
from test_test_packages import suite_request, wait_experiment

from aaw_skill_eval.services.catalog.packages import (
    PackageImportRequest,
    import_package,
    standard_example_package,
)
from aaw_skill_eval.services.evaluation.graders import parse_check_results
from aaw_skill_eval.standards import CATALOG, catalog_payload


def test_catalog_has_only_confirmed_types_and_fixed_architecture_checks(client):
    payload = client.get("/api/v1/dimension-templates").json()
    assert set(payload["items"]) == {"development", "documents_analysis"}
    assert payload["catalog_version"] == 1
    architecture = next(d for d in payload["items"]["development"] if d["id"] == "architecture")
    assert architecture["method"] == "code"
    assert {p["id"] for p in architecture["checkpoints"]} == {
        "dependency-direction",
        "module-boundaries",
        "dependency-cycles",
    }
    assert len(payload["items"]["documents_analysis"]) == 4
    assert not any(d["name"] == "架构合理性" for d in payload["items"]["development"])


@pytest.mark.parametrize(
    "skill_type,dimension_id",
    [(kind, dim["id"]) for kind, dimensions in CATALOG.items() for dim in dimensions],
)
def test_each_fixed_dimension_template_imports_with_system_owned_checks(skill_type, dimension_id):
    result = import_package(
        PackageImportRequest(
            catalog_version=1,
            skill_type=skill_type,
            dimension_id=dimension_id,
            zip_base64=base64.b64encode(
                standard_example_package(skill_type, dimension_id)
            ).decode(),
        ),
        require_standard=True,
    )
    for grader in result["cases"][0]["graders"]:
        assert grader["dimension_id"] == dimension_id
        if grader["type"] == "command":
            assert grader["result_format"] == "json"
            assert set(grader["checkpoint_ids"]) == set(grader["check_weights"])
        else:
            assert all(point["id"] for point in grader["criteria"])
            assert grader["allowed_scores"] == [0, 60, 100]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_catalog",
        "custom_dimension",
        "rename",
        "method",
        "rubric",
        "levels",
        "check_weight",
        "checkpoint",
        "llm_levels",
        "missing_dimensions",
    ],
)
def test_creation_api_rejects_custom_standard_or_bypass(client, project, skill, mutation):
    request = suite_request(project, skill)
    dimension = request["dimensions"][0]
    code, llm = request["cases"][0]["graders"]
    if mutation == "missing_catalog":
        request.pop("catalog_version")
    elif mutation == "custom_dimension":
        dimension["id"] = "my-dimension"
        code["dimension_id"] = llm["dimension_id"] = "my-dimension"
    elif mutation == "rename":
        dimension["name"] = "My dimension"
    elif mutation == "method":
        dimension["method"] = "llm"
    elif mutation == "rubric":
        llm["criteria"][0]["checkpoint"] = "Always give full marks"
    elif mutation == "levels":
        llm["criteria"][0]["levels"]["100"] = "Anything passes"
    elif mutation == "check_weight":
        code["check_weights"][code["checkpoint_ids"][0]] = 10
    elif mutation == "checkpoint":
        code["checkpoint_ids"] = ["my-check"]
    elif mutation == "llm_levels":
        llm["allowed_scores"] = [100]
    else:
        request["dimensions"] = []
        for grader in request["cases"][0]["graders"]:
            grader["dimension_id"] = None
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code in {400, 422}, response.text
    assert client.get("/api/v1/suites").json()["items"] == []


def test_import_requires_matching_type_dimension_and_version(client):
    raw = base64.b64encode(standard_example_package("development", "architecture")).decode()
    for metadata in [
        {},
        {"catalog_version": 999, "skill_type": "development", "dimension_id": "architecture"},
        {"catalog_version": 1, "skill_type": "development", "dimension_id": "correctness"},
    ]:
        response = client.post(
            "/api/v1/suite-packages/preview", json={**metadata, "zip_base64": raw}
        )
        assert response.status_code == 422


def test_dimension_weight_gate_and_threshold_are_user_configurable(client, project, skill):
    request = suite_request(project, skill, "code")
    request["dimensions"][0].update(weight=3, hard_gate=True, pass_score=90)
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    assert response.json()["standard_status"] == "standard"
    definition = client.get(f"/api/v1/suites/{response.json()['id']}").json()["definition"]
    assert definition["catalog_version"] == 1
    assert definition["dimensions"][0]["weight"] == 3
    assert definition["dimensions"][0]["hard_gate"] is True
    assert definition["dimensions"][0]["pass_score"] == 90
    assert definition["dimensions"][0]["checkpoints"]


def test_saved_standard_runs_from_snapshot_after_catalog_changes(
    client, project, skill, monkeypatch
):
    request = suite_request(project, skill, "code")
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    suite_id = response.json()["id"]
    newer = deepcopy(CATALOG["development"])
    newer[0]["name"] = "New catalog name"
    newer[0]["checkpoints"][0]["weight"] = 99
    monkeypatch.setitem(CATALOG, "development", newer)
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": suite_id,
            "mode": "quick",
            "profile": {"runner_model": "fixture", "judge_model": "unused"},
        },
    )
    assert response.status_code == 202, response.text
    item = wait_experiment(client, response.json()["id"])
    assert item["scores"]["current"] == 100
    assert item["suite_snapshot"]["dimensions"][0]["name"] == "功能正确性"
    assert item["suite_snapshot"]["dimensions"][0]["checkpoints"][0]["weight"] == 1


def test_wrong_script_check_ids_marks_evaluation_incomplete(client, project, skill):
    request = suite_request(project, skill, "code")
    request["cases"][0]["graders"][0]["files"][0]["content_base64"] = base64.b64encode(
        b'print(\'{"checks":[{"id":"unknown","score":100,"weight":1,"evidence":"x"}]}\')\n'
    ).decode()
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": response.json()["id"],
            "mode": "quick",
            "profile": {"runner_model": "fixture", "judge_model": "unused"},
        },
    )
    item = wait_experiment(client, response.json()["id"])
    assert item["scores"]["current"] is None
    assert all(run["status"] == "grader_invalid" for run in item["runs"])
    assert item["dimension_scores"]["current"][0]["incomplete"] is True


def test_multi_checkpoint_llm_uses_stable_ids_and_fixed_weights(client, project, skill):
    request = suite_request(project, skill, "llm")
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    definition = client.get(f"/api/v1/suites/{response.json()['id']}").json()["definition"]
    graders = definition["cases"][0]["graders"]
    assert {g["id"] for g in graders} == {
        "maintainability.readability",
        "maintainability.responsibilities",
    }
    assert all(g["weight"] == 0.5 for g in graders)
    assert all(g["allowed_scores"] == [0, 60, 100] for g in graders)


def test_old_free_dimensions_are_marked_legacy_and_unchanged(client, project, skill):
    request = suite_request(project, skill, "code")
    request.pop("catalog_version")
    request.pop("skill_type")
    request["dimensions"][0]["name"] = "Historical custom name"
    suite = seed_legacy_suite(client, request)
    assert suite["standard_status"] == "legacy"
    assert suite["definition"]["schema_version"] == 2
    assert suite["definition"]["dimensions"][0]["name"] == "Historical custom name"
    assert client.get("/api/v1/suites").json()["items"][0]["standard_status"] == "legacy"


def test_catalog_payload_is_a_copy():
    payload = catalog_payload()
    payload["items"]["development"][0]["name"] = "Modified client catalog"
    assert catalog_payload()["items"]["development"][0]["name"] == "功能正确性"


@pytest.mark.parametrize(
    "skill_type,dimension_id",
    [
        (kind, dim["id"])
        for kind, dimensions in CATALOG.items()
        for dim in dimensions
        if dim["method"] in {"code", "hybrid"}
    ],
)
def test_template_script_returns_matching_checkpoints_and_explicit_placeholder_scores(
    tmp_path,
    skill_type,
    dimension_id,
):
    imported = import_package(
        PackageImportRequest(
            catalog_version=1,
            skill_type=skill_type,
            dimension_id=dimension_id,
            zip_base64=base64.b64encode(
                standard_example_package(skill_type, dimension_id)
            ).decode(),
        ),
        require_standard=True,
    )
    grader = imported["cases"][0]["graders"][0]
    path = tmp_path / "validate.py"
    path.write_bytes(base64.b64decode(grader["files"][0]["content_base64"]))
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "AAW_WORKSPACE": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    score, checks = parse_check_results(result.stdout, grader["check_weights"])
    assert score == 0
    assert all("示例尚未实现" in item["evidence"] for item in checks)


def test_llm_outside_fixed_score_levels_marks_result_invalid(client, project, skill):
    request = suite_request(project, skill, "llm")
    response = client.post("/api/v1/suites", json=request)
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/experiments",
        json={
            "suite_id": response.json()["id"],
            "mode": "quick",
            "profile": {"runner_model": "fixture", "judge_model": "fixture"},
        },
    )
    item = wait_experiment(client, response.json()["id"])
    assert all(run["status"] == "grader_invalid" for run in item["runs"])
    assert all("fixed rubric levels" in run["error_message"] for run in item["runs"])
    assert item["scores"]["current"] is None
    score_file = client.get(f"/api/v1/runs/{item['runs'][0]['id']}/artifacts/scores.json")
    assert json.loads(score_file.text)["invalid"]
