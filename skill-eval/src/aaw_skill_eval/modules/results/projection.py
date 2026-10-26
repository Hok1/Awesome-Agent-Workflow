"""Read models join immutable executions with a selected assessment, without ORM writes."""

import json

from aaw_skill_eval.errors import EvalError


class View:
    def __init__(self, source, **values):
        self._source = source
        self.__dict__.update(values)

    def __getattr__(self, name):
        return getattr(self._source, name)


def project_execution(execution, assessment_id=None):
    if isinstance(execution, View):
        return execution
    assessments = list(execution.assessments)
    assessment = (
        next((a for a in assessments if a.id == assessment_id), None)
        if assessment_id
        else (assessments[-1] if assessments else None)
    )
    if assessment_id and not assessment:
        raise EvalError("ASSESSMENT_NOT_FOUND", "评分记录不属于此执行", status_code=404)
    results = {r.run_id: r for r in assessment.results} if assessment else {}
    runs = []
    for run in execution.runs:
        result = results.get(run.id)
        scores = json.loads(result.score_json or "{}") if result else {}
        state = result.status if result and run.status == "completed" else run.status
        if run.status == "completed" and not result:
            state = "queued"
        runs.append(
            View(
                run,
                execution_status=run.status,
                status=state,
                assessment_artifact_path=result.artifact_path if result else None,
                score_json=result.score_json if result else None,
                quality_score=scores.get("quality_score"),
                hard_gates_passed=scores.get("hard_gates_passed", 0),
                hard_gates_total=scores.get("hard_gates_total", 0),
                error_kind=run.error_kind
                or (state if state not in {"completed", "queued", "running"} else None),
                error_message=run.error_message or (result.error_message if result else None),
                current_stage="judge" if result and state == "running" else run.current_stage,
            )
        )
    state = execution.status
    if not assessment and state == "completed":
        state = "running"
    if assessment and state not in {"queued", "preparing", "running", "cancelled"}:
        state = "running" if assessment.status in {"queued", "running"} else assessment.status
    return View(
        execution,
        runs=runs,
        status=state,
        execution_status=execution.status,
        assessment_id=assessment.id if assessment else None,
        assessment_status=assessment.status if assessment else "not_started",
        profile_json=assessment.profile_json if assessment else execution.profile_json,
    )
