from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtGui import QIcon


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ICON_DIR = ASSET_DIR / "icons"

# Semantic keys prevent individual screens from choosing unrelated artwork.
# The local SVG set is deliberately small, stroke-based, and remains legible
# at the 16px navigation size and on high-DPI Windows displays.
CLINICAL_ICON_FILES = {
    "prescription": "prescription.svg",
    "intervention": "intervention.svg",
    "history": "history.svg",
    "dashboard": "dashboard.svg",
    "medicine": "medicine.svg",
    "mapping": "mapping.svg",
    "interaction": "interaction.svg",
    "import_export": "import-export.svg",
    "safety": "safety.svg",
    "connection": "connection.svg",
    "audio": "audio.svg",
    "backup": "backup.svg",
    "settings": "settings.svg",
    "validation": "validation.svg",
    "simulator": "simulator.svg",
    "refresh": "refresh.svg",
    "search": "search.svg",
    "save": "save.svg",
}

NAVIGATION_ICON_KEYS = {
    "Antrean Resep": "prescription",
    "Intervensi Apoteker": "intervention",
    "Riwayat Pemeriksaan": "history",
    "Riwayat Intervensi": "history",
    "Dashboard Kajian pDDI": "dashboard",
    "Master Obat": "medicine",
    "Impor Pemetaan Obat": "mapping",
    "Pasangan Interaksi Obat": "interaction",
    "Impor Data Interaksi": "import_export",
    "Keselamatan Obat": "safety",
    "Koneksi Khanza": "connection",
    "Suara Peringatan": "audio",
    "Pencadangan & Pemulihan": "backup",
    "Status Sistem & Diagnostik": "settings",
    "Validasi Klinis & UAT": "validation",
    "Simulasi Resep Dummy": "simulator",
}


def icon_path(key: str) -> Path | None:
    """Return only known, bundled SVG assets; never resolve user input."""
    filename = CLINICAL_ICON_FILES.get(key)
    if filename is None:
        return None
    path = ICON_DIR / filename
    return path if path.is_file() else None


def clinical_icon(key: str, fallback: QIcon | None = None) -> QIcon:
    """Load a semantic clinical icon and preserve a native fallback if missing."""
    path = icon_path(key)
    if path is not None:
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return fallback if fallback is not None else QIcon()


def navigation_icon_key(title: str) -> str:
    return NAVIGATION_ICON_KEYS.get(title, "settings")


BUTTON_ICON_RULES = (
    (("intervensi",), "intervention"),
    (("pasangan", "interaksi", "pair"), "interaction"),
    (("master obat", "obat baru", "obat"), "medicine"),
    (("pemetaan", "mapping"), "mapping"),
    (("dashboard", "laporan"), "dashboard"),
    (("riwayat", "history"), "history"),
    (("koneksi", "polling", "integrasi"), "connection"),
    (("suara", "audio", "peringatan"), "audio"),
    (("cadangan", "backup", "pulihkan", "restore"), "backup"),
    (("simulasi", "dummy"), "simulator"),
    (("ekspor", "impor", "berkas", "format"), "import_export"),
    (("cari", "search"), "search"),
    (("muat ulang", "refresh", "periksa ulang", "evaluasi ulang", "coba periksa"), "refresh"),
    (("simpan", "commit"), "save"),
    (("setujui", "aktifkan", "validasi", "tandai", "approve", "pass"), "validation"),
    (("emergency", "nonaktifkan", "hapus", "rollback", "halt"), "safety"),
)


def button_icon_key(label: str) -> str | None:
    normalized = " ".join(label.casefold().split())
    for terms, key in BUTTON_ICON_RULES:
        if any(term in normalized for term in terms):
            return key
    return None


def apply_contextual_icons(root) -> int:
    """Apply only known semantic icons to clickable buttons below ``root``."""
    from PySide6.QtWidgets import QPushButton

    applied = 0
    for button in root.findChildren(QPushButton):
        key = button_icon_key(button.text())
        if key is None:
            continue
        icon = clinical_icon(key)
        if icon.isNull():
            continue
        button.setIcon(icon)
        applied += 1
    return applied


def application_icon(*, tray: bool = False) -> QIcon:
    """Muat ikon resmi; QIcon null menjadi fallback aman saat aset hilang."""
    filename = "emss-tray.png" if tray else "emss.ico"
    return QIcon(str(ASSET_DIR / filename))


def configure_windows_app_identity() -> None:
    """Pisahkan ikon/taskbar e-MSS dari ikon generik runtime Python."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "eMSS.Farmasi.RS"
        )
    except (AttributeError, OSError):
        return
