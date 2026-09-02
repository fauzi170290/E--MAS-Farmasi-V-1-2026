"""Exercise shipped reference bundles and their upgrade path on disposable data."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from sqlalchemy import select, text

from emss.app import build_application
from emss.config.settings import AppSettings
from emss.database.catalog_models import DrugMaster
from emss.database.engine import DatabaseManager
from emss.services.bundled_ddi import BUNDLE_ID, verify_bundled_ddi_seed
from emss.services.bundled_mapping import _read_bundle


def run_bundle_smoke() -> dict[str, object]:
    """Prove clean seed plus recovery from a pre-ledger upgrade.

    Only a temporary SQLite database is used. The drill deliberately removes the
    bundle ledger through its supported migration downgrade, then starts the
    current application so migration and H1 recovery run exactly as on upgrade.
    """

    try:
        ddi_manifest, _ = verify_bundled_ddi_seed()
        mapping_manifest, _, _ = _read_bundle()
        with TemporaryDirectory(prefix="emas-reference-smoke-") as temp:
            root = Path(temp)
            settings = AppSettings(
                environment="production",
                data_dir=root,
                khanza_adapter="disabled",
                khanza_polling_enabled=False,
                backup_daily_enabled=False,
            )
            container = build_application(settings)
            try:
                admin = container.users.create_first_admin(
                    username="smoke.dummy",
                    display_name="Uji Data Referensi",
                    password="Dummy#BundleSmoke2026",
                )
                admin_id = admin.id
                local_version = container.knowledge.create_version(
                    "LOCAL-SMOKE-v1",
                    "Master lokal sentinel upgrade",
                    admin.id,
                    source_checksum="a" * 64,
                )
                ddi_result = container.bundled_ddi.apply_if_eligible(admin.id)
                mapping_result = container.bundled_mapping.apply_if_eligible(admin.id)
                with container.database.session() as session:
                    counts_before = {
                        table: session.execute(
                            text(f"SELECT COUNT(*) FROM {table}")
                        ).scalar_one()
                        for table in (
                            "ddi_rule",
                            "drug_master",
                            "drug_component_mapping",
                        )
                    }
                    enabled_before = session.execute(
                        text("SELECT COUNT(*) FROM ddi_rule WHERE is_enabled=1")
                    ).scalar_one()
                    approved_before = session.execute(
                        text(
                            "SELECT COUNT(*) FROM drug_master "
                            "WHERE review_status != 'PENDING_REVIEW'"
                        )
                    ).scalar_one()
                    bundled = session.execute(
                        text(
                            "SELECT id FROM knowledge_base_version "
                            "WHERE version_code=:code"
                        ),
                        {"code": BUNDLE_ID},
                    ).scalar_one()
                    reviewed_rule = session.execute(
                        text(
                            "SELECT id FROM ddi_rule "
                            "WHERE knowledge_base_version_id=:version "
                            "ORDER BY pair_key LIMIT 1"
                        ),
                        {"version": bundled},
                    ).scalar_one()
                    session.execute(
                        text(
                            "UPDATE ddi_rule SET clinical_effect=:value, notes=:notes "
                            "WHERE id=:rule"
                        ),
                        {
                            "value": "Koreksi klinis sentinel upgrade",
                            "notes": "Jangan ditimpa installer",
                            "rule": reviewed_rule,
                        },
                    )
                    drug = session.scalar(
                        select(DrugMaster).where(
                            DrugMaster.khanza_code == "000001074"
                        )
                    )
                    if drug is None:
                        raise ValueError("MAPPING_SENTINEL_MISSING")
                    drug.display_name = "Koreksi pengguna sentinel upgrade"
                    session.commit()
                (root / "config-sentinel.toml").write_bytes(
                    b"# konfigurasi pengguna tidak boleh ditimpa\n"
                )
                (root / "audio-preferences.json").write_bytes(
                    b'{"upgrade_sentinel":true}'
                )
            finally:
                container.close()

            # Simulate an older installation whose clinical catalog remains but
            # whose immutable bundle ledger did not yet exist.
            legacy_database = DatabaseManager(settings)
            try:
                command.downgrade(
                    legacy_database._alembic_config(),
                    "0025_uat_execution_acceptance",
                )
            finally:
                legacy_database.dispose()

            upgraded = build_application(settings)
            try:
                with upgraded.database.session() as session:
                    counts_after = {
                        table: session.execute(
                            text(f"SELECT COUNT(*) FROM {table}")
                        ).scalar_one()
                        for table in (
                            "ddi_rule",
                            "drug_master",
                            "drug_component_mapping",
                        )
                    }
                    recovered_ledger = session.execute(
                        text(
                            "SELECT COUNT(*) FROM bundled_ddi_seed_application "
                            "WHERE bundle_id=:code"
                        ),
                        {"code": BUNDLE_ID},
                    ).scalar_one()
                    local_preserved = session.execute(
                        text(
                            "SELECT COUNT(*) FROM knowledge_base_version "
                            "WHERE id=:version AND version_code='LOCAL-SMOKE-v1'"
                        ),
                        {"version": local_version},
                    ).scalar_one() == 1
                    review_preserved = session.execute(
                        text(
                            "SELECT clinical_effect, notes FROM ddi_rule "
                            "WHERE id=:rule"
                        ),
                        {"rule": reviewed_rule},
                    ).one() == (
                        "Koreksi klinis sentinel upgrade",
                        "Jangan ditimpa installer",
                    )
                    mapping_preserved = (
                        session.scalar(
                            select(DrugMaster.display_name).where(
                                DrugMaster.khanza_code == "000001074"
                            )
                        )
                        == "Koreksi pengguna sentinel upgrade"
                    )
                    bundle_status = session.execute(
                        text(
                            "SELECT status FROM knowledge_base_version "
                            "WHERE version_code=:code"
                        ),
                        {"code": BUNDLE_ID},
                    ).scalar_one()
                files_preserved = (
                    (root / "config-sentinel.toml").read_bytes()
                    == b"# konfigurasi pengguna tidak boleh ditimpa\n"
                    and (root / "audio-preferences.json").read_bytes()
                    == b'{"upgrade_sentinel":true}'
                )
                valid = (
                    ddi_result.status == "APPLIED_ALONGSIDE_EXISTING_MASTER"
                    and mapping_result.status == "APPLIED"
                    and counts_before
                    == counts_after
                    == {
                        "ddi_rule": 5432,
                        "drug_master": 414,
                        "drug_component_mapping": 444,
                    }
                    and enabled_before == approved_before == 0
                    and bundle_status == "DRAFT"
                    and recovered_ledger == 1
                    and local_preserved
                    and review_preserved
                    and mapping_preserved
                    and files_preserved
                    and upgraded.database.current_revision() == "0029_kfa_identity"
                )
                activation = upgraded.h3_activation.activate(
                    admin_id, "Validasi KFT sintetis frozen binary H3"
                )
                with upgraded.database.session() as session:
                    h3_active_ddi = session.execute(
                        text(
                            "SELECT COUNT(*) FROM ddi_rule WHERE "
                            "knowledge_base_version_id=:version AND is_enabled=1 "
                            "AND activation_status='ACTIVE'"
                        ),
                        {"version": activation.version_id},
                    ).scalar_one()
                    h3_approved_mappings = session.execute(
                        text(
                            "SELECT COUNT(*) FROM drug_master "
                            "WHERE review_status='APPROVED'"
                        )
                    ).scalar_one()
                valid = (
                    valid
                    and activation.active_pairs == 379
                    and activation.held_pairs == 175
                    and activation.draft_pairs == 11
                    and h3_active_ddi == 379
                    and h3_approved_mappings == 414
                )
                return {
                    "state": "READY" if valid else "ERROR",
                    "counts": counts_after,
                    "ddi_status": bundle_status,
                    "enabled_ddi": enabled_before,
                    "non_pending_mappings": approved_before,
                    "h3_active_ddi": h3_active_ddi,
                    "h3_approved_mappings": h3_approved_mappings,
                    "h3_held_ddi": activation.held_pairs,
                    "h3_draft_ddi": activation.draft_pairs,
                    "schema_revision": upgraded.database.current_revision(),
                    "ledger_recovered": recovered_ledger == 1,
                    "local_master_preserved": local_preserved,
                    "clinical_review_preserved": review_preserved,
                    "mapping_correction_preserved": mapping_preserved,
                    "user_files_preserved": files_preserved,
                    "ddi_sha256": ddi_manifest["bundle_sha256"],
                    "mapping_sha256": mapping_manifest["bundle_sha256"],
                    "operational_data_accessed": False,
                }
            finally:
                upgraded.close()
    except Exception as exc:
        return {"state": "ERROR", "error_type": type(exc).__name__}
