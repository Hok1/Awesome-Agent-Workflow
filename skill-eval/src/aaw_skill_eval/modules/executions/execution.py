from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import (
    Experiment,
    Run,
    SkillRevision,
    Suite,
)
from aaw_skill_eval.contracts.providers import (
    build_runner,
    prepare_trial_runtime,
)
from aaw_skill_eval.contracts.schemas import CaseSpec, EvalProfile
from aaw_skill_eval.contracts.workflows import inspect_workflow, runner_case
from aaw_skill_eval.errors import EvalError, InfrastructureError
from aaw_skill_eval.infrastructure.observability.logs import LogWriter
from aaw_skill_eval.infrastructure.storage.artifacts import (
    archive_untracked,
    write_json,
)
from aaw_skill_eval.infrastructure.storage.evidence import collect_terminal_outputs
from aaw_skill_eval.infrastructure.storage.frozen import artifact_hash
from aaw_skill_eval.infrastructure.workspace.cleanup import (
    mark_workspace_retained,
    remove_run_workspace_dirs,
)
from aaw_skill_eval.infrastructure.workspace.paths import experiment_workspace, run_workspace
from aaw_skill_eval.infrastructure.workspace.repository import (
    _git,
    capture_changes,
    file_tree_manifest,
)
from aaw_skill_eval.modules.evaluations.graders import evaluate_deterministic
from aaw_skill_eval.modules.executions.prepare import prepare_experiment
from aaw_skill_eval.modules.executions.progress import RunProgress, now
from aaw_skill_eval.modules.executions.scheduling import (
    claim_run,
    db_write,
    experiment_cancelled,
    ordered_runs,
)
from aaw_skill_eval.modules.executions.skills import install_snapshot, prepare_eval_workspace
from aaw_skill_eval.modules.suites.packages import materialize_files


def remove_tree_with_retry(path: Path, *, attempts: int = 3, delay: float = 0.2) -> None:
    """Best-effort directory removal with a short retry for Windows.

    Antivirus software briefly holds handles to freshly written files (the
    chrys template is written moments earlier), which can make a single
    rmtree leave files behind. Retrying a couple of times keeps stale
    template directories from accumulating; the final attempt still ignores
    errors because a leftover template is harmless (it is regenerated per
    experiment id).
    """
    for attempt in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        if attempt < attempts - 1:
            time.sleep(delay)


def execute(
    settings: Settings,
    session_factory: sessionmaker[Session],
    runner,
    judge,
    experiment_id: str,
) -> None:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None or experiment.status not in {"queued", "interrupted"}:
            return
        experiment.status = "preparing"
        experiment.started_at = now()
        session.commit()
        suite = session.get(Suite, experiment.suite_id)
        assert suite is not None
        definition = json.loads(experiment.suite_snapshot_json)
        profile = EvalProfile.model_validate_json(experiment.profile_json)
        current = (
            session.get(SkillRevision, experiment.current_revision_id)
            if experiment.current_revision_id
            else None
        )
        baseline = None
        if current is not None:
            _ = current.skill.name

    root = experiment_workspace(settings, experiment_id)
    base = root / "base"
    experiment_log = LogWriter(
        settings.artifacts_dir / experiment_id / "logs",
        scope="experiment",
    )
    experiment_log.event("system", "实验开始准备")
    chrys_template: Path | None = None
    try:
        chrys_template = prepare_experiment(
            settings,
            session_factory,
            experiment_id,
            root=root,
            base=base,
            experiment=experiment,
            suite=suite,
            definition=definition,
            profile=profile,
            has_baseline=baseline is not None,
            experiment_log=experiment_log,
        )
        with session_factory() as session:
            item = session.get(Experiment, experiment_id)
            assert item is not None
            item.status = "running"
            item.execution_mode = "single_candidate_v1"
            item.concurrency_limit = 1
            session.commit()
        experiment_log.event("system", "按用例和 Trial 执行所选候选", stage="running")
        for run_id in ordered_runs(session_factory, experiment_id, definition):
            if experiment_cancelled(session_factory, experiment_id):
                break
            execute_run(
                settings,
                session_factory,
                runner,
                judge,
                run_id,
                base,
                current,
                None,
                profile,
                definition,
                chrys_template,
            )
        finish_experiment(settings, session_factory, experiment_id)
    except EvalError as exc:
        experiment_log.event("system", f"实验准备失败：{exc.kind} · {exc.message}", stage="failed")
        fail_experiment(settings, session_factory, experiment_id, exc.kind, exc.message)
    except Exception as exc:
        experiment_log.event(
            "system", f"实验基础设施异常：{type(exc).__name__}: {exc}", stage="failed"
        )
        fail_experiment(
            settings, session_factory, experiment_id, "infra_error", f"{type(exc).__name__}: {exc}"
        )
    finally:
        if chrys_template is not None:
            remove_tree_with_retry(chrys_template)
        shutil.rmtree(base, ignore_errors=True)


