from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import aliased, selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import (
    ActiveIngredient,
    DrugComponentMapping,
    DrugMaster,
)
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.database.models import AppUser, UserRole
from emss.importexport.xlsx_writer import XlsxSheet, write_xlsx
from emss.utils.time import utc_now


class DdiExportError(ValueError):
    pass


@dataclass(frozen=True)
class DdiExportResult:
    path: Path
    checksum_path: Path
    checksum_sha256: str
    version_code: str
    version_status: str
    rule_count: int
    unresolved_holds: int


IMPORT_HEADERS = (
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
)


FULL_HEADERS = (
    "rule_id",
    "knowledge_base_version_id",
    "knowledge_base_version",
    "version_workflow_status",
    "external_pair_id",
    "ingredient_low_id",
    "ingredient_low_name",
    "ingredient_low_normalized",
    "ingredient_high_id",
    "ingredient_high_name",
    "ingredient_high_normalized",
    "pair_key",
    "interaction_status",
    "severity_code",
    "severity_label",
    "severity_rank",
    "app_severity",
    "clinical_effect",
    "mechanism",
    "recommendation",
    "monitoring",
    "population_risk",
    "source_name",
    "source_reference",
    "source_accessed_at",
    "source_batch",
    "source_evidence_count",
    "source_validation_status",
    "source_final_code",
    "activation_status",
    "clinical_review_required",
    "clinical_review_resolved",
    "record_status",
    "is_enabled",
    "validated_by_name",
    "validated_at",
    "notes",
    "created_by_user_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
)


