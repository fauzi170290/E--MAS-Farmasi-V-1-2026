from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from emss.audit.service import AuditService
from emss.config.settings import AppEnvironment, AppSettings
from emss.database.engine import DatabaseManager
from emss.security.passwords import PasswordService
from emss.services.bundled_ddi import (
    BUNDLE_ID,
    EXPECTED_BUNDLE_SHA256,
    EXPECTED_INGREDIENT_COUNT,
    EXPECTED_RULE_COUNT,
    EXPECTED_SEMANTIC_SHA256,
    BundledDdiSeedService,
)
from emss.services.users import UserService


def test_mapping_bundle_loads_counts_preserves_review_and_does_not_recreate_user_deletions(app_container):
    from sqlalchemy import select
    from emss.database.catalog_models import DrugMaster, DrugComponentMapping
    admin = _admin(app_container)
    app_container.bundled_ddi.apply_if_eligible(admin.id)
    result = app_container.bundled_mapping.apply_if_eligible(admin.id)
    assert (result.status, result.inserted, result.component_count) == ('APPLIED', 414, 444)
    with app_container.database.session() as session:
        assert session.execute(text('SELECT COUNT(*) FROM drug_master')).scalar_one() == 414
        assert session.execute(text("SELECT COUNT(*) FROM drug_master WHERE review_status != 'PENDING_REVIEW'")).scalar_one() == 0
        assert session.execute(text('SELECT COUNT(*) FROM drug_component_mapping WHERE is_active = 1')).scalar_one() == 0
        row = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == '000001074'))
        assert json.loads(row.mapping_note)['clinical_approval'] is False
        assert json.loads(row.mapping_note)['strength_mg'] is None
        row.display_name = 'Koreksi pengguna tetap ada'
        other = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code != row.khanza_code))
        session.delete(other)
        session.commit()
    assert app_container.bundled_mapping.apply_if_eligible(admin.id).status == 'ALREADY_APPLIED'
    with app_container.database.session() as session:
        assert session.execute(text('SELECT COUNT(*) FROM drug_master')).scalar_one() == 413
        assert session.scalar(select(DrugMaster.display_name).where(DrugMaster.khanza_code == '000001074')) == 'Koreksi pengguna tetap ada'


def test_mapping_upgrade_keeps_existing_code_and_source_status(app_container):
    from sqlalchemy import select
    from emss.database.catalog_models import DrugMaster
    admin = _admin(app_container)
    with app_container.database.session() as session:
        session.add(DrugMaster(khanza_code='000001074', display_name='Obat versi pengguna', normalized_name='obat versi pengguna',
            source_version='USER', source_mapping_status='UNMAPPED', review_status='APPROVED', mapping_method='USER', component_count=0))
        session.commit()
    result = app_container.bundled_mapping.apply_if_eligible(admin.id)
    assert result.inserted == 413 and result.preserved == 1
    with app_container.database.session() as session:
        row = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == '000001074'))
        assert (row.display_name, row.review_status, row.source_mapping_status) == ('Obat versi pengguna', 'APPROVED', 'UNMAPPED')


def test_mapping_bundle_rejects_tampering_and_defers_without_admin(app_container, tmp_path):
    from emss.services.bundled_mapping import _read_bundle, BUNDLE_FILE, MANIFEST_FILE, BundledMappingError
    from emss.utils.resources import bundled_resource
    assert app_container.bundled_mapping.apply_if_eligible().status == 'DEFERRED_NO_ADMIN'
    folder = tmp_path / 'seed'; folder.mkdir()
    for name in (BUNDLE_FILE, MANIFEST_FILE): (folder/name).write_bytes((bundled_resource('seed')/name).read_bytes())
    (folder/BUNDLE_FILE).write_bytes(b'invalid')
    with pytest.raises(BundledMappingError, match='Checksum'):
        _read_bundle(folder)


def _admin(container):
    return container.users.create_first_admin(
        username="admin.seed",
        display_name="Admin Seed DDI",
        password="Seed#Aman2026",
    )


@pytest.mark.integration
def test_bundled_ddi_seed_is_exact_draft_audited_and_idempotent(app_container):
    admin = _admin(app_container)

    applied = app_container.bundled_ddi.apply_if_eligible(admin.id)
    repeated = app_container.bundled_ddi.apply_if_eligible(admin.id)

    assert applied.status == "APPLIED"
    assert applied.bundle_id == BUNDLE_ID
    assert applied.rule_count == EXPECTED_RULE_COUNT
    assert applied.ingredient_count == EXPECTED_INGREDIENT_COUNT
    assert repeated.status == "ALREADY_APPLIED"
    assert repeated.knowledge_base_version_id == applied.knowledge_base_version_id

    with app_container.database.session() as session:
        version = session.execute(
            text(
                "SELECT version_code, status, source_checksum "
                "FROM knowledge_base_version"
            )
        ).one()
        assert version.version_code == BUNDLE_ID
        assert version.status == "DRAFT"
        assert session.execute(text("SELECT COUNT(*) FROM ddi_rule")).scalar_one() == 5432
        assert session.execute(text("SELECT COUNT(*) FROM active_ingredient")).scalar_one() == 159
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE is_enabled = 1")
        ).scalar_one() == 0
        assert dict(
            session.execute(
                text(
                    "SELECT app_severity, COUNT(*) total FROM ddi_rule "
                    "GROUP BY app_severity"
                )
            ).all()
        ) == {None: 4867, "CRITICAL": 4, "HIGH_RISK": 55, "INFO": 102, "REVIEW": 404}
        ledger = session.execute(
            text(
                "SELECT bundle_checksum_sha256, semantic_checksum_sha256, "
                "rule_count, ingredient_count FROM bundled_ddi_seed_application"
            )
        ).one()
        assert ledger.bundle_checksum_sha256 == EXPECTED_BUNDLE_SHA256
        assert ledger.semantic_checksum_sha256 == EXPECTED_SEMANTIC_SHA256
        assert ledger.rule_count == 5432
        assert ledger.ingredient_count == 159
        audit = session.execute(
            text(
                "SELECT details_json FROM audit_log "
                "WHERE action = 'BUNDLED_DDI_SEED'"
            )
        ).one()
        details = json.loads(audit.details_json)
        assert details["patient_identity_included"] is False
        assert details["user_accounts_included"] is False

        for statement in (
            "UPDATE bundled_ddi_seed_application SET rule_count = 1",
            "DELETE FROM bundled_ddi_seed_application",
        ):
            with pytest.raises(DatabaseError):
                session.execute(text(statement))
            session.rollback()


