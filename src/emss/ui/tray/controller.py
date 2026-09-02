from __future__ import annotations
import heapq
from pathlib import Path
import logging

from emss.alerts.audio import AudioPreferences, resolve_audio_path
from emss.ui.tray.audio import AlertAudioPlayer

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QStyle,
    QSystemTrayIcon,
)

from emss.services.queue import QueueEnqueueResult, QueueSummary
from emss.ui.icons import application_icon
from emss.ui.tray.fullscreen_alert import FullscreenAlertPopup


LOGGER = logging.getLogger(__name__)


class SystemTrayController(QObject):
    show_requested = Signal()
    alert_open_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    alert_displayed = Signal(str)
    alert_suppressed = Signal(str)
    audio_delivered = Signal(str)
    audio_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication belum dibuat")
        icon = application_icon(tray=True)
        if icon.isNull():
            icon = app.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxInformation
            )
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setObjectName("emssSystemTray")
        self.tray.setToolTip("E-MAS Farmasi")
        self.fullscreen_alert = FullscreenAlertPopup()
        self.fullscreen_alert.setObjectName("emssFullscreenAlert")
        self.fullscreen_alert.open_requested.connect(self.alert_open_requested)
        self.audio = AlertAudioPlayer(self)
        self.audio.failed.connect(self._audio_failed)
        self.preferences_path = None
        self.test_label = 'UJI DUMMY'
        self.delivery_allowed = lambda _result: True
        self._pending = []
        self._pending_ids = set()
        self._serial = 0
        self._current = None
        self._dispatch_timer = QTimer(self)
        self._dispatch_timer.setSingleShot(True)
        self._dispatch_timer.timeout.connect(self._drain)
        self._guard_timer = QTimer(self)
        self._guard_timer.setInterval(500)
        self._guard_timer.timeout.connect(self._check_active)
        self._guard_timer.start()

        menu = QMenu()
        menu.setObjectName("emssTrayMenu")
        menu.setStyleSheet(
            """
            QMenu#emssTrayMenu {
                color: #EAF8FF;
                background-color: #102A3D;
                border: 1px solid #2C6078;
                border-radius: 7px;
                padding: 7px;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QMenu#emssTrayMenu::item {
                color: #EAF8FF;
                background-color: transparent;
                padding: 8px 28px 8px 12px;
                border-radius: 4px;
            }
            QMenu#emssTrayMenu::item:selected {
                color: #FFFFFF;
                background-color: #087EA4;
            }
            QMenu#emssTrayMenu::item:disabled {
                color: #94AFC0;
            }
            QMenu#emssTrayMenu::separator {
                height: 1px;
                background-color: #2C6078;
                margin: 6px 8px;
            }
            """
        )
        show_action = QAction('Buka E-MAS Farmasi', menu)
        hide_action = QAction("Sembunyikan Panel", menu)
        quit_action = QAction('Keluar dari E-MAS Farmasi', menu)
        show_action.triggered.connect(self.show_requested)
        hide_action.triggered.connect(self.hide_requested)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)
        self.tray.messageClicked.connect(self.alert_open_requested)

    @property
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> bool:
        if not self.available:
            return False
        self.tray.show()
        return True

    def hide(self) -> None:
        self.audio.player.stop()
        self._dispatch_timer.stop()
        self._guard_timer.stop()
        self.fullscreen_alert.hide()
        self.tray.hide()

    def update_summary(self, summary: QueueSummary) -> None:
        self.tray.setToolTip(
            "E-MAS Farmasi\n"
            f"Baru: {summary.new} · CRITICAL: {summary.critical} · "
            f"Risiko tinggi: {summary.high_risk}"
        )

    def show_screening_alert(self, result: QueueEnqueueResult) -> bool:
        if not result.notify or not result.alert_id or result.alert_id in self._pending_ids:
            return False
        if len(self._pending) >= 500:
            return False  # NEW persists in the outbox; the UI retries later.
        priority = {'contraindicated': 300, 'major': 200, 'duplicate': 180,
            'high-alert': 150, 'significant-review': 120, 'screening-clear': 20}.get(
            result.audio_category, result.item.priority)
        self._serial += 1
        heapq.heappush(self._pending, (-priority, self._serial, result))
        self._pending_ids.add(result.alert_id)
        if self._current is None and not self._dispatch_timer.isActive():
            self._dispatch_timer.start(50)
        return False  # Only alert_displayed marks the durable outbox SHOWN.

    def _drain(self):
        if self._current:
            self._pending_ids.discard(self._current.alert_id)
        self._current = None
        while self._pending:
            entry = heapq.heappop(self._pending)
            _, _, result = entry
            try:
                allowed = self.delivery_allowed(result)
            except Exception:
                allowed = False
            if allowed is None:
                heapq.heappush(self._pending, entry)
                self._dispatch_timer.start(1000)
                return  # Connection temporarily unavailable; do not erase delivery obligation.
            if not allowed:
                self._pending_ids.discard(result.alert_id)
                self.alert_suppressed.emit(result.alert_id)
                continue
            self._current = result
            self._present(result)
            return

    def _present(self, result):
        prefs = AudioPreferences.load(self.preferences_path) if self.preferences_path else AudioPreferences()
        categories = result.audio_categories or ((result.audio_category,) if result.audio_category else ())
        paths = []
        for category in categories:
            path, used_fallback = resolve_audio_path(category, prefs.paths.get(category, ''))
            if used_fallback:
                LOGGER.warning(
                    "Audio custom tidak tersedia; memakai audio bawaan",
                    extra={"audio_category": category},
                )
            if path is not None:
                paths.append(str(path))
        if result.audio_only:
            if self.audio.play_sequence(paths, prefs.volume):
                # Delivery means the local media backend accepted playback; hearing is not inferred.
                self.audio_delivered.emit(result.alert_id)
            else:
                self.audio_failed.emit(result.alert_id)
            self._dispatch_timer.start(500)
            return
        simulated = result.item.is_mock
        title = f'{self.test_label} — {result.alert_title}' if simulated else result.alert_title
        icon = (
            QSystemTrayIcon.MessageIcon.Critical
            if result.item.alert_level in {"CRITICAL", "ERROR"}
            else QSystemTrayIcon.MessageIcon.Warning
        )
        if self.tray.isVisible():
            self.tray.showMessage(title, result.alert_message, icon, 8000)
        # The queue card identifies one recipe without exposing a patient identity.
        message = f'Resep {result.item.no_resep} · revisi {result.item.revision_number or "-"}\n{result.alert_message}'
        if simulated:
            message += '\nHasil pengujian; bukan arahan klinis.'
        if result.audio_category in {'major', 'contraindicated'}:
            self.fullscreen_alert.show_interaction(result.item.patient_label, result.audio_category,
                result.item.no_resep, is_mock=simulated,
                incomplete=result.item.completeness_status != 'COMPLETE',
                duration_ms=15000 if result.persistent else 8000, test_label=self.test_label,
                clinical_message=result.alert_message)
        else:
            self.fullscreen_alert.show_alert(title, message, result.item.alert_level,
                15000 if result.persistent else 8000,
                hint='Klik untuk melihat obat dan resep terkait.' if result.audio_category == 'duplicate' else '')
        self.alert_displayed.emit(result.alert_id)
        if categories:
            self.audio.play_sequence(paths, prefs.volume)
        self._dispatch_timer.start(15000 if result.persistent else 8000)

    @property
    def current_queue_item_id(self):
        return self._current.item.id if self._current else ''

    def _audio_failed(self, message):
        if self._current and self._current.audio_only:
            return
        self.fullscreen_alert.hint.setText(message)

    def _check_active(self):
        if self._current:
            try:
                allowed = self.delivery_allowed(self._current)
            except Exception:
                allowed = False
            if not allowed:
                self.fullscreen_alert.hide()
                self.audio.player.stop()
                self._dispatch_timer.start(0)

    def schedule_fullscreen_test(self, delay_ms: int = 3000) -> bool:
        if not self.tray.isVisible():
            return False
        QTimer.singleShot(max(1000, delay_ms), self._show_fullscreen_test)
        return True

    def _show_fullscreen_test(self) -> None:
        if self._current or self._pending:
            return  # A demo must not overwrite an operational notification.
        title = "UJI Popup E-MAS"
        message = (
            "Ini hanya simulasi tampilan. Tidak ada resep atau data pasien "
            "yang dibuat."
        )
        self.tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Critical,
            12000,
        )
        self.fullscreen_alert.show_alert(
            title,
            message,
            "CRITICAL",
            12000,
        )

    def _activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_requested.emit()
