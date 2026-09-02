from __future__ import annotations

from typing import Any

from emss.importexport.drug_import import normalize_name, normalize_text


KNOWLEDGE_STATUSES = ("DRAFT", "REVIEWED", "APPROVED", "PUBLISHED", "RETIRED")
INTERACTION_STATUSES = frozenset(
    {
        "INTERACTION_FOUND",
        "ASSESSED_NO_INTERACTION",
        "NOT_ASSESSABLE",
        "EXCLUDED",
    }
)
SEVERITY_MAP = {
    "NONE": (0, None),
    "MINOR": (1, "INFO"),
    "SIGNIFICANT": (2, "REVIEW"),
    "SERIOUS": (3, "HIGH_RISK"),
    "CONTRAINDICATED": (4, "CRITICAL"),
}


def canonical_pair(first: Any, second: Any) -> tuple[str, str, str]:
    left = normalize_name(first)
    right = normalize_name(second)
    if not left or not right:
        raise ValueError("Kedua zat aktif wajib diisi")
    if left == right:
        raise ValueError("Pasangan DDI harus terdiri dari dua zat aktif berbeda")
    low, high = sorted((left, right))
    return low, high, f"{low} || {high}"


def normalize_severity(value: Any) -> tuple[str, int, str | None]:
    code = normalize_text(value).upper().replace(" ", "_")
    if code not in SEVERITY_MAP:
        raise ValueError(f"Severity tidak valid: {code or '(kosong)'}")
    rank, app_status = SEVERITY_MAP[code]
    return code, rank, app_status


def validate_status_severity(interaction_status: str, severity_code: str) -> None:
    if interaction_status not in INTERACTION_STATUSES:
        raise ValueError(f"Status interaksi tidak valid: {interaction_status}")
    if interaction_status == "INTERACTION_FOUND" and severity_code == "NONE":
        raise ValueError("Interaksi positif tidak boleh menggunakan severity NONE")
    if interaction_status != "INTERACTION_FOUND" and severity_code != "NONE":
        raise ValueError(
            "Rule non-interaksi/tidak dapat dinilai harus menggunakan severity NONE"
        )

