"""Pair-parallel execution tests (用户方案第五部分).

The primary evidence that the no_skill/current runs of one
(case_id, trial_index) pair really executed simultaneously is a
``threading.Barrier`` inside the fake runner: both runs must be inside
``run()`` at the same time for the barrier to pass, and a serial scheduler
breaks it after the timeout. Wall-clock comparisons are only auxiliary.
"""

from __future__ import annotations

import io
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from conftest import seed_legacy_suite
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from aaw_skill_eval.config import Settings
from aaw_skill_eval.infrastructure.database import is_locked_error, with_lock_retry
from aaw_skill_eval.contracts.entities import Experiment, Run
from aaw_skill_eval.contracts.schemas import CaseSpec, EvalProfile
from aaw_skill_eval.modules.executions.scheduling import claim_run
from aaw_skill_eval.adapters.agents.chrys import ChrysJudge, ChrysRunner
from aaw_skill_eval.contracts.agents import RunOutcome
from aaw_skill_eval.adapters.agents.chrys.runtime import (
    RUNNER_PROFILE_NAME,
    materialize_run_chrys_home,
    prepare_experiment_chrys_template,
    prepare_isolated_home,
)
from aaw_skill_eval.adapters.agents.protocols.acp import AcpSession, AcpTurnResult

# --------------------------------------------------------------------- helpers


def _case(case_id: str) -> dict:
    return {
        "id": case_id,
        "name": f"Case {case_id}",
        "input": "Create result.md",
        "expected": "A useful result.md must exist",
        "weight": 1,
        "agent_context": "",
        "followups": [],
        "max_turns": 6,
        "graders": [
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
            {
                "id": "quality",
                "type": "llm_rubric",
                "name": "Quality",
                "weight": 100,
                "hard_gate": False,
                "rubric": "Judge quality",
                "timeout_seconds": 300,
            },
        ],
    }


def _suite(client: TestClient, project: Path, skill: Path, cases: list[dict]) -> dict:
    return seed_legacy_suite(
        client,
        {
            "name": "Parallel suite",
            "project_path": str(project),
            "skill_path": str(skill),
            "setup": {"commands": [], "preflight": [], "network": False},
            "cases": cases,
        },
    )


