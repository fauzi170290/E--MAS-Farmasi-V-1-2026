from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from emss import __version__
from emss.audit.service import AuditEvent, AuditService
from emss.database.deployment_models import GoLiveAcceptanceSession
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole, new_uuid
from emss.database.rollout_models import (
    LimitedRolloutLedger,
    LimitedRolloutSession,
    LimitedRolloutWave,
)
from emss.services.go_live import GoLiveService
from emss.utils.time import utc_now


class LimitedRolloutError(ValueError):
    pass


class LimitedRolloutPermissionError(LimitedRolloutError):
    pass


@dataclass(frozen=True)
class RolloutSessionView:
    id: str
    acceptance_session_id: str
    application_version: str
    schema_revision: str
    scope_label: str
    max_workstations: int
    incident_halt_threshold: int
    critical_halt_threshold: int
    status: str
    expires_at: datetime
    clinical_attested_by: str | None
    technical_attested_by: str | None
    decided_by: str | None
    decision_reason: str


@dataclass(frozen=True)
class RolloutWaveView:
    id: str
    wave_number: int
    cohort_label: str
    planned_workstations: int
    status: str
    activated_at: datetime | None
    closed_at: datetime | None


@dataclass(frozen=True)
class RolloutReadiness:
    session: RolloutSessionView
    waves_completed: int
    waves_total: int
    incidents_total: int
    critical_incidents: int
    ledger_valid: bool
    operational_allowed: bool
    ready_for_completion: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class RolloutLedgerEntry:
    sequence: int
    event_id: str
    rollout_session_id: str
    wave_id: str | None
    event_type: str
    severity: str
    actor_user_id: str | None
    occurred_at: datetime
    payload_json: str
    previous_hash: str
    entry_hash: str


