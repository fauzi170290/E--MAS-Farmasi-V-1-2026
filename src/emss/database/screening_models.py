from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class Prescription(Base):
    __tablename__ = "prescription"
    __table_args__ = (
        Index("ix_prescription_source_updated", "source_no_resep", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_no_resep: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True
    )
    patient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_unit: Mapped[str | None] = mapped_column(String(150), nullable=True)
    prescriber_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_mock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    revisions: Mapped[list[PrescriptionRevision]] = relationship(
        back_populates="prescription", cascade="all, delete-orphan"
    )


class PrescriptionRevision(Base):
    __tablename__ = "prescription_revision"
    __table_args__ = (
        UniqueConstraint(
            "prescription_id",
            "prescription_hash",
            "knowledge_base_version_id",
            "is_mock",
            name="uq_prescription_revision_identity",
        ),
        UniqueConstraint(
            "prescription_id",
            "revision_number",
            name="uq_prescription_revision_number",
        ),
        Index(
            "ix_prescription_revision_hash_version",
            "prescription_hash",
            "knowledge_base_version_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    prescription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prescription.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prescription_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_mock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    source_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    prescription: Mapped[Prescription] = relationship(back_populates="revisions")
    items: Mapped[list[PrescriptionItem]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    screening: Mapped[Screening | None] = relationship(
        back_populates="revision", cascade="all, delete-orphan", uselist=False
    )


class PrescriptionItem(Base):
    __tablename__ = "prescription_item"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "source_item_key", name="uq_prescription_item_source"
        ),
        Index("ix_prescription_item_khanza_code", "khanza_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prescription_revision.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_item_key: Mapped[str] = mapped_column(String(100), nullable=False)
    khanza_code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(250), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    directions: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compound_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(30), nullable=False)
    active_ingredients_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )

    revision: Mapped[PrescriptionRevision] = relationship(back_populates="items")


class Screening(Base):
    __tablename__ = "screening"
    __table_args__ = (
        Index("ix_screening_status_completed", "overall_status", "completed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prescription_revision.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    knowledge_base_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    risk_status: Mapped[str] = mapped_column(String(30), nullable=False)
    completeness_status: Mapped[str] = mapped_column(String(30), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(30), nullable=False)
    highest_severity_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pair_count: Mapped[int] = mapped_column(Integer, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    assessed_no_interaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    not_assessed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmapped_drug_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_mock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    revision: Mapped[PrescriptionRevision] = relationship(
        back_populates="screening"
    )
    pairs: Mapped[list[ScreeningPair]] = relationship(
        back_populates="screening", cascade="all, delete-orphan"
    )
    issues: Mapped[list[ScreeningIssue]] = relationship(
        back_populates="screening", cascade="all, delete-orphan"
    )


class ScreeningPair(Base):
    __tablename__ = "screening_pair"
    __table_args__ = (
        UniqueConstraint(
            "screening_id", "pair_key", name="uq_screening_pair_key"
        ),
        Index("ix_screening_pair_classification", "classification"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    screening_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("screening.id", ondelete="CASCADE"),
        nullable=False,
    )
    pair_key: Mapped[str] = mapped_column(String(450), nullable=False)
    ingredient_low: Mapped[str] = mapped_column(String(200), nullable=False)
    ingredient_high: Mapped[str] = mapped_column(String(200), nullable=False)
    khanza_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    ddi_rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ddi_rule.id", ondelete="SET NULL"), nullable=True
    )
    severity_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    severity_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    app_severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    clinical_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_validation_status: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    screening: Mapped[Screening] = relationship(back_populates="pairs")


class ScreeningIssue(Base):
    __tablename__ = "screening_issue"
    __table_args__ = (
        Index("ix_screening_issue_type", "issue_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    screening_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("screening.id", ondelete="CASCADE"),
        nullable=False,
    )
    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)
    khanza_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    pair_key: Mapped[str | None] = mapped_column(String(450), nullable=True)
    app_severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    screening: Mapped[Screening] = relationship(back_populates="issues")
