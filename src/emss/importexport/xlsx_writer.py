from __future__ import annotations

import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape


_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


class XlsxWriteError(ValueError):
    pass


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    rows: Iterable[Sequence[Any]]
    widths: Sequence[float]
    freeze_rows: int = 1
    auto_filter: bool = True
    row_styles: dict[int, int] = field(default_factory=dict)
    merges: tuple[str, ...] = ()


def write_xlsx(path: Path | str, sheets: Sequence[XlsxSheet]) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        raise XlsxWriteError("File export harus berekstensi .xlsx")
    if not sheets:
        raise XlsxWriteError("Workbook harus memiliki minimal satu sheet")
    names = [sheet.name for sheet in sheets]
    if len(set(names)) != len(names):
        raise XlsxWriteError("Nama sheet harus unik")
    for name in names:
        if not name or len(name) > 31 or any(char in name for char in "[]:*?/\\"):
            raise XlsxWriteError(f"Nama sheet tidak valid: {name}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f"._xlsx_{uuid.uuid4().hex[:8]}.tmp"
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
            archive.writestr("_rels/.rels", _root_relationships())
            archive.writestr("docProps/core.xml", _core_properties())
            archive.writestr("docProps/app.xml", _app_properties(names))
            archive.writestr("xl/workbook.xml", _workbook(names))
            archive.writestr(
                "xl/_rels/workbook.xml.rels", _workbook_relationships(len(sheets))
            )
            archive.writestr("xl/styles.xml", _styles())
            for index, sheet in enumerate(sheets, start=1):
                _write_worksheet(archive, index, sheet)
        temporary.replace(target)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        temporary.unlink(missing_ok=True)
        raise XlsxWriteError(f"Gagal membuat workbook: {exc}") from exc
    return target


def _write_worksheet(
    archive: zipfile.ZipFile, index: int, sheet: XlsxSheet
) -> None:
    rows = list(sheet.rows)
    column_count = max((len(row) for row in rows), default=len(sheet.widths))
    if column_count == 0:
        column_count = 1
    last_row = max(1, len(rows))
    dimension = f"A1:{_column_name(column_count)}{last_row}"
    with archive.open(f"xl/worksheets/sheet{index}.xml", "w") as output:
        output.write(
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main">'
                f'<dimension ref="{dimension}"/>'
                "<sheetViews><sheetView workbookViewId=\"0\" showGridLines=\"0\">"
                + (
                    f'<pane ySplit="{sheet.freeze_rows}" '
                    f'topLeftCell="A{sheet.freeze_rows + 1}" '
                    'activePane="bottomLeft" state="frozen"/>'
                    if sheet.freeze_rows
                    else ""
                )
                + "</sheetView></sheetViews><sheetFormatPr defaultRowHeight=\"18\"/>"
                + _columns(sheet.widths)
                + "<sheetData>"
            ).encode("utf-8")
        )
        for row_index, row in enumerate(rows, start=1):
            style = sheet.row_styles.get(row_index, 0)
            cells = "".join(
                _cell_xml(row_index, column_index, value, style)
                for column_index, value in enumerate(row, start=1)
                if value is not None
            )
            height = ' ht="30" customHeight="1"' if style == 1 else ""
            output.write(f'<row r="{row_index}"{height}>{cells}</row>'.encode("utf-8"))
        output.write(b"</sheetData>")
        if sheet.auto_filter and rows:
            output.write(
                f'<autoFilter ref="A1:{_column_name(column_count)}{last_row}"/>'.encode(
                    "utf-8"
                )
            )
        if sheet.merges:
            output.write(
                (
                    f'<mergeCells count="{len(sheet.merges)}">'
                    + "".join(f'<mergeCell ref="{escape(ref)}"/>' for ref in sheet.merges)
                    + "</mergeCells>"
                ).encode("utf-8")
            )
        output.write(b"</worksheet>")


def _cell_xml(row: int, column: int, value: Any, style: int) -> str:
    reference = f"{_column_name(column)}{row}"
    style_attribute = f' s="{style}"' if style else ""
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"{style_attribute}><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}"{style_attribute}><v>{value}</v></c>'
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    text = _ILLEGAL_XML.sub("", str(value))
    if len(text) > 32767:
        raise XlsxWriteError(f"Isi sel {reference} melebihi batas Excel 32.767 karakter")
    escaped = escape(text)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f'<c r="{reference}" t="inlineStr"{style_attribute}>'
        f'<is><t{preserve}>{escaped}</t></is></c>'
    )


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _columns(widths: Sequence[float]) -> str:
    if not widths:
        return ""
    entries = "".join(
        f'<col min="{index}" max="{index}" width="{max(6, min(width, 60))}" '
        'customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    return f"<cols>{entries}</cols>"


def _content_types(sheet_count: int) -> str:
    worksheets = "".join(
        '<Override PartName="/xl/worksheets/sheet'
        f'{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{worksheets}</Types>"
    )


def _root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _workbook(names: Sequence[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets><calcPr calcId=\"191029\"/></workbook>"
    )


def _workbook_relationships(sheet_count: int) -> str:
    sheets = "".join(
        '<Relationship Id="rId'
        f'{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        f'relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{sheets}<Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )


def _styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="4">
    <font><sz val="10"/><name val="Aptos"/><color rgb="FF1F2937"/></font>
    <font><b/><sz val="16"/><name val="Aptos Display"/><color rgb="FFFFFFFF"/></font>
    <font><b/><sz val="10"/><name val="Aptos"/><color rgb="FFFFFFFF"/></font>
    <font><b/><sz val="10"/><name val="Aptos"/><color rgb="FF123B5D"/></font>
  </fonts>
  <fills count="6">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF123B5D"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1D4ED8"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF2FF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF7D6"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2"><border/><border><bottom style="thin"><color rgb="FFCBD5E1"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="5">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _core_properties() -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Export Master DDI Lengkap E-MAS Farmasi</dc:title>
  <dc:creator>E-MAS Farmasi</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
</cp:coreProperties>"""


def _app_properties(names: Sequence[str]) -> str:
    titles = "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name in names)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>E-MAS Farmasi</Application><Sheets>{len(names)}</Sheets>
  <TitlesOfParts><vt:vector size="{len(names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>
</Properties>"""
