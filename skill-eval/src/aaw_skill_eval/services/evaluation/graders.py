from __future__ import annotations

import fnmatch
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ...schemas import CaseSpec, DimensionSpec
from ..catalog.packages import materialize_files
from ..observability.logs import LogCallback
from ..providers.base import JudgeOutcome
from ..workspace.repository import run_trusted_command


@dataclass
class ScoreComponent:
    grader_id: str
    name: str
    grader_type: str
    score: float
    weight: float
    hard_gate: bool
    passed: bool
    evidence: str
    reasoning: str = ""
    invalid: bool = False
    dimension_id: str | None = None
    checks: list[dict] = field(default_factory=list)


def parse_check_results(
    raw: str, expected_weights: dict[str, float] | None = None
) -> tuple[float, list[dict]]:
    value = json.loads(raw)
    checks = value.get("checks") if isinstance(value, dict) else None
    if not isinstance(checks, list) or not 1 <= len(checks) <= 500:
        raise ValueError("JSON result requires 1-500 checks")
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str):
            raise ValueError("every check requires a string id")
        if not check["id"] or check["id"] in ids:
            raise ValueError("check ids must be nonempty and unique")
        ids.add(check["id"])
        score, weight = check.get("score"), check.get("weight", 1)
        if (
            type(score) not in {int, float}
            or not math.isfinite(score)
            or not 0 <= score <= 100
            or type(weight) not in {int, float}
            or not math.isfinite(weight)
            or not 0 < weight <= 1000
        ):
            raise ValueError("check score must be 0-100 and weight must be 0-1000")
        if not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
            raise ValueError("every check requires evidence")
        check["weight"] = weight
    if expected_weights:
        if ids != set(expected_weights):
            raise ValueError("Script results must cover exactly the fixed checkpoint ids")
        if any(check["weight"] != expected_weights[check["id"]] for check in checks):
            raise ValueError("Fixed checkpoint weights cannot be changed by the script")
    return (
        sum(check["score"] * check["weight"] for check in checks)
        / sum(check["weight"] for check in checks)
    ), checks


def _safe_relative(workspace: Path, raw: str) -> Path | None:
    candidate = (workspace / raw).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        return None
    return candidate


EXECUTION_TIME_GRADER_ID = "__execution_time__"


def execution_time_component(case: CaseSpec, duration_ms: int | None) -> ScoreComponent | None:
    """把 run 总耗时按用例的 time_scoring 配置折算为「执行效率」分量。

    ≤target_seconds 满分、≥limit_seconds 零分、中间线性；用例未配置或无时长数据时
    返回 None（不计入评价标准，历史实验不受影响）。
    """
    spec = case.time_scoring
    if spec is None or duration_ms is None:
        return None
    seconds = duration_ms / 1000
    if seconds <= spec.target_seconds:
        ratio = 1.0
    elif seconds >= spec.limit_seconds:
        ratio = 0.0
    else:
        ratio = (spec.limit_seconds - seconds) / (spec.limit_seconds - spec.target_seconds)
    score = round(100.0 * ratio, 1)
    return ScoreComponent(
        grader_id=EXECUTION_TIME_GRADER_ID,
        name="执行效率",
        grader_type="duration",
        score=score,
        weight=spec.weight,
        hard_gate=False,
        passed=score >= 60,
        evidence=(
            f"总耗时 {seconds:.0f}s；计分窗口：≤{spec.target_seconds}s → 100 分，"
            f"≥{spec.limit_seconds}s → 0 分，线性折算（权重 {spec.weight:g}）"
        ),
    )


