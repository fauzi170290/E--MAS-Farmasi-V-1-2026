from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog


def fit_dialog_to_available_screen(
    dialog: QDialog,
    preferred_width: int,
    preferred_height: int,
    *,
    margin: int = 48,
) -> None:
    """Keep a dialog inside the usable desktop area, including the taskbar."""
    screen = dialog.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        dialog.resize(preferred_width, preferred_height)
        return

    available = screen.availableGeometry()
    maximum_width = max(320, available.width() - margin)
    maximum_height = max(320, available.height() - margin)
    dialog.setMaximumSize(maximum_width, maximum_height)
    dialog.resize(
        min(preferred_width, maximum_width),
        min(preferred_height, maximum_height),
    )