@pytest.mark.integration
def test_bundled_seed_defers_without_admin_and_merges_beside_existing_master(app_container):
    deferred = app_container.bundled_ddi.apply_if_eligible()
    assert deferred.status == "DEFERRED_NO_ADMIN"
    admin = _admin(app_container)
    app_container.knowledge.create_version(
        "LOCAL-VALIDATED-v2",
        "Master lokal yang harus dipertahankan",
        admin.id,
        source_checksum="a" * 64,
    )

    merged = app_container.bundled_ddi.apply_if_eligible(admin.id)

    assert merged.status == "APPLIED_ALONGSIDE_EXISTING_MASTER"
    with app_container.database.session() as session:
        assert session.execute(
            text("SELECT COUNT(*) FROM knowledge_base_version")
        ).scalar_one() == 2
        assert session.execute(text("SELECT COUNT(*) FROM ddi_rule")).scalar_one() == 5432
        assert session.execute(
            text("SELECT COUNT(*) FROM bundled_ddi_seed_application")
        ).scalar_one() == 1
        assert session.execute(text(
            "SELECT COUNT(*) FROM knowledge_base_version WHERE version_code='LOCAL-VALIDATED-v2'"
        )).scalar_one() == 1


@pytest.mark.integration
def test_bundled_seed_reuses_existing_ingredient_without_overwriting(app_container):
    admin = _admin(app_container)
    with app_container.database.session() as session:
        first = json.loads(
            gzip.decompress(
                (Path(__file__).resolve().parents[2]
                 / "seed/ddi-khanza-v1.0.0.json.gz").read_bytes()
            )
        )["ingredients"][0]
        session.execute(
            text(
                "INSERT INTO active_ingredient "
                "(id, standard_name, normalized_name, is_active, created_at, updated_at) "
                "VALUES ('preexisting-ingredient', :standard, :normalized, 1, :created, :updated)"
            ),
            {
                "standard": first["standard_name"],
                "normalized": first["normalized_name"],
                "created": first["created_at"],
                "updated": first["updated_at"],
            },
        )
        session.commit()

    result = app_container.bundled_ddi.apply_if_eligible(admin.id)

    assert result.status == "APPLIED"
    assert result.reused_ingredient_count == 1
    with app_container.database.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM active_ingredient")).scalar_one() == 159
        assert session.execute(
            text(
                "SELECT COUNT(*) FROM ddi_rule WHERE "
                "ingredient_low_id = 'preexisting-ingredient' OR "
                "ingredient_high_id = 'preexisting-ingredient'"
            )
        ).scalar_one() > 0


@pytest.mark.integration
def test_seed_provenance_migration_rolls_back_and_reupgrades_without_data_loss(tmp_path):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "seed-rollback",
        log_level="ERROR",
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    try:
        database.migrate()
        admin = UserService(database, PasswordService(), AuditService()).create_first_admin(
            username="rollback.seed",
            display_name="Rollback Seed",
            password="Rollback#Seed2026",
        )
        service = BundledDdiSeedService(database, AuditService())
        assert service.apply_if_eligible(admin.id).status == "APPLIED"

        command.downgrade(database._alembic_config(), "0025_uat_execution_acceptance")
        assert database.current_revision() == "0025_uat_execution_acceptance"
        assert "bundled_ddi_seed_application" not in set(
            inspect(database.engine).get_table_names()
        )
        with database.session() as session:
            assert session.execute(text("SELECT COUNT(*) FROM ddi_rule")).scalar_one() == 5432

        database.migrate()
        assert database.current_revision() == "0029_kfa_identity"
        assert "bundled_ddi_seed_application" in set(
            inspect(database.engine).get_table_names()
        )
        assert service.apply_if_eligible(admin.id).status == "RECOVERED_EXISTING_BUNDLE"
        with database.session() as session:
            assert session.execute(text("SELECT COUNT(*) FROM ddi_rule")).scalar_one() == 5432
    finally:
        database.dispose()


@pytest.mark.integration
def test_existing_bundle_ledger_detects_pair_identity_tampering_but_preserves_reviews(app_container):
    admin = _admin(app_container)
    app_container.bundled_ddi.apply_if_eligible(admin.id)
    with app_container.database.session() as session:
        session.execute(text("UPDATE ddi_rule SET clinical_effect='hasil review KFT' WHERE id=(SELECT id FROM ddi_rule LIMIT 1)"))
        session.commit()
    assert app_container.bundled_ddi.apply_if_eligible(admin.id).status == "ALREADY_APPLIED"
    with app_container.database.session() as session:
        session.execute(text("UPDATE ddi_rule SET pair_key='pair asing' WHERE id=(SELECT id FROM ddi_rule LIMIT 1)"))
        session.commit()
    from emss.services.bundled_ddi import BundledDdiSeedError
    with pytest.raises(BundledDdiSeedError, match="Pair asing"):
        app_container.bundled_ddi.apply_if_eligible(admin.id)


