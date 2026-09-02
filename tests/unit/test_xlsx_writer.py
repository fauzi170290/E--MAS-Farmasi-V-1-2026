from __future__ import annotations

import zipfile

from emss.importexport.tabular_reader import XlsxTableReader
from emss.importexport.xlsx_writer import XlsxSheet, write_xlsx


def test_xlsx_writer_keeps_formula_like_text_as_inert_value(tmp_path):
    target = tmp_path / "safe.xlsx"
    payload = '=HYPERLINK("https://example.invalid","click")'
    write_xlsx(
        target,
        [
            XlsxSheet(
                "DATA",
                [["text"], [payload]],
                (40,),
                row_styles={1: 2},
            )
        ],
    )

    sheet = XlsxTableReader().read(target)["DATA"]
    assert sheet.rows[1][0] == payload
    assert not sheet.formula_cells
    with zipfile.ZipFile(target) as archive:
        assert b"<f>" not in archive.read("xl/worksheets/sheet1.xml")
