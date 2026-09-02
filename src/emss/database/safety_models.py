from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class MedicationSafetyPolicy(Base):
    __tablename__ = "medication_safety_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    polypharmacy_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    hyperpolypharmacy_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class IngredientTherapyProfile(Base):
    __tablename__ = "ingredient_therapy_profile"
    __table_args__ = (Index("ix_therapy_profile_class", "therapeutic_class", "is_active"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    ingredient_id: Mapped[str] = mapped_column(String(36), ForeignKey("active_ingredient.id", ondelete="CASCADE"), nullable=False, unique=True)
    therapeutic_class: Mapped[str] = mapped_column(String(160), nullable=False)
    therapeutic_subclass: Mapped[str | None] = mapped_column(String(160), nullable=True)
    atc_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    route_context: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(250), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class HighAlertMedication(Base):
    __tablename__ = "high_alert_medication"
    __table_args__ = (
        UniqueConstraint("drug_id", "unit_scope", name="uq_high_alert_drug_unit"),
        Index("ix_high_alert_active_unit", "is_active", "unit_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    drug_id: Mapped[str] = mapped_column(String(36), ForeignKey("drug_master.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_scope: Mapped[str] = mapped_column(String(150), nullable=False, default="*", server_default="*")
    app_severity: Mapped[str] = mapped_column(String(30), nullable=False, default="REVIEW", server_default="REVIEW")
    requires_double_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class LasaPair(Base):
    __tablename__ = "lasa_pair"
    __table_args__ = (
        UniqueConstraint("drug_low_id", "drug_high_id", "lasa_type", "unit_scope", name="uq_lasa_pair_type_unit"),
        Index("ix_lasa_active_unit", "is_active", "unit_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    drug_low_id: Mapped[str] = mapped_column(String(36), ForeignKey("drug_master.id", ondelete="CASCADE"), nullable=False)
    drug_high_id: Mapped[str] = mapped_column(String(36), ForeignKey("drug_master.id", ondelete="CASCADE"), nullable=False)
    lasa_type: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_scope: Mapped[str] = mapped_column(String(150), nullable=False, default="*", server_default="*")
    app_severity: Mapped[str] = mapped_column(String(30), nullable=False, default="REVIEW", server_default="REVIEW")
    requires_double_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
