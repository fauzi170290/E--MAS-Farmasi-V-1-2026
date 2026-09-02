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
from emss.database.deployment_models import GoLiveAcceptanceSession
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole, new_uuid
from emss.database.production_release_models import (
    ProductionChangeApproval,
    ProductionReleaseEvidence,
    ProductionReleaseLedger,
    ProductionReleaseRecord,
)
from emss.database.production_evidence_models import (
    ProductionDeploymentCeremony,
    ProductionEvidencePackageVerification,
)
from emss.database.rollout_models import LimitedRolloutSession
from emss.database.surveillance_models import EarlyLifeSurveillanceSession
from emss.services.surveillance import SurveillanceService
from emss.utils.time import utc_now


class ProductionReleaseError(ValueError):
    pass


class ProductionReleasePermissionError(ProductionReleaseError):
    pass


@dataclass(frozen=True)
class ProductionReleaseView:
    id: str
    surveillance_session_id: str
    application_version: str
    schema_revision: str
    environment_label: str
    installer_filename: str
    installer_checksum_sha256: str
    status: str
    expires_at: datetime
    authorized_by: str | None
    authorized_at: datetime | None
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class ProductionEvidenceView:
    id: str
    evidence_type: str
    evidence_filename: str
    evidence_checksum_sha256: str
    observed_at: datetime
    valid_until: datetime | None
    recorded_by: str


@dataclass(frozen=True)
class ProductionChangeApprovalView:
    evidence_filename: str
    evidence_checksum_sha256: str
    approval_reference_hash_sha256: str
    deployment_window_start: datetime
    deployment_window_end: datetime
    approved_by: str
    approved_at: datetime


@dataclass(frozen=True)
class ProductionReleaseReadiness:
    record: ProductionReleaseView
    evidence_types: tuple[str, ...]
    signature_basis: str | None
    change_approval: ProductionChangeApprovalView | None
    ledger_valid: bool
    ready_for_authorization: bool
    manual_deployment_authorized: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ProductionReleaseLedgerEntry:
    sequence: int
    release_record_id: str
    event_type: str
    actor_user_id: str | None
    occurred_at: datetime
    entry_hash: str


