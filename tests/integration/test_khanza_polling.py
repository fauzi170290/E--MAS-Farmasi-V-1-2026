from __future__ import annotations

from emss.config.settings import KhanzaAdapterMode
from emss.integrations.khanza import MockKhanzaAdapter
from emss.services.khanza_polling import KhanzaPollingService


def _mock_service(app_container) -> KhanzaPollingService:
    app_container.settings.khanza_adapter = KhanzaAdapterMode.MOCK
    adapter = MockKhanzaAdapter()
    return KhanzaPollingService(
        app_container.database,
        app_container.settings,
        adapter,
        app_container.screening,
        app_container.queue,
        sleeper=lambda _seconds: None,
    )


def test_mock_polling_without_knowledge_base_never_marks_failure_safe(app_container):
    actor = app_container.users.create_first_admin(
        username="admin.poll",
        display_name="Admin Poll",
        password="Frasa aman polling 2026!",
    )
    service = _mock_service(app_container)
    no_resep = service.seed_mock_prescription()

    result = service.poll_once(actor.id, force=True)

    assert result.status in {"SUCCESS", "PARTIAL"}
    assert result.detected == 1
    assert result.stable == 1
    assert result.processed == 0
    assert result.failed == 1
    item = app_container.queue.list_items(search=no_resep)[0]
    assert item.completeness_status == "ERROR"
    assert item.risk_status == "SAFE"
    assert item.overall_status == "ERROR"


def test_disconnect_records_backoff_without_queueing_safe(app_container):
    actor = app_container.users.create_first_admin(
        username="admin.disconnect",
        display_name="Admin Disconnect",
        password="Frasa aman disconnect 2026!",
    )
    service = _mock_service(app_container)
    adapter = service.adapter
    assert isinstance(adapter, MockKhanzaAdapter)
    adapter.set_connected(False)

    result = service.poll_once(actor.id, force=True)

    assert result.status == "DISCONNECTED"
    assert service.status().connection_status == "DISCONNECTED"
    assert app_container.queue.summary().total == 0
