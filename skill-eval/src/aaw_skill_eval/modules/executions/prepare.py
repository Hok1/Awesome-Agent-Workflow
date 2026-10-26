from __future__ import annotations

import json
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import (
    Experiment,
    Run,
    RunProgressEvent,
    SkillRevision,
    Suite,
)
from aaw_skill_eval.contracts.providers import (
    enrich_profile,
    prepare_execution_runtime,
    verify_profile,
)
from aaw_skill_eval.contracts.schemas import (
    CaseSpec,
    EvalProfile,
    ExperimentCreateRequest,
    SetupSpec,
)
from aaw_skill_eval.contracts.workflows import adapter as workflow_adapter
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.observability.logs import LogWriter
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json, content_hash, write_json
from aaw_skill_eval.infrastructure.workspace.repository import (
    clone_at_commit,
    file_tree_manifest,
    inspect_project_commit,
    run_trusted_command,
)
from aaw_skill_eval.modules.executions.progress import now
from aaw_skill_eval.modules.executions.skills import import_skill


def create(
    settings: Settings,
    session_factory: sessionmaker[Session],
    request: ExperimentCreateRequest,
) -> Experiment:
    with session_factory() as session:
        suite = session.get(Suite, request.suite_id)
        if suite is None:
            raise EvalError(
                "SUITE_NOT_FOUND",
                "Evaluation suite was not found",
                status_code=404,
            )
        if suite.archived:
            raise EvalError("SUITE_ARCHIVED", "测试套已归档，请先恢复", status_code=409)
        definition = json.loads(suite.definition_json)
        project = inspect_project_commit(
            suite.project_path, definition["project"]["commit_at_creation"]
        )
        current = None
        if request.candidate_kind == "skill":
            if bool(request.skill_revision_id) == bool(request.skill_path):
                raise EvalError("SKILL_REQUIRED", "请选择 Skill 路径或已保存版本", status_code=422)
            current = (
                session.get(SkillRevision, request.skill_revision_id)
                if request.skill_revision_id
                else import_skill(session, settings, request.skill_path)
            )
            if not current:
                raise EvalError("SKILL_NOT_FOUND", "Skill 版本不存在", status_code=404)
        elif request.skill_path or request.skill_revision_id:
            raise EvalError("INVALID_CANDIDATE", "no_skill 不能携带 Skill", status_code=422)
        definition = json.loads(suite.definition_json)
        needs_judge = any(
            g["type"] == "llm_rubric" for c in definition["cases"] for g in c["graders"]
        )
        profile = enrich_profile(settings, request.profile, needs_judge=needs_judge)
        if (
            current
            and workflow_adapter(current.skill.name)
            and any(c.get("workflow") for c in definition["cases"])
            and profile.runner_snapshot
        ):
            snapshot = profile.runner_snapshot.model_copy(
                update={
                    "metadata": {
                        **profile.runner_snapshot.metadata,
                        "workflow_execution_policy": "aaw-terminal-v1",
                        "required_reviewer_tools": ["reviewer_a", "reviewer_b"],
                    }
                }
            )
            profile = profile.model_copy(update={"runner_snapshot": snapshot})
        profile_data = profile.model_dump(mode="json")
        profile_identity = {key: value for key, value in profile_data.items() if key != "name"}
        profile_json = canonical_json(profile_data)
        experiment = Experiment(
            suite_id=suite.id,
            evaluation_mode=request.evaluation_mode,
            current_revision_id=current.id if current else None,
            candidate_kind=request.candidate_kind,
            project_commit=project.commit,
            suite_hash=suite.definition_hash,
            profile_hash=content_hash(profile_identity),
            profile_json=profile_json,
            suite_snapshot_json=suite.definition_json,
            mode=request.mode,
            trials=1 if request.mode == "quick" else 3,
            seed=secrets.randbits(31),
            status="queued",
        )
        session.add(experiment)
        session.commit()
        session.refresh(experiment)
        return experiment


