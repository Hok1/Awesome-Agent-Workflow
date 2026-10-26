"""Authoritative display rules for completed and partial assessments."""

import json
from collections import Counter
from statistics import fmean


def verdict(runs, expected, dimension_id=None):
    if not runs:
        return "未执行"
    snapshots = [(run, json.loads(run.score_json or "{}")) for run in runs]

    def valid_partial(run, score):
        return (
            dimension_id
            and run.execution_status == "completed"
            and any(
                d["id"] == dimension_id and not d.get("invalid") and d.get("score") is not None
                for d in score.get("dimensions", [])
            )
        )

    if any(
        r.status not in {"completed", "running", "queued"} and not valid_partial(r, s)
        for r, s in snapshots
    ):
        return "Error"
    if len(runs) < expected or any(
        r.status != "completed" and not valid_partial(r, s) for r, s in snapshots
    ):
        return "未完成"
    if not dimension_id and any(r.hard_gates_passed < r.hard_gates_total for r in runs):
        return "Failed"
    dimensions = [
        d
        for _, s in snapshots
        for d in s.get("dimensions", [])
        if not dimension_id or d["id"] == dimension_id
    ]
    if any(d.get("invalid") for d in dimensions):
        return "Error"
    if dimension_id and len(dimensions) != len(runs):
        return "未完成"
    return (
        "Failed"
        if any(
            not d.get("passed") or d.get("score") is None or d["score"] < d["pass_score"]
            for d in dimensions
        )
        else "Pass"
    )


def presentation(execution, definition):
    cases, dimension_states, component_scores = [], {}, {}
    for case in definition["cases"]:
        runs = [r for r in execution.runs if r.case_id == case["id"]]
        states = {
            d["id"]: verdict(runs, execution.trials, d["id"])
            for d in definition.get("dimensions", [])
        }
        cases.append(
            {
                "id": case["id"],
                "name": case["name"],
                "verdict": verdict(runs, execution.trials),
                "dimensions": states,
            }
        )
        component_scores[case["id"]] = {}
        for grader in case["graders"]:
            values = [
                c["score"]
                for r in runs
                if r.execution_status == "completed"
                for c in json.loads(r.score_json or "{}").get("components", [])
                if c["grader_id"] == grader["id"] and not c.get("invalid")
            ]
            component_scores[case["id"]][grader["id"]] = fmean(values) if values else None
    for dim in definition.get("dimensions", []):
        ids = {
            c["id"]
            for c in definition["cases"]
            if any(g.get("dimension_id") == dim["id"] for g in c["graders"])
        }
        dimension_states[dim["id"]] = verdict(
            [r for r in execution.runs if r.case_id in ids], len(ids) * execution.trials, dim["id"]
        )
    expected = (
        sum(
            sum(g.get("hard_gate", False) for g in c["graders"])
            + sum(
                d.get("hard_gate", False)
                for d in definition.get("dimensions", [])
                if any(g.get("dimension_id") == d["id"] for g in c["graders"])
            )
            for c in definition["cases"]
        )
        * execution.trials
    )
    total = sum(r.hard_gates_total for r in execution.runs)
    gates = (
        "未通过"
        if any(r.hard_gates_passed < r.hard_gates_total for r in execution.runs)
        else "不适用"
        if not expected and not total
        else "待检查"
        if execution.status in {"queued", "running", "preparing"}
        else "缺少检查结果"
        if total < expected
        else "通过"
    )
    return {
        "cases": cases,
        "counts": dict(Counter(c["verdict"] for c in cases)),
        "dimensions": dimension_states,
        "component_scores": component_scores,
        "gate_status": gates,
    }
