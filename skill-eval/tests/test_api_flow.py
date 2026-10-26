from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from conftest import seed_legacy_suite
from fastapi.testclient import TestClient

from aaw_skill_eval.infrastructure.observability.logs import MAX_LOG_READ_BYTES, LogWriter
from aaw_skill_eval.contracts.agents import RunOutcome


def _draft(client: TestClient, project: Path, skill: Path) -> dict:
    return {
        "case": {
            "id": "result",
            "name": "Deliver result",
            "input": "Create result.md",
            "expected": "Useful result.md",
            "graders": [
                {
                    "id": "quality",
                    "type": "llm_rubric",
                    "name": "Quality",
                    "rubric": "Useful",
                    "weight": 1,
                }
            ],
        }
    }


def _suite(client: TestClient, project: Path, skill: Path) -> dict:
    draft = _draft(client, project, skill)
    draft["case"]["graders"].insert(
        0,
        {
            "id": "result-file",
            "type": "file_exists",
            "name": "Result file exists",
            "weight": 0,
            "hard_gate": True,
            "path": "result.md",
            "patterns": [],
            "timeout_seconds": 300,
        },
    )
    return seed_legacy_suite(
        client,
        {
            "name": "Fixture suite",
            "project_path": str(project),
            "skill_path": str(skill),
            "setup": {"commands": [], "preflight": [], "network": False},
            "cases": [draft["case"]],
        },
    )


def _wait(client: TestClient, experiment_id: str) -> dict:
    for _ in range(100):
        item = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if item["status"] in {"completed", "completed_with_failures", "failed", "invalid"}:
            return item
        time.sleep(0.05)
    raise AssertionError("experiment did not finish")


def test_index_serves_benchmark_frontend(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert "/assets/benchmark/assets/" in response.text