def create_retry(
    session_factory: sessionmaker[Session],
    experiment_id: str,
    *,
    settings: Settings | None = None,
    refresh_runtime: bool = False,
) -> Experiment:
    with session_factory() as session:
        original = session.get(Experiment, experiment_id)
        if original is None:
            raise EvalError(
                "EXPERIMENT_NOT_FOUND",
                "Experiment was not found",
                status_code=404,
            )
        suite = session.get(Suite, original.suite_id)
        assert suite is not None
        project_path = suite.project_path
        snapshot = {
            "suite_id": original.suite_id,
            "evaluation_mode": original.evaluation_mode,
            "current_revision_id": original.current_revision_id,
            "candidate_kind": original.candidate_kind,
            "project_commit": original.project_commit,
            "suite_hash": original.suite_hash,
            "profile_hash": original.profile_hash,
            "profile_json": original.profile_json,
            "suite_snapshot_json": original.suite_snapshot_json,
            "mode": original.mode,
            "trials": original.trials,
            "seed": original.seed,
        }

    inspect_project_commit(project_path, snapshot["project_commit"])

    if refresh_runtime:
        assert settings is not None
        definition = json.loads(snapshot["suite_snapshot_json"])
        needs_judge = any(
            g["type"] == "llm_rubric" for c in definition["cases"] for g in c["graders"]
        )
        profile = enrich_profile(
            settings,
            EvalProfile.model_validate_json(snapshot["profile_json"]),
            needs_judge=needs_judge,
        )
        profile_data = profile.model_dump(mode="json")
        snapshot["profile_json"] = canonical_json(profile_data)
        snapshot["profile_hash"] = content_hash(
            {k: v for k, v in profile_data.items() if k != "name"}
        )

    with session_factory() as session:
        original = session.get(Experiment, experiment_id)
        assert original is not None
        if original.status in {"queued", "interrupted"}:
            original.status = "cancelled"
            original.cancel_requested_at = original.cancel_requested_at or now()
            original.error_kind = "cancelled"
            original.error_message = "Experiment cancelled because a retry was requested"
            original.completed_at = original.completed_at or now()
        elif original.status in {"preparing", "running"}:
            original.cancel_requested_at = original.cancel_requested_at or now()
            original.error_kind = "cancelled"
            original.error_message = (
                "Experiment cancellation requested because a retry was requested"
            )

        retry = Experiment(
            **snapshot,
            retry_of_experiment_id=original.id,
            status="queued",
        )
        session.add(retry)
        session.commit()
        session.refresh(retry)
        return retry


def prepare_experiment(
    settings: Settings,
    session_factory: sessionmaker[Session],
    experiment_id: str,
    *,
    root: Path,
    base: Path,
    experiment: Experiment,
    suite: Suite,
    definition: dict,
    profile: EvalProfile,
    has_baseline: bool,
    experiment_log: LogWriter,
) -> Path | None:
    """Run the preparation phase of an experiment and return the chrys template.

    Verifies the Runner/Judge configuration, re-validates the project state,
    clones the fixed-commit evaluation copy, executes the setup commands,
    prepares the experiment-level chrys template (when needed) and creates the
    queued runs. Raises on the first failure so the caller can mark the
    experiment as failed.
    """
    chrys_template: Path | None = None
    experiment_log.event("system", "正在校验 Runner/Judge 配置", stage="preparing")
    needs_judge = any(g["type"] == "llm_rubric" for c in definition["cases"] for g in c["graders"])
    verify_profile(settings, profile, needs_judge=False)
    experiment_log.event("system", "Runner/Judge 配置校验完成", stage="preparing")
    snapshot = inspect_project_commit(suite.project_path, experiment.project_commit)
    if root.exists():
        shutil.rmtree(root)
    experiment_log.event("system", "正在创建固定提交的评测副本", stage="cloning")
    clone_at_commit(snapshot, base)
    experiment_log.event("system", "评测副本已创建", stage="cloning")
    setup = SetupSpec.model_validate(definition.get("setup") or {})
    setup_log = prepare_base(base, setup, log_writer=experiment_log)
    write_json(settings.artifacts_dir / experiment_id / "setup.json", setup_log)
    if profile.runner_provider == "chrys" or (needs_judge and profile.judge_provider == "chrys"):
        chrys_template = prepare_execution_runtime(settings, profile, experiment_id)
        experiment_log.event(
            "system",
            "已生成实验级 Chrys 配置模板，每个 Run 将使用独立配置目录",
            stage="queuing_runs",
        )
    experiment_log.event("system", "正在创建独立评测运行", stage="queuing_runs")
    create_runs(session_factory, experiment_id, definition, has_baseline)
    return chrys_template


