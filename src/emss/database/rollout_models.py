from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class LimitedRolloutSession(Base):
    __tablename__ = "limited_rollout_session"
    __table_args__ = (
        Index("ix_limited_rollout_status", "status", "created_at"),
        Index("ix_limited_rollout_acceptance", "acceptance_session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    acceptance_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("go_live_acceptance_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_label: Mapped[str] = mapped_column(String(120), nullable=False)
    max_workstations: Mapped[int] = mapped_column(Integer, nullable=False)
    incident_halt_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_halt_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PLANNED", server_default="PLANNED"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clinical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    clinical_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    technical_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    started_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class LimitedRolloutWave(Base):
    __tablename__ = "limited_rollout_wave"
    __table_args__ = (
        UniqueConstraint("rollout_session_id", "wave_number", name="uq_rollout_wave_number"),
        Index("ix_limited_rollout_wave_status", "rollout_session_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rollout_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("limited_rollout_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    wave_number: Mapped[int] = mapped_column(Integer, nullable=False)
    cohort_label: Mapped[str] = mapped_column(String(120), nullable=False)
    planned_workstations: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )
    activated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class LimitedRolloutLedger(Base):
    __tablename__ = "limited_rollout_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_limited_rollout_event"),
        UniqueConstraint("entry_hash", name="uq_limited_rollout_hash"),
        UniqueConstraint("previous_hash", name="uq_limited_rollout_previous"),
        Index("ix_limited_rollout_ledger_session", "rollout_session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    rollout_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("limited_rollout_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    wave_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("limited_rollout_wave.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
