"""Read terminal AAW evidence without running the CLI (which can update itself)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from ...schemas import CaseSpec, FollowupSpec, WorkflowSpec


def runner_case(case: CaseSpec, *, with_skill: bool) -> CaseSpec:
    if not case.workflow:
        return case
    spec = case.workflow
    common = (
        f"\n场景入口={spec.entry}, SR={spec.sr}"
        + (f", AR={spec.ar}" if spec.ar else "")
        + "。最终交付需包含设计文档、代码、测试与实际验证依据。"
    )
    if not with_skill:
        return case.model_copy(update={"agent_context": case.agent_context + common})
    context = (
        f"\nAAW 工作流场景：entry={spec.entry}, SR={spec.sr}"
        + (f", AR={spec.ar}" if spec.ar else "")
        + "。使用被测 Skill 的工作流及随包依赖，按真实工作单执行至终态。"
        "保留文档、代码和验证记录；不得伪造完成状态或 Reviewer 证据。"
        "CLI 返回 awaiting_user_confirm 时，汇报交付件，输出 AWAITING_EVAL_CONFIRM 并结束本轮。"
        "不要在线更新 Skill；设置 AAW_UPDATE_CHECK=off、AAW_TELEMETRY_ENABLED=false。"
        "能力不足或真实需求缺失时报告阻塞。"
    )
    followups = list(case.followups)
    if spec.confirmation_reply:
        followups.append(
            FollowupSpec(
                when_output_contains="AWAITING_EVAL_CONFIRM",
                reply=spec.confirmation_reply,
                repeat=True,
            )
        )
    return case.model_copy(
        update={"agent_context": case.agent_context + common + context, "followups": followups}
    )


def _inside(workspace: Path, path: str) -> Path:
    candidate = (workspace / path).resolve()
    if not candidate.is_relative_to(workspace.resolve()):
        raise ValueError("证据路径超出工作区")
    return candidate


def inspect_workflow(workspace: Path, spec: WorkflowSpec) -> dict:
    errors: list[str] = []
    remarks = [
        "设计门禁结果未由 CLI 序列化到 workflow.yaml，本评价器无法校验 gate_result，"
        "仅校验步骤完成与交付件"
    ]
    state_path = f".sdd/{spec.sr}/workflow.yaml"
    try:
        state = yaml.safe_load(_inside(workspace, state_path).read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("workflow.yaml 必须为对象")
        steps = state.get("steps")
        if state.get("sr") != spec.sr or state.get("entry") != spec.entry:
            errors.append("工作流 SR 或入口与场景不一致")
        if state.get("status") != "done" or state.get("pending_user_confirm"):
            errors.append("工作流未到 done 终态或仍等待确认")
        if not isinstance(steps, list) or not steps:
            raise ValueError("工作流缺少步骤")
        if not all(isinstance(step, dict) and step.get("finished") is True for step in steps):
            errors.append("仍有未完成步骤")
        tasks = [step for step in steps if step.get("type") in {"task-dev", "dev-task-dev"}]
        if not tasks:
            errors.append("工作流未生成代码交付任务")
        for step in steps:
            for output in step.get("output", []):
                if output.get("required", True) and output.get("path"):
                    path = _inside(workspace, output["path"])
                    if not path.is_file() or not path.stat().st_size:
                        errors.append(f"缺少非空交付件：{output['path']}")
        for step in tasks:
            task_path = (
                f".sdd/{spec.sr}/.aaw/task-dev/{step['id']}/{step.get('attempt', 1)}/state.json"
            )
            task = json.loads(_inside(workspace, task_path).read_text(encoding="utf-8"))
            if task.get("status") != "completed" or task.get("open_findings"):
                errors.append(f"任务 {step['id']} 未完成验证或存在未解决 Review 问题")
            reports = task.get("reports", {})
            for name in ("implementation", "review", "revalidation", "delivery", "codecheck"):
                report_path = reports.get(name)
                if not report_path or not _inside(workspace, report_path).is_file():
                    errors.append(f"任务 {step['id']} 缺少 {name} 记录")
                    continue
                report = json.loads(_inside(workspace, report_path).read_text(encoding="utf-8"))
                if name == "review":
                    roles = {
                        r.get("role")
                        for r in report.get("reviewers", [])
                        if r.get("status") == "completed" and r.get("report_ref")
                    }
                    # 用户决策（2026-10-10）：Chrys Runner 无 subagent 工具，
                    # 跑不出 reviewer-a/b 双报告——缺独立 Reviewer 证据降级为备注
                    if roles != {"reviewer-a", "reviewer-b"}:
                        remarks.append(
                            f"任务 {step['id']} Reviewer 报告引用="
                            f"{sorted(roles) if roles else '无'}（Chrys Runner 下属预期）"
                        )
        return {
            "required": True,
            "passed": not errors,
            "state_path": state_path,
            "entry": spec.entry,
            "status": state.get("status"),
            "errors": errors,
            "remarks": remarks,
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        return {
            "required": True,
            "passed": False,
            "state_path": state_path,
            "entry": spec.entry,
            "errors": errors + [f"流程证据缺失或无效：{exc}"],
            "remarks": remarks,
        }


def collect_terminal_outputs(
    workspace: Path, case: CaseSpec, changed: list[str], artifact_dir: Path
) -> dict:
    """Archive terminal files even when ignored by Git; give the judge a bounded text view."""
    paths = list(case.output_paths)
    if case.workflow:
        root = workspace / ".sdd"
        if root.is_dir():
            paths += [
                p.relative_to(workspace).as_posix() for p in sorted(root.rglob("*")) if p.is_file()
            ]
    paths += changed
    outputs, inventory = {}, []
    budget = 240_000
    archived_bytes = 0
    with zipfile.ZipFile(
        artifact_dir / "terminal-outputs.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for relative in dict.fromkeys(paths):
            try:
                candidate = _inside(workspace, relative)
                if not candidate.is_file():
                    continue
                size = candidate.stat().st_size
                archived = size <= 5_000_000 and archived_bytes + size <= 50_000_000
                if archived:
                    archive.write(candidate, relative)
                    archived_bytes += size
                inventory.append({"path": relative, "size": size, "archived": archived})
                if budget > 0:
                    with candidate.open("rb") as stream:
                        raw = stream.read(min(budget, 30_000))
                        if b"\0" in raw:
                            continue
                        content = raw.decode("utf-8", errors="replace")
                    outputs[relative] = content
                    budget -= len(content)
            except (OSError, UnicodeError, ValueError):
                continue
    return {"output_files": outputs, "terminal_inventory": inventory}
