from __future__ import annotations

from datetime import UTC, datetime, timedelta

from emss.integrations.khanza import (
    KhanzaCursor,
    MockKhanzaAdapter,
    PrescriptionHeader,
    PrescriptionItem,
    PrescriptionSnapshot,
    read_snapshot,
)
from emss.services.khanza_polling import exponential_backoff


def _snapshot(no_resep: str, changed_at: datetime, revision: str = "1"):
    return PrescriptionSnapshot(
        header=PrescriptionHeader(
            no_resep=no_resep,
            no_rawat="R-1",
            service_unit="DEPO",
            changed_at=changed_at,
        ),
        regular_items=(PrescriptionItem("1", "OBAT-1", "Obat 1"),),
        compounded_items=(),
        revision=revision,
    )


def test_mock_adapter_uses_time_and_prescription_cursor():
    adapter = MockKhanzaAdapter()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    adapter.add_snapshot(_snapshot("RX-002", now))
    adapter.add_snapshot(_snapshot("RX-001", now))
    adapter.add_snapshot(_snapshot("RX-003", now + timedelta(seconds=1)))

    first = adapter.get_new_prescriptions(None, 2)
    second = adapter.get_new_prescriptions(first[-1].cursor, 2)

    assert [row.no_resep for row in first] == ["RX-001", "RX-002"]
    assert [row.no_resep for row in second] == ["RX-003"]
    assert read_snapshot(adapter, "RX-001").items[0].khanza_code == "OBAT-1"


def test_exponential_backoff_is_bounded():
    assert [exponential_backoff(i, 5, 60) for i in range(1, 6)] == [5, 10, 20, 40, 60]


def test_cursor_normalizes_naive_datetime_to_utc():
    cursor = KhanzaCursor(datetime(2026, 8, 3), "RX-1")
    assert cursor.changed_at.tzinfo is UTC
