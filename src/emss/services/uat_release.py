from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from emss import __version__
from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole, new_uuid
from emss.database.uat_release_models import (
    UatCandidateLedger,
    UatExecutionIssue,
    UatExecutionLedger,
    UatExecutionResult,
    UatExecutionSession,
    UatReadinessEvidence,
    UatReleaseCandidate,
)
from emss.utils.time import utc_now


class UatReleaseError(ValueError):
    pass


class UatReleasePermissionError(UatReleaseError):
    pass


@dataclass(frozen=True)
class UatCandidateView:
    id: str
    application_version: str
    schema_revision: str
    environment_label: str
    installer_filename: str
    installer_checksum_sha256: str
    status: str
    expires_at: datetime
    clinical_attested_by: str | None
    technical_attested_by: str | None
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class UatEvidenceView:
    evidence_type: str
    evidence_filename: str
    evidence_checksum_sha256: str
    observed_at: datetime
    valid_until: datetime | None
    recorded_by: str


@dataclass(frozen=True)
class UatExecutionView:
    id: str
    candidate_id: str
    status: str
    window_start: datetime
    window_end: datetime
    clinical_signed_by: str | None
    technical_signed_by: str | None
    decided_by: str | None
    created_by: str


@dataclass(frozen=True)
class UatResultView:
    id: int
    scenario_code: str
    owner_type: str
    status: str
    evidence_filename: str
    evidence_checksum_sha256: str
    observed_at: datetime
    tested_by: str


@dataclass(frozen=True)
class UatIssueView:
    id: str
    issue_number: int
    severity: str
    status: str
    summary_hash_sha256: str
    resolution_hash_sha256: str | None


@dataclass(frozen=True)
class UatReadiness:
    candidate: UatCandidateView
    execution: UatExecutionView | None
    evidence_types: tuple[str, ...]
    latest_results: tuple[UatResultView, ...]
    open_issues: int
    candidate_ledger_valid: bool
    execution_ledger_valid: bool
    ready_to_start: bool
    ready_for_acceptance: bool
    uat_accepted_active: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class UatExport:
    path: Path
    checksum_sha256: str


@dataclass(frozen=True)
class UatLedgerView:
    source: str
    sequence: int
    event_type: str
    actor_user_id: str | None
    occurred_at: datetime
    entry_hash: str


