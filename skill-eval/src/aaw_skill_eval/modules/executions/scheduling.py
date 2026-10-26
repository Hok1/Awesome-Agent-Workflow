from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from aaw_skill_eval.contracts.entities import Experiment, Run
from aaw_skill_eval.infrastructure.database import with_lock_retry
from aaw_skill_eval.modules.executions.progress import now


def db_write(session_factory: sessionmaker[Session], work):
    """Run one session transaction with bounded retry on SQLite locks.

    Every execution thread opens its own short-lived session (the factory
    is thread-safe and pooled), so the two runs of a pair never share a
    session; this wrapper only adds lock-error resilience.
    """

    def attempt():
        with session_factory() as session:
            result = work(session)
            session.commit()
            return result

    return with_lock_retry(attempt)


def experiment_cancelled(session_factory: sessionmaker[Session], experiment_id: str) -> bool:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        return bool(experiment is None or experiment.cancel_requested_at)


def claim_run(session_factory: sessionmaker[Session], run_id: str) -> dict | None:
    """Atomically claim a queued run (queued -> running) and snapshot it.

    The conditional UPDATE makes the claim safe under concurrency: if two
    threads (or a retry racing the scheduler) try to claim the same run,
    exactly one UPDATE matches and the loser sees rowcount 0.
    """
    timestamp = now()

    def work(session: Session) -> dict | None:
        claimed = session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(
                status="running",
                current_stage="creating_workspace",
                started_at=timestamp,
                stage_started_at=timestamp,
                last_activity_at=timestamp,
                last_heartbeat_at=timestamp,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.rollback()
            return None
        run = session.get(Run, run_id)
        assert run is not None
        return {
            "run_id": run.id,
            "experiment_id": run.experiment_id,
            "case_id": run.case_id,
            "group": run.group_name,
            "trial_index": run.trial_index,
            "anonymous_id": run.anonymous_id,
            "attempt": run.current_attempt,
            "started_at": timestamp,
        }

    return db_write(session_factory, work)


def ordered_runs(factory, execution_id, definition):
    order = {case["id"]: i for i, case in enumerate(definition["cases"])}
    with factory() as session:
        runs = session.scalars(
            select(Run).where(Run.experiment_id == execution_id, Run.status == "queued")
        ).all()
        return [r.id for r in sorted(runs, key=lambda r: (order[r.case_id], r.trial_index))]
