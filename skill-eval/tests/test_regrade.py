from __future__ import annotations

import json
from collections import Counter

from test_benchmark import save_fixture
from test_test_packages import wait_experiment

from aaw_skill_eval.contracts.entities import Experiment, Run
from aaw_skill_eval.contracts.schemas import CaseSpec, EvalProfile, ProviderSnapshot
from aaw_skill_eval.modules.evaluations.evidence import dimension_evidence
from aaw_skill_eval.modules.executions import execution, prepare
from aaw_skill_eval.contracts.agents import JudgeOutcome, JudgeScore
from aaw_skill_eval.adapters.agents.chrys import judge as judge_module
from aaw_skill_eval.adapters.agents.chrys.runtime import ChrysRuntime


class FixedJudge:
    def evaluate(self, *, graders, **kwargs):
        return JudgeOutcome(
            scores=[
                JudgeScore(g.id, 100, "result.md verified", "matches rubric")
                for g in graders
                if g.type == "llm_rubric"
            ]
        )


def test_dimension_evidence_keeps_complete_files_and_declares_omissions():
    evidence = {
        "output_files": {
            ".sdd/SR-1/design.md": "d" * 12000,
            "src/main.js": "c" * 22000,
            "index.html": "h" * 30000,
            ".sdd/SR-1/.aaw/state.json": "i" * 8000,
            ".aaw/harness/dom.txt": "debug" * 12000,
            ".aaw/harness/check.js": "debug code",
            ".context/notes.txt": "internal notes",
            ".aaw\\harness\\windows.txt": "internal windows path",
        },
        "git_patch": "duplicate" * 2000,
    }
    view = dimension_evidence(evidence, "clarity")
    assert list(view["output_files"]) == [".sdd/SR-1/design.md"]
    assert "git_patch" not in view
    assert len(view["omitted_files"]) == 7
    code = dimension_evidence(evidence, "maintainability")
    assert code["output_files"]["src/main.js"] == evidence["output_files"]["src/main.js"]
    assert sum(map(len, code["output_files"].values())) <= 60000
    assert not any(p.startswith((".aaw", ".context")) for p in code["output_files"])
    assert len(evidence["output_files"]) == 8


def test_dimension_failures_keep_successes_and_model_change_invalidates_cache(
    tmp_path, monkeypatch
):
    calls = Counter()
    monkeypatch.setattr(judge_module, "prepare_isolated_home", lambda *a, **kw: tmp_path)

    def batch(self, *, graders, profile, **kw):
        key = graders[0].dimension_id
        calls[key] += 1
        if key == "clarity" and calls[key] == 1:
            return JudgeOutcome(error="transient timeout")
        assert profile.timeout_seconds == 1800
        assert profile.judge_timeout_seconds <= 300
        return JudgeOutcome(scores=[JudgeScore(g.id, 100, "file:1", "verified") for g in graders])

    monkeypatch.setattr(judge_module.ChrysJudge, "_evaluate_batch", batch)
    case = CaseSpec.model_validate(
        {
            "id": "case",
            "name": "task",
            "input": "task",
            "expected": "expected",
            "graders": [
                {
                    "id": key,
                    "name": key,
                    "type": "llm_rubric",
                    "rubric": "fixed",
                    "weight": 1,
                    "dimension_id": key,
                    "allowed_scores": [0, 60, 100],
                }
                for key in ["maintainability", "clarity"]
            ],
        }
    )
    from aaw_skill_eval.config import Settings

    service = judge_module.ChrysJudge(Settings(data_dir=tmp_path / "data"))
    params = dict(
        anonymous_id="candidate",
        case=case,
        graders=case.graders,
        evidence={"output_files": {"README.md": "content"}},
        profile=EvalProfile(runner_model="r", judge_model="j"),
        artifact_dir=tmp_path / "artifact",
    )
    first = service.evaluate(**params)
    assert first.error and len(first.scores) == 1
    second = service.evaluate(**{**params, "anonymous_id": "different-candidate"})
    assert not second.error and len(second.scores) == 2
    assert calls == {"maintainability": 1, "clarity": 2}
    states = json.loads((tmp_path / "artifact/judge-progress.json").read_text())
    assert states["dimensions"]["maintainability"]["status"] == "cached"
    service.evaluate(
        **{**params, "profile": params["profile"].model_copy(update={"judge_model": "other"})}
    )
    assert calls == {"maintainability": 2, "clarity": 3}


def test_judge_budget_is_independent_and_cancels_inside_same_batch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aaw_skill_eval.config import Settings
    from aaw_skill_eval.adapters.agents.protocols.acp.session import AcpTurnResult

    clock = [100.0]
    monkeypatch.setattr(judge_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class Session:
        def initialize(self):
            pass

        def new_session(self, *args):
            pass

        def ensure_model(self, *args):
            pass

        def close(self):
            pass

        def prompt(self, *args, **kwargs):
            assert kwargs["timeout_seconds"] == 30
            assert not kwargs["is_cancelled"]()
            clock[0] = 131
            assert kwargs["is_cancelled"]()
            return AcpTurnResult(cancelled=True)

    monkeypatch.setattr(judge_module, "_build_session", lambda *a, **kw: Session())
    monkeypatch.setattr(judge_module, "_start_session", lambda *a: None)
    case = CaseSpec.model_validate(
        {
            "id": "test",
            "name": "test",
            "input": "task",
            "expected": "result",
            "graders": [
                {"id": "q", "name": "q", "type": "llm_rubric", "rubric": "fixed", "weight": 1}
            ],
        }
    )
    result = judge_module.ChrysJudge(Settings(data_dir=tmp_path))._evaluate_batch(
        anonymous_id="candidate",
        case=case,
        graders=case.graders,
        evidence={},
        profile=EvalProfile(
            runner_model="r", judge_model="j", timeout_seconds=1800, judge_timeout_seconds=30
        ),
        artifact_dir=tmp_path,
    )
    assert "30s budget" in result.error


def test_partial_judge_failure_shows_valid_dimensions_without_total():
    from types import SimpleNamespace

    from aaw_skill_eval.modules.results.dimensions import dimension_summary, dimension_total

    run = SimpleNamespace(
        group_name="current",
        status="judge_error",
        execution_status="completed",
        exit_code=0,
        case_id="c",
        score_json=json.dumps(
            {
                "dimensions": [{"id": "code", "score": 100, "invalid": False, "passed": True}],
                "workflow_completion": {"passed": True},
            }
        ),
    )
    definition = {
        "dimensions": [
            {"id": "code", "hard_gate": False, "weight": 1},
            {"id": "doc", "hard_gate": False, "weight": 1},
        ],
        "cases": [{"id": "c", "graders": [{"dimension_id": "code"}, {"dimension_id": "doc"}]}],
    }
    dims = dimension_summary(SimpleNamespace(runs=[run], trials=1), definition, "current")
    assert dims[0]["score"] == 100 and dims[0]["completed"] == 1
    assert dims[1]["incomplete"]
    assert dimension_total(dims) is None
