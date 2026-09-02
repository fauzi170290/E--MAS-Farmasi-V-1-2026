from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from emss.database.catalog_models import (
    ActiveIngredient,
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
)
from emss.database.knowledge_models import (
    DdiRule,
    KnowledgeBaseTransition,
    KnowledgeBaseVersion,
)
from emss.database.models import AuditLog
from emss.importexport.ddi_import import (
    DdiImportError,
    DdiImportPermissionError,
    DdiImportStateError,
)
from emss.importexport.ddi_export import DdiExportError, IMPORT_HEADERS
from emss.importexport.tabular_reader import XlsxTableReader
from emss.services.knowledge import (
    KnowledgePermissionError,
    KnowledgeStateError,
    ManualDdiRule,
)
from tests.helpers.xlsx_factory import (
    DDI_TEMPLATE_HEADERS,
    valid_ddi_source_rows,
    write_ddi_workbook,
)


def _admin(container):
    return container.users.create_first_admin(
        username="admin.ddi",
        display_name="Admin DDI",
        password="Frasa aman admin DDI!",
    )


def _seed_ingredients(container, *names: str) -> None:
    with container.database.session() as session:
        for name in names:
            session.add(
                ActiveIngredient(
                    standard_name=name,
                    normalized_name=name.casefold(),
                )
            )
        session.commit()


def _seed_approved_khanza_drug(
    container,
    *,
    code: str,
    display_name: str,
    ingredient_name: str,
) -> None:
    with container.database.session() as session:
        ingredient = session.scalar(
            select(ActiveIngredient).where(
                ActiveIngredient.normalized_name == ingredient_name.casefold()
            )
        )
        assert ingredient is not None
        drug = DrugMaster(
            khanza_code=code,
            display_name=display_name,
            normalized_name=display_name.casefold(),
            source_version="TEST",
            source_mapping_status="MAPPED",
            review_status="APPROVED",
            mapping_method="test",
            component_count=1,
        )
        session.add(drug)
        session.flush()
        session.add(
            DrugComponentMapping(
                drug_id=drug.id,
                ingredient_id=ingredient.id,
                component_order=1,
                source_mapping_status="MAPPED",
                mapping_method="test",
                review_status="APPROVED",
                is_active=True,
                source_version="TEST",
            )
        )
        session.commit()


