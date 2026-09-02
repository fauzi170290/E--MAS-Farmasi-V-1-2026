from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


class TabularReadError(ValueError):
    pass


@dataclass(frozen=True)
class TabularSheet:
    name: str
    rows: tuple[tuple[Any, ...], ...]
    formula_cells: tuple[str, ...] = ()
    row_numbers: tuple[int, ...] = ()


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def _safe_xml(data: bytes, label: str) -> ET.Element:
    upper = data[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise TabularReadError(f"XML tidak aman pada {label}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise TabularReadError(f"XML rusak pada {label}") from exc


def _column_index(cell_reference: str) -> int:
    match = _CELL_REF.match(cell_reference)
    if not match:
        raise TabularReadError(f"Referensi sel tidak valid: {cell_reference}")
    index = 0
    for character in match.group(1):
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


class XlsxTableReader:
    MAX_FILE_BYTES = 50 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
    MAX_ZIP_ENTRIES = 2000
    MAX_SHEET_ROWS = 50000
    MAX_SHEET_COLUMNS = 100

    def read(self, path: Path) -> dict[str, TabularSheet]:
        if path.suffix.lower() != ".xlsx":
            raise TabularReadError("Hanya file .xlsx tanpa macro yang didukung")
        if not path.is_file():
            raise TabularReadError(f"File tidak ditemukan: {path}")
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise TabularReadError("Ukuran workbook melebihi batas 50 MB")

        try:
            archive = zipfile.ZipFile(path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise TabularReadError("File XLSX tidak valid") from exc

        with archive:
            infos = archive.infolist()
            if len(infos) > self.MAX_ZIP_ENTRIES:
                raise TabularReadError("Jumlah bagian XLSX melebihi batas")
            total_size = sum(item.file_size for item in infos)
            if total_size > self.MAX_UNCOMPRESSED_BYTES:
                raise TabularReadError("Ukuran hasil ekstraksi XLSX melebihi batas")
            for item in infos:
                name = PurePosixPath(item.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise TabularReadError("XLSX mengandung path yang tidak aman")

            shared_strings = self._read_shared_strings(archive)
            sheet_paths = self._sheet_paths(archive)
            return {
                sheet_name: self._read_sheet(
                    archive, sheet_name, sheet_path, shared_strings
                )
                for sheet_name, sheet_path in sheet_paths.items()
            }

    def _read_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            data = archive.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = _safe_xml(data, "sharedStrings.xml")
        result: list[str] = []
        for item in root.findall(f"{{{_MAIN_NS}}}si"):
            text_parts = [
                node.text or ""
                for node in item.iter(f"{{{_MAIN_NS}}}t")
            ]
            result.append("".join(text_parts))
        return result

    def _sheet_paths(self, archive: zipfile.ZipFile) -> dict[str, str]:
        try:
            workbook_root = _safe_xml(
                archive.read("xl/workbook.xml"), "workbook.xml"
            )
            rels_root = _safe_xml(
                archive.read("xl/_rels/workbook.xml.rels"),
                "workbook.xml.rels",
            )
        except KeyError as exc:
            raise TabularReadError("Struktur workbook tidak lengkap") from exc

        relationships = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship")
            if "Id" in item.attrib and "Target" in item.attrib
        }
        result: dict[str, str] = {}
        for sheet in workbook_root.findall(
            f".//{{{_MAIN_NS}}}sheet"
        ):
            name = sheet.attrib.get("name", "").strip()
            relation_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            if not name or relation_id not in relationships:
                continue
            target = relationships[relation_id].replace("\\", "/")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = f"xl/{target}"
            normalized = PurePosixPath(target)
            if ".." in normalized.parts:
                raise TabularReadError("Relasi worksheet tidak aman")
            result[name] = normalized.as_posix()
        return result

    def _read_sheet(
        self,
        archive: zipfile.ZipFile,
        sheet_name: str,
        sheet_path: str,
        shared_strings: list[str],
    ) -> TabularSheet:
        try:
            root = _safe_xml(archive.read(sheet_path), sheet_path)
        except KeyError as exc:
            raise TabularReadError(
                f"Worksheet {sheet_name} tidak ditemukan"
            ) from exc

        rows: list[tuple[Any, ...]] = []
        row_numbers: list[int] = []
        formula_cells: list[str] = []
        for sequential_row, row_node in enumerate(
            root.findall(f".//{{{_MAIN_NS}}}row"), start=1
        ):
            try:
                row_number = int(row_node.attrib.get("r", sequential_row))
            except ValueError:
                row_number = sequential_row
            if row_number > self.MAX_SHEET_ROWS:
                raise TabularReadError(
                    f"Worksheet {sheet_name} melebihi batas baris"
                )
            values: list[Any] = []
            for cell in row_node.findall(f"{{{_MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                column = _column_index(reference)
                if column >= self.MAX_SHEET_COLUMNS:
                    raise TabularReadError(
                        f"Worksheet {sheet_name} melebihi batas kolom"
                    )
                while len(values) <= column:
                    values.append(None)
                if cell.find(f"{{{_MAIN_NS}}}f") is not None:
                    formula_cells.append(reference)
                values[column] = self._cell_value(cell, shared_strings)
            while values and values[-1] is None:
                values.pop()
            rows.append(tuple(values))
            row_numbers.append(row_number)
        return TabularSheet(
            name=sheet_name,
            rows=tuple(rows),
            formula_cells=tuple(formula_cells),
            row_numbers=tuple(row_numbers),
        )

    @staticmethod
    def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(
                node.text or ""
                for node in cell.iter(f"{{{_MAIN_NS}}}t")
            )
        value_node = cell.find(f"{{{_MAIN_NS}}}v")
        if value_node is None:
            return None
        raw = value_node.text or ""
        if cell_type == "s":
            try:
                return shared_strings[int(raw)]
            except (ValueError, IndexError) as exc:
                raise TabularReadError(
                    "Indeks shared string tidak valid"
                ) from exc
        if cell_type in {"str", "e"}:
            return raw
        if cell_type == "b":
            return raw == "1"
        try:
            number = float(raw)
            return int(number) if number.is_integer() else number
        except ValueError:
            return raw


class CsvTableReader:
    MAX_FILE_BYTES = 20 * 1024 * 1024
    MAX_ROWS = 50000
    MAX_COLUMNS = 100

    def read(self, path: Path) -> TabularSheet:
        if path.suffix.lower() != ".csv":
            raise TabularReadError("File harus berformat .csv")
        if not path.is_file():
            raise TabularReadError(f"File tidak ditemukan: {path}")
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise TabularReadError("Ukuran CSV melebihi batas 20 MB")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise TabularReadError("CSV harus menggunakan UTF-8") from exc
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        rows: list[tuple[str, ...]] = []
        for index, row in enumerate(reader, start=1):
            if index > self.MAX_ROWS:
                raise TabularReadError("CSV melebihi batas baris")
            if len(row) > self.MAX_COLUMNS:
                raise TabularReadError("CSV melebihi batas kolom")
            rows.append(tuple(row))
        return TabularSheet(
            name=path.stem,
            rows=tuple(rows),
            row_numbers=tuple(range(1, len(rows) + 1)),
        )
