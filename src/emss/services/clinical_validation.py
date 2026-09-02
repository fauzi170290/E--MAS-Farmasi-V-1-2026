from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from emss import __version__
from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.intervention_models import PharmacistIntervention
from emss.database.knowledge_models import KnowledgeBaseVersion
from emss.database.models import AppUser, UserRole, new_uuid
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.database.validation_models import (
    AdvisoryPilotActivation,
    AdvisoryPilotAuthorizationRequest,
    AdvisoryPilotSessionLedger,
    AdvisoryPilotSafetyControl,
    AdvisoryPilotShiftCloseout,
    ClinicalValidationCase,
    PilotEvidenceVerification,
    UatChecklistItem,
    UatSession,
    ValidationCampaign,
)
from emss.importexport.drug_import import normalize_text
from emss.importexport.tabular_reader import TabularReadError, XlsxTableReader
from emss.services.medication_safety import MedicationSafetyService
from emss.services.screening import DdiScreeningService
from emss.utils.time import utc_now


class ClinicalValidationError(ValueError):
    pass


class ClinicalValidationPermissionError(ClinicalValidationError):
    pass


@dataclass(frozen=True)
class ValidationImportResult:
    campaign_id: str
    campaign_name: str
    total_cases: int
    reviewed_cases: int
    matched_cases: int


@dataclass(frozen=True)
class ValidationCaseView:
    case_code: str
    drug_list: str
    expected_severity: str
    actual_severity: str
    review_status: str
    match: bool | None
    reviewer: str


@dataclass(frozen=True)
class UatItemView:
    id: str
    item_code: str
    category: str
    description: str
    owner_role: str
    status: str
    tester: str


@dataclass(frozen=True)
class PilotGateResult:
    status: str
    campaign_name: str
    cases_total: int
    cases_reviewed: int
    cases_matched: int
    critical_detected: int
    critical_total: int
    high_risk_detected: int
    high_risk_total: int
    uat_passed: int
    uat_total: int
    pharmacist_approved: bool
    it_approved: bool
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == "READY_FOR_ADVISORY_PILOT"


@dataclass(frozen=True)
class AdvisoryPilotStatus:
    active: bool
    gate_ready: bool
    activation_id: str | None
    campaign_id: str | None
    activated_at: datetime | None
    expires_at: datetime | None
    clinical_owner_id: str | None
    shift_started_at: datetime | None
    shift_expires_at: datetime | None
    emergency_stop: bool
    reason: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class AdvisoryAuthorizationRequestStatus:
    id: str
    purpose: str
    status: str
    duration_hours: int
    requested_by: str
    requested_at: datetime
    request_expires_at: datetime
    technical_approved_by: str | None
    clinical_approved_by: str | None
    outgoing_attested_by: str | None
    unresolved_alerts: int | None
    unresolved_critical_alerts: int | None
    unresolved_interventions: int | None


@dataclass(frozen=True)
class PilotShiftSummary:
    captured_at: datetime
    unresolved_alerts: int
    unresolved_critical_alerts: int
    unresolved_interventions: int
    summary_json: str
    summary_sha256: str


@dataclass(frozen=True)
class PilotSessionLedgerEntry:
    sequence: int
    event_id: str
    activation_id: str
    event_type: str
    actor_user_id: str | None
    occurred_at: datetime
    payload_json: str
    previous_hash: str
    entry_hash: str


@dataclass(frozen=True)
class PilotEvidenceExportResult:
    path: Path
    checksum_sha256: str
    ledger_entries: int
    closeouts: int
    ledger_head_hash: str


@dataclass(frozen=True)
class PilotEvidenceVerificationResult:
    record_id: str
    package_filename: str
    checksum_sha256: str | None
    valid: bool
    errors: tuple[str, ...]
    manifest_format: str | None
    application_version: str | None
    schema_revision: str | None
    ledger_head_hash: str | None
    ledger_entries: int | None
    closeouts: int | None
    verified_by: str | None
    verified_at: datetime


@dataclass(frozen=True)
class _PilotEvidenceInspection:
    checksum_sha256: str | None = None
    errors: tuple[str, ...] = ()
    manifest_format: str | None = None
    application_version: str | None = None
    schema_revision: str | None = None
    ledger_head_hash: str | None = None
    ledger_entries: int | None = None
    closeouts: int | None = None


@dataclass(frozen=True)
class PilotMonitoringSummary:
    period_days: int
    prescriptions_total: int
    critical_prescriptions: int
    high_risk_prescriptions: int
    alerts_total: int
    alerts_shown: int
    alerts_acknowledged: int
    critical_unacknowledged: int
    alert_rate_per_100: float
    acknowledgement_rate: float
    median_acknowledgement_minutes: float | None
    interventions_total: int
    interventions_completed: int
    accepted_interventions: int
    assessable_interventions: int
    acceptance_rate: float | None

    @property
    def has_operational_data(self) -> bool:
        return self.prescriptions_total > 0


VALIDATION_HEADERS = (
    "case_id", "daftar_obat", "context_klinis", "expected_pairs",
    "expected_highest_severity", "expected_duplicate_therapy",
    "expected_polypharmacy", "expected_high_alert", "expected_lasa",
    "expected_unmapped", "expected_alert", "checks_compound",
    "checks_revision", "actual_result", "actual_highest_severity",
    "actual_overall_status", "actual_duplicate_therapy",
    "actual_polypharmacy", "actual_high_alert", "actual_lasa",
    "actual_unmapped", "actual_alert", "duplicate_output_count",
    "compound_pass", "revision_pass", "match", "reviewer",
    "review_date", "notes",
)
_REQUIRED_HEADERS = frozenset(VALIDATION_HEADERS)
_SEVERITIES = frozenset({"SAFE", "INFO", "REVIEW", "HIGH_RISK", "CRITICAL"})
_TRUE = frozenset({"1", "TRUE", "YES", "YA", "Y"})
_FALSE = frozenset({"0", "FALSE", "NO", "TIDAK", "N"})


DEFAULT_UAT_ITEMS = (
    ("CLIN-01", "Klinis", "Kasus CRITICAL terdeteksi sesuai expected result", "CRITICAL muncul dan pasangan benar", "APOTEKER"),
    ("CLIN-02", "Klinis", "Kasus HIGH_RISK terdeteksi sesuai expected result", "HIGH_RISK muncul dan pasangan benar", "APOTEKER"),
    ("CLIN-03", "Klinis", "Obat/pasangan UNMAPPED tidak pernah dinyatakan SAFE", "Risiko dan kelengkapan tampil sebagai dua dimensi", "APOTEKER"),
    ("CLIN-04", "Klinis", "Tidak ada pasangan/hasil duplikat", "Setiap pasangan kanonik muncul satu kali", "APOTEKER"),
    ("CLIN-05", "Klinis", "Resep racikan dibaca per komponen", "Komponen racikan dan pasangan lintas item benar", "APOTEKER"),
    ("CLIN-06", "Klinis", "Perubahan resep dikenali sebagai revisi", "Hash berubah dan revision_number bertambah", "APOTEKER"),
    ("CLIN-07", "Klinis", "High-alert tampil sebagai alert keselamatan, bukan DDI", "Kategori alert tidak tercampur dengan interaksi", "APOTEKER"),
    ("TECH-01", "Teknis", "Integrasi Khanza terbukti read-only", "Hanya SELECT melalui empat view integrasi", "IT"),
    ("TECH-02", "Teknis", "Polling, stability check, dan reconnect diuji", "Tidak ada resep parsial atau duplikat", "IT"),
    ("TECH-03", "Teknis", "Silent mode tidak memunculkan alert operasional", "Data tersimpan tetapi tray/popup tidak tampil", "IT"),
    ("TECH-04", "Teknis", "Backup, checksum, restore, dan rollback diuji", "Pemulihan berhasil tanpa merusak database aktif", "IT"),
    ("TECH-05", "Teknis", "Installer diuji pada Windows bersih 64-bit", "Instal, start, upgrade, dan uninstall berhasil", "IT"),
)


