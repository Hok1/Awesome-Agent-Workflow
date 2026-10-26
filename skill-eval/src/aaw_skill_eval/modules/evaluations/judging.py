from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from aaw_skill_eval.contracts.agents import Judge, JudgeOutcome, judge_scores
from aaw_skill_eval.infrastructure.storage.artifacts import content_hash, write_json
from aaw_skill_eval.modules.evaluations.evidence import dimension_evidence


class DimensionJudge(Judge):
    """Shared scoring policy: bounded dimensions, evidence selection, cache and progress."""

    def prepare_batch(self, target):
        return None

    def _evaluate_batch(self, **kwargs):
        raise NotImplementedError

    def evaluate(
        self,
        *,
        anonymous_id,
        case,
        graders,
        evidence,
        profile,
        artifact_dir,
        on_progress=None,
        on_log=None,
        is_cancelled=None,
        chrys_home_root=None,
    ):
        groups = {}
        for grader in graders:
            if grader.type == "llm_rubric":
                groups.setdefault(grader.dimension_id or "legacy", []).append(grader)
        if not groups:
            return JudgeOutcome()
        started = time.monotonic()
        deadline = started + profile.judge_total_timeout_seconds
        states = {key: {"status": "pending"} for key in groups}
        lock = threading.Lock()

        def update(key, **fields):
            with lock:
                states[key].update(fields)
                write_json(
                    artifact_dir / "judge-progress.json",
                    {
                        "model": profile.judge_model,
                        "per_dimension_timeout": profile.judge_timeout_seconds,
                        "total_timeout": profile.judge_total_timeout_seconds,
                        "dimensions": states,
                    },
                )
            if on_progress:
                on_progress(
                    "activity",
                    f"Judge · {key} · {fields.get('status', '')} {fields.get('error', '')}",
                )

        def cancelled():
            return bool(is_cancelled and is_cancelled()) or time.monotonic() >= deadline

        def score_group(entry):
            key, checks = entry
            group_start = time.monotonic()
            view = dimension_evidence(evidence, key)
            fingerprint = content_hash(
                {
                    "version": 1,
                    "model": profile.judge_model,
                    "snapshot": profile.judge_snapshot.model_dump(
                        exclude={"metadata", "model_profile_name"}
                    )
                    if profile.judge_snapshot
                    else None,
                    "task": case.input,
                    "expected": case.expected,
                    "checks": [g.model_dump() for g in checks],
                    "evidence": view,
                    "full_evidence_hash": content_hash(evidence),
                }
            )
            cache = artifact_dir / "judge-cache" / f"{content_hash(key)[:12]}.json"
            try:
                if cache.exists():
                    stored = json.loads(cache.read_text(encoding="utf-8"))
                    if stored.get("fingerprint") == fingerprint:
                        scores = judge_scores(
                            json.dumps({"candidate_id": anonymous_id, "scores": stored["scores"]}),
                            anonymous_id=anonymous_id,
                            graders=checks,
                        )
                        update(key, status="cached", elapsed_seconds=0)
                        return JudgeOutcome(scores=scores)
                if cancelled():
                    raise ValueError("Judge total budget exhausted or task cancelled")
                update(
                    key,
                    status="running",
                    input_characters=len(json.dumps(view, ensure_ascii=False)),
                    selected_files=list(view.get("output_files", {})),
                )
                target = artifact_dir / "judge-dimensions" / content_hash(key)[:10]
                home = self.prepare_batch(target)
                remaining = max(
                    1, min(profile.judge_timeout_seconds, int(deadline - time.monotonic()))
                )
                result = self._evaluate_batch(
                    anonymous_id=anonymous_id,
                    case=case,
                    graders=checks,
                    evidence=view,
                    profile=profile.model_copy(update={"judge_timeout_seconds": remaining}),
                    artifact_dir=target,
                    on_progress=on_progress,
                    on_log=on_log,
                    is_cancelled=cancelled,
                    chrys_home_root=home,
                    full_evidence=evidence,
                )
                if result.error:
                    raise ValueError(result.error)
                for score in result.scores:
                    check = next(g for g in checks if g.id == score.grader_id)
                    if (
                        not score.evidence.strip()
                        or check.allowed_scores
                        and score.score not in check.allowed_scores
                    ):
                        raise ValueError(
                            f"Invalid fixed-level score or missing evidence: {score.grader_id}"
                        )
                write_json(
                    cache,
                    {"fingerprint": fingerprint, "scores": [asdict(s) for s in result.scores]},
                )
                update(
                    key,
                    status="completed",
                    elapsed_seconds=round(time.monotonic() - group_start, 1),
                )
                return result
            except Exception as exc:
                update(
                    key,
                    status="failed",
                    error=str(exc)[:1500],
                    elapsed_seconds=round(time.monotonic() - group_start, 1),
                )
                return JudgeOutcome(error=f"{key}: {exc}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(score_group, groups.items()))
        errors = [r.error for r in results if r.error]
        return JudgeOutcome(
            scores=[s for r in results for s in r.scores],
            events=[e for r in results for e in r.events],
            error="; ".join(errors) if errors else None,
        )
