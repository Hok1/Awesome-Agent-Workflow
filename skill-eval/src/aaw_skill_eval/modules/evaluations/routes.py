from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select

from aaw_skill_eval.contracts.entities import Experiment, TrialAssessment
from aaw_skill_eval.contracts.http import RejudgeInput
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.http_artifacts import (
    _log_stream_payload,
    _media_type_for,
    _safe_artifact_dir,
)
from aaw_skill_eval.modules.suites.access import suite

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    def result_root(assessment_id, run_id, session):
        item = session.scalar(
            select(TrialAssessment).where(
                TrialAssessment.assessment_id == assessment_id, TrialAssessment.run_id == run_id
            )
        )
        if not item:
            raise EvalError("ASSESSMENT_NOT_FOUND", "评分记录不存在", status_code=404)
        return _safe_artifact_dir(settings, item.artifact_path)

    @router.get("/assessments/{assessment_id}/runs/{run_id}/logs")
    def logs(
        assessment_id: str,
        run_id: str,
        cursor: str | None = None,
        mode: str = "events",
        session=Depends(dependency),
    ):
        root = result_root(assessment_id, run_id, session)
        if not root:
            return {"records": [], "next_cursor": "", "pending": True}
        return _log_stream_payload(
            root / "logs" / "index.jsonl",
            cursor=cursor,
            channels=None,
            sources=None,
            mode=mode,
            unmasked=False,
            limit_bytes=100000,
        )

    @router.get("/assessments/{assessment_id}/runs/{run_id}/artifacts")
    def artifacts(assessment_id: str, run_id: str, session=Depends(dependency)):
        root = result_root(assessment_id, run_id, session)
        return {
            "items": [
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "url": (
                        f"/api/v1/benchmark/assessments/{assessment_id}"
                        f"/runs/{run_id}/artifacts/{p.name}"
                    ),
                }
                for p in sorted(root.iterdir())
                if p.is_file()
            ]
            if root
            else []
        }

    @router.get("/assessments/{assessment_id}/runs/{run_id}/artifacts/{name}")
    def artifact(assessment_id: str, run_id: str, name: str, session=Depends(dependency)):
        root = result_root(assessment_id, run_id, session)
        path = (root / name).resolve() if root else None
        if not path or path.parent != root or not path.is_file():
            raise EvalError("ARTIFACT_NOT_FOUND", "评分产物不存在", status_code=404)
        return FileResponse(path, media_type=_media_type_for(path))

    @router.post("/suites/{key}/experiments/{experiment_id}/rejudge", status_code=202)
    async def rejudge(
        key: str, experiment_id: str, request: RejudgeInput, session=Depends(dependency)
    ):
        from aaw_skill_eval.modules.evaluations.service import create as create_regrade

        suite(session, key)
        original = session.get(Experiment, experiment_id)
        if not original or original.suite_id != key:
            raise EvalError("EXPERIMENT_NOT_FOUND", "执行记录不存在", status_code=404)
        item = create_regrade(
            settings,
            factory,
            experiment_id,
            request.judge_model,
            judge_timeout_seconds=request.judge_timeout_seconds,
            judge_total_timeout_seconds=request.judge_total_timeout_seconds,
        )
        await jobs.enqueue_assessment(item.id)
        return {
            "id": experiment_id,
            "assessment_id": item.id,
            "status": "queued",
        }

    return router
