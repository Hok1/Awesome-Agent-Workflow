from types import SimpleNamespace

from aaw_skill_eval.adapters.agents.chrys import runner
from aaw_skill_eval.adapters.agents.protocols.acp.session import AcpTurnResult
from aaw_skill_eval.config import Settings


def test_runner_absolute_budget_applies_to_initial_and_followup_turns(monkeypatch, tmp_path):
    calls = []

    class Session:
        skills_loaded = []

        def start(self):
            pass

        def initialize(self):
            pass

        def new_session(self, workspace):
            return "test-session"

        def ensure_model(self, model):
            pass

        def close(self):
            pass

        def prompt(self, text, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return AcpTurnResult(text="CONFIRM", stop_reason="end_turn")
            return AcpTurnResult(timed_out=True)

    monkeypatch.setattr(runner, "_build_session", lambda *args, **kwargs: Session())
    settings = Settings(_env_file=None, runner_turn_timeout_seconds=10800)
    case = SimpleNamespace(
        input="Implement Jupiter", agent_context="", max_turns=2,
        followups=[SimpleNamespace(when_output_contains="CONFIRM", reply="Continue", repeat=False)],
    )
    outcome = runner.ChrysRunner(settings).run(
        workspace=tmp_path, artifact_dir=tmp_path, case=case,
        profile=SimpleNamespace(runner_model="test-model", timeout_seconds=1800),
        skill_name=None,
    )
    assert len(calls) == 2
    assert all(call["absolute_timeout_seconds"] == 10800 for call in calls)
    assert all(call["timeout_seconds"] == 1800 for call in calls)
    assert outcome.error_kind == "timeout"
    assert "10800s" in outcome.error_message
