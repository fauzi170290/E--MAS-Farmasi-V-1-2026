from __future__ import annotations

import csv

import pytest
from sqlalchemy import func, select

from emss.database.catalog_models import (
    ActiveIngredient,
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
)
from emss.database.models import AuditLog
from emss.importexport.drug_import import (
    DrugImportError,
    ImportPermissionError,
    ImportStateError,
)
from tests.helpers.xlsx_factory import (
    DRUG_HEADERS,
    valid_test_rows,
    write_drug_workbook,
)


ADMIN_PASSWORD = "Frasa aman untuk import 2026!"


def _admin(app_container):
    return app_container.users.create_first_admin(
        username="import.admin",
        display_name="Administrator Import",
        password=ADMIN_PASSWORD,
    )


@pytest.mark.integration
def test_preview_commit_and_approval_are_separate_transactions(
    tmp_path, app_container
):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)

    preview = app_container.drug_import.preview(source, admin.id)

    assert preview.total_rows == 5
    assert preview.valid_rows == 5
    assert preview.invalid_rows == 0
    assert preview.commit_allowed
    assert app_container.catalog.summary().total_drugs == 0

    counts = app_container.drug_import.commit(preview.batch_id, admin.id)
    after_commit = app_container.catalog.summary()

    assert counts["inserted"] == 7  # 2 obat + 3 mapping + 2 zat aktif
    assert after_commit.total_drugs == 2
    assert after_commit.pending_review == 2
    assert after_commit.active_components == 0

    approved = app_container.drug_import.approve_batch(
        preview.batch_id, admin.id
    )
    final = app_container.catalog.summary()

    assert approved == 2
    assert final.approved == 2
    assert final.pending_review == 0
    assert final.active_components == 3

    with app_container.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(ActiveIngredient)
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(DrugComponentMapping)
        ) == 3
        assert session.scalar(
            select(func.count()).select_from(AuditLog)
        ) == 4
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_invalid_component_count_blocks_commit(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    components.pop()
    source = write_drug_workbook(tmp_path / "invalid.xlsx", drugs, components)

    preview = app_container.drug_import.preview(source, admin.id)

    assert preview.invalid_rows > 0
    assert not preview.commit_allowed
    assert any("DRUG_COMPONENT_MAP" in issue.message for issue in preview.issues)
    with pytest.raises(ImportStateError):
        app_container.drug_import.commit(preview.batch_id, admin.id)
    assert app_container.catalog.summary().total_drugs == 0


@pytest.mark.integration
def test_formula_in_import_sheet_is_rejected(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source = write_drug_workbook(
        tmp_path / "formula.xlsx",
        drugs,
        components,
        formula_cell="F4",
    )

    with pytest.raises(DrugImportError, match="Formula tidak diperbolehkan"):
        app_container.drug_import.preview(source, admin.id)


@pytest.mark.integration
def test_same_file_cannot_be_committed_twice(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)
    first = app_container.drug_import.preview(source, admin.id)
    app_container.drug_import.commit(first.batch_id, admin.id)
    second = app_container.drug_import.preview(source, admin.id)

    with pytest.raises(ImportStateError, match="sudah pernah"):
        app_container.drug_import.commit(second.batch_id, admin.id)


@pytest.mark.integration
def test_apoteker_role_cannot_import(tmp_path, app_container):
    admin = _admin(app_container)
    apoteker = app_container.users.create_user(
        username="apoteker.uji",
        display_name="Apoteker Uji",
        password="Frasa aman apoteker uji!",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)

    with pytest.raises(ImportPermissionError):
        app_container.drug_import.preview(source, apoteker.id)


@pytest.mark.integration
def test_csv_can_add_unmapped_master(tmp_path, app_container):
    admin = _admin(app_container)
    source = tmp_path / "drug_master.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DRUG_HEADERS)
        writer.writerow(
            [
                "DDI-TEST-v1",
                "009",
                "OBAT BELUM MAPPING",
                "OBAT BELUM MAPPING",
                "",
                0,
                "UNMAPPED",
                "manual_entry",
                "Menunggu mapping",
                1,
                1,
                "OBAT BELUM MAPPING (1)",
            ]
        )

    preview = app_container.drug_import.preview(source, admin.id)
    app_container.drug_import.commit(preview.batch_id, admin.id)

    summary = app_container.catalog.summary()
    assert preview.commit_allowed
    assert summary.total_drugs == 1
    assert summary.source_unmapped == 1


@pytest.mark.integration
def test_mapping_preview_marks_padded_code_with_different_ingredients_as_conflict(tmp_path, app_container):
    admin = _admin(app_container)
    with app_container.database.session() as session:
        session.add(DrugMaster(
            khanza_code="000000001", display_name="OBAT KOMBINASI",
            normalized_name="obat kombinasi", source_version="HISTORICAL",
            source_mapping_status="UNMAPPED", review_status="PENDING_REVIEW",
            mapping_method="HISTORICAL", component_count=0,
        ))
        session.commit()
    drugs, components = valid_test_rows()
    preview = app_container.drug_import.preview(
        write_drug_workbook(tmp_path / "conflicting-padding.xlsx", drugs, components), admin.id
    )
    assert not preview.commit_allowed
    assert any("Konflik kode Khanza" in issue.message for issue in preview.issues)


@pytest.mark.integration
def test_catalog_search_and_batch_history(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)
    preview = app_container.drug_import.preview(source, admin.id)
    app_container.drug_import.commit(preview.batch_id, admin.id)

    result = app_container.catalog.list_drugs("002")
    batches = app_container.catalog.recent_batches()

    assert len(result) == 1
    assert result[0].display_name == "DIAZEPAM 2 MG"
    assert result[0].ingredients == ("diazepam",)
    assert batches[0].id == preview.batch_id
    assert batches[0].status == "COMMITTED"


@pytest.mark.integration
def test_updated_mapping_returns_to_pending_review(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source_v1 = write_drug_workbook(
        tmp_path / "master-v1.xlsx", drugs, components
    )
    first = app_container.drug_import.preview(source_v1, admin.id)
    app_container.drug_import.commit(first.batch_id, admin.id)
    app_container.drug_import.approve_batch(first.batch_id, admin.id)

    for row in drugs:
        row[0] = "DDI-TEST-v2"
        row[7] = "updated_clinical_mapping"
    for row in components:
        row[0] = "DDI-TEST-v2"
        row[6] = "updated_clinical_mapping"
    drugs[0][9] = 11
    source_v2 = write_drug_workbook(
        tmp_path / "master-v2.xlsx", drugs, components
    )

    second = app_container.drug_import.preview(source_v2, admin.id)
    restored = app_container.drug_import.get_preview(second.batch_id)
    counts = app_container.drug_import.commit(second.batch_id, admin.id)
    summary = app_container.catalog.summary()

    assert restored.batch_id == second.batch_id
    assert counts["updated"] >= 1
    assert counts["unchanged"] >= 1
    assert summary.pending_review == 2
    assert summary.active_components == 0


@pytest.mark.integration
def test_component_csv_can_update_existing_drug(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    initial = write_drug_workbook(
        tmp_path / "initial.xlsx", drugs, components
    )
    first = app_container.drug_import.preview(initial, admin.id)
    app_container.drug_import.commit(first.batch_id, admin.id)
    app_container.drug_import.approve_batch(first.batch_id, admin.id)

    component_csv = tmp_path / "DRUG_COMPONENT_MAP.csv"
    with component_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "database_version",
                "khanza_code",
                "khanza_name_display",
                "component_order",
                "standard_active_ingredient",
                "mapping_status",
                "mapping_method",
            ]
        )
        writer.writerow(
            [
                "DDI-TEST-v3",
                "001",
                "OBAT KOMBINASI",
                1,
                "paracetamol",
                "MAPPED",
                "manual_revision",
            ]
        )

    preview = app_container.drug_import.preview(component_csv, admin.id)
    app_container.drug_import.commit(preview.batch_id, admin.id)
    result = app_container.catalog.list_drugs("001")[0]

    assert preview.commit_allowed
    assert result.ingredients == ("paracetamol",)
    assert result.review_status == "PENDING_REVIEW"


@pytest.mark.integration
def test_invalid_row_reports_multiple_validation_errors(
    tmp_path, app_container
):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    drugs[0][0] = ""
    drugs[0][5] = -1
    drugs[0][6] = "UNKNOWN_STATUS"
    drugs[0][7] = ""
    drugs[0][9] = "bukan angka"
    source = write_drug_workbook(
        tmp_path / "many-errors.xlsx", drugs, components
    )

    preview = app_container.drug_import.preview(source, admin.id)
    messages = " ".join(issue.message for issue in preview.issues)

    assert preview.invalid_rows > 0
    assert "database_version wajib diisi" in messages
    assert "mapping_status tidak valid" in messages
    assert "mapping_method wajib diisi" in messages
    assert "rx_row_count harus berupa bilangan bulat" in messages


@pytest.mark.integration
def test_approval_requires_committed_batch(tmp_path, app_container):
    admin = _admin(app_container)
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)
    preview = app_container.drug_import.preview(source, admin.id)

    with pytest.raises(ImportStateError, match="COMMITTED"):
        app_container.drug_import.approve_batch(preview.batch_id, admin.id)

    with app_container.database.session() as session:
        batch = session.get(ImportBatch, preview.batch_id)
        assert batch.status == "PREVIEWED"
