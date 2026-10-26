from __future__ import annotations

import base64
import math
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FollowupSpec(BaseModel):
    when_output_contains: str = Field(min_length=1, max_length=500)
    reply: str = Field(min_length=1, max_length=20_000)
    repeat: bool = False


class WorkflowSpec(BaseModel):
    """A scene starts one real AAW workflow; evidence is collected at the end."""

    entry: Literal["sr", "ar", "dev"]
    sr: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
    ar: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
    confirmation_reply: str | None = Field(default=None, min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def entry_inputs(self):
        if self.entry == "ar" and not self.ar:
            raise ValueError("ar 入口必须提供 AR 编号及场景中的已有软件架构文档")
        return self


class PackageFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content_base64: str = Field(max_length=14_000_000)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str):
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(
                part.lower() in {".git", ".codex", ".agents", ".aaw-eval"} for part in path.parts
            )
        ):
            raise ValueError("package files require safe relative paths")
        devices = {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }
        if any(
            part.endswith((".", " "))
            or part.split(".")[0].lower() in devices
            or any(char in part for char in '<>"|?*')
            for part in path.parts
        ):
            raise ValueError("package file path is not portable")
        return value

    @field_validator("content_base64")
    @classmethod
    def valid_content(cls, value: str):
        base64.b64decode(value, validate=True)
        return value


