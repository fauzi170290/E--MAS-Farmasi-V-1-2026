from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
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


class KnowledgeBaseVersion(Base):
    __tablename__ = "knowledge_base_version"
    __table_args__ = (
        Index("ix_knowledge_base_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    based_on_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    rules: Mapped[list[DdiRule]] = relationship(
        back_populates="knowledge_version", cascade="all, delete-orphan"
    )


class KnowledgeBaseTransition(Base):
    __tablename__ = "knowledge_base_transition"
    __table_args__ = (
        Index("ix_kb_transition_version_time", "knowledge_base_version_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    knowledge_base_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class BundledDdiSeedApplication(Base):
    __tablename__ = "bundled_ddi_seed_application"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bundle_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    bundle_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_knowledge_checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    knowledge_base_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    ingredient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reused_ingredient_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    applied_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class DdiRule(Base):
    __tablename__ = "ddi_rule"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_version_id",
            "ingredient_low_id",
            "ingredient_high_id",
            name="uq_ddi_rule_version_canonical_pair",
        ),
        Index("ix_ddi_rule_pair_key", "pair_key"),
        Index(
            "ix_ddi_rule_version_status",
            "knowledge_base_version_id",
            "record_status",
        ),
        Index(
            "ix_ddi_rule_clinical_hold",
            "clinical_review_required",
            "clinical_review_resolved",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    knowledge_base_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_base_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_pair_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ingredient_low_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_ingredient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ingredient_high_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_ingredient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pair_key: Mapped[str] = mapped_column(String(450), nullable=False)
    interaction_status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity_code: Mapped[str] = mapped_column(String(30), nullable=False)
    severity_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    app_severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    clinical_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring: Mapped[str | None] = mapped_column(Text, nullable=True)
    population_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(250), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_accessed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_batch: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    source_validation_status: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    source_final_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activation_status: Mapped[str] = mapped_column(
        String(60), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    clinical_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    clinical_review_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    record_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    validated_by_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
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

    knowledge_version: Mapped[KnowledgeBaseVersion] = relationship(
        back_populates="rules"
    )