class DdiExportService:
    EXPORT_ROLES = frozenset(
        {"SUPER_ADMIN", "KNOWLEDGE_ADMIN", "CLINICAL_REVIEWER", "KFT", "IT_ADMIN"}
    )

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def export_version(
        self,
        version_id: str,
        target: Path | str,
        actor_user_id: str,
    ) -> DdiExportResult:
        destination = Path(target)
        if destination.suffix.lower() != ".xlsx":
            destination = destination.with_suffix(".xlsx")
        low = aliased(ActiveIngredient)
        high = aliased(ActiveIngredient)
        with self.database.session() as session:
            self._require_exporter(session, actor_user_id)
            version = session.get(KnowledgeBaseVersion, version_id)
            if version is None:
                raise DdiExportError("Versi knowledge base tidak ditemukan")
            query_rows = session.execute(
                select(DdiRule, low, high)
                .join(low, low.id == DdiRule.ingredient_low_id)
                .join(high, high.id == DdiRule.ingredient_high_id)
                .where(DdiRule.knowledge_base_version_id == version.id)
                .order_by(DdiRule.pair_key)
            ).all()
            if not query_rows:
                raise DdiExportError("Versi knowledge base belum memiliki rule")
            unresolved = sum(
                rule.clinical_review_required and not rule.clinical_review_resolved
                for rule, _, _ in query_rows
            )
            resolved = sum(
                rule.clinical_review_required and rule.clinical_review_resolved
                for rule, _, _ in query_rows
            )
            missing_source = sum(not rule.source_name.strip() for rule, _, _ in query_rows)
            missing_date = sum(rule.source_accessed_at is None for rule, _, _ in query_rows)
            ingredient_ids = {
                ingredient_id
                for rule, _, _ in query_rows
                for ingredient_id in (rule.ingredient_low_id, rule.ingredient_high_id)
            }
            drug_mapping_rows = session.execute(
                select(
                    DrugMaster.khanza_code,
                    DrugMaster.display_name,
                    ActiveIngredient.standard_name,
                    DrugMaster.review_status,
                    DrugComponentMapping.review_status,
                    DrugComponentMapping.is_active,
                    DrugMaster.mapping_method,
                )
                .join(DrugComponentMapping, DrugComponentMapping.drug_id == DrugMaster.id)
                .join(ActiveIngredient, ActiveIngredient.id == DrugComponentMapping.ingredient_id)
                .where(ActiveIngredient.id.in_(ingredient_ids))
                .order_by(DrugMaster.khanza_code, DrugComponentMapping.component_order)
            ).all()

            exported_at = utc_now().isoformat(timespec="seconds")
            summary_rows = [
                ["EXPORT MASTER DDI LENGKAP", "", "", ""],
                ["Keterangan", "Nilai", "Kontrol", "Penjelasan"],
                ["Versi", version.version_code, "Workflow", version.status],
                ["Judul", version.title, "Diekspor", exported_at],
                ["Jumlah rule", len(query_rows), "Rule aktif", sum(rule.is_enabled for rule, _, _ in query_rows)],
                ["HOLD belum selesai", unresolved, "HOLD selesai", resolved],
                ["Sumber kosong", missing_source, "Tanggal sumber kosong", missing_date],
                ["Pasangan duplikat", 0, "Format", "XLSX tanpa macro/formula"],
                ["Tujuan DDI_IMPORT", "Pemulihan konten sebagai DRAFT", "Keamanan", "Preview dan review ulang tetap wajib"],
                ["Tujuan DDI_EXPORT_LENGKAP", "Arsip seluruh field aplikasi", "Catatan", "Restore database SQLite tetap metode pemulihan utama"],
                ["Kerahasiaan", "Tidak memuat data pasien", "Password", "Tidak pernah diekspor"],
            ]
            import_rows = [list(IMPORT_HEADERS)]
            full_rows = [list(FULL_HEADERS)]
            ingredient_rows = [["ingredient_id", "standard_name", "normalized_name", "is_active"]]
            seen_ingredients: set[str] = set()
            for rule, low_item, high_item in query_rows:
                import_rows.append(
                    [
                        "",
                        low_item.standard_name,
                        "",
                        high_item.standard_name,
                        rule.interaction_status,
                        rule.severity_code,
                        rule.severity_label or "",
                        rule.clinical_effect or "",
                        rule.mechanism or "",
                        rule.recommendation or "",
                        rule.monitoring or "",
                        rule.population_risk or "",
                        rule.source_name,
                        rule.source_reference or "",
                        rule.source_accessed_at.isoformat() if rule.source_accessed_at else "",
                        rule.validated_by_name or "",
                        rule.validated_at.isoformat() if rule.validated_at else "",
                        version.version_code,
                        "DRAFT",
                        rule.notes or "",
                    ]
                )
                full_rows.append(
                    [
                        rule.id,
                        version.id,
                        version.version_code,
                        version.status,
                        rule.external_pair_id or "",
                        low_item.id,
                        low_item.standard_name,
                        low_item.normalized_name,
                        high_item.id,
                        high_item.standard_name,
                        high_item.normalized_name,
                        rule.pair_key,
                        rule.interaction_status,
                        rule.severity_code,
                        rule.severity_label or "",
                        rule.severity_rank,
                        rule.app_severity or "",
                        rule.clinical_effect or "",
                        rule.mechanism or "",
                        rule.recommendation or "",
                        rule.monitoring or "",
                        rule.population_risk or "",
                        rule.source_name,
                        rule.source_reference or "",
                        rule.source_accessed_at.isoformat() if rule.source_accessed_at else "",
                        rule.source_batch or "",
                        rule.source_evidence_count,
                        rule.source_validation_status or "",
                        rule.source_final_code or "",
                        rule.activation_status,
                        rule.clinical_review_required,
                        rule.clinical_review_resolved,
                        rule.record_status,
                        rule.is_enabled,
                        rule.validated_by_name or "",
                        rule.validated_at.isoformat() if rule.validated_at else "",
                        rule.notes or "",
                        rule.created_by,
                        rule.updated_by,
                        rule.created_at.isoformat(),
                        rule.updated_at.isoformat(),
                    ]
                )
                for ingredient in (low_item, high_item):
                    if ingredient.id not in seen_ingredients:
                        ingredient_rows.append(
                            [
                                ingredient.id,
                                ingredient.standard_name,
                                ingredient.normalized_name,
                                ingredient.is_active,
                            ]
                        )
                        seen_ingredients.add(ingredient.id)

            mapping_rows = [[
                "kode_khanza",
                "nama_obat_khanza",
                "zat_aktif",
                "review_obat",
                "review_komponen",
                "komponen_aktif",
                "metode_mapping",
            ]] + [list(row) for row in drug_mapping_rows]
            codebook_rows = [["Sheet/Kolom", "Definisi", "Nilai/aturan"]] + _codebook()

        write_xlsx(
            destination,
            [
                XlsxSheet(
                    "RINGKASAN",
                    summary_rows,
                    (28, 38, 26, 55),
                    freeze_rows=2,
                    auto_filter=False,
                    row_styles={1: 1, 2: 2, 3: 3, 4: 3, 5: 3, 6: 4, 7: 4, 8: 3, 9: 4, 10: 3, 11: 3},
                    merges=("A1:D1",),
                ),
                XlsxSheet(
                    "DDI_IMPORT",
                    import_rows,
                    (14, 24, 14, 24, 25, 20, 20, 45, 35, 45, 40, 32, 25, 45, 18, 22, 22, 24, 14, 40),
                    row_styles={1: 2},
                ),
                XlsxSheet(
                    "DDI_EXPORT_LENGKAP",
                    full_rows,
                    tuple(20 if index < 17 else 38 for index in range(len(FULL_HEADERS))),
                    row_styles={1: 2},
                ),
                XlsxSheet(
                    "MASTER_ZAT_AKTIF",
                    ingredient_rows,
                    (38, 28, 28, 14),
                    row_styles={1: 2},
                ),
                XlsxSheet(
                    "MAPPING_OBAT_KHANZA",
                    mapping_rows,
                    (18, 36, 28, 18, 20, 18, 30),
                    row_styles={1: 2},
                ),
                XlsxSheet(
                    "CODEBOOK",
                    codebook_rows,
                    (34, 60, 60),
                    row_styles={1: 2},
                ),
            ],
        )
        checksum = _sha256(destination)
        checksum_path = destination.with_suffix(".sha256.txt")
        checksum_path.write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")

        with self.database.session() as session:
            self._require_exporter(session, actor_user_id)
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action="DDI_MASTER_EXPORTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="KNOWLEDGE_BASE_VERSION",
                    entity_id=version_id,
                    details={
                        "version_code": version.version_code,
                        "version_status": version.status,
                        "rule_count": len(query_rows),
                        "filename": destination.name,
                        "checksum_sha256": checksum,
                    },
                ),
            )
            session.commit()
        return DdiExportResult(
            path=destination,
            checksum_path=checksum_path,
            checksum_sha256=checksum,
            version_code=version.version_code,
            version_status=version.status,
            rule_count=len(query_rows),
            unresolved_holds=unresolved,
        )

    def _require_exporter(self, session, actor_user_id: str) -> None:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id, AppUser.is_active.is_(True))
        )
        if user is None:
            raise DdiExportError("Pengguna aktif tidak ditemukan")
        roles = {link.role.code for link in user.roles}
        if not roles.intersection(self.EXPORT_ROLES):
            raise DdiExportError("Role tidak berwenang mengekspor master DDI")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _codebook() -> list[list[object]]:
    return [
        ["DDI_IMPORT", "Sheet kompatibel dengan menu Import DDI", "Selalu dipulihkan sebagai DRAFT; preview wajib"],
        ["DDI_EXPORT_LENGKAP", "Arsip semua field rule dan workflow", "Untuk audit/pembelajaran; bukan sheet impor"],
        ["interaction_status", "Hasil asesmen pasangan", "INTERACTION_FOUND; ASSESSED_NO_INTERACTION; NOT_ASSESSABLE; EXCLUDED"],
        ["severity_code", "Severity sumber/klinis", "NONE; MINOR; SIGNIFICANT; SERIOUS; CONTRAINDICATED"],
        ["app_severity", "Level alert aplikasi", "INFO; REVIEW; HIGH_RISK; CRITICAL atau kosong"],
        ["clinical_review_required", "Pasangan memerlukan review klinis/HOLD", "TRUE/FALSE"],
        ["clinical_review_resolved", "Review klinis telah selesai", "TRUE/FALSE; hanya dipertahankan di arsip lengkap"],
        ["record_status", "Workflow rule dalam knowledge base", "DRAFT; REVIEWED; APPROVED; PUBLISHED; RETIRED"],
        ["is_enabled", "Rule dipakai engine produksi", "TRUE hanya bila published dan memenuhi kontrol klinis"],
        ["source_accessed_at", "Tanggal sumber diakses", "YYYY-MM-DD"],
        ["validated_at", "Waktu validasi", "ISO 8601"],
        ["pair_key", "Pasangan zat aktif kanonik", "Nama alfabetis dipisahkan oleh ||"],
        ["Pemulihan", "Gunakan backup SQLite untuk restore operasional penuh", "Excel adalah cadangan konten DDI dan bahan pembelajaran"],
        ["Privasi", "Workbook tidak berisi pasien, resep, nomor RM, atau password", "Tetap simpan sebagai dokumen internal terkendali"],
    ]