class RubricCriterion(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    checkpoint: str = Field(min_length=1, max_length=3000)
    weight: float = Field(default=1, gt=0, le=1000)
    levels: dict[str, str] = Field(min_length=2, max_length=20)
    evidence_required: str = Field(min_length=1, max_length=3000)

    @field_validator("levels")
    @classmethod
    def score_levels(cls, value: dict[str, str]):
        for score, description in value.items():
            if not 0 <= float(score) <= 100 or not description.strip():
                raise ValueError("rubric levels require scores 0-100 and descriptions")
        return value


class DimensionSpec(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    name: str = Field(min_length=1, max_length=160)
    method: Literal["code", "llm", "hybrid"] = "hybrid"
    weight: float = Field(default=1, gt=0, le=1000)
    hard_gate: bool = False
    pass_score: float = Field(default=60, ge=0, le=100)


class GraderSpec(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    type: Literal["command", "file_exists", "forbidden_changes", "llm_rubric"]
    name: str = Field(min_length=1, max_length=160)
    weight: float = Field(default=0, ge=0, le=1000)
    hard_gate: bool = False
    command: str | None = Field(default=None, max_length=4000)
    path: str | None = Field(default=None, max_length=1000)
    patterns: list[str] = Field(default_factory=list, max_length=100)
    rubric: str | None = Field(default=None, max_length=30_000)
    timeout_seconds: int = Field(default=300, ge=1, le=7200)
    dimension_id: str | None = None
    result_format: Literal["exit_code", "json"] = "exit_code"
    files: list[PackageFile] = Field(default_factory=list, max_length=500)
    setup_commands: list[str] = Field(default_factory=list, max_length=30)
    criteria: list[RubricCriterion] = Field(default_factory=list, max_length=50)
    checkpoint_ids: list[str] = Field(default_factory=list, max_length=50)
    check_weights: dict[str, float] = Field(default_factory=dict, max_length=50)
    allowed_scores: list[float] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.type == "command" and not self.command:
            raise ValueError("command grader requires command")
        if self.type == "file_exists" and not self.path:
            raise ValueError("file_exists grader requires path")
        if self.type == "forbidden_changes" and not self.patterns:
            raise ValueError("forbidden_changes grader requires patterns")
        if self.criteria:
            if self.type != "llm_rubric":
                raise ValueError("structured criteria require an LLM grader")
            self.rubric = (
                "逐项按评分档位评价，按检查点权重加权，每项引用实际产出证据。\n"
                + self.model_dump_json(include={"criteria"})
            )
        if self.type == "llm_rubric" and not self.rubric:
            raise ValueError("llm_rubric grader requires rubric")
        if not self.hard_gate and self.weight <= 0:
            raise ValueError("quality grader weight must be greater than zero")
        return self


class SetupSpec(BaseModel):
    commands: list[str] = Field(default_factory=list, max_length=30)
    preflight: list[str] = Field(default_factory=list, max_length=30)
    network: bool = False
    timeout_seconds: int = Field(default=900, ge=1, le=7200)


class TimeScoringSpec(BaseModel):
    """执行时间计分（可选）：run 总耗时 ≤target_seconds 得满分，≥limit_seconds 得零分，中间线性。"""

    target_seconds: int = Field(ge=1, le=86_400)
    limit_seconds: int = Field(ge=1, le=86_400)
    weight: float = Field(default=10, gt=0, le=1000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.limit_seconds <= self.target_seconds:
            raise ValueError("limit_seconds must be greater than target_seconds")
        return self


class CaseSpec(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")
    name: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1, max_length=50_000)
    expected: str = Field(min_length=1, max_length=50_000)
    weight: float = Field(default=1, gt=0, le=1000)
    agent_context: str = Field(default="", max_length=50_000)
    followups: list[FollowupSpec] = Field(default_factory=list, max_length=20)
    max_turns: int = Field(default=6, ge=1, le=30)
    graders: list[GraderSpec] = Field(min_length=1, max_length=50)
    time_scoring: TimeScoringSpec | None = None
    files: list[PackageFile] = Field(default_factory=list, max_length=500)
    workflow: WorkflowSpec | None = None
    output_paths: list[str] = Field(default_factory=list, max_length=100)
    dimension_weights: dict[str, float] = Field(default_factory=dict, max_length=50)

    @field_validator("dimension_weights")
    @classmethod
    def valid_dimension_weights(cls, value: dict[str, float]):
        if any(not math.isfinite(weight) or not 0 < weight <= 1000 for weight in value.values()):
            raise ValueError("dimension case weights must be greater than zero and at most 1000")
        return value

    @model_validator(mode="after")
    def unique_graders_and_files(self):
        for path in self.output_paths:
            PackageFile.safe_path(path)
        if self.workflow and any(
            file.path == f".sdd/{self.workflow.sr}/workflow.yaml"
            or file.path.startswith(f".sdd/{self.workflow.sr}/.aaw/task-dev/")
            for file in self.files
        ):
            raise ValueError("场景不能预置待测流程状态或任务完成记录")
        ids = [grader.id for grader in self.graders]
        if len(ids) != len(set(ids)):
            raise ValueError("grader ids must be unique within a scenario")
        for files in [self.files, *(grader.files for grader in self.graders)]:
            paths = [file.path.casefold() for file in files]
            if len(paths) != len(set(paths)):
                raise ValueError("duplicate package file paths")
        return self


class ProviderSnapshot(BaseModel):
    provider: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    runtime_version: str | None = None
    model_profile_id: str
    model_profile_name: str | None = None
    model_id: str | None = None
    model_provider: str | None = None
    api_style: str | None = None
    config_hash: str | None = None
    agent_profile: str | None = None
    agent_profile_hash: str | None = None
    isolation: Literal["workspace-write", "read-only", "soft", "unknown"] = "unknown"
    network_policy: Literal["disabled", "enabled", "uncontrolled"] = "disabled"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalProfile(BaseModel):
    schema_version: int = Field(default=2, ge=1, le=2)
    name: str = Field(default="chrys-standard", min_length=1, max_length=120)
    runner_provider: str = Field(default="chrys", pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    runner_model: str = Field(min_length=1, max_length=160)
    runner_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "high"
    judge_provider: str = Field(default="chrys", pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    judge_model: str = Field(min_length=1, max_length=160)
    judge_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "high"
    timeout_seconds: int = Field(default=1800, ge=30, le=14_400)
    judge_timeout_seconds: int = Field(default=300, ge=30, le=900)
    judge_total_timeout_seconds: int = Field(default=900, ge=30, le=3600)
    network: bool = False
    allowed_mcp_servers: list[str] = Field(default_factory=list, max_length=50)
    runner_snapshot: ProviderSnapshot | None = None
    judge_snapshot: ProviderSnapshot | None = None


class RubricDraftRequest(BaseModel):
    project_path: str = Field(min_length=1, max_length=2000)
    skill_path: str = Field(min_length=1, max_length=2000)
    input: str = Field(min_length=1, max_length=50_000)
    expected: str = Field(min_length=1, max_length=50_000)


class RubricDraftResponse(BaseModel):
    project: dict
    skill: dict
    case: CaseSpec


class SuiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    requirement: str = Field(default="", max_length=50000)
    project_path: str = Field(min_length=1, max_length=2000)
    skill_path: str = Field(default="", max_length=2000)
    setup: SetupSpec = Field(default_factory=SetupSpec)
    cases: list[CaseSpec] = Field(min_length=1, max_length=200)
    dimensions: list[DimensionSpec] = Field(default_factory=list, max_length=50)
    catalog_version: int | None = None
    skill_type: Literal["development", "documents_analysis", "workflow"] | None = None

    @model_validator(mode="after")
    def validate_dimensions(self):
        if not self.dimensions:
            if any(g.dimension_id for case in self.cases for g in case.graders):
                raise ValueError("dimension definitions are required")
            return self
        dimensions = {dimension.id: dimension for dimension in self.dimensions}
        if len(dimensions) != len(self.dimensions):
            raise ValueError("dimension ids must be unique")
        used: dict[str, set[str]] = {key: set() for key in dimensions}
        for case in self.cases:
            if case.time_scoring is not None:
                raise ValueError(
                    "dimension suites require an explicit efficiency dimension "
                    "instead of time_scoring"
                )
            if set(case.dimension_weights) - set(dimensions):
                raise ValueError("case weights reference unselected dimensions")
            for grader in case.graders:
                if grader.dimension_id not in dimensions:
                    raise ValueError("every check must reference a selected dimension")
                method = "llm" if grader.type == "llm_rubric" else "code"
                if dimensions[grader.dimension_id].method not in {method, "hybrid"}:
                    raise ValueError("check type does not match dimension method")
                if method == "llm" and not grader.criteria:
                    raise ValueError("LLM dimensions require structured criteria")
                used[grader.dimension_id].add(method)
        for key, dimension in dimensions.items():
            if not used[key]:
                raise ValueError(f"dimension {key} has no test cases")
            if dimension.method == "hybrid" and used[key] != {"code", "llm"}:
                raise ValueError(f"hybrid dimension {key} requires code and LLM checks")
        total_bytes = sum(
            len(base64.b64decode(file.content_base64))
            for case in self.cases
            for files in [case.files, *(g.files for g in case.graders)]
            for file in files
        )
        if total_bytes > 20 * 1024 * 1024:
            raise ValueError("suite package assets exceed 20 MB")
        return self

    @field_validator("cases")
    @classmethod
    def unique_case_ids(cls, value: list[CaseSpec]):
        ids = [case.id for case in value]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return value


class ExperimentCreateRequest(BaseModel):
    suite_id: str
    evaluation_mode: Literal["current_only"] = "current_only"
    candidate_kind: Literal["no_skill", "skill"] = "no_skill"
    skill_path: str | None = None
    skill_revision_id: str | None = None
    mode: Literal["quick", "formal"] = "formal"
    profile: EvalProfile


class BaselineRequest(BaseModel):
    revision_id: str


class HumanReviewRequest(BaseModel):
    score: float = Field(ge=0, le=100)
    note: str = Field(default="", max_length=20_000)
    reviewer: str = Field(default="local-user", min_length=1, max_length=128)
