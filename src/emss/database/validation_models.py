from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class ValidationCampaign(Base):
    __tablename__ = "validation_campaign"
    __table_args__ = (Index("ix_validation_campaign_status", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False, default="CLINICAL_VALIDATION", server_default="CLINICAL_VALIDATION")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="IN_PROGRESS", server_default="IN_PROGRESS")
    source_filename: Mapped[str | None] = mapped_column(String(260), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    application_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    screening_engine_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    knowledge_base_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="RESTRICT"),
        nullable=True,
    )
    safety_configuration_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    cases: Mapped[list[ClinicalValidationCase]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class ClinicalValidationCase(Base):
    __tablename__ = "clinical_validation_case"
    __table_args__ = (
        UniqueConstraint("campaign_id", "case_code", name="uq_validation_case_campaign_code"),
        Index("ix_validation_case_gate", "campaign_id", "review_status", "match"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("validation_campaign.id", ondelete="CASCADE"), nullable=False)
    case_code: Mapped[str] = mapped_column(String(80), nullable=False)
    drug_list: Mapped[str] = mapped_column(Text, nullable=False)
    clinical_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_pairs: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_highest_severity: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_duplicate_therapy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    expected_polypharmacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    expected_high_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    expected_lasa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    expected_unmapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    expected_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    checks_compound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    checks_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_highest_severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actual_overall_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actual_duplicate_therapy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_polypharmacy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_high_alert: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_lasa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_unmapped: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_alert: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duplicate_output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    compound_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    revision_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_REVIEWED", server_default="NOT_REVIEWED")
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    campaign: Mapped[ValidationCampaign] = relationship(back_populates="cases")


class UatSession(Base):
    __tablename__ = "uat_session"
    __table_args__ = (Index("ix_uat_session_status", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="IN_PROGRESS", server_default="IN_PROGRESS")
    pharmacist_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    pharmacist_approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    pharmacist_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pharmacist_approved_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pharmacist_approved_campaign_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("validation_campaign.id", ondelete="SET NULL"),
        nullable=True,
    )
    it_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    it_approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    it_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    it_approved_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    it_approved_campaign_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("validation_campaign.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    items: Mapped[list[UatChecklistItem]] = relationship(back_populates="session", cascade="all, delete-orphan")


class UatChecklistItem(Base):
    __tablename__ = "uat_checklist_item"
    __table_args__ = (
        UniqueConstraint("session_id", "item_code", name="uq_uat_item_session_code"),
        Index("ix_uat_item_status", "session_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("uat_session.id", ondelete="CASCADE"), nullable=False)
    item_code: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_TESTED", server_default="NOT_TESTED")
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    tester: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[UatSession] = relationship(back_populates="items")


class AdvisoryPilotActivation(Base):
    __tablename__ = "advisory_pilot_activation"
    __table_args__ = (
        Index(
            "ix_advisory_pilot_activation_status",
            "status",
            "activated_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    application_version: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    validation_campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("validation_campaign.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uat_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uat_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pharmacist_approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    it_approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    clinical_owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    technical_authorizer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    authorization_request_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shift_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shift_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )


class AdvisoryPilotSafetyControl(Base):
    __tablename__ = "advisory_pilot_safety_control"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    emergency_stop: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    ledger_quarantine: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    ledger_quarantine_reason: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    ledger_quarantined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ledger_detected_head_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    ledger_quarantine_cleared_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    ledger_quarantine_cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stop_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    stopped_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    restored_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    restored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AdvisoryPilotAuthorizationRequest(Base):
    __tablename__ = "advisory_pilot_authorization_request"
    __table_args__ = (
        Index(
            "ix_advisory_authorization_request_status",
            "status",
            "requested_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("validation_campaign.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uat_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uat_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pharmacist_approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    it_approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    request_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    technical_approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    technical_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clinical_approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    clinical_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handover_from_activation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("advisory_pilot_activation.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resulting_activation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("advisory_pilot_activation.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    handover_summary_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    handover_summary_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    unresolved_alerts: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    unresolved_critical_alerts: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    unresolved_interventions: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    outgoing_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    outgoing_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdvisoryPilotShiftCloseout(Base):
    __tablename__ = "advisory_pilot_shift_closeout"
    __table_args__ = (
        UniqueConstraint(
            "activation_id", name="uq_advisory_shift_closeout_activation"
        ),
        Index("ix_advisory_shift_closeout_closed", "closed_at", "closeout_type"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    activation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("advisory_pilot_activation.id", ondelete="RESTRICT"),
        nullable=False,
    )
    closeout_type: Mapped[str] = mapped_column(String(40), nullable=False)
    closed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    summary_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    unresolved_alerts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    unresolved_critical_alerts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    unresolved_interventions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    outgoing_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    outgoing_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    incoming_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    incoming_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handover_request_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "advisory_pilot_authorization_request.id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AdvisoryPilotSessionLedger(Base):
    __tablename__ = "advisory_pilot_session_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_pilot_session_ledger_event"),
        UniqueConstraint("entry_hash", name="uq_pilot_session_ledger_hash"),
        UniqueConstraint(
            "previous_hash", name="uq_pilot_session_ledger_previous"
        ),
        Index("ix_pilot_session_ledger_activation", "activation_id", "id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=new_uuid
    )
    activation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("advisory_pilot_activation.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PilotEvidenceVerification(Base):
    __tablename__ = "pilot_evidence_verification"
    __table_args__ = (
        Index(
            "ix_pilot_evidence_verification_time",
            "verified_at",
            "outcome",
        ),
        Index(
            "ix_pilot_evidence_verification_checksum",
            "package_checksum_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    package_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    package_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    manifest_format: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    application_version: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    schema_revision: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    ledger_head_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    ledger_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closeouts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    errors_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    verified_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
