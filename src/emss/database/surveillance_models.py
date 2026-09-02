from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class EarlyLifeSurveillanceSession(Base):
    __tablename__ = "early_life_surveillance_session"
    __table_args__ = (
        Index("ix_surveillance_status", "status", "created_at"),
        UniqueConstraint("rollout_session_id", name="uq_surveillance_rollout"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    rollout_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("limited_rollout_session.id", ondelete="RESTRICT"), nullable=False
    )
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_label: Mapped[str] = mapped_column(String(120), nullable=False)
    minimum_snapshots: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_observation_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_snapshot_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OBSERVING", server_default="OBSERVING"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clinical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    clinical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    technical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SurveillanceSnapshot(Base):
    __tablename__ = "surveillance_snapshot"
    __table_args__ = (Index("ix_surveillance_snapshot_session", "surveillance_session_id", "captured_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    surveillance_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("early_life_surveillance_session.id", ondelete="RESTRICT"), nullable=False
    )
    prescriptions_total: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_total: Mapped[int] = mapped_column(Integer, nullable=False)
    unacknowledged_critical_alerts: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interventions: Mapped[int] = mapped_column(Integer, nullable=False)
    polling_failures: Mapped[int] = mapped_column(Integer, nullable=False)
    health_state: Mapped[str] = mapped_column(String(20), nullable=False)
    audit_chain_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    captured_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SurveillanceIssue(Base):
    __tablename__ = "surveillance_issue"
    __table_args__ = (
        UniqueConstraint("surveillance_session_id", "issue_number", name="uq_surveillance_issue_number"),
        Index("ix_surveillance_issue_status", "surveillance_session_id", "status", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    surveillance_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("early_life_surveillance_session.id", ondelete="RESTRICT"), nullable=False
    )
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    summary_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    resolution_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    closed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurveillanceLedger(Base):
    __tablename__ = "surveillance_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_surveillance_event"),
        UniqueConstraint("entry_hash", name="uq_surveillance_hash"),
        UniqueConstraint("previous_hash", name="uq_surveillance_previous"),
        Index("ix_surveillance_ledger_session", "surveillance_session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    surveillance_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("early_life_surveillance_session.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
