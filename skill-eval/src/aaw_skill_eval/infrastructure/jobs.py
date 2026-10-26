from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import Assessment, Experiment, Run, TrialAssessment
from aaw_skill_eval.infrastructure.workspace.cleanup import (
    cleanup_orphan_workspaces,
    remove_run_workspace_dirs,
)
from aaw_skill_eval.modules.executions.service import ExperimentOrchestrator


def mark_service_restart(settings: Settings, session_factory: sessionmaker[Session]) -> None:
    """Mark unfinished work as interrupted after a service restart.

    Execution and assessment states recover independently. Retrying an execution
    clones a fresh workspace; retrying an assessment reuses frozen evidence.
    """
    interrupted_runs: list[tuple[str, str, int]] = []
    with session_factory() as session:
        experiment_ids = session.scalars(
            select(Experiment.id).where(Experiment.status.in_(["preparing", "running"]))
        ).all()
        if experiment_ids:
            interrupted_runs = [
                (run.experiment_id, run.id, run.current_attempt)
                for run in session.scalars(
                    select(Run).where(
                        Run.experiment_id.in_(experiment_ids), Run.status == "running"
                    )
                ).all()
            ]
        session.execute(
            update(Experiment)
            .where(Experiment.status.in_(["preparing", "running"]))
            .values(
                status="interrupted",
                error_kind="infra_error",
                error_message="Service restarted",
            )
        )
        session.execute(
            update(Run)
            .where(Run.status == "running")
            .values(
                status="infra_error",
                current_stage="infra_error",
                error_kind="infra_error",
                error_message="Service restarted",
                completed_at=datetime.now(UTC),
            )
        )
        session.execute(
            update(Assessment).where(Assessment.status == "running").values(status="interrupted")
        )
        session.execute(
            update(TrialAssessment)
            .where(TrialAssessment.status == "running")
            .values(status="judge_error", error_message="评分服务重启，可重试评分")
        )
        session.commit()
    for experiment_id, run_id, attempt in interrupted_runs:
        result = remove_run_workspace_dirs(settings, experiment_id, run_id, attempt)
        retained = bool(result["failed"])
        with session_factory() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.workspace_retained = retained
                session.commit()


class JobManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        orchestrator: ExperimentOrchestrator,
    ) -> None:
        self.session_factory = session_factory
        self.orchestrator = orchestrator
        self.queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        self.worker: asyncio.Task | None = None

    async def start(self) -> None:
        # 纯手动清理模式：启动时只清孤儿目录（数据库无记录的残留），
        # 有记录的现场一律保留，由用户在页面手动清理。
        cleanup_orphan_workspaces(
            self.orchestrator.settings,
            self.session_factory,
        )
        mark_service_restart(self.orchestrator.settings, self.session_factory)
        from aaw_skill_eval.modules.evaluations.service import record_failure

        with self.session_factory() as session:
            unscored = session.scalars(
                select(Experiment.id).where(
                    Experiment.status.in_(["completed", "completed_with_failures"]),
                    ~Experiment.assessments.any(),
                    Experiment.runs.any(Run.status == "completed"),
                )
            ).all()
        for execution_id in unscored:
            record_failure(self.session_factory, execution_id, "评分启动前服务中断，可重新评分")
        with self.session_factory() as session:
            queued = list(
                session.scalars(
                    select(Experiment.id)
                    .where(Experiment.status == "queued")
                    .order_by(Experiment.created_at)
                )
            )
            session.commit()
        self.worker = asyncio.create_task(self._run(), name="skill-eval-worker")
        with self.session_factory() as session:
            assessments = session.scalars(
                select(Assessment.id).where(Assessment.status == "queued")
            ).all()
        for assessment_id in assessments:
            await self.enqueue_assessment(assessment_id)
        for experiment_id in queued:
            await self.queue.put(("experiment", experiment_id))

    async def stop(self) -> None:
        if self.worker is None:
            return
        await self.queue.put(None)
        with suppress(asyncio.CancelledError):
            await self.worker
        self.worker = None

    async def enqueue(self, experiment_id: str) -> None:
        await self.queue.put(("experiment", experiment_id))

    async def enqueue_assessment(self, assessment_id):
        await self.queue.put(("assessment", assessment_id))

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            scoring_id = None
            try:
                if job is None:
                    return
                kind, item_id = job
                from aaw_skill_eval.modules.evaluations import service as evaluations

                if kind == "assessment":
                    scoring_id = item_id
                    await asyncio.to_thread(
                        evaluations.execute,
                        self.orchestrator.settings,
                        self.session_factory,
                        self.orchestrator.judge,
                        item_id,
                    )
                else:
                    await asyncio.to_thread(self.orchestrator.execute, item_id)
                    with self.session_factory() as session:
                        execution = session.get(Experiment, item_id)
                        ready = execution and any(
                            run.status == "completed" for run in execution.runs
                        )
                    if ready:
                        assessment = await asyncio.to_thread(
                            evaluations.create,
                            self.orchestrator.settings,
                            self.session_factory,
                            item_id,
                        )
                        scoring_id = assessment.id
                        await asyncio.to_thread(
                            evaluations.execute,
                            self.orchestrator.settings,
                            self.session_factory,
                            self.orchestrator.judge,
                            assessment.id,
                        )
            except Exception as exc:
                if scoring_id:
                    with self.session_factory() as session:
                        assessment = session.get(Assessment, scoring_id)
                        execution_id = assessment.execution_id
                    evaluations.record_failure(self.session_factory, execution_id, exc, scoring_id)
                    continue
                if job is None or job[0] != "experiment":
                    continue
                experiment_id = job[1]
                with self.session_factory() as session:
                    experiment = session.get(Experiment, experiment_id)
                    finished = experiment is not None and experiment.status in {
                        "completed",
                        "completed_with_failures",
                    }
                    if experiment is not None and not finished:
                        experiment.status = "failed"
                        experiment.error_kind = "infra_error"
                        experiment.error_message = f"{type(exc).__name__}: {exc}"[:10_000]
                        experiment.completed_at = datetime.now(UTC)
                        session.commit()
                if finished:
                    evaluations.record_failure(self.session_factory, experiment_id, exc)
            finally:
                self.queue.task_done()