def prepare_base(
    base: Path,
    setup: SetupSpec,
    *,
    log_writer: LogWriter | None = None,
) -> dict:
    setup_log: dict[str, Any] = {"commands": [], "preflight": [], "network": setup.network}
    for index, command in enumerate(setup.commands, start=1):
        if log_writer is not None:
            log_writer.event("setup", f"开始 Setup 命令 #{index}: {command}", stage="setup")
        result = run_trusted_command(
            command,
            base,
            setup.timeout_seconds,
            on_log=log_writer.write if log_writer is not None else None,
            source="setup",
            stdout_path=(log_writer.root / f"setup-{index}.stdout.txt")
            if log_writer is not None
            else None,
            stderr_path=(log_writer.root / f"setup-{index}.stderr.txt")
            if log_writer is not None
            else None,
        )
        setup_log["commands"].append(result)
        if log_writer is not None:
            log_writer.event(
                "setup",
                f"Setup 命令 #{index} 结束（exit_code={result.get('exit_code')}）",
                stage="setup",
            )
        if result.get("exit_code") != 0:
            raise EvalError("SETUP_FAILED", f"Setup command failed: {command}")
    for index, command in enumerate(setup.preflight, start=1):
        if log_writer is not None:
            log_writer.event(
                "preflight", f"开始 Preflight 命令 #{index}: {command}", stage="preflight"
            )
        result = run_trusted_command(
            command,
            base,
            setup.timeout_seconds,
            on_log=log_writer.write if log_writer is not None else None,
            source="preflight",
            stdout_path=(log_writer.root / f"preflight-{index}.stdout.txt")
            if log_writer is not None
            else None,
            stderr_path=(log_writer.root / f"preflight-{index}.stderr.txt")
            if log_writer is not None
            else None,
        )
        setup_log["preflight"].append(result)
        if log_writer is not None:
            log_writer.event(
                "preflight",
                f"Preflight 命令 #{index} 结束（exit_code={result.get('exit_code')}）",
                stage="preflight",
            )
        if result.get("exit_code") != 0:
            raise EvalError("PREFLIGHT_FAILED", f"Preflight command failed: {command}")
    setup_log["manifest"] = file_tree_manifest(base)
    return setup_log


def create_runs(
    session_factory: sessionmaker[Session],
    experiment_id: str,
    definition: dict,
    has_baseline: bool,
) -> None:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        assert experiment is not None
        existing = session.scalar(select(Run).where(Run.experiment_id == experiment_id))
        if existing is not None:
            return
        groups = ["current"]
        for case_data in definition["cases"]:
            case = CaseSpec.model_validate(case_data)
            for trial_index in range(1, experiment.trials + 1):
                block = list(groups)
                for group in block:
                    anonymous = f"candidate-{uuid.uuid4().hex[:8].upper()}"
                    run = Run(
                        experiment_id=experiment_id,
                        case_id=case.id,
                        group_name=group,
                        trial_index=trial_index,
                        anonymous_id=anonymous,
                        status="queued",
                    )
                    session.add(run)
                    session.flush()
                    session.add(
                        RunProgressEvent(
                            run_id=run.id,
                            attempt=1,
                            kind="stage",
                            stage="queued",
                            message="等待执行此用例",
                        )
                    )
        session.commit()
