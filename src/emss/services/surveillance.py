from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from emss import __version__
from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.integration_models import PollingRun
from emss.database.intervention_models import PharmacistIntervention
from emss.database.models import AppUser, UserRole, new_uuid
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.database.rollout_models import LimitedRolloutSession
from emss.database.surveillance_models import (
    EarlyLifeSurveillanceSession,
    SurveillanceIssue,
    SurveillanceLedger,
    SurveillanceSnapshot,
)
from emss.health.service import HealthService
from emss.services.limited_rollout import LimitedRolloutService
from emss.utils.time import utc_now


class SurveillanceError(ValueError):
    pass


class SurveillancePermissionError(SurveillanceError):
    pass


@dataclass(frozen=True)
class SurveillanceSessionView:
    id: str
    rollout_session_id: str
    application_version: str
    schema_revision: str
    environment_label: str
    minimum_snapshots: int
    minimum_observation_hours: int
    maximum_snapshot_age_hours: int
    status: str
    expires_at: datetime
    clinical_attested_by: str | None
    technical_attested_by: str | None
    decided_by: str | None
    decision_reason: str


@dataclass(frozen=True)
class SurveillanceSnapshotView:
    id: str
    prescriptions_total: int
    critical_total: int
    unacknowledged_critical_alerts: int
    open_interventions: int
    polling_failures: int
    health_state: str
    audit_chain_valid: bool
    captured_by: str
    captured_at: datetime


@dataclass(frozen=True)
class SurveillanceIssueView:
    id: str
    issue_number: int
    severity: str
    summary_hash_sha256: str
    status: str
    resolution_hash_sha256: str | None
    recorded_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class SurveillanceReadiness:
    session: SurveillanceSessionView
    snapshots_total: int
    observation_hours: float
    open_issues: int
    open_critical_issues: int
    ledger_valid: bool
    ready_for_promotion: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class SurveillanceLedgerEntry:
    sequence: int
    event_type: str
    actor_user_id: str | None
    occurred_at: datetime
    entry_hash: str


