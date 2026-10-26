import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import func, select

from aaw_skill_eval.app.main import create_app
from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import Assessment, Experiment, Run, Suite, SuiteDraft
from aaw_skill_eval.contracts.providers import register_provider
from aaw_skill_eval.contracts.schemas import (
    EvalProfile,
    ExperimentCreateRequest,
    ProviderSnapshot,
    SuiteCreateRequest,
)
from aaw_skill_eval.modules.evaluations import service as evaluations
from aaw_skill_eval.modules.results.projection import project_execution
from aaw_skill_eval.modules.results.views import _experiment_summary
from aaw_skill_eval.modules.suites.service import create_suite
from conftest import FakeJudge, FakeRunner


class FakeRuntime:
    def __init__(self, settings):
        pass

    def snapshot(self, model, *, role):
        return ProviderSnapshot(provider="fake", model_profile_id=model, model_id=model)

    def verify_snapshot(self, expected, *, role):
        pass


def setup_app(tmp_path, project):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    register_provider(
        "fake",
        runner=lambda settings: FakeRunner(),
        judge=lambda settings: FakeJudge(),
        runtime=FakeRuntime,
    )
    app.state.orchestrator.runner, app.state.orchestrator.judge = FakeRunner(), FakeJudge()
    request = SuiteCreateRequest(
        name="Reusable task",
        project_path=str(project),
        skill_path="missing-optional-reference",
        cases=[
            {
                "id": "task",
                "name": "Write result",
                "input": "Write result.md",
                "expected": "A useful result",
                "graders": [
                    {
                        "id": "exists",
                        "name": "Deliverable",
                        "type": "file_exists",
                        "path": "result.md",
                        "weight": 1,
                    }
                ],
            }
        ],
    )
    with app.state.session_factory() as session:
        suite = create_suite(session, app.state.settings, request, allow_legacy=True)
    return app, suite.id


def run_candidate(app, suite_id, **candidate):
    item = app.state.orchestrator.create(
        ExperimentCreateRequest(
            suite_id=suite_id,
            mode="quick",
            profile=EvalProfile(
                runner_provider="fake",
                judge_provider="fake",
                runner_model="model",
                judge_model="judge",
            ),
            **candidate,
        )
    )
    app.state.orchestrator.execute(item.id)
    with app.state.session_factory() as session:
        execution = session.get(Experiment, item.id)
        assert execution.status == "completed", execution.error_message
        assert len(execution.runs) == 1
        assert execution.runs[0].status == "completed", execution.runs[0].error_message
    assessment = evaluations.create(app.state.settings, app.state.session_factory, item.id)
    evaluations.execute(app.state.settings, app.state.session_factory, FakeJudge(), assessment.id)
    return item.id, assessment.id


def test_candidate_history_and_regrade_are_independent(tmp_path, project, skill):
    app, suite_id = setup_app(tmp_path, project)
    factory = app.state.session_factory
    first, baseline_id = run_candidate(app, suite_id, candidate_kind="no_skill")
    with factory() as session:
        suite = session.get(Suite, suite_id)
        assert suite.skill_id is None
        suite.baseline_experiment_id, suite.baseline_assessment_id = first, baseline_id
        session.commit()
    second, _ = run_candidate(app, suite_id, candidate_kind="skill", skill_path=str(skill))
    (skill / "references/guide.md").write_text("New version", encoding="utf8")
    third, _ = run_candidate(app, suite_id, candidate_kind="skill", skill_path=str(skill))
    regrade = evaluations.create(app.state.settings, factory, first)
    evaluations.execute(app.state.settings, factory, FakeJudge(), regrade.id)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Experiment)) == 3
        assert session.scalar(select(func.count()).select_from(Run)) == 3
        assert session.scalar(select(func.count()).select_from(Assessment)) == 4
        assert session.get(Suite, suite_id).baseline_assessment_id == baseline_id
        assert session.get(Experiment, first).current_revision_id is None
        assert (
            session.get(Experiment, second).current_revision_id
            != session.get(Experiment, third).current_revision_id
        )
        view = _experiment_summary(session.get(Experiment, first), baseline_id)
        assert view["assessment_id"] == baseline_id
        assert view["scores"]["current"] == 100
        assert view["candidate_kind"] == "no_skill"
    app.state.engine.dispose()


