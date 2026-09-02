from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import (
    ActiveIngredient,
    DrugAlias,
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
    ImportStagingRow,
)
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole
from emss.importexport.tabular_reader import (
    CsvTableReader,
    TabularReadError,
    TabularSheet,
    XlsxTableReader,
)
from emss.utils.time import utc_now


class DrugImportError(ValueError):
    pass


class ImportPermissionError(DrugImportError):
    pass


class ImportStateError(DrugImportError):
    pass


@dataclass(frozen=True)
class ImportIssue:
    sheet: str
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class ImportPreview:
    batch_id: str
    filename: str
    source_version: str | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    proposed_inserts: int
    proposed_updates: int
    proposed_unchanged: int
    issues: tuple[ImportIssue, ...]

    @property
    def commit_allowed(self) -> bool:
        return self.total_rows > 0 and self.invalid_rows == 0


@dataclass
class _Candidate:
    sheet: str
    row: int
    entity_type: str
    raw: dict[str, Any]
    normalized: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)
    proposed_action: str = "INSERT"


DRUG_HEADERS = frozenset(
    {
        "database_version",
        "khanza_code",
        "khanza_name_display",
        "khanza_name_normalized_source",
        "standard_active_ingredients",
        "component_count",
        "mapping_status",
        "mapping_method",
        "mapping_note",
        "rx_row_count",
        "episode_count",
        "name_variants",
    }
)
COMPONENT_HEADERS = frozenset(
    {
        "database_version",
        "khanza_code",
        "khanza_name_display",
        "component_order",
        "standard_active_ingredient",
        "mapping_status",
        "mapping_method",
    }
)
ALLOWED_MAPPING_STATUSES = frozenset(
    {"MAPPED", "PARTIALLY_MAPPED", "UNMAPPED"}
)
MANAGER_ROLES = frozenset(
    {"SUPER_ADMIN", "KNOWLEDGE_ADMIN", "CLINICAL_REVIEWER"}
)
_VARIANT_COUNT = re.compile(r"\s+\([0-9][0-9,.\s]*\)\s*$")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return " ".join(text.strip().split())


def normalize_name(value: Any) -> str:
    return normalize_text(value).casefold()


def normalize_code(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return normalize_text(value)


def parse_nonnegative_int(value: Any, field_name: str, errors: list[str]) -> int:
    if value in (None, ""):
        errors.append(f"{field_name} wajib diisi")
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field_name} harus berupa bilangan bulat")
        return 0
    if number < 0:
        errors.append(f"{field_name} tidak boleh negatif")
        return 0
    return number


def split_ingredients(value: Any) -> list[str]:
    return [
        normalize_name(item)
        for item in normalize_text(value).split(";")
        if normalize_name(item)
    ]


def split_aliases(display_name: str, variants: Any) -> list[str]:
    result: dict[str, str] = {normalize_name(display_name): display_name}
    for item in normalize_text(variants).split(";"):
        cleaned = _VARIANT_COUNT.sub("", item).strip()
        normalized = normalize_name(cleaned)
        if normalized:
            result.setdefault(normalized, cleaned)
    return list(result.values())