class SurveillanceService:
    LEDGER_GENESIS_HASH = "0" * 64
    AUTHORIZED_READERS = LimitedRolloutService.AUTHORIZED_READERS
    TECHNICAL_ROLES = LimitedRolloutService.TECHNICAL_ROLES
    CLINICAL_ROLES = LimitedRolloutService.CLINICAL_ROLES
    DECISION_ROLES = LimitedRolloutService.DECISION_ROLES
    ISSUE_ROLES = TECHNICAL_ROLES | CLINICAL_ROLES | DECISION_ROLES
    FINAL_STATUSES = frozenset({"PROMOTED", "ROLLED_BACK"})

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        health: HealthService,
        limited_rollout: LimitedRolloutService,
    ) -> None:
        self.database = database
        self.audit = audit
        self.health = health
        self.limited_rollout = limited_rollout

    def create_session(
        self,
        rollout_session_id: str,
        environment_label: str,
        actor_user_id: str,
        *,
        validity_days: int = 14,
        minimum_snapshots: int = 2,
        minimum_observation_hours: int = 24,
        maximum_snapshot_age_hours: int = 24,
    ) -> SurveillanceSessionView:
        environment_label = environment_label.strip()
        if not 3 <= len(environment_label) <= 120:
            raise SurveillanceError("Label environment wajib 3-120 karakter")
        if not 1 <= validity_days <= 30:
            raise SurveillanceError("Masa surveillance wajib 1-30 hari")
        if not 2 <= minimum_snapshots <= 30:
            raise SurveillanceError("Minimum snapshot wajib 2-30")
        if not 1 <= minimum_observation_hours <= 168:
            raise SurveillanceError("Minimum observasi wajib 1-168 jam")
        if not 1 <= maximum_snapshot_age_hours <= 72:
            raise SurveillanceError("Freshness snapshot wajib 1-72 jam")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            self._assert_ledgers(session)
            rollout = session.get(LimitedRolloutSession, rollout_session_id)
            if rollout is None:
                raise SurveillanceError("Limited rollout tidak ditemukan")
            blockers = self._upstream_blockers(rollout, session)
            if blockers:
                raise SurveillanceError("Rollout tidak valid: " + "; ".join(blockers))
            if session.scalar(
                select(EarlyLifeSurveillanceSession).where(
                    EarlyLifeSurveillanceSession.rollout_session_id == rollout.id
                )
            ) is not None:
                raise SurveillanceError("Rollout sudah memiliki sesi surveillance")
            now = utc_now()
            record = EarlyLifeSurveillanceSession(
                rollout_session_id=rollout.id,
                application_version=rollout.application_version,
                schema_revision=rollout.schema_revision,
                environment_label=environment_label,
                minimum_snapshots=minimum_snapshots,
                minimum_observation_hours=minimum_observation_hours,
                maximum_snapshot_age_hours=maximum_snapshot_age_hours,
                status="OBSERVING",
                expires_at=now + timedelta(days=validity_days),
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            self._append_ledger(session, record.id, "SURVEILLANCE_CREATED", actor_user_id, {
                "rollout_session_id": rollout.id,
                "minimum_snapshots": minimum_snapshots,
                "minimum_observation_hours": minimum_observation_hours,
                "maximum_snapshot_age_hours": maximum_snapshot_age_hours,
                "expires_at": AuditService._canonical_datetime(record.expires_at),
            })
            self._audit(session, record, "SURVEILLANCE_CREATED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def sessions(self, actor_user_id: str) -> tuple[SurveillanceSessionView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            rows = session.scalars(
                select(EarlyLifeSurveillanceSession).order_by(EarlyLifeSurveillanceSession.created_at.desc())
            ).all()
            return tuple(self._session_view(row) for row in rows)

    def snapshots(self, surveillance_session_id: str, actor_user_id: str) -> tuple[SurveillanceSnapshotView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            self._get_session(session, surveillance_session_id)
            rows = self._snapshots(session, surveillance_session_id)
            return tuple(self._snapshot_view(row) for row in rows)

    def issues(self, surveillance_session_id: str, actor_user_id: str) -> tuple[SurveillanceIssueView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            self._get_session(session, surveillance_session_id)
            rows = session.scalars(
                select(SurveillanceIssue)
                .where(SurveillanceIssue.surveillance_session_id == surveillance_session_id)
                .order_by(SurveillanceIssue.issue_number)
            ).all()
            return tuple(self._issue_view(row) for row in rows)

    def capture_snapshot(self, surveillance_session_id: str, actor_user_id: str) -> SurveillanceSnapshotView:
        health = self.health.check()
        now = utc_now()
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            record = self._get_session(session, surveillance_session_id)
            self._assert_open(record)
            self._assert_ledgers(session)
            self._assert_upstream(record, session)
            start = record.created_at
            prescriptions_total = int(session.scalar(
                select(func.count()).select_from(ProcessingQueue).where(
                    ProcessingQueue.is_mock.is_(False), ProcessingQueue.detected_at >= start
                )
            ) or 0)
            critical_total = int(session.scalar(
                select(func.count()).select_from(ProcessingQueue).where(
                    ProcessingQueue.is_mock.is_(False),
                    ProcessingQueue.detected_at >= start,
                    ProcessingQueue.risk_status == "CRITICAL",
                )
            ) or 0)
            unacknowledged = int(session.scalar(
                select(func.count()).select_from(AlertEvent)
                .join(ProcessingQueue, AlertEvent.queue_item_id == ProcessingQueue.id)
                .where(
                    ProcessingQueue.is_mock.is_(False),
                    AlertEvent.created_at >= start,
                    AlertEvent.level == "CRITICAL",
                    AlertEvent.acknowledged_at.is_(None),
                )
            ) or 0)
            open_interventions = int(session.scalar(
                select(func.count()).select_from(PharmacistIntervention)
                .join(ProcessingQueue, PharmacistIntervention.queue_item_id == ProcessingQueue.id)
                .where(
                    ProcessingQueue.is_mock.is_(False),
                    PharmacistIntervention.created_at >= start,
                    PharmacistIntervention.status != "COMPLETED",
                )
            ) or 0)
            polling_failures = int(session.scalar(
                select(func.count()).select_from(PollingRun).where(
                    PollingRun.started_at >= start,
                    (PollingRun.error_code.is_not(None)) | (PollingRun.failed_count > 0),
                )
            ) or 0)
            snapshot = SurveillanceSnapshot(
                surveillance_session_id=record.id,
                prescriptions_total=prescriptions_total,
                critical_total=critical_total,
                unacknowledged_critical_alerts=unacknowledged,
                open_interventions=open_interventions,
                polling_failures=polling_failures,
                health_state=health.state.value,
                audit_chain_valid=health.audit_chain_valid,
                captured_by=actor_user_id,
                captured_at=now,
            )
            session.add(snapshot)
            session.flush()
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, "SNAPSHOT_CAPTURED", actor_user_id, {
                "snapshot_id": snapshot.id,
                "prescriptions_total": prescriptions_total,
                "critical_total": critical_total,
                "unacknowledged_critical_alerts": unacknowledged,
                "open_interventions": open_interventions,
                "polling_failures": polling_failures,
                "health_state": snapshot.health_state,
                "audit_chain_valid": snapshot.audit_chain_valid,
            })
            self._audit(session, record, "SURVEILLANCE_SNAPSHOT_CAPTURED", actor_user_id)
            session.commit()
            return self._snapshot_view(snapshot)

    def record_issue(self, surveillance_session_id: str, severity: str, summary: str, actor_user_id: str) -> SurveillanceIssueView:
        severity = severity.strip().upper()
        summary = self._validated_text(summary)
        if severity not in {"WARNING", "CRITICAL"}:
            raise SurveillanceError("Severity isu harus WARNING atau CRITICAL")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.ISSUE_ROLES)
            record = self._get_session(session, surveillance_session_id)
            self._assert_open(record)
            self._assert_ledgers(session)
            count = int(session.scalar(
                select(func.count()).select_from(SurveillanceIssue).where(
                    SurveillanceIssue.surveillance_session_id == record.id
                )
            ) or 0)
            issue = SurveillanceIssue(
                surveillance_session_id=record.id,
                issue_number=count + 1,
                severity=severity,
                summary_hash_sha256=self._text_hash(summary),
                status="OPEN",
                recorded_by=actor_user_id,
                recorded_at=utc_now(),
            )
            session.add(issue)
            session.flush()
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, "ISSUE_RECORDED", actor_user_id, {
                "issue_number": issue.issue_number,
                "severity": severity,
                "summary_hash_sha256": issue.summary_hash_sha256,
            })
            self._audit(session, record, "SURVEILLANCE_ISSUE_RECORDED", actor_user_id)
            session.commit()
            return self._issue_view(issue)

    def close_issue(self, issue_id: str, resolution: str, actor_user_id: str) -> SurveillanceIssueView:
        resolution = self._validated_text(resolution)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.ISSUE_ROLES)
            issue = session.get(SurveillanceIssue, issue_id)
            if issue is None:
                raise SurveillanceError("Isu surveillance tidak ditemukan")
            record = self._get_session(session, issue.surveillance_session_id)
            self._assert_open(record)
            self._assert_ledgers(session)
            if issue.status == "CLOSED":
                raise SurveillanceError("Isu sudah CLOSED dan immutable")
            now = utc_now()
            issue.status = "CLOSED"
            issue.resolution_hash_sha256 = self._text_hash(resolution)
            issue.closed_by = actor_user_id
            issue.closed_at = now
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, "ISSUE_CLOSED", actor_user_id, {
                "issue_number": issue.issue_number,
                "resolution_hash_sha256": issue.resolution_hash_sha256,
            })
            self._audit(session, record, "SURVEILLANCE_ISSUE_CLOSED", actor_user_id)
            session.commit()
            return self._issue_view(issue)

    def attest(self, surveillance_session_id: str, kind: str, actor_user_id: str) -> SurveillanceSessionView:
        kind = kind.strip().upper()
        if kind not in {"CLINICAL", "TECHNICAL"}:
            raise SurveillanceError("Jenis attestation harus CLINICAL atau TECHNICAL")
        allowed = self.CLINICAL_ROLES if kind == "CLINICAL" else self.TECHNICAL_ROLES
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, allowed)
            record = self._get_session(session, surveillance_session_id)
            self._assert_open(record)
            blockers = self._evidence_blockers(record, session)
            if blockers:
                raise SurveillanceError("Attestation ditolak: " + "; ".join(blockers))
            other = record.technical_attested_by if kind == "CLINICAL" else record.clinical_attested_by
            if other == actor_user_id:
                raise SurveillanceError("Attestor klinis dan teknis wajib berbeda")
            now = utc_now()
            if kind == "CLINICAL":
                record.clinical_attested_by = actor_user_id
                record.clinical_attested_at = now
            else:
                record.technical_attested_by = actor_user_id
                record.technical_attested_at = now
            self._append_ledger(session, record.id, f"{kind}_ATTESTED", actor_user_id, {})
            self._audit(session, record, f"SURVEILLANCE_{kind}_ATTESTED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def evaluate(self, surveillance_session_id: str, actor_user_id: str | None = None) -> SurveillanceReadiness:
        with self.database.session() as session:
            if actor_user_id is not None:
                self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            record = self._get_session(session, surveillance_session_id)
            snapshots = self._snapshots(session, record.id)
            issues = session.scalars(select(SurveillanceIssue).where(
                SurveillanceIssue.surveillance_session_id == record.id
            )).all()
            ledger_valid = self._all_ledgers_valid(session)
            blockers = self._evidence_blockers(record, session)
            if record.status != "OBSERVING":
                blockers.append(f"Sesi sudah final: {record.status}")
            if record.clinical_attested_by is None:
                blockers.append("Attestation klinis belum tersedia")
            if record.technical_attested_by is None:
                blockers.append("Attestation teknis belum tersedia")
            if record.clinical_attested_by is not None and record.clinical_attested_by == record.technical_attested_by:
                blockers.append("Attestor klinis dan teknis tidak independen")
            observation_hours = self._observation_hours(snapshots)
            return SurveillanceReadiness(
                session=self._session_view(record),
                snapshots_total=len(snapshots),
                observation_hours=observation_hours,
                open_issues=sum(issue.status != "CLOSED" for issue in issues),
                open_critical_issues=sum(issue.status != "CLOSED" and issue.severity == "CRITICAL" for issue in issues),
                ledger_valid=ledger_valid,
                ready_for_promotion=not blockers,
                blockers=tuple(blockers),
            )

    def decide(self, surveillance_session_id: str, decision: str, reason: str, actor_user_id: str) -> SurveillanceSessionView:
        decision = decision.strip().upper()
        reason = self._validated_text(reason)
        if decision not in {"PROMOTE", "ROLLBACK"}:
            raise SurveillanceError("Keputusan harus PROMOTE atau ROLLBACK")
        if decision == "PROMOTE":
            readiness = self.evaluate(surveillance_session_id, actor_user_id)
            if not readiness.ready_for_promotion:
                raise SurveillanceError("Promotion ditolak: " + "; ".join(readiness.blockers))
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION_ROLES)
            record = self._get_session(session, surveillance_session_id)
            self._assert_open(record)
            if not self._verify_ledger_in_session(session):
                raise SurveillanceError("Ledger surveillance tidak valid")
            if decision == "PROMOTE" and actor_user_id in {record.clinical_attested_by, record.technical_attested_by}:
                raise SurveillanceError("Pengambil keputusan wajib independen dari attestor")
            now = utc_now()
            record.status = "PROMOTED" if decision == "PROMOTE" else "ROLLED_BACK"
            record.decided_by = actor_user_id
            record.decided_at = now
            record.decision_reason = reason
            record.updated_at = now
            self._append_ledger(session, record.id, f"DECISION_{decision}", actor_user_id, {
                "reason_hash_sha256": self._text_hash(reason)
            })
            self._audit(session, record, f"SURVEILLANCE_DECISION_{decision}", actor_user_id)
            session.commit()
            return self._session_view(record)

    def ledger(self, actor_user_id: str) -> tuple[SurveillanceLedgerEntry, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            if not self._verify_ledger_in_session(session):
                raise SurveillanceError("Ledger surveillance tidak valid")
            rows = session.scalars(select(SurveillanceLedger).order_by(SurveillanceLedger.id)).all()
            return tuple(SurveillanceLedgerEntry(row.id, row.event_type, row.actor_user_id, row.occurred_at, row.entry_hash) for row in rows)

    def _evidence_blockers(self, record: EarlyLifeSurveillanceSession, session: Session) -> list[str]:
        blockers = self._upstream_for_session(record, session)
        if self._as_utc(record.expires_at) <= utc_now():
            blockers.append("Sesi surveillance telah kedaluwarsa")
        if not self._all_ledgers_valid(session):
            blockers.append("Ledger upstream/surveillance tidak valid")
        snapshots = self._snapshots(session, record.id)
        if len(snapshots) < record.minimum_snapshots:
            blockers.append(f"Snapshot belum cukup: {len(snapshots)}/{record.minimum_snapshots}")
        if self._observation_hours(snapshots) < record.minimum_observation_hours:
            blockers.append("Rentang observasi minimum belum terpenuhi")
        if snapshots:
            latest = snapshots[-1]
            if self._as_utc(latest.captured_at) < utc_now() - timedelta(hours=record.maximum_snapshot_age_hours):
                blockers.append("Snapshot terbaru sudah basi")
            if latest.prescriptions_total <= 0:
                blockers.append("Belum ada resep non-MOCK dalam observasi")
            if latest.health_state != "READY" or not latest.audit_chain_valid:
                blockers.append("Health/audit snapshot terbaru tidak READY")
            if latest.unacknowledged_critical_alerts > 0:
                blockers.append("Masih ada alert CRITICAL belum diakui")
            if latest.open_interventions > 0:
                blockers.append("Masih ada intervensi terbuka")
            if latest.polling_failures > 0:
                blockers.append("Masih ada kegagalan polling dalam periode observasi")
        open_issues = session.scalars(select(SurveillanceIssue).where(
            SurveillanceIssue.surveillance_session_id == record.id,
            SurveillanceIssue.status != "CLOSED",
        )).all()
        if open_issues:
            blockers.append("Masih ada isu surveillance terbuka")
        return blockers

    def _upstream_blockers(self, rollout: LimitedRolloutSession, session: Session) -> list[str]:
        blockers: list[str] = []
        if rollout.status != "COMPLETED":
            blockers.append("Limited rollout belum COMPLETED")
        if rollout.application_version != __version__:
            blockers.append("Rollout bukan untuk versi aplikasi aktif")
        if rollout.schema_revision != self.database.current_revision():
            blockers.append("Rollout bukan untuk schema aktif")
        if not self.limited_rollout._verify_ledger_in_session(session):
            blockers.append("Ledger limited rollout tidak valid")
        if not self.limited_rollout.go_live._verify_ledger_in_session(session):
            blockers.append("Ledger go-live tidak valid")
        return blockers

    def _upstream_for_session(self, record: EarlyLifeSurveillanceSession, session: Session) -> list[str]:
        rollout = session.get(LimitedRolloutSession, record.rollout_session_id)
        if rollout is None:
            return ["Limited rollout terikat tidak ditemukan"]
        blockers = self._upstream_blockers(rollout, session)
        if record.application_version != rollout.application_version or record.schema_revision != rollout.schema_revision:
            blockers.append("Binding surveillance berubah")
        return blockers

    def _assert_upstream(self, record: EarlyLifeSurveillanceSession, session: Session) -> None:
        blockers = self._upstream_for_session(record, session)
        if blockers:
            raise SurveillanceError("Surveillance fail-closed: " + "; ".join(blockers))

    def _all_ledgers_valid(self, session: Session) -> bool:
        return (
            self._verify_ledger_in_session(session)
            and self.limited_rollout._verify_ledger_in_session(session)
            and self.limited_rollout.go_live._verify_ledger_in_session(session)
        )

    def _assert_ledgers(self, session: Session) -> None:
        if not self._all_ledgers_valid(session):
            raise SurveillanceError("Ledger upstream/surveillance tidak valid")

    def _append_ledger(self, session: Session, surveillance_session_id: str, event_type: str, actor_user_id: str | None, payload: dict[str, Any]) -> None:
        previous = session.scalar(select(SurveillanceLedger).order_by(SurveillanceLedger.id.desc()).limit(1))
        previous_hash = previous.entry_hash if previous else self.LEDGER_GENESIS_HASH
        event_id = new_uuid()
        occurred_at = utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_payload = {
            "event_id": event_id,
            "surveillance_session_id": surveillance_session_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "occurred_at": AuditService._canonical_datetime(occurred_at),
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        session.add(SurveillanceLedger(
            event_id=event_id,
            surveillance_session_id=surveillance_session_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
            payload_json=payload_json,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        ))
        session.flush()

    def _verify_ledger_in_session(self, session: Session) -> bool:
        expected_previous = self.LEDGER_GENESIS_HASH
        rows = session.scalars(select(SurveillanceLedger).order_by(SurveillanceLedger.id)).all()
        for row in rows:
            payload = {
                "event_id": row.event_id,
                "surveillance_session_id": row.surveillance_session_id,
                "event_type": row.event_type,
                "actor_user_id": row.actor_user_id,
                "occurred_at": AuditService._canonical_datetime(row.occurred_at),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if row.previous_hash != expected_previous or row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    @staticmethod
    def _snapshots(session: Session, surveillance_session_id: str) -> list[SurveillanceSnapshot]:
        return list(session.scalars(select(SurveillanceSnapshot).where(
            SurveillanceSnapshot.surveillance_session_id == surveillance_session_id
        ).order_by(SurveillanceSnapshot.captured_at, SurveillanceSnapshot.id)).all())

    @staticmethod
    def _observation_hours(snapshots: list[SurveillanceSnapshot]) -> float:
        if len(snapshots) < 2:
            return 0.0
        first = SurveillanceService._as_utc(snapshots[0].captured_at)
        last = SurveillanceService._as_utc(snapshots[-1].captured_at)
        return max(0.0, (last - first).total_seconds() / 3600)

    @staticmethod
    def _revoke_attestations(record: EarlyLifeSurveillanceSession) -> None:
        record.clinical_attested_by = None
        record.clinical_attested_at = None
        record.technical_attested_by = None
        record.technical_attested_at = None
        record.updated_at = utc_now()

    def _audit(self, session: Session, record: EarlyLifeSurveillanceSession, action: str, actor_user_id: str | None) -> None:
        self.audit.append(session, AuditEvent(
            category="SURVEILLANCE", action=action, outcome="SUCCESS",
            actor_user_id=actor_user_id, entity_type="SURVEILLANCE", entity_id=record.id,
            details={"status": record.status, "rollout_session_id": record.rollout_session_id},
        ))

    @staticmethod
    def _get_session(session: Session, surveillance_session_id: str) -> EarlyLifeSurveillanceSession:
        record = session.get(EarlyLifeSurveillanceSession, surveillance_session_id)
        if record is None:
            raise SurveillanceError("Sesi surveillance tidak ditemukan")
        return record

    @staticmethod
    def _assert_open(record: EarlyLifeSurveillanceSession) -> None:
        if record.status != "OBSERVING":
            raise SurveillanceError("Keputusan surveillance sudah final dan immutable")
        if SurveillanceService._as_utc(record.expires_at) <= utc_now():
            raise SurveillanceError("Sesi surveillance telah kedaluwarsa")

    @staticmethod
    def _validated_text(value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 300:
            raise SurveillanceError("Ringkasan/alasan wajib 10-300 karakter")
        return value

    @staticmethod
    def _text_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _session_view(row: EarlyLifeSurveillanceSession) -> SurveillanceSessionView:
        return SurveillanceSessionView(
            row.id, row.rollout_session_id, row.application_version, row.schema_revision,
            row.environment_label, row.minimum_snapshots, row.minimum_observation_hours,
            row.maximum_snapshot_age_hours, row.status, row.expires_at,
            row.clinical_attested_by, row.technical_attested_by, row.decided_by,
            row.decision_reason or "",
        )

    @staticmethod
    def _snapshot_view(row: SurveillanceSnapshot) -> SurveillanceSnapshotView:
        return SurveillanceSnapshotView(
            row.id, row.prescriptions_total, row.critical_total,
            row.unacknowledged_critical_alerts, row.open_interventions,
            row.polling_failures, row.health_state, row.audit_chain_valid,
            row.captured_by, row.captured_at,
        )

    @staticmethod
    def _issue_view(row: SurveillanceIssue) -> SurveillanceIssueView:
        return SurveillanceIssueView(
            row.id, row.issue_number, row.severity, row.summary_hash_sha256,
            row.status, row.resolution_hash_sha256, row.recorded_at, row.closed_at,
        )

    @staticmethod
    def _require_roles(session: Session, actor_user_id: str, allowed: frozenset[str]) -> None:
        user = session.scalar(
            select(AppUser).options(selectinload(AppUser.roles).selectinload(UserRole.role)).where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active:
            raise SurveillancePermissionError("Pengguna aktif tidak ditemukan")
        if not frozenset(item.role.code for item in user.roles).intersection(allowed):
            raise SurveillancePermissionError("Role tidak berwenang untuk surveillance")
