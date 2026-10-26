"""Independent capability registries. Only app composition registers implementations."""

from aaw_skill_eval.errors import EvalError

RUNNERS = {}
JUDGES = {}
DESIGNERS = {}
RUNTIME_FACTORIES = {}


def register_provider(provider, *, runner=None, judge=None, designer=None, runtime=None):
    for registry, implementation in (
        (RUNNERS, runner),
        (JUDGES, judge),
        (DESIGNERS, designer),
        (RUNTIME_FACTORIES, runtime),
    ):
        if implementation is not None:
            registry[provider] = implementation


def runtime(settings, provider):
    try:
        return RUNTIME_FACTORIES[provider](settings)
    except KeyError:
        raise EvalError(
            "UNSUPPORTED_AGENT", f"Agent 尚未接入：{provider}", status_code=422
        ) from None


def build_runner(settings, provider):
    if provider not in RUNNERS:
        raise EvalError("UNSUPPORTED_RUNNER", f"Runner 尚未接入：{provider}", status_code=422)
    return RUNNERS[provider](settings)


def build_judge(settings, provider):
    if provider not in JUDGES:
        raise EvalError("UNSUPPORTED_JUDGE", f"Judge 尚未接入：{provider}", status_code=422)
    return JUDGES[provider](settings)


def enrich_profile(settings, profile, *, needs_judge=True):
    values = {"schema_version": 2}
    for role in ("runner", "judge"):
        if role == "judge" and not needs_judge:
            continue
        values[f"{role}_snapshot"] = runtime(
            settings, getattr(profile, f"{role}_provider")
        ).snapshot(getattr(profile, f"{role}_model"), role=role)
    return profile.model_copy(update=values)


def verify_profile(settings, profile, *, needs_judge=True):
    for role in ("runner", "judge"):
        if role == "judge" and not needs_judge:
            continue
        runtime(settings, getattr(profile, f"{role}_provider")).verify_snapshot(
            getattr(profile, f"{role}_snapshot"), role=role
        )


def prepare_execution_runtime(settings, profile, execution_id):
    implementation = runtime(settings, profile.runner_provider)
    hook = getattr(implementation, "prepare_execution", None)
    return hook(execution_id) if hook else None


def prepare_trial_runtime(settings, profile, template, root):
    hook = getattr(runtime(settings, profile.runner_provider), "prepare_trial", None)
    return hook(template, root) if hook else None
