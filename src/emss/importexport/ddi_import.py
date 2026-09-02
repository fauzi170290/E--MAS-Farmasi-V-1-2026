from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import (
    ActiveIngredient,
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
    ImportStagingRow,
)
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import (
    DdiRule,
    KnowledgeBaseTransition,
    KnowledgeBaseVersion,
)
from emss.database.models import AppUser, UserRole
from emss.domain.knowledge import (
    INTERACTION_STATUSES,
    canonical_pair,
    normalize_severity,
    validate_status_severity,
)
from emss.importexport.drug_import import normalize_name, normalize_text
from emss.importexport.tabular_reader import (
    CsvTableReader,
    TabularReadError,
    TabularSheet,
    XlsxTableReader,
)
from emss.utils.time import utc_now


class DdiImportError(ValueError):
    pass


class DdiImportPermissionError(DdiImportError):
    pass


class DdiImportStateError(DdiImportError):
    pass


@dataclass(frozen=True)
class DdiImportIssue:
    sheet: str
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class DdiImportPreview:
    batch_id: str
    filename: str
    version_code: str | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    proposed_inserts: int
    proposed_updates: int
    proposed_unchanged: int
    issues: tuple[DdiImportIssue, ...]

    @property
    def commit_allowed(self) -> bool:
        return self.total_rows > 0 and self.invalid_rows == 0


@dataclass(frozen=True)
class DdiCommitResult:
    version_id: str
    version_code: str
    inserted: int
    updated: int
    unchanged: int
    backup_path: str


@dataclass
class _Candidate:
    sheet: str
    row: int
    raw: dict[str, Any]
    normalized: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)
    proposed_action: str = "INSERT"


@dataclass(frozen=True)
class _DrugCodeMapping:
    display_name: str
    normalized_display_name: str
    ingredient_names: tuple[str, ...]
    approved: bool


SOURCE_HEADERS = frozenset(
    {
        "pair_id",
        "pair_key",
        "active_ingredient_a",
        "active_ingredient_b",
        "pair_order_rule",
        "interaction_flag",
        "severity",
        "severity_code",
        "severity_rank",
        "clinical_explanation",
        "recommendation",
        "monitoring_parameters",
        "monitoring_basis",
        "clinical_content_basis",
        "clinical_review_required",
        "activation_status",
        "validation_status",
        "status_final_code",
        "frequency_episode",
        "source",
        "source_url",
        "access_date",
        "source_batch",
        "source_evidence_count",
        "duplicate_evidence_flag",
        "duplicate_resolution",
        "database_version",
        "build_date",
        "notes",
    }
)
TEMPLATE_HEADERS = frozenset(
    {
        "drug_a_code",
        "drug_a_name",
        "drug_b_code",
        "drug_b_name",
        "interaction_status",
        "severity_code",
        "severity_label",
        "clinical_effect",
        "mechanism",
        "recommendation",
        "monitoring",
        "population_risk",
        "source_name",
        "source_reference",
        "source_accessed_at",
        "validated_by",
        "validated_at",
        "knowledge_base_version",
        "status",
        "notes",
    }
)
WRITER_ROLES = frozenset({"SUPER_ADMIN", "KNOWLEDGE_ADMIN"})


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return normalize_text(value).upper() in {"1", "TRUE", "YES", "YA"}


def _nonnegative_int(value: Any, field_name: str, errors: list[str]) -> int:
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field_name} harus berupa bilangan bulat")
        return 0
    if parsed < 0:
        errors.append(f"{field_name} tidak boleh negatif")
        return 0
    return parsed


def _parse_date(value: Any, field_name: str, errors: list[str]) -> date | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        errors.append(f"{field_name} harus berformat YYYY-MM-DD")
        return None


def _parse_datetime(
    value: Any, field_name: str, errors: list[str]
) -> datetime | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field_name} harus berformat ISO 8601")
        return None


