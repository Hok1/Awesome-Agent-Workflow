from __future__ import annotations

from test_benchmark import save_fixture
from test_test_packages import wait_experiment

from aaw_skill_eval.contracts.entities import Experiment
from aaw_skill_eval.contracts.schemas import EvalProfile, ProviderSnapshot
from aaw_skill_eval.modules.executions import execution, prepare
from aaw_skill_eval.contracts.agents import JudgeOutcome, JudgeScore


def test_runtime_notification_exposes_real_registered_reviewers(tmp_path):
    from aaw_skill_eval.adapters.agents.protocols.acp import AcpSession

    acp = AcpSession(
        command=["unused"],
        env={},
        agent_profile="test",
        cwd=tmp_path,
        artifact_dir=tmp_path,
        on_log=None,
        log_source="test",
    )
    acp._handle_notification(
        "_chrys/runtime_update",
        {"runtime": {"runtimeDetails": {"sub_agent_tools": ["reviewer_a", "reviewer_b"]}}},
    )
    assert acp.runtime_observed.is_set()
    assert acp.sub_agent_tool_names == ["reviewer_a", "reviewer_b"]


def test_missing_reviewers_stops_before_workflow_execution(tmp_path, monkeypatch):
    import threading

    import pytest

    from aaw_skill_eval.config import Settings
    from aaw_skill_eval.errors import InfrastructureError
    from aaw_skill_eval.contracts.schemas import CaseSpec
    from aaw_skill_eval.adapters.agents.chrys import runner as module
    from aaw_skill_eval.adapters.agents.protocols.acp.session import AcpTurnResult

    class Session:
        runtime_observed = threading.Event()
        sub_agent_tool_names = []

        def initialize(self):
            pass

        def new_session(self, *args):
            return "fixture"

        def ensure_model(self, *args):
            pass

        def close(self):
            pass

        def prompt(self, *args, **kwargs):
            self.runtime_observed.set()
            assert kwargs["is_cancelled"]()
            return AcpTurnResult(cancelled=True)

    monkeypatch.setattr(module, "_build_session", lambda *args, **kwargs: Session())
    monkeypatch.setattr(module, "_start_session", lambda *args: None)
    case = CaseSpec.model_validate(
        {
            "id": "case",
            "name": "task",
            "input": "task",
            "expected": "done",
            "workflow": {"entry": "dev", "sr": "SR-TEST"},
            "graders": [
                {
                    "id": "check",
                    "name": "check",
                    "type": "file_exists",
                    "path": "result.md",
                    "weight": 1,
                }
            ],
        }
    )
    with pytest.raises(InfrastructureError) as error:
        module.ChrysRunner(Settings(data_dir=tmp_path)).run(
            workspace=tmp_path,
            artifact_dir=tmp_path,
            case=case,
            profile=EvalProfile(runner_model="fixture", judge_model="fixture"),
            skill_name="aaw",
        )
    assert error.value.kind == "infra_error"
    assert error.value.code == "CHRYS_REVIEWERS_UNAVAILABLE"
