from __future__ import annotations

from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text

from emss import __version__
from emss.audit.service import AuditService
from emss.config.settings import AppEnvironment, AppSettings
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser
from emss.database.models import Role
from emss.security.passwords import PasswordService
from emss.services.clinical_validation import ClinicalValidationService
from emss.services.users import UserService
from emss.utils.time import utc_now


@pytest.mark.integration
def test_migration_seeds_roles_and_sqlite_pragmas(app_container):
    assert app_container.database.current_revision() == "0029_kfa_identity"

    with app_container.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Role)) == 10
        role_codes = set(session.scalars(select(Role.code)).all())

    assert {"SUPER_ADMIN", "IT_ADMIN", "APOTEKER", "KFT"} <= role_codes

    with app_container.database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert (
            str(connection.execute(text("PRAGMA journal_mode")).scalar_one()).upper()
            == "WAL"
        )
        assert (
            connection.execute(text("PRAGMA busy_timeout")).scalar_one()
            == app_container.settings.sqlite_busy_timeout_ms
        )


@pytest.mark.integration
def test_migration_is_idempotent(app_container):
    app_container.database.migrate()
    app_container.database.migrate()

    assert app_container.database.current_revision() == "0029_kfa_identity"


@pytest.mark.integration
def test_upgrade_from_sprint1_preserves_existing_user(tmp_path):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "upgrade-data",
        log_level="ERROR",
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    try:
        database.migrate("0001_sprint1")
        users = UserService(database, PasswordService(), AuditService())
        created = users.create_first_admin(
            username="existing.admin",
            display_name="Existing Admin",
            password="Frasa aman existing admin!",
        )

        database.migrate()

        with database.session() as session:
            preserved = session.get(AppUser, created.id)
            assert preserved is not None
            assert preserved.username == "existing.admin"
        assert database.current_revision() == "0029_kfa_identity"
    finally:
        database.dispose()


