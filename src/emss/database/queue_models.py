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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class ProcessingQueue(Base):
    __tablename__ = "processing_queue"
    __table_args__ = (
        Index(
            "ix_processing_queue_operational",
            "processing_status",
            "priority",
            "detected_at",
        ),
        Index(
            "ix_processing_queue_unit_review",
            "service_unit",
            "review_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    screening_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("screening.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    prescription_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("prescription.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_no_resep: Mapped[str] = mapped_column(String(80), nullable=False)
    revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_unit: Mapped[str | None] = mapped_column(String(150), nullable=True)
    care_setting: Mapped[str] = mapped_column(String(10), nullable=False, default='UNKNOWN', server_default='UNKNOWN')
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED", server_default="QUEUED"
    )
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEW", server_default="NEW"
    )
    risk_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="SAFE", server_default="SAFE"
    )
    completeness_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ERROR", server_default="ERROR"
    )
    overall_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ERROR", server_default="ERROR"
    )
    alert_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ERROR", server_default="ERROR"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    hold_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    alerts: Mapped[list[AlertEvent]] = relationship(
        back_populates="queue_item", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_event"
    __table_args__ = (
        Index("ix_alert_event_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    queue_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("processing_queue.id", ondelete="CASCADE"),
        nullable=False,
    )
    screening_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("screening.id", ondelete="CASCADE"),
        nullable=True,
    )
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEW", server_default="NEW"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    hold_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    shown_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    queue_item: Mapped[ProcessingQueue] = relationship(back_populates="alerts")