class DrugImportService:
    def __init__(
        self, database: DatabaseManager, audit: AuditService
    ) -> None:
        self.database = database
        self.audit = audit
        self.xlsx_reader = XlsxTableReader()
        self.csv_reader = CsvTableReader()

    def preview(self, path: Path | str, actor_user_id: str) -> ImportPreview:
        source = Path(path)
        with self.database.session() as session:
            self._require_manager(session, actor_user_id)

        try:
            checksum = self._sha256(source)
            sheets = self._read_source(source)
            with self.database.session() as session:
                existing_catalog = {
                    drug.khanza_code: {
                        "display_name": drug.display_name,
                        "ingredients": sorted(
                            mapping.ingredient.normalized_name
                            for mapping in drug.components
                        ),
                    }
                    for drug in session.scalars(
                        select(DrugMaster).options(
                            selectinload(DrugMaster.components).selectinload(
                                DrugComponentMapping.ingredient
                            )
                        )
                    ).all()
                }
            candidates = self._validate(sheets, existing_catalog)
        except (OSError, TabularReadError, DrugImportError) as exc:
            raise DrugImportError(str(exc)) from exc

        with self.database.session() as session:
            self._require_manager(session, actor_user_id)
            self._assign_actions(session, candidates)
            source_versions = {
                row.normalized["database_version"]
                for row in candidates
                if row.normalized and row.normalized.get("database_version")
            }
            source_version = (
                next(iter(source_versions)) if len(source_versions) == 1 else None
            )
            total = len(candidates)
            invalid = sum(bool(row.errors) for row in candidates)
            batch = ImportBatch(
                import_type="DRUG_CATALOG",
                source_filename=source.name,
                source_sha256=checksum,
                source_version=source_version,
                status="PREVIEWED",
                requested_by=actor_user_id,
                total_rows=total,
                valid_rows=total - invalid,
                invalid_rows=invalid,
                summary_json="{}",
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
                        entity_type=candidate.entity_type,
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
                            )
                            if candidate.normalized is not None
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
            action_counts = {
                action: sum(
                    1
                    for row in candidates
                    if not row.errors and row.proposed_action == action
                )
                for action in ("INSERT", "UPDATE", "UNCHANGED")
            }
            batch.summary_json = json.dumps(
                {"proposed_actions": action_counts},
                sort_keys=True,
            )
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DRUG_IMPORT_PREVIEWED",
                    outcome="SUCCESS" if invalid == 0 else "VALIDATION_FAILED",
                    actor_user_id=actor_user_id,
                    entity_type="IMPORT_BATCH",
                    entity_id=batch.id,
                    details={
                        "filename": source.name,
                        "sha256": checksum,
                        "total_rows": total,
                        "invalid_rows": invalid,
                    },
                ),
            )
            session.commit()

            issues = tuple(
                ImportIssue(
                    sheet=row.sheet,
                    row=row.row,
                    field="row",
                    message=message,
                )
                for row in candidates
                for message in row.errors
            )
            return ImportPreview(
                batch_id=batch.id,
                filename=source.name,
                source_version=source_version,
                total_rows=total,
                valid_rows=total - invalid,
                invalid_rows=invalid,
                proposed_inserts=action_counts["INSERT"],
                proposed_updates=action_counts["UPDATE"],
                proposed_unchanged=action_counts["UNCHANGED"],
                issues=issues,
            )

    def commit(self, batch_id: str, actor_user_id: str) -> dict[str, int]:
        with self.database.session() as session:
            self._require_manager(session, actor_user_id)
            batch = session.scalar(
                select(ImportBatch)
                .options(selectinload(ImportBatch.staging_rows))
                .where(ImportBatch.id == batch_id)
            )
            if batch is None:
                raise ImportStateError("Batch import tidak ditemukan")
            if batch.status != "PREVIEWED":
                raise ImportStateError(
                    f"Batch tidak dapat di-commit dari status {batch.status}"
                )
            if batch.invalid_rows:
                raise ImportStateError(
                    "Batch masih memiliki baris invalid dan tidak boleh di-commit"
                )
            duplicate = session.scalar(
                select(ImportBatch.id).where(
                    ImportBatch.source_sha256 == batch.source_sha256,
                    ImportBatch.status.in_(("COMMITTED", "APPROVED")),
                    ImportBatch.id != batch.id,
                )
            )
            if duplicate:
                raise ImportStateError(
                    "File yang sama sudah pernah di-commit"
                )

            normalized_rows = [
                (
                    row.entity_type,
                    json.loads(row.normalized_json or "{}"),
                )
                for row in batch.staging_rows
                if row.validation_status == "VALID"
            ]
            drug_rows = {
                data["khanza_code"]: data
                for entity, data in normalized_rows
                if entity == "DRUG"
            }
            component_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entity, data in normalized_rows:
                if entity == "COMPONENT":
                    component_rows[data["khanza_code"]].append(data)

            counts = {"inserted": 0, "updated": 0, "unchanged": 0}
            drugs: dict[str, DrugMaster] = {}
            for code, data in drug_rows.items():
                drug, action = self._upsert_drug(
                    session, data, batch.id
                )
                drugs[code] = drug
                counts[action] += 1
                self._upsert_aliases(session, drug, data["aliases"])

            for code in component_rows:
                if code not in drugs:
                    drug = session.scalar(
                        select(DrugMaster).where(DrugMaster.khanza_code == code)
                    )
                    if drug is None:
                        raise ImportStateError(
                            f"Master obat untuk kode {code} tidak ditemukan"
                        )
                    drugs[code] = drug

            for code, rows in component_rows.items():
                component_counts = self._replace_or_refresh_components(
                    session,
                    drugs[code],
                    rows,
                    batch.id,
                )
                for key, value in component_counts.items():
                    counts[key] += value

            for code, drug in drugs.items():
                if code in drug_rows and not component_rows.get(code):
                    if drug_rows[code]["component_count"] == 0:
                        for mapping in list(drug.components):
                            session.delete(mapping)
                        drug.review_status = "PENDING_REVIEW"

            batch.status = "COMMITTED"
            batch.inserted_rows = counts["inserted"]
            batch.updated_rows = counts["updated"]
            batch.unchanged_rows = counts["unchanged"]
            batch.completed_at = utc_now()
            batch.summary_json = json.dumps(counts, sort_keys=True)
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DRUG_IMPORT_COMMITTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="IMPORT_BATCH",
                    entity_id=batch.id,
                    details=counts,
                ),
            )
            session.commit()
            return counts

    def approve_batch(self, batch_id: str, reviewer_user_id: str) -> int:
        with self.database.session() as session:
            self._require_manager(session, reviewer_user_id)
            batch = session.get(ImportBatch, batch_id)
            if batch is None or batch.status != "COMMITTED":
                raise ImportStateError(
                    "Hanya batch COMMITTED yang dapat disetujui"
                )
            drugs = session.scalars(
                select(DrugMaster)
                .options(selectinload(DrugMaster.components))
                .where(DrugMaster.last_import_batch_id == batch_id)
            ).all()
            reviewed_at = utc_now()
            for drug in drugs:
                drug.review_status = "APPROVED"
                for mapping in drug.components:
                    if mapping.last_import_batch_id == batch_id:
                        mapping.review_status = "APPROVED"
                        mapping.is_active = True
                        mapping.reviewed_by = reviewer_user_id
                        mapping.reviewed_at = reviewed_at
            batch.status = "APPROVED"
            batch.completed_at = reviewed_at
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DRUG_MAPPING_BATCH_APPROVED",
                    outcome="SUCCESS",
                    actor_user_id=reviewer_user_id,
                    entity_type="IMPORT_BATCH",
                    entity_id=batch.id,
                    details={"approved_drugs": len(drugs)},
                ),
            )
            session.commit()
            return len(drugs)

    def get_preview(self, batch_id: str) -> ImportPreview:
        with self.database.session() as session:
            batch = session.scalar(
                select(ImportBatch)
                .options(selectinload(ImportBatch.staging_rows))
                .where(ImportBatch.id == batch_id)
            )
            if batch is None:
                raise ImportStateError("Batch import tidak ditemukan")
            action_counts = json.loads(batch.summary_json or "{}").get(
                "proposed_actions", {}
            )
            issues = tuple(
                ImportIssue(
                    sheet=row.sheet_name,
                    row=row.source_row_number,
                    field="row",
                    message=message,
                )
                for row in batch.staging_rows
                for message in json.loads(row.errors_json)
            )
            return ImportPreview(
                batch_id=batch.id,
                filename=batch.source_filename,
                source_version=batch.source_version,
                total_rows=batch.total_rows,
                valid_rows=batch.valid_rows,
                invalid_rows=batch.invalid_rows,
                proposed_inserts=int(action_counts.get("INSERT", 0)),
                proposed_updates=int(action_counts.get("UPDATE", 0)),
                proposed_unchanged=int(action_counts.get("UNCHANGED", 0)),
                issues=issues,
            )

    def _read_source(self, path: Path) -> dict[str, TabularSheet]:
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            sheets = self.xlsx_reader.read(path)
            missing = {
                "DRUG_MASTER_KHANZA",
                "DRUG_COMPONENT_MAP",
            } - sheets.keys()
            if missing:
                raise DrugImportError(
                    f"Sheet wajib tidak ditemukan: {', '.join(sorted(missing))}"
                )
            for name in ("DRUG_MASTER_KHANZA", "DRUG_COMPONENT_MAP"):
                if sheets[name].formula_cells:
                    cells = ", ".join(sheets[name].formula_cells[:10])
                    raise DrugImportError(
                        f"Formula tidak diperbolehkan pada {name}: {cells}"
                    )
            return {
                name: sheets[name]
                for name in ("DRUG_MASTER_KHANZA", "DRUG_COMPONENT_MAP")
            }
        if suffix == ".csv":
            sheet = self.csv_reader.read(path)
            return {sheet.name: sheet}
        raise DrugImportError("Format import harus .xlsx atau .csv")

    def _validate(
        self,
        sheets: dict[str, TabularSheet],
        existing_catalog: dict[str, dict[str, Any]],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for sheet in sheets.values():
            header_set = self._detect_headers(sheet)
            if DRUG_HEADERS <= header_set:
                candidates.extend(
                    self._parse_drug_rows(sheet, DRUG_HEADERS)
                )
            elif COMPONENT_HEADERS <= header_set:
                candidates.extend(
                    self._parse_component_rows(sheet, COMPONENT_HEADERS)
                )
            else:
                raise DrugImportError(
                    f"Header pada sheet {sheet.name} tidak dikenali"
                )
        if not candidates:
            raise DrugImportError("Tidak ada baris data yang dapat diproses")
        self._cross_validate(candidates, existing_catalog)
        return candidates

    @staticmethod
    def _detect_headers(sheet: TabularSheet) -> set[str]:
        for row in sheet.rows[:20]:
            headers = {normalize_text(item) for item in row if item is not None}
            if DRUG_HEADERS <= headers or COMPONENT_HEADERS <= headers:
                return headers
        return set()

    @staticmethod
    def _table_rows(
        sheet: TabularSheet, required: frozenset[str]
    ) -> list[tuple[int, dict[str, Any]]]:
        for index, row in enumerate(sheet.rows[:20]):
            headers = [normalize_text(item) for item in row]
            if required <= set(headers):
                if len(headers) != len(set(headers)):
                    raise DrugImportError(
                        f"Header duplikat pada sheet {sheet.name}"
                    )
                result: list[tuple[int, dict[str, Any]]] = []
                for relative_index, data_row in enumerate(
                    sheet.rows[index + 1 :], start=index + 1
                ):
                    if not any(value not in (None, "") for value in data_row):
                        continue
                    source_index = (
                        sheet.row_numbers[relative_index]
                        if sheet.row_numbers
                        else relative_index + 1
                    )
                    values = list(data_row) + [None] * (
                        len(headers) - len(data_row)
                    )
                    result.append(
                        (
                            source_index,
                            dict(zip(headers, values, strict=True)),
                        )
                    )
                return result
        raise DrugImportError(f"Header tidak ditemukan pada {sheet.name}")

    def _parse_drug_rows(
        self, sheet: TabularSheet, required: frozenset[str]
    ) -> list[_Candidate]:
        result: list[_Candidate] = []
        for row_number, raw in self._table_rows(sheet, required):
            errors: list[str] = []
            version = normalize_text(raw.get("database_version"))
            code = normalize_code(raw.get("khanza_code"))
            display_name = normalize_text(raw.get("khanza_name_display"))
            normalized_source = normalize_name(
                raw.get("khanza_name_normalized_source") or display_name
            )
            ingredients = split_ingredients(
                raw.get("standard_active_ingredients")
            )
            component_count = parse_nonnegative_int(
                raw.get("component_count"), "component_count", errors
            )
            mapping_status = normalize_text(
                raw.get("mapping_status")
            ).upper()
            mapping_method = normalize_text(raw.get("mapping_method"))
            rx_row_count = parse_nonnegative_int(
                raw.get("rx_row_count"), "rx_row_count", errors
            )
            episode_count = parse_nonnegative_int(
                raw.get("episode_count"), "episode_count", errors
            )
            if not version:
                errors.append("database_version wajib diisi")
            if not code or len(code) > 50:
                errors.append("khanza_code wajib diisi dan maksimal 50 karakter")
            if not display_name:
                errors.append("khanza_name_display wajib diisi")
            if not normalized_source:
                errors.append("khanza_name_normalized_source wajib diisi")
            if mapping_status not in ALLOWED_MAPPING_STATUSES:
                errors.append(f"mapping_status tidak valid: {mapping_status}")
            if not mapping_method:
                errors.append("mapping_method wajib diisi")
            if component_count != len(ingredients):
                errors.append(
                    "component_count tidak sama dengan daftar zat aktif master"
                )
            if mapping_status == "MAPPED" and component_count == 0:
                errors.append("Status MAPPED wajib mempunyai komponen")
            normalized = {
                "database_version": version,
                "khanza_code": code,
                "display_name": display_name,
                "normalized_name": normalized_source,
                "source_ingredients": ingredients,
                "component_count": component_count,
                "source_mapping_status": mapping_status,
                "mapping_method": mapping_method,
                "mapping_note": normalize_text(raw.get("mapping_note")) or None,
                "rx_row_count": rx_row_count,
                "episode_count": episode_count,
                "name_variants_raw": normalize_text(
                    raw.get("name_variants")
                )
                or None,
                "aliases": split_aliases(
                    display_name, raw.get("name_variants")
                ),
            }
            result.append(
                _Candidate(
                    sheet=sheet.name,
                    row=row_number,
                    entity_type="DRUG",
                    raw=raw,
                    normalized=normalized,
                    errors=errors,
                )
            )
        return result

    def _parse_component_rows(
        self, sheet: TabularSheet, required: frozenset[str]
    ) -> list[_Candidate]:
        result: list[_Candidate] = []
        for row_number, raw in self._table_rows(sheet, required):
            errors: list[str] = []
            version = normalize_text(raw.get("database_version"))
            code = normalize_code(raw.get("khanza_code"))
            display_name = normalize_text(raw.get("khanza_name_display"))
            order = parse_nonnegative_int(
                raw.get("component_order"), "component_order", errors
            )
            ingredient = normalize_name(
                raw.get("standard_active_ingredient")
            )
            mapping_status = normalize_text(
                raw.get("mapping_status")
            ).upper()
            mapping_method = normalize_text(raw.get("mapping_method"))
            if not version:
                errors.append("database_version wajib diisi")
            if not code or len(code) > 50:
                errors.append("khanza_code wajib diisi dan maksimal 50 karakter")
            if not display_name:
                errors.append("khanza_name_display wajib diisi")
            if order < 1:
                errors.append("component_order harus dimulai dari 1")
            if not ingredient:
                errors.append("standard_active_ingredient wajib diisi")
            if mapping_status not in ALLOWED_MAPPING_STATUSES:
                errors.append(f"mapping_status tidak valid: {mapping_status}")
            if not mapping_method:
                errors.append("mapping_method wajib diisi")
            normalized = {
                "database_version": version,
                "khanza_code": code,
                "display_name": display_name,
                "component_order": order,
                "standard_active_ingredient": ingredient,
                "source_mapping_status": mapping_status,
                "mapping_method": mapping_method,
            }
            result.append(
                _Candidate(
                    sheet=sheet.name,
                    row=row_number,
                    entity_type="COMPONENT",
                    raw=raw,
                    normalized=normalized,
                    errors=errors,
                )
            )
        return result

    def _cross_validate(
        self,
        candidates: list[_Candidate],
        existing_catalog: dict[str, dict[str, Any]],
    ) -> None:
        versions: dict[str, list[_Candidate]] = defaultdict(list)
        drugs: dict[str, list[_Candidate]] = defaultdict(list)
        components: dict[str, list[_Candidate]] = defaultdict(list)
        for candidate in candidates:
            if not candidate.normalized:
                continue
            version = candidate.normalized.get("database_version", "")
            versions[version].append(candidate)
            code = candidate.normalized.get("khanza_code", "")
            if candidate.entity_type == "DRUG":
                drugs[code].append(candidate)
            else:
                components[code].append(candidate)

        nonempty_versions = {item for item in versions if item}
        if len(nonempty_versions) > 1:
            for rows in versions.values():
                for row in rows:
                    row.errors.append(
                        "database_version tidak konsisten dalam satu import"
                    )

        for code, rows in drugs.items():
            if code and len(rows) > 1:
                for row in rows:
                    row.errors.append(f"khanza_code duplikat: {code}")

        for code, rows in components.items():
            orders: dict[int, list[_Candidate]] = defaultdict(list)
            ingredients: dict[str, list[_Candidate]] = defaultdict(list)
            for row in rows:
                orders[row.normalized["component_order"]].append(row)
                ingredients[
                    row.normalized["standard_active_ingredient"]
                ].append(row)
            for order, duplicates in orders.items():
                if len(duplicates) > 1:
                    for row in duplicates:
                        row.errors.append(
                            f"component_order duplikat untuk {code}: {order}"
                        )
            for ingredient, duplicates in ingredients.items():
                if len(duplicates) > 1:
                    for row in duplicates:
                        row.errors.append(
                            f"zat aktif duplikat untuk {code}: {ingredient}"
                        )

        for code, drug_rows in drugs.items():
            if not code or len(drug_rows) != 1:
                continue
            drug = drug_rows[0]
            component_group = components.get(code, [])
            if not component_group and drug.normalized["component_count"] > 0:
                existing = existing_catalog.get(code)
                expected = sorted(drug.normalized["source_ingredients"])
                if existing is None or existing["ingredients"] != expected:
                    drug.errors.append(
                        "Detail DRUG_COMPONENT_MAP untuk kode ini tidak ditemukan"
                    )
                    continue
            if component_group:
                expected_count = drug.normalized["component_count"]
                actual_count = len(component_group)
                if expected_count != actual_count:
                    drug.errors.append(
                        "component_count tidak sama dengan jumlah baris komponen"
                    )
                actual_orders = sorted(
                    row.normalized["component_order"]
                    for row in component_group
                )
                if actual_orders != list(range(1, actual_count + 1)):
                    for row in component_group:
                        row.errors.append(
                            "Urutan komponen harus berurutan mulai dari 1"
                        )
                actual_ingredients = sorted(
                    row.normalized["standard_active_ingredient"]
                    for row in component_group
                )
                if sorted(drug.normalized["source_ingredients"]) != actual_ingredients:
                    drug.errors.append(
                        "Daftar zat aktif master tidak sama dengan detail komponen"
                    )
                for row in component_group:
                    if (
                        normalize_name(row.normalized["display_name"])
                        != normalize_name(drug.normalized["display_name"])
                    ):
                        row.errors.append(
                            "Nama obat komponen tidak konsisten dengan master"
                        )
                    if (
                        row.normalized["database_version"]
                        != drug.normalized["database_version"]
                    ):
                        row.errors.append(
                            "database_version komponen tidak sama dengan master"
                        )

        for code, component_rows in components.items():
            if code not in drugs:
                existing = existing_catalog.get(code)
                if existing is None:
                    for row in component_rows:
                        row.errors.append(
                            "Master obat tidak tersedia dalam file atau database"
                        )
                else:
                    for row in component_rows:
                        if (
                            normalize_name(row.normalized["display_name"])
                            != normalize_name(existing["display_name"])
                        ):
                            row.errors.append(
                                "Nama obat komponen tidak konsisten dengan master database"
                            )

    def _assign_actions(
        self, session, candidates: list[_Candidate]
    ) -> None:
        existing_drugs = {
            row.khanza_code: row
            for row in session.scalars(select(DrugMaster)).all()
        }
        for candidate in candidates:
            if candidate.errors or candidate.normalized is None:
                candidate.proposed_action = "INVALID"
                continue
            code = candidate.normalized["khanza_code"]
            drug = existing_drugs.get(code)
            if drug is None:
                candidate.proposed_action = "INSERT"
                continue
            if candidate.entity_type == "DRUG":
                candidate.proposed_action = (
                    "UNCHANGED"
                    if self._drug_matches(drug, candidate.normalized)
                    else "UPDATE"
                )
                continue
            existing = {
                item.component_order: item
                for item in drug.components
            }.get(candidate.normalized["component_order"])
            candidate.proposed_action = (
                "UPDATE" if existing is not None else "INSERT"
            )

    @staticmethod
    def _drug_matches(drug: DrugMaster, data: dict[str, Any]) -> bool:
        return (
            drug.display_name == data["display_name"]
            and drug.normalized_name == data["normalized_name"]
            and drug.source_mapping_status == data["source_mapping_status"]
            and drug.mapping_method == data["mapping_method"]
            and drug.component_count == data["component_count"]
            and drug.rx_row_count == data["rx_row_count"]
            and drug.episode_count == data["episode_count"]
        )

    def _upsert_drug(
        self, session, data: dict[str, Any], batch_id: str
    ) -> tuple[DrugMaster, str]:
        drug = session.scalar(
            select(DrugMaster).where(
                DrugMaster.khanza_code == data["khanza_code"]
            )
        )
        if drug is None:
            drug = DrugMaster(
                khanza_code=data["khanza_code"],
                display_name=data["display_name"],
                normalized_name=data["normalized_name"],
                source_version=data["database_version"],
                source_mapping_status=data["source_mapping_status"],
                review_status="PENDING_REVIEW",
                mapping_method=data["mapping_method"],
                mapping_note=data["mapping_note"],
                component_count=data["component_count"],
                rx_row_count=data["rx_row_count"],
                episode_count=data["episode_count"],
                name_variants_raw=data["name_variants_raw"],
                last_import_batch_id=batch_id,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(drug)
            session.flush()
            return drug, "inserted"

        unchanged = self._drug_matches(drug, data)
        mapping_relevant_changed = (
            drug.source_mapping_status != data["source_mapping_status"]
            or drug.mapping_method != data["mapping_method"]
            or drug.component_count != data["component_count"]
        )
        drug.display_name = data["display_name"]
        drug.normalized_name = data["normalized_name"]
        drug.source_version = data["database_version"]
        drug.source_mapping_status = data["source_mapping_status"]
        drug.mapping_method = data["mapping_method"]
        drug.mapping_note = data["mapping_note"]
        drug.component_count = data["component_count"]
        drug.rx_row_count = data["rx_row_count"]
        drug.episode_count = data["episode_count"]
        drug.name_variants_raw = data["name_variants_raw"]
        drug.last_import_batch_id = batch_id
        drug.updated_at = utc_now()
        if mapping_relevant_changed:
            drug.review_status = "PENDING_REVIEW"
        return drug, "unchanged" if unchanged else "updated"

    @staticmethod
    def _upsert_aliases(session, drug: DrugMaster, aliases: list[str]) -> None:
        existing = {alias.normalized_alias for alias in drug.aliases}
        for index, alias_name in enumerate(aliases):
            normalized = normalize_name(alias_name)
            if not normalized or normalized in existing:
                continue
            session.add(
                DrugAlias(
                    drug_id=drug.id,
                    alias_name=alias_name,
                    normalized_alias=normalized,
                    source="IMPORT",
                    is_preferred=index == 0,
                    created_at=utc_now(),
                )
            )
            existing.add(normalized)

    def _replace_or_refresh_components(
        self,
        session,
        drug: DrugMaster,
        rows: list[dict[str, Any]],
        batch_id: str,
    ) -> dict[str, int]:
        rows = sorted(rows, key=lambda item: item["component_order"])
        current = sorted(
            (
                mapping.component_order,
                mapping.ingredient.normalized_name,
            )
            for mapping in drug.components
        )
        proposed = [
            (row["component_order"], row["standard_active_ingredient"])
            for row in rows
        ]
        if current == proposed:
            mapping_metadata_changed = any(
                mapping.source_mapping_status != row["source_mapping_status"]
                or mapping.mapping_method != row["mapping_method"]
                for mapping, row in zip(
                    sorted(
                        drug.components,
                        key=lambda item: item.component_order,
                    ),
                    rows,
                    strict=True,
                )
            )
            for mapping, row in zip(
                sorted(drug.components, key=lambda item: item.component_order),
                rows,
                strict=True,
            ):
                mapping.source_mapping_status = row["source_mapping_status"]
                mapping.mapping_method = row["mapping_method"]
                mapping.source_version = row["database_version"]
                mapping.last_import_batch_id = batch_id
                mapping.updated_at = utc_now()
                if mapping_metadata_changed:
                    mapping.review_status = "PENDING_REVIEW"
                    mapping.is_active = False
                    mapping.reviewed_by = None
                    mapping.reviewed_at = None
            if mapping_metadata_changed:
                drug.review_status = "PENDING_REVIEW"
            return {"inserted": 0, "updated": 0, "unchanged": len(rows)}

        existing_count = len(drug.components)
        for mapping in list(drug.components):
            session.delete(mapping)
        session.flush()
        drug.review_status = "PENDING_REVIEW"
        drug.component_count = len(rows)
        drug.last_import_batch_id = batch_id

        ingredients = {
            item.normalized_name: item
            for item in session.scalars(
                select(ActiveIngredient).where(
                    ActiveIngredient.normalized_name.in_(
                        [row["standard_active_ingredient"] for row in rows]
                    )
                )
            ).all()
        }
        inserted_ingredients = 0
        for row in rows:
            ingredient_name = row["standard_active_ingredient"]
            ingredient = ingredients.get(ingredient_name)
            if ingredient is None:
                ingredient = ActiveIngredient(
                    standard_name=ingredient_name,
                    normalized_name=ingredient_name,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                session.add(ingredient)
                session.flush()
                ingredients[ingredient_name] = ingredient
                inserted_ingredients += 1
            session.add(
                DrugComponentMapping(
                    drug_id=drug.id,
                    ingredient_id=ingredient.id,
                    component_order=row["component_order"],
                    source_mapping_status=row["source_mapping_status"],
                    mapping_method=row["mapping_method"],
                    review_status="PENDING_REVIEW",
                    is_active=False,
                    source_version=row["database_version"],
                    last_import_batch_id=batch_id,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        return {
            "inserted": len(rows) + inserted_ingredients,
            "updated": existing_count,
            "unchanged": 0,
        }

    @staticmethod
    def _require_manager(session, actor_user_id: str) -> AppUser:
        user = session.scalar(
            select(AppUser)
            .options(
                selectinload(AppUser.roles).selectinload(UserRole.role)
            )
            .where(AppUser.id == actor_user_id)
        )
        if user is None or not user.is_active:
            raise ImportPermissionError("Pengguna tidak aktif atau tidak ditemukan")
        roles = {link.role.code for link in user.roles}
        if not roles.intersection(MANAGER_ROLES):
            raise ImportPermissionError(
                "Role pengguna tidak berwenang mengelola mapping obat"
            )
        return user

    @staticmethod
    def _sha256(path: Path) -> str:
        if not path.is_file():
            raise DrugImportError(f"File tidak ditemukan: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
