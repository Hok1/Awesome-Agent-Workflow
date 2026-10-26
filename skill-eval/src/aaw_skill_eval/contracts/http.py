from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aaw_skill_eval.contracts.schemas import EvalProfile


class DraftInput(BaseModel):
    data: dict
    revision: int | None = None


class MessageInput(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    revision: int


class ConversationInput(MessageInput):
    mode: Literal["auto", "generate", "retry"] = "auto"


class SuggestionInput(BaseModel):
    revision: int
    action: Literal["adopt", "ignore"]


class RevisionInput(BaseModel):
    revision: int


class CaseEditInput(RevisionInput):
    name: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1, max_length=100000)
    expected: str = Field(min_length=1, max_length=100000)


class ArchiveInput(BaseModel):
    archived: bool = True


class BaselineInput(BaseModel):
    assessment_id: str | None = None
    experiment_id: str | None = None
    group: Literal["current", "no_skill"] = "current"


class ExecuteInput(BaseModel):
    candidate_kind: Literal["no_skill", "skill"] = "no_skill"
    skill_path: str | None = None
    skill_revision_id: str | None = None
    mode: Literal["quick", "formal"] = "formal"
    profile: EvalProfile


class RejudgeInput(BaseModel):
    judge_model: str = Field(min_length=1, max_length=160)
    judge_timeout_seconds: int = Field(default=300, ge=30, le=900)
    judge_total_timeout_seconds: int = Field(default=900, ge=30, le=3600)