def run_artifact_dir(settings: Settings, experiment_id: str, run_id: str, attempt: int) -> Path:
    artifact_dir = settings.artifacts_dir / experiment_id / run_id
    if attempt > 1:
        artifact_dir = artifact_dir / f"attempt-{attempt}"
    return artifact_dir


def execute_run(
    settings: Settings,
    session_factory: sessionmaker[Session],
    runner,
    judge,
    run_id: str,
    base: Path,
    current: SkillRevision | None,
    baseline: SkillRevision | None,
    profile: EvalProfile,
    definition: dict,
    chrys_template: Path | None = None,
) -> None:
    info = claim_run(session_factory, run_id)
    if info is None:
        return
    execute_claimed_run(
        settings,
        session_factory,
        runner,
        judge,
        info,
        base,
        current,
        baseline,
        profile,
        definition,
        chrys_template,
    )


def execute_claimed_run_safely(
    settings: Settings,
    session_factory: sessionmaker[Session],
    runner,
    judge,
    info: dict,
    base: Path,
    current: SkillRevision | None,
    baseline: SkillRevision | None,
    profile: EvalProfile,
    definition: dict,
    chrys_template: Path | None,
) -> None:
    try:
        execute_claimed_run(
            settings,
            session_factory,
            runner,
            judge,
            info,
            base,
            current,
            baseline,
            profile,
            definition,
            chrys_template,
        )
    except Exception as exc:  # pragma: no cover - defensive thread boundary
        artifact_dir = run_artifact_dir(
            settings, info["experiment_id"], info["run_id"], info["attempt"]
        )
        fail_run(
            session_factory,
            info["run_id"],
            "infra_error",
            f"{type(exc).__name__}: {exc}",
            artifact_dir,
            retain=True,
        )


