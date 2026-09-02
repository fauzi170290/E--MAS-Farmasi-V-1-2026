from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


DRUG_HEADERS = [
    "database_version",
    "khanza_code",
    "khanza_name_display",
    "khanza_name_normalized_source",
    "standard_active_ingredients",
    "component_count",
    "mapping_status",
    "mapping_method",
    "mapping_note",
    "rx_row_count",
    "episode_count",
    "name_variants",
]
COMPONENT_HEADERS = [
    "database_version",
    "khanza_code",
    "khanza_name_display",
    "component_order",
    "standard_active_ingredient",
    "mapping_status",
    "mapping_method",
]
DDI_SOURCE_HEADERS = [
    "pair_id",
    "pair_key",
    "active_ingredient_a",
    "active_ingredient_b",
    "pair_order_rule",
    "interaction_flag",
    "severity",
    "severity_code",
    "severity_rank",
    "clinical_explanation",
    "recommendation",
    "monitoring_parameters",
    "monitoring_basis",
    "clinical_content_basis",
    "clinical_review_required",
    "activation_status",
    "validation_status",
    "status_final_code",
    "frequency_episode",
    "source",
    "source_url",
    "access_date",
    "source_batch",
    "source_evidence_count",
    "duplicate_evidence_flag",
    "duplicate_resolution",
    "database_version",
    "build_date",
    "notes",
]
DDI_TEMPLATE_HEADERS = [
    "drug_a_code",
    "drug_a_name",
    "drug_b_code",
    "drug_b_name",
    "interaction_status",
    "severity_code",
    "severity_label",
    "clinical_effect",
    "mechanism",
    "recommendation",
    "monitoring",
    "population_risk",
    "source_name",
    "source_reference",
    "source_accessed_at",
    "validated_by",
    "validated_at",
    "knowledge_base_version",
    "status",
    "notes",
]


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(
    headers: list[str],
    rows: list[list[object]],
    *,
    formula_cell: str | None = None,
) -> str:
    all_rows = [["TEST DATA"], [], headers, *rows]
    row_xml: list[str] = []
    for row_number, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_number, value in enumerate(row, start=1):
            if value is None:
                continue
            reference = f"{_column_name(column_number)}{row_number}"
            if reference == formula_cell:
                cells.append(
                    f'<c r="{reference}"><f>1+1</f><v>2</v></c>'
                )
            elif isinstance(value, (int, float)):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{reference}" t="inlineStr"><is><t>'
                    f"{escape(str(value))}</t></is></c>"
                )
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        f'{"".join(row_xml)}</sheetData></worksheet>'
    )


def write_drug_workbook(
    path: Path,
    drug_rows: list[list[object]],
    component_rows: list[list[object]],
    *,
    formula_cell: str | None = None,
) -> Path:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="DRUG_MASTER_KHANZA" sheetId="1" r:id="rId1"/>
    <sheet name="DRUG_COMPONENT_MAP" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            _sheet_xml(DRUG_HEADERS, drug_rows, formula_cell=formula_cell),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            _sheet_xml(COMPONENT_HEADERS, component_rows),
        )
    return path


def write_ddi_workbook(
    path: Path,
    rows: list[list[object]],
    *,
    template: bool = False,
    formula_cell: str | None = None,
) -> Path:
    sheet_name = "DDI_IMPORT" if template else "DDI_RULE_MASTER"
    headers = DDI_TEMPLATE_HEADERS if template else DDI_SOURCE_HEADERS
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            _sheet_xml(headers, rows, formula_cell=formula_cell),
        )
    return path


def valid_ddi_source_rows(version: str = "DDI-TEST-v1") -> list[list[object]]:
    return [
        [
            "DDI-001",
            "diazepam || warfarin",
            "diazepam",
            "warfarin",
            "alphabetical_ascending",
            1,
            "Serious",
            "SERIOUS",
            3,
            "Risiko perdarahan meningkat.",
            "Pertimbangkan alternatif dan monitor.",
            "INR dan tanda perdarahan",
            "SOURCE",
            "PAIR_SPECIFIC_SOURCE",
            1,
            "HOLD_CLINICAL_REVIEW_REQUIRED",
            "DDI_POSITIVE",
            "SUDAH_TERDETEKSI_DDI_MASTER",
            3,
            "Sumber Uji",
            "https://example.test/ddi",
            "2026-07-01",
            "TEST",
            1,
            0,
            "Kanonik",
            version,
            "2026-07-01",
            "Perlu review.",
        ],
        [
            "DDI-002",
            "paracetamol || warfarin",
            "paracetamol",
            "warfarin",
            "alphabetical_ascending",
            0,
            "",
            "NONE",
            0,
            "",
            "",
            "",
            "",
            "",
            0,
            "NOT_AN_ALERT_RULE",
            "NO_INTERACTION_BATCH_CONFIRMED",
            "SUDAH_DICEK_NO_INTERACTION",
            2,
            "Sumber Uji",
            "https://example.test/ddi",
            "2026-07-01",
            "TEST",
            0,
            0,
            "Kanonik",
            version,
            "2026-07-01",
            "Bukti no interaction batch.",
        ],
        [
            "DDI-003",
            "diazepam || paracetamol",
            "diazepam",
            "paracetamol",
            "alphabetical_ascending",
            0,
            "",
            "NONE",
            0,
            "",
            "",
            "",
            "",
            "",
            0,
            "NOT_AN_ALERT_RULE",
            "NOT_ASSESSABLE",
            "TIDAK_DAPAT_DINILAI",
            1,
            "Sumber Uji",
            "https://example.test/ddi",
            "2026-07-01",
            "TEST",
            0,
            0,
            "Kanonik",
            version,
            "2026-07-01",
            "Tidak dapat dinilai.",
        ],
    ]


def valid_test_rows() -> tuple[list[list[object]], list[list[object]]]:
    drugs = [
        [
            "DDI-TEST-v1",
            "001",
            "OBAT KOMBINASI",
            "OBAT KOMBINASI",
            "diazepam; metamizole",
            2,
            "MAPPED",
            "manual_review",
            "Data uji",
            10,
            8,
            "OBAT KOMBINASI (10)",
        ],
        [
            "DDI-TEST-v1",
            "002",
            "DIAZEPAM 2 MG",
            "DIAZEPAM 2 MG",
            "diazepam",
            1,
            "MAPPED",
            "manual_review",
            "Data uji",
            5,
            5,
            "DIAZEPAM 2 MG (5)",
        ],
    ]
    components = [
        [
            "DDI-TEST-v1",
            "001",
            "OBAT KOMBINASI",
            1,
            "diazepam",
            "MAPPED",
            "manual_review",
        ],
        [
            "DDI-TEST-v1",
            "001",
            "OBAT KOMBINASI",
            2,
            "metamizole",
            "MAPPED",
            "manual_review",
        ],
        [
            "DDI-TEST-v1",
            "002",
            "DIAZEPAM 2 MG",
            1,
            "diazepam",
            "MAPPED",
            "manual_review",
        ],
    ]
    return drugs, components
