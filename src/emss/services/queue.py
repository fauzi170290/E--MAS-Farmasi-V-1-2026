from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json
import re
from types import SimpleNamespace

from sqlalchemy import func, or_, select, true, false, update
from sqlalchemy.orm import selectinload

from emss.alerts import route_alert
from emss.alerts.notification import notification_decision
from emss.database.monitoring_models import MonitorEvent, MonitorInbox
from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, Role, UserRole
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.database.screening_models import (
    Prescription,
    PrescriptionRevision,
    Screening,
    ScreeningIssue,
    ScreeningPair,
)
from emss.utils.time import utc_now
from emss.services.longitudinal import decode_provenance


class QueueError(ValueError):
    pass


ALERT_SUPPRESSION_REASONS = frozenset(
    {
        "SILENT_PILOT",
        "ADVISORY_GATE_BLOCKED",
        "ADVISORY_GATE_UNAVAILABLE",
        "ADVISORY_NOT_ACTIVATED",
        "ADVISORY_AUTHORIZATION_EXPIRED",
        "ADVISORY_SHIFT_EXPIRED",
        "ADVISORY_LEDGER_QUARANTINED",
        "ADVISORY_EMERGENCY_STOP",
        "RUNTIME_GATE_BLOCKED",
    }
)


@dataclass(frozen=True)
class QueueItem:
    id: str
    screening_id: str | None
    no_resep: str
    revision_number: int | None
    patient_label: str
    service_unit: str
    processing_status: str
    review_status: str
    risk_status: str
    completeness_status: str
    overall_status: str
    alert_level: str
    priority: int
    hold_recommended: bool
    attempts: int
    error_message: str
    is_mock: bool
    detected_at: str
    care_setting: str = 'UNKNOWN'
    reviewed_at: str = ''
    reviewed_by: str = ''
    source_adapter: str = ''
    # A queue row is immutable evidence.  The normal queue shows only the
    # newest result for a prescription; History can deliberately show older
    # revisions without making them look actionable.
    is_effective: bool = True
    context_pending: bool = False


@dataclass(frozen=True)
class QueuePairDetail:
    pair_key: str
    classification: str
    severity: str
    recommendation: str
    provenance: dict | None = None


@dataclass(frozen=True)
class QueueIssueDetail:
    issue_type: str
    reference: str
    severity: str
    message: str
    display_name: str = ''


@dataclass(frozen=True)
class QueueDetail:
    item: QueueItem
    pairs: tuple[QueuePairDetail, ...]
    issues: tuple[QueueIssueDetail, ...]


@dataclass(frozen=True)
class QueueSummary:
    total: int
    new: int
    high_risk: int
    critical: int
    incomplete: int
    dead_letter: int


@dataclass(frozen=True)
class QueueEnqueueResult:
    item: QueueItem
    alert_id: str | None
    alert_title: str
    alert_message: str
    notify: bool
    persistent: bool
    reused: bool
    audio_category: str = ""
    audio_categories: tuple[str, ...] = ()

    @property
    def audio_only(self):
        return self.item.alert_level == 'AUDIO'