def _source_interaction_status(validation_status: str, interaction_flag: bool) -> str:
    if interaction_flag:
        return "INTERACTION_FOUND"
    upper = validation_status.upper()
    if upper.startswith("NO_INTERACTION"):
        return "ASSESSED_NO_INTERACTION"
    if upper == "NOT_ASSESSABLE":
        return "NOT_ASSESSABLE"
    if upper == "EXCLUDED":
        return "EXCLUDED"
    return ""


class DdiImportService:
    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit
        self.xlsx_reader = XlsxTableReader()
        self.csv_reader = CsvTableReader()

    def preview(
        self, path: Path | str, actor_user_id: str
    ) -> DdiImportPreview:
        source = Path(path)
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
        try:
            checksum = self._sha256(source)
            sheet = self._read_source(source)
            with self.database.session() as session:
                ingredients = {
                    item.normalized_name
                    for item in session.scalars(select(ActiveIngredient))
                }
                drug_code_mappings = self._drug_code_mappings(session)
                existing = self._existing_pairs(session)
            candidates = self._validate_sheet(
                sheet, ingredients, drug_code_mappings
            )
        except (OSError, TabularReadError, DdiImportError) as exc:
            raise DdiImportError(str(exc)) from exc

        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            versions = {
                row.normalized["knowledge_base_version"]
                for row in candidates
                if row.normalized and row.normalized.get("knowledge_base_version")
            }
            version_code = next(iter(versions)) if len(versions) == 1 else None
            if version_code:
                current_version = session.scalar(
                    select(KnowledgeBaseVersion).where(
                        KnowledgeBaseVersion.version_code == version_code
                    )
                )
                if current_version and current_version.status != "DRAFT":
                    for row in candidates:
                        row.errors.append(
                            f"Versi {version_code} berstatus "
                            f"{current_version.status}; hanya DRAFT dapat diubah"
                        )
            for row in candidates:
                if row.normalized:
                    key = (
                        row.normalized["knowledge_base_version"],
                        row.normalized["pair_key"],
                    )
                    row.proposed_action = (
                        "UPDATE" if key in existing else "INSERT"
                    )
            total = len(candidates)
            invalid = sum(bool(row.errors) for row in candidates)
            action_counts = {
                action: sum(
                    1
                    for row in candidates
                    if not row.errors and row.proposed_action == action
                )
                for action in ("INSERT", "UPDATE", "UNCHANGED")
            }
            batch = ImportBatch(
                import_type="DDI_RULES",
                source_filename=source.name,
                source_sha256=checksum,
                source_version=version_code,
                status="PREVIEWED",
                requested_by=actor_user_id,
                total_rows=total,
                valid_rows=total - invalid,
                invalid_rows=invalid,
                summary_json=json.dumps(
                    {"proposed_actions": action_counts}, sort_keys=True
                ),
                created_at=utc_now(),
            )
            session.add(batch)
            session.flush()
            for candidate in candidates:
                session.add(
                    ImportStagingRow(
                        batch_id=batch.id,
                        sheet_name=candidate.sheet,
                        source_row_number=candidate.row,
                        entity_type="DDI_RULE",
                        raw_json=json.dumps(
                            candidate.raw,
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ),
                        normalized_json=(
                            json.dumps(
                                candidate.normalized,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )
                            if candidate.normalized
                            else None
                        ),
                        validation_status=(
                            "INVALID" if candidate.errors else "VALID"
                        ),
                        errors_json=json.dumps(
                            candidate.errors, ensure_ascii=False
                        ),
                        proposed_action=candidate.proposed_action,
                    )
                )
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DDI_IMPORT_PREVIEWED",
                    outcome="SUCCESS" if invalid == 0 else "VALIDATION_FAILED",
                    actor_user_id=actor_user_id,
                    entity_type="IMPORT_BATCH",
                    entity_id=batch.id,
                    details={
                        "filename": source.name,
                        "sha256": checksum,
                        "version": version_code,
                        "rows": total,
                        "invalid": invalid,
                    },
                ),
            )
            session.commit()
            return self._preview_from_candidates(
                batch, candidates, action_counts
            )

    def commit(self, batch_id: str, actor_user_id: str) -> DdiCommitResult:
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            batch = session.get(ImportBatch, batch_id)
            if batch is None or batch.import_type != "DDI_RULES":
                raise DdiImportError("Batch impor DDI tidak ditemukan")
            if batch.status != "PREVIEWED":
                raise DdiImportStateError("Batch harus berstatus PREVIEWED")
            if batch.invalid_rows:
                raise DdiImportStateError("Batch invalid tidak boleh di-commit")
            duplicate = session.scalar(
                select(ImportBatch.id).where(
                    ImportBatch.import_type == "DDI_RULES",
                    ImportBatch.source_sha256 == batch.source_sha256,
                    ImportBatch.status == "COMMITTED",
                    ImportBatch.id != batch.id,
                )
            )
            if duplicate:
                raise DdiImportStateError(
                    "File DDI dengan checksum sama sudah pernah di-commit"
                )
            staged = session.scalars(
                select(ImportStagingRow)
                .where(ImportStagingRow.batch_id == batch.id)
                .order_by(ImportStagingRow.source_row_number)
            ).all()
            rows = [json.loads(item.normalized_json or "{}") for item in staged]
            version_codes = {
                row.get("knowledge_base_version") for row in rows if row
            }
            if len(version_codes) != 1:
                raise DdiImportStateError(
                    "Batch harus memiliki tepat satu versi knowledge base"
                )
            version_code = str(next(iter(version_codes)))

        backup_path = self._backup_before_import(batch_id)

        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            batch = session.get(ImportBatch, batch_id)
            if batch is None or batch.status != "PREVIEWED":
                raise DdiImportStateError("Status batch berubah sebelum commit")
            version = session.scalar(
                select(KnowledgeBaseVersion).where(
                    KnowledgeBaseVersion.version_code == version_code
                )
            )
            if version is None:
                version = KnowledgeBaseVersion(
                    version_code=version_code,
                    title=f"Knowledge Base {version_code}",
                    description=f"Diimpor dari {batch.source_filename}",
                    status="DRAFT",
                    source_checksum=batch.source_sha256,
                    created_by=actor_user_id,
                )
                session.add(version)
                session.flush()
                session.add(
                    KnowledgeBaseTransition(
                        knowledge_base_version_id=version.id,
                        from_status=None,
                        to_status="DRAFT",
                        action="IMPORT",
                        reason=f"Diimpor dari {batch.source_filename}",
                        actor_user_id=actor_user_id,
                    )
                )
            elif version.status != "DRAFT":
                raise DdiImportStateError(
                    "Hanya versi DRAFT yang dapat menerima impor"
                )

            ingredients = {
                item.normalized_name: item
                for item in session.scalars(select(ActiveIngredient))
            }
            existing = {
                rule.pair_key: rule
                for rule in session.scalars(
                    select(DdiRule).where(
                        DdiRule.knowledge_base_version_id == version.id
                    )
                )
            }
            inserted = updated = unchanged = 0
            for raw in rows:
                low_name = raw["ingredient_low"]
                high_name = raw["ingredient_high"]
                low_id, high_id = sorted(
                    (ingredients[low_name].id, ingredients[high_name].id)
                )
                rule = existing.get(raw["pair_key"])
                payload = self._rule_payload(
                    raw, low_id, high_id, actor_user_id
                )
                if rule is None:
                    session.add(
                        DdiRule(
                            knowledge_base_version_id=version.id,
                            created_by=actor_user_id,
                            **payload,
                        )
                    )
                    inserted += 1
                elif self._same_rule(rule, payload):
                    unchanged += 1
                else:
                    for field_name, value in payload.items():
                        setattr(rule, field_name, value)
                    rule.record_status = "DRAFT"
                    rule.is_enabled = False
                    updated += 1

            batch.status = "COMMITTED"
            batch.inserted_rows = inserted
            batch.updated_rows = updated
            batch.unchanged_rows = unchanged
            batch.completed_at = utc_now()
            batch.summary_json = json.dumps(
                {
                    "version_id": version.id,
                    "version_code": version.version_code,
                    "backup_path": backup_path,
                    "inserted": inserted,
                    "updated": updated,
                    "unchanged": unchanged,
                },
                sort_keys=True,
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DDI_IMPORT_COMMITTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="KNOWLEDGE_BASE_VERSION",
                    entity_id=version.id,
                    details={
                        "batch_id": batch.id,
                        "version": version.version_code,
                        "inserted": inserted,
                        "updated": updated,
                        "unchanged": unchanged,
                        "backup": Path(backup_path).name,
                    },
                ),
            )
            session.commit()
            return DdiCommitResult(
                version_id=version.id,
                version_code=version.version_code,
                inserted=inserted,
                updated=updated,
                unchanged=unchanged,
                backup_path=backup_path,
            )

    def get_preview(self, batch_id: str) -> DdiImportPreview:
        with self.database.session() as session:
            batch = session.get(ImportBatch, batch_id)
            if batch is None or batch.import_type != "DDI_RULES":
                raise DdiImportError("Batch impor DDI tidak ditemukan")
            staged = session.scalars(
                select(ImportStagingRow)
                .where(ImportStagingRow.batch_id == batch.id)
                .order_by(ImportStagingRow.source_row_number)
            ).all()
            issues = tuple(
                DdiImportIssue(
                    sheet=row.sheet_name,
                    row=row.source_row_number,
                    field="row",
                    message=message,
                )
                for row in staged
                for message in json.loads(row.errors_json)
            )
            summary = json.loads(batch.summary_json or "{}")
            actions = summary.get("proposed_actions", {})
            return DdiImportPreview(
                batch_id=batch.id,
                filename=batch.source_filename,
                version_code=batch.source_version,
                total_rows=batch.total_rows,
                valid_rows=batch.valid_rows,
                invalid_rows=batch.invalid_rows,
                proposed_inserts=int(actions.get("INSERT", 0)),
                proposed_updates=int(actions.get("UPDATE", 0)),
                proposed_unchanged=int(actions.get("UNCHANGED", 0)),
                issues=issues,
            )

    def recent_batches(self, limit: int = 20) -> list[ImportBatch]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ImportBatch)
                    .where(ImportBatch.import_type == "DDI_RULES")
                    .order_by(ImportBatch.created_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            )

    def _read_source(self, source: Path) -> TabularSheet:
        suffix = source.suffix.lower()
        if suffix == ".xlsx":
            sheets = self.xlsx_reader.read(source)
            if "DDI_RULE_MASTER" in sheets:
                return sheets["DDI_RULE_MASTER"]
            if "DDI_IMPORT" in sheets:
                return sheets["DDI_IMPORT"]
            raise DdiImportError(
                "Workbook harus memiliki sheet DDI_RULE_MASTER atau DDI_IMPORT"
            )
        if suffix == ".csv":
            return self.csv_reader.read(source)
        raise DdiImportError("Format impor DDI harus .xlsx atau .csv")

    def _validate_sheet(
        self,
        sheet: TabularSheet,
        ingredient_names: set[str],
        drug_code_mappings: dict[str, _DrugCodeMapping] | None = None,
    ) -> list[_Candidate]:
        if sheet.formula_cells:
            raise DdiImportError(
                f"Formula tidak diizinkan pada sheet {sheet.name}: "
                + ", ".join(sheet.formula_cells[:10])
            )
        header_index = self._find_header(sheet)
        headers = tuple(
            normalize_text(value).lower() for value in sheet.rows[header_index]
        )
        header_set = frozenset(headers)
        if header_set == SOURCE_HEADERS:
            source_format = "SOURCE"
        elif header_set == TEMPLATE_HEADERS:
            source_format = "TEMPLATE"
        else:
            missing_source = sorted(SOURCE_HEADERS - header_set)
            missing_template = sorted(TEMPLATE_HEADERS - header_set)
            best_missing = (
                missing_source
                if len(missing_source) <= len(missing_template)
                else missing_template
            )
            raise DdiImportError(
                "Header DDI tidak sesuai. Kolom hilang: "
                + ", ".join(best_missing[:12])
            )
        seen: dict[tuple[str, str], int] = {}
        candidates: list[_Candidate] = []
        for offset, values in enumerate(sheet.rows[header_index + 1 :], start=1):
            if not any(value not in (None, "") for value in values):
                continue
            row_number = (
                sheet.row_numbers[header_index + offset]
                if sheet.row_numbers
                else header_index + offset + 1
            )
            raw = {
                header: values[index] if index < len(values) else None
                for index, header in enumerate(headers)
            }
            candidate = (
                self._normalize_source(sheet.name, row_number, raw)
                if source_format == "SOURCE"
                else self._normalize_template(
                    sheet.name,
                    row_number,
                    raw,
                    drug_code_mappings or {},
                )
            )
            if candidate.normalized:
                low = candidate.normalized["ingredient_low"]
                high = candidate.normalized["ingredient_high"]
                missing = [
                    name for name in (low, high) if name not in ingredient_names
                ]
                if missing:
                    candidate.errors.append(
                        "Zat aktif belum ada di master obat: " + ", ".join(missing)
                    )
                key = (
                    candidate.normalized["knowledge_base_version"],
                    candidate.normalized["pair_key"],
                )
                if key in seen:
                    candidate.errors.append(
                        f"Pasangan duplikat/terbalik dengan baris {seen[key]}"
                    )
                else:
                    seen[key] = row_number
            candidates.append(candidate)
        if not candidates:
            raise DdiImportError("Tidak ada baris data DDI")
        versions = {
            row.normalized["knowledge_base_version"]
            for row in candidates
            if row.normalized and row.normalized.get("knowledge_base_version")
        }
        if len(versions) > 1:
            for candidate in candidates:
                candidate.errors.append(
                    "Satu batch hanya boleh memuat satu knowledge_base_version"
                )
        return candidates

    def _normalize_source(
        self, sheet: str, row: int, raw: dict[str, Any]
    ) -> _Candidate:
        errors: list[str] = []
        try:
            low, high, pair_key = canonical_pair(
                raw.get("active_ingredient_a"), raw.get("active_ingredient_b")
            )
        except ValueError as exc:
            errors.append(str(exc))
            low = high = pair_key = ""
        source_pair_key = normalize_name(raw.get("pair_key"))
        if pair_key and source_pair_key != pair_key:
            errors.append("pair_key tidak sesuai urutan kanonik")
        validation_status = normalize_text(raw.get("validation_status")).upper()
        interaction_status = _source_interaction_status(
            validation_status, _bool_value(raw.get("interaction_flag"))
        )
        if not interaction_status:
            errors.append("validation_status/interaction_flag tidak dikenali")
        try:
            severity_code, severity_rank, app_severity = normalize_severity(
                raw.get("severity_code")
            )
            validate_status_severity(interaction_status, severity_code)
        except ValueError as exc:
            errors.append(str(exc))
            severity_code, severity_rank, app_severity = "NONE", 0, None
        source_rank = _nonnegative_int(
            raw.get("severity_rank"), "severity_rank", errors
        )
        if source_rank != severity_rank:
            errors.append("severity_rank tidak sesuai severity_code")
        version_code = normalize_text(raw.get("database_version"))
        source_name = normalize_text(raw.get("source"))
        if not version_code:
            errors.append("database_version wajib diisi")
        if not source_name:
            errors.append("source wajib diisi")
        accessed = _parse_date(raw.get("access_date"), "access_date", errors)
        if accessed is None:
            errors.append("access_date wajib diisi")
        review_required = _bool_value(raw.get("clinical_review_required"))
        activation = normalize_text(raw.get("activation_status")).upper()
        if review_required and activation != "HOLD_CLINICAL_REVIEW_REQUIRED":
            errors.append(
                "Rule clinical_review_required harus berstatus HOLD"
            )
        normalized = {
            "external_pair_id": normalize_text(raw.get("pair_id")) or None,
            "ingredient_low": low,
            "ingredient_high": high,
            "pair_key": pair_key,
            "interaction_status": interaction_status,
            "severity_code": severity_code,
            "severity_label": normalize_text(raw.get("severity")) or None,
            "severity_rank": severity_rank,
            "app_severity": app_severity,
            "clinical_effect": normalize_text(raw.get("clinical_explanation")) or None,
            "mechanism": None,
            "recommendation": normalize_text(raw.get("recommendation")) or None,
            "monitoring": normalize_text(raw.get("monitoring_parameters")) or None,
            "population_risk": None,
            "source_name": source_name,
            "source_reference": normalize_text(raw.get("source_url")) or None,
            "source_accessed_at": accessed.isoformat() if accessed else None,
            "source_batch": normalize_text(raw.get("source_batch")) or None,
            "source_evidence_count": _nonnegative_int(
                raw.get("source_evidence_count"),
                "source_evidence_count",
                errors,
            ),
            "source_validation_status": validation_status or None,
            "source_final_code": normalize_text(raw.get("status_final_code")) or None,
            "activation_status": activation or "DRAFT",
            "clinical_review_required": review_required,
            "clinical_review_resolved": False,
            "validated_by_name": None,
            "validated_at": None,
            "notes": normalize_text(raw.get("notes")) or None,
            "knowledge_base_version": version_code,
        }
        return _Candidate(sheet, row, raw, normalized, errors)

    def _normalize_template(
        self,
        sheet: str,
        row: int,
        raw: dict[str, Any],
        drug_code_mappings: dict[str, _DrugCodeMapping],
    ) -> _Candidate:
        errors: list[str] = []
        ingredient_a = self._resolve_template_drug(
            "A",
            raw.get("drug_a_code"),
            raw.get("drug_a_name"),
            drug_code_mappings,
            errors,
        )
        ingredient_b = self._resolve_template_drug(
            "B",
            raw.get("drug_b_code"),
            raw.get("drug_b_name"),
            drug_code_mappings,
            errors,
        )
        try:
            low, high, pair_key = canonical_pair(ingredient_a, ingredient_b)
        except ValueError as exc:
            errors.append(str(exc))
            low = high = pair_key = ""
        interaction_status = normalize_text(raw.get("interaction_status")).upper()
        try:
            severity_code, severity_rank, app_severity = normalize_severity(
                raw.get("severity_code")
            )
            validate_status_severity(interaction_status, severity_code)
        except ValueError as exc:
            errors.append(str(exc))
            severity_code, severity_rank, app_severity = "NONE", 0, None
        version_code = normalize_text(raw.get("knowledge_base_version"))
        source_name = normalize_text(raw.get("source_name"))
        if not version_code:
            errors.append("knowledge_base_version wajib diisi")
        if not source_name:
            errors.append("source_name wajib diisi")
        status = normalize_text(raw.get("status")).upper()
        if status != "DRAFT":
            errors.append("Status impor template harus DRAFT")
        accessed = _parse_date(
            raw.get("source_accessed_at"), "source_accessed_at", errors
        )
        if accessed is None:
            errors.append("source_accessed_at wajib diisi")
        validated_at = _parse_datetime(
            raw.get("validated_at"), "validated_at", errors
        )
        clinical_required = (
            interaction_status == "INTERACTION_FOUND"
            and severity_code in {"SIGNIFICANT", "SERIOUS", "CONTRAINDICATED"}
        )
        normalized = {
            "external_pair_id": None,
            "ingredient_low": low,
            "ingredient_high": high,
            "pair_key": pair_key,
            "interaction_status": interaction_status,
            "severity_code": severity_code,
            "severity_label": normalize_text(raw.get("severity_label")) or None,
            "severity_rank": severity_rank,
            "app_severity": app_severity,
            "clinical_effect": normalize_text(raw.get("clinical_effect")) or None,
            "mechanism": normalize_text(raw.get("mechanism")) or None,
            "recommendation": normalize_text(raw.get("recommendation")) or None,
            "monitoring": normalize_text(raw.get("monitoring")) or None,
            "population_risk": normalize_text(raw.get("population_risk")) or None,
            "source_name": source_name,
            "source_reference": normalize_text(raw.get("source_reference")) or None,
            "source_accessed_at": accessed.isoformat() if accessed else None,
            "source_batch": None,
            "source_evidence_count": 1,
            "source_validation_status": None,
            "source_final_code": None,
            "activation_status": (
                "HOLD_CLINICAL_REVIEW_REQUIRED"
                if clinical_required
                else "DRAFT"
            ),
            "clinical_review_required": clinical_required,
            "clinical_review_resolved": False,
            "validated_by_name": normalize_text(raw.get("validated_by")) or None,
            "validated_at": validated_at.isoformat() if validated_at else None,
            "notes": normalize_text(raw.get("notes")) or None,
            "knowledge_base_version": version_code,
            "drug_a_code": normalize_text(raw.get("drug_a_code")) or None,
            "drug_b_code": normalize_text(raw.get("drug_b_code")) or None,
        }
        return _Candidate(sheet, row, raw, normalized, errors)

    @staticmethod
    def _resolve_template_drug(
        side: str,
        code_value: Any,
        name_value: Any,
        mappings: dict[str, _DrugCodeMapping],
        errors: list[str],
    ) -> str:
        code = normalize_text(code_value)
        name = normalize_name(name_value)
        if not code:
            return name

        mapping = mappings.get(code)
        if mapping is None:
            errors.append(f"Kode obat Khanza {side} tidak ditemukan: {code}")
            return name
        if not mapping.approved:
            errors.append(
                f"Mapping kode obat Khanza {side} belum disetujui: {code}"
            )
            return name
        if len(mapping.ingredient_names) != 1:
            errors.append(
                f"Kode obat Khanza {side} harus memiliki tepat satu zat aktif: "
                f"{code}"
            )
            return name

        ingredient_name = mapping.ingredient_names[0]
        if name and name not in {
            mapping.normalized_display_name,
            ingredient_name,
        }:
            errors.append(
                f"Nama obat Khanza {side} tidak sesuai kode {code}: "
                f"seharusnya {mapping.display_name}"
            )
        return ingredient_name

    @staticmethod
    def _find_header(sheet: TabularSheet) -> int:
        for index, row in enumerate(sheet.rows[:10]):
            values = {normalize_text(value).lower() for value in row if value}
            if (
                {"pair_key", "active_ingredient_a", "active_ingredient_b"} <= values
                or {"drug_a_name", "drug_b_name", "interaction_status"} <= values
            ):
                return index
        raise DdiImportError(f"Header DDI tidak ditemukan pada sheet {sheet.name}")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _backup_before_import(self, batch_id: str) -> str:
        source = self.database.settings.database_path.resolve()
        target_dir = self.database.settings.backup_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        if self.database.settings.data_dir.resolve() not in target_dir.parents:
            raise DdiImportError("Lokasi backup berada di luar data directory")
        target = target_dir / (
            f"pre-ddi-import-{utc_now():%Y%m%d-%H%M%S}-{batch_id[:8]}.db"
        )
        with sqlite3.connect(source) as source_db:
            if source_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise DdiImportError("Database aktif gagal integrity check")
            with sqlite3.connect(target) as target_db:
                source_db.backup(target_db)
                if target_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DdiImportError("Backup gagal integrity check")
        return str(target)

    @staticmethod
    def _existing_pairs(session) -> set[tuple[str, str]]:
        return {
            (version_code, pair_key)
            for version_code, pair_key in session.execute(
                select(KnowledgeBaseVersion.version_code, DdiRule.pair_key).join(
                    DdiRule,
                    DdiRule.knowledge_base_version_id == KnowledgeBaseVersion.id,
                )
            )
        }

    @staticmethod
    def _drug_code_mappings(session) -> dict[str, _DrugCodeMapping]:
        drugs = session.scalars(
            select(DrugMaster).options(
                selectinload(DrugMaster.components).selectinload(
                    DrugComponentMapping.ingredient
                )
            )
        ).all()
        return {
            drug.khanza_code: _DrugCodeMapping(
                display_name=drug.display_name,
                normalized_display_name=normalize_name(drug.display_name),
                ingredient_names=tuple(
                    sorted(
                        component.ingredient.normalized_name
                        for component in drug.components
                        if component.is_active and component.ingredient.is_active
                    )
                ),
                approved=(
                    drug.is_active
                    and drug.review_status == "APPROVED"
                    and bool(drug.components)
                    and all(
                        component.is_active
                        and component.review_status == "APPROVED"
                        for component in drug.components
                    )
                ),
            )
            for drug in drugs
        }

    @staticmethod
    def _rule_payload(
        raw: dict[str, Any],
        low_id: str,
        high_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        return {
            "external_pair_id": raw.get("external_pair_id"),
            "ingredient_low_id": low_id,
            "ingredient_high_id": high_id,
            "pair_key": raw["pair_key"],
            "interaction_status": raw["interaction_status"],
            "severity_code": raw["severity_code"],
            "severity_label": raw.get("severity_label"),
            "severity_rank": int(raw["severity_rank"]),
            "app_severity": raw.get("app_severity"),
            "clinical_effect": raw.get("clinical_effect"),
            "mechanism": raw.get("mechanism"),
            "recommendation": raw.get("recommendation"),
            "monitoring": raw.get("monitoring"),
            "population_risk": raw.get("population_risk"),
            "source_name": raw["source_name"],
            "source_reference": raw.get("source_reference"),
            "source_accessed_at": (
                date.fromisoformat(raw["source_accessed_at"])
                if raw.get("source_accessed_at")
                else None
            ),
            "source_batch": raw.get("source_batch"),
            "source_evidence_count": int(raw.get("source_evidence_count", 0)),
            "source_validation_status": raw.get("source_validation_status"),
            "source_final_code": raw.get("source_final_code"),
            "activation_status": raw.get("activation_status") or "DRAFT",
            "clinical_review_required": bool(
                raw.get("clinical_review_required")
            ),
            "clinical_review_resolved": bool(
                raw.get("clinical_review_resolved")
            ),
            "record_status": "DRAFT",
            "is_enabled": False,
            "validated_by_name": raw.get("validated_by_name"),
            "validated_at": (
                datetime.fromisoformat(raw["validated_at"])
                if raw.get("validated_at")
                else None
            ),
            "notes": raw.get("notes"),
            "updated_by": actor_user_id,
        }

    @staticmethod
    def _same_rule(rule: DdiRule, payload: dict[str, Any]) -> bool:
        return all(getattr(rule, key) == value for key, value in payload.items())

    @staticmethod
    def _preview_from_candidates(
        batch: ImportBatch,
        candidates: list[_Candidate],
        actions: dict[str, int],
    ) -> DdiImportPreview:
        return DdiImportPreview(
            batch_id=batch.id,
            filename=batch.source_filename,
            version_code=batch.source_version,
            total_rows=batch.total_rows,
            valid_rows=batch.valid_rows,
            invalid_rows=batch.invalid_rows,
            proposed_inserts=actions["INSERT"],
            proposed_updates=actions["UPDATE"],
            proposed_unchanged=actions["UNCHANGED"],
            issues=tuple(
                DdiImportIssue(
                    sheet=row.sheet,
                    row=row.row,
                    field="row",
                    message=message,
                )
                for row in candidates
                for message in row.errors
            ),
        )

    @staticmethod
    def _require_writer(session, actor_user_id: str) -> None:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id, AppUser.is_active.is_(True))
        )
        if user is None:
            raise DdiImportPermissionError("Pengguna aktif tidak ditemukan")
        if not {link.role.code for link in user.roles}.intersection(WRITER_ROLES):
            raise DdiImportPermissionError(
                "Role tidak berwenang mengimpor master DDI"
            )
