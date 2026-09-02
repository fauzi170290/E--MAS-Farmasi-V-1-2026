"""Durable read-only integration work. Clinical ledgers are never rewritten."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from emss.database.base import Base
from emss.database.models import new_uuid
from emss.utils.time import utc_now


class MonitorCheckpoint(Base):
    __tablename__ = 'monitor_checkpoint'
    adapter_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    lane: Mapped[str] = mapped_column(String(30), primary_key=True)
    cursor_key: Mapped[str] = mapped_column(String(80), default='')
    cursor_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycles: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MonitorInbox(Base):
    __tablename__ = 'monitor_inbox'
    __table_args__ = (Index('ix_monitor_inbox_due', 'adapter_code', 'next_attempt_at', 'priority'),)
    adapter_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    no_resep: Mapped[str] = mapped_column(String(80), primary_key=True)
    lane: Mapped[str] = mapped_column(String(30), default='HISTORY')
    priority: Mapped[int] = mapped_column(Integer, default=10)
    state: Mapped[str] = mapped_column(String(30), default='PENDING')
    fingerprint: Mapped[str] = mapped_column(String(64), default='')
    source_status: Mapped[str] = mapped_column(String(40), default='')
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    event_id: Mapped[str | None] = mapped_column(String(36))
    stable_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default='')
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    screening_id: Mapped[str | None] = mapped_column(String(36))


class MonitorEvent(Base):
    __tablename__ = 'monitor_event'
    __table_args__ = (Index('ix_monitor_event_source', 'adapter_code', 'no_resep', 'sequence', unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    adapter_code: Mapped[str] = mapped_column(String(30))
    no_resep: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_status: Mapped[str] = mapped_column(String(40))
    snapshot_json: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    state: Mapped[str] = mapped_column(String(30), default='OBSERVED')
    screening_id: Mapped[str | None] = mapped_column(String(36))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
