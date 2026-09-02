from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    create_engine,
)

from emss.config.settings import AppSettings
from emss.integrations.khanza import KhanzaCursor, MySQLKhanzaAdapter


def _contract_engine():
    sqlite3.register_converter(
        "DATETIME", lambda value: datetime.fromisoformat(value.decode("utf-8"))
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"detect_types": sqlite3.PARSE_DECLTYPES},
    )
    metadata = MetaData()
    header = Table(
        "vw_emss_prescription_header",
        metadata,
        Column("no_resep", String, primary_key=True),
        Column("no_rawat", String),
        Column("asal_layanan", String),
        Column("no_rm", String),
        Column("nama_pasien", String),
        Column("unit_depo", String),
        Column("dokter", String),
        Column("status_resep", String),
        Column("changed_at", DateTime),
    )
    item = Table(
        "vw_emss_prescription_item",
        metadata,
        Column("no_resep", String),
        Column("source_item_key", String),
        Column("kode_brng", String),
        Column("nama_brng", String),
        Column("jumlah", Float),
        Column("aturan_pakai", String),
        Column("rute", String),
    )
    compound = Table(
        "vw_emss_compound_item",
        metadata,
        Column("no_resep", String),
        Column("source_item_key", String),
        Column("kode_brng", String),
        Column("nama_brng", String),
        Column("jumlah", Float),
        Column("aturan_pakai", String),
        Column("rute", String),
        Column("no_racik", String),
    )
    drug = Table(
        "vw_emss_drug_master",
        metadata,
        Column("kode_brng", String, primary_key=True),
        Column("nama_brng", String),
        Column("aktif", Boolean),
    )
    metadata.create_all(engine)
    changed = datetime(2026, 8, 3, 8, 30)
    with engine.begin() as connection:
        connection.execute(
            header.insert(),
            [
                {
                    "no_resep": "RX-UJI-001",
                    "no_rawat": "RAWAT-UJI-001",
                    "asal_layanan": "ralan",
                    "no_rm": "RM-UJI",
                    "nama_pasien": "PASIEN SINTETIS",
                    "unit_depo": "POLI UJI",
                    "dokter": "DOKTER UJI",
                    "status_resep": "DIRESEPKAN",
                    "changed_at": changed,
                },
                {
                    "no_resep": "RX-UJI-002",
                    "no_rawat": "RAWAT-UJI-002",
                    "asal_layanan": "ranap",
                    "no_rm": "RM-UJI-2",
                    "nama_pasien": "PASIEN SINTETIS 2",
                    "unit_depo": "IGD UJI",
                    "dokter": "DOKTER UJI",
                    "status_resep": "DIPROSES_FARMASI",
                    "changed_at": changed + timedelta(seconds=1),
                },
            ],
        )
        connection.execute(
            item.insert(),
            {
                "no_resep": "RX-UJI-001",
                "source_item_key": "R:OBAT-A:UJI",
                "kode_brng": "OBAT-A",
                "nama_brng": "Obat Sintetis A",
                "jumlah": 2,
                "aturan_pakai": "ATURAN UJI",
                "rute": "",
            },
        )
        connection.execute(
            compound.insert(),
            {
                "no_resep": "RX-UJI-001",
                "source_item_key": "C:1:OBAT-B",
                "kode_brng": "OBAT-B",
                "nama_brng": "Obat Sintetis B",
                "jumlah": 1,
                "aturan_pakai": "ATURAN RACIKAN UJI",
                "rute": "",
                "no_racik": "1",
            },
        )
        connection.execute(
            drug.insert(),
            [
                {"kode_brng": "OBAT-A", "nama_brng": "Obat Sintetis A", "aktif": True},
                {"kode_brng": "OBAT-X", "nama_brng": "Obat Nonaktif", "aktif": False},
            ],
        )
    return engine, changed


def test_mysql_adapter_reads_the_four_view_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("EMSS_KHANZA_PASSWORD", "hanya-untuk-test-sintetis")
    engine, changed = _contract_engine()
    adapter = MySQLKhanzaAdapter(AppSettings(data_dir=tmp_path), engine=engine)

    adapter.test_connection()
    first = adapter.get_new_prescriptions(None, 1)
    second = adapter.get_new_prescriptions(
        KhanzaCursor(
            (changed + timedelta(milliseconds=500)).replace(tzinfo=UTC),
            "RX-UJI-001",
        ),
        10,
    )
    header = adapter.get_prescription_header("RX-UJI-001")
    regular = adapter.get_prescription_items("RX-UJI-001")
    compound = adapter.get_compounded_items("RX-UJI-001")
    revision = adapter.get_prescription_revision("RX-UJI-001")
    drugs = adapter.get_active_drug_master()
    latest = adapter.latest_cursor()

    assert [row.no_resep for row in first] == ["RX-UJI-001"]
    assert [row.no_resep for row in second] == ["RX-UJI-002"]
    assert header.patient_name == "PASIEN SINTETIS"
    assert regular[0].khanza_code == "OBAT-A"
    assert compound[0].compound_group == "1"
    assert len(revision) == 64
    assert [row.khanza_code for row in drugs] == ["OBAT-A"]
    assert latest == KhanzaCursor((changed + timedelta(seconds=1)).replace(tzinfo=UTC), 'RX-UJI-002')


