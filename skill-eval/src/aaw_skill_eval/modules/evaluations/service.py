"""Assessment lifecycle: scoring never creates or mutates an execution."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlalchemy import select

from aaw_skill_eval.contracts.agents import JudgeOutcome
from aaw_skill_eval.contracts.entities import Assessment, Experiment, Run, TrialAssessment, utc_now
from aaw_skill_eval.contracts.providers import build_judge, runtime
from aaw_skill_eval.contracts.schemas import CaseSpec, DimensionSpec, EvalProfile
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.observability.logs import LogWriter
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json, content_hash, write_json
from aaw_skill_eval.infrastructure.storage.frozen import artifact_hash
from aaw_skill_eval.modules.evaluations.graders import (
    ScoreComponent,
    execution_time_component,
    merge_scores,
)

ACTIVE = {"queued", "running"}


def record_failure(factory, execution_id, error, assessment_id=None):
    """Keep scheduler failures in scoring history without changing execution state."""
    with factory() as session:
        execution = session.get(Experiment, execution_id)
        item = session.get(Assessment, assessment_id) if assessment_id else None
        if item is None:
            item = Assessment(execution_id=execution_id, profile_json=execution.profile_json)
            session.add(item)
            session.flush()
            item.results = [
                TrialAssessment(
                    run_id=run.id, status="queued" if run.status == "completed" else "blocked"
                )
                for run in execution.runs
            ]
        item.status = "completed_with_failures"
        item.error_message = str(error)[:4000]
        item.completed_at = utc_now()
        for result in item.results:
            if result.status in ACTIVE:
                result.status = "judge_error"
                result.error_message = item.error_message
                result.completed_at = item.completed_at
        session.commit()


def create(
    settings,
    factory,
    execution_id,
    judge_model=None,
    *,
    judge_timeout_seconds=300,
    judge_total_timeout_seconds=900,
):
    with factory() as session:
        execution = session.get(Experiment, execution_id)
        if not execution:
            raise EvalError("EXECUTION_NOT_FOUND", "执行记录不存在", status_code=404)
        if execution.status in {"queued", "preparing", "running"}:
            raise EvalError("EXECUTION_ACTIVE", "请等待执行结束", status_code=409)
        if not any(run.status == "completed" for run in execution.runs):
            raise EvalError("NO_ARTIFACTS", "没有已完成的执行产物，请重新执行", status_code=422)
        if any(item.status in ACTIVE for item in execution.assessments):
            raise EvalError("ASSESSMENT_ACTIVE", "当前执行已有评分任务", status_code=409)
        profile = EvalProfile.model_validate_json(execution.profile_json)
        if judge_model:
            profile = profile.model_copy(
                update={
                    "judge_model": judge_model,
                    "judge_timeout_seconds": judge_timeout_seconds,
                    "judge_total_timeout_seconds": judge_total_timeout_seconds,
                    "judge_snapshot": runtime(settings, profile.judge_provider).snapshot(
                        judge_model, role="judge"
                    ),
                }
            )
        item = Assessment(execution_id=execution_id, profile_json=profile.model_dump_json())
        session.add(item)
        session.flush()
        for run in execution.runs:
            session.add(
                TrialAssessment(
                    assessment_id=item.id,
                    run_id=run.id,
                    status="queued" if run.status == "completed" else "blocked",
                    error_message=None if run.status == "completed" else "执行未完成，无法评分",
                )
            )
        session.commit()
        return item


def source_artifacts(settings, run):
    root = Path(run.artifact_path or "").resolve()
    if not root.is_relative_to(settings.artifacts_dir.resolve()) or run.status != "completed":
        raise EvalError("INVALID_ARTIFACTS", "执行产物不存在或执行未完成")
    if not run.artifact_hash or artifact_hash(root) != run.artifact_hash:
        raise EvalError("ARTIFACTS_CHANGED", "冻结的执行证据已变化，不能用于重新评分")
    evidence = json.loads((root / "terminal-evidence.json").read_text(encoding="utf-8"))
    record = json.loads((root / "run.json").read_text(encoding="utf-8"))
    deterministic = json.loads((root / "deterministic.json").read_text(encoding="utf-8"))
    return root, evidence, record, deterministic


def execute(settings, factory, judge, assessment_id):
    with factory() as session:
        item = session.get(Assessment, assessment_id)
        if not item or item.status != "queued":
            return
        item.status = "running"
        execution = item.execution
        profile = EvalProfile.model_validate_json(item.profile_json)
        definition = json.loads(execution.suite_snapshot_json)
        result_ids = [result.id for result in item.results if result.status == "queued"]
        session.commit()

    def cancelled():
        with factory() as session:
            return session.get(Assessment, assessment_id).cancel_requested

    for result_id in result_ids:
        target = settings.artifacts_dir / "assessments" / assessment_id / result_id
        target.mkdir(parents=True, exist_ok=True)
        log = LogWriter(target / "logs", scope="assessment")
        try:
            with factory() as session:
                result = session.get(TrialAssessment, result_id)
                run = session.get(Run, result.run_id)
                root, evidence, record, deterministic_data = source_artifacts(settings, run)
                case = CaseSpec.model_validate(
                    next(c for c in definition["cases"] if c["id"] == run.case_id)
                )
                anonymous_id, duration = run.anonymous_id, run.duration_ms
                result.status, result.artifact_path = "running", str(target)
                # Cache is an optimization, never the source of truth. It is verified by
                # Judge against the model, rubric and complete evidence fingerprint.
                prior = session.scalars(
                    select(TrialAssessment)
                    .where(TrialAssessment.run_id == run.id, TrialAssessment.id != result_id)
                    .order_by(TrialAssessment.completed_at.desc())
                ).all()
                for old in prior:
                    cache = Path(old.artifact_path or "") / "judge-cache"
                    if old.artifact_path and cache.is_dir():
                        shutil.copytree(cache, target / "judge-cache", dirs_exist_ok=True)
                        break
                session.commit()
            write_json(
                target / "source-execution.json",
                {
                    "run_id": run.id,
                    "execution_id": execution.id,
                    "evidence_hash": content_hash(evidence),
                },
            )
            if cancelled():
                raise EvalError("CANCELLED", "评分已停止")
            deterministic = [ScoreComponent(**component) for component in deterministic_data]
            partial = merge_scores(
                case,
                deterministic,
                JudgeOutcome(error="评分尚未完成"),
                extra=execution_time_component(case, duration),
                dimensions=[
                    DimensionSpec.model_validate(d) for d in definition.get("dimensions", [])
                ],
            )
            with factory() as session:
                session.get(TrialAssessment, result_id).score_json = canonical_json(partial)
                session.commit()
            if any(g.type == "llm_rubric" for g in case.graders):
                if judge is None:
                    runtime(settings, profile.judge_provider).verify_snapshot(
                        profile.judge_snapshot, role="judge"
                    )
                outcome = (judge or build_judge(settings, profile.judge_provider)).evaluate(
                    anonymous_id=anonymous_id,
                    case=case,
                    graders=case.graders,
                    evidence=evidence,
                    profile=profile,
                    artifact_dir=target,
                    on_log=log.write,
                    on_progress=lambda kind, text, log=log: log.event("judge", text, stage=kind),
                    is_cancelled=cancelled,
                )
            else:
                outcome = JudgeOutcome()
            merged = merge_scores(
                case,
                deterministic,
                outcome,
                extra=execution_time_component(case, duration),
                dimensions=[
                    DimensionSpec.model_validate(d) for d in definition.get("dimensions", [])
                ],
            )
            # Compliance is displayed independently and never changes the common score.
            compliance = root / "compliance.json"
            merged["workflow_completion"] = (
                json.loads(compliance.read_text(encoding="utf-8")) if compliance.exists() else {}
            )
            merged["skill_invoked"] = record["outcome"].get("skill_invoked")
            merged["skills_loaded"] = record["outcome"].get("skills_loaded", [])
            write_json(target / "scores.json", merged)
            with factory() as session:
                result = session.get(TrialAssessment, result_id)
                result.score_json = canonical_json(merged)
                result.status = (
                    "cancelled"
                    if cancelled()
                    else "judge_error"
                    if outcome.error
                    else "grader_invalid"
                    if merged["invalid"]
                    else "completed"
                )
                result.error_message = (
                    outcome.error or "; ".join(merged.get("evaluation_errors", [])) or None
                )
                result.completed_at = utc_now()
                session.commit()
        except Exception as exc:
            log.event("system", str(exc), stage="failed")
            with factory() as session:
                result = session.get(TrialAssessment, result_id)
                result.status = "cancelled" if cancelled() else "judge_error"
                result.error_message = str(exc)[:4000]
                result.completed_at = utc_now()
                session.commit()
    with factory() as session:
        item = session.get(Assessment, assessment_id)
        item.status = (
            "cancelled"
            if item.cancel_requested
            else "completed"
            if all(r.status == "completed" for r in item.results)
            else "completed_with_failures"
        )
        item.completed_at = utc_now()
        session.commit()