def execute_claimed_run(
    settings: Settings,
    session_factory: sessionmaker[Session],
    runner,
    judge,
    info: dict,
    base: Path,
    current: SkillRevision | None,
    baseline: SkillRevision | None,
    profile: EvalProfile,
    definition: dict,
    chrys_template: Path | None,
) -> None:
    run_id = info["run_id"]
    experiment_id = info["experiment_id"]
    group = info["group"]
    trial_index = info["trial_index"]
    anonymous_id = info["anonymous_id"]
    attempt = info["attempt"]
    case = CaseSpec.model_validate(
        next(item for item in definition["cases"] if item["id"] == info["case_id"])
    )

    run_root = run_workspace(settings, experiment_id, run_id, attempt)
    workspace = run_root / "workspace"
    artifact_dir = run_artifact_dir(settings, experiment_id, run_id, attempt)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    chrys_home_root = prepare_trial_runtime(settings, profile, chrys_template, run_root)

    def set_artifact_path(session: Session) -> None:
        run = session.get(Run, run_id)
        assert run is not None
        run.artifact_path = str(artifact_dir)

    db_write(session_factory, set_artifact_path)
    log_writer = LogWriter(artifact_dir / "logs", scope="run", attempt=attempt)

    def record_progress(kind: str, message: str, stage: str | None) -> None:
        log_writer.event("system", message, stage=stage)

    progress = RunProgress(session_factory, run_id, on_event=record_progress)
    log_writer.event(
        "system",
        f"开始执行 {group} · Trial {trial_index} · 尝试 #{attempt}",
        stage="creating_workspace",
    )
    try:
        progress.stage("creating_workspace", "正在创建独立工作区")
        if base.resolve() != workspace.resolve():
            shutil.copytree(base, workspace)
        prepare_eval_workspace(workspace)
        if case.files:
            materialize_files(workspace, case.files)
            _git(workspace, "add", "--force", "--", *(file.path for file in case.files))
            _git(
                workspace,
                "-c",
                "user.name=AAW Scene",
                "-c",
                "user.email=scene@aaw.local",
                "commit",
                "--allow-empty",
                "-m",
                "Install evaluation scene inputs",
            )
        scene_baseline = _git(workspace, "rev-parse", "HEAD").strip()
        selected = current
        if selected is not None:
            progress.stage("installing_skill", "正在安装 Skill 快照")
            install_snapshot(
                Path(selected.snapshot_path),
                workspace,
                selected.skill.name,
                provider=profile.runner_provider,
            )

        runner = runner or build_runner(settings, profile.runner_provider)
        progress.stage("runner", "Runner 第 1 轮已启动")
        outcome = runner.run(
            workspace=workspace,
            artifact_dir=artifact_dir,
            case=runner_case(
                case.model_copy(update={"expected": "", "graders": [], "files": []}),
                skill_name=selected.skill.name if selected else None,
            ),
            profile=profile,
            skill_name=selected.skill.name if selected else None,
            on_progress=lambda kind, message: progress.emit(
                kind, message, activity=kind == "activity"
            ),
            on_log=log_writer.write,
            is_cancelled=progress.cancelled,
            chrys_home_root=chrys_home_root,
        )
        if selected is None and outcome.skills_loaded:
            outcome.error_kind = "skill_isolation_error"
            outcome.error_message = "no_skill 运行意外加载了 Skill，结果不可用于比较"
        if outcome.exit_code not in (None, 0) and not outcome.error_kind:
            outcome.error_kind = "agent_error"
            outcome.error_message = f"Runner exited with code {outcome.exit_code}"
        if outcome.error_kind == "cancelled":
            fail_run(
                session_factory,
                run_id,
                "cancelled",
                outcome.error_message or "Run cancelled by user",
                artifact_dir,
                retain=True,
            )
            return
        if outcome.error_kind == "timeout":
            fail_run(
                session_factory,
                run_id,
                "timeout",
                outcome.error_message or "Runner timed out",
                artifact_dir,
                retain=True,
            )
            return
        progress.stage("collecting_changes", "正在收集文件改动和响应证据")
        changes = (
            capture_changes(workspace, baseline=scene_baseline)
            if case.workflow
            else capture_changes(workspace)
        )
        (artifact_dir / "final-response.md").write_text(outcome.final_response, encoding="utf-8")
        if definition.get("dimensions"):
            terminal = collect_terminal_outputs(
                workspace, case, changes["changed_files"], artifact_dir
            )
        workflow_result = (
            inspect_workflow(workspace, case.workflow, skill_name=selected.skill.name)
            if case.workflow and selected
            else None
        )

        progress.stage("validators", "正在执行确定性验证器")
        deterministic, command_results = evaluate_deterministic(
            case,
            workspace=workspace,
            changed_files=changes["changed_files"],
            artifact_dir=artifact_dir,
            on_log=log_writer.write,
            evaluator_root=run_root / "evaluators",
        )
        evidence = {
            "final_response": outcome.final_response[-80_000:],
            "git_patch": changes["patch"][-120_000:],
            "changed_files": changes["changed_files"],
            "validator_results": command_results,
            "agent_exit_code": outcome.exit_code,
            "agent_error_kind": outcome.error_kind,
            "skill_invoked": outcome.skill_invoked,
        }
        if definition.get("dimensions"):
            evidence.update(terminal)
        write_json(artifact_dir / "terminal-evidence.json", evidence)
        from dataclasses import asdict

        write_json(artifact_dir / "deterministic.json", [asdict(c) for c in deterministic])
        write_json(artifact_dir / "compliance.json", workflow_result or {"applicable": False})
        write_json(
            artifact_dir / "input-and-rubric.json",
            {"case": case.model_dump(mode="json"), "anonymous_id": anonymous_id},
        )
        (artifact_dir / "final-response.md").write_text(outcome.final_response, encoding="utf-8")
        (artifact_dir / "changes.patch").write_text(changes["patch"], encoding="utf-8")
        write_json(artifact_dir / "file-tree.json", file_tree_manifest(workspace))
        included = archive_untracked(
            workspace, changes["untracked_files"], artifact_dir / "untracked.zip"
        )
        write_json(
            artifact_dir / "run.json",
            {
                "anonymous_id": anonymous_id,
                "outcome": {
                    "exit_code": outcome.exit_code,
                    "duration_ms": outcome.duration_ms,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "thread_id": outcome.thread_id,
                    "turns": outcome.turns,
                    "error_kind": outcome.error_kind,
                    "error_message": outcome.error_message,
                    "skill_invoked": outcome.skill_invoked,
                    "skills_loaded": list(outcome.skills_loaded),
                },
                "profile": profile.model_dump(mode="json"),
                "changed_files": changes["changed_files"],
                "untracked_archive": included,
            },
        )
        status = outcome.error_kind or "completed"
        progress.stage("persisting", "正在保存结果和证据包")

        def persist(session: Session) -> None:
            run = session.get(Run, run_id)
            assert run is not None
            run.status = status
            run.artifact_hash = artifact_hash(artifact_dir)
            run.duration_ms = outcome.duration_ms
            run.input_tokens = outcome.input_tokens
            run.output_tokens = outcome.output_tokens
            run.exit_code = outcome.exit_code
            run.artifact_path = str(artifact_dir)
            run.error_kind = outcome.error_kind
            run.error_message = outcome.error_message
            # 纯手动清理：现场一律保留在盘上，由用户在页面手动删除；
            # workspace_retained 仅表示"现场仍在磁盘上"。
            run.workspace_retained = True
            run.completed_at = now()

        db_write(session_factory, persist)
        progress.stage(status, "Run 已完成" if status == "completed" else "Run 已结束")
    except InfrastructureError as exc:
        fail_run(session_factory, run_id, exc.kind, exc.message, artifact_dir, retain=True)
    except Exception as exc:
        fail_run(
            session_factory,
            run_id,
            "infra_error",
            f"{type(exc).__name__}: {exc}",
            artifact_dir,
            retain=True,
        )


