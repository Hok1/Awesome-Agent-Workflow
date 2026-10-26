from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from aaw_skill_eval.contracts.entities import Run, RunProgressEvent
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.workspace.cleanup import (
    cleanup_experiment_workspaces,
    cleanup_run_workspace,
    workspace_usage,
)
from aaw_skill_eval.modules.results.views import _age_seconds, _iso


def build_router(*, settings, session_factory, get_session, orchestrator, jobs):
    router = APIRouter(prefix="/api/v1")

    @router.post("/experiments/{experiment_id}/cancel", status_code=202)
    def cancel_experiment(experiment_id: str):
        from aaw_skill_eval.contracts.entities import Assessment, Experiment

        with session_factory() as session:
            item = session.get(Experiment, experiment_id)
            if item and item.status not in {"queued", "preparing", "running", "interrupted"}:
                active = session.scalars(
                    select(Assessment).where(
                        Assessment.execution_id == experiment_id,
                        Assessment.status.in_(["queued", "running"]),
                    )
                ).all()
                if active:
                    for assessment in active:
                        assessment.cancel_requested = True
                    session.commit()
                    return {"id": item.id, "status": "running", "cancel_requested": True}
        experiment = orchestrator.request_experiment_cancel(experiment_id)
        return {"id": experiment.id, "status": experiment.status, "cancel_requested": True}

    @router.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str):
        run = orchestrator.request_run_cancel(run_id)
        return {"id": run.id, "status": run.status, "cancel_requested": True}

    @router.post("/runs/{run_id}/workspace-cleanup")
    def run_workspace_cleanup(run_id: str):
        # 只删除 workspaces/ 下的现场目录；数据库记录与证据包不受影响
        return cleanup_run_workspace(settings, session_factory, run_id)

    @router.post("/experiments/{experiment_id}/workspace-cleanup")
    def experiment_workspace_cleanup(experiment_id: str):
        return cleanup_experiment_workspaces(settings, session_factory, experiment_id)

    @router.get("/experiments/{experiment_id}/workspace-usage")
    def experiment_workspace_usage(experiment_id: str):
        # 目录大小按需计算，调用方须避免放进轮询路径
        return workspace_usage(settings, session_factory, experiment_id)

    @router.get("/runs/{run_id}/events")
    def run_events(
        run_id: str,
        after: int = 0,
        limit: int = 500,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        limit = min(max(limit, 1), 2000)
        events = session.scalars(
            select(RunProgressEvent)
            .where(RunProgressEvent.run_id == run_id, RunProgressEvent.id > max(after, 0))
            .order_by(RunProgressEvent.id)
            .limit(limit)
        ).all()
        return {
            "items": [
                {
                    "id": item.id,
                    "attempt": item.attempt,
                    "kind": item.kind,
                    "stage": item.stage,
                    "message": item.message,
                    "created_at": _iso(item.created_at),
                }
                for item in events
            ],
            "state": {
                "status": run.status,
                "stage": run.current_stage,
                "heartbeat_age_seconds": _age_seconds(run.last_heartbeat_at),
                "activity_age_seconds": _age_seconds(run.last_activity_at),
                "stalled": bool(
                    run.status == "running"
                    and run.last_activity_at
                    and (_age_seconds(run.last_activity_at) or 0) >= 120
                ),
            },
        }

    return router
