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


class ActiveIngredient(Base):
    __tablename__ = "active_ingredient"
    __table_args__ = (
        Index("uq_active_ingredient_kfa_bza_code", "kfa_bza_code", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    standard_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    kfa_bza_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kfa_validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_SET", server_default="NOT_SET"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
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


class DrugMaster(Base):
    __tablename__ = "drug_master"
    __table_args__ = (
        Index("ix_drug_master_normalized_name", "normalized_name"),
        Index(
            "ix_drug_master_mapping_review",
            "source_mapping_status",
            "review_status",
        ),
        Index("ix_drug_master_kfa_product", "kfa_product_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    khanza_code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    source_system: Mapped[str] = mapped_column(
        String(40), nullable=False, default="KHANZA", server_default="KHANZA"
    )
    kfa_product_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kfa_product_type: Mapped[str | None] = mapped_column(String(4), nullable=True)
    kfa_validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_SET", server_default="NOT_SET"
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_mapping_status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING_REVIEW"
    )
    mapping_method: Mapped[str] = mapped_column(String(100), nullable=False)
    mapping_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rx_row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    episode_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    name_variants_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    last_import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", ondelete="SET NULL"),
        nullable=True,
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

    aliases: Mapped[list[DrugAlias]] = relationship(
        back_populates="drug", cascade="all, delete-orphan"
    )
    components: Mapped[list[DrugComponentMapping]] = relationship(
        back_populates="drug", cascade="all, delete-orphan"
    )


class DrugAlias(Base):
    __tablename__ = "drug_alias"
    __table_args__ = (
        UniqueConstraint(
            "drug_id", "normalized_alias", name="uq_drug_alias_drug_normalized"
        ),
        Index("ix_drug_alias_normalized", "normalized_alias"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    drug_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("drug_master.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    is_preferred: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    drug: Mapped[DrugMaster] = relationship(back_populates="aliases")


class DrugComponentMapping(Base):
    __tablename__ = "drug_component_mapping"
    __table_args__ = (
        UniqueConstraint(
            "drug_id",
            "component_order",
            name="uq_drug_component_mapping_order",
        ),
        UniqueConstraint(
            "drug_id",
            "ingredient_id",
            name="uq_drug_component_mapping_ingredient",
        ),
        Index(
            "ix_drug_component_mapping_review",
            "review_status",
            "is_active",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    drug_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("drug_master.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("active_ingredient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    component_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_mapping_status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    mapping_method: Mapped[str] = mapped_column(String(100), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING_REVIEW"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    last_import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
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

    drug: Mapped[DrugMaster] = relationship(back_populates="components")
    ingredient: Mapped[ActiveIngredient] = relationship()


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        Index("ix_import_batch_status_created", "status", "created_at"),
        Index("ix_import_batch_checksum", "source_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    import_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    inserted_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    unchanged_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    summary_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    staging_rows: Mapped[list[ImportStagingRow]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class ImportStagingRow(Base):
    __tablename__ = "import_staging_row"
    __table_args__ = (
        Index(
            "ix_import_staging_batch_status",
            "batch_id",
            "validation_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    errors_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    proposed_action: Mapped[str] = mapped_column(String(20), nullable=False)

    batch: Mapped[ImportBatch] = relationship(back_populates="staging_rows")

