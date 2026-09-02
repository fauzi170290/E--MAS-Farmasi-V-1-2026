from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertDecision:
    level: str
    priority: int
    title: str
    message: str
    notify: bool
    persistent: bool
    hold_recommended: bool


_RISK = {
    "SAFE": ("NONE", 0, "Resep selesai diskrining", "", False, False),
    "INFO": (
        "HISTORY",
        10,
        "Informasi obat",
        "Terdapat informasi minor pada hasil skrining.",
        False,
        False,
    ),
    "REVIEW": (
        "TOAST",
        30,
        "Resep perlu ditinjau",
        "Ditemukan risiko yang memerlukan tinjauan apoteker.",
        True,
        False,
    ),
    "HIGH_RISK": (
        "PERSISTENT",
        70,
        "Risiko tinggi",
        "Ditemukan risiko serius. Review apoteker diperlukan.",
        True,
        True,
    ),
    "CRITICAL": (
        "CRITICAL",
        100,
        "Risiko kritis",
        "HOLD RECOMMENDED — lakukan review sebelum obat disiapkan.",
        True,
        True,
    ),
}

_COMPLETENESS = {
    "COMPLETE": ("NONE", 0, "", "", False, False),
    "NOT_ASSESSED": (
        "TOAST",
        40,
        "Asesmen belum lengkap",
        "Terdapat pasangan yang belum dinilai; resep belum dapat dinyatakan aman.",
        True,
        False,
    ),
    "UNMAPPED": (
        "PERSISTENT",
        80,
        "Obat belum dipetakan",
        "Resep belum dapat dinyatakan aman karena terdapat obat yang belum dipetakan.",
        True,
        True,
    ),
    "INCOMPLETE": (
        "PERSISTENT",
        90,
        "Data resep belum lengkap",
        "Komponen resep belum lengkap atau belum stabil. Jangan menyatakan SAFE.",
        True,
        True,
    ),
    "ERROR": (
        "ERROR",
        110,
        "Skrining gagal",
        "Terjadi kegagalan proses. Resep tidak boleh dinyatakan SAFE.",
        True,
        True,
    ),
}


def route_alert(risk_status: str, completeness_status: str) -> AlertDecision:
    if risk_status not in _RISK:
        raise ValueError(f"Status risiko tidak valid: {risk_status}")
    if completeness_status not in _COMPLETENESS:
        raise ValueError(
            f"Status kelengkapan tidak valid: {completeness_status}"
        )
    risk = _RISK[risk_status]
    completeness = _COMPLETENESS[completeness_status]
    selected = completeness if completeness[1] > risk[1] else risk
    level, priority, title, message, notify, persistent = selected
    return AlertDecision(
        level=level,
        priority=priority,
        title=title,
        message=message,
        notify=notify,
        persistent=persistent,
        hold_recommended=risk_status == "CRITICAL",
    )