class ProductionReleaseService:
    """Fail-closed evidence ledger. This service never performs deployment."""

    LEDGER_GENESIS_HASH = "0" * 64
    EVIDENCE_FORMAT = "EMSS_PRODUCTION_EVIDENCE_V1"
    CHANGE_FORMAT = "EMSS_PRODUCTION_CHANGE_APPROVAL_V1"
    MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
    EVIDENCE_TYPES = frozenset(
        {
            "AUTHENTICODE",
            "FORMAL_WAIVER",
            "CLEAN_INSTALL",
            "CLEAN_UPGRADE",
            "CLEAN_UNINSTALL",
            "DATA_PRESERVATION",
            "ROLLBACK_RESTORE",
        }
    )
    REQUIRED_TECHNICAL_EVIDENCE = frozenset(
        {
            "CLEAN_INSTALL",
            "CLEAN_UPGRADE",
            "CLEAN_UNINSTALL",
            "DATA_PRESERVATION",
            "ROLLBACK_RESTORE",
        }
    )
    AUTHORIZED_READERS = SurveillanceService.AUTHORIZED_READERS
    TECHNICAL_ROLES = SurveillanceService.TECHNICAL_ROLES
    APPROVAL_ROLES = frozenset({"DIREKTUR"})
    DECISION_ROLES = frozenset({"DIREKTUR"})
    EMERGENCY_ROLES = TECHNICAL_ROLES | DECISION_ROLES
    TERMINAL_STATUSES = frozenset({"REJECTED", "REVOKED", "ROLLBACK_ORDERED"})

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        surveillance: SurveillanceService,
    ) -> None:
        self.database = database
        self.audit = audit
        self.surveillance = surveillance

    def create_record(
        self,
        surveillance_session_id: str,
        actor_user_id: str,
        *,
        validity_days: int = 14,
    ) -> ProductionReleaseView:
        if not 1 <= validity_days <= 30:
            raise ProductionReleaseError("Masa record produksi wajib 1-30 hari")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            self._assert_all_ledgers(session)
            surveillance = session.get(EarlyLifeSurveillanceSession, surveillance_session_id)
            if surveillance is None:
                raise ProductionReleaseError("Surveillance tidak ditemukan")
            if surveillance.status != "PROMOTED":
                raise ProductionReleaseError("Surveillance belum PROMOTED")
            if (
                surveillance.application_version != __version__
                or surveillance.schema_revision != self.database.current_revision()
            ):
                raise ProductionReleaseError("Surveillance bukan untuk release aktif")
            if session.scalar(
                select(ProductionReleaseRecord).where(
                    ProductionReleaseRecord.surveillance_session_id == surveillance.id
                )
            ) is not None:
                raise ProductionReleaseError("Surveillance sudah memiliki production release record")
            rollout = session.get(LimitedRolloutSession, surveillance.rollout_session_id)
            acceptance = (
                session.get(GoLiveAcceptanceSession, rollout.acceptance_session_id)
                if rollout is not None
                else None
            )
            if rollout is None or acceptance is None:
                raise ProductionReleaseError("Binding release upstream tidak lengkap")
            if (
                acceptance.application_version != surveillance.application_version
                or acceptance.schema_revision != surveillance.schema_revision
            ):
                raise ProductionReleaseError("Binding versi/schema upstream berubah")
            now = utc_now()
            record = ProductionReleaseRecord(
                surveillance_session_id=surveillance.id,
                application_version=surveillance.application_version,
                schema_revision=surveillance.schema_revision,
                environment_label=surveillance.environment_label,
                installer_filename=acceptance.installer_filename,
                installer_checksum_sha256=acceptance.installer_checksum_sha256,
                status="DRAFT",
                expires_at=now + timedelta(days=validity_days),
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            self._append_ledger(
                session,
                record.id,
                "PRODUCTION_RELEASE_CREATED",
                actor_user_id,
                {
                    "surveillance_session_id": surveillance.id,
                    "application_version": record.application_version,
                    "schema_revision": record.schema_revision,
                    "installer_checksum_sha256": record.installer_checksum_sha256,
                    "expires_at": AuditService._canonical_datetime(record.expires_at),
                },
            )
            self._audit(session, record, "PRODUCTION_RELEASE_CREATED", actor_user_id)
            session.commit()
            return self._record_view(record)

    def records(self, actor_user_id: str) -> tuple[ProductionReleaseView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            rows = session.scalars(
                select(ProductionReleaseRecord).order_by(ProductionReleaseRecord.created_at.desc())
            ).all()
            return tuple(self._record_view(row) for row in rows)

    def evidence(
        self, release_record_id: str, actor_user_id: str
    ) -> tuple[ProductionEvidenceView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            self._get_record(session, release_record_id)
            rows = session.scalars(
                select(ProductionReleaseEvidence)
                .where(ProductionReleaseEvidence.release_record_id == release_record_id)
                .order_by(ProductionReleaseEvidence.evidence_type)
            ).all()
            return tuple(self._evidence_view(row) for row in rows)

    def record_evidence(
        self,
        release_record_id: str,
        evidence_type: str,
        evidence_path: Path,
        actor_user_id: str,
    ) -> ProductionEvidenceView:
        evidence_type = evidence_type.strip().upper()
        if evidence_type not in self.EVIDENCE_TYPES:
            raise ProductionReleaseError("Jenis evidence produksi tidak dikenal")
        payload, filename, checksum = self._read_json_evidence(evidence_path)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL_ROLES)
            record = self._get_record(session, release_record_id)
            self._assert_draft(record)
            self._assert_all_ledgers(session)
            if session.scalar(
                select(ProductionReleaseEvidence).where(
                    ProductionReleaseEvidence.release_record_id == record.id,
                    ProductionReleaseEvidence.evidence_type == evidence_type,
                )
            ) is not None:
                raise ProductionReleaseError("Jenis evidence sudah tercatat dan immutable")
            observed_at, valid_until = self._validate_evidence_contract(
                payload, evidence_type, record
            )
            row = ProductionReleaseEvidence(
                release_record_id=record.id,
                evidence_type=evidence_type,
                evidence_filename=filename,
                evidence_checksum_sha256=checksum,
                observed_at=observed_at,
                valid_until=valid_until,
                recorded_by=actor_user_id,
                recorded_at=utc_now(),
            )
            session.add(row)
            session.flush()
            self._append_ledger(
                session,
                record.id,
                "EVIDENCE_RECORDED",
                actor_user_id,
                {
                    "evidence_type": evidence_type,
                    "evidence_checksum_sha256": checksum,
                    "observed_at": AuditService._canonical_datetime(observed_at),
                    "valid_until": (
                        AuditService._canonical_datetime(valid_until) if valid_until else None
                    ),
                },
            )
            self._audit(session, record, f"PRODUCTION_EVIDENCE_{evidence_type}", actor_user_id)
            session.commit()
            return self._evidence_view(row)

    def record_change_approval(
        self,
        release_record_id: str,
        evidence_path: Path,
        actor_user_id: str,
    ) -> ProductionChangeApprovalView:
        payload, filename, checksum = self._read_json_evidence(evidence_path)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.APPROVAL_ROLES)
            record = self._get_record(session, release_record_id)
            self._assert_draft(record)
            self._assert_all_ledgers(session)
            if session.scalar(
                select(ProductionChangeApproval).where(
                    ProductionChangeApproval.release_record_id == record.id
                )
            ) is not None:
                raise ProductionReleaseError("Change approval sudah tercatat dan immutable")
            evidence_actors = set(
                session.scalars(
                    select(ProductionReleaseEvidence.recorded_by).where(
                        ProductionReleaseEvidence.release_record_id == record.id
                    )
                ).all()
            )
            if actor_user_id == record.created_by or actor_user_id in evidence_actors:
                raise ProductionReleaseError("Change approver wajib independen dari preparer evidence")
            start, end, reference_hash, approver_hash = self._validate_change_contract(
                payload, record
            )
            row = ProductionChangeApproval(
                release_record_id=record.id,
                evidence_filename=filename,
                evidence_checksum_sha256=checksum,
                approval_reference_hash_sha256=reference_hash,
                external_approver_hash_sha256=approver_hash,
                deployment_window_start=start,
                deployment_window_end=end,
                approved_by=actor_user_id,
                approved_at=utc_now(),
            )
            session.add(row)
            session.flush()
            self._append_ledger(
                session,
                record.id,
                "CHANGE_APPROVAL_RECORDED",
                actor_user_id,
                {
                    "evidence_checksum_sha256": checksum,
                    "approval_reference_hash_sha256": reference_hash,
                    "deployment_window_start": AuditService._canonical_datetime(start),
                    "deployment_window_end": AuditService._canonical_datetime(end),
                },
            )
            self._audit(session, record, "PRODUCTION_CHANGE_APPROVED", actor_user_id)
            session.commit()
            return self._approval_view(row)

    def evaluate(
        self, release_record_id: str, actor_user_id: str | None = None
    ) -> ProductionReleaseReadiness:
        with self.database.session() as session:
            if actor_user_id is not None:
                self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            record = self._get_record(session, release_record_id)
            rows = session.scalars(
                select(ProductionReleaseEvidence).where(
                    ProductionReleaseEvidence.release_record_id == record.id
                )
            ).all()
            approval = session.scalar(
                select(ProductionChangeApproval).where(
                    ProductionChangeApproval.release_record_id == record.id
                )
            )
            verification = session.scalar(
                select(ProductionEvidencePackageVerification)
                .where(ProductionEvidencePackageVerification.release_record_id == record.id)
                .order_by(ProductionEvidencePackageVerification.id.desc())
                .limit(1)
            )
            ceremony = session.scalar(
                select(ProductionDeploymentCeremony).where(
                    ProductionDeploymentCeremony.release_record_id == record.id
                )
            )
            ledger_valid = self._all_ledgers_valid(session)
            blockers = self._readiness_blockers(
                record, rows, approval, verification, ceremony, ledger_valid, session
            )
            if actor_user_id is not None and record.status == "DRAFT":
                actors = {record.created_by, *(row.recorded_by for row in rows)}
                if approval is not None:
                    actors.add(approval.approved_by)
                if verification is not None:
                    actors.add(verification.verified_by)
                if ceremony is not None:
                    actors.update(
                        {
                            ceremony.created_by,
                            ceremony.technical_attested_by,
                            ceremony.clinical_attested_by,
                        }
                    )
                    actors.discard(None)
                if actor_user_id in actors:
                    blockers.append("Pengambil keputusan produksi wajib independen")
            evidence_types = tuple(sorted(row.evidence_type for row in rows))
            signature_basis = next(
                (kind for kind in ("AUTHENTICODE", "FORMAL_WAIVER") if kind in evidence_types),
                None,
            )
            return ProductionReleaseReadiness(
                record=self._record_view(record),
                evidence_types=evidence_types,
                signature_basis=signature_basis,
                change_approval=self._approval_view(approval) if approval else None,
                ledger_valid=ledger_valid,
                ready_for_authorization=record.status == "DRAFT" and not blockers,
                manual_deployment_authorized=record.status == "AUTHORIZED" and not blockers,
                blockers=tuple(blockers),
            )

    def decide(
        self,
        release_record_id: str,
        decision: str,
        reason: str,
        actor_user_id: str,
    ) -> ProductionReleaseView:
        decision = decision.strip().upper()
        reason = self._validated_reason(reason)
        if decision not in {"AUTHORIZE", "REJECT"}:
            raise ProductionReleaseError("Keputusan harus AUTHORIZE atau REJECT")
        if decision == "AUTHORIZE":
            readiness = self.evaluate(release_record_id, actor_user_id)
            if not readiness.ready_for_authorization:
                raise ProductionReleaseError("Otorisasi ditolak: " + "; ".join(readiness.blockers))
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION_ROLES)
            record = self._get_record(session, release_record_id)
            self._assert_draft(record)
            self._assert_all_ledgers(session)
            now = utc_now()
            record.status = "AUTHORIZED" if decision == "AUTHORIZE" else "REJECTED"
            record.authorized_by = actor_user_id
            record.authorized_at = now
            record.decision_reason_hash_sha256 = self._text_hash(reason)
            record.updated_at = now
            self._append_ledger(
                session,
                record.id,
                f"DECISION_{decision}",
                actor_user_id,
                {"reason_hash_sha256": record.decision_reason_hash_sha256},
            )
            self._audit(session, record, f"PRODUCTION_DECISION_{decision}", actor_user_id)
            session.commit()
            return self._record_view(record)

    def revoke(
        self, release_record_id: str, reason: str, actor_user_id: str
    ) -> ProductionReleaseView:
        reason = self._validated_reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION_ROLES)
            record = self._get_record(session, release_record_id)
            if record.status != "AUTHORIZED":
                raise ProductionReleaseError("Hanya authorization aktif yang dapat dicabut")
            self._assert_all_ledgers(session)
            now = utc_now()
            record.status = "REVOKED"
            record.revoked_by = actor_user_id
            record.revoked_at = now
            record.revocation_reason_hash_sha256 = self._text_hash(reason)
            record.updated_at = now
            self._append_ledger(
                session,
                record.id,
                "AUTHORIZATION_REVOKED",
                actor_user_id,
                {"reason_hash_sha256": record.revocation_reason_hash_sha256},
            )
            self._audit(session, record, "PRODUCTION_AUTHORIZATION_REVOKED", actor_user_id)
            session.commit()
            return self._record_view(record)

    def order_emergency_rollback(
        self, release_record_id: str, reason: str, actor_user_id: str
    ) -> ProductionReleaseView:
        """Record a manual rollback order even when other gates are unhealthy."""
        reason = self._validated_reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.EMERGENCY_ROLES)
            record = self._get_record(session, release_record_id)
            if record.status in self.TERMINAL_STATUSES:
                raise ProductionReleaseError("Production release sudah terminal")
            now = utc_now()
            record.status = "ROLLBACK_ORDERED"
            record.rollback_ordered_by = actor_user_id
            record.rollback_ordered_at = now
            record.rollback_reason_hash_sha256 = self._text_hash(reason)
            record.updated_at = now
            self._append_ledger(
                session,
                record.id,
                "EMERGENCY_ROLLBACK_ORDERED",
                actor_user_id,
                {"reason_hash_sha256": record.rollback_reason_hash_sha256},
            )
            self._audit(session, record, "PRODUCTION_EMERGENCY_ROLLBACK", actor_user_id)
            session.commit()
            return self._record_view(record)

    def ledger(self, actor_user_id: str) -> tuple[ProductionReleaseLedgerEntry, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_READERS)
            if not self._verify_ledger_in_session(session):
                raise ProductionReleaseError("Ledger production release tidak valid")
            rows = session.scalars(
                select(ProductionReleaseLedger).order_by(ProductionReleaseLedger.id)
            ).all()
            return tuple(
                ProductionReleaseLedgerEntry(
                    row.id,
                    row.release_record_id,
                    row.event_type,
                    row.actor_user_id,
                    row.occurred_at,
                    row.entry_hash,
                )
                for row in rows
            )

    def _readiness_blockers(
        self,
        record: ProductionReleaseRecord,
        evidence: list[ProductionReleaseEvidence],
        approval: ProductionChangeApproval | None,
        verification: ProductionEvidencePackageVerification | None,
        ceremony: ProductionDeploymentCeremony | None,
        ledger_valid: bool,
        session: Session,
    ) -> list[str]:
        blockers: list[str] = []
        surveillance = session.get(EarlyLifeSurveillanceSession, record.surveillance_session_id)
        if surveillance is None or surveillance.status != "PROMOTED":
            blockers.append("Surveillance upstream tidak PROMOTED")
        elif (
            surveillance.application_version != record.application_version
            or surveillance.schema_revision != record.schema_revision
        ):
            blockers.append("Binding surveillance berubah")
        if record.application_version != __version__:
            blockers.append("Record bukan untuk versi aplikasi aktif")
        if record.schema_revision != self.database.current_revision():
            blockers.append("Record bukan untuk schema aktif")
        if not ledger_valid:
            blockers.append("Ledger upstream/production tidak valid")
        now = utc_now()
        if self._as_utc(record.expires_at) <= now:
            blockers.append("Production release record telah kedaluwarsa")
        if record.status in self.TERMINAL_STATUSES:
            blockers.append(f"Production release sudah terminal: {record.status}")
        by_type = {row.evidence_type: row for row in evidence}
        missing = sorted(self.REQUIRED_TECHNICAL_EVIDENCE - by_type.keys())
        if missing:
            blockers.append("Evidence wajib belum lengkap: " + ", ".join(missing))
        if not {"AUTHENTICODE", "FORMAL_WAIVER"}.intersection(by_type):
            blockers.append("Authenticode Valid atau waiver formal belum tersedia")
        for row in evidence:
            if row.valid_until is not None and self._as_utc(row.valid_until) <= now:
                blockers.append(f"Evidence {row.evidence_type} telah kedaluwarsa")
        if approval is None:
            blockers.append("Change approval dan deployment window belum tersedia")
        else:
            start = self._as_utc(approval.deployment_window_start)
            end = self._as_utc(approval.deployment_window_end)
            if now < start:
                blockers.append("Deployment window belum dimulai")
            if now >= end:
                blockers.append("Deployment window telah berakhir")
        expected_snapshot = self.evidence_snapshot_hash(evidence, approval) if approval else None
        if verification is None:
            blockers.append("Paket evidence belum diverifikasi")
        elif verification.status != "VALID":
            blockers.append("Verifikasi paket evidence terbaru INVALID")
        elif verification.evidence_snapshot_sha256 != expected_snapshot:
            blockers.append("Verifikasi paket evidence sudah stale")
        if ceremony is None:
            blockers.append("Manual deployment ceremony belum tersedia")
        elif ceremony.status != "ATTESTED":
            blockers.append(f"Manual deployment ceremony belum ATTESTED: {ceremony.status}")
        elif verification is None or ceremony.verification_id != verification.id:
            blockers.append("Binding package pada deployment ceremony tidak valid")
        elif ceremony.technical_attested_by == ceremony.clinical_attested_by:
            blockers.append("Attestor teknis dan klinis ceremony tidak independen")
        return blockers

    @staticmethod
    def evidence_snapshot_hash(
        evidence: list[ProductionReleaseEvidence],
        approval: ProductionChangeApproval,
    ) -> str:
        payload = {
            "evidence": [
                {
                    "evidence_type": row.evidence_type,
                    "filename": row.evidence_filename,
                    "checksum_sha256": row.evidence_checksum_sha256,
                    "observed_at": AuditService._canonical_datetime(row.observed_at),
                    "valid_until": (
                        AuditService._canonical_datetime(row.valid_until)
                        if row.valid_until else None
                    ),
                }
                for row in sorted(evidence, key=lambda item: item.evidence_type)
            ],
            "change_approval": {
                "filename": approval.evidence_filename,
                "checksum_sha256": approval.evidence_checksum_sha256,
                "approval_reference_hash_sha256": approval.approval_reference_hash_sha256,
                "deployment_window_start": AuditService._canonical_datetime(
                    approval.deployment_window_start
                ),
                "deployment_window_end": AuditService._canonical_datetime(
                    approval.deployment_window_end
                ),
            },
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _validate_evidence_contract(
        self,
        payload: dict[str, Any],
        evidence_type: str,
        record: ProductionReleaseRecord,
    ) -> tuple[datetime, datetime | None]:
        if payload.get("format") != self.EVIDENCE_FORMAT:
            raise ProductionReleaseError("Format evidence produksi tidak valid")
        if str(payload.get("evidence_type", "")).upper() != evidence_type:
            raise ProductionReleaseError("Jenis evidence tidak cocok dengan paket")
        if payload.get("status") != "PASS":
            raise ProductionReleaseError("Evidence produksi tidak berstatus PASS")
        self._assert_contract_binding(payload, record)
        observed_at = self._parse_datetime(payload.get("observed_at"), "observed_at")
        now = utc_now()
        if observed_at > now + timedelta(minutes=5):
            raise ProductionReleaseError("Waktu observasi evidence berada di masa depan")
        valid_until = None
        if payload.get("valid_until"):
            valid_until = self._parse_datetime(payload["valid_until"], "valid_until")
            if valid_until <= now:
                raise ProductionReleaseError("Evidence sudah kedaluwarsa")
        if evidence_type == "AUTHENTICODE" and payload.get("signature_status") != "Valid":
            raise ProductionReleaseError("Authenticode evidence wajib berstatus Valid")
        if evidence_type == "FORMAL_WAIVER":
            if not self._valid_reference(payload.get("waiver_id")):
                raise ProductionReleaseError("Waiver wajib memiliki referensi formal")
            if not self._valid_reference(payload.get("approved_by_external")):
                raise ProductionReleaseError("Waiver wajib memiliki approver eksternal")
            if valid_until is None:
                raise ProductionReleaseError("Waiver formal wajib memiliki expiry")
        if evidence_type.startswith("CLEAN_"):
            if payload.get("clean_host") is not True or not self._is_sha256(
                payload.get("host_fingerprint_sha256")
            ):
                raise ProductionReleaseError("Evidence clean-host tidak lengkap")
        if evidence_type == "DATA_PRESERVATION":
            before = payload.get("data_checksum_before_sha256")
            after = payload.get("data_checksum_after_sha256")
            if payload.get("data_preserved") is not True or not (
                self._is_sha256(before) and before == after
            ):
                raise ProductionReleaseError("Evidence preservasi data tidak valid")
        if evidence_type == "ROLLBACK_RESTORE" and not (
            payload.get("rollback_tested") is True
            and payload.get("restore_verified") is True
        ):
            raise ProductionReleaseError("Evidence rollback/restore tidak valid")
        return observed_at, valid_until

    def _validate_change_contract(
        self, payload: dict[str, Any], record: ProductionReleaseRecord
    ) -> tuple[datetime, datetime, str, str]:
        if payload.get("format") != self.CHANGE_FORMAT or payload.get("status") != "APPROVED":
            raise ProductionReleaseError("Change approval evidence tidak valid")
        self._assert_contract_binding(payload, record)
        reference = payload.get("approval_reference")
        external_approver = payload.get("approved_by_external")
        if not self._valid_reference(reference) or not self._valid_reference(external_approver):
            raise ProductionReleaseError("Referensi/approver change approval wajib diisi")
        start = self._parse_datetime(payload.get("deployment_window_start"), "deployment_window_start")
        end = self._parse_datetime(payload.get("deployment_window_end"), "deployment_window_end")
        if start >= end:
            raise ProductionReleaseError("Deployment window tidak valid")
        if end <= utc_now():
            raise ProductionReleaseError("Deployment window telah berakhir")
        if end > self._as_utc(record.expires_at):
            raise ProductionReleaseError("Deployment window melewati expiry record")
        return start, end, self._text_hash(str(reference)), self._text_hash(str(external_approver))

    @staticmethod
    def _assert_contract_binding(payload: dict[str, Any], record: ProductionReleaseRecord) -> None:
        expected = {
            "application_version": record.application_version,
            "schema_revision": record.schema_revision,
            "installer_checksum_sha256": record.installer_checksum_sha256,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ProductionReleaseError("Evidence tidak terikat ke release record")

    @classmethod
    def _read_json_evidence(cls, path: Path) -> tuple[dict[str, Any], str, str]:
        path = Path(path)
        if not path.is_file():
            raise ProductionReleaseError("File evidence tidak ditemukan")
        size = path.stat().st_size
        if size <= 0 or size > cls.MAX_EVIDENCE_BYTES:
            raise ProductionReleaseError("Ukuran evidence wajib 1 byte-5 MiB")
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionReleaseError("Evidence wajib JSON UTF-8 yang valid") from exc
        if not isinstance(payload, dict):
            raise ProductionReleaseError("Evidence JSON wajib berupa object")
        return payload, path.name, hashlib.sha256(raw).hexdigest()

    def _all_ledgers_valid(self, session: Session) -> bool:
        return self._verify_ledger_in_session(session) and self.surveillance._all_ledgers_valid(session)

    def _assert_all_ledgers(self, session: Session) -> None:
        if not self._all_ledgers_valid(session):
            raise ProductionReleaseError("Ledger upstream/production tidak valid")

    def _append_ledger(
        self,
        session: Session,
        release_record_id: str,
        event_type: str,
        actor_user_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        previous = session.scalar(
            select(ProductionReleaseLedger).order_by(ProductionReleaseLedger.id.desc()).limit(1)
        )
        previous_hash = previous.entry_hash if previous else self.LEDGER_GENESIS_HASH
        event_id = new_uuid()
        occurred_at = utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_payload = {
            "event_id": event_id,
            "release_record_id": release_record_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "occurred_at": AuditService._canonical_datetime(occurred_at),
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(
            json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        session.add(
            ProductionReleaseLedger(
                event_id=event_id,
                release_record_id=release_record_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                occurred_at=occurred_at,
                payload_json=payload_json,
                previous_hash=previous_hash,
                entry_hash=entry_hash,
            )
        )
        session.flush()

    def _verify_ledger_in_session(self, session: Session) -> bool:
        expected_previous = self.LEDGER_GENESIS_HASH
        rows = session.scalars(
            select(ProductionReleaseLedger).order_by(ProductionReleaseLedger.id)
        ).all()
        for row in rows:
            payload = {
                "event_id": row.event_id,
                "release_record_id": row.release_record_id,
                "event_type": row.event_type,
                "actor_user_id": row.actor_user_id,
                "occurred_at": AuditService._canonical_datetime(row.occurred_at),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if row.previous_hash != expected_previous or row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    def _audit(
        self,
        session: Session,
        record: ProductionReleaseRecord,
        action: str,
        actor_user_id: str | None,
    ) -> None:
        self.audit.append(
            session,
            AuditEvent(
                category="PRODUCTION_RELEASE",
                action=action,
                outcome="SUCCESS",
                actor_user_id=actor_user_id,
                entity_type="PRODUCTION_RELEASE",
                entity_id=record.id,
                details={
                    "status": record.status,
                    "application_version": record.application_version,
                    "schema_revision": record.schema_revision,
                },
            ),
        )

    @staticmethod
    def _get_record(session: Session, release_record_id: str) -> ProductionReleaseRecord:
        record = session.get(ProductionReleaseRecord, release_record_id)
        if record is None:
            raise ProductionReleaseError("Production release record tidak ditemukan")
        return record

    @staticmethod
    def _assert_draft(record: ProductionReleaseRecord) -> None:
        if record.status != "DRAFT":
            raise ProductionReleaseError("Production release record bukan DRAFT")
        if ProductionReleaseService._as_utc(record.expires_at) <= utc_now():
            raise ProductionReleaseError("Production release record telah kedaluwarsa")

    @staticmethod
    def _record_view(row: ProductionReleaseRecord) -> ProductionReleaseView:
        return ProductionReleaseView(
            row.id,
            row.surveillance_session_id,
            row.application_version,
            row.schema_revision,
            row.environment_label,
            row.installer_filename,
            row.installer_checksum_sha256,
            row.status,
            row.expires_at,
            row.authorized_by,
            row.authorized_at,
            row.created_by,
            row.created_at,
        )

    @staticmethod
    def _evidence_view(row: ProductionReleaseEvidence) -> ProductionEvidenceView:
        return ProductionEvidenceView(
            row.id,
            row.evidence_type,
            row.evidence_filename,
            row.evidence_checksum_sha256,
            row.observed_at,
            row.valid_until,
            row.recorded_by,
        )

    @staticmethod
    def _approval_view(row: ProductionChangeApproval) -> ProductionChangeApprovalView:
        return ProductionChangeApprovalView(
            row.evidence_filename,
            row.evidence_checksum_sha256,
            row.approval_reference_hash_sha256,
            row.deployment_window_start,
            row.deployment_window_end,
            row.approved_by,
            row.approved_at,
        )

    @staticmethod
    def _validated_reason(value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 300:
            raise ProductionReleaseError("Alasan wajib 10-300 karakter")
        return value

    @staticmethod
    def _valid_reference(value: object) -> bool:
        return isinstance(value, str) and 3 <= len(value.strip()) <= 300

    @staticmethod
    def _is_sha256(value: object) -> bool:
        if not isinstance(value, str) or len(value) != 64:
            return False
        try:
            int(value, 16)
        except ValueError:
            return False
        return True

    @staticmethod
    def _text_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _parse_datetime(value: object, field: str) -> datetime:
        if not isinstance(value, str):
            raise ProductionReleaseError(f"{field} wajib timestamp ISO-8601")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProductionReleaseError(f"{field} wajib timestamp ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ProductionReleaseError(f"{field} wajib memiliki timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _require_roles(session: Session, actor_user_id: str, allowed: frozenset[str]) -> None:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active:
            raise ProductionReleasePermissionError("Pengguna aktif tidak ditemukan")
        if not frozenset(item.role.code for item in user.roles).intersection(allowed):
            raise ProductionReleasePermissionError("Role tidak berwenang untuk production release")