class UatReleaseService:
    """Release-candidate UAT evidence governance; never performs UAT or deployment."""

    CANDIDATE_FORMAT = "EMSS_UAT_RELEASE_CANDIDATE_V1"
    EVIDENCE_FORMAT = "EMSS_UAT_READINESS_EVIDENCE_V1"
    RESULT_FORMAT = "EMSS_UAT_EXECUTION_RESULT_V1"
    KIT_FORMAT = "EMSS_UAT_EXECUTION_KIT_V1"
    RECEIPT_FORMAT = "EMSS_UAT_ACCEPTANCE_RECEIPT_V1"
    GENESIS_HASH = "0" * 64
    MAX_JSON_BYTES = 5 * 1024 * 1024
    READERS = frozenset({"SUPER_ADMIN", "IT_ADMIN", "DIREKTUR", "APOTEKER", "CLINICAL_REVIEWER", "KFT"})
    TECHNICAL = frozenset({"SUPER_ADMIN", "IT_ADMIN"})
    CLINICAL = frozenset({"APOTEKER", "CLINICAL_REVIEWER", "KFT"})
    DECISION = frozenset({"DIREKTUR"})
    EMERGENCY = TECHNICAL | DECISION
    EVIDENCE_TYPES = frozenset({
        "SITE_APPROVAL", "TEST_DATA_APPROVAL", "USER_ROSTER", "CLEAN_HOST",
        "BACKUP_RESTORE", "KHANZA_READ_ONLY", "TRAINING_SOP",
    })
    EVIDENCE_CONTROL_FIELDS = {
        "SITE_APPROVAL": "site_approved",
        "TEST_DATA_APPROVAL": "deidentified_test_data",
        "USER_ROSTER": "named_accounts_verified",
        "CLEAN_HOST": "clean_host_verified",
        "BACKUP_RESTORE": "backup_restore_verified",
        "KHANZA_READ_ONLY": "select_only_verified",
        "TRAINING_SOP": "training_and_sop_verified",
    }
    SCENARIOS = {
        "CLINICAL_DDI_CRITICAL": "CLINICAL",
        "CLINICAL_HIGH_RISK": "CLINICAL",
        "CLINICAL_DUPLICATE_THERAPY": "CLINICAL",
        "CLINICAL_HIGH_ALERT_LASA": "CLINICAL",
        "TECH_KHANZA_READ_ONLY": "TECHNICAL",
        "TECH_POLLING_RECONNECT": "TECHNICAL",
        "TECH_CLEAN_INSTALL": "TECHNICAL",
        "TECH_UPGRADE_DATA_PRESERVATION": "TECHNICAL",
        "TECH_BACKUP_RESTORE": "TECHNICAL",
        "TECH_SILENT_MODE_ACCESS_AUDIT": "TECHNICAL",
    }
    FORBIDDEN_KEYS = frozenset({
        "patient", "patient_id", "patient_name", "pasien", "nama_pasien",
        "no_rm", "nomor_rm", "medical_record", "medical_record_number",
        "no_resep", "nomor_resep", "prescription_number", "doctor_name",
    })

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    # Sprint 21: release-candidate dossier.
    def create_candidate(
        self,
        qualification_path: Path,
        installer_path: Path,
        environment_label: str,
        actor_user_id: str,
        *,
        validity_days: int = 14,
    ) -> UatCandidateView:
        if not 1 <= validity_days <= 30:
            raise UatReleaseError("Masa dossier UAT wajib 1-30 hari")
        environment_label = environment_label.strip()
        if not 3 <= len(environment_label) <= 120:
            raise UatReleaseError("Label environment wajib 3-120 karakter")
        qualification_path = Path(qualification_path)
        installer_path = Path(installer_path)
        payload, qualification_raw = self._json_file(qualification_path)
        if not installer_path.is_file():
            raise UatReleaseError("Installer release candidate tidak ditemukan")
        installer_checksum = self._file_hash(installer_path)
        current_revision = self.database.current_revision()
        if (
            payload.get("format") != "EMSS_RELEASE_QUALIFICATION_V1"
            or payload.get("status") != "QUALIFIED"
            or payload.get("application_version") != __version__
            or payload.get("schema_revision") != current_revision
        ):
            raise UatReleaseError("Qualification tidak cocok dengan release aktif")
        artifact = next(
            (
                row for row in payload.get("artifacts", [])
                if isinstance(row, dict)
                and Path(str(row.get("path", ""))).name == installer_path.name
            ),
            None,
        )
        if artifact is None or artifact.get("checksum_sha256") != installer_checksum:
            raise UatReleaseError("Installer tidak terikat pada qualification")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL)
            self._assert_ledgers(session)
            if session.scalar(select(UatReleaseCandidate).where(
                UatReleaseCandidate.status.in_(("DRAFT", "SEALED"))
            )) is not None:
                raise UatReleaseError("Masih ada dossier UAT aktif")
            now = utc_now()
            row = UatReleaseCandidate(
                application_version=__version__,
                schema_revision=current_revision,
                qualification_filename=qualification_path.name,
                qualification_checksum_sha256=hashlib.sha256(qualification_raw).hexdigest(),
                installer_filename=installer_path.name,
                installer_checksum_sha256=installer_checksum,
                environment_label=environment_label,
                status="DRAFT",
                expires_at=now + timedelta(days=validity_days),
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._append_candidate_ledger(session, row.id, "CANDIDATE_CREATED", actor_user_id, {
                "application_version": row.application_version,
                "schema_revision": row.schema_revision,
                "qualification_checksum_sha256": row.qualification_checksum_sha256,
                "installer_checksum_sha256": row.installer_checksum_sha256,
                "environment_label": row.environment_label,
                "expires_at": self._canonical_time(row.expires_at),
            })
            self._audit(session, "UAT_CANDIDATE_CREATED", row.id, actor_user_id, row.status)
            session.commit()
            return self._candidate_view(row)

    def candidates(self, actor_user_id: str) -> tuple[UatCandidateView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            rows = session.scalars(select(UatReleaseCandidate).order_by(UatReleaseCandidate.created_at.desc())).all()
            return tuple(self._candidate_view(row) for row in rows)

    def record_readiness_evidence(
        self, candidate_id: str, evidence_type: str, evidence_path: Path, actor_user_id: str
    ) -> UatEvidenceView:
        evidence_type = evidence_type.strip().upper()
        if evidence_type not in self.EVIDENCE_TYPES:
            raise UatReleaseError("Jenis readiness evidence tidak valid")
        payload, raw = self._json_file(Path(evidence_path))
        if self._contains_sensitive_key(payload):
            raise UatReleaseError("Readiness evidence memuat key identitas pasien")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.TECHNICAL)
            candidate = self._get_candidate(session, candidate_id)
            self._assert_candidate_draft(candidate)
            self._assert_ledgers(session)
            if session.scalar(select(UatReadinessEvidence).where(
                UatReadinessEvidence.candidate_id == candidate.id,
                UatReadinessEvidence.evidence_type == evidence_type,
            )) is not None:
                raise UatReleaseError("Evidence type sudah tersedia dan immutable")
            expected = {
                "format": self.EVIDENCE_FORMAT,
                "evidence_type": evidence_type,
                "status": "PASS",
                "application_version": candidate.application_version,
                "schema_revision": candidate.schema_revision,
                "installer_checksum_sha256": candidate.installer_checksum_sha256,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise UatReleaseError("Readiness evidence tidak terikat pada candidate")
            if payload.get(self.EVIDENCE_CONTROL_FIELDS[evidence_type]) is not True:
                raise UatReleaseError("Kontrol readiness evidence belum terverifikasi")
            observed = self._parse_time(payload.get("observed_at"), "observed_at")
            now = utc_now()
            if observed > now + timedelta(minutes=5) or observed < now - timedelta(days=90):
                raise UatReleaseError("Readiness evidence berada di luar freshness policy")
            valid_until = None
            if payload.get("valid_until") is not None:
                valid_until = self._parse_time(payload.get("valid_until"), "valid_until")
                if valid_until <= now or valid_until > self._as_utc(candidate.expires_at):
                    raise UatReleaseError("Masa berlaku evidence tidak valid")
            row = UatReadinessEvidence(
                candidate_id=candidate.id,
                evidence_type=evidence_type,
                evidence_filename=Path(evidence_path).name,
                evidence_checksum_sha256=hashlib.sha256(raw).hexdigest(),
                observed_at=observed,
                valid_until=valid_until,
                recorded_by=actor_user_id,
                recorded_at=now,
            )
            session.add(row)
            session.flush()
            self._append_candidate_ledger(session, candidate.id, "READINESS_EVIDENCE_RECORDED", actor_user_id, {
                "evidence_type": evidence_type,
                "evidence_checksum_sha256": row.evidence_checksum_sha256,
                "observed_at": self._canonical_time(observed),
            })
            self._audit(session, "UAT_READINESS_EVIDENCE_RECORDED", candidate.id, actor_user_id, candidate.status)
            session.commit()
            return self._evidence_view(row)

    def readiness_evidence(self, candidate_id: str, actor_user_id: str) -> tuple[UatEvidenceView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            self._get_candidate(session, candidate_id)
            rows = session.scalars(select(UatReadinessEvidence).where(
                UatReadinessEvidence.candidate_id == candidate_id
            ).order_by(UatReadinessEvidence.evidence_type)).all()
            return tuple(self._evidence_view(row) for row in rows)

    def attest_candidate(self, candidate_id: str, kind: str, actor_user_id: str) -> UatCandidateView:
        kind = kind.strip().upper()
        if kind not in {"CLINICAL", "TECHNICAL"}:
            raise UatReleaseError("Jenis attestation harus CLINICAL atau TECHNICAL")
        roles = self.CLINICAL if kind == "CLINICAL" else self.TECHNICAL
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, roles)
            candidate = self._get_candidate(session, candidate_id)
            self._assert_candidate_draft(candidate)
            self._assert_ledgers(session)
            evidence = list(session.scalars(select(UatReadinessEvidence).where(
                UatReadinessEvidence.candidate_id == candidate.id
            )).all())
            blockers = self._candidate_blockers(candidate, evidence)
            if blockers:
                raise UatReleaseError("Attestation ditolak: " + "; ".join(blockers))
            preparers = {candidate.created_by, *(row.recorded_by for row in evidence)}
            if actor_user_id in preparers:
                raise UatReleaseError("Attestor wajib independen dari pembuat/recorder dossier")
            if actor_user_id in {candidate.clinical_attested_by, candidate.technical_attested_by}:
                raise UatReleaseError("Attestor klinis dan teknis wajib berbeda")
            snapshot = self._evidence_snapshot(evidence)
            if candidate.evidence_snapshot_sha256 not in {None, snapshot}:
                raise UatReleaseError("Snapshot evidence berubah setelah attestation")
            now = utc_now()
            candidate.evidence_snapshot_sha256 = snapshot
            if kind == "CLINICAL":
                if candidate.clinical_attested_by:
                    raise UatReleaseError("Attestation klinis sudah tersedia")
                candidate.clinical_attested_by = actor_user_id
                candidate.clinical_attested_at = now
            else:
                if candidate.technical_attested_by:
                    raise UatReleaseError("Attestation teknis sudah tersedia")
                candidate.technical_attested_by = actor_user_id
                candidate.technical_attested_at = now
            if candidate.clinical_attested_by and candidate.technical_attested_by:
                candidate.status = "SEALED"
            candidate.updated_at = now
            self._append_candidate_ledger(session, candidate.id, f"CANDIDATE_{kind}_ATTESTED", actor_user_id, {
                "evidence_snapshot_sha256": snapshot, "status": candidate.status,
            })
            self._audit(session, f"UAT_CANDIDATE_{kind}_ATTESTED", candidate.id, actor_user_id, candidate.status)
            session.commit()
            return self._candidate_view(candidate)

    def revoke_candidate(self, candidate_id: str, reason: str, actor_user_id: str) -> UatCandidateView:
        reason = self._reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.EMERGENCY)
            candidate = self._get_candidate(session, candidate_id)
            if candidate.status not in {"DRAFT", "SEALED"}:
                raise UatReleaseError("Dossier UAT sudah terminal")
            now = utc_now()
            candidate.status = "REVOKED"
            candidate.revoked_by = actor_user_id
            candidate.revoked_at = now
            candidate.revocation_reason_hash_sha256 = self._text_hash(reason)
            candidate.updated_at = now
            self._append_candidate_ledger(session, candidate.id, "CANDIDATE_REVOKED", actor_user_id, {
                "reason_hash_sha256": candidate.revocation_reason_hash_sha256,
            })
            self._audit(session, "UAT_CANDIDATE_REVOKED", candidate.id, actor_user_id, candidate.status)
            session.commit()
            return self._candidate_view(candidate)

    def export_uat_kit(self, candidate_id: str, output_path: Path, actor_user_id: str) -> UatExport:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".zip" or not output_path.parent.is_dir():
            raise UatReleaseError("Tujuan kit wajib ZIP pada folder yang tersedia")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            candidate = self._get_candidate(session, candidate_id)
            if candidate.status == "REVOKED" or self._as_utc(candidate.expires_at) <= utc_now():
                raise UatReleaseError("Dossier UAT tidak aktif")
            manifest = {
                "format": self.KIT_FORMAT,
                "generated_at": self._canonical_time(utc_now()),
                "candidate_id": candidate.id,
                "application_version": candidate.application_version,
                "schema_revision": candidate.schema_revision,
                "installer_filename": candidate.installer_filename,
                "installer_checksum_sha256": candidate.installer_checksum_sha256,
                "environment_label": candidate.environment_label,
                "candidate_status": candidate.status,
                "execution_status": "NOT_STARTED",
                "production_authorization": "NOT_GRANTED_BY_UAT_KIT",
                "scenarios": [
                    {"scenario_code": code, "owner_type": owner, "result": "NOT_RECORDED"}
                    for code, owner in sorted(self.SCENARIOS.items())
                ],
            }
            try:
                with zipfile.ZipFile(output_path, "x", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                    archive.writestr(
                        "README.txt",
                        "Kit ini hanya rencana UAT. Isi hasil berdasarkan pelaksanaan aktual rumah sakit.\n"
                        "Jangan memasukkan identitas pasien. Kit tidak menjalankan UAT atau deployment.\n",
                    )
            except FileExistsError as exc:
                raise UatReleaseError("File kit tujuan sudah ada") from exc
            checksum = self._file_hash(output_path)
            self._append_candidate_ledger(session, candidate.id, "UAT_KIT_EXPORTED", actor_user_id, {
                "kit_checksum_sha256": checksum,
            })
            self._audit(session, "UAT_KIT_EXPORTED", candidate.id, actor_user_id, candidate.status)
            session.commit()
            return UatExport(output_path, checksum)

    # Sprint 22: externally executed UAT and independent acceptance.
    def start_execution(
        self, candidate_id: str, actor_user_id: str, *, duration_hours: int = 8
    ) -> UatExecutionView:
        if not 1 <= duration_hours <= 168:
            raise UatReleaseError("Durasi execution window wajib 1-168 jam")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION)
            candidate = self._get_candidate(session, candidate_id)
            self._assert_candidate_sealed(candidate, session)
            if session.scalar(select(UatExecutionSession).where(
                UatExecutionSession.candidate_id == candidate.id
            )) is not None:
                raise UatReleaseError("Candidate sudah memiliki execution session")
            now = utc_now()
            end = min(now + timedelta(hours=duration_hours), self._as_utc(candidate.expires_at))
            if end <= now:
                raise UatReleaseError("Execution window tidak valid")
            row = UatExecutionSession(
                candidate_id=candidate.id,
                status="OPEN",
                window_start=now,
                window_end=end,
                created_by=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._append_execution_ledger(session, row.id, "EXECUTION_STARTED", actor_user_id, {
                "candidate_id": candidate.id,
                "window_start": self._canonical_time(now),
                "window_end": self._canonical_time(end),
            })
            self._audit(session, "UAT_EXECUTION_STARTED", row.id, actor_user_id, row.status)
            session.commit()
            return self._execution_view(row)

    def execution(self, candidate_id: str, actor_user_id: str) -> UatExecutionView | None:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            self._get_candidate(session, candidate_id)
            row = session.scalar(select(UatExecutionSession).where(
                UatExecutionSession.candidate_id == candidate_id
            ))
            return self._execution_view(row) if row else None

    def record_result(self, session_id: str, evidence_path: Path, actor_user_id: str) -> UatResultView:
        payload, raw = self._json_file(Path(evidence_path))
        if self._contains_sensitive_key(payload):
            raise UatReleaseError("UAT result evidence memuat key identitas pasien")
        scenario = str(payload.get("scenario_code", "")).strip().upper()
        owner = self.SCENARIOS.get(scenario)
        if owner is None:
            raise UatReleaseError("Scenario UAT tidak valid")
        allowed = self.CLINICAL if owner == "CLINICAL" else self.TECHNICAL
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, allowed)
            execution = self._get_execution(session, session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            self._assert_execution_open(execution, candidate, session)
            expected = {
                "format": self.RESULT_FORMAT,
                "candidate_id": candidate.id,
                "session_id": execution.id,
                "application_version": candidate.application_version,
                "schema_revision": candidate.schema_revision,
                "installer_checksum_sha256": candidate.installer_checksum_sha256,
                "scenario_code": scenario,
                "owner_type": owner,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise UatReleaseError("UAT result tidak terikat pada session")
            status = str(payload.get("status", "")).strip().upper()
            if status not in {"PASS", "FAIL", "BLOCKED"}:
                raise UatReleaseError("Status UAT result tidak valid")
            summary = str(payload.get("result_summary", "")).strip()
            if not 10 <= len(summary) <= 500:
                raise UatReleaseError("Ringkasan hasil wajib 10-500 karakter")
            observed = self._parse_time(payload.get("observed_at"), "observed_at")
            if not self._as_utc(execution.window_start) <= observed <= min(utc_now() + timedelta(minutes=5), self._as_utc(execution.window_end)):
                raise UatReleaseError("Waktu hasil di luar execution window")
            row = UatExecutionResult(
                session_id=execution.id,
                scenario_code=scenario,
                owner_type=owner,
                status=status,
                evidence_filename=Path(evidence_path).name,
                evidence_checksum_sha256=hashlib.sha256(raw).hexdigest(),
                result_summary_hash_sha256=self._text_hash(summary),
                observed_at=observed,
                tested_by=actor_user_id,
                recorded_at=utc_now(),
            )
            session.add(row)
            session.flush()
            self._clear_execution_signoffs(execution)
            self._append_execution_ledger(session, execution.id, "RESULT_RECORDED", actor_user_id, {
                "result_id": row.result_id,
                "scenario_code": scenario,
                "owner_type": owner,
                "status": status,
                "evidence_checksum_sha256": row.evidence_checksum_sha256,
                "result_summary_hash_sha256": row.result_summary_hash_sha256,
            })
            self._audit(session, "UAT_RESULT_RECORDED", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._result_view(row)

    def results(self, session_id: str, actor_user_id: str) -> tuple[UatResultView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            self._get_execution(session, session_id)
            rows = session.scalars(select(UatExecutionResult).where(
                UatExecutionResult.session_id == session_id
            ).order_by(UatExecutionResult.id)).all()
            return tuple(self._result_view(row) for row in rows)

    def raise_issue(
        self, session_id: str, severity: str, summary: str, actor_user_id: str
    ) -> UatIssueView:
        severity = severity.strip().upper()
        if severity not in {"WARNING", "CRITICAL"}:
            raise UatReleaseError("Severity issue harus WARNING atau CRITICAL")
        summary = self._reason(summary)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.CLINICAL | self.TECHNICAL)
            execution = self._get_execution(session, session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            self._assert_execution_open(execution, candidate, session)
            number = (session.scalar(select(func.max(UatExecutionIssue.issue_number)).where(
                UatExecutionIssue.session_id == execution.id
            )) or 0) + 1
            row = UatExecutionIssue(
                session_id=execution.id,
                issue_number=number,
                severity=severity,
                status="OPEN",
                summary_hash_sha256=self._text_hash(summary),
                raised_by=actor_user_id,
                raised_at=utc_now(),
            )
            session.add(row)
            session.flush()
            self._clear_execution_signoffs(execution)
            self._append_execution_ledger(session, execution.id, "ISSUE_RAISED", actor_user_id, {
                "issue_number": number, "severity": severity,
                "summary_hash_sha256": row.summary_hash_sha256,
            })
            self._audit(session, "UAT_ISSUE_RAISED", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._issue_view(row)

    def resolve_issue(self, issue_id: str, resolution: str, actor_user_id: str) -> UatIssueView:
        resolution = self._reason(resolution)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.CLINICAL | self.TECHNICAL)
            issue = session.get(UatExecutionIssue, issue_id)
            if issue is None or issue.status != "OPEN":
                raise UatReleaseError("Issue OPEN tidak ditemukan")
            execution = self._get_execution(session, issue.session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            self._assert_execution_open(execution, candidate, session)
            issue.status = "RESOLVED"
            issue.resolution_hash_sha256 = self._text_hash(resolution)
            issue.resolved_by = actor_user_id
            issue.resolved_at = utc_now()
            self._clear_execution_signoffs(execution)
            self._append_execution_ledger(session, execution.id, "ISSUE_RESOLVED", actor_user_id, {
                "issue_number": issue.issue_number,
                "resolution_hash_sha256": issue.resolution_hash_sha256,
            })
            self._audit(session, "UAT_ISSUE_RESOLVED", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._issue_view(issue)

    def issues(self, session_id: str, actor_user_id: str) -> tuple[UatIssueView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            self._get_execution(session, session_id)
            rows = session.scalars(select(UatExecutionIssue).where(
                UatExecutionIssue.session_id == session_id
            ).order_by(UatExecutionIssue.issue_number)).all()
            return tuple(self._issue_view(row) for row in rows)

    def sign_execution(self, session_id: str, kind: str, actor_user_id: str) -> UatExecutionView:
        kind = kind.strip().upper()
        if kind not in {"CLINICAL", "TECHNICAL"}:
            raise UatReleaseError("Jenis sign-off harus CLINICAL atau TECHNICAL")
        allowed = self.CLINICAL if kind == "CLINICAL" else self.TECHNICAL
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, allowed)
            execution = self._get_execution(session, session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            self._assert_execution_open(execution, candidate, session)
            latest = self._latest_results(session, execution.id)
            issues = list(session.scalars(select(UatExecutionIssue).where(
                UatExecutionIssue.session_id == execution.id
            )).all())
            blockers = self._execution_blockers(execution, candidate, latest, issues, session)
            if blockers:
                raise UatReleaseError("Sign-off ditolak: " + "; ".join(blockers))
            testers = {row.tested_by for row in latest.values() if row.owner_type == kind}
            if actor_user_id in testers or actor_user_id == execution.created_by:
                raise UatReleaseError("Signatory wajib independen dari tester/creator")
            if actor_user_id in {execution.clinical_signed_by, execution.technical_signed_by}:
                raise UatReleaseError("Signatory klinis dan teknis wajib berbeda")
            snapshot = self._results_snapshot(latest, issues)
            if execution.results_snapshot_sha256 not in {None, snapshot}:
                raise UatReleaseError("Snapshot hasil berubah setelah sign-off")
            now = utc_now()
            execution.results_snapshot_sha256 = snapshot
            if kind == "CLINICAL":
                if execution.clinical_signed_by:
                    raise UatReleaseError("Sign-off klinis sudah tersedia")
                execution.clinical_signed_by = actor_user_id
                execution.clinical_signed_at = now
            else:
                if execution.technical_signed_by:
                    raise UatReleaseError("Sign-off teknis sudah tersedia")
                execution.technical_signed_by = actor_user_id
                execution.technical_signed_at = now
            execution.updated_at = now
            self._append_execution_ledger(session, execution.id, f"EXECUTION_{kind}_SIGNED", actor_user_id, {
                "results_snapshot_sha256": snapshot,
            })
            self._audit(session, f"UAT_EXECUTION_{kind}_SIGNED", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._execution_view(execution)

    def decide_execution(
        self, session_id: str, decision: str, reason: str, actor_user_id: str
    ) -> UatExecutionView:
        decision = decision.strip().upper()
        if decision not in {"ACCEPT", "REJECT"}:
            raise UatReleaseError("Keputusan harus ACCEPT atau REJECT")
        reason = self._reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION)
            execution = self._get_execution(session, session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            self._assert_execution_open(execution, candidate, session)
            latest = self._latest_results(session, execution.id)
            issues = list(session.scalars(select(UatExecutionIssue).where(
                UatExecutionIssue.session_id == execution.id
            )).all())
            if decision == "ACCEPT":
                blockers = self._execution_blockers(execution, candidate, latest, issues, session)
                snapshot = self._results_snapshot(latest, issues)
                if not execution.clinical_signed_by or not execution.technical_signed_by:
                    blockers.append("Dual sign-off belum lengkap")
                if execution.results_snapshot_sha256 != snapshot:
                    blockers.append("Sign-off tidak terikat snapshot hasil terbaru")
                if blockers:
                    raise UatReleaseError("Acceptance ditolak: " + "; ".join(blockers))
            actors = {
                candidate.created_by, execution.created_by,
                candidate.clinical_attested_by, candidate.technical_attested_by,
                execution.clinical_signed_by, execution.technical_signed_by,
                *(row.tested_by for row in latest.values()),
                *(row.raised_by for row in issues),
                *(row.resolved_by for row in issues),
            }
            actors.discard(None)
            if actor_user_id in actors:
                raise UatReleaseError("Decision maker UAT wajib independen")
            now = utc_now()
            execution.status = "ACCEPTED" if decision == "ACCEPT" else "REJECTED"
            execution.decided_by = actor_user_id
            execution.decided_at = now
            execution.decision_reason_hash_sha256 = self._text_hash(reason)
            execution.updated_at = now
            self._append_execution_ledger(session, execution.id, f"UAT_{execution.status}", actor_user_id, {
                "reason_hash_sha256": execution.decision_reason_hash_sha256,
                "results_snapshot_sha256": execution.results_snapshot_sha256,
            })
            self._audit(session, f"UAT_{execution.status}", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._execution_view(execution)

    def revoke_acceptance(self, session_id: str, reason: str, actor_user_id: str) -> UatExecutionView:
        reason = self._reason(reason)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.DECISION)
            execution = self._get_execution(session, session_id)
            if execution.status != "ACCEPTED":
                raise UatReleaseError("UAT acceptance aktif tidak ditemukan")
            now = utc_now()
            execution.status = "REVOKED"
            execution.revoked_by = actor_user_id
            execution.revoked_at = now
            execution.revocation_reason_hash_sha256 = self._text_hash(reason)
            execution.updated_at = now
            self._append_execution_ledger(session, execution.id, "UAT_ACCEPTANCE_REVOKED", actor_user_id, {
                "reason_hash_sha256": execution.revocation_reason_hash_sha256,
            })
            self._audit(session, "UAT_ACCEPTANCE_REVOKED", execution.id, actor_user_id, execution.status)
            session.commit()
            return self._execution_view(execution)

    def evaluate(self, candidate_id: str, actor_user_id: str | None = None) -> UatReadiness:
        with self.database.session() as session:
            if actor_user_id is not None:
                self._require_roles(session, actor_user_id, self.READERS)
            candidate = self._get_candidate(session, candidate_id)
            evidence = list(session.scalars(select(UatReadinessEvidence).where(
                UatReadinessEvidence.candidate_id == candidate.id
            )).all())
            execution = session.scalar(select(UatExecutionSession).where(
                UatExecutionSession.candidate_id == candidate.id
            ))
            latest = self._latest_results(session, execution.id) if execution else {}
            issues = list(session.scalars(select(UatExecutionIssue).where(
                UatExecutionIssue.session_id == execution.id
            )).all()) if execution else []
            candidate_ledger = self._verify_candidate_ledger(session)
            execution_ledger = self._verify_execution_ledger(session)
            blockers = self._candidate_blockers(candidate, evidence)
            if not candidate_ledger:
                blockers.append("Candidate ledger tidak valid")
            if candidate.status == "REVOKED":
                blockers.append("Dossier UAT telah dicabut")
            if candidate.status != "SEALED":
                blockers.append("Dossier UAT belum SEALED")
            ready_to_start = not blockers
            acceptance_blockers = list(blockers)
            if execution is None:
                acceptance_blockers.append("Execution session belum tersedia")
            else:
                acceptance_blockers.extend(self._execution_blockers(execution, candidate, latest, issues, session))
                if not execution_ledger:
                    acceptance_blockers.append("Execution ledger tidak valid")
                if not execution.clinical_signed_by or not execution.technical_signed_by:
                    acceptance_blockers.append("Dual sign-off execution belum lengkap")
                if execution.status not in {"OPEN", "ACCEPTED"}:
                    acceptance_blockers.append(f"Execution status {execution.status}")
            ready_for_acceptance = bool(execution and execution.status == "OPEN" and not acceptance_blockers)
            active = bool(
                execution and execution.status == "ACCEPTED"
                and candidate.status == "SEALED"
                and self._as_utc(candidate.expires_at) > utc_now()
                and candidate_ledger and execution_ledger
            )
            return UatReadiness(
                candidate=self._candidate_view(candidate),
                execution=self._execution_view(execution) if execution else None,
                evidence_types=tuple(sorted(row.evidence_type for row in evidence)),
                latest_results=tuple(self._result_view(row) for _, row in sorted(latest.items())),
                open_issues=sum(row.status == "OPEN" for row in issues),
                candidate_ledger_valid=candidate_ledger,
                execution_ledger_valid=execution_ledger,
                ready_to_start=ready_to_start,
                ready_for_acceptance=ready_for_acceptance,
                uat_accepted_active=active,
                blockers=tuple(dict.fromkeys(acceptance_blockers)),
            )

    def ledger(self, candidate_id: str, actor_user_id: str) -> tuple[UatLedgerView, ...]:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            self._get_candidate(session, candidate_id)
            candidate_rows = session.scalars(select(UatCandidateLedger).where(
                UatCandidateLedger.candidate_id == candidate_id
            ).order_by(UatCandidateLedger.id)).all()
            execution = session.scalar(select(UatExecutionSession).where(
                UatExecutionSession.candidate_id == candidate_id
            ))
            execution_rows = session.scalars(select(UatExecutionLedger).where(
                UatExecutionLedger.session_id == execution.id
            ).order_by(UatExecutionLedger.id)).all() if execution else []
            return tuple(
                [UatLedgerView("DOSSIER", row.id, row.event_type, row.actor_user_id, row.occurred_at, row.entry_hash) for row in candidate_rows]
                + [UatLedgerView("EXECUTION", row.id, row.event_type, row.actor_user_id, row.occurred_at, row.entry_hash) for row in execution_rows]
            )

    def export_acceptance_receipt(
        self, session_id: str, output_path: Path, actor_user_id: str
    ) -> UatExport:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".json" or not output_path.parent.is_dir():
            raise UatReleaseError("Tujuan receipt wajib JSON pada folder yang tersedia")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.READERS)
            execution = self._get_execution(session, session_id)
            candidate = self._get_candidate(session, execution.candidate_id)
            readiness = self.evaluate(candidate.id, actor_user_id)
            if not readiness.uat_accepted_active:
                raise UatReleaseError("UAT acceptance aktif tidak tersedia")
            ledger_head = session.scalar(select(UatExecutionLedger).order_by(UatExecutionLedger.id.desc()).limit(1))
            payload = {
                "format": self.RECEIPT_FORMAT,
                "generated_at": self._canonical_time(utc_now()),
                "candidate_id": candidate.id,
                "session_id": execution.id,
                "application_version": candidate.application_version,
                "schema_revision": candidate.schema_revision,
                "installer_filename": candidate.installer_filename,
                "installer_checksum_sha256": candidate.installer_checksum_sha256,
                "status": execution.status,
                "accepted_by": execution.decided_by,
                "accepted_at": self._canonical_time(execution.decided_at),
                "results_snapshot_sha256": execution.results_snapshot_sha256,
                "ledger_head_sha256": ledger_head.entry_hash,
                "execution_origin": "EXTERNAL_HOSPITAL_EVIDENCE",
                "production_authorization": "NOT_GRANTED_BY_UAT_ACCEPTANCE",
            }
            raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
            try:
                with output_path.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError as exc:
                raise UatReleaseError("Receipt tujuan sudah ada") from exc
            checksum = hashlib.sha256(raw).hexdigest()
            self._append_execution_ledger(session, execution.id, "ACCEPTANCE_RECEIPT_EXPORTED", actor_user_id, {
                "receipt_checksum_sha256": checksum,
            })
            self._audit(session, "UAT_ACCEPTANCE_RECEIPT_EXPORTED", execution.id, actor_user_id, execution.status)
            session.commit()
            return UatExport(output_path, checksum)

    # Shared validation and immutable ledgers.
    def _candidate_blockers(self, candidate: UatReleaseCandidate, evidence: list[UatReadinessEvidence]) -> list[str]:
        blockers: list[str] = []
        now = utc_now()
        if candidate.application_version != __version__ or candidate.schema_revision != self.database.current_revision():
            blockers.append("Candidate bukan release aktif")
        if self._as_utc(candidate.expires_at) <= now:
            blockers.append("Dossier UAT kedaluwarsa")
        by_type = {row.evidence_type: row for row in evidence}
        missing = sorted(self.EVIDENCE_TYPES - by_type.keys())
        if missing:
            blockers.append("Readiness evidence belum lengkap: " + ", ".join(missing))
        if any(row.valid_until and self._as_utc(row.valid_until) <= now for row in evidence):
            blockers.append("Readiness evidence kedaluwarsa")
        if evidence and candidate.evidence_snapshot_sha256 and candidate.evidence_snapshot_sha256 != self._evidence_snapshot(evidence):
            blockers.append("Snapshot readiness evidence tidak cocok")
        return blockers

    def _execution_blockers(
        self,
        execution: UatExecutionSession,
        candidate: UatReleaseCandidate,
        latest: dict[str, UatExecutionResult],
        issues: list[UatExecutionIssue],
        session: Session,
    ) -> list[str]:
        blockers: list[str] = []
        now = utc_now()
        if candidate.status != "SEALED" or self._as_utc(candidate.expires_at) <= now:
            blockers.append("Dossier UAT tidak aktif")
        if execution.status not in {"OPEN", "ACCEPTED"}:
            blockers.append(f"Execution status {execution.status}")
        if execution.status == "OPEN" and not self._as_utc(execution.window_start) <= now < self._as_utc(execution.window_end):
            blockers.append("Execution window tidak aktif")
        missing = sorted(set(self.SCENARIOS) - latest.keys())
        if missing:
            blockers.append("Scenario belum lengkap: " + ", ".join(missing))
        failed = sorted(code for code, row in latest.items() if row.status != "PASS")
        if failed:
            blockers.append("Scenario latest belum PASS: " + ", ".join(failed))
        if any(row.status == "OPEN" for row in issues):
            blockers.append("Masih ada issue UAT terbuka")
        if not self._verify_candidate_ledger(session) or not self._verify_execution_ledger(session):
            blockers.append("Ledger UAT tidak valid")
        return blockers

    def _assert_candidate_draft(self, candidate: UatReleaseCandidate) -> None:
        if candidate.status != "DRAFT":
            raise UatReleaseError("Dossier UAT bukan DRAFT")
        if self._as_utc(candidate.expires_at) <= utc_now():
            raise UatReleaseError("Dossier UAT kedaluwarsa")

    def _assert_candidate_sealed(self, candidate: UatReleaseCandidate, session: Session) -> None:
        evidence = list(session.scalars(select(UatReadinessEvidence).where(
            UatReadinessEvidence.candidate_id == candidate.id
        )).all())
        blockers = self._candidate_blockers(candidate, evidence)
        if candidate.status != "SEALED":
            blockers.append("Dossier UAT belum SEALED")
        if not self._verify_candidate_ledger(session):
            blockers.append("Candidate ledger tidak valid")
        if blockers:
            raise UatReleaseError("Candidate tidak siap: " + "; ".join(blockers))

    def _assert_execution_open(
        self, execution: UatExecutionSession, candidate: UatReleaseCandidate, session: Session
    ) -> None:
        if execution.status != "OPEN":
            raise UatReleaseError("Execution session bukan OPEN")
        self._assert_candidate_sealed(candidate, session)
        now = utc_now()
        if not self._as_utc(execution.window_start) <= now < self._as_utc(execution.window_end):
            raise UatReleaseError("Execution window tidak aktif")
        if not self._verify_execution_ledger(session):
            raise UatReleaseError("Execution ledger tidak valid")

    @staticmethod
    def _clear_execution_signoffs(execution: UatExecutionSession) -> None:
        execution.results_snapshot_sha256 = None
        execution.clinical_signed_by = None
        execution.clinical_signed_at = None
        execution.technical_signed_by = None
        execution.technical_signed_at = None
        execution.updated_at = utc_now()

    @staticmethod
    def _evidence_snapshot(evidence: list[UatReadinessEvidence]) -> str:
        payload = [{
            "evidence_type": row.evidence_type,
            "filename": row.evidence_filename,
            "checksum_sha256": row.evidence_checksum_sha256,
            "observed_at": UatReleaseService._canonical_time(row.observed_at),
            "valid_until": UatReleaseService._canonical_time(row.valid_until),
            "recorded_by": row.recorded_by,
        } for row in sorted(evidence, key=lambda value: value.evidence_type)]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _results_snapshot(latest: dict[str, UatExecutionResult], issues: list[UatExecutionIssue]) -> str:
        payload = {
            "results": [{
                "scenario_code": code,
                "result_id": row.result_id,
                "status": row.status,
                "evidence_checksum_sha256": row.evidence_checksum_sha256,
                "result_summary_hash_sha256": row.result_summary_hash_sha256,
                "tested_by": row.tested_by,
            } for code, row in sorted(latest.items())],
            "issues": [{
                "issue_number": row.issue_number,
                "severity": row.severity,
                "status": row.status,
                "summary_hash_sha256": row.summary_hash_sha256,
                "resolution_hash_sha256": row.resolution_hash_sha256,
            } for row in sorted(issues, key=lambda value: value.issue_number)],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _latest_results(session: Session, session_id: str) -> dict[str, UatExecutionResult]:
        rows = session.scalars(select(UatExecutionResult).where(
            UatExecutionResult.session_id == session_id
        ).order_by(UatExecutionResult.id)).all()
        return {row.scenario_code: row for row in rows}

    def _append_candidate_ledger(
        self, session: Session, candidate_id: str, event_type: str,
        actor_user_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._append_ledger(session, UatCandidateLedger, "candidate_id", candidate_id, event_type, actor_user_id, payload)

    def _append_execution_ledger(
        self, session: Session, session_id: str, event_type: str,
        actor_user_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._append_ledger(session, UatExecutionLedger, "session_id", session_id, event_type, actor_user_id, payload)

    def _append_ledger(
        self, session: Session, model, binding_field: str, binding_id: str,
        event_type: str, actor_user_id: str | None, payload: dict[str, Any]
    ) -> None:
        previous = session.scalar(select(model).order_by(model.id.desc()).limit(1))
        previous_hash = previous.entry_hash if previous else self.GENESIS_HASH
        event_id = new_uuid()
        occurred = utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_payload = {
            "event_id": event_id,
            binding_field: binding_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "occurred_at": self._canonical_time(occurred),
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }
        entry_hash = hashlib.sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        row = model(
            event_id=event_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            occurred_at=occurred,
            payload_json=payload_json,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            **{binding_field: binding_id},
        )
        session.add(row)
        session.flush()

    def _verify_candidate_ledger(self, session: Session) -> bool:
        return self._verify_ledger(session, UatCandidateLedger, "candidate_id")

    def _verify_execution_ledger(self, session: Session) -> bool:
        return self._verify_ledger(session, UatExecutionLedger, "session_id")

    def _verify_ledger(self, session: Session, model, binding_field: str) -> bool:
        expected_previous = self.GENESIS_HASH
        for row in session.scalars(select(model).order_by(model.id)).all():
            payload = {
                "event_id": row.event_id,
                binding_field: getattr(row, binding_field),
                "event_type": row.event_type,
                "actor_user_id": row.actor_user_id,
                "occurred_at": self._canonical_time(row.occurred_at),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if row.previous_hash != expected_previous or row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    def _assert_ledgers(self, session: Session) -> None:
        if not self._verify_candidate_ledger(session) or not self._verify_execution_ledger(session):
            raise UatReleaseError("Ledger UAT tidak valid")

    @classmethod
    def _contains_sensitive_key(cls, value: object) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if normalized in cls.FORBIDDEN_KEYS or cls._contains_sensitive_key(nested):
                    return True
        if isinstance(value, list):
            return any(cls._contains_sensitive_key(item) for item in value)
        return False

    def _json_file(self, path: Path) -> tuple[dict[str, Any], bytes]:
        if not path.is_file():
            raise UatReleaseError("File evidence tidak ditemukan")
        if path.stat().st_size <= 0 or path.stat().st_size > self.MAX_JSON_BYTES:
            raise UatReleaseError("Ukuran JSON evidence wajib 1 byte-5 MiB")
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UatReleaseError("Evidence wajib JSON UTF-8 valid") from exc
        if not isinstance(payload, dict):
            raise UatReleaseError("Evidence JSON wajib object")
        return payload, raw

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _parse_time(value: object, field: str) -> datetime:
        if not isinstance(value, str):
            raise UatReleaseError(f"{field} wajib timestamp ISO-8601")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise UatReleaseError(f"{field} wajib timestamp ISO-8601") from exc
        if parsed.tzinfo is None:
            raise UatReleaseError(f"{field} wajib memiliki timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _canonical_time(value: datetime | None) -> str | None:
        return AuditService._canonical_datetime(value) if value is not None else None

    @staticmethod
    def _text_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _reason(value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 300:
            raise UatReleaseError("Alasan wajib 10-300 karakter")
        return value

    @staticmethod
    def _get_candidate(session: Session, candidate_id: str) -> UatReleaseCandidate:
        row = session.get(UatReleaseCandidate, candidate_id)
        if row is None:
            raise UatReleaseError("UAT release candidate tidak ditemukan")
        return row

    @staticmethod
    def _get_execution(session: Session, session_id: str) -> UatExecutionSession:
        row = session.get(UatExecutionSession, session_id)
        if row is None:
            raise UatReleaseError("UAT execution session tidak ditemukan")
        return row

    @staticmethod
    def _require_roles(session: Session, actor_user_id: str, allowed: frozenset[str]) -> None:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active or user.normalized_username == 'mode.farmasi':
            raise UatReleasePermissionError("Pengguna aktif tidak ditemukan")
        roles = {link.role.code for link in user.roles}
        if not roles.intersection(allowed):
            raise UatReleasePermissionError("Role tidak berwenang untuk workflow UAT release")

    def _audit(
        self, session: Session, action: str, entity_id: str,
        actor_user_id: str | None, status: str
    ) -> None:
        self.audit.append(session, AuditEvent(
            category="UAT_RELEASE",
            action=action,
            outcome="SUCCESS",
            actor_user_id=actor_user_id,
            entity_type="UAT_RELEASE",
            entity_id=entity_id,
            details={"status": status, "application_version": __version__},
        ))

    @staticmethod
    def _candidate_view(row: UatReleaseCandidate) -> UatCandidateView:
        return UatCandidateView(
            row.id, row.application_version, row.schema_revision, row.environment_label,
            row.installer_filename, row.installer_checksum_sha256, row.status,
            row.expires_at, row.clinical_attested_by, row.technical_attested_by,
            row.created_by, row.created_at,
        )

    @staticmethod
    def _evidence_view(row: UatReadinessEvidence) -> UatEvidenceView:
        return UatEvidenceView(
            row.evidence_type, row.evidence_filename, row.evidence_checksum_sha256,
            row.observed_at, row.valid_until, row.recorded_by,
        )

    @staticmethod
    def _execution_view(row: UatExecutionSession) -> UatExecutionView:
        return UatExecutionView(
            row.id, row.candidate_id, row.status, row.window_start, row.window_end,
            row.clinical_signed_by, row.technical_signed_by, row.decided_by, row.created_by,
        )

    @staticmethod
    def _result_view(row: UatExecutionResult) -> UatResultView:
        return UatResultView(
            row.id, row.scenario_code, row.owner_type, row.status, row.evidence_filename,
            row.evidence_checksum_sha256, row.observed_at, row.tested_by,
        )

    @staticmethod
    def _issue_view(row: UatExecutionIssue) -> UatIssueView:
        return UatIssueView(
            row.id, row.issue_number, row.severity, row.status,
            row.summary_hash_sha256, row.resolution_hash_sha256,
        )