def fail_run(
    session_factory: sessionmaker[Session],
    run_id: str,
    kind: str,
    message: str,
    artifact_dir: Path,
    *,
    retain: bool,
) -> None:
    write_json(artifact_dir / "error.json", {"kind": kind, "message": message})
    with session_factory() as session:
        run = session.get(Run, run_id)
        attempt = run.current_attempt if run is not None else None
    log_writer = LogWriter(artifact_dir / "logs", scope="run", attempt=attempt)
    log_writer.event("system", f"Run 失败：{kind} · {message}", stage=kind)
    progress = RunProgress(
        session_factory,
        run_id,
        on_event=lambda event_kind, event_message, stage: log_writer.event(
            "system", event_message, stage=stage
        ),
    )
    progress.error(kind, message)

    def persist(session: Session) -> None:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = kind
        run.error_kind = kind
        run.error_message = message[:10_000]
        run.artifact_path = str(artifact_dir)
        run.workspace_retained = retain
        run.current_stage = kind
        run.completed_at = now()

    db_write(session_factory, persist)


def fail_experiment(
    settings: Settings,
    session_factory: sessionmaker[Session],
    experiment_id: str,
    kind: str,
    message: str,
) -> None:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            return
        experiment.status = "invalid" if kind == "invalid" else "failed"
        experiment.error_kind = kind
        experiment.error_message = message[:10_000]
        experiment.completed_at = now()
        session.commit()
    LogWriter(
        settings.artifacts_dir / experiment_id / "logs",
        scope="experiment",
    ).event("system", f"实验失败：{kind} · {message}", stage="failed")


def finish_experiment(
    settings: Settings,
    session_factory: sessionmaker[Session],
    experiment_id: str,
) -> None:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        assert experiment is not None
        discarded_runs: list[Run] = []
        if experiment.cancel_requested_at:
            for run in experiment.runs:
                if run.status == "queued":
                    run.status = "cancelled"
                    run.current_stage = "cancelled"
                    run.error_kind = "cancelled"
                    run.error_message = "Experiment cancelled before this run started"
                    run.completed_at = now()
                # 取消的实验整体废弃：全部现场随收尾删除（重试会重新克隆）
                discarded_runs.append(run)
            experiment.status = "cancelled"
            experiment.error_kind = "cancelled"
            experiment.error_message = experiment.error_message or "Experiment cancelled by user"
        else:
            failures = [run for run in experiment.runs if run.status != "completed"]
            experiment.status = "completed_with_failures" if failures else "completed"
            if failures:
                experiment.error_kind = "run_failures"
                experiment.error_message = f"{len(failures)} run(s) did not complete successfully"
        experiment.completed_at = now()
        session.commit()
    for run in discarded_runs:
        result = remove_run_workspace_dirs(settings, run.experiment_id, run.id, run.current_attempt)
        mark_workspace_retained(session_factory, run.id, retained=bool(result["failed"]))
    status = experiment.status
    message = experiment.error_message or "所有 run 已完成"
    LogWriter(
        settings.artifacts_dir / experiment_id / "logs",
        scope="experiment",
    ).event("system", f"实验结束：{status} · {message}", stage=status)


def request_run_cancel(session_factory: sessionmaker[Session], run_id: str) -> Run:
    with session_factory() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
        if run.status not in {"queued", "running"}:
            raise EvalError("RUN_NOT_ACTIVE", "Only queued or running runs can be cancelled")
        run.cancel_requested_at = now()
        if run.status == "queued":
            run.status = "cancelled"
            run.current_stage = "cancelled"
            run.error_kind = "cancelled"
            run.error_message = "Run cancelled before it started"
            run.completed_at = now()
        session.commit()
        session.refresh(run)
        return run


def request_experiment_cancel(
    session_factory: sessionmaker[Session], experiment_id: str
) -> Experiment:
    with session_factory() as session:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
        if experiment.status not in {"queued", "preparing", "running", "interrupted"}:
            raise EvalError("EXPERIMENT_NOT_ACTIVE", "Only active experiments can be cancelled")
        experiment.cancel_requested_at = now()
        if experiment.status == "queued":
            experiment.status = "cancelled"
            experiment.error_kind = "cancelled"
            experiment.error_message = "Experiment cancelled before it started"
            experiment.completed_at = now()
        session.commit()
        session.refresh(experiment)
        return experiment
