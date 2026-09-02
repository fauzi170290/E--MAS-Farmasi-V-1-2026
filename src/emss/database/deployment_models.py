from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class GoLiveAcceptanceSession(Base):
    __tablename__ = "go_live_acceptance_session"
    __table_args__ = (
        Index("ix_go_live_acceptance_status", "status", "created_at"),
        Index(
            "ix_go_live_acceptance_release",
            "application_version",
            "release_report_checksum_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    release_report_checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    installer_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    installer_checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    environment_label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="IN_PROGRESS", server_default="IN_PROGRESS"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
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
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class GoLiveAcceptanceItem(Base):
    __tablename__ = "go_live_acceptance_item"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "item_code", name="uq_go_live_acceptance_item_code"
        ),
        Index("ix_go_live_acceptance_item_status", "session_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("go_live_acceptance_session.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_code: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_TESTED", server_default="NOT_TESTED"
    )
    evidence_filename: Mapped[str | None] = mapped_column(String(260), nullable=True)
    evidence_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GoLiveDecisionLedger(Base):
    __tablename__ = "go_live_decision_ledger"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_go_live_decision_event"),
        UniqueConstraint("entry_hash", name="uq_go_live_decision_hash"),
        UniqueConstraint("previous_hash", name="uq_go_live_decision_previous"),
        Index("ix_go_live_decision_session", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=new_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("go_live_acceptance_session.id", ondelete="RESTRICT"),
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