def test_judge_failure_does_not_fail_execution(tmp_path, project):
    from aaw_skill_eval.contracts.agents import JudgeOutcome

    class BrokenJudge:
        def evaluate(self, **kwargs):
            return JudgeOutcome(error="timeout")

    app, suite_id = setup_app(tmp_path, project)
    factory = app.state.session_factory
    with factory() as session:
        suite = session.get(Suite, suite_id)
        definition = json.loads(suite.definition_json)
        definition["cases"][0]["graders"].append(
            {
                "id": "quality",
                "name": "Quality",
                "type": "llm_rubric",
                "rubric": "Useful output",
                "weight": 1,
            }
        )
        suite.definition_json = json.dumps(definition)
        session.commit()
    execution_id, _ = run_candidate(app, suite_id)
    assessment = evaluations.create(app.state.settings, factory, execution_id)
    evaluations.execute(app.state.settings, factory, BrokenJudge(), assessment.id)
    with factory() as session:
        execution = session.get(Experiment, execution_id)
        assert execution.status == "completed"
        assert execution.runs[0].status == "completed"
        assert session.get(Assessment, assessment.id).status == "completed_with_failures"
        view = project_execution(execution)
        assert view.runs[0].execution_status == "completed"
        assert view.runs[0].status == "judge_error"
    app.state.engine.dispose()


