from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class UatReleaseCandidate(Base):
    __tablename__ = "uat_release_candidate"
    __table_args__ = (Index("ix_uat_candidate_status", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    qualification_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    qualification_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    installer_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    installer_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    evidence_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clinical_attested_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    clinical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technical_attested_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    technical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class UatReadinessEvidence(Base):
    __tablename__ = "uat_readiness_evidence"
    __table_args__ = (
        UniqueConstraint("candidate_id", "evidence_type", name="uq_uat_readiness_evidence_type"),
        Index("ix_uat_readiness_candidate", "candidate_id", "evidence_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_release_candidate.id", ondelete="RESTRICT"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    evidence_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UatCandidateLedger(Base):
    __tablename__ = "uat_candidate_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_uat_candidate_event"),
        UniqueConstraint("entry_hash", name="uq_uat_candidate_hash"),
        UniqueConstraint("previous_hash", name="uq_uat_candidate_previous"),
        Index("ix_uat_candidate_ledger", "candidate_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_release_candidate.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class UatExecutionSession(Base):
    __tablename__ = "uat_execution_session"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_uat_execution_candidate"),
        Index("ix_uat_execution_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_release_candidate.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", server_default="OPEN")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    results_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clinical_signed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    clinical_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technical_signed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    technical_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class UatExecutionResult(Base):
    __tablename__ = "uat_execution_result"
    __table_args__ = (
        Index("ix_uat_result_scenario", "session_id", "scenario_code", "id"),
        Index("ix_uat_result_status", "session_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid, unique=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_execution_session.id", ondelete="RESTRICT"), nullable=False)
    scenario_code: Mapped[str] = mapped_column(String(60), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    evidence_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    evidence_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_summary_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tested_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UatExecutionIssue(Base):
    __tablename__ = "uat_execution_issue"
    __table_args__ = (
        UniqueConstraint("session_id", "issue_number", name="uq_uat_issue_number"),
        Index("ix_uat_issue_status", "session_id", "status", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_execution_session.id", ondelete="RESTRICT"), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN", server_default="OPEN")
    summary_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raised_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolution_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UatExecutionLedger(Base):
    __tablename__ = "uat_execution_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_uat_execution_event"),
        UniqueConstraint("entry_hash", name="uq_uat_execution_hash"),
        UniqueConstraint("previous_hash", name="uq_uat_execution_previous"),
        Index("ix_uat_execution_ledger", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_execution_session.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
