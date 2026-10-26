"""Optional candidate-specific compliance. Never a common scoring criterion."""

WORKFLOWS = {}


def adapter(skill_name):
    return WORKFLOWS.get(skill_name)


def runner_case(case, *, skill_name=None):
    workflow = adapter(skill_name)
    if workflow and case.workflow:
        return workflow.runner_case(case, with_skill=True)
    return case.model_copy(update={"workflow": None})


def inspect_workflow(workspace, spec, *, skill_name=None):
    workflow = adapter(skill_name)
    return workflow.inspect_workflow(workspace, spec) if workflow and spec else None
