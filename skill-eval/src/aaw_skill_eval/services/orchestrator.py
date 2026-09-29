from __future__ import annotations

import json
import random
import secrets
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..errors import EvalError, InfrastructureError
from ..models import Experiment, Run, RunAttempt, RunProgressEvent, SkillRevision, Suite
from ..schemas import CaseSpec, EvalProfile, ExperimentCreateRequest, SetupSpec
from .chrys import enrich_profile, verify_profile
from .graders import evaluate_deterministic, merge_scores
from .logs import LogWriter
from .progress import RunProgress
from .repository import (
    capture_changes,
    clone_at_commit,
    file_tree_manifest,
    inspect_clean_project,
    inspect_project_commit,
    run_trusted_command,
)
from .runner import build_judge, build_runner
from .skills import import_skill, install_snapshot, prepare_eval_workspace
from .storage import archive_untracked, canonical_json, content_hash, write_json
from .workspace_paths import experiment_workspace, run_workspace


def _now() -> datetime:
    return datetime.now(UTC)


class ExperimentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        runner=None,
        judge=None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.runner = runner
        self.judge = judge

    def create(self, request: ExperimentCreateRequest) -> Experiment:
        with self.session_factory() as session:
            suite = session.get(Suite, request.suite_id)
            if suite is None:
                raise EvalError(
                    "SUITE_NOT_FOUND",
                    "Evaluation suite was not found",
                    status_code=404,
                )
            project = inspect_clean_project(suite.project_path)
            current = import_skill(session, self.settings, suite.skill.source_path)
            session.refresh(suite.skill)
            baseline_id = suite.skill.baseline_revision_id
            if baseline_id == current.id:
                baseline_id = None
            profile = enrich_profile(self.settings, request.profile)
            profile_data = profile.model_dump(mode="json")
            profile_identity = {key: value for key, value in profile_data.items() if key != "name"}
            profile_json = canonical_json(profile_data)
            experiment = Experiment(
                suite_id=suite.id,
                current_revision_id=current.id,
                baseline_revision_id=baseline_id,
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

    def create_retry(self, experiment_id: str) -> Experiment:
        with self.session_factory() as session:
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
                "current_revision_id": original.current_revision_id,
                "baseline_revision_id": original.baseline_revision_id,
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

        with self.session_factory() as session:
            original = session.get(Experiment, experiment_id)
            assert original is not None
            if original.status in {"queued", "interrupted"}:
                original.status = "cancelled"
                original.cancel_requested_at = original.cancel_requested_at or _now()
                original.error_kind = "cancelled"
                original.error_message = "Experiment cancelled because a retry was requested"
                original.completed_at = original.completed_at or _now()
            elif original.status in {"preparing", "running"}:
                original.cancel_requested_at = original.cancel_requested_at or _now()
                original.error_kind = "cancelled"
                original.error_message = "Experiment cancellation requested because a retry was requested"

            retry = Experiment(
                **snapshot,
                retry_of_experiment_id=original.id,
                status="queued",
            )
            session.add(retry)
            session.commit()
            session.refresh(retry)
            return retry

    def execute(self, experiment_id: str) -> None:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None or experiment.status not in {"queued", "interrupted"}:
                return
            experiment.status = "preparing"
            experiment.started_at = _now()
            session.commit()
            suite = session.get(Suite, experiment.suite_id)
            assert suite is not None
            definition = json.loads(experiment.suite_snapshot_json)
            profile = EvalProfile.model_validate_json(experiment.profile_json)
            current = session.get(SkillRevision, experiment.current_revision_id)
            baseline = (
                session.get(SkillRevision, experiment.baseline_revision_id)
                if experiment.baseline_revision_id
                else None
            )
            assert current is not None
            _ = current.skill.name
            if baseline is not None:
                _ = baseline.skill.name

        root = experiment_workspace(self.settings, experiment_id)
        base = root / "base"
        experiment_log = LogWriter(
            self.settings.artifacts_dir / experiment_id / "logs",
            scope="experiment",
        )
        experiment_log.event("system", "实验开始准备")
        try:
            experiment_log.event("system", "正在校验 Runner/Judge 配置", stage="preparing")
            verify_profile(self.settings, profile)
            experiment_log.event("system", "Runner/Judge 配置校验完成", stage="preparing")
            if experiment.retry_of_experiment_id:
                snapshot = inspect_project_commit(suite.project_path, experiment.project_commit)
            else:
                snapshot = inspect_clean_project(suite.project_path)
                if snapshot.commit != experiment.project_commit:
                    raise EvalError(
                        "PROJECT_MOVED",
                        "Project HEAD changed after the experiment was queued; create a new experiment",
                    )
            if root.exists():
                shutil.rmtree(root)
            experiment_log.event("system", "正在创建固定提交的评测副本", stage="cloning")
            clone_at_commit(snapshot, base)
            experiment_log.event("system", "评测副本已创建", stage="cloning")
            setup = SetupSpec.model_validate(definition.get("setup") or {})
            setup_log = self._prepare_base(base, setup, log_writer=experiment_log)
            write_json(self.settings.artifacts_dir / experiment_id / "setup.json", setup_log)
            experiment_log.event("system", "正在创建独立评测运行", stage="queuing_runs")
            self._create_runs(experiment_id, definition, baseline is not None)
            with self.session_factory() as session:
                item = session.get(Experiment, experiment_id)
                assert item is not None
                item.status = "running"
                session.commit()
            experiment_log.event("system", "运行队列已创建，开始依次执行", stage="running")
            for run_id in self._ordered_run_ids(experiment_id):
                if self._experiment_cancelled(experiment_id):
                    experiment_log.event("system", "实验已取消，停止启动后续 run", stage="cancelled")
                    break
                self._execute_run(run_id, base, current, baseline, profile, definition)
            self._finish_experiment(experiment_id)
        except EvalError as exc:
            experiment_log.event("system", f"实验准备失败：{exc.kind} · {exc.message}", stage="failed")
            self._fail_experiment(experiment_id, exc.kind, exc.message)
        except Exception as exc:
            experiment_log.event(
                "system", f"实验基础设施异常：{type(exc).__name__}: {exc}", stage="failed"
            )
            self._fail_experiment(experiment_id, "infra_error", f"{type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def _prepare_base(
        self,
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

    def _create_runs(self, experiment_id: str, definition: dict, has_baseline: bool) -> None:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            assert experiment is not None
            existing = session.scalar(select(Run).where(Run.experiment_id == experiment_id))
            if existing is not None:
                return
            groups = ["no_skill", "current"]
            if has_baseline:
                groups.insert(1, "baseline")
            rng = random.Random(experiment.seed)
            order = 0
            for case_data in definition["cases"]:
                case = CaseSpec.model_validate(case_data)
                for trial_index in range(1, experiment.trials + 1):
                    block = list(groups)
                    rng.shuffle(block)
                    for group in block:
                        anonymous = f"candidate-{uuid.uuid4().hex[:8].upper()}"
                        run = Run(
                            experiment_id=experiment_id,
                            case_id=case.id,
                            group_name=group,
                            trial_index=trial_index,
                            anonymous_id=anonymous,
                            status="queued",
                            score_json=canonical_json({"execution_order": order}),
                        )
                        order += 1
                        session.add(run)
                        session.flush()
                        session.add(
                            RunProgressEvent(
                                run_id=run.id,
                                attempt=1,
                                kind="stage",
                                stage="queued",
                                message="等待前序 run 完成",
                            )
                        )
            session.commit()

    def _ordered_run_ids(self, experiment_id: str) -> list[str]:
        with self.session_factory() as session:
            runs = list(session.scalars(select(Run).where(Run.experiment_id == experiment_id)))
            return [
                run.id
                for run in sorted(
                    runs,
                    key=lambda item: json.loads(item.score_json or "{}").get("execution_order", 0),
                )
            ]

    def _execute_run(
        self,
        run_id: str,
        base: Path,
        current: SkillRevision,
        baseline: SkillRevision | None,
        profile: EvalProfile,
        definition: dict,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            assert run is not None
            if run.status != "queued":
                return
            case = CaseSpec.model_validate(
                next(item for item in definition["cases"] if item["id"] == run.case_id)
            )
            run.status = "running"
            run.current_stage = "creating_workspace"
            run.started_at = _now()
            run.stage_started_at = run.started_at
            run.last_activity_at = run.started_at
            run.last_heartbeat_at = run.started_at
            session.commit()
            group = run.group_name
            trial_index = run.trial_index
            anonymous_id = run.anonymous_id
            experiment_id = run.experiment_id
            attempt = run.current_attempt

        run_root = run_workspace(self.settings, experiment_id, run_id, attempt)
        workspace = run_root / "workspace"
        artifact_dir = self.settings.artifacts_dir / experiment_id / run_id
        if attempt > 1:
            artifact_dir = artifact_dir / f"attempt-{attempt}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            assert run is not None
            run.artifact_path = str(artifact_dir)
            session.commit()
        log_writer = LogWriter(artifact_dir / "logs", scope="run", attempt=attempt)

        def record_progress(kind: str, message: str, stage: str | None) -> None:
            log_writer.event("system", message, stage=stage)

        progress = RunProgress(self.session_factory, run_id, on_event=record_progress)
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
            selected: SkillRevision | None = None
            if group == "current":
                selected = current
            elif group == "baseline":
                selected = baseline
            if selected is not None:
                progress.stage("installing_skill", "正在安装 Skill 快照")
                install_snapshot(
                    Path(selected.snapshot_path),
                    workspace,
                    selected.skill.name,
                    provider=profile.runner_provider,
                )

            runner = self.runner or build_runner(self.settings, profile.runner_provider)
            progress.stage("runner", "Runner 第 1 轮已启动")
            outcome = runner.run(
                workspace=workspace,
                artifact_dir=artifact_dir,
                case=case,
                profile=profile,
                skill_name=selected.skill.name if selected else None,
                on_progress=lambda kind, message: progress.emit(
                    kind, message, activity=kind == "activity"
                ),
                on_log=log_writer.write,
                is_cancelled=progress.cancelled,
            )
            if outcome.error_kind == "cancelled":
                self._fail_run(
                    run_id,
                    "cancelled",
                    outcome.error_message or "Run cancelled by user",
                    artifact_dir,
                    retain=True,
                )
                return
            if outcome.error_kind == "timeout":
                self._fail_run(
                    run_id,
                    "timeout",
                    outcome.error_message or "Runner timed out",
                    artifact_dir,
                    retain=True,
                )
                return
            progress.stage("collecting_changes", "正在收集文件改动和响应证据")
            changes = capture_changes(workspace)
            progress.stage("validators", "正在执行确定性验证器")
            deterministic, command_results = evaluate_deterministic(
                case,
                workspace=workspace,
                changed_files=changes["changed_files"],
                artifact_dir=artifact_dir,
                on_log=log_writer.write,
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
            judge_service = self.judge or build_judge(self.settings, profile.judge_provider)
            progress.stage("judge", "Judge 正在进行盲评")
            judge = judge_service.evaluate(
                anonymous_id=anonymous_id,
                case=case,
                graders=case.graders,
                evidence=evidence,
                profile=profile,
                artifact_dir=artifact_dir,
                on_progress=lambda kind, message: progress.emit(
                    kind, message, activity=kind == "activity"
                ),
                on_log=log_writer.write,
                is_cancelled=progress.cancelled,
            )
            if progress.cancelled():
                self._fail_run(
                    run_id,
                    "cancelled",
                    "Run cancelled by user",
                    artifact_dir,
                    retain=True,
                )
                return
            progress.stage("scoring", "正在合并评分与 hard gates")
            merged = merge_scores(case, deterministic, judge)
            merged["skill_invoked"] = outcome.skill_invoked
            merged["skills_loaded"] = list(outcome.skills_loaded)
            write_json(
                artifact_dir / "input-and-rubric.json",
                {"case": case.model_dump(mode="json"), "anonymous_id": anonymous_id},
            )
            (artifact_dir / "final-response.md").write_text(
                outcome.final_response, encoding="utf-8"
            )
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
                    "scores": merged,
                },
            )
            write_json(artifact_dir / "scores.json", merged)
            status = outcome.error_kind or ("grader_invalid" if merged["invalid"] else "completed")
            progress.stage("persisting", "正在保存结果和证据包")
            with self.session_factory() as session:
                run = session.get(Run, run_id)
                assert run is not None
                run.status = status
                run.quality_score = merged["quality_score"]
                run.hard_gates_passed = merged["hard_gates_passed"]
                run.hard_gates_total = merged["hard_gates_total"]
                run.duration_ms = outcome.duration_ms
                run.input_tokens = outcome.input_tokens
                run.output_tokens = outcome.output_tokens
                run.exit_code = outcome.exit_code
                run.artifact_path = str(artifact_dir)
                run.score_json = canonical_json(merged)
                run.error_kind = "grader_invalid" if merged["invalid"] else outcome.error_kind
                run.error_message = merged.get("judge_error") or outcome.error_message
                run.workspace_retained = run.error_kind is not None
                run.completed_at = _now()
                session.commit()
            progress.stage(status, "Run 已完成" if status == "completed" else "Run 已结束")
            if status == "completed" and outcome.error_kind is None:
                shutil.rmtree(run_root, ignore_errors=True)
                if run_root.exists():
                    with self.session_factory() as session:
                        retained = session.get(Run, run_id)
                        assert retained is not None
                        retained.workspace_retained = True
                        session.commit()
        except InfrastructureError as exc:
            self._fail_run(run_id, exc.kind, exc.message, artifact_dir, retain=True)
        except Exception as exc:
            self._fail_run(
                run_id,
                "infra_error",
                f"{type(exc).__name__}: {exc}",
                artifact_dir,
                retain=True,
            )

    def _fail_run(
        self,
        run_id: str,
        kind: str,
        message: str,
        artifact_dir: Path,
        *,
        retain: bool,
    ) -> None:
        write_json(artifact_dir / "error.json", {"kind": kind, "message": message})
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            attempt = run.current_attempt if run is not None else None
        log_writer = LogWriter(artifact_dir / "logs", scope="run", attempt=attempt)
        log_writer.event("system", f"Run 失败：{kind} · {message}", stage=kind)
        progress = RunProgress(
            self.session_factory,
            run_id,
            on_event=lambda event_kind, event_message, stage: log_writer.event(
                "system", event_message, stage=stage
            ),
        )
        progress.error(kind, message)
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            assert run is not None
            run.status = kind
            run.error_kind = kind
            run.error_message = message[:10_000]
            run.artifact_path = str(artifact_dir)
            run.workspace_retained = retain
            run.current_stage = kind
            run.completed_at = _now()
            session.commit()

    def _fail_experiment(self, experiment_id: str, kind: str, message: str) -> None:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                return
            experiment.status = "invalid" if kind == "invalid" else "failed"
            experiment.error_kind = kind
            experiment.error_message = message[:10_000]
            experiment.completed_at = _now()
            session.commit()
        LogWriter(
            self.settings.artifacts_dir / experiment_id / "logs",
            scope="experiment",
        ).event("system", f"实验失败：{kind} · {message}", stage="failed")

    def _experiment_cancelled(self, experiment_id: str) -> bool:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            return bool(experiment is None or experiment.cancel_requested_at)

    def _finish_experiment(self, experiment_id: str) -> None:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            assert experiment is not None
            if experiment.cancel_requested_at:
                for run in experiment.runs:
                    if run.status == "queued":
                        run.status = "cancelled"
                        run.current_stage = "cancelled"
                        run.error_kind = "cancelled"
                        run.error_message = "Experiment cancelled before this run started"
                        run.completed_at = _now()
                experiment.status = "cancelled"
                experiment.error_kind = "cancelled"
                experiment.error_message = experiment.error_message or "Experiment cancelled by user"
            else:
                failures = [run for run in experiment.runs if run.status != "completed"]
                experiment.status = "completed_with_failures" if failures else "completed"
                if failures:
                    experiment.error_kind = "run_failures"
                    experiment.error_message = (
                        f"{len(failures)} run(s) did not complete successfully"
                    )
            experiment.completed_at = _now()
            session.commit()
            status = experiment.status
            message = experiment.error_message or "所有 run 已完成"
        LogWriter(
            self.settings.artifacts_dir / experiment_id / "logs",
            scope="experiment",
        ).event("system", f"实验结束：{status} · {message}", stage=status)

    def request_run_cancel(self, run_id: str) -> Run:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
            if run.status not in {"queued", "running"}:
                raise EvalError("RUN_NOT_ACTIVE", "Only queued or running runs can be cancelled")
            run.cancel_requested_at = _now()
            if run.status == "queued":
                run.status = "cancelled"
                run.current_stage = "cancelled"
                run.error_kind = "cancelled"
                run.error_message = "Run cancelled before it started"
                run.completed_at = _now()
            session.commit()
            session.refresh(run)
            return run

    def request_experiment_cancel(self, experiment_id: str) -> Experiment:
        with self.session_factory() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise EvalError("EXPERIMENT_NOT_FOUND", "Experiment was not found", status_code=404)
            if experiment.status not in {"queued", "preparing", "running", "interrupted"}:
                raise EvalError("EXPERIMENT_NOT_ACTIVE", "Only active experiments can be cancelled")
            experiment.cancel_requested_at = _now()
            if experiment.status == "queued":
                experiment.status = "cancelled"
                experiment.error_kind = "cancelled"
                experiment.error_message = "Experiment cancelled before it started"
                experiment.completed_at = _now()
            session.commit()
            session.refresh(experiment)
            return experiment

    def prepare_retry(self, run_id: str) -> Run:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise EvalError("RUN_NOT_FOUND", "Run was not found", status_code=404)
            if run.error_kind not in {"infra_error", "timeout"}:
                raise EvalError(
                    "RUN_NOT_RETRIABLE",
                    "Only infrastructure errors and timeouts can be formally retried",
                )
            if run.current_attempt >= 2:
                raise EvalError("RETRY_LIMIT_REACHED", "A formal retry was already used")
            session.add(
                RunAttempt(
                    run_id=run.id,
                    attempt_index=run.current_attempt,
                    status=run.status,
                    stage=run.current_stage,
                    artifact_path=run.artifact_path,
                    error_kind=run.error_kind,
                    error_message=run.error_message,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )
            )
            run.current_attempt += 1
            run.status = "queued"
            run.current_stage = "queued"
            run.stage_started_at = _now()
            run.last_heartbeat_at = None
            run.last_activity_at = None
            run.cancel_requested_at = None
            run.quality_score = None
            run.hard_gates_passed = 0
            run.hard_gates_total = 0
            run.duration_ms = None
            run.input_tokens = None
            run.output_tokens = None
            run.exit_code = None
            run.artifact_path = None
            run.score_json = canonical_json({"retry": True})
            run.error_kind = None
            run.error_message = None
            run.workspace_retained = False
            run.started_at = None
            run.completed_at = None
            experiment = session.get(Experiment, run.experiment_id)
            assert experiment is not None
            experiment.status = "queued"
            experiment.error_kind = None
            experiment.error_message = None
            experiment.completed_at = None
            session.add(
                RunProgressEvent(
                    run_id=run.id,
                    attempt=run.current_attempt,
                    kind="stage",
                    stage="queued",
                    message="正式重试已加入队列",
                )
            )
            session.commit()
            session.refresh(run)
            return run

    def execute_retry(self, run_id: str) -> None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is None or run.status != "queued" or run.current_attempt != 2:
                return
            experiment = session.get(Experiment, run.experiment_id)
            assert experiment is not None
            suite = session.get(Suite, experiment.suite_id)
            assert suite is not None
            definition = json.loads(experiment.suite_snapshot_json)
            profile = EvalProfile.model_validate_json(experiment.profile_json)
            current = session.get(SkillRevision, experiment.current_revision_id)
            baseline = (
                session.get(SkillRevision, experiment.baseline_revision_id)
                if experiment.baseline_revision_id
                else None
            )
            assert current is not None
            _ = current.skill.name
            if baseline is not None:
                _ = baseline.skill.name
            experiment.status = "running"
            session.commit()

        base = run_workspace(
            self.settings, experiment.id, run.id, run.current_attempt
        ) / "workspace"
        experiment_log = LogWriter(
            self.settings.artifacts_dir / experiment.id / "logs",
            scope="experiment",
        )
        experiment_log.event(
            "system",
            f"正在为 run {run.id[:8]} 准备正式重试 #{run.current_attempt}",
            stage="retry_preparing",
        )
        try:
            verify_profile(self.settings, profile)
            snapshot = inspect_clean_project(suite.project_path)
            if snapshot.commit != experiment.project_commit:
                raise EvalError(
                    "PROJECT_MOVED",
                    "Project HEAD changed after the experiment; create a new experiment",
                )
            clone_at_commit(snapshot, base)
            setup = SetupSpec.model_validate(definition.get("setup") or {})
            setup_log = self._prepare_base(base, setup, log_writer=experiment_log)
            write_json(
                self.settings.artifacts_dir
                / experiment.id
                / run.id
                / f"retry-setup-{run.current_attempt}.json",
                setup_log,
            )
            self._execute_run(run.id, base, current, baseline, profile, definition)
            self._finish_experiment(experiment.id)
        except EvalError as exc:
            experiment_log.event("system", f"重试准备失败：{exc.kind} · {exc.message}", stage="failed")
            artifact_dir = self.settings.artifacts_dir / experiment.id / run.id / "attempt-2"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            self._fail_run(run.id, exc.kind, exc.message, artifact_dir, retain=True)
            self._finish_experiment(experiment.id)