@pytest.mark.integration
def test_ddi_preview_commit_creates_draft_and_backup(tmp_path, app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin", "paracetamol")
    source = write_ddi_workbook(
        tmp_path / "ddi.xlsx", valid_ddi_source_rows()
    )

    preview = app_container.ddi_import.preview(source, admin.id)
    restored = app_container.ddi_import.get_preview(preview.batch_id)
    result = app_container.ddi_import.commit(preview.batch_id, admin.id)

    assert preview.commit_allowed
    assert preview.total_rows == 3
    assert restored.version_code == "DDI-TEST-v1"
    assert result.inserted == 3
    assert Path(result.backup_path).is_file()
    with app_container.database.session() as session:
        version = session.get(KnowledgeBaseVersion, result.version_id)
        rules = session.scalars(
            select(DdiRule).where(
                DdiRule.knowledge_base_version_id == result.version_id
            )
        ).all()
        batch = session.get(ImportBatch, preview.batch_id)
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert version is not None and version.status == "DRAFT"
        assert len(rules) == 3
        assert not any(rule.is_enabled for rule in rules)
        assert sum(rule.clinical_review_required for rule in rules) == 1
        assert batch is not None and batch.status == "COMMITTED"
        assert {"DDI_IMPORT_PREVIEWED", "DDI_IMPORT_COMMITTED"} <= actions


@pytest.mark.integration
def test_complete_ddi_export_is_populated_reimportable_and_audited(
    tmp_path, app_container
):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin", "paracetamol")
    source = write_ddi_workbook(tmp_path / "ddi.xlsx", valid_ddi_source_rows())
    preview = app_container.ddi_import.preview(source, admin.id)
    committed = app_container.ddi_import.commit(preview.batch_id, admin.id)

    target = tmp_path / "MASTER_DDI_EXPORT_LENGKAP.xlsx"
    result = app_container.ddi_export.export_version(
        committed.version_id, target, admin.id
    )
    sheets = XlsxTableReader().read(target)
    exported_preview = app_container.ddi_import.preview(target, admin.id)

    assert result.rule_count == 3
    assert result.path.is_file()
    assert result.checksum_path.is_file()
    assert result.checksum_sha256 in result.checksum_path.read_text(encoding="utf-8")
    assert {
        "RINGKASAN",
        "DDI_IMPORT",
        "DDI_EXPORT_LENGKAP",
        "MASTER_ZAT_AKTIF",
        "MAPPING_OBAT_KHANZA",
        "CODEBOOK",
    } == set(sheets)
    assert tuple(value for value in sheets["DDI_IMPORT"].rows[0]) == IMPORT_HEADERS
    assert len(sheets["DDI_IMPORT"].rows) == 4
    assert len(sheets["DDI_EXPORT_LENGKAP"].rows) == 4
    assert not sheets["DDI_IMPORT"].formula_cells
    assert exported_preview.total_rows == 3
    assert exported_preview.invalid_rows == 0
    with app_container.database.session() as session:
        assert "DDI_MASTER_EXPORTED" in set(
            session.scalars(select(AuditLog.action)).all()
        )


@pytest.mark.integration
def test_complete_ddi_export_rejects_unauthorized_role(tmp_path, app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin", "paracetamol")
    source = write_ddi_workbook(tmp_path / "ddi.xlsx", valid_ddi_source_rows())
    preview = app_container.ddi_import.preview(source, admin.id)
    committed = app_container.ddi_import.commit(preview.batch_id, admin.id)
    user = app_container.users.create_user(
        username="apoteker.export",
        display_name="Apoteker Export",
        password="Frasa aman apoteker export!",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )

    with pytest.raises(DdiExportError, match="tidak berwenang"):
        app_container.ddi_export.export_version(
            committed.version_id, tmp_path / "blocked.xlsx", user.id
        )


@pytest.mark.integration
def test_duplicate_or_unknown_pairs_block_commit(tmp_path, app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin")
    rows = valid_ddi_source_rows()[:1]
    reversed_row = list(rows[0])
    reversed_row[1] = "diazepam || warfarin"
    reversed_row[2] = "warfarin"
    reversed_row[3] = "diazepam"
    rows.append(reversed_row)
    unknown = list(rows[0])
    unknown[0] = "DDI-999"
    unknown[1] = "diazepam || unknown"
    unknown[3] = "unknown"
    rows.append(unknown)
    source = write_ddi_workbook(tmp_path / "invalid-ddi.xlsx", rows)

    preview = app_container.ddi_import.preview(source, admin.id)
    messages = " ".join(issue.message for issue in preview.issues)

    assert preview.invalid_rows >= 2
    assert "duplikat/terbalik" in messages
    assert "belum ada di master obat" in messages
    with pytest.raises(DdiImportStateError):
        app_container.ddi_import.commit(preview.batch_id, admin.id)


@pytest.mark.integration
def test_formula_and_bad_source_validation_are_rejected(tmp_path, app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin")
    formula = write_ddi_workbook(
        tmp_path / "formula.xlsx",
        valid_ddi_source_rows()[:1],
        formula_cell="J4",
    )
    with pytest.raises(DdiImportError, match="Formula"):
        app_container.ddi_import.preview(formula, admin.id)

    rows = valid_ddi_source_rows()[:1]
    rows[0][1] = "warfarin || diazepam"
    rows[0][8] = 1
    rows[0][21] = "31/07/2026"
    bad = write_ddi_workbook(tmp_path / "bad.xlsx", rows)
    preview = app_container.ddi_import.preview(bad, admin.id)
    messages = " ".join(issue.message for issue in preview.issues)
    assert "pair_key tidak sesuai" in messages
    assert "severity_rank tidak sesuai" in messages
    assert "YYYY-MM-DD" in messages


@pytest.mark.integration
def test_template_csv_import_and_checksum_protection(tmp_path, app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin")
    source = tmp_path / "ddi.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DDI_TEMPLATE_HEADERS)
        writer.writerow(
            [
                "",
                "diazepam",
                "",
                "warfarin",
                "INTERACTION_FOUND",
                "SIGNIFICANT",
                "Significant",
                "Risiko sedasi/perdarahan.",
                "Farmakodinamik",
                "Monitor dan evaluasi.",
                "Respons klinis",
                "Lansia",
                "Sumber Lokal",
                "DOC-001",
                "2026-07-30",
                "Apoteker",
                "2026-07-30T08:00:00",
                "LOCAL-v1",
                "DRAFT",
                "Uji template",
            ]
        )

    first = app_container.ddi_import.preview(source, admin.id)
    app_container.ddi_import.commit(first.batch_id, admin.id)
    second = app_container.ddi_import.preview(source, admin.id)
    with pytest.raises(DdiImportStateError, match="checksum"):
        app_container.ddi_import.commit(second.batch_id, admin.id)


@pytest.mark.integration
def test_template_resolves_approved_khanza_codes_to_active_ingredients(
    tmp_path, app_container
):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin")
    _seed_approved_khanza_drug(
        app_container,
        code="RX-DIAZ",
        display_name="DIAZEPAM TAB 5 MG",
        ingredient_name="diazepam",
    )
    _seed_approved_khanza_drug(
        app_container,
        code="RX-WARF",
        display_name="WARFARIN TAB 2 MG",
        ingredient_name="warfarin",
    )
    source = tmp_path / "ddi-khanza-code.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DDI_TEMPLATE_HEADERS)
        writer.writerow(
            [
                "RX-DIAZ",
                "DIAZEPAM TAB 5 MG",
                "RX-WARF",
                "WARFARIN TAB 2 MG",
                "INTERACTION_FOUND",
                "SERIOUS",
                "Major",
                "Efek klinis uji.",
                "Mekanisme uji.",
                "Rekomendasi uji.",
                "Monitoring uji.",
                "",
                "Sumber Uji",
                "REF-001",
                "2026-08-04",
                "",
                "",
                "DDI-KHANZA-CODE-v1",
                "DRAFT",
                "Uji resolusi kode Khanza",
            ]
        )

    preview = app_container.ddi_import.preview(source, admin.id)
    result = app_container.ddi_import.commit(preview.batch_id, admin.id)

    assert preview.commit_allowed
    assert result.inserted == 1
    with app_container.database.session() as session:
        rule = session.scalar(
            select(DdiRule)
            .join(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.version_code == "DDI-KHANZA-CODE-v1"
            )
        )
        assert rule is not None
        assert rule.pair_key == "diazepam || warfarin"


@pytest.mark.integration
def test_knowledge_workflow_requires_roles_and_resolved_holds(app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin", "paracetamol")
    version_id = app_container.knowledge.create_version(
        "MANUAL-v1", "Manual v1", admin.id
    )
    serious = ManualDdiRule(
        version_id=version_id,
        ingredient_a="warfarin",
        ingredient_b="diazepam",
        interaction_status="INTERACTION_FOUND",
        severity_code="SERIOUS",
        severity_label="Serious",
        clinical_effect="Risiko meningkat.",
        recommendation="Monitor.",
        source_name="Sumber Internal",
        source_accessed_at=date(2026, 7, 30),
    )
    rule_id = app_container.knowledge.save_manual_rule(serious, admin.id)
    unresolved = app_container.knowledge.list_rules(
        version_id, filter_code="UNRESOLVED_HOLD"
    )
    assert [row.id for row in unresolved] == [rule_id]
    detail = app_container.knowledge.get_rule_detail(rule_id)
    assert detail.pair_key == "diazepam || warfarin"
    assert detail.recommendation == "Monitor."
    assert detail.clinical_review_required
    app_container.knowledge.save_manual_rule(
        ManualDdiRule(
            version_id=version_id,
            ingredient_a="paracetamol",
            ingredient_b="warfarin",
            interaction_status="ASSESSED_NO_INTERACTION",
            severity_code="NONE",
            source_name="Sumber Internal",
            source_accessed_at=date(2026, 7, 30),
        ),
        admin.id,
    )
    with pytest.raises(KnowledgeStateError, match="HOLD"):
        app_container.knowledge.review_version(version_id, admin.id)

    reviewer = app_container.users.create_user(
        username="reviewer.ddi",
        display_name="Reviewer DDI",
        password="Frasa aman reviewer DDI!",
        roles=("CLINICAL_REVIEWER",),
        actor_user_id=admin.id,
    )
    app_container.knowledge.resolve_rule_review(
        rule_id, reviewer.id, "Isi klinis dan sumber telah diverifikasi"
    )
    assert not app_container.knowledge.list_rules(
        version_id, filter_code="UNRESOLVED_HOLD"
    )
    assert [
        row.id
        for row in app_container.knowledge.list_rules(
            version_id, filter_code="RESOLVED_HOLD"
        )
    ] == [rule_id]
    app_container.knowledge.review_version(version_id, reviewer.id, "Valid")
    app_container.knowledge.approve_version(version_id, admin.id, "Disetujui")
    app_container.knowledge.publish_version(version_id, admin.id, "Berlaku")

    summary = app_container.knowledge.summary(version_id)
    assert summary.required_holds == 1
    rules = app_container.knowledge.list_rules(version_id)
    assert summary.total_rules == 2
    assert summary.enabled_rules == 1
    assert next(row for row in rules if row.id == rule_id).is_enabled
    assert not next(
        row for row in rules if row.interaction_status == "ASSESSED_NO_INTERACTION"
    ).is_enabled

    app_container.knowledge.retire_version(version_id, admin.id, "Diganti")
    app_container.knowledge.rollback_to(version_id, admin.id, "Rollback uji")
    versions = app_container.knowledge.list_versions()
    assert versions[0].status == "PUBLISHED"
    with app_container.database.session() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(KnowledgeBaseTransition)
            )
            >= 6
        )


@pytest.mark.integration
def test_duplicate_version_returns_rules_to_draft(app_container):
    admin = _admin(app_container)
    _seed_ingredients(app_container, "diazepam", "warfarin")
    source_id = app_container.knowledge.create_version(
        "SOURCE-v1", "Source", admin.id
    )
    app_container.knowledge.save_manual_rule(
        ManualDdiRule(
            version_id=source_id,
            ingredient_a="diazepam",
            ingredient_b="warfarin",
            interaction_status="INTERACTION_FOUND",
            severity_code="MINOR",
            source_name="Sumber",
            source_accessed_at=date(2026, 7, 30),
        ),
        admin.id,
    )
    target_id = app_container.knowledge.duplicate_version(
        source_id, "SOURCE-v2", "Source v2", admin.id
    )
    target = app_container.knowledge.list_rules(target_id)
    assert len(target) == 1
    assert target[0].record_status == "DRAFT"
    assert not target[0].is_enabled


@pytest.mark.integration
def test_unauthorized_user_cannot_manage_knowledge(tmp_path, app_container):
    admin = _admin(app_container)
    apoteker = app_container.users.create_user(
        username="apoteker.ddi",
        display_name="Apoteker DDI",
        password="Frasa aman apoteker DDI!",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    _seed_ingredients(app_container, "diazepam", "warfarin")
    source = write_ddi_workbook(
        tmp_path / "ddi.xlsx", valid_ddi_source_rows()[:1]
    )
    with pytest.raises(DdiImportPermissionError):
        app_container.ddi_import.preview(source, apoteker.id)
    with pytest.raises(KnowledgePermissionError):
        app_container.knowledge.create_version(
            "DENIED-v1", "Denied", apoteker.id
        )
