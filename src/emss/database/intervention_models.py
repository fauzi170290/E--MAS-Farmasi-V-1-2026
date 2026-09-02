from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class PharmacistIntervention(Base):
    __tablename__ = "pharmacist_intervention"
    __table_args__ = (
        Index("ix_intervention_status_created", "status", "created_at"),
        Index(
            "ix_intervention_pharmacist",
            "pharmacist_user_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    queue_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("processing_queue.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    screening_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("screening.id", ondelete="SET NULL"), nullable=True
    )
    pharmacist_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OPEN", server_default="OPEN"
    )
    intervention_type: Mapped[str] = mapped_column(String(60), nullable=False)
    decision: Mapped[str] = mapped_column(String(60), nullable=False)
    communication_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    communication_result: Mapped[str | None] = mapped_column(String(60), nullable=True)
    contacted_party: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason_if_continued: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    details: Mapped[list[InterventionDetail]] = relationship(
        back_populates="intervention", cascade="all, delete-orphan"
    )


class InterventionDetail(Base):
    __tablename__ = "intervention_detail"
    __table_args__ = (
        Index("ix_intervention_detail_parent", "intervention_id", "finding_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    intervention_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pharmacist_intervention.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    intervention: Mapped[PharmacistIntervention] = relationship(
        back_populates="details"
    )