class LimitedRolloutService:
    LEDGER_GENESIS_HASH = "0" * 64
    AUTHORIZED_READERS = GoLiveService.AUTHORIZED_READERS
    TECHNICAL_ROLES = GoLiveService.TECHNICAL_ROLES
    CLINICAL_ROLES = GoLiveService.CLINICAL_ROLES
    DECISION_ROLES = GoLiveService.DECISION_ROLES
    HALT_ROLES = TECHNICAL_ROLES | CLINICAL_ROLES | DECISION_ROLES
    FINAL_STATUSES = frozenset({"COMPLETED", "ROLLED_BACK"})

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        go_live: GoLiveService,
    ) -> None:
        self.database = database
        self.audit = audit
        self.go_live = go_live

    def create_session(
        self,
        acceptance_session_id: str,
        scope_label: str,
        max_workstations: int,
        actor_user_id: str,
        *,
        validity_days: int = 7,
        incident_halt_threshold: int = 3,
        critical_halt_threshold: int = 1,
    ) -> RolloutSessionView:
        scope_label = scope_label.strip()
        if not 3 <= len(scope_label) <= 120:
            raise LimitedRolloutError("Label scope wajib 3-120 karakter")
        if not 1 <= max_workstations <= 500:
            raise LimitedRolloutError("Batas workstation wajib 1-500")
        if not 1 <= validity_days <= 30:
            raise LimitedRolloutError("Masa rollout wajib 1-30 hari")
        if not 1 <= incident_halt_threshold <= 50:
            raise LimitedRolloutError("Ambang insiden wajib 1-50")
        if not 1 <= critical_halt_threshold <= 5:
            raise LimitedRolloutError("Ambang CRITICAL wajib 1-5")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            self._assert_ledgers(session)
            acceptance = session.get(GoLiveAcceptanceSession, acceptance_session_id)
            if acceptance is None:
                raise LimitedRolloutError("Sesi acceptance tidak ditemukan")
            blockers = self._acceptance_blockers(acceptance)
            if blockers:
                raise LimitedRolloutError("Acceptance GO tidak valid: " + "; ".join(blockers))
            existing = session.scalar(
                select(LimitedRolloutSession).where(
                    LimitedRolloutSession.acceptance_session_id == acceptance_session_id,
                    LimitedRolloutSession.status.notin_(self.FINAL_STATUSES),
                )
            )
            if existing is not None:
                raise LimitedRolloutError("Acceptance sudah memiliki rollout yang belum final")
            now = utc_now()
            expiry = min(
                self._as_utc(acceptance.expires_at),
                now + timedelta(days=validity_days),
            )
            record = LimitedRolloutSession(
                acceptance_session_id=acceptance.id,
                application_version=acceptance.application_version,
                schema_revision=acceptance.schema_revision,
                scope_label=scope_label,
                max_workstations=max_workstations,
                incident_halt_threshold=incident_halt_threshold,
                critical_halt_threshold=critical_halt_threshold,
                status="PLANNED",
                expires_at=expiry,
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            self._append_ledger(
                session,
                record.id,
                None,
                "ROLLOUT_CREATED",
                "INFO",
                actor_user_id,
                {
                    "acceptance_session_id": acceptance.id,
                    "scope_label": scope_label,
                    "max_workstations": max_workstations,
                    "incident_halt_threshold": incident_halt_threshold,
                    "critical_halt_threshold": critical_halt_threshold,
                    "expires_at": AuditService._canonical_datetime(expiry),
                },
            )
            self._audit(session, record, "LIMITED_ROLLOUT_CREATED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def sessions(self, actor_user_id: str) -> tuple[RolloutSessionView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            rows = session.scalars(
                select(LimitedRolloutSession).order_by(LimitedRolloutSession.created_at.desc())
            ).all()
            return tuple(self._session_view(row) for row in rows)

    def waves(self, rollout_session_id: str, actor_user_id: str) -> tuple[RolloutWaveView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            self._get_session(session, rollout_session_id)
            rows = session.scalars(
                select(LimitedRolloutWave)
                .where(LimitedRolloutWave.rollout_session_id == rollout_session_id)
                .order_by(LimitedRolloutWave.wave_number)
            ).all()
            return tuple(self._wave_view(row) for row in rows)

    def add_wave(
        self,
        rollout_session_id: str,
        cohort_label: str,
        planned_workstations: int,
        actor_user_id: str,
    ) -> RolloutWaveView:
        cohort_label = cohort_label.strip()
        if not 3 <= len(cohort_label) <= 120:
            raise LimitedRolloutError("Label cohort wajib 3-120 karakter")
        if not 1 <= planned_workstations <= 500:
            raise LimitedRolloutError("Jumlah workstation wave wajib 1-500")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            record = self._get_session(session, rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status != "PLANNED":
                raise LimitedRolloutError("Wave hanya dapat ditambah saat rollout PLANNED")
            waves = self._waves(session, record.id)
            if sum(row.planned_workstations for row in waves) + planned_workstations > record.max_workstations:
                raise LimitedRolloutError("Total workstation wave melampaui batas rollout")
            wave = LimitedRolloutWave(
                rollout_session_id=record.id,
                wave_number=len(waves) + 1,
                cohort_label=cohort_label,
                planned_workstations=planned_workstations,
                status="PENDING",
                created_at=utc_now(),
            )
            session.add(wave)
            session.flush()
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, wave.id, "WAVE_ADDED", "INFO", actor_user_id, {
                "wave_number": wave.wave_number,
                "cohort_label": cohort_label,
                "planned_workstations": planned_workstations,
            })
            self._audit(session, record, "LIMITED_ROLLOUT_WAVE_ADDED", actor_user_id)
            session.commit()
            return self._wave_view(wave)

    def start(self, rollout_session_id: str, actor_user_id: str) -> RolloutSessionView:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            record = self._get_session(session, rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status != "PLANNED":
                raise LimitedRolloutError("Hanya rollout PLANNED yang dapat dimulai")
            if not self._waves(session, record.id):
                raise LimitedRolloutError("Minimal satu wave harus direncanakan")
            now = utc_now()
            record.status = "ACTIVE"
            record.started_by = actor_user_id
            record.started_at = now
            record.updated_at = now
            self._append_ledger(session, record.id, None, "ROLLOUT_STARTED", "INFO", actor_user_id, {})
            self._audit(session, record, "LIMITED_ROLLOUT_STARTED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def activate_wave(self, wave_id: str, actor_user_id: str) -> RolloutWaveView:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            wave = self._get_wave(session, wave_id)
            record = self._get_session(session, wave.rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status != "ACTIVE" or wave.status != "PENDING":
                raise LimitedRolloutError("Wave hanya dapat diaktifkan dari PENDING pada rollout ACTIVE")
            if any(row.status == "ACTIVE" for row in self._waves(session, record.id)):
                raise LimitedRolloutError("Masih ada wave aktif")
            now = utc_now()
            wave.status = "ACTIVE"
            wave.activated_by = actor_user_id
            wave.activated_at = now
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, wave.id, "WAVE_ACTIVATED", "INFO", actor_user_id, {
                "wave_number": wave.wave_number,
                "planned_workstations": wave.planned_workstations,
            })
            self._audit(session, record, "LIMITED_ROLLOUT_WAVE_ACTIVATED", actor_user_id)
            session.commit()
            return self._wave_view(wave)

    def complete_wave(self, wave_id: str, actor_user_id: str) -> RolloutWaveView:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            wave = self._get_wave(session, wave_id)
            record = self._get_session(session, wave.rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status != "ACTIVE" or wave.status != "ACTIVE":
                raise LimitedRolloutError("Hanya wave ACTIVE yang dapat diselesaikan")
            now = utc_now()
            wave.status = "COMPLETED"
            wave.closed_by = actor_user_id
            wave.closed_at = now
            self._revoke_attestations(record)
            self._append_ledger(session, record.id, wave.id, "WAVE_COMPLETED", "INFO", actor_user_id, {
                "wave_number": wave.wave_number,
            })
            self._audit(session, record, "LIMITED_ROLLOUT_WAVE_COMPLETED", actor_user_id)
            session.commit()
            return self._wave_view(wave)

    def pause(self, rollout_session_id: str, reason: str, actor_user_id: str, *, emergency: bool = False) -> RolloutSessionView:
        reason = self._validated_reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.HALT_ROLES)
            record = self._get_session(session, rollout_session_id)
            if record.status not in {"ACTIVE", "PAUSED", "HALTED"}:
                raise LimitedRolloutError("Rollout tidak berada pada status yang dapat dihentikan")
            if not self._verify_ledger_in_session(session):
                raise LimitedRolloutError("Ledger rollout tidak valid; operasi dikarantina")
            target = "HALTED" if emergency or record.status == "HALTED" else "PAUSED"
            record.status = target
            record.updated_at = utc_now()
            for wave in self._waves(session, record.id):
                if wave.status == "ACTIVE":
                    wave.status = target
            self._revoke_attestations(record)
            event = "EMERGENCY_HALT" if emergency else "ROLLOUT_PAUSED"
            self._append_ledger(session, record.id, None, event, "CRITICAL" if emergency else "WARNING", actor_user_id, {
                "reason_sha256": self._text_hash(reason),
            })
            self._audit(session, record, f"LIMITED_{event}", actor_user_id)
            session.commit()
            return self._session_view(record)

    def resume(self, rollout_session_id: str, reason: str, actor_user_id: str) -> RolloutSessionView:
        reason = self._validated_reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            record = self._get_session(session, rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status not in {"PAUSED", "HALTED"}:
                raise LimitedRolloutError("Hanya rollout PAUSED/HALTED yang dapat dilanjutkan")
            paused = [wave for wave in self._waves(session, record.id) if wave.status in {"PAUSED", "HALTED"}]
            if len(paused) > 1:
                raise LimitedRolloutError("State wave tidak konsisten; rollout tetap dihentikan")
            record.status = "ACTIVE"
            record.updated_at = utc_now()
            if paused:
                paused[0].status = "ACTIVE"
            self._append_ledger(session, record.id, paused[0].id if paused else None, "ROLLOUT_RESUMED", "WARNING", actor_user_id, {
                "reason_sha256": self._text_hash(reason),
            })
            self._audit(session, record, "LIMITED_ROLLOUT_RESUMED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def record_incident(
        self,
        rollout_session_id: str,
        severity: str,
        summary: str,
        actor_user_id: str,
        *,
        affected_workstations: int = 0,
    ) -> RolloutSessionView:
        severity = severity.strip().upper()
        summary = self._validated_reason(summary)
        if severity not in {"WARNING", "CRITICAL"}:
            raise LimitedRolloutError("Severity insiden harus WARNING atau CRITICAL")
        if not 0 <= affected_workstations <= 500:
            raise LimitedRolloutError("Jumlah workstation terdampak tidak valid")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.HALT_ROLES)
            record = self._get_session(session, rollout_session_id)
            if record.status not in {"ACTIVE", "PAUSED", "HALTED"}:
                raise LimitedRolloutError("Insiden hanya dapat dicatat pada rollout berjalan")
            if not self._verify_ledger_in_session(session):
                raise LimitedRolloutError("Ledger rollout tidak valid; operasi dikarantina")
            active_wave = next((wave for wave in self._waves(session, record.id) if wave.status == "ACTIVE"), None)
            self._append_ledger(session, record.id, active_wave.id if active_wave else None, "INCIDENT_RECORDED", severity, actor_user_id, {
                "summary_sha256": self._text_hash(summary),
                "affected_workstations": affected_workstations,
            })
            session.flush()
            incidents, critical = self._incident_counts(session, record.id)
            binding_blockers = self._binding_blockers(record, session)
            halt_reasons: list[str] = []
            if binding_blockers:
                halt_reasons.extend(binding_blockers)
            if incidents >= record.incident_halt_threshold:
                halt_reasons.append("Ambang total insiden tercapai")
            if critical >= record.critical_halt_threshold:
                halt_reasons.append("Ambang insiden CRITICAL tercapai")
            if halt_reasons:
                record.status = "HALTED"
                for wave in self._waves(session, record.id):
                    if wave.status == "ACTIVE":
                        wave.status = "HALTED"
                self._append_ledger(session, record.id, active_wave.id if active_wave else None, "AUTO_HALT", "CRITICAL", None, {
                    "reasons": sorted(halt_reasons),
                    "incidents_total": incidents,
                    "critical_incidents": critical,
                })
            self._revoke_attestations(record)
            record.updated_at = utc_now()
            self._audit(session, record, "LIMITED_ROLLOUT_INCIDENT_RECORDED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def attest(self, rollout_session_id: str, kind: str, actor_user_id: str) -> RolloutSessionView:
        kind = kind.strip().upper()
        if kind not in {"CLINICAL", "TECHNICAL"}:
            raise LimitedRolloutError("Jenis attestation harus CLINICAL atau TECHNICAL")
        allowed = self.CLINICAL_ROLES if kind == "CLINICAL" else self.TECHNICAL_ROLES
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, allowed)
            record = self._get_session(session, rollout_session_id)
            self._assert_ledgers(session)
            self._assert_binding(record, session)
            if record.status not in {"ACTIVE", "PAUSED"}:
                raise LimitedRolloutError("Rollout tidak siap untuk attestation closeout")
            waves = self._waves(session, record.id)
            if not waves or any(wave.status != "COMPLETED" for wave in waves):
                raise LimitedRolloutError("Seluruh wave wajib COMPLETED sebelum attestation")
            other = record.technical_attested_by if kind == "CLINICAL" else record.clinical_attested_by
            if other == actor_user_id:
                raise LimitedRolloutError("Attestor klinis dan teknis wajib berbeda")
            now = utc_now()
            if kind == "CLINICAL":
                record.clinical_attested_by = actor_user_id
                record.clinical_attested_at = now
            else:
                record.technical_attested_by = actor_user_id
                record.technical_attested_at = now
            self._append_ledger(session, record.id, None, f"{kind}_CLOSEOUT_ATTESTED", "INFO", actor_user_id, {})
            self._audit(session, record, f"LIMITED_ROLLOUT_{kind}_ATTESTED", actor_user_id)
            session.commit()
            return self._session_view(record)

    def decide(self, rollout_session_id: str, decision: str, reason: str, actor_user_id: str) -> RolloutSessionView:
        decision = decision.strip().upper()
        reason = self._validated_reason(reason)
        if decision not in {"COMPLETE", "ROLLBACK"}:
            raise LimitedRolloutError("Keputusan harus COMPLETE atau ROLLBACK")
        if decision == "COMPLETE":
            readiness = self.evaluate(rollout_session_id, actor_user_id)
            if not readiness.ready_for_completion:
                raise LimitedRolloutError("Completion ditolak: " + "; ".join(readiness.blockers))
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION_ROLES)
            record = self._get_session(session, rollout_session_id)
            if record.status in self.FINAL_STATUSES:
                raise LimitedRolloutError("Keputusan rollout sudah final dan immutable")
            if not self._verify_ledger_in_session(session):
                raise LimitedRolloutError("Ledger rollout tidak valid; operasi dikarantina")
            if decision == "COMPLETE" and actor_user_id in {record.clinical_attested_by, record.technical_attested_by}:
                raise LimitedRolloutError("Pengambil keputusan wajib independen dari attestor")
            now = utc_now()
            record.status = "COMPLETED" if decision == "COMPLETE" else "ROLLED_BACK"
            record.decided_by = actor_user_id
            record.decided_at = now
            record.decision_reason = reason
            record.updated_at = now
            if decision == "ROLLBACK":
                for wave in self._waves(session, record.id):
                    if wave.status != "COMPLETED":
                        wave.status = "ROLLED_BACK"
                        wave.closed_by = actor_user_id
                        wave.closed_at = now
            self._append_ledger(session, record.id, None, f"DECISION_{decision}", "WARNING" if decision == "ROLLBACK" else "INFO", actor_user_id, {
                "reason_sha256": self._text_hash(reason),
            })
            self._audit(session, record, f"LIMITED_ROLLOUT_DECISION_{decision}", actor_user_id)
            session.commit()
            return self._session_view(record)

    def evaluate(self, rollout_session_id: str, actor_user_id: str | None = None) -> RolloutReadiness:
        with self.database.session() as session:
            if actor_user_id is not None:
                self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            record = self._get_session(session, rollout_session_id)
            waves = self._waves(session, record.id)
            incidents, critical = self._incident_counts(session, record.id)
            ledger_valid = self._verify_ledger_in_session(session) and self.go_live._verify_ledger_in_session(session)
            blockers = self._binding_blockers(record, session)
            if not ledger_valid:
                blockers.append("Ledger keputusan/rollout tidak valid")
            if record.status in self.FINAL_STATUSES:
                blockers.append(f"Rollout sudah final: {record.status}")
            if record.status not in {"ACTIVE", "PAUSED"}:
                blockers.append("Rollout harus ACTIVE/PAUSED untuk closeout")
            if not waves:
                blockers.append("Belum ada wave rollout")
            if any(wave.status != "COMPLETED" for wave in waves):
                blockers.append("Belum seluruh wave COMPLETED")
            if record.clinical_attested_by is None:
                blockers.append("Attestation closeout klinis belum tersedia")
            if record.technical_attested_by is None:
                blockers.append("Attestation closeout teknis belum tersedia")
            if record.clinical_attested_by is not None and record.clinical_attested_by == record.technical_attested_by:
                blockers.append("Attestor klinis dan teknis tidak independen")
            operational = (
                ledger_valid
                and not self._binding_blockers(record, session)
                and record.status == "ACTIVE"
                and any(wave.status == "ACTIVE" for wave in waves)
            )
            return RolloutReadiness(
                session=self._session_view(record),
                waves_completed=sum(wave.status == "COMPLETED" for wave in waves),
                waves_total=len(waves),
                incidents_total=incidents,
                critical_incidents=critical,
                ledger_valid=ledger_valid,
                operational_allowed=operational,
                ready_for_completion=not blockers,
                blockers=tuple(blockers),
            )

    def operational_allowed(self, rollout_session_id: str) -> bool:
        return self.evaluate(rollout_session_id).operational_allowed

    def ledger(self, actor_user_id: str) -> tuple[RolloutLedgerEntry, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            if not self._verify_ledger_in_session(session):
                raise LimitedRolloutError("Ledger rollout tidak valid; operasi dikarantina")
            rows = session.scalars(select(LimitedRolloutLedger).order_by(LimitedRolloutLedger.id)).all()
            return tuple(self._ledger_view(row) for row in rows)

    def verify_ledger(self, actor_user_id: str) -> bool:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            return self._verify_ledger_in_session(session)

    def _acceptance_blockers(self, acceptance: GoLiveAcceptanceSession) -> list[str]:
        blockers: list[str] = []
        if acceptance.status != "GO":
            blockers.append("Keputusan acceptance bukan GO")
        if self._as_utc(acceptance.expires_at) <= utc_now():
            blockers.append("Acceptance GO telah kedaluwarsa")
        if acceptance.application_version != __version__:
            blockers.append("Acceptance bukan untuk versi aplikasi aktif")
        if acceptance.schema_revision != self.database.current_revision():
            blockers.append("Acceptance bukan untuk schema database aktif")
        return blockers

    def _binding_blockers(self, record: LimitedRolloutSession, session: Session) -> list[str]:
        blockers: list[str] = []
        acceptance = session.get(GoLiveAcceptanceSession, record.acceptance_session_id)
        if acceptance is None:
            return ["Acceptance terikat tidak ditemukan"]
        blockers.extend(self._acceptance_blockers(acceptance))
        if self._as_utc(record.expires_at) <= utc_now():
            blockers.append("Rollout telah kedaluwarsa")
        if record.application_version != acceptance.application_version or record.schema_revision != acceptance.schema_revision:
            blockers.append("Binding versi/schema rollout berubah")
        if not self.go_live._verify_ledger_in_session(session):
            blockers.append("Ledger keputusan go-live tidak valid")
        return blockers

    def _assert_binding(self, record: LimitedRolloutSession, session: Session) -> None:
        blockers = self._binding_blockers(record, session)
        if blockers:
            raise LimitedRolloutError("Rollout fail-closed: " + "; ".join(blockers))

    def _assert_ledgers(self, session: Session) -> None:
        if not self._verify_ledger_in_session(session) or not self.go_live._verify_ledger_in_session(session):
            raise LimitedRolloutError("Ledger keputusan/rollout tidak valid; operasi dikarantina")

    def _append_ledger(
        self,
        session: Session,
        rollout_session_id: str,
        wave_id: str | None,
        event_type: str,
        severity: str,
        actor_user_id: str | None,
        payload: dict[str, Any],
    ) -> LimitedRolloutLedger:
        previous = session.scalar(select(LimitedRolloutLedger).order_by(LimitedRolloutLedger.id.desc()).limit(1))
        previous_hash = previous.entry_hash if previous else self.LEDGER_GENESIS_HASH
        event_id = new_uuid()
        occurred_at = utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_payload = {
            "event_id": event_id,
            "rollout_session_id": rollout_session_id,
            "wave_id": wave_id,
            "event_type": event_type,
            "severity": severity,
            "actor_user_id": actor_user_id,
            "occurred_at": AuditService._canonical_datetime(occurred_at),
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        entry = LimitedRolloutLedger(
            event_id=event_id,
            rollout_session_id=rollout_session_id,
            wave_id=wave_id,
            event_type=event_type,
            severity=severity,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
            payload_json=payload_json,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        session.add(entry)
        session.flush()
        return entry

    def _verify_ledger_in_session(self, session: Session) -> bool:
        expected_previous = self.LEDGER_GENESIS_HASH
        rows = session.scalars(select(LimitedRolloutLedger).order_by(LimitedRolloutLedger.id)).all()
        for row in rows:
            if row.previous_hash != expected_previous:
                return False
            payload = {
                "event_id": row.event_id,
                "rollout_session_id": row.rollout_session_id,
                "wave_id": row.wave_id,
                "event_type": row.event_type,
                "severity": row.severity,
                "actor_user_id": row.actor_user_id,
                "occurred_at": AuditService._canonical_datetime(row.occurred_at),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    @staticmethod
    def _waves(session: Session, rollout_session_id: str) -> list[LimitedRolloutWave]:
        return list(session.scalars(select(LimitedRolloutWave).where(LimitedRolloutWave.rollout_session_id == rollout_session_id).order_by(LimitedRolloutWave.wave_number)).all())

    @staticmethod
    def _incident_counts(session: Session, rollout_session_id: str) -> tuple[int, int]:
        rows = session.scalars(select(LimitedRolloutLedger).where(LimitedRolloutLedger.rollout_session_id == rollout_session_id, LimitedRolloutLedger.event_type == "INCIDENT_RECORDED")).all()
        return len(rows), sum(row.severity == "CRITICAL" for row in rows)

    @staticmethod
    def _revoke_attestations(record: LimitedRolloutSession) -> None:
        record.clinical_attested_by = None
        record.clinical_attested_at = None
        record.technical_attested_by = None
        record.technical_attested_at = None
        record.updated_at = utc_now()

    def _audit(self, session: Session, record: LimitedRolloutSession, action: str, actor_user_id: str | None) -> None:
        self.audit.append(session, AuditEvent(
            category="LIMITED_ROLLOUT",
            action=action,
            outcome="SUCCESS",
            actor_user_id=actor_user_id,
            entity_type="LIMITED_ROLLOUT",
            entity_id=record.id,
            details={"status": record.status, "acceptance_session_id": record.acceptance_session_id},
        ))

    @staticmethod
    def _get_session(session: Session, rollout_session_id: str) -> LimitedRolloutSession:
        record = session.get(LimitedRolloutSession, rollout_session_id)
        if record is None:
            raise LimitedRolloutError("Sesi rollout tidak ditemukan")
        return record

    @staticmethod
    def _get_wave(session: Session, wave_id: str) -> LimitedRolloutWave:
        wave = session.get(LimitedRolloutWave, wave_id)
        if wave is None:
            raise LimitedRolloutError("Wave rollout tidak ditemukan")
        return wave

    @staticmethod
    def _validated_reason(value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 300:
            raise LimitedRolloutError("Alasan/ringkasan wajib 10-300 karakter")
        return value

    @staticmethod
    def _text_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _session_view(record: LimitedRolloutSession) -> RolloutSessionView:
        return RolloutSessionView(
            id=record.id,
            acceptance_session_id=record.acceptance_session_id,
            application_version=record.application_version,
            schema_revision=record.schema_revision,
            scope_label=record.scope_label,
            max_workstations=record.max_workstations,
            incident_halt_threshold=record.incident_halt_threshold,
            critical_halt_threshold=record.critical_halt_threshold,
            status=record.status,
            expires_at=record.expires_at,
            clinical_attested_by=record.clinical_attested_by,
            technical_attested_by=record.technical_attested_by,
            decided_by=record.decided_by,
            decision_reason=record.decision_reason or "",
        )

    @staticmethod
    def _wave_view(record: LimitedRolloutWave) -> RolloutWaveView:
        return RolloutWaveView(
            id=record.id,
            wave_number=record.wave_number,
            cohort_label=record.cohort_label,
            planned_workstations=record.planned_workstations,
            status=record.status,
            activated_at=record.activated_at,
            closed_at=record.closed_at,
        )

    @staticmethod
    def _ledger_view(record: LimitedRolloutLedger) -> RolloutLedgerEntry:
        return RolloutLedgerEntry(
            sequence=record.id,
            event_id=record.event_id,
            rollout_session_id=record.rollout_session_id,
            wave_id=record.wave_id,
            event_type=record.event_type,
            severity=record.severity,
            actor_user_id=record.actor_user_id,
            occurred_at=record.occurred_at,
            payload_json=record.payload_json,
            previous_hash=record.previous_hash,
            entry_hash=record.entry_hash,
        )

    @staticmethod
    def _require_roles(session: Session, actor_user_id: str, allowed: frozenset[str]) -> frozenset[str]:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active:
            raise LimitedRolloutPermissionError("Pengguna aktif tidak ditemukan")
        roles = frozenset(item.role.code for item in user.roles)
        if not roles.intersection(allowed):
            raise LimitedRolloutPermissionError("Role tidak berwenang untuk limited rollout")
        return roles