class ProcessingQueueService:
    def __init__(self, database: DatabaseManager, audit: AuditService, settings=None) -> None:
        self.database = database
        self.audit = audit
        self.settings = settings or database.settings

    def scope_predicate(self):
        if not self.settings.pharmacy_scope_required:
            return true()
        if self.settings.pharmacy_care_setting not in {'RALAN', 'RANAP'}:
            return false()
        return ProcessingQueue.care_setting == self.settings.pharmacy_care_setting

    def allows(self, care_setting):
        return not self.settings.pharmacy_scope_required or (
            self.settings.pharmacy_care_setting in {'RALAN', 'RANAP'} and
            care_setting == self.settings.pharmacy_care_setting)

    def pending_screening_ids(self, limit=50):
        detected_after, detected_before = self.operational_day_bounds()
        with self.database.session() as session:
            return tuple(session.scalars(select(AlertEvent.screening_id)
                .join(ProcessingQueue, ProcessingQueue.id == AlertEvent.queue_item_id)
                .where(self.scope_predicate())
                .where(ProcessingQueue.detected_at >= detected_after,
                    ProcessingQueue.detected_at < detected_before)
                .where(AlertEvent.status == 'NEW', AlertEvent.screening_id.is_not(None))
                .order_by(AlertEvent.created_at).limit(limit)).all())

    def enqueue_screening(self, screening_id: str) -> QueueEnqueueResult:
        with self.database.session() as session:
            screening = session.scalar(
                select(Screening)
                .options(
                    selectinload(Screening.revision).selectinload(
                        PrescriptionRevision.prescription
                    )
                )
                .where(Screening.id == screening_id)
            )
            if screening is None:
                raise QueueError("Hasil skrining tidak ditemukan")
            source_event = session.scalar(select(MonitorEvent).where(MonitorEvent.screening_id == screening_id))
            messages = self._issue_messages(session, screening.issues, source_event)
            notification_issues = [SimpleNamespace(issue_type=i.issue_type, message=messages.get(i.id, i.message))
                for i in screening.issues]
            care = json.loads(source_event.snapshot_json).get('header', {}).get('care_setting', 'UNKNOWN') if source_event else 'UNKNOWN'
            decision, audio_category = notification_decision(screening, screening.pairs,
                notification_issues, validated=bool(source_event and source_event.source_status in {'DIPROSES_FARMASI', 'DISERAHKAN'}),
                validated_high_only=bool(source_event and source_event.adapter_code in {'mysql', 'mysql_dummy'}))
            if not self.allows(care) or (source_event and source_event.event_type == 'SCOPE_INITIALIZED'):
                decision = replace(decision, notify=False, persistent=False)
            audio_categories = (audio_category,) if audio_category else ()
            if (audio_category != 'high-alert' and source_event
                    and source_event.source_status in {'DIPROSES_FARMASI', 'DISERAHKAN'}
                    and any(i.issue_type == 'HIGH_ALERT' for i in screening.issues)):
                audio_categories += ('high-alert',)
            existing = session.scalar(
                select(ProcessingQueue)
                .options(selectinload(ProcessingQueue.alerts))
                .where(ProcessingQueue.screening_id == screening_id)
            )
            if existing is not None:
                alert = existing.alerts[0] if existing.alerts else None
                return QueueEnqueueResult(
                    item=self._item(existing, source_event),
                    alert_id=alert.id if alert else None,
                    alert_title=decision.title if alert else "",
                    alert_message=decision.message if alert else "",
                    notify=bool(alert and alert.status == "NEW" and decision.notify and self.allows(existing.care_setting)),
                    persistent=existing.alert_level
                    in {"PERSISTENT", "CRITICAL", "ERROR"},
                    reused=True,
                    audio_category=audio_category,
                    audio_categories=audio_categories,
                )

            revision = screening.revision
            prescription = revision.prescription
            # A newer result supersedes only pending deliveries, never clinical
            # reviews/interventions or historical screening rows.
            obsolete_alert_ids = tuple(session.scalars(select(AlertEvent.id)
                .join(ProcessingQueue, AlertEvent.queue_item_id == ProcessingQueue.id)
                .where(ProcessingQueue.prescription_id == prescription.id,
                    ProcessingQueue.revision_number < revision.revision_number,
                    AlertEvent.status == "NEW")).all())
            if obsolete_alert_ids:
                session.execute(update(AlertEvent).where(AlertEvent.id.in_(obsolete_alert_ids))
                    .values(status="SUPPRESSED"))
            now = utc_now()
            row = ProcessingQueue(
                screening_id=screening.id,
                prescription_id=prescription.id,
                source_no_resep=prescription.source_no_resep,
                revision_number=revision.revision_number,
                patient_id=prescription.patient_id,
                patient_name=prescription.patient_name,
                service_unit=prescription.service_unit,
                care_setting=care,
                processing_status="COMPLETED",
                review_status=(
                    "NEW"
                    if decision.level not in {"NONE", "HISTORY"}
                    else "NO_REVIEW_REQUIRED"
                ),
                risk_status=screening.risk_status,
                completeness_status=screening.completeness_status,
                overall_status=screening.overall_status,
                alert_level=decision.level,
                priority=decision.priority,
                hold_recommended=decision.hold_recommended,
                attempts=1,
                is_mock=screening.is_mock,
                last_attempt_at=now,
                completed_at=now,
                detected_at=revision.captured_at,
            )
            session.add(row)
            session.flush()
            alert = None
            if decision.level != "NONE":
                alert = AlertEvent(
                    queue_item_id=row.id,
                    screening_id=screening.id,
                    level=decision.level,
                    status="NEW" if decision.notify else "SUPPRESSED",
                    title=decision.title,
                    message=decision.message,
                    hold_recommended=decision.hold_recommended,
                )
                session.add(alert)
                session.flush()
            self.audit.append(
                session,
                AuditEvent(
                    category="PROCESSING_QUEUE",
                    action="QUEUE_ITEM_CREATED",
                    outcome="SUCCESS",
                    entity_type="processing_queue",
                    entity_id=row.id,
                    details={
                        "screening_id": screening.id,
                        "no_resep": prescription.source_no_resep,
                        "risk_status": screening.risk_status,
                        "completeness_status": screening.completeness_status,
                        "alert_level": decision.level,
                        "is_mock": screening.is_mock,
                        "superseded_pending_alert_ids": obsolete_alert_ids,
                    },
                ),
            )
            session.commit()
            return QueueEnqueueResult(
                item=self._item(row, source_event),
                alert_id=alert.id if alert else None,
                alert_title=decision.title,
                alert_message=decision.message,
                notify=decision.notify,
                persistent=decision.persistent,
                reused=False,
                audio_category=audio_category,
                audio_categories=audio_categories,
            )

    def list_items(
        self,
        *,
        service_unit: str = "",
        status: str = "",
        search: str = "",
        detected_after: datetime | None = None,
        detected_before: datetime | None = None,
        include_history: bool = False,
        limit: int = 500,
    ) -> list[QueueItem]:
        if not include_history and detected_after is None and detected_before is None:
            detected_after, detected_before = self.operational_day_bounds()
        statement = select(ProcessingQueue).where(self.scope_predicate())
        if detected_after is not None:
            statement = statement.where(
                ProcessingQueue.detected_at >= self._as_utc(detected_after)
            )
        if detected_before is not None:
            statement = statement.where(
                ProcessingQueue.detected_at < self._as_utc(detected_before)
            )
        if service_unit:
            statement = statement.where(
                ProcessingQueue.service_unit == service_unit
            )
        if search.strip():
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    ProcessingQueue.source_no_resep.ilike(pattern),
                    ProcessingQueue.patient_id.ilike(pattern),
                    ProcessingQueue.patient_name.ilike(pattern),
                )
            )
        statement = statement.order_by(
            ProcessingQueue.priority.desc(), ProcessingQueue.detected_at.desc()
        )
        with self.database.session() as session:
            rows = session.scalars(statement).all()
            effective = self._effective_ids(rows)
            if not include_history:
                rows = [row for row in rows if row.id in effective]
            rows = [row for row in rows if self._matches_status(row, status)]
            rows = rows[:max(1, min(limit, 2000))]
            sources = self._sources(session, [row.screening_id for row in rows if row.screening_id])
            pending = self._context_pending_sources(session, sources.values())
            return [self._item(
                row,
                sources.get(row.screening_id),
                is_effective=row.id in effective,
                context_pending=(
                    bool(sources.get(row.screening_id))
                    and (sources[row.screening_id].adapter_code, sources[row.screening_id].no_resep) in pending
                ),
            ) for row in rows]

    @staticmethod
    def _effective_ids(rows: list[ProcessingQueue]) -> set[str]:
        """Choose the latest result per prescription without deleting history."""
        latest: dict[str, ProcessingQueue] = {}
        for row in rows:
            key = row.prescription_id or f"source:{row.source_no_resep}"
            previous = latest.get(key)
            rank = (row.revision_number if row.revision_number is not None else -1, row.detected_at, row.id)
            if previous is None or rank > (
                previous.revision_number if previous.revision_number is not None else -1,
                previous.detected_at,
                previous.id,
            ):
                latest[key] = row
        return {row.id for row in latest.values()}

    @staticmethod
    def _matches_status(row: ProcessingQueue, status: str) -> bool:
        if status == 'ATTENTION':
            return (
                row.risk_status in {'HIGH_RISK', 'CRITICAL', 'REVIEW'}
                or row.completeness_status != 'COMPLETE'
                or row.processing_status in {'FAILED', 'DEAD_LETTER'}
                or row.review_status == 'NEW'
            )
        return not status or status in {
            row.review_status, row.processing_status, row.overall_status,
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def operational_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
        local = (now or datetime.now().astimezone()).astimezone()
        start = datetime(local.year, local.month, local.day, tzinfo=local.tzinfo)
        return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)

    @staticmethod
    def _sources(session, screening_ids):
        if not screening_ids:
            return {}
        revisions = session.execute(select(Screening.id, PrescriptionRevision.prescription_id)
            .join(PrescriptionRevision, PrescriptionRevision.id == Screening.revision_id)
            .where(Screening.id.in_(screening_ids))).all()
        if not revisions:
            return {}
        events = session.execute(select(MonitorEvent, PrescriptionRevision.prescription_id)
            .join(Screening, Screening.id == MonitorEvent.screening_id)
            .join(PrescriptionRevision, PrescriptionRevision.id == Screening.revision_id)
            .where(PrescriptionRevision.prescription_id.in_({p for _, p in revisions}))
            .order_by(MonitorEvent.sequence)).all()
        by_prescription = {}
        identities = {}
        for event, prescription_id in events:
            identities.setdefault(prescription_id, set()).add((event.adapter_code, event.no_resep))
            by_prescription[prescription_id] = event
        return {screening_id: by_prescription[prescription_id]
            for screening_id, prescription_id in revisions
            if len(identities.get(prescription_id, ())) == 1}

    @staticmethod
    def _context_pending_sources(session, sources):
        keys = {(event.adapter_code, event.no_resep) for event in sources if event}
        if not keys:
            return set()
        adapters = {adapter for adapter, _number in keys}
        rows = session.scalars(select(MonitorInbox).where(
            MonitorInbox.adapter_code.in_(adapters),
            MonitorInbox.state == 'CONTEXT_PENDING',
        )).all()
        return {(row.adapter_code, row.no_resep) for row in rows if (row.adapter_code, row.no_resep) in keys}

    @staticmethod
    def _issue_messages(session, issues, source_event):
        return {}

    def list_units(self, *, detected_after=None, detected_before=None, include_history=False) -> tuple[str, ...]:
        if not include_history and detected_after is None and detected_before is None:
            detected_after, detected_before = self.operational_day_bounds()
        statement = (
            select(ProcessingQueue.service_unit)
            .where(self.scope_predicate())
            .where(ProcessingQueue.service_unit.is_not(None))
        )
        if detected_after is not None:
            statement = statement.where(ProcessingQueue.detected_at >= self._as_utc(detected_after))
        if detected_before is not None:
            statement = statement.where(ProcessingQueue.detected_at < self._as_utc(detected_before))
        with self.database.session() as session:
            values = session.scalars(
                statement.distinct().order_by(ProcessingQueue.service_unit)
            ).all()
            return tuple(value for value in values if value)

    def get_detail(self, queue_item_id: str) -> QueueDetail:
        with self.database.session() as session:
            row = session.get(ProcessingQueue, queue_item_id)
            if row is None or not self.allows(row.care_setting):
                raise QueueError("Item antrean tidak ditemukan")
            pairs: list[ScreeningPair] = []
            issues: list[ScreeningIssue] = []
            if row.screening_id:
                pairs = session.scalars(
                    select(ScreeningPair)
                    .where(ScreeningPair.screening_id == row.screening_id)
                    .order_by(
                        ScreeningPair.severity_rank.desc(),
                        ScreeningPair.pair_key,
                    )
                ).all()
                issues = session.scalars(
                    select(ScreeningIssue)
                    .where(ScreeningIssue.screening_id == row.screening_id)
                    .order_by(
                        ScreeningIssue.issue_type,
                        ScreeningIssue.pair_key,
                    )
                ).all()
            source_event = self._sources(session, [row.screening_id]).get(row.screening_id)
            pending = self._context_pending_sources(session, (source_event,))
            messages = self._issue_messages(session, issues, source_event)
            return QueueDetail(
                item=self._item(
                    row, source_event,
                    context_pending=bool(source_event and (source_event.adapter_code, source_event.no_resep) in pending),
                ),
                pairs=tuple(
                    QueuePairDetail(
                        pair_key=f"{pair.ingredient_low} || {pair.ingredient_high}",
                        classification=pair.classification,
                        severity=pair.severity_code
                        or pair.app_severity
                        or "NONE",
                        recommendation=pair.recommendation
                        or pair.clinical_effect
                        or "",
                        provenance=decode_provenance(pair.khanza_codes_json),
                    )
                    for pair in pairs
                ),
                issues=tuple(
                    QueueIssueDetail(
                        issue_type=issue.issue_type,
                        reference=issue.pair_key
                        or issue.khanza_code
                        or issue.display_name
                        or "",
                        severity=issue.app_severity or "KELENGKAPAN",
                        message=messages.get(issue.id, issue.message),
                        display_name=issue.display_name or '',
                    )
                    for issue in issues
                ),
            )

    def acknowledge(self, queue_item_id: str, actor_user_id: str) -> None:
        with self.database.session() as session:
            actor = session.get(AppUser, actor_user_id)
            role_codes = set(session.scalars(
                select(Role.code).join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == actor_user_id)
            ).all())
            if (actor is None or not actor.is_active or actor.normalized_username == 'mode.farmasi'
                    or not role_codes.intersection({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN'})):
                raise QueueError("Review hanya dapat dicatat oleh petugas klinis yang berwenang")
            row = session.get(ProcessingQueue, queue_item_id)
            if row is None or not self.allows(row.care_setting):
                raise QueueError("Item antrean tidak ditemukan")
            now = utc_now()
            related = session.scalars(select(ProcessingQueue).where(
                ProcessingQueue.prescription_id == row.prescription_id,
                ProcessingQueue.care_setting == row.care_setting,
                ProcessingQueue.revision_number <= (row.revision_number or 0),
                ProcessingQueue.review_status.in_({'NEW', 'NO_REVIEW_REQUIRED'}),
                self.scope_predicate(),
            )).all() if row.prescription_id else [row]
            if not related or (not row.prescription_id and row.review_status not in {'NEW', 'NO_REVIEW_REQUIRED'}):
                return
            related_ids = [item.id for item in related]
            for item in related:
                item.review_status = "REVIEWED"
                item.reviewed_by = actor_user_id
                item.reviewed_at = now
            alerts = session.scalars(
                select(AlertEvent).where(
                    AlertEvent.queue_item_id.in_(related_ids),
                    AlertEvent.status.in_(("NEW", "SHOWN")),
                )
            ).all()
            for alert in alerts:
                alert.status = "ACKNOWLEDGED"
                alert.acknowledged_by = actor_user_id
                alert.acknowledged_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="QUEUE_ITEM_REVIEWED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="processing_queue",
                    entity_id=row.id,
                    details={
                        "no_resep": row.source_no_resep,
                        "alert_level": row.alert_level,
                        "queue_items_reviewed": len(related_ids),
                        "through_revision": row.revision_number,
                        "care_setting": row.care_setting,
                        "clinical_intervention_created": False,
                    },
                ),
            )
            session.commit()

    def mark_alert_shown(self, alert_id: str) -> None:
        with self.database.session() as session:
            alert = session.get(AlertEvent, alert_id)
            if alert is None or alert.status != "NEW":
                return
            alert.status = "SHOWN"
            alert.shown_at = utc_now()
            session.commit()

    def mark_audio_outcome(self, alert_id: str, outcome: str) -> None:
        if outcome not in {'AUDIO_PLAYED', 'AUDIO_FAILED', 'AUDIO_INTERRUPTED'}:
            raise QueueError('Hasil audio tidak valid')
        with self.database.session() as session:
            alert = session.get(AlertEvent, alert_id)
            if alert is None or alert.status != 'NEW' or alert.level != 'AUDIO':
                return
            alert.status = outcome
            self.audit.append(session, AuditEvent(category='PROCESSING_QUEUE', action=outcome,
                outcome='SUCCESS' if outcome == 'AUDIO_PLAYED' else 'FAILURE', entity_type='alert_event', entity_id=alert.id,
                details={'speaker_heard_not_verified':True}))
            session.commit()

    def suppress_alert(self, alert_id: str, reason: str) -> bool:
        """Persist a mode/gate suppression so an alert cannot surface later."""
        if reason not in ALERT_SUPPRESSION_REASONS:
            raise QueueError("Alasan penahanan alert tidak valid")
        with self.database.session() as session:
            alert = session.get(AlertEvent, alert_id)
            if alert is None or alert.status != "NEW":
                return False
            alert.status = "SUPPRESSED"
            self.audit.append(
                session,
                AuditEvent(
                    category="PROCESSING_QUEUE",
                    action="ALERT_SUPPRESSED_BY_RUNTIME_MODE",
                    outcome="SUCCESS",
                    entity_type="alert_event",
                    entity_id=alert.id,
                    details={
                        "alert_level": alert.level,
                        "reason": reason,
                    },
                ),
            )
            session.commit()
            return True

    def record_failure(
        self,
        *,
        no_resep: str,
        service_unit: str = "",
        error_message: str,
        max_attempts: int = 3,
    ) -> str:
        now = utc_now()
        with self.database.session() as session:
            row = ProcessingQueue(
                source_no_resep=no_resep.strip() or "UNKNOWN",
                service_unit=service_unit.strip() or None,
                care_setting=(self.settings.pharmacy_care_setting or 'UNKNOWN'),
                processing_status="FAILED",
                review_status="NEW",
                risk_status="SAFE",
                completeness_status="ERROR",
                overall_status="ERROR",
                alert_level="ERROR",
                priority=110,
                attempts=1,
                max_attempts=max(1, max_attempts),
                error_message=error_message[:2000],
                last_attempt_at=now,
                detected_at=now,
            )
            session.add(row)
            session.flush()
            session.add(
                AlertEvent(
                    queue_item_id=row.id,
                    level="ERROR",
                    status="NEW",
                    title="Skrining gagal",
                    message=(
                        "Resep gagal diproses dan tidak boleh dinyatakan SAFE."
                    ),
                )
            )
            session.commit()
            return row.id

    def record_incomplete(
        self,
        *,
        no_resep: str,
        service_unit: str = "",
        message: str = "Resep belum stabil atau belum lengkap",
    ) -> str:
        now = utc_now()
        with self.database.session() as session:
            row = ProcessingQueue(
                source_no_resep=no_resep.strip() or "UNKNOWN",
                service_unit=service_unit.strip() or None,
                care_setting=(self.settings.pharmacy_care_setting or 'UNKNOWN'),
                processing_status="INCOMPLETE",
                review_status="NEW",
                risk_status="SAFE",
                completeness_status="INCOMPLETE",
                overall_status="INCOMPLETE",
                alert_level="PERSISTENT",
                priority=95,
                attempts=1,
                error_message=message[:2000],
                last_attempt_at=now,
                detected_at=now,
            )
            session.add(row)
            session.flush()
            session.add(
                AlertEvent(
                    queue_item_id=row.id,
                    level="PERSISTENT",
                    status="NEW",
                    title="Resep belum lengkap",
                    message="Resep belum stabil dan tidak boleh dinyatakan SAFE.",
                )
            )
            session.commit()
            return row.id

    def retry(self, queue_item_id: str, actor_user_id: str) -> str:
        with self.database.session() as session:
            actor = session.get(AppUser, actor_user_id)
            if actor is None:
                raise QueueError("Identitas petugas tidak ditemukan")
            row = session.get(ProcessingQueue, queue_item_id)
            if row is None or not self.allows(row.care_setting):
                raise QueueError("Item antrean tidak ditemukan")
            if row.processing_status not in {"FAILED", "DEAD_LETTER"}:
                raise QueueError("Hanya item gagal/dead-letter yang dapat di-retry")
            row.attempts += 1
            row.last_attempt_at = utc_now()
            row.processing_status = (
                "DEAD_LETTER"
                if row.attempts > row.max_attempts
                else "QUEUED"
            )
            row.error_message = (
                None
                if row.processing_status == "QUEUED"
                else row.error_message
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="PROCESSING_QUEUE",
                    action="QUEUE_RETRY_REQUESTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="processing_queue",
                    entity_id=row.id,
                    details={
                        "attempts": row.attempts,
                        "status": row.processing_status,
                    },
                ),
            )
            session.commit()
            return row.processing_status

    def summary(self, *, detected_after=None, detected_before=None, include_history=False) -> QueueSummary:
        rows = self.list_items(
            detected_after=detected_after,
            detected_before=detected_before,
            include_history=include_history,
            limit=2000,
        )
        return QueueSummary(
            total=len(rows),
            new=sum(row.review_status == 'NEW' for row in rows),
            high_risk=sum(row.risk_status == 'HIGH_RISK' for row in rows),
            critical=sum(row.risk_status == 'CRITICAL' for row in rows),
            incomplete=sum(row.completeness_status in {'NOT_ASSESSED', 'UNMAPPED', 'INCOMPLETE', 'ERROR'} for row in rows),
            dead_letter=sum(row.processing_status == 'DEAD_LETTER' for row in rows),
        )

    @staticmethod
    def _item(row: ProcessingQueue, source_event=None, *, is_effective=True, context_pending=False) -> QueueItem:
        patient_label = row.patient_name or row.patient_id or "—"
        return QueueItem(
            id=row.id,
            screening_id=row.screening_id,
            no_resep=source_event.no_resep if source_event else row.source_no_resep,
            revision_number=row.revision_number,
            patient_label=patient_label,
            service_unit=row.service_unit or "—",
            processing_status=row.processing_status,
            review_status=row.review_status,
            risk_status=row.risk_status,
            completeness_status=row.completeness_status,
            overall_status=row.overall_status,
            alert_level=row.alert_level,
            priority=row.priority,
            hold_recommended=row.hold_recommended,
            attempts=row.attempts,
            error_message=row.error_message or "",
            is_mock=row.is_mock,
            detected_at=row.detected_at.isoformat(timespec="seconds"),
            care_setting=row.care_setting,
            reviewed_at=(row.reviewed_at.isoformat(timespec="seconds") if row.reviewed_at else ''),
            reviewed_by=row.reviewed_by or '',
            source_adapter=source_event.adapter_code if source_event else '',
            is_effective=is_effective,
            context_pending=context_pending,
        )
