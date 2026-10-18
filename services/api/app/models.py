"""Relational model.

Content tables (module, card, lab, rubric, technique) are a projection of the YAML in
`content/` and are rebuilt by the seeder. Everything else is learner data.
Prompts are immutable once written; every run stores the exact model settings and
content versions it used so results stay reproducible.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- identity & access


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    # Stable identity from the token: "<issuer-tenant>:<oid>" for Entra, "dev:<email>" locally.
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    college: Mapped[str | None] = mapped_column(String(200))
    interests: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | pro
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    streak_last_date: Mapped[date | None] = mapped_column(Date)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["RoleAssignment"]] = relationship(back_populates="user", lazy="selectin")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), default="college")  # college | company | community
    city: Mapped[str | None] = mapped_column(String(100))


class Cohort(TimestampMixin, Base):
    __tablename__ = "cohorts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    join_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)


class Event(TimestampMixin, Base):
    """A hackathon or workshop. Joining by code enrols the learner and can grant pro access."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    join_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lab_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    grants_pro_days: Mapped[int] = mapped_column(Integer, default=0)
    entry_fee_inr: Mapped[int] = mapped_column(Integer, default=0)
    prize_inr: Mapped[int] = mapped_column(Integer, default=0)


class RoleAssignment(TimestampMixin, Base):
    """Scoped role. scope_type 'platform' has scope_id NULL."""

    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role", "scope_type", "scope_id", name="uq_role_scope"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    scope_type: Mapped[str] = mapped_column(String(20))  # platform | org | cohort | event
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    user: Mapped[User] = relationship(back_populates="roles")


class Consent(Base):
    """Explicit, versioned, revocable consent (DPDP Act: consent + purpose limitation)."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(40))  # learner_analytics | cohort_sharing | hiring_share
    policy_version: Mapped[str] = mapped_column(String(20))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- content projection


class Technique(Base):
    __tablename__ = "techniques"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(80), index=True)
    order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ConceptCard(Base):
    __tablename__ = "concept_cards"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    technique_id: Mapped[str | None] = mapped_column(String(80), index=True)
    position: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    # Content hash of the brief + pinned test set + rubric additions; runs record it.
    version: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


# ---------------------------------------------------------------- the workspace


class Attempt(TimestampMixin, Base):
    """One learner's canvas for one lab. Holds the versioned prompt trail."""

    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("user_id", "lab_id", "event_id", name="uq_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("labs.id"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    first_score: Mapped[float | None] = mapped_column(Float)
    best_score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    prompts: Mapped[list["PromptVersion"]] = relationship(
        back_populates="attempt", order_by="PromptVersion.version", lazy="selectin"
    )


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("attempt_id", "version", name="uq_prompt_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    lint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Reflection: which technique the learner says they applied in this revision.
    technique_id: Mapped[str | None] = mapped_column(String(80))
    reflection: Mapped[str | None] = mapped_column(Text)

    attempt: Mapped[Attempt] = relationship(back_populates="prompts")


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|critiquing|done|failed
    error: Mapped[str | None] = mapped_column(Text)
    lab_version: Mapped[str] = mapped_column(String(16))
    rubric_version: Mapped[int] = mapped_column(Integer)
    run_deployment: Mapped[str] = mapped_column(String(80))
    run_settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float | None] = mapped_column(Float)
    delta: Mapped[float | None] = mapped_column(Float)
    xp_awarded: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cases: Mapped[list["RunCase"]] = relationship(lazy="selectin", order_by="RunCase.position")
    critique: Mapped["Critique | None"] = relationship(lazy="selectin", uselist=False)


class RunCase(Base):
    __tablename__ = "run_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class Critique(TimestampMixin, Base):
    __tablename__ = "critiques"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), unique=True)
    deployment: Mapped[str] = mapped_column(String(80))
    # {criterion_id: {score, evidence, prompt_diagnosis}}
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB)
    total: Mapped[float] = mapped_column(Float)  # weighted, 0-100
    summary: Mapped[str] = mapped_column(Text)
    # [{quote, criterion, issue, suggestion_kind}] — where in the PROMPT things went wrong
    prompt_spans: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    detected_techniques: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    next_focus: Mapped[str | None] = mapped_column(String(80))  # technique id to try next


class PredictionAnswer(TimestampMixin, Base):
    __tablename__ = "prediction_answers"
    __table_args__ = (UniqueConstraint("run_id", "prediction_id", name="uq_prediction"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    prediction_id: Mapped[str] = mapped_column(String(40))
    choice: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)


# ---------------------------------------------------------------- gamification


class XpEntry(TimestampMixin, Base):
    __tablename__ = "xp_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(60))
    ref: Mapped[str | None] = mapped_column(String(80))


class TechniqueMastery(Base):
    __tablename__ = "technique_mastery"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    technique_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    improving_uses: Mapped[int] = mapped_column(Integer, default=0)
    labs: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    best_delta: Mapped[float] = mapped_column(Float, default=0.0)
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JudgeScore(TimestampMixin, Base):
    __tablename__ = "judge_scores"
    __table_args__ = (UniqueConstraint("event_id", "judge_id", "user_id", name="uq_judge_score"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    judge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    craft: Mapped[int] = mapped_column(Integer)  # 0-10: quality of the iteration trail
    reasoning: Mapped[int] = mapped_column(Integer)  # 0-10: quality of reflections
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- cost & analytics


class UsageEntry(TimestampMixin, Base):
    __tablename__ = "usage_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)  # IST calendar day
    role: Mapped[str] = mapped_column(String(30))
    deployment: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)


class RunCache(TimestampMixin, Base):
    __tablename__ = "run_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    deployment: Mapped[str] = mapped_column(String(80))
    output: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class AnalyticsEvent(TimestampMixin, Base):
    """Append-only learner event stream. Only written when learner_analytics consent is active."""

    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
