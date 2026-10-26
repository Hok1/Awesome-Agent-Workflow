from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aaw_skill_eval.infrastructure.database import Base
from aaw_skill_eval.infrastructure.identity import new_id, utc_now

if TYPE_CHECKING:
    from aaw_skill_eval.contracts.entities import (
        Skill,
    )


class Suite(Base):
    __tablename__ = "suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    skill_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("skills.id"), nullable=True)
    baseline_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_path: Mapped[str] = mapped_column(Text)
    definition_path: Mapped[str] = mapped_column(Text)
    definition_hash: Mapped[str] = mapped_column(String(64))
    definition_json: Mapped[str] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    baseline_experiment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    baseline_group: Mapped[str] = mapped_column(
        String(32), default="current", server_default="current"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    skill: Mapped[Skill] = relationship()


class SuiteDraft(Base):
    __tablename__ = "suite_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    messages_json: Mapped[str] = mapped_column(Text, default="[]")
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    workflow_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    suite_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suites.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
