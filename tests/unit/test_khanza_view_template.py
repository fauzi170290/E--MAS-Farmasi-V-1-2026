from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VIEW_SQL = ROOT / "templates" / "khanza_integration_views_mariadb104.sql"


def _sql() -> str:
    return VIEW_SQL.read_text(encoding="utf-8")


def test_rs_view_template_defines_exactly_four_expected_views():
    names = re.findall(
        r"CREATE\s+OR\s+REPLACE\s+SQL\s+SECURITY\s+DEFINER\s+VIEW\s+(\w+)",
        _sql(),
        flags=re.IGNORECASE,
    )
    assert names == [
        "vw_emss_prescription_header",
        "vw_emss_prescription_item",
        "vw_emss_compound_item",
        "vw_emss_drug_master",
    ]


def test_rs_view_template_is_view_only_and_has_required_contract_aliases():
    sql = _sql()
    without_comments = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    forbidden = r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|GRANT|REVOKE)\b"
    assert re.search(forbidden, without_comments, flags=re.IGNORECASE) is None

    aliases = {
        "no_resep", "no_rawat", "no_rm", "nama_pasien", "unit_depo",
        "dokter", "asal_layanan", "status_resep", "validation_token",
        "item_basis", "composition_complete", "changed_at", "source_item_key",
        "kode_brng", "nama_brng", "jumlah", "aturan_pakai", "rute",
        "no_racik", "aktif",
    }
    for alias in aliases:
        assert re.search(rf"\bAS\s+{alias}\b", sql, flags=re.IGNORECASE)

    # Khanza 10.4 may store no_resep as latin1 while CAST(... AS CHAR) uses
    # utf8mb4. Normalize the identifier before CONCAT_WS builds the token.
    assert "CONVERT(ro.no_resep USING utf8mb4)" in sql


def test_rs_view_template_uses_only_mapped_khanza_source_tables():
    sql = _sql().lower()
    required = {
        "resep_obat", "resep_dokter", "resep_dokter_racikan",
        "resep_dokter_racikan_detail", "databarang", "reg_periksa",
        "pasien", "dokter", "poliklinik",
    }
    for table in required:
        assert re.search(rf"\b{table}\b", sql)