def evaluate_deterministic(
    case: CaseSpec,
    *,
    workspace: Path,
    changed_files: list[str],
    artifact_dir: Path | None = None,
    on_log: LogCallback | None = None,
    evaluator_root: Path | None = None,
) -> tuple[list[ScoreComponent], list[dict[str, Any]]]:
    components: list[ScoreComponent] = []
    command_results: list[dict[str, Any]] = []
    for grader in case.graders:
        if grader.type == "llm_rubric":
            continue
        if grader.type == "command":
            safe_id = grader.id  # Schema restricts ids to safe, unique filename characters.
            stdout_path = (
                artifact_dir / "logs" / f"validator-{safe_id}.stdout.txt"
                if artifact_dir is not None
                else None
            )
            stderr_path = (
                artifact_dir / "logs" / f"validator-{safe_id}.stderr.txt"
                if artifact_dir is not None
                else None
            )
            if on_log is not None:
                on_log("validator", "event", f"开始验证器：{grader.name}")
            cwd = workspace
            environment = None
            if evaluator_root is not None and (grader.files or grader.dimension_id):
                cwd = evaluator_root / grader.id
                materialize_files(cwd, grader.files)
                environment = {
                    "AAW_WORKSPACE": str(workspace.resolve()),
                    "AAW_FINAL_RESPONSE": str((artifact_dir / "final-response.md").resolve())
                    if artifact_dir
                    else "",
                }
                for command in grader.setup_commands:
                    setup_result = run_trusted_command(
                        command, cwd, grader.timeout_seconds, env=environment, on_log=on_log
                    )
                    command_results.append(setup_result)
                    if setup_result.get("exit_code") != 0:
                        components.append(
                            ScoreComponent(
                                grader.id,
                                grader.name,
                                grader.type,
                                0,
                                grader.weight,
                                grader.hard_gate,
                                False,
                                str(setup_result),
                                reasoning="Evaluator setup failed",
                                invalid=True,
                                dimension_id=grader.dimension_id,
                            )
                        )
                        break
                else:
                    setup_result = None
                if setup_result is not None:
                    continue
            result = run_trusted_command(
                grader.command or "",
                cwd,
                grader.timeout_seconds,
                on_log=on_log,
                source="validator",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                env=environment,
            )
            command_results.append(result)
            timed_out = bool(result.get("timed_out"))
            passed = result.get("exit_code") == 0 and not timed_out
            invalid = timed_out
            score = 100.0 if passed else 0.0
            checks = []
            reasoning = "Validator timed out" if timed_out else ""
            if grader.result_format == "json":
                try:
                    if not passed:
                        raise ValueError("JSON validator did not exit successfully")
                    score, checks = parse_check_results(
                        result.get("stdout", ""), grader.check_weights
                    )
                    passed = score >= 60
                except (ValueError, TypeError) as exc:
                    invalid, reasoning = True, str(exc)
            elif grader.dimension_id and result.get("exit_code") not in {0, 1}:
                invalid, reasoning = True, "Validator crashed or could not start"
            if on_log is not None:
                on_log(
                    "validator",
                    "event",
                    f"验证器结束：{grader.name}（{'通过' if passed else '失败'}）",
                )
            evidence = (
                f"exit_code={result.get('exit_code')}\n"
                f"stdout:\n{result.get('stdout', '')[-4000:]}\n"
                f"stderr:\n{result.get('stderr', '')[-4000:]}"
            )
            components.append(
                ScoreComponent(
                    grader_id=grader.id,
                    name=grader.name,
                    grader_type=grader.type,
                    score=score,
                    weight=grader.weight,
                    hard_gate=grader.hard_gate,
                    passed=passed,
                    evidence=evidence,
                    invalid=invalid,
                    reasoning=reasoning,
                    checks=checks,
                )
            )
        elif grader.type == "file_exists":
            candidate = _safe_relative(workspace, grader.path or "")
            passed = bool(candidate and candidate.exists())
            if on_log is not None:
                on_log(
                    "validator",
                    "event",
                    f"文件检查：{grader.path or ''}（{'通过' if passed else '失败'}）",
                )
            components.append(
                ScoreComponent(
                    grader_id=grader.id,
                    name=grader.name,
                    grader_type=grader.type,
                    score=100.0 if passed else 0.0,
                    weight=grader.weight,
                    hard_gate=grader.hard_gate,
                    passed=passed,
                    evidence=str(candidate) if candidate else "Unsafe path rejected",
                    invalid=candidate is None,
                )
            )
        elif grader.type == "forbidden_changes":
            matched = sorted(
                {
                    path
                    for path in changed_files
                    for pattern in grader.patterns
                    if fnmatch.fnmatch(path, pattern)
                }
            )
            passed = not matched
            if on_log is not None:
                on_log(
                    "validator",
                    "event",
                    f"变更约束检查：{grader.name}（{'通过' if passed else '失败'}）",
                )
            components.append(
                ScoreComponent(
                    grader_id=grader.id,
                    name=grader.name,
                    grader_type=grader.type,
                    score=100.0 if passed else 0.0,
                    weight=grader.weight,
                    hard_gate=grader.hard_gate,
                    passed=passed,
                    evidence="No forbidden changes" if passed else "\n".join(matched),
                )
            )
    for component in components:
        component.dimension_id = next(
            g.dimension_id for g in case.graders if g.id == component.grader_id
        )
    return components, command_results


