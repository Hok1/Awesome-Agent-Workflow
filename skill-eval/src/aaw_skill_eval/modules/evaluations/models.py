from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aaw_skill_eval.infrastructure.database import Base
from aaw_skill_eval.infrastructure.identity import new_id, utc_now

if TYPE_CHECKING:
    from aaw_skill_eval.contracts.entities import (
        Experiment,
        Run,
    )


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(128), default="local-user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[Run] = relationship()


class Assessment(Base):
    """One scoring attempt over the immutable artifacts of an execution."""

    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    profile_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution: Mapped[Experiment] = relationship(back_populates="assessments")
    results: Mapped[list[TrialAssessment]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class TrialAssessment(Base):
    __tablename__ = "trial_assessments"
    __table_args__ = (UniqueConstraint("assessment_id", "run_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    score_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment: Mapped[Assessment] = relationship(back_populates="results")
