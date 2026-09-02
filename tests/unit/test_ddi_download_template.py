from __future__ import annotations

from pathlib import Path

from emss.importexport.ddi_import import TEMPLATE_HEADERS
from emss.importexport.tabular_reader import XlsxTableReader


TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "ddi_import_template.xlsx"


def test_downloadable_ddi_template_has_prefilled_new_pairs_and_manual_rows():
    sheets = XlsxTableReader().read(TEMPLATE)
    ddi_import = sheets["DDI_IMPORT"]
    header_index = next(
        index
        for index, row in enumerate(ddi_import.rows)
        if {str(value).casefold() for value in row if value} == TEMPLATE_HEADERS
    )
    candidates = [
        row
        for row in ddi_import.rows[header_index + 1 :]
        if len(row) >= 19 and row[0] and row[1] and row[2] and row[3]
    ]

    assert not ddi_import.formula_cells
    assert len(candidates) == 22
    assert all(row[4] == "INTERACTION_FOUND" for row in candidates)
    assert all(row[17] == "DDI-KHANZA-v1.0.0" for row in candidates)
    assert all(row[18] == "DRAFT" for row in candidates)
