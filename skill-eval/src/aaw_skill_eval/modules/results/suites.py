from __future__ import annotations

from sqlalchemy import select

from aaw_skill_eval.contracts.entities import Experiment
from aaw_skill_eval.modules.results.comparison import comparison
from aaw_skill_eval.modules.results.views import _experiment_summary, _suite_payload


def suite_view(session, item):
    experiments = session.scalars(
        select(Experiment)
        .where(Experiment.suite_id == item.id)
        .order_by(Experiment.created_at.desc())
    ).all()
    latest = experiments[0] if experiments else None
    baseline = (
        session.get(Experiment, item.baseline_experiment_id)
        if item.baseline_experiment_id
        else None
    )
    return {
        **_suite_payload(item),
        "archived": item.archived,
        "locked": True,
        "baseline_experiment_id": item.baseline_experiment_id,
        "baseline_assessment_id": item.baseline_assessment_id,
        "baseline_group": item.baseline_group,
        "baseline": (
            {
                **_experiment_summary(baseline, item.baseline_assessment_id),
                "selected_group": item.baseline_group,
            }
            if baseline
            else None
        ),
        "latest": _experiment_summary(latest) if latest else None,
        "comparison": comparison(
            latest,
            baseline,
            item.baseline_group,
            baseline_assessment_id=item.baseline_assessment_id,
        ),
        "execution_count": len(experiments),
    }
