from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from statistics import fmean

from aaw_skill_eval.contracts.entities import Experiment, Run, Suite
from aaw_skill_eval.contracts.schemas import EvalProfile
from aaw_skill_eval.infrastructure.observability.logs import display_record
from aaw_skill_eval.modules.results.dimensions import dimension_summary, dimension_total
from aaw_skill_eval.modules.results.projection import project_execution
from aaw_skill_eval.modules.suites.service import suite_definition


def _iso(value):
    """Serialize datetimes as explicit-UTC ISO strings.

    Bare "2026-09-28T08:54:58.750230" strings get parsed as *local* time by
    JavaScript, which made running-run durations read +8h on UTC+8 machines.
    """
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _age_seconds(value) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - value).total_seconds()))


def _masked_diagnostic(value):
    if isinstance(value, str):
        return display_record({"text": value}, mode="raw", unmasked=False)["text"]
    if isinstance(value, dict):
        return {key: _masked_diagnostic(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_masked_diagnostic(item) for item in value]
    return value


def _active_run_view(run: Run) -> dict:
    activity_age = _age_seconds(run.last_activity_at)
    return {
        "id": run.id,
        "group": run.group_name,
        "case_id": run.case_id,
        "trial": run.trial_index,
        "stage": run.current_stage,
        "started_at": _iso(run.started_at),
        "activity_age_seconds": activity_age,
        "heartbeat_age_seconds": _age_seconds(run.last_heartbeat_at),
        "stalled": bool(
            run.status == "running" and activity_age is not None and activity_age >= 120
        ),
        "cancel_requested": run.cancel_requested_at is not None,
    }


def _progress_payload(experiment: Experiment) -> dict:
    counts = Counter(run.status for run in experiment.runs)
    total = len(experiment.runs)
    completed = counts["completed"]
    # Pair-parallel execution has up to two runs active at once (the
    # no_skill/current pair of one block). active_runs[] lists every running
    # run; the legacy single-run fields keep describing the first one so old
    # clients keep working.
    active_runs = [run for run in experiment.runs if run.status == "running"]
    active_views = [_active_run_view(run) for run in active_runs]
    primary = active_views[0] if active_views else None
    tracked = any(run.current_stage or run.progress_events for run in experiment.runs)
    return {
        "total": total,
        "completed": completed,
        "running": counts["running"],
        "queued": counts["queued"],
        "failed": total - completed - counts["running"] - counts["queued"],
        "tracking_available": tracked,
        "active_run_id": primary["id"] if primary else None,
        "active_runs": active_views,
        "active_stage": primary["stage"] if primary else None,
        "active_activity_age_seconds": primary["activity_age_seconds"] if primary else None,
        "active_heartbeat_age_seconds": primary["heartbeat_age_seconds"] if primary else None,
        "stalled": any(view["stalled"] for view in active_views),
    }


def _group_score(experiment: Experiment, definition: dict, group_name: str) -> float | None:
    if definition.get("dimensions"):
        return dimension_total(dimension_summary(experiment, definition, group_name))
    weights = {case["id"]: float(case.get("weight", 1)) for case in definition["cases"]}
    case_scores: list[tuple[float, float]] = []
    for case_id, weight in weights.items():
        scores = [
            run.quality_score
            for run in experiment.runs
            if run.case_id == case_id
            and run.group_name == group_name
            and run.quality_score is not None
            and run.status == "completed"
        ]
        if scores:
            case_scores.append((fmean(scores), weight))
    total_weight = sum(weight for _, weight in case_scores)
    if not total_weight:
        return None
    return sum(score * weight for score, weight in case_scores) / total_weight


def _conclusion_payload(experiment: Experiment, definition: dict, group_scores: dict) -> dict:
    """Conclusion rules: hard gates outrank quality scores.

    - A group whose gates failed keeps every score for analysis, but the
      overall verdict is "gates_failed" (candidate did not qualify).
    - A group missing trials shows a provisional score; deltas that involve a
      provisional group are not formal comparisons.
    """
    expected = experiment.trials * len(definition["cases"])
    groups = {}
    for group in ("no_skill", "baseline", "current"):
        runs = [run for run in experiment.runs if run.group_name == group]
        completed = [run for run in runs if run.status == "completed"]
        gates_total = sum(run.hard_gates_total for run in completed)
        gates_passed = sum(run.hard_gates_passed for run in completed)
        groups[group] = {
            "missing": not runs,
            "score": group_scores[group],
            "completed_trials": len(completed),
            "expected_trials": expected,
            "provisional": len(completed) < expected,
            "gates_passed": gates_passed,
            "gates_total": gates_total,
            "gates_failed": gates_total > 0 and gates_passed < gates_total,
        }
    current = groups["current"]
    formal_deltas = {
        side: not (current["provisional"] or groups[side]["provisional"])
        for side in ("no_skill", "baseline")
    }
    if not current["completed_trials"]:
        verdict = "no_score"
    elif current["gates_failed"]:
        verdict = "gates_failed"
    elif current["provisional"]:
        verdict = "provisional"
    else:
        verdict = "solid"
    return {
        "verdict": verdict,
        "expected_trials_per_group": expected,
        "groups": groups,
        "formal_deltas": formal_deltas,
    }


def _profile_payload(experiment: Experiment) -> dict:
    raw = json.loads(experiment.profile_json)
    profile = EvalProfile.model_validate(raw)

    def role_payload(role: str) -> dict:
        provider = getattr(profile, f"{role}_provider")
        model = getattr(profile, f"{role}_model")
        snapshot = getattr(profile, f"{role}_snapshot")
        return {
            "provider": provider,
            "model": model,
            "model_name": snapshot.model_profile_name if snapshot else model,
            "model_id": snapshot.model_id if snapshot else model,
            "runtime_version": snapshot.runtime_version if snapshot else None,
            "agent_profile": snapshot.agent_profile if snapshot else None,
            "isolation": snapshot.isolation if snapshot else "unknown",
            "network_policy": snapshot.network_policy
            if snapshot
            else ("enabled" if profile.network and role == "runner" else "disabled"),
        }

    runner = role_payload("runner")
    judge = role_payload("judge")
    return {
        "name": profile.name,
        "hash": experiment.profile_hash,
        "schema_version": profile.schema_version,
        "legacy": "schema_version" not in raw,
        "runner": runner,
        "judge": judge,
        "self_judge": (
            runner["provider"] == judge["provider"] and runner["model"] == judge["model"]
        ),
    }


def _experiment_summary(experiment: Experiment, assessment_id=None) -> dict:
    experiment = project_execution(experiment, assessment_id)
    definition = json.loads(experiment.suite_snapshot_json)
    dimension_scores = (
        {
            group: dimension_summary(experiment, definition, group)
            for group in ("no_skill", "baseline", "current")
        }
        if definition.get("dimensions")
        else {}
    )
    scores = {
        group: dimension_total(dimension_scores[group])
        if dimension_scores
        else _group_score(experiment, definition, group)
        for group in ("no_skill", "baseline", "current")
    }
    current = scores["current"]
    baseline = scores["baseline"]
    no_skill = scores["no_skill"]
    return {
        "id": experiment.id,
        "candidate_kind": experiment.candidate_kind,
        "candidate_label": experiment.current_revision.skill.name
        if experiment.current_revision
        else "no_skill",
        "execution_status": experiment.execution_status,
        "assessment_id": experiment.assessment_id,
        "assessment_status": experiment.assessment_status,
        "assessments": [
            {
                "id": a.id,
                "status": a.status,
                "created_at": _iso(a.created_at),
                "judge_model": json.loads(a.profile_json)["judge_model"],
            }
            for a in experiment.assessments
        ],
        "evaluation_mode": experiment.evaluation_mode,
        "execution_kind": experiment.execution_kind,
        "suite_id": experiment.suite_id,
        "suite_name": experiment.suite.name,
        "standard_status": "standard" if definition.get("catalog_version") else "legacy",
        "catalog_version": definition.get("catalog_version"),
        "skill_type": definition.get("skill_type"),
        "skill_id": experiment.suite.skill_id,
        "project_path": experiment.suite.project_path,
        "project_commit": experiment.project_commit,
        "status": experiment.status,
        "retry_of_experiment_id": experiment.retry_of_experiment_id,
        "retry_experiment_ids": [retry.id for retry in experiment.retries],
        "mode": experiment.mode,
        "trials": experiment.trials,
        # Pair-parallel execution metadata (方案第五部分); NULL/absent on
        # legacy experiments and reported as-is, never backfilled.
        "execution_mode": experiment.execution_mode,
        "concurrency_limit": experiment.concurrency_limit,
        "created_at": _iso(experiment.created_at),
        "completed_at": _iso(experiment.completed_at),
        "scores": scores,
        "dimension_scores": dimension_scores,
        "conclusion": _conclusion_payload(experiment, definition, scores),
        "delta_no_skill": (
            current - no_skill if current is not None and no_skill is not None else None
        ),
        "delta_baseline": (
            current - baseline if current is not None and baseline is not None else None
        ),
        "current_revision": experiment.current_revision.content_hash
        if experiment.current_revision
        else "no_skill",
        "current_revision_id": experiment.current_revision_id,
        "baseline_revision": (
            experiment.baseline_revision.content_hash if experiment.baseline_revision else None
        ),
        "baseline_revision_id": experiment.baseline_revision_id,
        "error_kind": experiment.error_kind,
        "error_message": experiment.error_message,
        "profile": _profile_payload(experiment),
        "progress": _progress_payload(experiment),
    }


def _suite_payload(suite: Suite) -> dict:
    definition = suite_definition(suite)
    return {
        "standard_status": "standard" if definition.get("catalog_version") else "legacy",
        "catalog_version": definition.get("catalog_version"),
        "skill_type": definition.get("skill_type"),
        "has_workflow": any(c.get("workflow") for c in definition["cases"]),
        "needs_judge": any(
            g["type"] == "llm_rubric" for c in definition["cases"] for g in c["graders"]
        ),
        "id": suite.id,
        "name": suite.name,
        "skill_id": suite.skill_id,
        "skill_name": "执行时选择",
        "reference_skill_path": definition.get("reference_skill_path", ""),
        "project_path": suite.project_path,
        "definition_hash": suite.definition_hash,
        "definition_path": suite.definition_path,
        "created_at": _iso(suite.created_at),
        "updated_at": _iso(suite.updated_at),
    }


def _execution_status(run):
    return getattr(run, "execution_status", run.status)
