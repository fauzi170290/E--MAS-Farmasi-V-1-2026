from __future__ import annotations

import pytest

from emss.database.models import AuditLog
from emss.health.service import HealthState


@pytest.mark.integration
def test_health_is_ready_after_migration(app_container):
    result = app_container.health.check()

    assert result.state is HealthState.READY
    assert result.database_connected
    assert result.schema_revision == "0029_kfa_identity"
    assert result.foreign_keys_enabled
    assert result.journal_mode == "WAL"
    assert result.audit_chain_valid
    assert result.khanza_connection == "NOT_CONFIGURED"
    assert result.details == ()


@pytest.mark.integration
def test_health_detects_tampered_audit(app_container):
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password="Frasa aman untuk admin 2026!",
    )
    with app_container.database.session() as session:
        row = session.query(AuditLog).first()
        row.details_json = '{"tampered":true}'
        session.commit()

    result = app_container.health.check()

    assert result.state is HealthState.ERROR
    assert not result.audit_chain_valid
    assert "Rantai audit tidak valid" in result.details


