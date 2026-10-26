from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from aaw_skill_eval.contracts.entities import Experiment
from aaw_skill_eval.contracts.http import ExecuteInput
from aaw_skill_eval.contracts.providers import RUNTIME_FACTORIES
from aaw_skill_eval.contracts.schemas import ExperimentCreateRequest
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.modules.suites.access import suite

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    @router.get("/skill-revisions")
    def revisions(session=Depends(dependency)):
        from aaw_skill_eval.contracts.entities import SkillRevision

        return {
            "items": [
                {
                    "id": r.id,
                    "name": r.skill.name,
                    "content_hash": r.content_hash,
                    "source_path": r.source_path,
                }
                for r in session.scalars(
                    select(SkillRevision).order_by(SkillRevision.created_at.desc())
                )
            ]
        }

    @router.post("/suites/{key}/execute", status_code=202)
    async def execute(key: str, request: ExecuteInput, session=Depends(dependency)):
        suite(session, key)
        if any(
            provider not in {"chrys", *RUNTIME_FACTORIES}
            for provider in (request.profile.runner_provider, request.profile.judge_provider)
        ):
            raise EvalError("UNSUPPORTED_AGENT", "新流程仅提供 Chrys Agent", status_code=422)
        if session.scalar(
            select(Experiment.id).where(Experiment.suite_id == key, Experiment.status.in_(ACTIVE))
        ):
            raise EvalError("SUITE_RUNNING", "测试套已有正在执行的任务", status_code=409)
        exp = orchestrator.create(
            ExperimentCreateRequest(
                suite_id=key,
                profile=request.profile,
                mode=request.mode,
                evaluation_mode="current_only",
                candidate_kind=request.candidate_kind,
                skill_path=request.skill_path,
                skill_revision_id=request.skill_revision_id,
            )
        )
        await jobs.enqueue(exp.id)
        return {"id": exp.id}

    @router.post("/suites/{key}/experiments/{experiment_id}/retry", status_code=202)
    async def rerun(key: str, experiment_id: str, session=Depends(dependency)):
        item = suite(session, key)
        original = session.get(Experiment, experiment_id)
        if not original or original.suite_id != key:
            raise EvalError("EXPERIMENT_NOT_FOUND", "执行记录不存在", status_code=404)
        if item.archived:
            raise EvalError("SUITE_ARCHIVED", "请先恢复测试套", status_code=409)
        if session.scalar(
            select(Experiment.id).where(Experiment.suite_id == key, Experiment.status.in_(ACTIVE))
        ):
            raise EvalError("SUITE_RUNNING", "测试套已有正在执行的任务", status_code=409)
        exp = orchestrator.create_retry(experiment_id, refresh_runtime=True)
        await jobs.enqueue(exp.id)
        return {"id": exp.id, "retry_of_experiment_id": experiment_id, "runtime_refreshed": True}

    return router


def build_creation_router(orchestrator, jobs):
    router = APIRouter(prefix="/api/v1")

    @router.post("/experiments", status_code=202)
    async def create(request: ExperimentCreateRequest):
        item = orchestrator.create(request)
        await jobs.enqueue(item.id)
        return {"id": item.id, "status": item.status}

    return router
