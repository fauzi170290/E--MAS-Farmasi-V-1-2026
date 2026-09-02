from __future__ import annotations

import json

import pytest

from emss.services.backup import BackupError


def _admin(container):
    return container.users.create_first_admin(
        username="admin.backup",
        display_name="Admin Backup",
        password="Frasa aman backup!",
    )


@pytest.mark.integration
def test_manual_backup_has_checksum_manifest_config_and_audit(app_container):
    admin = _admin(app_container)

    record = app_container.backup.create_backup("MANUAL", admin.id)
    verified = app_container.backup.verify_backup(record.database_path, admin.id)
    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))

    assert record.database_path.is_file()
    assert record.config_snapshot_path is not None
    assert record.config_snapshot_path.is_file()
    assert verified.checksum_sha256 == record.checksum_sha256
    assert manifest["reason"] == "MANUAL"
    assert manifest["integrity_ok"] is True
    assert manifest["schema_revision"] == "0029_kfa_identity"


@pytest.mark.integration
def test_daily_backup_is_idempotent_for_same_day(app_container):
    _admin(app_container)

    first = app_container.backup.create_daily_if_due()
    second = app_container.backup.create_daily_if_due()

    assert first is not None
    assert second is None
    assert [row.reason for row in app_container.backup.list_backups()] == ["DAILY"]


@pytest.mark.integration
def test_checksum_mismatch_blocks_restore(app_container):
    admin = _admin(app_container)
    record = app_container.backup.create_backup("MANUAL", admin.id)
    with record.database_path.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(BackupError, match="Checksum"):
        app_container.backup.restore_backup(record.database_path, admin.id)


@pytest.mark.integration
def test_restore_drill_recovers_previous_database_and_keeps_audit_valid(
    app_container,
):
    admin = _admin(app_container)
    record = app_container.backup.create_backup("MANUAL", admin.id)
    app_container.users.create_user(
        username="temporary.user",
        display_name="Temporary User",
        password="Frasa aman temporary!",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    assert app_container.users.count_users() == 2

    result = app_container.backup.restore_backup(record.database_path, admin.id)

    assert result.restart_required
    assert result.safety_backup.is_file()
    assert app_container.users.count_users() == 1
    with app_container.database.session() as session:
        assert app_container.audit.verify_chain(session)


