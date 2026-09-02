from __future__ import annotations

import tempfile
from pathlib import Path

from emss.app import build_application
from emss.config.settings import AppSettings


def run_gui_smoke() -> dict[str, object]:
    """Exercise the actual login UI without reading any operational config/data."""
    try:
        with tempfile.TemporaryDirectory(prefix="emss-gui-smoke-") as temp:
            settings = AppSettings(
                environment="test", data_dir=Path(temp),
                khanza_adapter="disabled", khanza_polling_enabled=False,
                khanza_internal_polling_consent=False,
                tray_enabled=False, single_instance=False, backup_daily_enabled=False,
            )
            container = build_application(settings)
            try:
                # Import after the guard: the frozen health command never loads Qt.
                from PySide6.QtCore import QEventLoop, QTimer
                from PySide6.QtWidgets import QApplication
                from emss.ui.application import LoginDialog

                app = QApplication.instance() or QApplication([])
                dialog = LoginDialog(container)
                try:
                    dialog.show()
                    loop = QEventLoop()
                    QTimer.singleShot(250, loop.quit)
                    loop.exec()
                    visible = dialog.isVisible()
                    return {
                        "state": "READY" if visible else "ERROR",
                        "login_visible": visible,
                        "platform": app.platformName(),
                        "schema_revision": container.database.current_revision(),
                    }
                finally:
                    dialog.close()
                    dialog.deleteLater()
                    app.processEvents()
            finally:
                container.close()
    except Exception as exc:
        return {"state": "ERROR", "error_type": type(exc).__name__}
