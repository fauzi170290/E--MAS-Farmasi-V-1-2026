from __future__ import annotations

import zipfile

import pytest

from emss.importexport.tabular_reader import (
    CsvTableReader,
    TabularReadError,
    XlsxTableReader,
)
from tests.helpers.xlsx_factory import valid_test_rows, write_drug_workbook


def test_xlsx_reader_reads_template_without_formula(tmp_path):
    drugs, components = valid_test_rows()
    source = write_drug_workbook(tmp_path / "master.xlsx", drugs, components)

    sheets = XlsxTableReader().read(source)

    assert set(sheets) == {"DRUG_MASTER_KHANZA", "DRUG_COMPONENT_MAP"}
    assert sheets["DRUG_MASTER_KHANZA"].rows[2][1] == "khanza_code"
    assert sheets["DRUG_MASTER_KHANZA"].rows[3][1] == "001"
    assert sheets["DRUG_MASTER_KHANZA"].row_numbers[3] == 4
    assert sheets["DRUG_MASTER_KHANZA"].formula_cells == ()


def test_xlsx_reader_reports_formula_cells(tmp_path):
    drugs, components = valid_test_rows()
    source = write_drug_workbook(
        tmp_path / "formula.xlsx",
        drugs,
        components,
        formula_cell="F4",
    )

    sheets = XlsxTableReader().read(source)

    assert sheets["DRUG_MASTER_KHANZA"].formula_cells == ("F4",)


def test_xlsx_reader_rejects_path_traversal_entry(tmp_path):
    source = tmp_path / "unsafe.xlsx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../escape.xml", "<x/>")

    with pytest.raises(TabularReadError, match="path yang tidak aman"):
        XlsxTableReader().read(source)


def test_xlsx_reader_rejects_bad_zip(tmp_path):
    source = tmp_path / "bad.xlsx"
    source.write_bytes(b"bukan workbook")

    with pytest.raises(TabularReadError, match="tidak valid"):
        XlsxTableReader().read(source)


def test_csv_reader_supports_utf8_and_semicolon(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("kode;nama\n001;Obat Uji\n", encoding="utf-8")

    sheet = CsvTableReader().read(source)

    assert sheet.rows[1] == ("001", "Obat Uji")
    assert sheet.row_numbers == (1, 2)


def test_csv_reader_rejects_non_utf8(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_bytes(b"kode,nama\n001,\xff")

    with pytest.raises(TabularReadError, match="UTF-8"):
        CsvTableReader().read(source)