def test_migration_preserves_definitions_and_requires_review(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    source = data / "skill-eval.db"
    with sqlite3.connect(source) as old:
        old.execute("CREATE TABLE suite_drafts (id TEXT, suite_id TEXT, data_json TEXT)")
        old.execute(
            "INSERT INTO suite_drafts VALUES ('draft', NULL, ?)",
            (json.dumps({"name": "Preserved", "requirement": "Use AAW"}),),
        )
    before = source.read_bytes()
    app = create_app(Settings(data_dir=data))
    with app.state.session_factory() as session:
        draft = session.get(SuiteDraft, "draft")
        payload = json.loads(draft.data_json)
        assert draft.status == "draft"
        assert payload["requirement"] == "Use AAW"
        assert payload["migration_review"]["required"]
        assert not payload["migration_review"]["confirmed"]
    assert source.read_bytes() == before
    app.state.engine.dispose()


def test_modules_do_not_import_concrete_agent_adapters():
    root = Path(__file__).parents[1] / "src/aaw_skill_eval/modules"
    for path in root.rglob("*.py"):
        assert "from aaw_skill_eval.adapters.agents" not in path.read_text(encoding="utf8"), path


def test_assessment_dispatch_failure_is_retryable_without_rerun(tmp_path, project):
    app, suite_id = setup_app(tmp_path, project)
    execution_id, _ = run_candidate(app, suite_id)
    evaluations.record_failure(app.state.session_factory, execution_id, "Judge startup failed")
    with app.state.session_factory() as session:
        execution = session.get(Experiment, execution_id)
        assert execution.status == "completed"
        view = project_execution(execution)
        assert view.status == "completed_with_failures"
        assert view.runs[0].status == "judge_error"
        assert "startup failed" in view.runs[0].error_message
    next_score = evaluations.create(app.state.settings, app.state.session_factory, execution_id)
    assert next_score.status == "queued"
    app.state.engine.dispose()


@pytest.mark.parametrize("failure", ["skill_leak", "nonzero_exit"])
def test_execution_rejects_skill_leak_and_unreported_exit_failure(tmp_path, project, failure):
    app, suite_id = setup_app(tmp_path, project)

    class InvalidRunner(FakeRunner):
        def run(self, **kwargs):
            outcome = super().run(**kwargs)
            if failure == "skill_leak":
                outcome.skills_loaded = ["unexpected-project-skill"]
            else:
                outcome.exit_code = 2
            return outcome

    app.state.orchestrator.runner = InvalidRunner()
    execution = app.state.orchestrator.create(
        ExperimentCreateRequest(
            suite_id=suite_id,
            candidate_kind="no_skill",
            mode="quick",
            profile=EvalProfile(
                runner_provider="fake",
                judge_provider="fake",
                runner_model="model",
                judge_model="judge",
            ),
        )
    )
    app.state.orchestrator.execute(execution.id)
    with app.state.session_factory() as session:
        item = session.get(Experiment, execution.id)
        assert item.status == "completed_with_failures"
        assert item.runs[0].error_kind == (
            "skill_isolation_error" if failure == "skill_leak" else "agent_error"
        )
    app.state.engine.dispose()


def test_baseline_api_pins_assessment_and_rejects_foreign_score(tmp_path, project, skill):
    from fastapi.testclient import TestClient

    app, suite_id = setup_app(tmp_path, project)
    first, assessment = run_candidate(app, suite_id)
    second, other = run_candidate(app, suite_id, candidate_kind="skill", skill_path=str(skill))
    client = TestClient(app)
    path = f"/api/v1/benchmark/suites/{suite_id}/baseline"
    response = client.post(path, json={"experiment_id": first, "assessment_id": assessment})
    assert response.status_code == 200, response.text
    assert response.json()["baseline_assessment_id"] == assessment
    assert (
        client.post(path, json={"experiment_id": first, "assessment_id": other}).status_code == 404
    )
    detail = client.get(f"/api/v1/experiments/{second}").json()
    assert detail["execution_status"] == "completed"
    assert detail["presentation"]["cases"][0]["verdict"] == "Pass"
    comparison = client.get(f"/api/v1/benchmark/suites/{suite_id}/comparison/{second}").json()
    assert comparison["formal"] is True
    files = client.get(
        f"/api/v1/benchmark/assessments/{assessment}/runs/{client.get(f'/api/v1/experiments/{first}').json()['runs'][0]['id']}/artifacts"
    ).json()
    assert any(f["name"] == "scores.json" for f in files["items"])
    app.state.engine.dispose()


def test_tampered_artifacts_cannot_be_regraded(tmp_path, project):
    app, suite_id = setup_app(tmp_path, project)
    execution_id, _ = run_candidate(app, suite_id)
    with app.state.session_factory() as session:
        run = session.get(Experiment, execution_id).runs[0]
        (Path(run.artifact_path) / "terminal-evidence.json").write_text("{}", encoding="utf8")
    assessment = evaluations.create(app.state.settings, app.state.session_factory, execution_id)
    evaluations.execute(app.state.settings, app.state.session_factory, FakeJudge(), assessment.id)
    with app.state.session_factory() as session:
        result = session.get(Assessment, assessment.id)
        assert result.status == "completed_with_failures"
        assert "证据已变化" in result.results[0].error_message
        assert session.get(Experiment, execution_id).status == "completed"
    app.state.engine.dispose()


def test_workflow_compliance_does_not_change_common_score(tmp_path, project, skill):
    app, suite_id = setup_app(tmp_path, project)
    entry = skill / "SKILL.md"
    entry.write_text(
        entry.read_text(encoding="utf8").replace("example-skill", "aaw-workflow"), encoding="utf8"
    )
    with app.state.session_factory() as session:
        suite = session.get(Suite, suite_id)
        definition = json.loads(suite.definition_json)
        definition["cases"][0]["workflow"] = {"entry": "sr", "sr": "SR-test"}
        suite.definition_json = json.dumps(definition)
        session.commit()
    execution_id, _ = run_candidate(app, suite_id, candidate_kind="skill", skill_path=str(skill))
    with app.state.session_factory() as session:
        item = session.get(Experiment, execution_id)
        view = project_execution(item)
        scores = json.loads(view.runs[0].score_json)
        assert scores["workflow_completion"]["passed"] is False
        assert scores["hard_gates_total"] == 0
        assert _experiment_summary(item)["scores"]["current"] == 100
    app.state.engine.dispose()
