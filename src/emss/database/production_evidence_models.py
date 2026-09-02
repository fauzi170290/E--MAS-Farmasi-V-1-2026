from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class ProductionEvidencePackageVerification(Base):
    __tablename__ = "production_evidence_package_verification"
    __table_args__ = (
        Index("ix_production_package_release", "release_record_id", "id"),
        Index("ix_production_package_status", "status", "verified_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid, unique=True)
    release_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("production_release_record.id", ondelete="RESTRICT"), nullable=False
    )
    package_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    package_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    verified_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProductionDeploymentCeremony(Base):
    __tablename__ = "production_deployment_ceremony"
    __table_args__ = (
        UniqueConstraint("release_record_id", name="uq_production_ceremony_release"),
        Index("ix_production_ceremony_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    release_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("production_release_record.id", ondelete="RESTRICT"), nullable=False
    )
    verification_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("production_evidence_package_verification.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OPEN", server_default="OPEN"
    )
    deployment_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deployment_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    technical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    technical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clinical_attested_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    clinical_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aborted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=True
    )
    aborted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abort_reason_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
