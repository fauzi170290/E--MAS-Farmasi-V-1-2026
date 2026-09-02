from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class ProductionReleaseRecord(Base):
    __tablename__ = "production_release_record"
    __table_args__ = (
        UniqueConstraint("surveillance_session_id", name="uq_production_release_surveillance"),
        Index("ix_production_release_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    surveillance_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("early_life_surveillance_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_label: Mapped[str] = mapped_column(String(120), nullable=False)
    installer_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    installer_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authorized_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_ordered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    rollback_ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProductionReleaseEvidence(Base):
    __tablename__ = "production_release_evidence"
    __table_args__ = (
        UniqueConstraint("release_record_id", "evidence_type", name="uq_production_evidence_type"),
        Index("ix_production_evidence_record", "release_record_id", "evidence_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    release_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("production_release_record.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    evidence_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProductionChangeApproval(Base):
    __tablename__ = "production_change_approval"
    __table_args__ = (UniqueConstraint("release_record_id", name="uq_production_change_release"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    release_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("production_release_record.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    evidence_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    external_approver_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deployment_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProductionReleaseLedger(Base):
    __tablename__ = "production_release_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_production_release_event"),
        UniqueConstraint("entry_hash", name="uq_production_release_hash"),
        UniqueConstraint("previous_hash", name="uq_production_release_previous"),
        Index("ix_production_release_ledger_record", "release_record_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    release_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("production_release_record.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
