from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from emss import __version__
from emss.audit.service import AuditEvent, AuditService
from emss.database.deployment_models import (
    GoLiveAcceptanceItem,
    GoLiveAcceptanceSession,
    GoLiveDecisionLedger,
)
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole, new_uuid
from emss.utils.time import utc_now


class GoLiveError(ValueError):
    pass


class GoLivePermissionError(GoLiveError):
    pass


@dataclass(frozen=True)
class GoLiveItemView:
    id: str
    item_code: str
    category: str
    description: str
    owner_type: str
    status: str
    evidence_filename: str | None
    evidence_checksum_sha256: str | None
    notes: str
    tested_by: str | None
    tested_at: datetime | None


@dataclass(frozen=True)
class GoLiveSessionView:
    id: str
    application_version: str
    schema_revision: str
    environment_label: str
    status: str
    expires_at: datetime
    release_report_checksum_sha256: str
    installer_filename: str
    installer_checksum_sha256: str
    clinical_attested_by: str | None
    clinical_attested_at: datetime | None
    technical_attested_by: str | None
    technical_attested_at: datetime | None
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str


@dataclass(frozen=True)
class GoLiveReadiness:
    session: GoLiveSessionView
    items_passed: int
    items_total: int
    ledger_valid: bool
    ready_for_go_decision: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class GoLiveLedgerEntry:
    sequence: int
    event_id: str
    session_id: str
    event_type: str
    actor_user_id: str | None
    occurred_at: datetime
    payload_json: str
    previous_hash: str
    entry_hash: str


@dataclass(frozen=True)
class _ReleaseBinding:
    report_checksum_sha256: str
    application_version: str
    schema_revision: str
    installer_checksum_sha256: str
    installer_filename: str


DEFAULT_GO_LIVE_ITEMS = (
    (
        "TECH-CLEAN-INSTALL",
        "Deployment",
        "Clean install dan health smoke pada Windows 64-bit bersih",
        "TECHNICAL",
    ),
    (
        "TECH-UPGRADE-DATA",
        "Data lifecycle",
        "Upgrade mempertahankan database, konfigurasi, dan backup ProgramData",
        "TECHNICAL",
    ),
    (
        "TECH-UNINSTALL-DATA",
        "Data lifecycle",
        "Uninstall tidak menghapus database dan backup ProgramData",
        "TECHNICAL",
    ),
    (
        "TECH-ROLLBACK",
        "Recovery",
        "Restore dan rollback drill pada staging representatif berhasil",
        "TECHNICAL",
    ),
    (
        "TECH-SIGNING",
        "Supply chain",
        "Kebijakan Authenticode dipenuhi atau pengecualian formal disetujui",
        "TECHNICAL",
    ),
    (
        "CLIN-UAT",
        "Clinical acceptance",
        "UAT klinis untuk versi rilis selesai tanpa blocker terbuka",
        "CLINICAL",
    ),
    (
        "CLIN-ALERT-FATIGUE",
        "Clinical acceptance",
        "Alert-fatigue review dan threshold operasional disetujui",
        "CLINICAL",
    ),
    (
        "CLIN-SOP-TRAINING",
        "Operational readiness",
        "SOP, pelatihan, downtime, dan eskalasi insiden ditandatangani",
        "CLINICAL",
    ),
)