def merge_scores(
    case: CaseSpec,
    deterministic: list[ScoreComponent],
    judge: JudgeOutcome,
    extra: ScoreComponent | None = None,
    dimensions: list[DimensionSpec] | None = None,
) -> dict[str, Any]:
    by_id = {component.grader_id: component for component in deterministic}
    grader_by_id = {grader.id: grader for grader in case.graders}
    for result in judge.scores:
        grader = grader_by_id[result.grader_id]
        by_id[result.grader_id] = ScoreComponent(
            grader_id=grader.id,
            name=grader.name,
            grader_type=grader.type,
            score=max(0.0, min(100.0, result.score)),
            weight=grader.weight,
            hard_gate=grader.hard_gate,
            passed=result.score >= 60,
            evidence=result.evidence,
            reasoning="Judge score must match the fixed rubric levels"
            if grader.allowed_scores and result.score not in grader.allowed_scores
            else result.reasoning,
            dimension_id=grader.dimension_id,
            invalid=bool(
                (grader.dimension_id and not result.evidence.strip())
                or (grader.allowed_scores and result.score not in grader.allowed_scores)
            ),
            checks=[
                {
                    "id": criterion.id or criterion.checkpoint,
                    "score": result.score,
                    "weight": criterion.weight,
                    "evidence": result.evidence,
                }
                for criterion in grader.criteria
            ],
        )
    components = [by_id[grader.id] for grader in case.graders if grader.id in by_id]
    # 合成分量（如「执行效率」执行时间分）不来自 case.graders，追加在评分维度之后
    if extra is not None and all(
        component.grader_id != extra.grader_id for component in components
    ):
        components.append(extra)
    invalid = (
        judge.error is not None
        or any(component.invalid for component in components)
        or len(by_id) != len(case.graders)
    )
    quality = [component for component in components if not component.hard_gate]
    total_weight = sum(component.weight for component in quality)
    quality_score = (
        sum(component.score * component.weight for component in quality) / total_weight
        if total_weight
        else None
    )
    gates = [component for component in components if component.hard_gate]
    dimension_scores = []
    for dimension in dimensions or []:
        items = [component for component in components if component.dimension_id == dimension.id]
        if not items:
            continue
        expected = [g for g in case.graders if g.dimension_id == dimension.id]
        valid = len(items) == len(expected) and not any(item.invalid for item in items)
        scored = [item for item in items if not item.hard_gate]
        weight = sum(item.weight for item in scored)
        score = sum(item.score * item.weight for item in scored) / weight if weight else None
        if score is None and items:
            score = 100.0 if all(item.passed for item in items) else 0.0
        passed = valid and all(item.passed for item in items if item.hard_gate)
        if dimension.hard_gate:
            passed = passed and score is not None and score >= dimension.pass_score
        dimension_scores.append(
            {
                **dimension.model_dump(),
                "score": score if valid else None,
                "invalid": not valid,
                "passed": passed,
            }
        )
    if dimension_scores:
        scored = [
            item for item in dimension_scores if not item["hard_gate"] and item["score"] is not None
        ]
        weight = sum(item["weight"] for item in scored)
        quality_score = (
            sum(item["score"] * item["weight"] for item in scored) / weight if weight else None
        )
    dimension_gates = [item for item in dimension_scores if item["hard_gate"]]
    result = {
        "quality_score": None if invalid else quality_score,
        "hard_gates_passed": sum(1 for component in gates if component.passed)
        + sum(1 for item in dimension_gates if item["passed"]),
        "hard_gates_total": len(gates) + len(dimension_gates),
        "invalid": invalid,
        "judge_error": judge.error,
        "components": [asdict(component) for component in components],
    }
    if dimensions:
        result["dimensions"] = dimension_scores
        result["evaluation_errors"] = [
            f"{component.name}: {component.reasoning or 'Missing required evidence'}"
            for component in components
            if component.invalid
        ] + [
            f"Missing evaluation result: {grader.name}"
            for grader in case.graders
            if grader.id not in by_id
        ]
    return result
