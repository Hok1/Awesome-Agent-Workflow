"""The only location that knows the installed Agent implementations."""

from aaw_skill_eval.contracts.providers import register_provider


def register_defaults():
    from aaw_skill_eval.adapters.agents.chrys import ChrysJudge, ChrysRunner
    from aaw_skill_eval.adapters.agents.chrys.designer import ChrysDesignFlow
    from aaw_skill_eval.adapters.agents.chrys.runtime import ChrysRuntime

    register_provider(
        "chrys",
        runner=ChrysRunner,
        judge=ChrysJudge,
        designer=ChrysDesignFlow,
        runtime=ChrysRuntime,
    )

    from aaw_skill_eval.adapters.workflows.aaw import evidence
    from aaw_skill_eval.contracts.workflows import WORKFLOWS

    WORKFLOWS.update({"aaw-workflow": evidence, "aaw-workflow-eval": evidence})