class GoLiveService:
    LEDGER_GENESIS_HASH = "0" * 64
    AUTHORIZED_READERS = frozenset(
        {
            "SUPER_ADMIN",
            "IT_ADMIN",
            "CLINICAL_REVIEWER",
            "APOTEKER",
            "KFT",
            "KEPALA_INSTALASI",
            "PMKP",
            "DIREKTUR",
        }
    )
    TECHNICAL_ROLES = frozenset({"SUPER_ADMIN", "IT_ADMIN"})
    CLINICAL_ROLES = frozenset(
        {"CLINICAL_REVIEWER", "APOTEKER", "KFT", "KEPALA_INSTALASI"}
    )
    DECISION_ROLES = frozenset({"SUPER_ADMIN", "DIREKTUR"})
    ITEM_STATUSES = frozenset({"NOT_TESTED", "PASS", "FAIL", "BLOCKED"})

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def create_session(
        self,
        release_report_path: Path | str,
        installer_path: Path | str,
        environment_label: str,
        actor_user_id: str,
        validity_days: int = 7,
    ) -> GoLiveSessionView:
        environment_label = environment_label.strip()
        if not 3 <= len(environment_label) <= 120:
            raise GoLiveError("Label environment wajib 3-120 karakter")
        if not 1 <= validity_days <= 30:
            raise GoLiveError("Masa acceptance wajib 1-30 hari")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            if not self._verify_ledger_in_session(session):
                raise GoLiveError("Ledger keputusan go-live tidak valid")
            binding = self._inspect_release_binding(
                release_report_path, installer_path
            )
            current_schema = self.database.current_revision()
            if binding.application_version != __version__:
                raise GoLiveError("Release report bukan untuk versi aplikasi aktif")
            if binding.schema_revision != current_schema:
                raise GoLiveError("Release report bukan untuk schema database aktif")
            now = utc_now()
            existing = session.scalar(
                select(GoLiveAcceptanceSession).where(
                    GoLiveAcceptanceSession.status == "IN_PROGRESS",
                    GoLiveAcceptanceSession.application_version == __version__,
                    GoLiveAcceptanceSession.expires_at > now,
                )
            )
            if existing is not None:
                raise GoLiveError("Masih ada sesi acceptance aktif untuk versi ini")
            record = GoLiveAcceptanceSession(
                application_version=binding.application_version,
                schema_revision=binding.schema_revision,
                release_report_checksum_sha256=binding.report_checksum_sha256,
                installer_filename=binding.installer_filename,
                installer_checksum_sha256=binding.installer_checksum_sha256,
                environment_label=environment_label,
                status="IN_PROGRESS",
                expires_at=now + timedelta(days=validity_days),
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            for item_code, category, description, owner_type in DEFAULT_GO_LIVE_ITEMS:
                session.add(
                    GoLiveAcceptanceItem(
                        session_id=record.id,
                        item_code=item_code,
                        category=category,
                        description=description,
                        owner_type=owner_type,
                    )
                )
            self._append_ledger(
                session,
                record.id,
                "ACCEPTANCE_SESSION_CREATED",
                actor_user_id,
                {
                    "application_version": binding.application_version,
                    "schema_revision": binding.schema_revision,
                    "report_checksum": binding.report_checksum_sha256,
                    "installer_checksum": binding.installer_checksum_sha256,
                    "expires_at": AuditService._canonical_datetime(record.expires_at),
                },
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="GO_LIVE",
                    action="GO_LIVE_ACCEPTANCE_CREATED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="GO_LIVE_ACCEPTANCE",
                    entity_id=record.id,
                    details={
                        "application_version": binding.application_version,
                        "schema_revision": binding.schema_revision,
                    },
                ),
            )
            session.commit()
            return self._session_view(record)

    def sessions(self, actor_user_id: str) -> tuple[GoLiveSessionView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            rows = session.scalars(
                select(GoLiveAcceptanceSession).order_by(
                    GoLiveAcceptanceSession.created_at.desc()
                )
            ).all()
            return tuple(self._session_view(row) for row in rows)

    def items(
        self, session_id: str, actor_user_id: str
    ) -> tuple[GoLiveItemView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            self._get_session(session, session_id)
            rows = session.scalars(
                select(GoLiveAcceptanceItem)
                .where(GoLiveAcceptanceItem.session_id == session_id)
                .order_by(GoLiveAcceptanceItem.item_code)
            ).all()
            return tuple(self._item_view(row) for row in rows)

    def update_item(
        self,
        item_id: str,
        status: str,
        actor_user_id: str,
        *,
        evidence_path: Path | str | None = None,
        notes: str = "",
    ) -> GoLiveItemView:
        status = status.strip().upper()
        notes = notes.strip()
        if status not in self.ITEM_STATUSES - {"NOT_TESTED"}:
            raise GoLiveError("Status evidence harus PASS, FAIL, atau BLOCKED")
        if len(notes) > 300:
            raise GoLiveError("Catatan evidence maksimal 300 karakter")
        if status in {"FAIL", "BLOCKED"} and len(notes) < 10:
            raise GoLiveError("FAIL/BLOCKED memerlukan alasan minimal 10 karakter")
        evidence_filename: str | None = None
        evidence_checksum: str | None = None
        if evidence_path is not None:
            evidence = self._safe_evidence_file(evidence_path)
            evidence_filename = evidence.name
            evidence_checksum = self._sha256(evidence)
        if status == "PASS" and evidence_checksum is None:
            raise GoLiveError("PASS memerlukan file bukti yang dapat di-checksum")

        with self.database.session() as session:
            item = session.get(GoLiveAcceptanceItem, item_id)
            if item is None:
                raise GoLiveError("Item acceptance tidak ditemukan")
            record = self._get_session(session, item.session_id)
            self._assert_open(record)
            allowed = (
                self.TECHNICAL_ROLES
                if item.owner_type == "TECHNICAL"
                else self.CLINICAL_ROLES
            )
            self._require_roles(session, actor_user_id, allowed)
            if not self._verify_ledger_in_session(session):
                raise GoLiveError("Ledger keputusan go-live tidak valid")
            item.status = status
            item.evidence_filename = evidence_filename
            item.evidence_checksum_sha256 = evidence_checksum
            item.notes = notes or None
            item.tested_by = actor_user_id
            item.tested_at = utc_now()
            if item.owner_type == "TECHNICAL":
                record.technical_attested_by = None
                record.technical_attested_at = None
            else:
                record.clinical_attested_by = None
                record.clinical_attested_at = None
            record.updated_at = utc_now()
            self._append_ledger(
                session,
                record.id,
                "ACCEPTANCE_ITEM_UPDATED",
                actor_user_id,
                {
                    "item_code": item.item_code,
                    "owner_type": item.owner_type,
                    "status": status,
                    "evidence_checksum": evidence_checksum,
                },
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="GO_LIVE",
                    action="GO_LIVE_EVIDENCE_UPDATED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="GO_LIVE_ACCEPTANCE_ITEM",
                    entity_id=item.id,
                    details={"item_code": item.item_code, "status": status},
                ),
            )
            session.commit()
            return self._item_view(item)

    def attest(
        self, session_id: str, attestation_type: str, actor_user_id: str
    ) -> GoLiveSessionView:
        attestation_type = attestation_type.strip().upper()
        if attestation_type not in {"CLINICAL", "TECHNICAL"}:
            raise GoLiveError("Jenis attestation harus CLINICAL atau TECHNICAL")
        allowed = (
            self.CLINICAL_ROLES
            if attestation_type == "CLINICAL"
            else self.TECHNICAL_ROLES
        )
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, allowed)
            record = self._get_session(session, session_id)
            self._assert_open(record)
            if not self._verify_ledger_in_session(session):
                raise GoLiveError("Ledger keputusan go-live tidak valid")
            owner_items = session.scalars(
                select(GoLiveAcceptanceItem).where(
                    GoLiveAcceptanceItem.session_id == session_id,
                    GoLiveAcceptanceItem.owner_type == attestation_type,
                )
            ).all()
            if not owner_items or any(item.status != "PASS" for item in owner_items):
                raise GoLiveError(
                    f"Seluruh item {attestation_type.lower()} wajib PASS"
                )
            if (
                attestation_type == "CLINICAL"
                and record.technical_attested_by == actor_user_id
            ) or (
                attestation_type == "TECHNICAL"
                and record.clinical_attested_by == actor_user_id
            ):
                raise GoLiveError("Attestation klinis dan teknis wajib pengguna berbeda")
            now = utc_now()
            if attestation_type == "CLINICAL":
                record.clinical_attested_by = actor_user_id
                record.clinical_attested_at = now
            else:
                record.technical_attested_by = actor_user_id
                record.technical_attested_at = now
            record.updated_at = now
            evidence_hashes = sorted(
                item.evidence_checksum_sha256 or "" for item in owner_items
            )
            statement_hash = hashlib.sha256(
                json.dumps(
                    {
                        "session_id": session_id,
                        "type": attestation_type,
                        "evidence_hashes": evidence_hashes,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            self._append_ledger(
                session,
                record.id,
                f"{attestation_type}_ATTESTED",
                actor_user_id,
                {"statement_hash": statement_hash},
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="GO_LIVE",
                    action=f"GO_LIVE_{attestation_type}_ATTESTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="GO_LIVE_ACCEPTANCE",
                    entity_id=record.id,
                    details={"statement_hash": statement_hash},
                ),
            )
            session.commit()
            return self._session_view(record)

    def evaluate(
        self, session_id: str, actor_user_id: str | None = None
    ) -> GoLiveReadiness:
        with self.database.session() as session:
            if actor_user_id is not None:
                self._require_roles(
                    session, actor_user_id, self.AUTHORIZED_READERS
                )
            record = self._get_session(session, session_id)
            items = session.scalars(
                select(GoLiveAcceptanceItem).where(
                    GoLiveAcceptanceItem.session_id == session_id
                )
            ).all()
            ledger_valid = self._verify_ledger_in_session(session)
            blockers: list[str] = []
            now = utc_now()
            if record.status != "IN_PROGRESS":
                blockers.append(f"Sesi sudah memiliki keputusan final {record.status}")
            if self._as_utc(record.expires_at) <= now:
                blockers.append("Sesi acceptance telah kedaluwarsa")
            if record.application_version != __version__:
                blockers.append("Sesi bukan untuk versi aplikasi aktif")
            if record.schema_revision != self.database.current_revision():
                blockers.append("Sesi bukan untuk schema database aktif")
            if not ledger_valid:
                blockers.append("Ledger keputusan go-live tidak valid")
            not_passed = [item.item_code for item in items if item.status != "PASS"]
            if not_passed:
                blockers.append("Evidence belum PASS: " + ", ".join(sorted(not_passed)))
            if record.clinical_attested_by is None:
                blockers.append("Attestation klinis belum tersedia")
            if record.technical_attested_by is None:
                blockers.append("Attestation teknis belum tersedia")
            if (
                record.clinical_attested_by is not None
                and record.clinical_attested_by == record.technical_attested_by
            ):
                blockers.append("Attestor klinis dan teknis tidak independen")
            return GoLiveReadiness(
                session=self._session_view(record),
                items_passed=sum(item.status == "PASS" for item in items),
                items_total=len(items),
                ledger_valid=ledger_valid,
                ready_for_go_decision=not blockers,
                blockers=tuple(blockers),
            )

    def decide(
        self,
        session_id: str,
        decision: str,
        reason: str,
        actor_user_id: str,
    ) -> GoLiveSessionView:
        decision = decision.strip().upper()
        reason = reason.strip()
        if decision not in {"GO", "NO_GO"}:
            raise GoLiveError("Keputusan harus GO atau NO_GO")
        if not 10 <= len(reason) <= 300:
            raise GoLiveError("Alasan keputusan wajib 10-300 karakter")
        if decision == "GO":
            readiness = self.evaluate(session_id, actor_user_id)
            if not readiness.ready_for_go_decision:
                raise GoLiveError("GO ditolak: " + "; ".join(readiness.blockers))
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION_ROLES)
            record = self._get_session(session, session_id)
            self._assert_open(record)
            if not self._verify_ledger_in_session(session):
                raise GoLiveError("Ledger keputusan go-live tidak valid")
            if decision == "GO" and actor_user_id in {
                record.clinical_attested_by,
                record.technical_attested_by,
            }:
                raise GoLiveError("Pengambil keputusan GO wajib independen dari attestor")
            now = utc_now()
            record.status = decision
            record.decided_by = actor_user_id
            record.decided_at = now
            record.decision_reason = reason
            record.updated_at = now
            self._append_ledger(
                session,
                record.id,
                f"DECISION_{decision}",
                actor_user_id,
                {
                    "decision": decision,
                    "reason_sha256": hashlib.sha256(reason.encode("utf-8")).hexdigest(),
                },
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="GO_LIVE",
                    action=f"GO_LIVE_DECISION_{decision}",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="GO_LIVE_ACCEPTANCE",
                    entity_id=record.id,
                    details={"decision": decision},
                ),
            )
            session.commit()
            return self._session_view(record)

    def ledger(self, actor_user_id: str) -> tuple[GoLiveLedgerEntry, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            if not self._verify_ledger_in_session(session):
                raise GoLiveError("Ledger keputusan go-live tidak valid")
            rows = session.scalars(
                select(GoLiveDecisionLedger).order_by(GoLiveDecisionLedger.id)
            ).all()
            return tuple(
                GoLiveLedgerEntry(
                    sequence=row.id,
                    event_id=row.event_id,
                    session_id=row.session_id,
                    event_type=row.event_type,
                    actor_user_id=row.actor_user_id,
                    occurred_at=row.occurred_at,
                    payload_json=row.payload_json,
                    previous_hash=row.previous_hash,
                    entry_hash=row.entry_hash,
                )
                for row in rows
            )

    def verify_ledger(self, actor_user_id: str) -> bool:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            return self._verify_ledger_in_session(session)

    def _append_ledger(
        self,
        session: Session,
        session_id: str,
        event_type: str,
        actor_user_id: str | None,
        payload: dict[str, Any],
    ) -> GoLiveDecisionLedger:
        previous = session.scalar(
            select(GoLiveDecisionLedger)
            .order_by(GoLiveDecisionLedger.id.desc())
            .limit(1)
        )
        previous_hash = previous.entry_hash if previous else self.LEDGER_GENESIS_HASH
        event_id = new_uuid()
        occurred_at = utc_now()
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        hash_payload = {
            "event_id": event_id,
            "session_id": session_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "occurred_at": AuditService._canonical_datetime(occurred_at),
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(
            json.dumps(
                hash_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        entry = GoLiveDecisionLedger(
            event_id=event_id,
            session_id=session_id,
            event_type=event_type,
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
        rows = session.scalars(
            select(GoLiveDecisionLedger).order_by(GoLiveDecisionLedger.id)
        ).all()
        for row in rows:
            if row.previous_hash != expected_previous:
                return False
            payload = {
                "event_id": row.event_id,
                "session_id": row.session_id,
                "event_type": row.event_type,
                "actor_user_id": row.actor_user_id,
                "occurred_at": AuditService._canonical_datetime(row.occurred_at),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    def _inspect_release_binding(
        self, report_path: Path | str, installer_path: Path | str
    ) -> _ReleaseBinding:
        report = self._safe_evidence_file(report_path, maximum=25 * 1024 * 1024)
        installer = self._safe_evidence_file(
            installer_path, maximum=2 * 1024 * 1024 * 1024
        )
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GoLiveError("Release qualification JSON tidak valid") from exc
        if not isinstance(payload, dict):
            raise GoLiveError("Release qualification harus berupa object JSON")
        if payload.get("format") != "EMSS_RELEASE_QUALIFICATION_V1":
            raise GoLiveError("Format release qualification tidak didukung")
        if payload.get("status") != "QUALIFIED":
            raise GoLiveError("Release qualification belum berstatus QUALIFIED")
        checks = payload.get("checks")
        if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) or check.get("status") != "PASS"
            for check in checks
        ):
            raise GoLiveError("Release qualification memuat check yang tidak lulus")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise GoLiveError("Manifest artefak release tidak tersedia")
        matches = [
            item
            for item in artifacts
            if isinstance(item, dict)
            and item.get("path") == f"installer/{installer.name}"
        ]
        if len(matches) != 1:
            raise GoLiveError("Installer tidak ditemukan tepat satu kali di manifest")
        expected_checksum = matches[0].get("checksum_sha256")
        actual_checksum = self._sha256(installer)
        if expected_checksum != actual_checksum:
            raise GoLiveError("Checksum installer tidak sesuai release manifest")
        version = payload.get("application_version")
        schema = payload.get("schema_revision")
        if not isinstance(version, str) or not isinstance(schema, str):
            raise GoLiveError("Binding versi/schema release tidak valid")
        return _ReleaseBinding(
            report_checksum_sha256=self._sha256(report),
            application_version=version,
            schema_revision=schema,
            installer_checksum_sha256=actual_checksum,
            installer_filename=installer.name,
        )

    @staticmethod
    def _safe_evidence_file(
        path: Path | str, *, maximum: int = 50 * 1024 * 1024
    ) -> Path:
        source = Path(path)
        if source.is_symlink():
            raise GoLiveError("File bukti tidak ditemukan atau berupa symlink")
        candidate = source.resolve()
        if not candidate.is_file():
            raise GoLiveError("File bukti tidak ditemukan atau berupa symlink")
        size = candidate.stat().st_size
        if size <= 0 or size > maximum:
            raise GoLiveError("Ukuran file bukti di luar batas")
        return candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _assert_open(record: GoLiveAcceptanceSession) -> None:
        if record.status != "IN_PROGRESS":
            raise GoLiveError("Keputusan sesi sudah final dan immutable")
        if GoLiveService._as_utc(record.expires_at) <= utc_now():
            raise GoLiveError("Sesi acceptance telah kedaluwarsa")

    @staticmethod
    def _get_session(session: Session, session_id: str) -> GoLiveAcceptanceSession:
        record = session.get(GoLiveAcceptanceSession, session_id)
        if record is None:
            raise GoLiveError("Sesi acceptance tidak ditemukan")
        return record

    @staticmethod
    def _session_view(record: GoLiveAcceptanceSession) -> GoLiveSessionView:
        return GoLiveSessionView(
            id=record.id,
            application_version=record.application_version,
            schema_revision=record.schema_revision,
            environment_label=record.environment_label,
            status=record.status,
            expires_at=record.expires_at,
            release_report_checksum_sha256=record.release_report_checksum_sha256,
            installer_filename=record.installer_filename,
            installer_checksum_sha256=record.installer_checksum_sha256,
            clinical_attested_by=record.clinical_attested_by,
            clinical_attested_at=record.clinical_attested_at,
            technical_attested_by=record.technical_attested_by,
            technical_attested_at=record.technical_attested_at,
            decided_by=record.decided_by,
            decided_at=record.decided_at,
            decision_reason=record.decision_reason or "",
        )

    @staticmethod
    def _item_view(record: GoLiveAcceptanceItem) -> GoLiveItemView:
        return GoLiveItemView(
            id=record.id,
            item_code=record.item_code,
            category=record.category,
            description=record.description,
            owner_type=record.owner_type,
            status=record.status,
            evidence_filename=record.evidence_filename,
            evidence_checksum_sha256=record.evidence_checksum_sha256,
            notes=record.notes or "",
            tested_by=record.tested_by,
            tested_at=record.tested_at,
        )

    @staticmethod
    def _require_roles(
        session: Session, actor_user_id: str, allowed: frozenset[str]
    ) -> frozenset[str]:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active:
            raise GoLivePermissionError("Pengguna aktif tidak ditemukan")
        roles = frozenset(item.role.code for item in user.roles)
        if not roles.intersection(allowed):
            raise GoLivePermissionError("Role tidak berwenang untuk go-live acceptance")
        return roles
