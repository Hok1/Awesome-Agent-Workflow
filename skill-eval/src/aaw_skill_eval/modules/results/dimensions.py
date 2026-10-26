from __future__ import annotations

import json
from collections import defaultdict
from statistics import fmean


def dimension_summary(experiment, definition: dict, group: str) -> list[dict]:
    """Average trials, then case weights inside a dimension; never flatten cases."""
    result = []
    runs_by_case = defaultdict(list)
    judge_incomplete = False
    for run in experiment.runs:
        usable_partial = (
            run.status in {"judge_error", "grader_invalid"}
            and getattr(run, "execution_status", None) == "completed"
        )
        if run.group_name == group and (run.status == "completed" or usable_partial):
            snapshot = json.loads(run.score_json) if run.score_json else {}
            judge_incomplete = judge_incomplete or usable_partial
            runs_by_case[run.case_id].append(
                {item["id"]: item for item in snapshot.get("dimensions", [])}
            )
    for dimension in definition.get("dimensions", []):
        relevant = [
            case
            for case in definition["cases"]
            if any(g.get("dimension_id") == dimension["id"] for g in case["graders"])
        ]
        values = []
        completed = 0
        passed = True
        for case in relevant:
            scores = []
            for snapshot in runs_by_case[case["id"]]:
                item = snapshot.get(dimension["id"])
                if not item or item["invalid"]:
                    continue
                completed += 1
                passed = passed and item["passed"]
                if item["score"] is not None:
                    scores.append(item["score"])
            if scores:
                values.append(
                    (
                        fmean(scores),
                        case.get("dimension_weights", {}).get(
                            dimension["id"], case.get("weight", 1)
                        ),
                    )
                )
        weight = sum(weight for _, weight in values)
        score = sum(score * weight for score, weight in values) / weight if weight else None
        expected = len(relevant) * experiment.trials
        result.append(
            {
                **dimension,
                "score": score,
                "completed": completed,
                "expected": expected,
                "incomplete": completed < expected,
                "passed": passed and completed == expected,
                "judge_incomplete": judge_incomplete,
            }
        )
    return result


def dimension_total(items: list[dict]) -> float | None:
    if any(item.get("judge_incomplete") for item in items):
        return None
    quality = [item for item in items if not item["hard_gate"] and item["score"] is not None]
    weight = sum(item["weight"] for item in quality)
    return sum(item["score"] * item["weight"] for item in quality) / weight if weight else None
