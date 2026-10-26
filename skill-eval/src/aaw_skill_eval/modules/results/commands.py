from __future__ import annotations

from fastapi import APIRouter, Depends

from aaw_skill_eval.contracts.entities import Experiment
from aaw_skill_eval.contracts.http import BaselineInput
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.modules.results.comparison import baseline_ready, comparison
from aaw_skill_eval.modules.results.suites import suite_view
from aaw_skill_eval.modules.results.views import _experiment_summary
from aaw_skill_eval.modules.suites.access import suite

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    @router.post("/suites/{key}/baseline")
    def baseline(key: str, request: BaselineInput, session=Depends(dependency)):
        item = suite(session, key)
        if request.experiment_id:
            exp = session.get(Experiment, request.experiment_id)
            if (
                not exp
                or exp.suite_id != key
                or not baseline_ready(_experiment_summary(exp, request.assessment_id), "current")
            ):
                raise EvalError(
                    "INVALID_BASELINE",
                    "请选择本测试套 Trial 齐全、有得分且门禁通过的结果组",
                    status_code=422,
                )
        item.baseline_assessment_id = (
            _experiment_summary(exp, request.assessment_id)["assessment_id"]
            if request.experiment_id
            else None
        )
        item.baseline_experiment_id = request.experiment_id
        item.baseline_group = "current"
        session.commit()
        return suite_view(session, item)

    @router.get("/suites/{key}/comparison/{experiment_id}")
    def compare(
        key: str, experiment_id: str, assessment_id: str | None = None, session=Depends(dependency)
    ):
        item = suite(session, key)
        exp = session.get(Experiment, experiment_id)
        if not exp or exp.suite_id != key:
            raise EvalError("EXPERIMENT_NOT_FOUND", "执行记录不存在", status_code=404)
        base = (
            session.get(Experiment, item.baseline_experiment_id)
            if item.baseline_experiment_id
            else None
        )
        return comparison(
            exp,
            base,
            item.baseline_group,
            assessment_id=assessment_id,
            baseline_assessment_id=item.baseline_assessment_id,
        )

    return router
