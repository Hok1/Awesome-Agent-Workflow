from __future__ import annotations

import json

from aaw_skill_eval.modules.results.projection import project_execution
from aaw_skill_eval.modules.results.views import _experiment_summary


def comparable_profile(execution):
    profile = json.loads(execution.profile_json)
    result = {
        k: v for k, v in profile.items() if k not in {"name", "runner_snapshot", "judge_snapshot"}
    }
    for role in ("runner", "judge"):
        snapshot = profile.get(f"{role}_snapshot") or {}
        result[role] = {
            k: snapshot.get(k)
            for k in (
                "provider",
                "runtime_version",
                "model_id",
                "config_hash",
                "agent_profile_hash",
                "isolation",
                "network_policy",
            )
        }
    return result


def baseline_ready(summary, group="current"):
    state = summary["conclusion"]["groups"][group]
    return (
        not state["missing"]
        and not state["provisional"]
        and not state["gates_failed"]
        and summary["scores"][group] is not None
        and all(not dim["incomplete"] for dim in summary["dimension_scores"].get(group, []))
    )


def comparison(
    current, baseline, baseline_group="current", *, assessment_id=None, baseline_assessment_id=None
):
    if not current or not baseline:
        return {"formal": False, "reasons": ["尚未选择对比基线"], "delta": None}
    reasons = []
    for key, label in (
        ("suite_hash", "用例定义"),
        ("project_commit", "项目提交"),
        ("mode", "Trial 模式"),
    ):
        if getattr(current, key) != getattr(baseline, key):
            reasons.append(label + "有变化")
    a, b = (
        _experiment_summary(current, assessment_id),
        _experiment_summary(baseline, baseline_assessment_id),
    )
    if comparable_profile(project_execution(current, assessment_id)) != comparable_profile(
        project_execution(baseline, baseline_assessment_id)
    ):
        reasons.append("模型或运行配置有变化")
    if not baseline_ready(a) or not baseline_ready(b, baseline_group):
        reasons.append("存在未完成 Trial 或未通过门禁")
    delta = (
        a["scores"]["current"] - b["scores"][baseline_group]
        if a["scores"]["current"] is not None and b["scores"][baseline_group] is not None
        else None
    )
    return {"formal": not reasons, "reasons": reasons, "delta": delta}
