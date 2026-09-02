"""Import/export APIs loaded lazily to keep submodules independently usable."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "DrugImportError": ("drug_import", "DrugImportError"),
    "DrugImportService": ("drug_import", "DrugImportService"),
    "ImportIssue": ("drug_import", "ImportIssue"),
    "ImportPreview": ("drug_import", "ImportPreview"),
    "DdiCommitResult": ("ddi_import", "DdiCommitResult"),
    "DdiImportError": ("ddi_import", "DdiImportError"),
    "DdiImportIssue": ("ddi_import", "DdiImportIssue"),
    "DdiImportPreview": ("ddi_import", "DdiImportPreview"),
    "DdiImportService": ("ddi_import", "DdiImportService"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(f"emss.importexport.{module_name}"), attribute)
    globals()[name] = value
    return value
