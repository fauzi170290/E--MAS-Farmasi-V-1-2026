from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from emss.audit.service import AuditEvent, AuditService
from emss.database.production_evidence_models import (
    ProductionDeploymentCeremony,
    ProductionEvidencePackageVerification,
)
from emss.database.production_release_models import (
    ProductionChangeApproval,
    ProductionReleaseEvidence,
    ProductionReleaseLedger,
    ProductionReleaseRecord,
)
from emss.services.production_release import (
    ProductionReleaseError,
    ProductionReleaseService,
)
from emss.utils.time import utc_now


class ProductionEvidenceError(ProductionReleaseError):
    pass


class _PackageInvalid(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvidencePackageVerificationView:
    id: int
    verification_id: str
    release_record_id: str
    package_filename: str
    package_checksum_sha256: str
    manifest_checksum_sha256: str | None
    evidence_snapshot_sha256: str | None
    status: str
    error_code: str | None
    entry_count: int
    verified_by: str
    verified_at: datetime


@dataclass(frozen=True)
class DeploymentCeremonyView:
    id: str
    release_record_id: str
    verification_id: int
    status: str
    deployment_window_start: datetime
    deployment_window_end: datetime
    technical_attested_by: str | None
    clinical_attested_by: str | None
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class AuthorizationReceipt:
    path: Path
    checksum_sha256: str


class ProductionEvidenceService:
    PACKAGE_FORMAT = "EMSS_PRODUCTION_EVIDENCE_PACKAGE_V1"
    RECEIPT_FORMAT = "EMSS_PRODUCTION_AUTHORIZATION_RECEIPT_V1"
    MAX_PACKAGE_BYTES = 12 * 1024 * 1024
    MAX_MEMBER_BYTES = 5 * 1024 * 1024
    MAX_MEMBERS = 20
    VERIFIER_ROLES = ProductionReleaseService.TECHNICAL_ROLES | ProductionReleaseService.DECISION_ROLES
    TECHNICAL_ROLES = ProductionReleaseService.TECHNICAL_ROLES
    CLINICAL_ROLES = frozenset({"APOTEKER", "CLINICAL_REVIEWER", "KFT"})
    CEREMONY_ROLES = ProductionReleaseService.APPROVAL_ROLES
    EMERGENCY_ROLES = ProductionReleaseService.EMERGENCY_ROLES
    FORBIDDEN_KEYS = frozenset(
        {
            "patient", "patient_id", "patient_name", "pasien", "nama_pasien",
            "no_rm", "nomor_rm", "medical_record", "medical_record_number",
            "no_resep", "nomor_resep", "prescription_number",
        }
    )

    def __init__(self, production_release: ProductionReleaseService) -> None:
        self.production_release = production_release
        self.database = production_release.database
        self.audit = production_release.audit

    def verify_package(
        self,
        release_record_id: str,
        package_path: Path,
        actor_user_id: str,
    ) -> EvidencePackageVerificationView:
        package_path = Path(package_path)
        if not package_path.is_file():
            raise ProductionEvidenceError("Paket evidence tidak ditemukan")
        size = package_path.stat().st_size
        if size <= 0 or size > self.MAX_PACKAGE_BYTES:
            raise ProductionEvidenceError("Ukuran paket evidence wajib 1 byte-12 MiB")
        package_raw = package_path.read_bytes()
        package_checksum = hashlib.sha256(package_raw).hexdigest()
        with self.database.session() as session:
            self.production_release._require_roles(session, actor_user_id, self.VERIFIER_ROLES)
            record = self.production_release._get_record(session, release_record_id)
            self.production_release._assert_draft(record)
            self.production_release._assert_all_ledgers(session)
            evidence = list(session.scalars(select(ProductionReleaseEvidence).where(
                ProductionReleaseEvidence.release_record_id == record.id
            )).all())
            approval = session.scalar(select(ProductionChangeApproval).where(
                ProductionChangeApproval.release_record_id == record.id
            ))
            manifest_checksum = None
            snapshot_checksum = None
            entry_count = 0
            status_value = "VALID"
            error_code = None
            try:
                manifest_checksum, snapshot_checksum, entry_count = self._inspect_package(
                    package_path, record, evidence, approval
                )
            except _PackageInvalid as exc:
                status_value = "INVALID"
                error_code = exc.code
            row = ProductionEvidencePackageVerification(
                release_record_id=record.id,
                package_filename=package_path.name,
                package_checksum_sha256=package_checksum,
                manifest_checksum_sha256=manifest_checksum,
                evidence_snapshot_sha256=snapshot_checksum,
                status=status_value,
                error_code=error_code,
                entry_count=entry_count,
                verified_by=actor_user_id,
                verified_at=utc_now(),
            )
            session.add(row)
            session.flush()
            self.production_release._append_ledger(
                session,
                record.id,
                "EVIDENCE_PACKAGE_VERIFIED",
                actor_user_id,
                {
                    "package_checksum_sha256": package_checksum,
                    "manifest_checksum_sha256": manifest_checksum,
                    "evidence_snapshot_sha256": snapshot_checksum,
                    "status": status_value,
                    "error_code": error_code,
                    "entry_count": entry_count,
                },
            )
            self._audit(session, record, f"EVIDENCE_PACKAGE_{status_value}", actor_user_id)
            session.commit()
            return self._verification_view(row)

    def verifications(
        self, release_record_id: str, actor_user_id: str
    ) -> tuple[EvidencePackageVerificationView, ...]:
        with self.database.session() as session:
            self.production_release._require_roles(
                session, actor_user_id, self.production_release.AUTHORIZED_READERS
            )
            self.production_release._get_record(session, release_record_id)
            rows = session.scalars(
                select(ProductionEvidencePackageVerification)
                .where(ProductionEvidencePackageVerification.release_record_id == release_record_id)
                .order_by(ProductionEvidencePackageVerification.id)
            ).all()
            return tuple(self._verification_view(row) for row in rows)

    def start_ceremony(
        self, release_record_id: str, actor_user_id: str
    ) -> DeploymentCeremonyView:
        with self.database.session() as session:
            self.production_release._require_roles(session, actor_user_id, self.CEREMONY_ROLES)
            record = self.production_release._get_record(session, release_record_id)
            self.production_release._assert_draft(record)
            self.production_release._assert_all_ledgers(session)
            if session.scalar(select(ProductionDeploymentCeremony).where(
                ProductionDeploymentCeremony.release_record_id == record.id
            )) is not None:
                raise ProductionEvidenceError("Deployment ceremony sudah tersedia dan immutable")
            verification = self._latest_verification(session, record.id)
            approval = session.scalar(select(ProductionChangeApproval).where(
                ProductionChangeApproval.release_record_id == record.id
            ))
            evidence = list(session.scalars(select(ProductionReleaseEvidence).where(
                ProductionReleaseEvidence.release_record_id == record.id
            )).all())
            if verification is None or verification.status != "VALID":
                raise ProductionEvidenceError("Paket evidence terbaru belum VALID")
            if approval is None:
                raise ProductionEvidenceError("Change approval belum tersedia")
            expected_snapshot = self.production_release.evidence_snapshot_hash(evidence, approval)
            if verification.evidence_snapshot_sha256 != expected_snapshot:
                raise ProductionEvidenceError("Verifikasi paket sudah stale")
            now = utc_now()
            start = self.production_release._as_utc(approval.deployment_window_start)
            end = self.production_release._as_utc(approval.deployment_window_end)
            if now < start or now >= end:
                raise ProductionEvidenceError("Deployment ceremony hanya dapat dimulai di dalam window")
            row = ProductionDeploymentCeremony(
                release_record_id=record.id,
                verification_id=verification.id,
                status="OPEN",
                deployment_window_start=approval.deployment_window_start,
                deployment_window_end=approval.deployment_window_end,
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self.production_release._append_ledger(
                session,
                record.id,
                "DEPLOYMENT_CEREMONY_STARTED",
                actor_user_id,
                {
                    "verification_id": verification.verification_id,
                    "package_checksum_sha256": verification.package_checksum_sha256,
                    "deployment_window_start": AuditService._canonical_datetime(start),
                    "deployment_window_end": AuditService._canonical_datetime(end),
                },
            )
            self._audit(session, record, "DEPLOYMENT_CEREMONY_STARTED", actor_user_id)
            session.commit()
            return self._ceremony_view(row)

    def ceremony(
        self, release_record_id: str, actor_user_id: str
    ) -> DeploymentCeremonyView | None:
        with self.database.session() as session:
            self.production_release._require_roles(
                session, actor_user_id, self.production_release.AUTHORIZED_READERS
            )
            self.production_release._get_record(session, release_record_id)
            row = session.scalar(select(ProductionDeploymentCeremony).where(
                ProductionDeploymentCeremony.release_record_id == release_record_id
            ))
            return self._ceremony_view(row) if row else None

    def attest_ceremony(
        self,
        release_record_id: str,
        kind: str,
        actor_user_id: str,
    ) -> DeploymentCeremonyView:
        kind = kind.strip().upper()
        allowed = self.TECHNICAL_ROLES if kind == "TECHNICAL" else self.CLINICAL_ROLES
        if kind not in {"TECHNICAL", "CLINICAL"}:
            raise ProductionEvidenceError("Jenis attestation harus TECHNICAL atau CLINICAL")
        with self.database.session() as session:
            self.production_release._require_roles(session, actor_user_id, allowed)
            record = self.production_release._get_record(session, release_record_id)
            self.production_release._assert_draft(record)
            self.production_release._assert_all_ledgers(session)
            row = session.scalar(select(ProductionDeploymentCeremony).where(
                ProductionDeploymentCeremony.release_record_id == record.id
            ))
            if row is None:
                raise ProductionEvidenceError("Deployment ceremony belum tersedia")
            if row.status != "OPEN":
                raise ProductionEvidenceError("Deployment ceremony sudah terminal")
            now = utc_now()
            if now < self.production_release._as_utc(row.deployment_window_start) or now >= self.production_release._as_utc(row.deployment_window_end):
                raise ProductionEvidenceError("Deployment window tidak aktif")
            verification = self._latest_verification(session, record.id)
            if verification is None or verification.id != row.verification_id or verification.status != "VALID":
                raise ProductionEvidenceError("Binding verifikasi ceremony tidak valid")
            if kind == "TECHNICAL":
                if row.technical_attested_by is not None:
                    raise ProductionEvidenceError("Attestation teknis sudah tersedia")
                if actor_user_id == row.clinical_attested_by:
                    raise ProductionEvidenceError("Attestor teknis dan klinis wajib berbeda")
                row.technical_attested_by = actor_user_id
                row.technical_attested_at = now
            else:
                if row.clinical_attested_by is not None:
                    raise ProductionEvidenceError("Attestation klinis sudah tersedia")
                if actor_user_id == row.technical_attested_by:
                    raise ProductionEvidenceError("Attestor teknis dan klinis wajib berbeda")
                row.clinical_attested_by = actor_user_id
                row.clinical_attested_at = now
            if row.technical_attested_by and row.clinical_attested_by:
                row.status = "ATTESTED"
            row.updated_at = now
            self.production_release._append_ledger(
                session,
                record.id,
                f"DEPLOYMENT_CEREMONY_{kind}_ATTESTED",
                actor_user_id,
                {"ceremony_id": row.id, "status": row.status},
            )
            self._audit(session, record, f"DEPLOYMENT_CEREMONY_{kind}_ATTESTED", actor_user_id)
            session.commit()
            return self._ceremony_view(row)

    def abort_ceremony(
        self, release_record_id: str, reason: str, actor_user_id: str
    ) -> DeploymentCeremonyView:
        reason = self.production_release._validated_reason(reason)
        with self.database.session() as session:
            self.production_release._require_roles(session, actor_user_id, self.EMERGENCY_ROLES)
            record = self.production_release._get_record(session, release_record_id)
            row = session.scalar(select(ProductionDeploymentCeremony).where(
                ProductionDeploymentCeremony.release_record_id == record.id
            ))
            if row is None or row.status != "OPEN":
                raise ProductionEvidenceError("Ceremony OPEN tidak ditemukan")
            now = utc_now()
            row.status = "ABORTED"
            row.aborted_by = actor_user_id
            row.aborted_at = now
            row.abort_reason_hash_sha256 = self.production_release._text_hash(reason)
            row.updated_at = now
            self.production_release._append_ledger(
                session,
                record.id,
                "DEPLOYMENT_CEREMONY_ABORTED",
                actor_user_id,
                {"ceremony_id": row.id, "reason_hash_sha256": row.abort_reason_hash_sha256},
            )
            self._audit(session, record, "DEPLOYMENT_CEREMONY_ABORTED", actor_user_id)
            session.commit()
            return self._ceremony_view(row)

    def export_authorization_receipt(
        self,
        release_record_id: str,
        output_path: Path,
        actor_user_id: str,
    ) -> AuthorizationReceipt:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".json" or not output_path.parent.is_dir():
            raise ProductionEvidenceError("Tujuan receipt wajib file JSON pada folder yang tersedia")
        readiness = self.production_release.evaluate(release_record_id, actor_user_id)
        if not readiness.manual_deployment_authorized:
            raise ProductionEvidenceError("Authorization receipt hanya tersedia untuk authorization aktif")
        with self.database.session() as session:
            record = self.production_release._get_record(session, release_record_id)
            verification = self._latest_verification(session, record.id)
            ceremony = session.scalar(select(ProductionDeploymentCeremony).where(
                ProductionDeploymentCeremony.release_record_id == record.id
            ))
            ledger_head = session.scalar(
                select(ProductionReleaseLedger)
                .order_by(ProductionReleaseLedger.id.desc())
                .limit(1)
            )
            payload = {
                "format": self.RECEIPT_FORMAT,
                "generated_at": AuditService._canonical_datetime(utc_now()),
                "release_record_id": record.id,
                "application_version": record.application_version,
                "schema_revision": record.schema_revision,
                "installer_filename": record.installer_filename,
                "installer_checksum_sha256": record.installer_checksum_sha256,
                "authorization_status": record.status,
                "authorized_by": record.authorized_by,
                "authorized_at": AuditService._canonical_datetime(record.authorized_at),
                "package_checksum_sha256": verification.package_checksum_sha256,
                "evidence_snapshot_sha256": verification.evidence_snapshot_sha256,
                "ceremony_id": ceremony.id,
                "technical_attested_by": ceremony.technical_attested_by,
                "clinical_attested_by": ceremony.clinical_attested_by,
                "deployment_window_start": AuditService._canonical_datetime(ceremony.deployment_window_start),
                "deployment_window_end": AuditService._canonical_datetime(ceremony.deployment_window_end),
                "ledger_head_sha256": ledger_head.entry_hash,
                "deployment_execution": "NOT_PERFORMED_BY_EMSS",
            }
            raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
            try:
                with output_path.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError as exc:
                raise ProductionEvidenceError("Receipt tujuan sudah ada") from exc
            checksum = hashlib.sha256(raw).hexdigest()
            self.production_release._append_ledger(
                session,
                record.id,
                "AUTHORIZATION_RECEIPT_EXPORTED",
                actor_user_id,
                {"receipt_checksum_sha256": checksum},
            )
            self._audit(session, record, "AUTHORIZATION_RECEIPT_EXPORTED", actor_user_id)
            session.commit()
            return AuthorizationReceipt(output_path, checksum)

    def _inspect_package(
        self,
        path: Path,
        record: ProductionReleaseRecord,
        evidence: list[ProductionReleaseEvidence],
        approval: ProductionChangeApproval | None,
    ) -> tuple[str, str, int]:
        if approval is None:
            raise _PackageInvalid("CHANGE_APPROVAL_MISSING", "Change approval belum tersedia")
        try:
            archive = zipfile.ZipFile(path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise _PackageInvalid("ZIP_INVALID", "Paket bukan ZIP valid") from exc
        with archive:
            infos = archive.infolist()
            if not infos or len(infos) > self.MAX_MEMBERS:
                raise _PackageInvalid("MEMBER_COUNT", "Jumlah anggota paket tidak valid")
            names: set[str] = set()
            total = 0
            for info in infos:
                self._validate_member(info, names)
                total += info.file_size
                if total > self.MAX_PACKAGE_BYTES:
                    raise _PackageInvalid("UNCOMPRESSED_LIMIT", "Ukuran uncompressed paket berlebih")
            if "manifest.json" not in names:
                raise _PackageInvalid("MANIFEST_MISSING", "Manifest paket tidak ditemukan")
            manifest_raw = archive.read("manifest.json")
            manifest_checksum = hashlib.sha256(manifest_raw).hexdigest()
            manifest = self._json_object(manifest_raw, "MANIFEST_INVALID")
            if manifest.get("format") != self.PACKAGE_FORMAT:
                raise _PackageInvalid("FORMAT_INVALID", "Format manifest tidak valid")
            expected_binding = {
                "release_record_id": record.id,
                "application_version": record.application_version,
                "schema_revision": record.schema_revision,
                "installer_checksum_sha256": record.installer_checksum_sha256,
            }
            if any(manifest.get(key) != value for key, value in expected_binding.items()):
                raise _PackageInvalid("BINDING_MISMATCH", "Binding manifest tidak cocok")
            entries = manifest.get("evidence")
            change = manifest.get("change_approval")
            if not isinstance(entries, list) or not isinstance(change, dict):
                raise _PackageInvalid("MANIFEST_STRUCTURE", "Struktur manifest tidak valid")
            by_type = {row.evidence_type: row for row in evidence}
            if len(entries) != len(by_type):
                raise _PackageInvalid("EVIDENCE_SET_MISMATCH", "Jumlah evidence tidak cocok")
            declared_paths = {"manifest.json"}
            seen_types: set[str] = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise _PackageInvalid("ENTRY_INVALID", "Entry evidence tidak valid")
                kind = entry.get("evidence_type")
                member = entry.get("path")
                row = by_type.get(kind)
                if row is None or kind in seen_types:
                    raise _PackageInvalid("EVIDENCE_SET_MISMATCH", "Set evidence tidak cocok")
                seen_types.add(kind)
                self._verify_declared_member(archive, names, declared_paths, member, entry, row.evidence_filename, row.evidence_checksum_sha256)
            self._verify_declared_member(
                archive, names, declared_paths, change.get("path"), change,
                approval.evidence_filename, approval.evidence_checksum_sha256,
            )
            if declared_paths != names:
                raise _PackageInvalid("UNDECLARED_MEMBER", "Paket memiliki anggota yang tidak dideklarasikan")
            snapshot = self.production_release.evidence_snapshot_hash(evidence, approval)
            if manifest.get("evidence_snapshot_sha256") != snapshot:
                raise _PackageInvalid("SNAPSHOT_MISMATCH", "Snapshot evidence manifest tidak cocok")
            return manifest_checksum, snapshot, len(entries) + 1

    def _verify_declared_member(
        self,
        archive: zipfile.ZipFile,
        names: set[str],
        declared_paths: set[str],
        member: object,
        declaration: dict[str, Any],
        expected_filename: str,
        expected_checksum: str,
    ) -> None:
        if not isinstance(member, str) or member not in names or member in declared_paths:
            raise _PackageInvalid("MEMBER_BINDING", "Path anggota evidence tidak valid")
        if declaration.get("filename") != expected_filename or declaration.get("checksum_sha256") != expected_checksum:
            raise _PackageInvalid("CHECKSUM_BINDING", "Metadata evidence tidak cocok")
        raw = archive.read(member)
        if hashlib.sha256(raw).hexdigest() != expected_checksum:
            raise _PackageInvalid("CHECKSUM_MISMATCH", "Checksum isi evidence tidak cocok")
        payload = self._json_object(raw, "EVIDENCE_JSON_INVALID")
        if self._contains_sensitive_key(payload):
            raise _PackageInvalid("SENSITIVE_KEY", "Evidence package memuat key identitas pasien")
        declared_paths.add(member)

    def _validate_member(self, info: zipfile.ZipInfo, names: set[str]) -> None:
        name = info.filename
        pure = PurePosixPath(name)
        mode = (info.external_attr >> 16) & 0o170000
        if (
            not name or "\\" in name or pure.is_absolute() or ".." in pure.parts
            or info.is_dir() or name in names or info.flag_bits & 0x1
            or mode == stat.S_IFLNK or info.file_size > self.MAX_MEMBER_BYTES
        ):
            raise _PackageInvalid("UNSAFE_MEMBER", "Anggota ZIP tidak aman")
        names.add(name)

    @staticmethod
    def _json_object(raw: bytes, code: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _PackageInvalid(code, "JSON paket tidak valid") from exc
        if not isinstance(payload, dict):
            raise _PackageInvalid(code, "JSON paket wajib object")
        return payload

    @classmethod
    def _contains_sensitive_key(cls, value: object) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if normalized in cls.FORBIDDEN_KEYS or cls._contains_sensitive_key(nested):
                    return True
        elif isinstance(value, list):
            return any(cls._contains_sensitive_key(item) for item in value)
        return False

    @staticmethod
    def _latest_verification(
        session: Session, release_record_id: str
    ) -> ProductionEvidencePackageVerification | None:
        return session.scalar(
            select(ProductionEvidencePackageVerification)
            .where(ProductionEvidencePackageVerification.release_record_id == release_record_id)
            .order_by(ProductionEvidencePackageVerification.id.desc())
            .limit(1)
        )

    def _audit(
        self,
        session: Session,
        record: ProductionReleaseRecord,
        action: str,
        actor_user_id: str,
    ) -> None:
        self.audit.append(session, AuditEvent(
            category="PRODUCTION_EVIDENCE",
            action=action,
            outcome="SUCCESS",
            actor_user_id=actor_user_id,
            entity_type="PRODUCTION_RELEASE",
            entity_id=record.id,
            details={"status": record.status, "application_version": record.application_version},
        ))

    @staticmethod
    def _verification_view(row: ProductionEvidencePackageVerification) -> EvidencePackageVerificationView:
        return EvidencePackageVerificationView(
            row.id, row.verification_id, row.release_record_id, row.package_filename,
            row.package_checksum_sha256, row.manifest_checksum_sha256,
            row.evidence_snapshot_sha256, row.status, row.error_code,
            row.entry_count, row.verified_by, row.verified_at,
        )

    @staticmethod
    def _ceremony_view(row: ProductionDeploymentCeremony) -> DeploymentCeremonyView:
        return DeploymentCeremonyView(
            row.id, row.release_record_id, row.verification_id, row.status,
            row.deployment_window_start, row.deployment_window_end,
            row.technical_attested_by, row.clinical_attested_by,
            row.created_by, row.created_at,
        )
