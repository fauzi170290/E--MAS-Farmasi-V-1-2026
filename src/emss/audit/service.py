from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from emss.database.models import AuditLog
from emss.utils.time import utc_now


@dataclass(frozen=True)
class AuditEvent:
    category: str
    action: str
    outcome: str
    actor_user_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class AuditService:
    GENESIS_HASH = "0" * 64

    @staticmethod
    def _canonical_datetime(value: datetime) -> str:
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return f"{value.isoformat(timespec='microseconds')}Z"

    def append(self, session: Session, event: AuditEvent) -> AuditLog:
        occurred_at = utc_now()
        details_json = json.dumps(
            event.details or {},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        previous = session.execute(
            select(AuditLog.entry_hash, AuditLog.occurred_at)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(1)
        ).one_or_none()
        previous_hash = previous.entry_hash if previous else self.GENESIS_HASH
        if previous is not None:
            previous_time = previous.occurred_at
            if previous_time.tzinfo is None:
                previous_time = previous_time.replace(tzinfo=UTC)
            else:
                previous_time = previous_time.astimezone(UTC)
            if occurred_at <= previous_time:
                occurred_at = previous_time + timedelta(microseconds=1)

        payload = {
            "occurred_at": self._canonical_datetime(occurred_at),
            "category": event.category,
            "action": event.action,
            "outcome": event.outcome,
            "actor_user_id": event.actor_user_id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "details_json": details_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        record = AuditLog(
            occurred_at=occurred_at,
            category=event.category,
            action=event.action,
            outcome=event.outcome,
            actor_user_id=event.actor_user_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            workstation=socket.gethostname(),
            correlation_id=event.correlation_id,
            details_json=details_json,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        session.add(record)
        session.flush()
        return record

    def verify_chain(self, session: Session) -> bool:
        rows = session.scalars(
            select(AuditLog).order_by(AuditLog.occurred_at, AuditLog.id)
        ).all()
        expected_previous = self.GENESIS_HASH
        for row in rows:
            if row.previous_hash != expected_previous:
                return False
            payload = {
                "occurred_at": self._canonical_datetime(row.occurred_at),
                "category": row.category,
                "action": row.action,
                "outcome": row.outcome,
                "actor_user_id": row.actor_user_id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "details_json": row.details_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(
                json.dumps(
                    payload,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True