def _experiment(
    client: TestClient,
    suite_id: str,
    *,
    mode: str = "quick",
    name: str = "parallel-fixture",
    profile: dict | None = None,
) -> str:
    body_profile = {
        "name": name,
        "runner_model": "fixture-model",
        "judge_model": "fixture-model",
        "network": False,
    }
    if profile:
        body_profile.update(profile)
    response = client.post(
        "/api/v1/experiments",
        json={"suite_id": suite_id, "mode": mode, "profile": body_profile},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def _wait(client: TestClient, experiment_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if item["status"] in {
            "completed",
            "completed_with_failures",
            "failed",
            "invalid",
            "cancelled",
            "interrupted",
        }:
            return item
        time.sleep(0.05)
    raise AssertionError(f"experiment did not finish: {item['status']}")


def _wait_for_active_runs(
    client: TestClient, experiment_id: str, count: int, timeout: float = 15.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if len(payload["progress"]["active_runs"]) >= count:
            return payload
        time.sleep(0.02)
    raise AssertionError(
        f"expected {count} active runs, saw {len(payload['progress']['active_runs'])}"
    )


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _wait_gone(path: Path, timeout: float = 5.0) -> bool:
    """Wait for a directory to disappear.

    The experiment reaches its terminal status slightly before the finally
    block removes the run workspace and the chrys template, and Windows AV
    can briefly hold handles to freshly written files — so deletion is
    asserted with a grace window instead of instantaneously.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not path.exists():
            return True
        time.sleep(0.05)
    return not path.exists()


class PairProbeRunner:
    """FakeRunner wrapper that proves the pair executed simultaneously.

    Both pair runs (no_skill/current) of a case must be inside ``run()`` at
    the same time for the per-case barrier to pass. A serial scheduler would
    time the first run out on the barrier and set ``broken``. Baseline runs
    skip the barrier (they are scheduled after the pair by design).
    """

    def __init__(
        self,
        delegate,
        session_factory,
        *,
        hold: threading.Event | None = None,
        barrier_timeout: float = 15.0,
    ):
        self.delegate = delegate
        self.session_factory = session_factory
        self.hold = hold
        self.barrier_timeout = barrier_timeout
        self._lock = threading.Lock()
        self._barriers: dict[str, threading.Barrier] = {}
        self.active = 0
        self.max_active = 0
        self.entries: list[dict] = []
        self.broken = False

    def _group_for(self, artifact_dir: Path) -> str | None:
        name = artifact_dir.name
        run_id = artifact_dir.parent.name if name.startswith("attempt-") else name
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            return run.group_name if run is not None else None

    def run(
        self,
        *,
        workspace,
        artifact_dir,
        case,
        profile,
        skill_name,
        on_progress=None,
        on_log=None,
        is_cancelled=None,
        chrys_home_root=None,
    ):
        group = self._group_for(Path(artifact_dir))
        entry = {
            "case": case.id,
            "group": group,
            "entered_at": time.monotonic(),
            "workspace": str(workspace),
            "artifact_dir": str(artifact_dir),
            "chrys_home_root": str(chrys_home_root) if chrys_home_root else None,
            "exited_at": None,
        }
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.entries.append(entry)
        try:
            if group in ("no_skill", "current"):
                with self._lock:
                    barrier = self._barriers.setdefault(case.id, threading.Barrier(2))
                try:
                    barrier.wait(timeout=self.barrier_timeout)
                except threading.BrokenBarrierError:
                    self.broken = True
            if self.hold is not None:
                deadline = time.monotonic() + 30.0
                while not self.hold.is_set() and time.monotonic() < deadline:
                    if is_cancelled is not None and is_cancelled():
                        break
                    time.sleep(0.01)
            return self.delegate.run(
                workspace=workspace,
                artifact_dir=artifact_dir,
                case=case,
                profile=profile,
                skill_name=skill_name,
                on_progress=on_progress,
                on_log=on_log,
                is_cancelled=is_cancelled,
                chrys_home_root=chrys_home_root,
            )
        finally:
            with self._lock:
                self.active -= 1
                entry["exited_at"] = time.monotonic()


# ------------------------------------------------------- database retry helpers


def test_with_lock_retry_retries_locked_errors_with_backoff(monkeypatch):
    import aaw_skill_eval.infrastructure.database as database_module

    attempts = []
    sleeps = []

    # replace the module's time/random references (not the global modules,
    # whose sleep is used by every other thread in the test process); fixing
    # the jitter makes the backoff-growth assertion deterministic
    monkeypatch.setattr(
        database_module,
        "time",
        type("TimeStub", (), {"sleep": staticmethod(lambda delay: sleeps.append(delay))}),
    )
    monkeypatch.setattr(
        database_module,
        "random",
        type("RandomStub", (), {"random": staticmethod(lambda: 0.5)}),
    )

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise OperationalError("statement", {}, "database is locked")
        return "ok"

    assert with_lock_retry(flaky) == "ok"
    assert len(attempts) == 3
    assert len(sleeps) == 2
    assert all(delay > 0 for delay in sleeps)
    assert sleeps[1] > sleeps[0]  # exponential backoff grows


def test_with_lock_retry_propagates_non_lock_errors_immediately():
    def boom():
        raise OperationalError("statement", {}, "no such table: runs")

    with pytest.raises(OperationalError):
        with_lock_retry(boom)
    assert not is_locked_error(OperationalError("statement", {}, "no such table: runs"))
    assert is_locked_error(OperationalError("statement", {}, "database is locked"))


# ------------------------------------------------------- pair-parallel evidence


# --------------------------------------------------------- mode combinations


# ----------------------------------------------------- chrys per-run isolation


def test_chrys_template_and_per_run_homes(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        chrys_home=tmp_path / "chrys",
        chrys_command="missing-chrys-for-test",
    )
    (tmp_path / "chrys" / "agents").mkdir(parents=True)

    template = prepare_experiment_chrys_template(settings, "exp-1")
    assert template == settings.data_dir / "chrys-templates" / "exp-1"
    agents = template / "chrys" / "agents"
    assert (agents / f"{RUNNER_PROFILE_NAME}.yaml").is_file()
    # legacy shared home is not touched by template preparation
    assert not (settings.data_dir / "chrys-isolated").exists()

    run_a = tmp_path / "runs" / "a"
    run_b = tmp_path / "runs" / "b"
    home_a = materialize_run_chrys_home(template, run_a)
    home_b = materialize_run_chrys_home(template, run_b)
    assert home_a == run_a / "chrys-home" and home_b == run_b / "chrys-home"
    assert home_a != home_b
    for home in (home_a, home_b):
        assert (home / "chrys" / "agents" / f"{RUNNER_PROFILE_NAME}.yaml").is_file()
    assert materialize_run_chrys_home(None, run_a) is None


def test_chrys_runner_and_judge_receive_per_run_config_root(tmp_path: Path, monkeypatch):
    import aaw_skill_eval.adapters.agents.chrys.runner as runner_module

    captured: list[dict] = []
    judge_payload = (
        '{"candidate_id":"candidate-1","scores":[{"grader_id":"quality",'
        '"score":90,"evidence":"e","reasoning":"r"}]}'
    )

    class StubAcpSession:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.skills_loaded = []

        def start(self):
            pass

        def initialize(self):
            pass

        def new_session(self, cwd):
            return "session-1"

        def ensure_model(self, model):
            return model

        def prompt(self, text, **kwargs):
            if "盲评 Judge" in text:
                return AcpTurnResult(stop_reason="end_turn", text=judge_payload)
            return AcpTurnResult(stop_reason="end_turn", text="runner ok")

        def close(self):
            pass

    monkeypatch.setattr(runner_module, "AcpSession", StubAcpSession)
    settings = Settings(
        data_dir=tmp_path / "data",
        chrys_home=tmp_path / "chrys",
        chrys_command="missing-chrys-for-test",
    )
    profile = EvalProfile(name="chrys", runner_model="m", judge_model="m")
    case = CaseSpec.model_validate(_case("case-1"))
    per_run_root = tmp_path / "run-root" / "chrys-home"

    ChrysRunner(settings).run(
        workspace=tmp_path / "ws",
        artifact_dir=tmp_path / "artifacts",
        case=case,
        profile=profile,
        skill_name=None,
        chrys_home_root=per_run_root,
    )
    assert captured[0]["isolated_root"] == per_run_root

    judge = ChrysJudge(settings)
    outcome = judge.evaluate(
        anonymous_id="candidate-1",
        case=case,
        graders=case.graders,
        evidence={"final_response": "completed with skill"},
        profile=profile,
        artifact_dir=tmp_path / "artifacts",
        chrys_home_root=per_run_root,
    )
    assert captured[1]["isolated_root"].is_relative_to(settings.data_dir / "judge-homes")
    assert outcome.error is None
    assert [score.grader_id for score in outcome.scores] == ["quality"]


def test_acp_session_uses_provided_root_without_shared_home(tmp_path: Path, monkeypatch):
    """提供 isolated_root 时直接使用，绝不改写共享 chrys-isolated 目录。"""
    import aaw_skill_eval.adapters.agents.chrys.runtime as chrys_module
    import aaw_skill_eval.adapters.agents.protocols.acp.session as acp_module

    def forbidden(*args, **kwargs):
        raise AssertionError("shared chrys-isolated home must not be prepared")

    monkeypatch.setattr(chrys_module, "prepare_isolated_home", forbidden)

    spawned: list[dict] = []

    class FakeProcess:
        def __init__(self):
            self.pid = 4242
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"")
            self.returncode = 0

        def poll(self):
            return 0

    def fake_popen(command, **kwargs):
        spawned.append(kwargs)
        return FakeProcess()

    monkeypatch.setattr(acp_module.subprocess, "Popen", fake_popen)

    per_run_root = tmp_path / "runs" / "abc" / "chrys-home"
    session = AcpSession(
        command=["chrys", "acp"],
        env={"APPDATA": str(per_run_root)},
        agent_profile=RUNNER_PROFILE_NAME,
        cwd=tmp_path,
        artifact_dir=tmp_path,
        isolated_root=per_run_root,
    )
    session.start()
    session.close()

    assert per_run_root.is_dir()
    assert spawned[0]["env"]["APPDATA"] == str(per_run_root)


def test_prepare_isolated_home_still_supports_shared_root(tmp_path: Path):
    """默认（无 root 参数）仍生成共享隔离目录，兼容既有调用。"""
    settings = Settings(
        data_dir=tmp_path / "data",
        chrys_home=tmp_path / "chrys",
        chrys_command="missing-chrys-for-test",
    )
    root = prepare_isolated_home(settings)
    assert root == settings.data_dir / "chrys-isolated"
    assert (root / "chrys" / "agents").is_dir()