class ClinicalValidationService:
    AUTHORIZED_ROLES = frozenset({"SUPER_ADMIN", "CLINICAL_REVIEWER", "APOTEKER", "KFT", "IT_ADMIN"})
    CLINICAL_APPROVERS = frozenset({"SUPER_ADMIN", "CLINICAL_REVIEWER", "APOTEKER", "KFT"})
    IT_APPROVERS = frozenset({"SUPER_ADMIN", "IT_ADMIN"})
    PILOT_CONTROLLERS = frozenset({"SUPER_ADMIN", "IT_ADMIN"})
    CLINICAL_DUTY_APPROVERS = frozenset(
        {"CLINICAL_REVIEWER", "APOTEKER", "KFT"}
    )
    PILOT_AUTHORIZATION_HOURS = frozenset({4, 8, 12, 24, 72, 168})
    SHIFT_MAX_HOURS = 12
    LEDGER_GENESIS_HASH = "0" * 64
    EVIDENCE_FORMAT = "EMSS_PILOT_EVIDENCE_V1"
    EVIDENCE_FILES = frozenset(
        {
            "manifest.json",
            "pilot_session_ledger.csv",
            "pilot_shift_closeouts.csv",
        }
    )
    EVIDENCE_LEDGER_HEADERS = (
        "sequence",
        "event_id",
        "activation_id",
        "event_type",
        "actor_user_id",
        "occurred_at",
        "payload_json",
        "previous_hash",
        "entry_hash",
    )
    EVIDENCE_CLOSEOUT_HEADERS = (
        "closeout_id",
        "activation_id",
        "closeout_type",
        "closed_by",
        "closed_at",
        "unresolved_alerts",
        "unresolved_critical_alerts",
        "unresolved_interventions",
        "summary_sha256",
        "outgoing_attested_by",
        "incoming_attested_by",
        "handover_request_id",
    )
    MAX_EVIDENCE_PACKAGE_BYTES = 20 * 1024 * 1024
    MAX_EVIDENCE_MEMBER_BYTES = 10 * 1024 * 1024
    MAX_EVIDENCE_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
    MAX_EVIDENCE_COMPRESSION_RATIO = 100
    MAX_EVIDENCE_ROWS = 100_000

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        medication_safety: MedicationSafetyService | None = None,
    ) -> None:
        self.database = database
        self.audit = audit
        self.medication_safety = medication_safety or MedicationSafetyService(
            database, audit
        )
        self.reader = XlsxTableReader()

    def import_workbook(self, path: Path | str, actor_user_id: str) -> ValidationImportResult:
        source = Path(path)
        try:
            workbook = self.reader.read(source)
        except (OSError, TabularReadError) as exc:
            raise ClinicalValidationError(str(exc)) from exc
        sheet = workbook.get("VALIDATION_CASES")
        if sheet is None:
            raise ClinicalValidationError("Sheet VALIDATION_CASES tidak ditemukan")
        if sheet.formula_cells:
            raise ClinicalValidationError("Formula tidak diizinkan pada data validasi; tempel sebagai nilai")
        if not sheet.rows:
            raise ClinicalValidationError("Sheet VALIDATION_CASES kosong")
        headers = tuple(normalize_text(value).casefold() for value in sheet.rows[0])
        missing = _REQUIRED_HEADERS - set(headers)
        if missing:
            raise ClinicalValidationError("Kolom wajib tidak lengkap: " + ", ".join(sorted(missing)))
        indexes = {name: headers.index(name) for name in _REQUIRED_HEADERS}
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        errors: list[str] = []
        for offset, row in enumerate(sheet.rows[1:], start=2):
            values = {name: (row[indexes[name]] if indexes[name] < len(row) else None) for name in _REQUIRED_HEADERS}
            if not any(normalize_text(value) for value in values.values()):
                continue
            try:
                record = self._parse_record(values)
                if record["case_code"] in seen:
                    raise ClinicalValidationError("case_id duplikat")
                seen.add(record["case_code"])
                records.append(record)
            except ClinicalValidationError as exc:
                errors.append(f"Baris {offset}: {exc}")
        if errors:
            raise ClinicalValidationError("; ".join(errors[:20]))
        if not records:
            raise ClinicalValidationError("Tidak ada kasus validasi yang dapat diimpor")

        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        now = utc_now()
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            knowledge = session.scalar(
                select(KnowledgeBaseVersion)
                .where(KnowledgeBaseVersion.status.in_(("DRAFT", "PUBLISHED")))
                .order_by(KnowledgeBaseVersion.created_at.desc())
                .limit(1)
            )
            if knowledge is None:
                raise ClinicalValidationError(
                    "Knowledge base DRAFT/PUBLISHED wajib tersedia sebelum "
                    "mengimpor hasil validasi"
                )
            safety_fingerprint = self.medication_safety.configuration_fingerprint(
                session
            )
            campaign = ValidationCampaign(
                name=f"Validasi Klinis {now.date().isoformat()} {now.strftime('%H:%M')}",
                source_filename=source.name,
                source_checksum=checksum,
                application_version=__version__,
                screening_engine_version=DdiScreeningService.ENGINE_VERSION,
                knowledge_base_version_id=knowledge.id,
                safety_configuration_fingerprint=safety_fingerprint,
                created_by=actor_user_id,
            )
            session.add(campaign)
            session.flush()
            for record in records:
                session.add(ClinicalValidationCase(campaign_id=campaign.id, **record))
            self.audit.append(session, AuditEvent(
                category="CLINICAL_VALIDATION", action="VALIDATION_WORKBOOK_IMPORTED", outcome="SUCCESS",
                actor_user_id=actor_user_id, entity_type="VALIDATION_CAMPAIGN", entity_id=campaign.id,
                details={
                    "application_version": __version__,
                    "case_count": len(records),
                    "checksum": checksum,
                    "filename": source.name,
                    "knowledge_base_version": knowledge.version_code,
                    "safety_configuration_fingerprint": safety_fingerprint,
                    "screening_engine_version": DdiScreeningService.ENGINE_VERSION,
                },
            ))
            session.commit()
            reviewed = sum(record["review_status"] == "REVIEWED" for record in records)
            matched = sum(record["match"] is True for record in records)
            return ValidationImportResult(campaign.id, campaign.name, len(records), reviewed, matched)

    def ensure_uat_session(self, actor_user_id: str) -> str:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            existing = session.scalar(select(UatSession).order_by(UatSession.created_at.desc()))
            if existing is not None:
                return existing.id
            row = UatSession(name="UAT Sprint 10", created_by=actor_user_id)
            session.add(row)
            session.flush()
            for code, category, description, expected, owner in DEFAULT_UAT_ITEMS:
                session.add(UatChecklistItem(session_id=row.id, item_code=code, category=category, description=description, expected_result=expected, owner_role=owner))
            self.audit.append(session, AuditEvent(
                category="UAT", action="UAT_SESSION_CREATED", outcome="SUCCESS",
                actor_user_id=actor_user_id, entity_type="UAT_SESSION", entity_id=row.id,
                details={"checklist_count": len(DEFAULT_UAT_ITEMS)},
            ))
            session.commit()
            return row.id

    def latest_cases(self) -> tuple[ValidationCaseView, ...]:
        with self.database.session() as session:
            campaign = session.scalar(select(ValidationCampaign).order_by(ValidationCampaign.created_at.desc()))
            if campaign is None:
                return ()
            rows = session.scalars(select(ClinicalValidationCase).where(ClinicalValidationCase.campaign_id == campaign.id).order_by(ClinicalValidationCase.case_code)).all()
            return tuple(ValidationCaseView(row.case_code, row.drug_list, row.expected_highest_severity, row.actual_highest_severity or "-", row.review_status, row.match, row.reviewer or "-") for row in rows)

    def uat_items(self, actor_user_id: str) -> tuple[UatItemView, ...]:
        session_id = self.ensure_uat_session(actor_user_id)
        with self.database.session() as session:
            rows = session.scalars(select(UatChecklistItem).where(UatChecklistItem.session_id == session_id).order_by(UatChecklistItem.item_code)).all()
            return tuple(UatItemView(row.id, row.item_code, row.category, row.description, row.owner_role, row.status, row.tester or "-") for row in rows)

    def update_uat_item(self, item_id: str, status: str, actor_user_id: str, tester: str, actual_result: str = "", evidence: str = "") -> str | None:
        normalized = status.strip().upper()
        if normalized not in {"PASS", "FAIL", "BLOCKED", "NOT_TESTED"}:
            raise ClinicalValidationError("Status UAT tidak valid")
        normalized_actual = normalize_text(actual_result) or None
        normalized_evidence = normalize_text(evidence) or None
        normalized_tester = normalize_text(tester)
        with self.database.session() as session:
            roles = self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            item = session.get(UatChecklistItem, item_id)
            if item is None:
                raise ClinicalValidationError("Item UAT tidak ditemukan")
            allowed = self.CLINICAL_APPROVERS if item.owner_role == "APOTEKER" else self.IT_APPROVERS
            if not roles.intersection(allowed):
                raise ClinicalValidationPermissionError("Role Anda tidak berwenang menguji item ini")
            changed = (
                item.status != normalized
                or item.actual_result != normalized_actual
                or item.evidence != normalized_evidence
                or item.tester != normalized_tester
            )
            if not changed:
                return None
            item.status = normalized
            item.actual_result = normalized_actual
            item.evidence = normalized_evidence
            item.tester = normalized_tester
            item.tested_at = utc_now() if normalized != "NOT_TESTED" else None
            uat = session.get(UatSession, item.session_id)
            revoked = False
            if item.owner_role == "APOTEKER" and uat.pharmacist_approved:
                uat.pharmacist_approved = False
                uat.pharmacist_approved_by = None
                uat.pharmacist_approved_at = None
                uat.pharmacist_approved_version = None
                uat.pharmacist_approved_campaign_id = None
                revoked = True
            elif item.owner_role == "IT" and uat.it_approved:
                uat.it_approved = False
                uat.it_approved_by = None
                uat.it_approved_at = None
                uat.it_approved_version = None
                uat.it_approved_campaign_id = None
                revoked = True
            if revoked:
                uat.status = "IN_PROGRESS"
                self.audit.append(session, AuditEvent(
                    category="UAT", action="UAT_APPROVAL_REVOKED", outcome="SUCCESS",
                    actor_user_id=actor_user_id, entity_type="UAT_SESSION", entity_id=uat.id,
                    details={"approval_type": item.owner_role, "item_code": item.item_code, "reason": "CHECKLIST_EVIDENCE_CHANGED"},
                ))
            self.audit.append(session, AuditEvent(
                category="UAT", action="UAT_ITEM_UPDATED", outcome="SUCCESS", actor_user_id=actor_user_id,
                entity_type="UAT_CHECKLIST_ITEM", entity_id=item.id,
                details={"item_code": item.item_code, "status": normalized},
            ))
            session.commit()
            return item.owner_role if revoked else None

    def _campaign_provenance_blockers(
        self, session: Session, campaign: ValidationCampaign
    ) -> list[str]:
        published_knowledge = session.scalar(
            select(KnowledgeBaseVersion)
            .where(KnowledgeBaseVersion.status == "PUBLISHED")
            .order_by(KnowledgeBaseVersion.published_at.desc())
            .limit(1)
        )
        safety_fingerprint = self.medication_safety.configuration_fingerprint(
            session
        )
        blockers: list[str] = []
        if campaign.application_version != __version__:
            blockers.append(
                "Kampanye validasi bukan untuk versi aplikasi saat ini"
            )
        if (
            campaign.screening_engine_version
            != DdiScreeningService.ENGINE_VERSION
        ):
            blockers.append(
                "Kampanye validasi bukan untuk screening engine saat ini"
            )
        if campaign.knowledge_base_version_id is None:
            blockers.append(
                "Kampanye validasi belum memiliki provenance knowledge base"
            )
        elif published_knowledge is None:
            blockers.append(
                "Knowledge base tervalidasi belum berstatus PUBLISHED"
            )
        elif published_knowledge.id != campaign.knowledge_base_version_id:
            blockers.append(
                "Knowledge base PUBLISHED berubah setelah validasi"
            )
        if campaign.safety_configuration_fingerprint is None:
            blockers.append(
                "Kampanye validasi belum memiliki fingerprint kebijakan keselamatan"
            )
        elif (
            campaign.safety_configuration_fingerprint != safety_fingerprint
        ):
            blockers.append(
                "Kebijakan keselamatan obat berubah setelah validasi"
            )
        return blockers

    def approve_uat(self, approval_type: str, actor_user_id: str) -> None:
        kind = approval_type.strip().upper()
        if kind not in {"APOTEKER", "IT"}:
            raise ClinicalValidationError("Jenis persetujuan UAT tidak valid")
        with self.database.session() as session:
            roles = self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            allowed = self.CLINICAL_APPROVERS if kind == "APOTEKER" else self.IT_APPROVERS
            if not roles.intersection(allowed):
                raise ClinicalValidationPermissionError("Role Anda tidak berwenang memberi persetujuan ini")
            uat = session.scalar(select(UatSession).options(selectinload(UatSession.items)).order_by(UatSession.created_at.desc()))
            if uat is None:
                raise ClinicalValidationError("Sesi UAT belum dibuat")
            relevant = [item for item in uat.items if item.owner_role == kind]
            if not relevant or any(item.status != "PASS" for item in relevant):
                raise ClinicalValidationError(f"Semua item UAT {kind} harus PASS sebelum persetujuan")
            campaign = session.scalar(
                select(ValidationCampaign)
                .order_by(ValidationCampaign.created_at.desc())
                .limit(1)
            )
            if campaign is None:
                raise ClinicalValidationError(
                    "Kampanye validasi klinis belum tersedia"
                )
            provenance_blockers = self._campaign_provenance_blockers(
                session, campaign
            )
            if provenance_blockers:
                raise ClinicalValidationError(
                    "Provenance kampanye validasi tidak sesuai: "
                    + "; ".join(provenance_blockers)
                )
            now = utc_now()
            if kind == "APOTEKER":
                uat.pharmacist_approved = True
                uat.pharmacist_approved_by = actor_user_id
                uat.pharmacist_approved_at = now
                uat.pharmacist_approved_version = __version__
                uat.pharmacist_approved_campaign_id = campaign.id
            else:
                uat.it_approved = True
                uat.it_approved_by = actor_user_id
                uat.it_approved_at = now
                uat.it_approved_version = __version__
                uat.it_approved_campaign_id = campaign.id
            uat.status = "APPROVED" if uat.pharmacist_approved and uat.it_approved else "IN_PROGRESS"
            self.audit.append(session, AuditEvent(
                category="UAT", action=f"UAT_{kind}_APPROVED", outcome="SUCCESS", actor_user_id=actor_user_id,
                entity_type="UAT_SESSION", entity_id=uat.id,
                details={
                    "application_version": __version__,
                    "validation_campaign_id": campaign.id,
                    "validation_source_checksum": campaign.source_checksum,
                },
            ))
            session.commit()

    @staticmethod
    def _approval_is_current(
        uat: UatSession | None,
        kind: str,
        campaign: ValidationCampaign | None,
    ) -> bool:
        if uat is None or campaign is None:
            return False
        if kind == "APOTEKER":
            approved = uat.pharmacist_approved
            approved_by = uat.pharmacist_approved_by
            approved_at = uat.pharmacist_approved_at
            approved_version = uat.pharmacist_approved_version
            approved_campaign_id = uat.pharmacist_approved_campaign_id
        else:
            approved = uat.it_approved
            approved_by = uat.it_approved_by
            approved_at = uat.it_approved_at
            approved_version = uat.it_approved_version
            approved_campaign_id = uat.it_approved_campaign_id
        if (
            not approved
            or not approved_by
            or approved_at is None
            or approved_version != __version__
            or approved_campaign_id != campaign.id
        ):
            return False
        relevant = [item for item in uat.items if item.owner_role == kind]
        return bool(relevant) and all(
            item.status == "PASS"
            and item.tested_at is not None
            and item.tested_at <= approved_at
            for item in relevant
        )

    def evaluate_gate(self, actor_user_id: str | None = None) -> PilotGateResult:
        with self.database.session() as session:
            if actor_user_id:
                self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            return self._evaluate_gate_in_session(session)

    def _evaluate_gate_in_session(self, session: Session) -> PilotGateResult:
        campaign = session.scalar(
            select(ValidationCampaign)
            .options(selectinload(ValidationCampaign.cases))
            .order_by(ValidationCampaign.created_at.desc())
        )
        uat = session.scalar(
            select(UatSession)
            .options(selectinload(UatSession.items))
            .order_by(UatSession.created_at.desc())
        )
        cases = campaign.cases if campaign else []
        critical = [
            row for row in cases
            if row.expected_highest_severity == "CRITICAL"
        ]
        serious = [
            row for row in cases
            if row.expected_highest_severity == "HIGH_RISK"
        ]
        critical_detected = sum(
            row.actual_highest_severity == "CRITICAL" for row in critical
        )
        serious_detected = sum(
            row.actual_highest_severity in {"HIGH_RISK", "CRITICAL"}
            for row in serious
        )
        blockers: list[str] = []
        if campaign is not None:
            blockers.extend(
                self._campaign_provenance_blockers(session, campaign)
            )
        reviewed = sum(row.review_status == "REVIEWED" for row in cases)
        matched = sum(row.match is True for row in cases)
        if not cases:
            blockers.append("Belum ada workbook validasi klinis yang diimpor")
        elif reviewed != len(cases):
            blockers.append(f"Kasus belum ditinjau: {len(cases) - reviewed}")
        if cases and matched != len(cases):
            blockers.append(
                f"Kasus tidak cocok/belum lengkap: {len(cases) - matched}"
            )
        if not critical:
            blockers.append("Minimal satu kasus CRITICAL wajib diuji")
        elif critical_detected != len(critical):
            blockers.append("Deteksi CRITICAL belum 100%")
        if not serious:
            blockers.append("Minimal satu kasus HIGH_RISK wajib diuji")
        elif serious_detected != len(serious):
            blockers.append("Deteksi HIGH_RISK belum 100%")
        if any(
            row.expected_unmapped and row.actual_overall_status == "SAFE"
            for row in cases
        ):
            blockers.append("Ditemukan UNMAPPED yang dinyatakan SAFE")
        if any(row.duplicate_output_count > 0 for row in cases):
            blockers.append("Masih ada hasil pasangan duplikat")
        compound = [row for row in cases if row.checks_compound]
        revision = [row for row in cases if row.checks_revision]
        if not compound or any(
            row.compound_pass is not True for row in compound
        ):
            blockers.append("Uji resep racikan belum lulus")
        if not revision or any(
            row.revision_pass is not True for row in revision
        ):
            blockers.append("Uji perubahan/revisi resep belum lulus")
        uat_items = uat.items if uat else []
        uat_passed = sum(item.status == "PASS" for item in uat_items)
        if not uat_items or uat_passed != len(uat_items):
            blockers.append("Checklist UAT belum seluruhnya PASS")
        pharmacist_approved = self._approval_is_current(
            uat, "APOTEKER", campaign
        )
        it_approved = self._approval_is_current(uat, "IT", campaign)
        if not pharmacist_approved:
            blockers.append(
                f"Persetujuan UAT Apoteker bukan untuk versi aplikasi {__version__}"
                if uat
                and uat.pharmacist_approved
                and uat.pharmacist_approved_version != __version__
                else (
                    "Persetujuan UAT Apoteker bukan untuk kampanye validasi terbaru"
                    if uat
                    and uat.pharmacist_approved
                    and campaign
                    and uat.pharmacist_approved_campaign_id != campaign.id
                    else (
                        "Persetujuan UAT Apoteker tidak lagi sesuai bukti terbaru"
                        if uat and uat.pharmacist_approved
                        else "UAT belum disetujui apoteker/validator klinis"
                    )
                )
            )
        if not it_approved:
            blockers.append(
                f"Persetujuan UAT IT bukan untuk versi aplikasi {__version__}"
                if uat
                and uat.it_approved
                and uat.it_approved_version != __version__
                else (
                    "Persetujuan UAT IT bukan untuk kampanye validasi terbaru"
                    if uat
                    and uat.it_approved
                    and campaign
                    and uat.it_approved_campaign_id != campaign.id
                    else (
                        "Persetujuan UAT IT tidak lagi sesuai bukti terbaru"
                        if uat and uat.it_approved
                        else "UAT belum disetujui IT"
                    )
                )
            )
        status = (
            "READY_FOR_ADVISORY_PILOT"
            if not blockers
            else "READY_FOR_CLINICAL_VALIDATION"
        )
        return PilotGateResult(
            status,
            campaign.name if campaign else "-",
            len(cases),
            reviewed,
            matched,
            critical_detected,
            len(critical),
            serious_detected,
            len(serious),
            uat_passed,
            len(uat_items),
            pharmacist_approved,
            it_approved,
            tuple(blockers),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _shift_summary(self, session: Session) -> PilotShiftSummary:
        unresolved_filter = (
            AlertEvent.status.in_(("NEW", "SHOWN")),
            ProcessingQueue.is_mock.is_(False),
        )
        unresolved_alerts = int(
            session.scalar(
                select(func.count(AlertEvent.id))
                .join(
                    ProcessingQueue,
                    ProcessingQueue.id == AlertEvent.queue_item_id,
                )
                .where(*unresolved_filter)
            )
            or 0
        )
        unresolved_critical = int(
            session.scalar(
                select(func.count(AlertEvent.id))
                .join(
                    ProcessingQueue,
                    ProcessingQueue.id == AlertEvent.queue_item_id,
                )
                .where(*unresolved_filter, AlertEvent.level == "CRITICAL")
            )
            or 0
        )
        unresolved_interventions = int(
            session.scalar(
                select(func.count(PharmacistIntervention.id))
                .join(
                    ProcessingQueue,
                    ProcessingQueue.id
                    == PharmacistIntervention.queue_item_id,
                )
                .where(
                    PharmacistIntervention.status == "OPEN",
                    ProcessingQueue.is_mock.is_(False),
                )
            )
            or 0
        )
        captured_at = utc_now()
        payload = {
            "captured_at": captured_at.isoformat(),
            "scope": "ALL_NON_MOCK_OUTSTANDING",
            "unresolved_alerts": unresolved_alerts,
            "unresolved_critical_alerts": unresolved_critical,
            "unresolved_interventions": unresolved_interventions,
        }
        summary_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return PilotShiftSummary(
            captured_at=captured_at,
            unresolved_alerts=unresolved_alerts,
            unresolved_critical_alerts=unresolved_critical,
            unresolved_interventions=unresolved_interventions,
            summary_json=summary_json,
            summary_sha256=hashlib.sha256(summary_json.encode("utf-8")).hexdigest(),
        )

    def _append_pilot_ledger(
        self,
        session: Session,
        activation_id: str,
        event_type: str,
        actor_user_id: str | None,
        payload: dict[str, Any],
    ) -> AdvisoryPilotSessionLedger:
        previous = session.scalar(
            select(AdvisoryPilotSessionLedger)
            .order_by(AdvisoryPilotSessionLedger.id.desc())
            .limit(1)
        )
        previous_hash = (
            previous.entry_hash if previous else self.LEDGER_GENESIS_HASH
        )
        event_id = new_uuid()
        occurred_at = utc_now()
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        hash_payload = {
            "event_id": event_id,
            "activation_id": activation_id,
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
        entry = AdvisoryPilotSessionLedger(
            event_id=event_id,
            activation_id=activation_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
            payload_json=payload_json,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        session.add(entry)
        session.flush()
        self.audit.append(
            session,
            AuditEvent(
                category="PILOT_LEDGER",
                action="PILOT_SESSION_LEDGER_APPENDED",
                outcome="SUCCESS",
                actor_user_id=actor_user_id,
                entity_type="PILOT_SESSION_LEDGER",
                entity_id=event_id,
                details={
                    "activation_id": activation_id,
                    "event_type": event_type,
                    "entry_hash": entry_hash,
                },
            ),
        )
        return entry

    def _verify_pilot_ledger_in_session(self, session: Session) -> bool:
        expected_previous = self.LEDGER_GENESIS_HASH
        rows = session.scalars(
            select(AdvisoryPilotSessionLedger).order_by(
                AdvisoryPilotSessionLedger.id
            )
        ).all()
        for row in rows:
            if row.previous_hash != expected_previous:
                return False
            hash_payload = {
                "event_id": row.event_id,
                "activation_id": row.activation_id,
                "event_type": row.event_type,
                "actor_user_id": row.actor_user_id,
                "occurred_at": AuditService._canonical_datetime(
                    row.occurred_at
                ),
                "payload_json": row.payload_json,
                "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(
                json.dumps(
                    hash_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if row.entry_hash != expected_hash:
                return False
            expected_previous = row.entry_hash
        return True

    def _finalize_shift_closeout(
        self,
        session: Session,
        activation: AdvisoryPilotActivation,
        closeout_type: str,
        actor_user_id: str | None,
        *,
        request: AdvisoryPilotAuthorizationRequest | None = None,
        notes: str | None = None,
        append_ledger: bool = True,
    ) -> AdvisoryPilotShiftCloseout:
        existing = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id == activation.id
            )
        )
        if existing is not None:
            return existing

        if request is not None:
            if not request.handover_summary_json:
                raise ClinicalValidationError(
                    "Ringkasan handover tidak tersedia"
                )
            expected_hash = hashlib.sha256(
                request.handover_summary_json.encode("utf-8")
            ).hexdigest()
            if expected_hash != request.handover_summary_sha256:
                raise ClinicalValidationError(
                    "Checksum ringkasan handover tidak valid"
                )
            summary_json = request.handover_summary_json
            summary_sha256 = expected_hash
            unresolved_alerts = int(request.unresolved_alerts or 0)
            unresolved_critical = int(
                request.unresolved_critical_alerts or 0
            )
            unresolved_interventions = int(
                request.unresolved_interventions or 0
            )
        else:
            summary = self._shift_summary(session)
            summary_json = summary.summary_json
            summary_sha256 = summary.summary_sha256
            unresolved_alerts = summary.unresolved_alerts
            unresolved_critical = summary.unresolved_critical_alerts
            unresolved_interventions = summary.unresolved_interventions

        now = utc_now()
        outgoing_user_id = (
            request.outgoing_attested_by
            if request is not None
            else (
                actor_user_id
                if closeout_type == "OWNER_CLOSEOUT"
                else None
            )
        )
        outgoing_at = (
            request.outgoing_attested_at
            if request is not None
            else (now if outgoing_user_id else None)
        )
        closeout = AdvisoryPilotShiftCloseout(
            activation_id=activation.id,
            closeout_type=closeout_type,
            closed_by=actor_user_id,
            closed_at=now,
            summary_json=summary_json,
            summary_sha256=summary_sha256,
            unresolved_alerts=unresolved_alerts,
            unresolved_critical_alerts=unresolved_critical,
            unresolved_interventions=unresolved_interventions,
            outgoing_attested_by=outgoing_user_id,
            outgoing_attested_at=outgoing_at,
            incoming_attested_by=(
                request.clinical_approved_by if request is not None else None
            ),
            incoming_attested_at=(
                request.clinical_approved_at if request is not None else None
            ),
            handover_request_id=(request.id if request is not None else None),
            notes=notes,
        )
        session.add(closeout)
        session.flush()
        if append_ledger:
            self._append_pilot_ledger(
                session,
                activation.id,
                "SHIFT_CLOSED",
                actor_user_id,
                {
                    "closeout_id": closeout.id,
                    "closeout_type": closeout_type,
                    "summary_sha256": summary_sha256,
                    "unresolved_alerts": unresolved_alerts,
                    "unresolved_critical_alerts": unresolved_critical,
                    "unresolved_interventions": unresolved_interventions,
                    "outgoing_attested_by": outgoing_user_id,
                    "incoming_attested_by": (
                        request.clinical_approved_by
                        if request is not None
                        else None
                    ),
                },
            )
        self.audit.append(
            session,
            AuditEvent(
                category="PILOT_CONTROL",
                action="ADVISORY_SHIFT_CLOSED",
                outcome="SUCCESS",
                actor_user_id=actor_user_id,
                entity_type="ADVISORY_SHIFT_CLOSEOUT",
                entity_id=closeout.id,
                details={
                    "activation_id": activation.id,
                    "closeout_type": closeout_type,
                    "summary_sha256": summary_sha256,
                },
            ),
        )
        return closeout

    @staticmethod
    def _safety_control(session: Session) -> AdvisoryPilotSafetyControl:
        control = session.get(AdvisoryPilotSafetyControl, "GLOBAL")
        if control is None:
            control = AdvisoryPilotSafetyControl(
                id="GLOBAL", emergency_stop=False, updated_at=utc_now()
            )
            session.add(control)
            session.flush()
        return control

    def _advisory_status_in_session(
        self, session: Session
    ) -> tuple[AdvisoryPilotStatus, bool]:
        gate = self._evaluate_gate_in_session(session)
        control = self._safety_control(session)
        campaign = session.scalar(
            select(ValidationCampaign)
            .order_by(ValidationCampaign.created_at.desc())
            .limit(1)
        )
        uat = session.scalar(
            select(UatSession)
            .order_by(UatSession.created_at.desc())
            .limit(1)
        )
        activation = session.scalar(
            select(AdvisoryPilotActivation)
            .where(AdvisoryPilotActivation.status == "ACTIVE")
            .order_by(AdvisoryPilotActivation.activated_at.desc())
            .limit(1)
        )
        ledger_valid = self._verify_pilot_ledger_in_session(session)
        quarantine_detected = False
        if not ledger_valid and not control.ledger_quarantine:
            now = utc_now()
            head = session.scalar(
                select(AdvisoryPilotSessionLedger)
                .order_by(AdvisoryPilotSessionLedger.id.desc())
                .limit(1)
            )
            control.ledger_quarantine = True
            control.ledger_quarantine_reason = (
                "Rantai ledger sesi pilot tidak valid"
            )
            control.ledger_quarantined_at = now
            control.ledger_detected_head_hash = (
                head.entry_hash if head is not None else None
            )
            control.ledger_quarantine_cleared_by = None
            control.ledger_quarantine_cleared_at = None
            control.updated_at = now
            quarantine_detected = True
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_LEDGER",
                    action="PILOT_LEDGER_INTEGRITY_QUARANTINED",
                    outcome="SUCCESS",
                    entity_type="ADVISORY_PILOT_SAFETY_CONTROL",
                    entity_id=control.id,
                    details={
                        "detected_head_hash": control.ledger_detected_head_hash,
                        "active_activation_id": (
                            activation.id if activation else None
                        ),
                    },
                ),
            )
        if control.ledger_quarantine:
            changed = quarantine_detected
            if activation is not None:
                activation.status = "REVOKED"
                activation.revoked_at = utc_now()
                activation.revocation_reason = (
                    "PILOT_LEDGER_INTEGRITY_FAILURE"
                )
                self._finalize_shift_closeout(
                    session,
                    activation,
                    "PILOT_LEDGER_INTEGRITY_FAILURE",
                    None,
                    notes=control.ledger_quarantine_reason,
                    append_ledger=False,
                )
                self.audit.append(
                    session,
                    AuditEvent(
                        category="PILOT_CONTROL",
                        action="ADVISORY_PILOT_AUTO_REVOKED",
                        outcome="SUCCESS",
                        entity_type="ADVISORY_PILOT_ACTIVATION",
                        entity_id=activation.id,
                        details={
                            "reason": "PILOT_LEDGER_INTEGRITY_FAILURE",
                        },
                    ),
                )
                changed = True
            return (
                AdvisoryPilotStatus(
                    active=False,
                    gate_ready=gate.ready,
                    activation_id=(activation.id if activation else None),
                    campaign_id=campaign.id if campaign else None,
                    activated_at=(
                        activation.activated_at if activation else None
                    ),
                    expires_at=(activation.expires_at if activation else None),
                    clinical_owner_id=(
                        activation.clinical_owner_id if activation else None
                    ),
                    shift_started_at=(
                        activation.shift_started_at if activation else None
                    ),
                    shift_expires_at=(
                        activation.shift_expires_at if activation else None
                    ),
                    emergency_stop=control.emergency_stop,
                    reason="LEDGER_QUARANTINED",
                    blockers=(
                        "Ledger sesi pilot dikarantina: "
                        + (
                            control.ledger_quarantine_reason
                            or "integritas tidak valid"
                        ),
                    ),
                ),
                changed,
            )
        if control.emergency_stop:
            changed = False
            if activation is not None:
                activation.status = "REVOKED"
                activation.revoked_at = utc_now()
                activation.revocation_reason = "EMERGENCY_STOP"
                self._finalize_shift_closeout(
                    session,
                    activation,
                    "EMERGENCY_STOP",
                    control.stopped_by,
                    notes=control.stop_reason,
                )
                self.audit.append(
                    session,
                    AuditEvent(
                        category="PILOT_CONTROL",
                        action="ADVISORY_PILOT_AUTO_REVOKED",
                        outcome="SUCCESS",
                        entity_type="ADVISORY_PILOT_ACTIVATION",
                        entity_id=activation.id,
                        details={
                            "reason": "EMERGENCY_STOP",
                            "stop_reason": control.stop_reason,
                        },
                    ),
                )
                changed = True
            return (
                AdvisoryPilotStatus(
                    active=False,
                    gate_ready=gate.ready,
                    activation_id=activation.id if activation else None,
                    campaign_id=campaign.id if campaign else None,
                    activated_at=(
                        activation.activated_at if activation else None
                    ),
                    expires_at=activation.expires_at if activation else None,
                    clinical_owner_id=(
                        activation.clinical_owner_id if activation else None
                    ),
                    shift_started_at=(
                        activation.shift_started_at if activation else None
                    ),
                    shift_expires_at=(
                        activation.shift_expires_at if activation else None
                    ),
                    emergency_stop=True,
                    reason="EMERGENCY_STOP",
                    blockers=(
                        "Emergency stop aktif: "
                        + (control.stop_reason or "alasan tidak tersedia"),
                    ),
                ),
                changed,
            )
        if activation is None:
            if gate.ready:
                blockers = (
                    "Advisory Pilot belum diaktifkan oleh IT/Super Admin",
                )
                reason = "NOT_ACTIVATED"
            else:
                blockers = gate.blockers
                reason = "GATE_NOT_READY"
            return (
                AdvisoryPilotStatus(
                    active=False,
                    gate_ready=gate.ready,
                    activation_id=None,
                    campaign_id=campaign.id if campaign else None,
                    activated_at=None,
                    expires_at=None,
                    clinical_owner_id=None,
                    shift_started_at=None,
                    shift_expires_at=None,
                    emergency_stop=False,
                    reason=reason,
                    blockers=blockers,
                ),
                False,
            )

        now = utc_now()
        activation_expiry_valid = bool(
            activation.expires_at
            and self._as_utc(activation.expires_at) > now
        )
        shift_expiry_valid = bool(
            activation.shift_started_at
            and activation.shift_expires_at
            and self._as_utc(activation.shift_expires_at) > now
            and (
                activation.expires_at is None
                or self._as_utc(activation.shift_expires_at)
                <= self._as_utc(activation.expires_at)
            )
        )
        binding_matches = bool(
            campaign
            and uat
            and activation.application_version == __version__
            and activation.validation_campaign_id == campaign.id
            and activation.uat_session_id == uat.id
            and activation.pharmacist_approved_at
            == uat.pharmacist_approved_at
            and activation.it_approved_at == uat.it_approved_at
            and activation.clinical_owner_id is not None
            and activation.technical_authorizer_id is not None
            and activation.clinical_owner_id
            != activation.technical_authorizer_id
            and activation.authorization_request_id is not None
        )
        if (
            gate.ready
            and binding_matches
            and activation_expiry_valid
            and shift_expiry_valid
        ):
            return (
                AdvisoryPilotStatus(
                    active=True,
                    gate_ready=True,
                    activation_id=activation.id,
                    campaign_id=campaign.id,
                    activated_at=activation.activated_at,
                    expires_at=activation.expires_at,
                    clinical_owner_id=activation.clinical_owner_id,
                    shift_started_at=activation.shift_started_at,
                    shift_expires_at=activation.shift_expires_at,
                    emergency_stop=False,
                    reason="ACTIVE",
                    blockers=(),
                ),
                False,
            )

        if not activation_expiry_valid:
            reason = "ACTIVATION_EXPIRED"
        elif not shift_expiry_valid:
            reason = "SHIFT_EXPIRED"
        elif not gate.ready:
            reason = "GATE_NOT_READY"
        else:
            reason = "ACTIVATION_BINDING_CHANGED"
        activation.status = "REVOKED"
        activation.revoked_at = now
        activation.revocation_reason = reason
        self._finalize_shift_closeout(
            session,
            activation,
            reason,
            None,
        )
        if reason == "ACTIVATION_EXPIRED":
            blockers = (
                "Masa berlaku otorisasi Advisory Pilot telah berakhir",
            )
        elif reason == "SHIFT_EXPIRED":
            blockers = (
                "Masa tugas pemilik shift klinis telah berakhir; handover "
                "atau aktivasi baru wajib dilakukan",
            )
        elif not gate.ready:
            blockers = gate.blockers
        else:
            blockers = (
                "Otorisasi Advisory Pilot tidak lagi sesuai bukti terbaru",
            )
        self.audit.append(
            session,
            AuditEvent(
                category="PILOT_CONTROL",
                action="ADVISORY_PILOT_AUTO_REVOKED",
                outcome="SUCCESS",
                entity_type="ADVISORY_PILOT_ACTIVATION",
                entity_id=activation.id,
                details={
                    "reason": reason,
                    "application_version": __version__,
                    "current_validation_campaign_id": (
                        campaign.id if campaign else None
                    ),
                    "current_uat_session_id": uat.id if uat else None,
                    "expires_at": (
                        activation.expires_at.isoformat()
                        if activation.expires_at
                        else None
                    ),
                    "blockers": list(blockers),
                },
            ),
        )
        return (
            AdvisoryPilotStatus(
                active=False,
                gate_ready=gate.ready,
                activation_id=activation.id,
                campaign_id=campaign.id if campaign else None,
                activated_at=activation.activated_at,
                expires_at=activation.expires_at,
                clinical_owner_id=activation.clinical_owner_id,
                shift_started_at=activation.shift_started_at,
                shift_expires_at=activation.shift_expires_at,
                emergency_stop=False,
                reason=reason,
                blockers=blockers,
            ),
            True,
        )

    def advisory_pilot_status(
        self, actor_user_id: str | None = None
    ) -> AdvisoryPilotStatus:
        with self.database.session() as session:
            if actor_user_id:
                self._require_roles(
                    session, actor_user_id, self.AUTHORIZED_ROLES
                )
            status, changed = self._advisory_status_in_session(session)
            if changed:
                session.commit()
            return status

    @staticmethod
    def _authorization_request_view(
        request: AdvisoryPilotAuthorizationRequest,
    ) -> AdvisoryAuthorizationRequestStatus:
        return AdvisoryAuthorizationRequestStatus(
            id=request.id,
            purpose=request.purpose,
            status=request.status,
            duration_hours=request.duration_hours,
            requested_by=request.requested_by,
            requested_at=request.requested_at,
            request_expires_at=request.request_expires_at,
            technical_approved_by=request.technical_approved_by,
            clinical_approved_by=request.clinical_approved_by,
            outgoing_attested_by=request.outgoing_attested_by,
            unresolved_alerts=request.unresolved_alerts,
            unresolved_critical_alerts=request.unresolved_critical_alerts,
            unresolved_interventions=request.unresolved_interventions,
        )

    def _pending_authorization_request(
        self, session: Session
    ) -> AdvisoryPilotAuthorizationRequest | None:
        request = session.scalar(
            select(AdvisoryPilotAuthorizationRequest)
            .where(
                AdvisoryPilotAuthorizationRequest.status.in_(
                    (
                        "PENDING_CLINICAL",
                        "PENDING_OUTGOING",
                        "PENDING_TECHNICAL",
                    )
                )
            )
            .order_by(AdvisoryPilotAuthorizationRequest.requested_at.desc())
            .limit(1)
        )
        if request and self._as_utc(request.request_expires_at) <= utc_now():
            request.status = "EXPIRED"
            request.cancelled_at = utc_now()
            request.cancellation_reason = "REQUEST_EXPIRED"
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_AUTHORIZATION_REQUEST_EXPIRED",
                    outcome="SUCCESS",
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={"purpose": request.purpose},
                ),
            )
            if request.handover_from_activation_id:
                self._append_pilot_ledger(
                    session,
                    request.handover_from_activation_id,
                    "HANDOVER_REQUEST_EXPIRED",
                    None,
                    {"authorization_request_id": request.id},
                )
            return None
        return request

    def pending_advisory_authorization(
        self, actor_user_id: str
    ) -> AdvisoryAuthorizationRequestStatus | None:
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            request = self._pending_authorization_request(session)
            session.commit()
            return (
                self._authorization_request_view(request)
                if request is not None
                else None
            )

    def request_advisory_pilot_activation(
        self, actor_user_id: str, duration_hours: int = 24
    ) -> AdvisoryAuthorizationRequestStatus:
        if duration_hours not in self.PILOT_AUTHORIZATION_HOURS:
            raise ClinicalValidationError(
                "Durasi aktivasi harus 4, 8, 12, 24, 72, atau 168 jam"
            )
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.PILOT_CONTROLLERS):
                raise ClinicalValidationPermissionError(
                    "Hanya IT Admin atau Super Admin yang dapat mengajukan "
                    "aktivasi Advisory Pilot"
                )
            current, _ = self._advisory_status_in_session(session)
            if current.reason == "LEDGER_QUARANTINED":
                raise ClinicalValidationError(
                    "Ledger sesi pilot dikarantina; pulihkan integritas "
                    "sebelum aktivasi baru"
                )
            if current.emergency_stop:
                raise ClinicalValidationError(
                    "Emergency stop masih aktif; IT Admin/Super Admin harus "
                    "membukanya sebelum aktivasi"
                )
            if current.active:
                raise ClinicalValidationError(
                    "Advisory Pilot sudah aktif dan masih valid"
                )
            if self._pending_authorization_request(session) is not None:
                raise ClinicalValidationError(
                    "Masih ada permintaan otorisasi Advisory yang menunggu"
                )
            if not current.gate_ready:
                raise ClinicalValidationError(
                    "Gate Advisory Pilot belum lulus: "
                    + "; ".join(current.blockers)
                )
            campaign = session.scalar(
                select(ValidationCampaign)
                .order_by(ValidationCampaign.created_at.desc())
                .limit(1)
            )
            uat = session.scalar(
                select(UatSession)
                .order_by(UatSession.created_at.desc())
                .limit(1)
            )
            if (
                campaign is None
                or uat is None
                or uat.pharmacist_approved_at is None
                or uat.it_approved_at is None
            ):
                raise ClinicalValidationError(
                    "Bukti kampanye dan dual sign-off UAT belum lengkap"
                )
            now = utc_now()
            request = AdvisoryPilotAuthorizationRequest(
                purpose="INITIAL",
                status="PENDING_CLINICAL",
                application_version=__version__,
                validation_campaign_id=campaign.id,
                uat_session_id=uat.id,
                pharmacist_approved_at=uat.pharmacist_approved_at,
                it_approved_at=uat.it_approved_at,
                duration_hours=duration_hours,
                requested_by=actor_user_id,
                requested_at=now,
                request_expires_at=now + timedelta(minutes=30),
                technical_approved_by=actor_user_id,
                technical_approved_at=now,
            )
            session.add(request)
            session.flush()
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_ACTIVATION_REQUESTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={
                        "application_version": __version__,
                        "validation_campaign_id": campaign.id,
                        "uat_session_id": uat.id,
                        "duration_hours": duration_hours,
                        "request_expires_at": (
                            request.request_expires_at.isoformat()
                        ),
                    },
                ),
            )
            session.commit()
            return self._authorization_request_view(request)

    def _complete_authorization_request(
        self,
        session: Session,
        request: AdvisoryPilotAuthorizationRequest,
        technical_actor_id: str,
        clinical_actor_id: str,
        prior_activation: AdvisoryPilotActivation | None = None,
    ) -> AdvisoryPilotStatus:
        if technical_actor_id == clinical_actor_id:
            raise ClinicalValidationPermissionError(
                "Otorisasi teknis dan klinis wajib diberikan pengguna berbeda"
            )
        current, _ = self._advisory_status_in_session(session)
        if current.emergency_stop:
            raise ClinicalValidationError("Emergency stop masih aktif")
        if not current.gate_ready:
            request.status = "CANCELLED"
            request.cancelled_at = utc_now()
            request.cancellation_reason = "GATE_NOT_READY"
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_AUTHORIZATION_REQUEST_CANCELLED",
                    outcome="SUCCESS",
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={"reason": "GATE_NOT_READY"},
                ),
            )
            session.commit()
            raise ClinicalValidationError(
                "Gate berubah setelah permintaan dibuat: "
                + "; ".join(current.blockers)
            )
        campaign = session.scalar(
            select(ValidationCampaign)
            .order_by(ValidationCampaign.created_at.desc())
            .limit(1)
        )
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc()).limit(1)
        )
        binding_matches = bool(
            campaign
            and uat
            and request.application_version == __version__
            and request.validation_campaign_id == campaign.id
            and request.uat_session_id == uat.id
            and request.pharmacist_approved_at == uat.pharmacist_approved_at
            and request.it_approved_at == uat.it_approved_at
        )
        if not binding_matches:
            request.status = "CANCELLED"
            request.cancelled_at = utc_now()
            request.cancellation_reason = "EVIDENCE_BINDING_CHANGED"
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_AUTHORIZATION_REQUEST_CANCELLED",
                    outcome="SUCCESS",
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={"reason": "EVIDENCE_BINDING_CHANGED"},
                ),
            )
            session.commit()
            raise ClinicalValidationError(
                "Bukti gate berubah; buat permintaan otorisasi baru"
            )
        now = utc_now()
        if prior_activation is not None:
            if (
                request.outgoing_attested_by
                != prior_activation.clinical_owner_id
                or request.outgoing_attested_at is None
            ):
                raise ClinicalValidationError(
                    "Pemilik shift lama belum memberikan outgoing attestation"
                )
            self._finalize_shift_closeout(
                session,
                prior_activation,
                "HANDOVER",
                technical_actor_id,
                request=request,
            )
            prior_activation.status = "REVOKED"
            prior_activation.revoked_by = technical_actor_id
            prior_activation.revoked_at = now
            prior_activation.revocation_reason = "SHIFT_HANDOVER"
        activation_expires_at = now + timedelta(hours=request.duration_hours)
        shift_expires_at = min(
            activation_expires_at,
            now + timedelta(hours=self.SHIFT_MAX_HOURS),
        )
        activation = AdvisoryPilotActivation(
            application_version=__version__,
            validation_campaign_id=campaign.id,
            uat_session_id=uat.id,
            pharmacist_approved_at=uat.pharmacist_approved_at,
            it_approved_at=uat.it_approved_at,
            activated_by=technical_actor_id,
            clinical_owner_id=clinical_actor_id,
            technical_authorizer_id=technical_actor_id,
            authorization_request_id=request.id,
            activated_at=now,
            expires_at=activation_expires_at,
            shift_started_at=now,
            shift_expires_at=shift_expires_at,
        )
        session.add(activation)
        session.flush()
        self._append_pilot_ledger(
            session,
            activation.id,
            "SHIFT_OPENED",
            clinical_actor_id,
            {
                "authorization_request_id": request.id,
                "purpose": request.purpose,
                "clinical_owner_id": clinical_actor_id,
                "technical_authorizer_id": technical_actor_id,
                "activation_expires_at": activation_expires_at.isoformat(),
                "shift_expires_at": shift_expires_at.isoformat(),
                "prior_activation_id": (
                    prior_activation.id if prior_activation else None
                ),
            },
        )
        request.status = "COMPLETED"
        request.technical_approved_by = technical_actor_id
        request.technical_approved_at = request.technical_approved_at or now
        request.clinical_approved_by = clinical_actor_id
        request.clinical_approved_at = request.clinical_approved_at or now
        request.resulting_activation_id = activation.id
        request.completed_at = now
        self.audit.append(
            session,
            AuditEvent(
                category="PILOT_CONTROL",
                action=(
                    "ADVISORY_SHIFT_HANDOVER_COMPLETED"
                    if request.purpose == "HANDOVER"
                    else "ADVISORY_PILOT_ACTIVATED"
                ),
                outcome="SUCCESS",
                actor_user_id=technical_actor_id,
                entity_type="ADVISORY_PILOT_ACTIVATION",
                entity_id=activation.id,
                details={
                    "authorization_request_id": request.id,
                    "technical_authorizer_id": technical_actor_id,
                    "clinical_owner_id": clinical_actor_id,
                    "validation_campaign_id": campaign.id,
                    "duration_hours": request.duration_hours,
                    "expires_at": activation.expires_at.isoformat(),
                    "prior_activation_id": (
                        prior_activation.id if prior_activation else None
                    ),
                },
            ),
        )
        session.commit()
        return AdvisoryPilotStatus(
            active=True,
            gate_ready=True,
            activation_id=activation.id,
            campaign_id=campaign.id,
            activated_at=activation.activated_at,
            expires_at=activation.expires_at,
            clinical_owner_id=activation.clinical_owner_id,
            shift_started_at=activation.shift_started_at,
            shift_expires_at=activation.shift_expires_at,
            emergency_stop=False,
            reason="ACTIVE",
            blockers=(),
        )

    def approve_advisory_pilot_activation(
        self, request_id: str, actor_user_id: str
    ) -> AdvisoryPilotStatus:
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.CLINICAL_DUTY_APPROVERS):
                raise ClinicalValidationPermissionError(
                    "Persetujuan kedua wajib diberikan Apoteker, KFT, atau "
                    "Clinical Reviewer"
                )
            request = session.get(AdvisoryPilotAuthorizationRequest, request_id)
            if request is None or request.status != "PENDING_CLINICAL":
                raise ClinicalValidationError(
                    "Permintaan aktivasi klinis tidak tersedia"
                )
            if self._as_utc(request.request_expires_at) <= utc_now():
                request.status = "EXPIRED"
                request.cancelled_at = utc_now()
                request.cancellation_reason = "REQUEST_EXPIRED"
                self.audit.append(
                    session,
                    AuditEvent(
                        category="PILOT_CONTROL",
                        action="ADVISORY_AUTHORIZATION_REQUEST_EXPIRED",
                        outcome="SUCCESS",
                        entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                        entity_id=request.id,
                        details={"purpose": request.purpose},
                    ),
                )
                session.commit()
                raise ClinicalValidationError("Permintaan aktivasi kedaluwarsa")
            return self._complete_authorization_request(
                session,
                request,
                request.technical_approved_by,
                actor_user_id,
            )

    def request_advisory_shift_handover(
        self, actor_user_id: str, duration_hours: int = 24
    ) -> AdvisoryAuthorizationRequestStatus:
        if duration_hours not in self.PILOT_AUTHORIZATION_HOURS:
            raise ClinicalValidationError("Durasi handover tidak valid")
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.CLINICAL_DUTY_APPROVERS):
                raise ClinicalValidationPermissionError(
                    "Handover hanya dapat diajukan petugas klinis pengganti"
                )
            current, _ = self._advisory_status_in_session(session)
            if not current.active or current.activation_id is None:
                raise ClinicalValidationError("Advisory Pilot tidak sedang aktif")
            prior = session.get(AdvisoryPilotActivation, current.activation_id)
            if prior.clinical_owner_id == actor_user_id:
                raise ClinicalValidationError(
                    "Pemilik shift saat ini tidak dapat handover kepada dirinya"
                )
            if self._pending_authorization_request(session) is not None:
                raise ClinicalValidationError("Masih ada permintaan yang menunggu")
            now = utc_now()
            summary = self._shift_summary(session)
            request = AdvisoryPilotAuthorizationRequest(
                purpose="HANDOVER",
                status="PENDING_OUTGOING",
                application_version=__version__,
                validation_campaign_id=prior.validation_campaign_id,
                uat_session_id=prior.uat_session_id,
                pharmacist_approved_at=prior.pharmacist_approved_at,
                it_approved_at=prior.it_approved_at,
                duration_hours=duration_hours,
                requested_by=actor_user_id,
                requested_at=now,
                request_expires_at=now + timedelta(minutes=30),
                clinical_approved_by=actor_user_id,
                clinical_approved_at=now,
                handover_from_activation_id=prior.id,
                handover_summary_json=summary.summary_json,
                handover_summary_sha256=summary.summary_sha256,
                unresolved_alerts=summary.unresolved_alerts,
                unresolved_critical_alerts=(
                    summary.unresolved_critical_alerts
                ),
                unresolved_interventions=summary.unresolved_interventions,
            )
            session.add(request)
            session.flush()
            self._append_pilot_ledger(
                session,
                prior.id,
                "HANDOVER_INCOMING_ATTESTED",
                actor_user_id,
                {
                    "authorization_request_id": request.id,
                    "summary_sha256": summary.summary_sha256,
                    "unresolved_alerts": summary.unresolved_alerts,
                    "unresolved_critical_alerts": (
                        summary.unresolved_critical_alerts
                    ),
                    "unresolved_interventions": (
                        summary.unresolved_interventions
                    ),
                },
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_SHIFT_HANDOVER_REQUESTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={
                        "prior_activation_id": prior.id,
                        "incoming_attested_by": actor_user_id,
                        "summary_sha256": summary.summary_sha256,
                        "unresolved_alerts": summary.unresolved_alerts,
                        "unresolved_critical_alerts": (
                            summary.unresolved_critical_alerts
                        ),
                        "unresolved_interventions": (
                            summary.unresolved_interventions
                        ),
                    },
                ),
            )
            session.commit()
            return self._authorization_request_view(request)

    def attest_advisory_shift_handover(
        self, request_id: str, actor_user_id: str
    ) -> AdvisoryAuthorizationRequestStatus:
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.CLINICAL_DUTY_APPROVERS):
                raise ClinicalValidationPermissionError(
                    "Outgoing attestation hanya dapat diberikan pemilik shift klinis"
                )
            request = session.get(AdvisoryPilotAuthorizationRequest, request_id)
            if request is None or request.status != "PENDING_OUTGOING":
                raise ClinicalValidationError(
                    "Permintaan handover tidak menunggu outgoing attestation"
                )
            if self._as_utc(request.request_expires_at) <= utc_now():
                request.status = "EXPIRED"
                request.cancelled_at = utc_now()
                request.cancellation_reason = "REQUEST_EXPIRED"
                self._append_pilot_ledger(
                    session,
                    request.handover_from_activation_id,
                    "HANDOVER_REQUEST_EXPIRED",
                    actor_user_id,
                    {"authorization_request_id": request.id},
                )
                self.audit.append(
                    session,
                    AuditEvent(
                        category="PILOT_CONTROL",
                        action="ADVISORY_AUTHORIZATION_REQUEST_EXPIRED",
                        outcome="SUCCESS",
                        actor_user_id=actor_user_id,
                        entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                        entity_id=request.id,
                        details={"purpose": request.purpose},
                    ),
                )
                session.commit()
                raise ClinicalValidationError("Permintaan handover kedaluwarsa")
            prior = session.get(
                AdvisoryPilotActivation, request.handover_from_activation_id
            )
            current, changed = self._advisory_status_in_session(session)
            if (
                changed
                or prior is None
                or not current.active
                or current.activation_id != prior.id
                or prior.status != "ACTIVE"
            ):
                if changed:
                    session.commit()
                raise ClinicalValidationError(
                    "Shift asal sudah tidak aktif atau kedaluwarsa"
                )
            if prior.clinical_owner_id != actor_user_id:
                raise ClinicalValidationPermissionError(
                    "Hanya pemilik shift saat ini yang dapat memberi outgoing attestation"
                )
            if request.clinical_approved_by == actor_user_id:
                raise ClinicalValidationPermissionError(
                    "Outgoing dan incoming attestation wajib memakai akun berbeda"
                )
            if not request.handover_summary_json:
                raise ClinicalValidationError("Ringkasan handover tidak tersedia")
            expected_hash = hashlib.sha256(
                request.handover_summary_json.encode("utf-8")
            ).hexdigest()
            if expected_hash != request.handover_summary_sha256:
                raise ClinicalValidationError(
                    "Checksum ringkasan handover tidak valid"
                )
            now = utc_now()
            request.outgoing_attested_by = actor_user_id
            request.outgoing_attested_at = now
            request.status = "PENDING_TECHNICAL"
            self._append_pilot_ledger(
                session,
                prior.id,
                "HANDOVER_OUTGOING_ATTESTED",
                actor_user_id,
                {
                    "authorization_request_id": request.id,
                    "incoming_attested_by": request.clinical_approved_by,
                    "summary_sha256": expected_hash,
                },
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_SHIFT_OUTGOING_ATTESTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                    entity_id=request.id,
                    details={
                        "prior_activation_id": prior.id,
                        "incoming_attested_by": request.clinical_approved_by,
                        "summary_sha256": expected_hash,
                    },
                ),
            )
            session.commit()
            return self._authorization_request_view(request)

    def approve_advisory_shift_handover(
        self, request_id: str, actor_user_id: str
    ) -> AdvisoryPilotStatus:
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.PILOT_CONTROLLERS):
                raise ClinicalValidationPermissionError(
                    "Handover wajib disahkan IT Admin atau Super Admin"
                )
            request = session.get(AdvisoryPilotAuthorizationRequest, request_id)
            if request is None or request.status != "PENDING_TECHNICAL":
                raise ClinicalValidationError("Permintaan handover tidak tersedia")
            if self._as_utc(request.request_expires_at) <= utc_now():
                request.status = "EXPIRED"
                request.cancelled_at = utc_now()
                request.cancellation_reason = "REQUEST_EXPIRED"
                self._append_pilot_ledger(
                    session,
                    request.handover_from_activation_id,
                    "HANDOVER_REQUEST_EXPIRED",
                    actor_user_id,
                    {"authorization_request_id": request.id},
                )
                self.audit.append(
                    session,
                    AuditEvent(
                        category="PILOT_CONTROL",
                        action="ADVISORY_AUTHORIZATION_REQUEST_EXPIRED",
                        outcome="SUCCESS",
                        entity_type="ADVISORY_AUTHORIZATION_REQUEST",
                        entity_id=request.id,
                        details={"purpose": request.purpose},
                    ),
                )
                session.commit()
                raise ClinicalValidationError("Permintaan handover kedaluwarsa")
            if request.clinical_approved_by == actor_user_id:
                raise ClinicalValidationPermissionError(
                    "Pengesah teknis harus berbeda dari pemilik shift klinis"
                )
            prior = session.get(
                AdvisoryPilotActivation, request.handover_from_activation_id
            )
            current, changed = self._advisory_status_in_session(session)
            if (
                changed
                or prior is None
                or prior.status != "ACTIVE"
                or not current.active
                or current.activation_id != prior.id
            ):
                if changed:
                    session.commit()
                raise ClinicalValidationError(
                    "Aktivasi atau shift asal handover tidak aktif"
                )
            return self._complete_authorization_request(
                session,
                request,
                actor_user_id,
                request.clinical_approved_by,
                prior,
            )

    def close_advisory_shift(
        self, actor_user_id: str, attestation_note: str
    ) -> AdvisoryPilotStatus:
        normalized_note = " ".join(attestation_note.strip().split())
        if not 10 <= len(normalized_note) <= 300:
            raise ClinicalValidationError(
                "Catatan closeout wajib 10-300 karakter"
            )
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.CLINICAL_DUTY_APPROVERS):
                raise ClinicalValidationPermissionError(
                    "Closeout hanya dapat dilakukan pemilik shift klinis"
                )
            current, changed = self._advisory_status_in_session(session)
            if changed or not current.active or current.activation_id is None:
                if changed:
                    session.commit()
                raise ClinicalValidationError(
                    "Shift Advisory tidak aktif atau sudah kedaluwarsa"
                )
            activation = session.get(
                AdvisoryPilotActivation, current.activation_id
            )
            if activation.clinical_owner_id != actor_user_id:
                raise ClinicalValidationPermissionError(
                    "Hanya pemilik klinis aktif yang dapat menutup shift"
                )
            now = utc_now()
            activation.status = "REVOKED"
            activation.revoked_by = actor_user_id
            activation.revoked_at = now
            activation.revocation_reason = "SHIFT_CLOSED_BY_OWNER"
            pending_requests = session.scalars(
                select(AdvisoryPilotAuthorizationRequest).where(
                    AdvisoryPilotAuthorizationRequest.status.in_(
                        (
                            "PENDING_CLINICAL",
                            "PENDING_OUTGOING",
                            "PENDING_TECHNICAL",
                        )
                    )
                )
            ).all()
            for pending in pending_requests:
                pending.status = "CANCELLED"
                pending.cancelled_at = now
                pending.cancellation_reason = "SHIFT_CLOSED_BY_OWNER"
            self._finalize_shift_closeout(
                session,
                activation,
                "OWNER_CLOSEOUT",
                actor_user_id,
                notes=normalized_note,
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_SHIFT_OWNER_CLOSEOUT",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_PILOT_ACTIVATION",
                    entity_id=activation.id,
                    details={
                        "cancelled_pending_requests": len(pending_requests),
                    },
                ),
            )
            session.commit()
            return AdvisoryPilotStatus(
                active=False,
                gate_ready=current.gate_ready,
                activation_id=activation.id,
                campaign_id=current.campaign_id,
                activated_at=activation.activated_at,
                expires_at=activation.expires_at,
                clinical_owner_id=activation.clinical_owner_id,
                shift_started_at=activation.shift_started_at,
                shift_expires_at=activation.shift_expires_at,
                emergency_stop=False,
                reason="SHIFT_CLOSED_BY_OWNER",
                blockers=("Shift ditutup oleh pemilik klinis",),
            )

    def pilot_session_ledger(
        self, actor_user_id: str, limit: int = 200
    ) -> tuple[PilotSessionLedgerEntry, ...]:
        if not 1 <= limit <= 500:
            raise ClinicalValidationError("Batas ledger harus 1-500 entri")
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not self._verify_pilot_ledger_in_session(session):
                raise ClinicalValidationError(
                    "Rantai ledger sesi pilot tidak valid"
                )
            rows = session.scalars(
                select(AdvisoryPilotSessionLedger)
                .order_by(AdvisoryPilotSessionLedger.id.desc())
                .limit(limit)
            ).all()
            return tuple(
                PilotSessionLedgerEntry(
                    sequence=row.id,
                    event_id=row.event_id,
                    activation_id=row.activation_id,
                    event_type=row.event_type,
                    actor_user_id=row.actor_user_id,
                    occurred_at=row.occurred_at,
                    payload_json=row.payload_json,
                    previous_hash=row.previous_hash,
                    entry_hash=row.entry_hash,
                )
                for row in rows
            )

    def verify_pilot_session_ledger(self, actor_user_id: str) -> bool:
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            return self._verify_pilot_ledger_in_session(session)

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _evidence_datetime(value: str) -> datetime:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)

    @classmethod
    def _evidence_csv_rows(
        cls, payload: bytes, expected_headers: tuple[str, ...]
    ) -> list[dict[str, str]]:
        text_payload = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text_payload, newline=""))
        if tuple(reader.fieldnames or ()) != expected_headers:
            raise ValueError("INVALID_HEADERS")
        rows = list(reader)
        if len(rows) > cls.MAX_EVIDENCE_ROWS:
            raise ValueError("TOO_MANY_ROWS")
        return rows

    @classmethod
    def _verify_evidence_ledger(
        cls, payload: bytes
    ) -> tuple[int, str]:
        rows = cls._evidence_csv_rows(
            payload, cls.EVIDENCE_LEDGER_HEADERS
        )
        expected_previous = cls.LEDGER_GENESIS_HASH
        for expected_sequence, row in enumerate(rows, start=1):
            if int(row["sequence"]) != expected_sequence:
                raise ValueError("INVALID_SEQUENCE")
            payload_value = json.loads(row["payload_json"])
            if not isinstance(payload_value, dict):
                raise ValueError("INVALID_PAYLOAD")
            canonical_payload = json.dumps(
                payload_value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if canonical_payload != row["payload_json"]:
                raise ValueError("NON_CANONICAL_PAYLOAD")
            if row["previous_hash"] != expected_previous:
                raise ValueError("INVALID_PREVIOUS_HASH")
            if not cls._is_sha256(row["entry_hash"]):
                raise ValueError("INVALID_ENTRY_HASH")
            actor_user_id = (
                None
                if row["actor_user_id"] == "SYSTEM"
                else row["actor_user_id"]
            )
            occurred_at = cls._evidence_datetime(row["occurred_at"])
            hash_payload = {
                "event_id": row["event_id"],
                "activation_id": row["activation_id"],
                "event_type": row["event_type"],
                "actor_user_id": actor_user_id,
                "occurred_at": AuditService._canonical_datetime(occurred_at),
                "payload_json": row["payload_json"],
                "previous_hash": row["previous_hash"],
            }
            expected_hash = hashlib.sha256(
                json.dumps(
                    hash_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if row["entry_hash"] != expected_hash:
                raise ValueError("ENTRY_HASH_MISMATCH")
            expected_previous = row["entry_hash"]
        return len(rows), expected_previous

    @classmethod
    def _verify_evidence_closeouts(cls, payload: bytes) -> int:
        rows = cls._evidence_csv_rows(
            payload, cls.EVIDENCE_CLOSEOUT_HEADERS
        )
        seen_ids: set[str] = set()
        for row in rows:
            closeout_id = row["closeout_id"]
            if not closeout_id or closeout_id in seen_ids:
                raise ValueError("INVALID_CLOSEOUT_ID")
            seen_ids.add(closeout_id)
            cls._evidence_datetime(row["closed_at"])
            for field in (
                "unresolved_alerts",
                "unresolved_critical_alerts",
                "unresolved_interventions",
            ):
                if int(row[field]) < 0:
                    raise ValueError("INVALID_CLOSEOUT_COUNT")
            if not cls._is_sha256(row["summary_sha256"]):
                raise ValueError("INVALID_SUMMARY_HASH")
        return len(rows)

    @classmethod
    def _inspect_pilot_evidence_package(
        cls, source: Path
    ) -> _PilotEvidenceInspection:
        errors: list[str] = []
        checksum: str | None = None
        if source.suffix.casefold() != ".zip":
            errors.append("INVALID_EXTENSION")
        try:
            size = source.stat().st_size
        except FileNotFoundError:
            return _PilotEvidenceInspection(errors=("FILE_NOT_FOUND",))
        except OSError:
            return _PilotEvidenceInspection(errors=("FILE_UNREADABLE",))
        if size > cls.MAX_EVIDENCE_PACKAGE_BYTES:
            return _PilotEvidenceInspection(errors=("PACKAGE_TOO_LARGE",))
        try:
            package_bytes = source.read_bytes()
        except OSError:
            return _PilotEvidenceInspection(errors=("FILE_UNREADABLE",))
        checksum = hashlib.sha256(package_bytes).hexdigest()
        if errors:
            return _PilotEvidenceInspection(
                checksum_sha256=checksum, errors=tuple(errors)
            )
        try:
            archive = zipfile.ZipFile(io.BytesIO(package_bytes))
        except (OSError, zipfile.BadZipFile):
            return _PilotEvidenceInspection(
                checksum_sha256=checksum, errors=("INVALID_ZIP",)
            )
        with archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > len(cls.EVIDENCE_FILES):
                errors.append("TOO_MANY_ENTRIES")
            if len(names) != len(set(names)):
                errors.append("DUPLICATE_ENTRY")
            if set(names) != cls.EVIDENCE_FILES:
                errors.append("UNEXPECTED_ENTRIES")
            total_size = sum(info.file_size for info in infos)
            if total_size > cls.MAX_EVIDENCE_UNCOMPRESSED_BYTES:
                errors.append("ARCHIVE_TOO_LARGE")
            for info in infos:
                unix_type = (info.external_attr >> 16) & 0o170000
                if info.is_dir() or unix_type == 0o120000:
                    errors.append("UNSAFE_ENTRY")
                if info.flag_bits & 0x1:
                    errors.append("ENCRYPTED_ENTRY")
                if info.file_size > cls.MAX_EVIDENCE_MEMBER_BYTES:
                    errors.append("ENTRY_TOO_LARGE")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > cls.MAX_EVIDENCE_COMPRESSION_RATIO:
                    errors.append("SUSPICIOUS_COMPRESSION")
            if errors:
                return _PilotEvidenceInspection(
                    checksum_sha256=checksum,
                    errors=tuple(dict.fromkeys(errors)),
                )
            try:
                contents = {
                    name: archive.read(name) for name in cls.EVIDENCE_FILES
                }
            except (OSError, RuntimeError, KeyError, zipfile.BadZipFile):
                return _PilotEvidenceInspection(
                    checksum_sha256=checksum, errors=("CORRUPT_ENTRY",)
                )

        try:
            manifest = json.loads(contents["manifest.json"])
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _PilotEvidenceInspection(
                checksum_sha256=checksum, errors=("INVALID_MANIFEST",)
            )
        if not isinstance(manifest, dict):
            return _PilotEvidenceInspection(
                checksum_sha256=checksum, errors=("INVALID_MANIFEST",)
            )
        manifest_format = manifest.get("format")
        application_version = manifest.get("application_version")
        schema_revision = manifest.get("schema_revision")
        ledger_head_hash = manifest.get("ledger_head_hash")
        ledger_entries = manifest.get("ledger_entries")
        closeouts = manifest.get("closeouts")
        if manifest_format != cls.EVIDENCE_FORMAT:
            errors.append("UNSUPPORTED_FORMAT")
        if manifest.get("contains_patient_identity") is not False:
            errors.append("PATIENT_IDENTITY_DECLARED")
        if not isinstance(application_version, str) or not application_version:
            errors.append("INVALID_APPLICATION_VERSION")
            application_version = None
        if not isinstance(schema_revision, str) or not schema_revision:
            errors.append("INVALID_SCHEMA_REVISION")
            schema_revision = None
        if not cls._is_sha256(ledger_head_hash):
            errors.append("INVALID_HEAD_HASH")
            ledger_head_hash = None
        if (
            not isinstance(ledger_entries, int)
            or isinstance(ledger_entries, bool)
            or ledger_entries < 0
        ):
            errors.append("INVALID_LEDGER_COUNT")
            ledger_entries = None
        if (
            not isinstance(closeouts, int)
            or isinstance(closeouts, bool)
            or closeouts < 0
        ):
            errors.append("INVALID_CLOSEOUT_COUNT")
            closeouts = None
        try:
            cls._evidence_datetime(str(manifest["exported_at"]))
        except (KeyError, TypeError, ValueError):
            errors.append("INVALID_EXPORTED_AT")
        file_digests = manifest.get("files")
        expected_digest_names = cls.EVIDENCE_FILES - {"manifest.json"}
        if not isinstance(file_digests, dict) or set(file_digests) != expected_digest_names:
            errors.append("INVALID_FILE_DIGESTS")
        else:
            for name in expected_digest_names:
                expected_digest = file_digests[name]
                actual_digest = hashlib.sha256(contents[name]).hexdigest()
                if not cls._is_sha256(expected_digest) or expected_digest != actual_digest:
                    errors.append("FILE_CHECKSUM_MISMATCH")
                    break
        try:
            actual_entries, actual_head = cls._verify_evidence_ledger(
                contents["pilot_session_ledger.csv"]
            )
        except (UnicodeDecodeError, csv.Error, KeyError, TypeError, ValueError):
            errors.append("LEDGER_CHAIN_INVALID")
        else:
            if ledger_entries is not None and ledger_entries != actual_entries:
                errors.append("LEDGER_COUNT_MISMATCH")
            if ledger_head_hash is not None and ledger_head_hash != actual_head:
                errors.append("HEAD_HASH_MISMATCH")
        try:
            actual_closeouts = cls._verify_evidence_closeouts(
                contents["pilot_shift_closeouts.csv"]
            )
        except (UnicodeDecodeError, csv.Error, KeyError, TypeError, ValueError):
            errors.append("CLOSEOUT_DATA_INVALID")
        else:
            if closeouts is not None and closeouts != actual_closeouts:
                errors.append("CLOSEOUT_COUNT_MISMATCH")
        return _PilotEvidenceInspection(
            checksum_sha256=checksum,
            errors=tuple(dict.fromkeys(errors)),
            manifest_format=(
                manifest_format if isinstance(manifest_format, str) else None
            ),
            application_version=application_version,
            schema_revision=schema_revision,
            ledger_head_hash=ledger_head_hash,
            ledger_entries=ledger_entries,
            closeouts=closeouts,
        )

    @staticmethod
    def _evidence_verification_view(
        row: PilotEvidenceVerification,
    ) -> PilotEvidenceVerificationResult:
        try:
            errors = tuple(json.loads(row.errors_json))
        except (TypeError, json.JSONDecodeError):
            errors = ("INVALID_STORED_RESULT",)
        return PilotEvidenceVerificationResult(
            record_id=row.id,
            package_filename=row.package_filename,
            checksum_sha256=row.package_checksum_sha256,
            valid=row.outcome == "VALID",
            errors=errors,
            manifest_format=row.manifest_format,
            application_version=row.application_version,
            schema_revision=row.schema_revision,
            ledger_head_hash=row.ledger_head_hash,
            ledger_entries=row.ledger_entries,
            closeouts=row.closeouts,
            verified_by=row.verified_by,
            verified_at=row.verified_at,
        )

    def verify_pilot_evidence_package(
        self, path: Path | str, actor_user_id: str
    ) -> PilotEvidenceVerificationResult:
        source = Path(path)
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            inspection = self._inspect_pilot_evidence_package(source)
            outcome = "VALID" if not inspection.errors else "INVALID"
            record = PilotEvidenceVerification(
                package_filename=(source.name or "UNNAMED")[:260],
                package_checksum_sha256=inspection.checksum_sha256,
                manifest_format=inspection.manifest_format,
                application_version=inspection.application_version,
                schema_revision=inspection.schema_revision,
                ledger_head_hash=inspection.ledger_head_hash,
                ledger_entries=inspection.ledger_entries,
                closeouts=inspection.closeouts,
                outcome=outcome,
                errors_json=json.dumps(list(inspection.errors)),
                verified_by=actor_user_id,
                verified_at=utc_now(),
            )
            session.add(record)
            session.flush()
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_EVIDENCE",
                    action="PILOT_EVIDENCE_PACKAGE_VERIFIED",
                    outcome="SUCCESS" if outcome == "VALID" else "FAILURE",
                    actor_user_id=actor_user_id,
                    entity_type="PILOT_EVIDENCE_VERIFICATION",
                    entity_id=record.id,
                    details={
                        "package_filename": record.package_filename,
                        "package_checksum_sha256": inspection.checksum_sha256,
                        "verification_outcome": outcome,
                        "error_codes": list(inspection.errors),
                        "ledger_head_hash": inspection.ledger_head_hash,
                    },
                ),
            )
            session.commit()
            return self._evidence_verification_view(record)

    def pilot_evidence_verifications(
        self, actor_user_id: str, limit: int = 100
    ) -> tuple[PilotEvidenceVerificationResult, ...]:
        if not 1 <= limit <= 200:
            raise ClinicalValidationError(
                "Batas riwayat verifikasi harus 1-200 entri"
            )
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            rows = session.scalars(
                select(PilotEvidenceVerification)
                .order_by(PilotEvidenceVerification.verified_at.desc())
                .limit(limit)
            ).all()
            return tuple(
                self._evidence_verification_view(row) for row in rows
            )

    def reset_pilot_ledger_quarantine(
        self, actor_user_id: str, recovery_reference: str
    ) -> AdvisoryPilotStatus:
        normalized_reference = " ".join(recovery_reference.strip().split())
        if not 10 <= len(normalized_reference) <= 300:
            raise ClinicalValidationError(
                "Referensi pemulihan wajib 10-300 karakter"
            )
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.PILOT_CONTROLLERS):
                raise ClinicalValidationPermissionError(
                    "Hanya IT Admin atau Super Admin yang dapat membuka "
                    "karantina ledger"
                )
            control = self._safety_control(session)
            if not control.ledger_quarantine:
                raise ClinicalValidationError(
                    "Ledger sesi pilot tidak sedang dikarantina"
                )
            if not self._verify_pilot_ledger_in_session(session):
                raise ClinicalValidationError(
                    "Rantai ledger masih tidak valid; restore backup "
                    "terverifikasi sebelum membuka karantina"
                )
            now = utc_now()
            previous_reason = control.ledger_quarantine_reason
            detected_head_hash = control.ledger_detected_head_hash
            control.ledger_quarantine = False
            control.ledger_quarantine_reason = None
            control.ledger_quarantined_at = None
            control.ledger_detected_head_hash = None
            control.ledger_quarantine_cleared_by = actor_user_id
            control.ledger_quarantine_cleared_at = now
            control.updated_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_LEDGER",
                    action="PILOT_LEDGER_QUARANTINE_CLEARED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_PILOT_SAFETY_CONTROL",
                    entity_id=control.id,
                    details={
                        "previous_reason": previous_reason,
                        "detected_head_hash": detected_head_hash,
                        "recovery_reference": normalized_reference,
                        "requires_reactivation": True,
                    },
                ),
            )
            status, _ = self._advisory_status_in_session(session)
            session.commit()
            return status

    def export_pilot_session_evidence(
        self, target: Path | str, actor_user_id: str
    ) -> PilotEvidenceExportResult:
        output = Path(target)
        if output.suffix.casefold() != ".zip":
            output = output.with_suffix(".zip")
        temporary = output.with_suffix(output.suffix + ".tmp")
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not self._verify_pilot_ledger_in_session(session):
                raise ClinicalValidationError(
                    "Paket bukti tidak dapat dibuat karena rantai ledger tidak valid"
                )
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ClinicalValidationError(
                    f"Folder ekspor paket bukti tidak dapat dibuat: {exc}"
                ) from exc
            ledger_rows = session.scalars(
                select(AdvisoryPilotSessionLedger).order_by(
                    AdvisoryPilotSessionLedger.id
                )
            ).all()
            closeout_rows = session.scalars(
                select(AdvisoryPilotShiftCloseout).order_by(
                    AdvisoryPilotShiftCloseout.closed_at,
                    AdvisoryPilotShiftCloseout.id,
                )
            ).all()

            ledger_buffer = io.StringIO(newline="")
            ledger_writer = csv.writer(ledger_buffer, lineterminator="\n")
            ledger_writer.writerow(
                (
                    "sequence",
                    "event_id",
                    "activation_id",
                    "event_type",
                    "actor_user_id",
                    "occurred_at",
                    "payload_json",
                    "previous_hash",
                    "entry_hash",
                )
            )
            for row in ledger_rows:
                ledger_writer.writerow(
                    (
                        row.id,
                        row.event_id,
                        row.activation_id,
                        row.event_type,
                        row.actor_user_id or "SYSTEM",
                        row.occurred_at.isoformat(),
                        row.payload_json,
                        row.previous_hash,
                        row.entry_hash,
                    )
                )
            ledger_bytes = ledger_buffer.getvalue().encode("utf-8")

            closeout_buffer = io.StringIO(newline="")
            closeout_writer = csv.writer(
                closeout_buffer, lineterminator="\n"
            )
            closeout_writer.writerow(
                (
                    "closeout_id",
                    "activation_id",
                    "closeout_type",
                    "closed_by",
                    "closed_at",
                    "unresolved_alerts",
                    "unresolved_critical_alerts",
                    "unresolved_interventions",
                    "summary_sha256",
                    "outgoing_attested_by",
                    "incoming_attested_by",
                    "handover_request_id",
                )
            )
            for row in closeout_rows:
                closeout_writer.writerow(
                    (
                        row.id,
                        row.activation_id,
                        row.closeout_type,
                        row.closed_by or "SYSTEM",
                        row.closed_at.isoformat(),
                        row.unresolved_alerts,
                        row.unresolved_critical_alerts,
                        row.unresolved_interventions,
                        row.summary_sha256,
                        row.outgoing_attested_by or "",
                        row.incoming_attested_by or "",
                        row.handover_request_id or "",
                    )
                )
            closeout_bytes = closeout_buffer.getvalue().encode("utf-8")
            ledger_head_hash = (
                ledger_rows[-1].entry_hash
                if ledger_rows
                else self.LEDGER_GENESIS_HASH
            )
            exported_at = utc_now()
            manifest = {
                "format": "EMSS_PILOT_EVIDENCE_V1",
                "application_version": __version__,
                "schema_revision": self.database.current_revision(),
                "exported_at": exported_at.isoformat(),
                "contains_patient_identity": False,
                "ledger_entries": len(ledger_rows),
                "closeouts": len(closeout_rows),
                "ledger_head_hash": ledger_head_hash,
                "files": {
                    "pilot_session_ledger.csv": hashlib.sha256(
                        ledger_bytes
                    ).hexdigest(),
                    "pilot_shift_closeouts.csv": hashlib.sha256(
                        closeout_bytes
                    ).hexdigest(),
                },
            }
            manifest_bytes = json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            try:
                with zipfile.ZipFile(
                    temporary, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    archive.writestr("manifest.json", manifest_bytes)
                    archive.writestr(
                        "pilot_session_ledger.csv", ledger_bytes
                    )
                    archive.writestr(
                        "pilot_shift_closeouts.csv", closeout_bytes
                    )
                temporary.replace(output)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise ClinicalValidationError(
                    f"Ekspor paket bukti pilot gagal: {exc}"
                ) from exc
            checksum = hashlib.sha256(output.read_bytes()).hexdigest()
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_LEDGER",
                    action="PILOT_SESSION_EVIDENCE_EXPORTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="PILOT_SESSION_LEDGER",
                    details={
                        "filename": output.name,
                        "checksum_sha256": checksum,
                        "ledger_entries": len(ledger_rows),
                        "closeouts": len(closeout_rows),
                        "ledger_head_hash": ledger_head_hash,
                        "contains_patient_identity": False,
                    },
                ),
            )
            session.commit()
            return PilotEvidenceExportResult(
                path=output,
                checksum_sha256=checksum,
                ledger_entries=len(ledger_rows),
                closeouts=len(closeout_rows),
                ledger_head_hash=ledger_head_hash,
            )

    def activate_advisory_pilot(
        self, actor_user_id: str, duration_hours: int = 24
    ) -> AdvisoryPilotStatus:
        raise ClinicalValidationError(
            "Aktivasi langsung dinonaktifkan; gunakan permintaan IT dan "
            "persetujuan petugas klinis yang berbeda"
        )

    def deactivate_advisory_pilot(
        self, actor_user_id: str
    ) -> AdvisoryPilotStatus:
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.PILOT_CONTROLLERS):
                raise ClinicalValidationPermissionError(
                    "Hanya IT Admin atau Super Admin yang dapat menonaktifkan "
                    "Advisory Pilot"
                )
            current, changed = self._advisory_status_in_session(session)
            if changed or not current.active or current.activation_id is None:
                if changed:
                    session.commit()
                raise ClinicalValidationError(
                    "Advisory Pilot tidak sedang aktif"
                )
            activation = session.get(
                AdvisoryPilotActivation, current.activation_id
            )
            now = utc_now()
            activation.status = "REVOKED"
            activation.revoked_by = actor_user_id
            activation.revoked_at = now
            activation.revocation_reason = "MANUAL_DEACTIVATION"
            self._finalize_shift_closeout(
                session,
                activation,
                "MANUAL_DEACTIVATION",
                actor_user_id,
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_PILOT_DEACTIVATED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_PILOT_ACTIVATION",
                    entity_id=activation.id,
                    details={"reason": "MANUAL_DEACTIVATION"},
                ),
            )
            session.commit()
            return AdvisoryPilotStatus(
                active=False,
                gate_ready=current.gate_ready,
                activation_id=activation.id,
                campaign_id=current.campaign_id,
                activated_at=activation.activated_at,
                expires_at=activation.expires_at,
                clinical_owner_id=activation.clinical_owner_id,
                shift_started_at=activation.shift_started_at,
                shift_expires_at=activation.shift_expires_at,
                emergency_stop=False,
                reason="MANUAL_DEACTIVATION",
                blockers=("Advisory Pilot dinonaktifkan secara manual",),
            )

    def trigger_advisory_emergency_stop(
        self, actor_user_id: str, reason: str
    ) -> AdvisoryPilotStatus:
        normalized_reason = " ".join(reason.strip().split())
        if not 10 <= len(normalized_reason) <= 300:
            raise ClinicalValidationError(
                "Alasan emergency stop wajib 10-300 karakter"
            )
        with self.database.session() as session:
            self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            control = self._safety_control(session)
            if control.emergency_stop:
                raise ClinicalValidationError(
                    "Emergency stop Advisory Pilot sudah aktif"
                )
            current, changed = self._advisory_status_in_session(session)
            activation = (
                session.get(
                    AdvisoryPilotActivation, current.activation_id
                )
                if current.active and current.activation_id
                else None
            )
            now = utc_now()
            if activation is not None:
                activation.status = "REVOKED"
                activation.revoked_by = actor_user_id
                activation.revoked_at = now
                activation.revocation_reason = "EMERGENCY_STOP"
                self._finalize_shift_closeout(
                    session,
                    activation,
                    "EMERGENCY_STOP",
                    actor_user_id,
                    notes=normalized_reason,
                )
            pending_requests = session.scalars(
                select(AdvisoryPilotAuthorizationRequest).where(
                    AdvisoryPilotAuthorizationRequest.status.in_(
                        (
                            "PENDING_CLINICAL",
                            "PENDING_OUTGOING",
                            "PENDING_TECHNICAL",
                        )
                    )
                )
            ).all()
            for pending in pending_requests:
                pending.status = "CANCELLED"
                pending.cancelled_at = now
                pending.cancellation_reason = "EMERGENCY_STOP"
            control.emergency_stop = True
            control.stop_reason = normalized_reason
            control.stopped_by = actor_user_id
            control.stopped_at = now
            control.restored_by = None
            control.restored_at = None
            control.updated_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_EMERGENCY_STOP_TRIGGERED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_PILOT_SAFETY_CONTROL",
                    entity_id=control.id,
                    details={
                        "reason": normalized_reason,
                        "revoked_activation_id": (
                            activation.id if activation else None
                        ),
                        "prior_status_change": changed,
                        "cancelled_pending_requests": len(pending_requests),
                    },
                ),
            )
            session.commit()
            return AdvisoryPilotStatus(
                active=False,
                gate_ready=current.gate_ready,
                activation_id=(activation.id if activation else None),
                campaign_id=current.campaign_id,
                activated_at=current.activated_at,
                expires_at=current.expires_at,
                clinical_owner_id=current.clinical_owner_id,
                shift_started_at=current.shift_started_at,
                shift_expires_at=current.shift_expires_at,
                emergency_stop=True,
                reason="EMERGENCY_STOP",
                blockers=(f"Emergency stop aktif: {normalized_reason}",),
            )

    def reset_advisory_emergency_stop(
        self, actor_user_id: str
    ) -> AdvisoryPilotStatus:
        with self.database.session() as session:
            roles = self._require_roles(
                session, actor_user_id, self.AUTHORIZED_ROLES
            )
            if not roles.intersection(self.PILOT_CONTROLLERS):
                raise ClinicalValidationPermissionError(
                    "Hanya IT Admin atau Super Admin yang dapat membuka "
                    "emergency stop"
                )
            control = self._safety_control(session)
            if not control.emergency_stop:
                raise ClinicalValidationError(
                    "Emergency stop Advisory Pilot tidak sedang aktif"
                )
            now = utc_now()
            previous_reason = control.stop_reason
            control.emergency_stop = False
            control.restored_by = actor_user_id
            control.restored_at = now
            control.updated_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_CONTROL",
                    action="ADVISORY_EMERGENCY_STOP_RESET",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="ADVISORY_PILOT_SAFETY_CONTROL",
                    entity_id=control.id,
                    details={
                        "previous_reason": previous_reason,
                        "requires_reactivation": True,
                    },
                ),
            )
            status, _ = self._advisory_status_in_session(session)
            session.commit()
            return status

    def pilot_monitoring(
        self, actor_user_id: str, period_days: int = 30
    ) -> PilotMonitoringSummary:
        if period_days not in {7, 30, 90, 365}:
            raise ClinicalValidationError("Periode monitoring harus 7, 30, 90, atau 365 hari")
        cutoff = utc_now() - timedelta(days=period_days)
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            prescriptions = session.scalars(
                select(ProcessingQueue).where(
                    ProcessingQueue.is_mock.is_(False),
                    ProcessingQueue.detected_at >= cutoff,
                )
            ).all()
            queue_ids = [row.id for row in prescriptions]
            alerts = (
                session.scalars(
                    select(AlertEvent).where(AlertEvent.queue_item_id.in_(queue_ids))
                ).all()
                if queue_ids
                else []
            )
            interventions = (
                session.scalars(
                    select(PharmacistIntervention).where(
                        PharmacistIntervention.queue_item_id.in_(queue_ids)
                    )
                ).all()
                if queue_ids
                else []
            )

        acknowledged = [row for row in alerts if row.acknowledged_at is not None]
        acknowledgement_minutes = [
            max(0.0, (row.acknowledged_at - row.created_at).total_seconds() / 60)
            for row in acknowledged
        ]
        completed = [row for row in interventions if row.status == "COMPLETED"]
        assessable_results = {"ACCEPTED_FULL", "ACCEPTED_PARTIAL", "NOT_ACCEPTED"}
        accepted_results = {"ACCEPTED_FULL", "ACCEPTED_PARTIAL"}
        assessable = [
            row for row in completed if row.communication_result in assessable_results
        ]
        accepted = [
            row for row in assessable if row.communication_result in accepted_results
        ]
        prescription_count = len(prescriptions)
        alert_count = len(alerts)
        return PilotMonitoringSummary(
            period_days=period_days,
            prescriptions_total=prescription_count,
            critical_prescriptions=sum(
                row.risk_status == "CRITICAL" for row in prescriptions
            ),
            high_risk_prescriptions=sum(
                row.risk_status == "HIGH_RISK" for row in prescriptions
            ),
            alerts_total=alert_count,
            alerts_shown=sum(row.shown_at is not None for row in alerts),
            alerts_acknowledged=len(acknowledged),
            critical_unacknowledged=sum(
                row.level == "CRITICAL" and row.acknowledged_at is None
                for row in alerts
            ),
            alert_rate_per_100=(
                round(alert_count * 100 / prescription_count, 1)
                if prescription_count
                else 0.0
            ),
            acknowledgement_rate=(
                round(len(acknowledged) * 100 / alert_count, 1)
                if alert_count
                else 0.0
            ),
            median_acknowledgement_minutes=(
                round(float(median(acknowledgement_minutes)), 1)
                if acknowledgement_minutes
                else None
            ),
            interventions_total=len(interventions),
            interventions_completed=len(completed),
            accepted_interventions=len(accepted),
            assessable_interventions=len(assessable),
            acceptance_rate=(
                round(len(accepted) * 100 / len(assessable), 1)
                if assessable
                else None
            ),
        )

    def export_pilot_monitoring(
        self,
        target: Path | str,
        actor_user_id: str,
        period_days: int = 30,
    ) -> Path:
        output = Path(target)
        summary = self.pilot_monitoring(actor_user_id, period_days)
        output.parent.mkdir(parents=True, exist_ok=True)
        rows = (
            ("periode_hari", summary.period_days),
            ("resep_non_mock", summary.prescriptions_total),
            ("resep_critical", summary.critical_prescriptions),
            ("resep_high_risk", summary.high_risk_prescriptions),
            ("alert_total", summary.alerts_total),
            ("alert_ditampilkan", summary.alerts_shown),
            ("alert_diakui", summary.alerts_acknowledged),
            ("critical_belum_diakui", summary.critical_unacknowledged),
            ("alert_per_100_resep", summary.alert_rate_per_100),
            ("acknowledgement_rate_persen", summary.acknowledgement_rate),
            ("median_ack_menit", summary.median_acknowledgement_minutes or ""),
            ("intervensi_total", summary.interventions_total),
            ("intervensi_selesai", summary.interventions_completed),
            ("intervensi_dapat_dinilai", summary.assessable_interventions),
            ("rekomendasi_diterima", summary.accepted_interventions),
            ("acceptance_rate_persen", summary.acceptance_rate or ""),
        )
        try:
            with output.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("METRIK_AGREGAT", "NILAI"))
                writer.writerows(rows)
        except OSError as exc:
            raise ClinicalValidationError(f"Ekspor monitoring gagal: {exc}") from exc
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.AUTHORIZED_ROLES)
            self.audit.append(
                session,
                AuditEvent(
                    category="PILOT_MONITORING",
                    action="PILOT_AGGREGATE_EXPORTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="PILOT_MONITORING",
                    details={
                        "filename": output.name,
                        "period_days": period_days,
                        "checksum": checksum,
                        "contains_patient_identity": False,
                    },
                ),
            )
            session.commit()
        return output

    @classmethod
    def _parse_record(cls, values: dict[str, Any]) -> dict[str, Any]:
        case_code = normalize_text(values["case_id"])
        drugs = normalize_text(values["daftar_obat"])
        expected_severity = normalize_text(values["expected_highest_severity"]).upper()
        if not case_code or not drugs:
            raise ClinicalValidationError("case_id dan daftar_obat wajib diisi")
        if expected_severity not in _SEVERITIES:
            raise ClinicalValidationError("expected_highest_severity tidak valid")
        expected_fields = ("expected_duplicate_therapy", "expected_polypharmacy", "expected_high_alert", "expected_lasa", "expected_unmapped", "expected_alert", "checks_compound", "checks_revision")
        expected = {name: cls._bool(values[name], name, required=True) for name in expected_fields}
        actual_severity = normalize_text(values["actual_highest_severity"]).upper()
        if actual_severity and actual_severity not in _SEVERITIES:
            raise ClinicalValidationError("actual_highest_severity tidak valid")
        actual_fields = ("actual_duplicate_therapy", "actual_polypharmacy", "actual_high_alert", "actual_lasa", "actual_unmapped", "actual_alert", "compound_pass", "revision_pass")
        actual = {name: cls._bool(values[name], name, required=False) for name in actual_fields}
        reviewed = bool(actual_severity and normalize_text(values["reviewer"]) and normalize_text(values["review_date"]))
        actual_core = all(actual[name] is not None for name in actual_fields[:6])
        calculated_match: bool | None = None
        duplicate_count = cls._integer(values["duplicate_output_count"], "duplicate_output_count")
        if reviewed and actual_core:
            calculated_match = expected_severity == actual_severity
            for expected_name, actual_name in zip(expected_fields[:6], actual_fields[:6], strict=True):
                calculated_match = calculated_match and expected[expected_name] == actual[actual_name]
            calculated_match = calculated_match and duplicate_count == 0
            if expected["checks_compound"]:
                calculated_match = calculated_match and actual["compound_pass"] is True
            if expected["checks_revision"]:
                calculated_match = calculated_match and actual["revision_pass"] is True
        review_date = None
        if normalize_text(values["review_date"]):
            try:
                review_date = date.fromisoformat(normalize_text(values["review_date"])[:10])
            except ValueError as exc:
                raise ClinicalValidationError("review_date harus YYYY-MM-DD") from exc
        return {
            "case_code": case_code, "drug_list": drugs,
            "clinical_context": normalize_text(values["context_klinis"]) or None,
            "expected_pairs": normalize_text(values["expected_pairs"]) or None,
            "expected_highest_severity": expected_severity,
            **expected,
            "actual_result": normalize_text(values["actual_result"]) or None,
            "actual_highest_severity": actual_severity or None,
            "actual_overall_status": normalize_text(values["actual_overall_status"]).upper() or None,
            **actual,
            "duplicate_output_count": duplicate_count,
            "match": calculated_match,
            "review_status": "REVIEWED" if reviewed else "NOT_REVIEWED",
            "reviewer": normalize_text(values["reviewer"]) or None,
            "review_date": review_date,
            "notes": normalize_text(values["notes"]) or None,
        }

    @staticmethod
    def _bool(value: Any, name: str, *, required: bool) -> bool | None:
        text = normalize_text(value).upper()
        if not text and not required:
            return None
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ClinicalValidationError(f"{name} harus YA/TIDAK")

    @staticmethod
    def _integer(value: Any, name: str) -> int:
        if value in (None, ""):
            return 0
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ClinicalValidationError(f"{name} harus bilangan bulat") from exc
        if parsed < 0:
            raise ClinicalValidationError(f"{name} tidak boleh negatif")
        return parsed

    @staticmethod
    def _require_roles(session, actor_user_id: str, allowed: frozenset[str]) -> frozenset[str]:
        user = session.scalar(select(AppUser).options(selectinload(AppUser.roles).selectinload(UserRole.role)).where(AppUser.id == actor_user_id))
        if user is None or not user.is_active or user.normalized_username == 'mode.farmasi':
            raise ClinicalValidationPermissionError("Pengguna aktif tidak ditemukan")
        roles = frozenset(item.role.code for item in user.roles)
        if not roles.intersection(allowed):
            raise ClinicalValidationPermissionError("Role tidak berwenang mengelola validasi/UAT")
        return roles