@pytest.mark.integration
def test_upgrade_from_sprint10_keeps_legacy_signoff_but_closes_gate(tmp_path):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "upgrade-sprint10-data",
        log_level="ERROR",
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    audit = AuditService()
    try:
        database.migrate("0009_sprint10")
        users = UserService(database, PasswordService(), audit)
        admin = users.create_first_admin(
            username="legacy.uat.admin",
            display_name="Legacy UAT Admin",
            password="Frasa aman legacy UAT!",
        )
        timestamp = utc_now().isoformat()
        with database.session() as session:
            session.execute(
                text(
                    "INSERT INTO uat_session ("
                    "id, name, status, pharmacist_approved, "
                    "pharmacist_approved_by, pharmacist_approved_at, "
                    "it_approved, it_approved_by, it_approved_at, notes, "
                    "created_by, created_at, updated_at"
                    ") VALUES ("
                    ":id, :name, 'APPROVED', 1, :actor, :approved_at, "
                    "1, :actor, :approved_at, NULL, :actor, :created_at, "
                    ":updated_at)"
                ),
                {
                    "id": "legacy-uat-session",
                    "name": "Legacy UAT",
                    "actor": admin.id,
                    "approved_at": timestamp,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
            session.commit()

        database.migrate()

        with database.session() as session:
            legacy = session.execute(
                text(
                    "SELECT pharmacist_approved, "
                    "pharmacist_approved_version, it_approved, "
                    "it_approved_version FROM uat_session "
                    "WHERE id = 'legacy-uat-session'"
                )
            ).one()
            assert legacy.pharmacist_approved
            assert legacy.it_approved
            assert legacy.pharmacist_approved_version is None
            assert legacy.it_approved_version is None

        gate = ClinicalValidationService(database, audit).evaluate_gate()
        assert not gate.pharmacist_approved
        assert not gate.it_approved
        assert (
            f"Persetujuan UAT Apoteker bukan untuk versi aplikasi {__version__}"
            in gate.blockers
        )
        assert (
            f"Persetujuan UAT IT bukan untuk versi aplikasi {__version__}"
            in gate.blockers
        )
        assert database.current_revision() == "0029_kfa_identity"
    finally:
        database.dispose()


@pytest.mark.integration
def test_shift_closeout_migration_can_rollback_without_losing_legacy_data(
    tmp_path,
):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "rollback-closeout-data",
        log_level="ERROR",
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    try:
        database.migrate("0015_two_person_advisory")
        users = UserService(database, PasswordService(), AuditService())
        created = users.create_first_admin(
            username="rollback.admin",
            display_name="Rollback Admin",
            password="Rollback#Aman2026",
        )
        timestamp = utc_now().isoformat()
        expires_at = (utc_now() + timedelta(hours=8)).isoformat()
        with database.session() as session:
            session.execute(
                text(
                    "INSERT INTO validation_campaign "
                    "(id, name, phase, status, created_by, created_at, updated_at) "
                    "VALUES ('legacy-campaign', 'Legacy Campaign', "
                    "'CLINICAL_VALIDATION', 'READY', :actor, :now, :now)"
                ),
                {"actor": created.id, "now": timestamp},
            )
            session.execute(
                text(
                    "INSERT INTO uat_session "
                    "(id, name, status, created_by, created_at, updated_at) "
                    "VALUES ('legacy-uat', 'Legacy UAT', 'APPROVED', "
                    ":actor, :now, :now)"
                ),
                {"actor": created.id, "now": timestamp},
            )
            session.execute(
                text(
                    "INSERT INTO advisory_pilot_activation "
                    "(id, status, application_version, validation_campaign_id, "
                    "uat_session_id, pharmacist_approved_at, it_approved_at, "
                    "activated_by, activated_at, expires_at, clinical_owner_id, "
                    "technical_authorizer_id, authorization_request_id) "
                    "VALUES ('legacy-activation', 'ACTIVE', '0.18.0', "
                    "'legacy-campaign', 'legacy-uat', :now, :now, :actor, :now, "
                    ":expires, :actor, :actor, 'legacy-request')"
                ),
                {
                    "actor": created.id,
                    "now": timestamp,
                    "expires": expires_at,
                },
            )
            session.commit()
        database.migrate()
        assert database.current_revision() == "0029_kfa_identity"
        tables = set(inspect(database.engine).get_table_names())
        assert "advisory_pilot_session_ledger" in tables
        assert "advisory_pilot_shift_closeout" in tables
        assert "pilot_evidence_verification" in tables
        safety_columns = {
            column["name"]
            for column in inspect(database.engine).get_columns(
                "advisory_pilot_safety_control"
            )
        }
        assert "ledger_quarantine" in safety_columns
        with database.engine.connect() as connection:
            backfilled = connection.execute(
                text(
                    "SELECT shift_started_at, shift_expires_at "
                    "FROM advisory_pilot_activation "
                    "WHERE id = 'legacy-activation'"
                )
            ).one()
            assert backfilled.shift_started_at is not None
            assert backfilled.shift_expires_at is not None

        command.downgrade(
            database._alembic_config(), "0015_two_person_advisory"
        )
        assert database.current_revision() == "0015_two_person_advisory"
        inspector = inspect(database.engine)
        tables = set(inspector.get_table_names())
        assert "advisory_pilot_session_ledger" not in tables
        assert "advisory_pilot_shift_closeout" not in tables
        assert "pilot_evidence_verification" not in tables
        activation_columns = {
            column["name"]
            for column in inspector.get_columns("advisory_pilot_activation")
        }
        assert "shift_started_at" not in activation_columns
        assert "shift_expires_at" not in activation_columns
        safety_columns = {
            column["name"]
            for column in inspector.get_columns(
                "advisory_pilot_safety_control"
            )
        }
        assert "ledger_quarantine" not in safety_columns
        with database.session() as session:
            preserved = session.get(AppUser, created.id)
            assert preserved is not None
            assert preserved.username == "rollback.admin"
            activation = session.execute(
                text(
                    "SELECT status, application_version "
                    "FROM advisory_pilot_activation "
                    "WHERE id = 'legacy-activation'"
                )
            ).one()
            assert activation.status == "ACTIVE"
            assert activation.application_version == "0.18.0"

        database.migrate()
        assert database.current_revision() == "0029_kfa_identity"
    finally:
        database.dispose()


@pytest.mark.integration
def test_evidence_verification_migration_rolls_back_without_legacy_loss(
    tmp_path,
):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "rollback-evidence-data",
        log_level="ERROR",
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    try:
        database.migrate("0017_pilot_ledger_quarantine")
        users = UserService(database, PasswordService(), AuditService())
        created = users.create_first_admin(
            username="rollback.evidence",
            display_name="Rollback Evidence",
            password="Rollback#Evidence2026",
        )
        database.migrate()
        assert database.current_revision() == "0029_kfa_identity"
        now = utc_now().isoformat()
        with database.session() as session:
            session.execute(
                text(
                    "INSERT INTO pilot_evidence_verification "
                    "(id, package_filename, package_checksum_sha256, outcome, "
                    "errors_json, verified_by, verified_at) VALUES "
                    "('verification-rollback', 'legacy.zip', :checksum, "
                    "'VALID', '[]', :actor, :now)"
                ),
                {"checksum": "a" * 64, "actor": created.id, "now": now},
            )
            session.commit()

        command.downgrade(
            database._alembic_config(), "0017_pilot_ledger_quarantine"
        )
        assert database.current_revision() == "0017_pilot_ledger_quarantine"
        assert "pilot_evidence_verification" not in set(
            inspect(database.engine).get_table_names()
        )
        with database.session() as session:
            preserved = session.get(AppUser, created.id)
            assert preserved.username == "rollback.evidence"

        database.migrate()
        assert database.current_revision() == "0029_kfa_identity"
        assert "pilot_evidence_verification" in set(
            inspect(database.engine).get_table_names()
        )
    finally:
        database.dispose()