def test_snapshot_transaction_context_optional_final_contract_and_item_cap(monkeypatch, tmp_path):
    import pytest
    from sqlalchemy import event, text
    from emss.integrations.khanza import KhanzaDataError
    monkeypatch.setenv('EMSS_KHANZA_PASSWORD', 'synthetic-only')
    engine, changed = _contract_engine()
    adapter = MySQLKhanzaAdapter(AppSettings(data_dir=tmp_path), engine=engine)
    connections = []
    def capture(connection, *args):
        connections.append(connection)
    event.listen(engine, 'before_cursor_execute', capture)
    snapshot = adapter.get_snapshot('RX-UJI-001')
    assert len(connections) == 3 and len({id(c) for c in connections}) == 1
    assert not snapshot.header.composition_complete
    assert snapshot.header.item_basis == 'UNVERIFIED'
    assert adapter._snapshot_connection.get() is None
    refs = adapter.scan_prescriptions('RX-UJI-001', 10, since=changed.replace(tzinfo=UTC))
    assert [r.no_resep for r in refs] == ['RX-UJI-002']
    assert len(adapter.scan_prescriptions('', 10)) == 2
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE vw_emss_prescription_header ADD COLUMN validation_token TEXT'))
        connection.execute(text('ALTER TABLE vw_emss_prescription_header ADD COLUMN item_basis TEXT'))
        connection.execute(text('ALTER TABLE vw_emss_prescription_header ADD COLUMN composition_complete INTEGER'))
        connection.execute(text("UPDATE vw_emss_prescription_header SET validation_token='v2', item_basis='FINAL', composition_complete=1"))
    header = adapter.get_snapshot('RX-UJI-001').header
    assert header.composition_complete and header.validation_token == 'v2' and header.item_basis == 'FINAL'
    with pytest.raises(KhanzaDataError): adapter.get_snapshot('not-found')
    assert adapter._snapshot_connection.get() is None
    with engine.begin() as connection:
        connection.execute(text('INSERT INTO vw_emss_prescription_item (no_resep, source_item_key, kode_brng) VALUES (:rx, :key, :code)'),
            [{'rx': 'RX-LARGE', 'key': str(i), 'code': 'SYN'} for i in range(1001)])
    with pytest.raises(KhanzaDataError): adapter.get_prescription_items('RX-LARGE')
    adapter.close()


def test_source_clock_uses_server_datetime(monkeypatch, tmp_path):
    engine, changed = _contract_engine()
    adapter = MySQLKhanzaAdapter(AppSettings(data_dir=tmp_path), engine=engine)
    monkeypatch.setattr(adapter, '_rows', lambda statement, params: [{'now': changed}])
    assert adapter.source_time() == changed.replace(tzinfo=UTC)
    adapter.close()


def test_mysql_health_check_does_not_probe_integration_views(monkeypatch, tmp_path):
    from sqlalchemy import event

    monkeypatch.setenv("EMSS_KHANZA_PASSWORD", "hanya-untuk-test-sintetis")
    engine, _changed = _contract_engine()
    adapter = MySQLKhanzaAdapter(AppSettings(data_dir=tmp_path), engine=engine)
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda *_args: statements.append(_args[2]))

    adapter.check_health()

    assert statements == ['SELECT 1']
    adapter.close()


def test_installation_scope_filters_header_scan_and_items(monkeypatch, tmp_path):
    monkeypatch.setenv('EMSS_KHANZA_PASSWORD', 'synthetic-only')
    engine, _ = _contract_engine()
    settings = AppSettings(data_dir=tmp_path, pharmacy_care_setting='RALAN')
    adapter = MySQLKhanzaAdapter(settings, engine=engine)
    adapter.test_connection()
    assert [row.no_resep for row in adapter.get_new_prescriptions(None, 10)] == ['RX-UJI-001']
    assert adapter.latest_cursor().no_resep == 'RX-UJI-001'
    assert adapter.get_prescription_header('RX-UJI-001').care_setting == 'RALAN'
    assert len(adapter.get_prescription_items('RX-UJI-001')) == 1
    assert adapter.get_prescription_items('RX-UJI-002') == ()
    from emss.integrations.khanza import KhanzaScopeMismatch
    import pytest
    with pytest.raises(KhanzaScopeMismatch):
        adapter.get_prescription_header('RX-UJI-002')
