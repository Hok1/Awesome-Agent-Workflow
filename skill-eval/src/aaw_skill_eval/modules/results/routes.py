from __future__ import annotations

import json
from collections import defaultdict, deque

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from aaw_skill_eval.contracts.entities import Experiment, HumanReview, Run
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.http_artifacts import (
    TEXT_MEDIA_TYPES,
    _artifact_dir,
    _attempt_artifact_dir,
    _attempt_dirs,
    _judge_progress,
    _legacy_log_items,
    _log_file_items,
    _log_file_preview,
    _log_file_response,
    _log_stream_payload,
    _media_type_for,
    _run_output_bytes,
)
from aaw_skill_eval.infrastructure.observability.conversation import rebuild_conversation
from aaw_skill_eval.infrastructure.observability.logs import MAX_LOG_READ_BYTES, display_record
from aaw_skill_eval.modules.results.projection import project_execution
from aaw_skill_eval.modules.results.verdicts import presentation
from aaw_skill_eval.modules.results.views import (
    _age_seconds,
    _execution_status,
    _experiment_summary,
    _iso,
    _masked_diagnostic,
    _profile_payload,
)


def build_router(*, settings, session_factory, get_session, orchestrator, jobs):
    router = APIRouter(prefix="/api/v1")

    @router.get("/experiments")
    def list_experiments(limit: int = 50, session: Session = Depends(get_session)):
        limit = min(max(limit, 1), 200)
        experiments = session.scalars(
            select(Experiment).order_by(Experiment.created_at.desc()).limit(limit)
        ).all()
        return {"items": [_experiment_summary(item) for item in experiments]}

    @router.get("/experiments/{experiment_id}")
    def get_experiment(
        experiment_id: str,
        assessment_id: str | None = None,
        session: Session = Depends(get_session),
    ):
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
        experiment = project_execution(experiment, assessment_id)
        reviews = defaultdict(list)
        run_ids = [run.id for run in experiment.runs]
        if run_ids:
            for review in session.scalars(
                select(HumanReview).where(HumanReview.run_id.in_(run_ids))
            ):
                reviews[review.run_id].append(
                    {
                        "id": review.id,
                        "score": review.score,
                        "note": review.note,
                        "reviewer": review.reviewer,
                        "created_at": _iso(review.created_at),
                    }
                )
        runs = []
        for run in sorted(
            experiment.runs,
            key=lambda item: (item.case_id, item.trial_index, item.group_name),
        ):
            runs.append(
                {
                    "id": run.id,
                    "execution_status": _execution_status(run),
                    "judge_progress": _judge_progress(settings, run),
                    "case_id": run.case_id,
                    "group": run.group_name,
                    "trial": run.trial_index,
                    "anonymous_id": run.anonymous_id,
                    "status": run.status,
                    "quality_score": run.quality_score,
                    "hard_gates": {
                        "passed": run.hard_gates_passed,
                        "total": run.hard_gates_total,
                    },
                    "duration_ms": run.duration_ms,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "exit_code": run.exit_code,
                    "error_kind": run.error_kind,
                    "error_message": run.error_message,
                    "current_stage": run.current_stage,
                    "stage_started_at": _iso(run.stage_started_at),
                    "last_heartbeat_at": _iso(run.last_heartbeat_at),
                    "last_activity_at": _iso(run.last_activity_at),
                    "heartbeat_age_seconds": _age_seconds(run.last_heartbeat_at),
                    "activity_age_seconds": _age_seconds(run.last_activity_at),
                    "stalled": bool(
                        run.status == "running"
                        and run.last_activity_at
                        and (_age_seconds(run.last_activity_at) or 0) >= 120
                    ),
                    "started_at": _iso(run.started_at),
                    "completed_at": _iso(run.completed_at),
                    "current_attempt": run.current_attempt,
                    "cancel_requested": run.cancel_requested_at is not None,
                    "workspace_retained": run.workspace_retained,
                    "artifact_available": bool(run.artifact_path),
                    "output_bytes": _run_output_bytes(settings, run),
                    "tracking_available": bool(run.current_stage or run.progress_events),
                    "attempts": [
                        {
                            "attempt": attempt.attempt_index,
                            "status": attempt.status,
                            "stage": attempt.stage,
                            "error_kind": attempt.error_kind,
                            "error_message": attempt.error_message,
                            "started_at": _iso(attempt.started_at),
                            "completed_at": _iso(attempt.completed_at),
                        }
                        for attempt in sorted(run.attempts, key=lambda item: item.attempt_index)
                    ],
                    "scores": json.loads(run.score_json) if run.score_json else None,
                    "reviews": reviews[run.id],
                }
            )
        return {
            **_experiment_summary(experiment),
            "profile_config": json.loads(experiment.profile_json),
            "suite_snapshot": json.loads(experiment.suite_snapshot_json),
            "runs": runs,
            "presentation": presentation(experiment, json.loads(experiment.suite_snapshot_json)),
        }

    @router.get("/experiments/{experiment_id}/logs")
    def experiment_logs(
        experiment_id: str,
        cursor: str | None = None,
        channels: str | None = None,
        sources: str | None = None,
        mode: str = "events",
        unmasked: bool = False,
        limit_bytes: int = MAX_LOG_READ_BYTES,
        session: Session = Depends(get_session),
    ):
        if session.get(Experiment, experiment_id) is None:
            raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
        return _log_stream_payload(
            settings.artifacts_dir / experiment_id / "logs" / "index.jsonl",
            cursor=cursor,
            channels=channels,
            sources=sources,
            mode=mode,
            unmasked=unmasked,
            limit_bytes=limit_bytes,
        )

    @router.get("/runs/{run_id}/logs")
    def run_logs(
        run_id: str,
        attempt: int | None = None,
        cursor: str | None = None,
        channels: str | None = None,
        sources: str | None = None,
        mode: str = "events",
        unmasked: bool = False,
        limit_bytes: int = MAX_LOG_READ_BYTES,
        tail: int | None = None,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        artifact_dir = _attempt_artifact_dir(settings, run, attempt)
        if tail is not None and cursor is None:
            return {"items": _legacy_log_items(artifact_dir, tail)}
        if artifact_dir is None:
            return {
                "records": [],
                "next_cursor": "",
                "reset_required": False,
                "historical": False,
                "pending": True,
                "has_more": False,
            }
        return _log_stream_payload(
            artifact_dir / "logs" / "index.jsonl",
            cursor=cursor,
            channels=channels,
            sources=sources,
            mode=mode,
            unmasked=unmasked,
            limit_bytes=limit_bytes,
        )

    @router.get("/runs/{run_id}/diagnostics")
    def run_diagnostics(
        run_id: str,
        attempt: int | None = None,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        artifact_dir = _attempt_artifact_dir(settings, run, attempt)
        invocations = []
        recent = deque(maxlen=100)
        if artifact_dir is not None:
            path = artifact_dir / "logs" / "index.jsonl"
            if path.is_file():
                with path.open(encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict):
                            continue
                        safe = display_record(record, mode="raw", unmasked=False)
                        if safe["channel"] == "invocation":
                            invocations.append(safe["details"])
                        else:
                            fields = ("timestamp", "source", "channel", "text")
                            recent.append({key: safe[key] for key in fields})
        return _masked_diagnostic(
            {
                "run_id": run.id,
                "experiment_id": run.experiment_id,
                "case_id": run.case_id,
                "group": run.group_name,
                "trial": run.trial_index,
                "attempt": attempt or run.current_attempt,
                "status": run.status,
                "stage": run.current_stage,
                "started_at": _iso(run.started_at),
                "stage_started_at": _iso(run.stage_started_at),
                "completed_at": _iso(run.completed_at),
                "error_kind": run.error_kind,
                "error_message": display_record(
                    {"text": run.error_message or ""}, mode="raw", unmasked=False
                )["text"],
                "heartbeat_age_seconds": _age_seconds(run.last_heartbeat_at),
                "activity_age_seconds": _age_seconds(run.last_activity_at),
                "output_bytes": _run_output_bytes(settings, run),
                "profile": _profile_payload(run.experiment),
                "invocations": invocations,
                "recent_logs": list(recent),
            }
        )

    @router.get("/experiments/{experiment_id}/log-files")
    def list_experiment_log_files(experiment_id: str, session: Session = Depends(get_session)):
        if session.get(Experiment, experiment_id) is None:
            raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
        root = settings.artifacts_dir / experiment_id / "logs"
        return {"items": _log_file_items(root, f"/api/v1/experiments/{experiment_id}/log-files")}

    @router.get("/experiments/{experiment_id}/log-files/{name:path}")
    def get_experiment_log_file(
        experiment_id: str,
        name: str,
        preview: bool = False,
        unmasked: bool = False,
        session: Session = Depends(get_session),
    ):
        if session.get(Experiment, experiment_id) is None:
            raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
        root = settings.artifacts_dir / experiment_id / "logs"
        if preview:
            return _log_file_preview(root, name, unmasked=unmasked)
        return _log_file_response(root, name)

    @router.get("/runs/{run_id}/log-files")
    def list_run_log_files(
        run_id: str,
        attempt: int | None = None,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        artifact_dir = _attempt_artifact_dir(settings, run, attempt)
        if artifact_dir is None:
            return {"items": [], "pending": True}
        suffix = f"?attempt={attempt}" if attempt is not None else ""
        return {
            "items": _log_file_items(
                artifact_dir,
                f"/api/v1/runs/{run_id}/log-files",
                suffix=suffix,
            )
        }

    @router.get("/runs/{run_id}/log-files/{name:path}")
    def get_run_log_file(
        run_id: str,
        name: str,
        attempt: int | None = None,
        preview: bool = False,
        unmasked: bool = False,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        artifact_dir = _attempt_artifact_dir(settings, run, attempt)
        if artifact_dir is None:
            raise EvalError("ARTIFACT_NOT_FOUND", "Run logs were not found", status_code=404)
        if preview:
            return _log_file_preview(artifact_dir, name, unmasked=unmasked)
        return _log_file_response(artifact_dir, name)

    @router.get("/runs/{run_id}/conversation")
    def run_conversation(
        run_id: str,
        source: str = "runner",
        unmasked: bool = False,
        session: Session = Depends(get_session),
    ):
        """Structured, read-only replay of one run's ACP conversation.

        Returns every attempt, each rebuilt as turns with prompt references,
        agent messages/thoughts and tool calls (input + result). Text fields
        are masked by default, matching the log console behaviour.
        """
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        if source not in {"runner", "judge"}:
            raise EvalError(
                "INVALID_SOURCE", "Conversation source must be runner or judge", status_code=400
            )
        attempts = []
        for attempt_index, artifact_dir in _attempt_dirs(settings, run):
            payload = rebuild_conversation(artifact_dir, source, run_status=run.status)
            payload["attempt"] = attempt_index
            attempts.append(payload)
        result = {
            "source": source,
            "run_id": run.id,
            "status": run.status,
            "pending": run.status == "running",
            "attempts": attempts,
        }
        if not unmasked:
            result = _masked_diagnostic(result)
        return result

    @router.get("/runs/{run_id}/artifacts")
    def list_run_artifacts(run_id: str, session: Session = Depends(get_session)):
        run = session.get(Run, run_id)
        artifact_dir = _artifact_dir(settings, run)
        return {
            "items": [
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "url": f"/api/v1/runs/{run_id}/artifacts/{path.name}",
                }
                for path in sorted(artifact_dir.iterdir(), key=lambda item: item.name)
                if path.is_file()
            ]
        }

    @router.get("/runs/{run_id}/artifacts/{name}")
    def get_run_artifact(
        run_id: str,
        name: str,
        session: Session = Depends(get_session),
    ):
        run = session.get(Run, run_id)
        artifact_dir = _artifact_dir(settings, run)
        path = (artifact_dir / name).resolve()
        if path.parent != artifact_dir or not path.is_file():
            raise EvalError("ARTIFACT_NOT_FOUND", "Artifact was not found", status_code=404)
        # Text evidence (markdown reports, patches, scores) renders inline in
        # the browser instead of triggering a download.
        disposition = "inline" if path.suffix.lower() in TEXT_MEDIA_TYPES else "attachment"
        return FileResponse(
            path,
            media_type=_media_type_for(path),
            content_disposition_type=disposition,
        )

    return router
