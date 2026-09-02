from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from emss.ui.icons import application_icon


class FullscreenAlertPopup(QWidget):
    """Top-most, non-activating alert that remains visible over fullscreen apps."""

    open_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("fullscreenAlertPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setFixedWidth(460)

        self.card = QFrame()
        self.card.setObjectName("fullscreenAlertCard")
        self.logo = QLabel()
        self.logo.setFixedSize(54, 54)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setPixmap(application_icon(tray=True).pixmap(48, 48))
        self.title = QLabel()
        self.title.setObjectName("fullscreenAlertTitle")
        self.title.setWordWrap(True)
        self.message = QLabel()
        self.message.setObjectName("fullscreenAlertMessage")
        self.message.setWordWrap(True)
        self.hint = QLabel("Klik notifikasi untuk membuka detail resep")
        self.hint.setObjectName("fullscreenAlertHint")
        for label in (self.title, self.message, self.hint):
            label.setTextFormat(Qt.TextFormat.PlainText)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.message)
        text_layout.addWidget(self.hint)
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 16, 12)
        card_layout.setSpacing(12)
        card_layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(text_layout, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self.card)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._apply_level("TOAST")

    def show_alert(
        self,
        title: str,
        message: str,
        level: str,
        duration_ms: int,
        *, compact: bool = False, hint: str = '',
    ) -> None:
        self.setFixedWidth(400 if compact else 460)
        icon_size = 40 if compact else 54
        self.logo.setFixedSize(icon_size, icon_size)
        self.logo.setPixmap(application_icon(tray=True).pixmap(icon_size, icon_size))
        self.hint.setText(hint or 'Klik notifikasi untuk membuka detail resep')
        self.title.setText(title)
        self.message.setText(message)
        self._apply_level(level, compact=compact)
        self.adjustSize()
        self._move_to_top_right()
        self.show()
        self.raise_()
        self._force_native_topmost()
        self._timer.start(max(3000, duration_ms))

    def show_interaction(
        self, patient_label, category, no_resep, *, is_mock, incomplete,
        duration_ms=12000, test_label='UJI DUMMY', clinical_message='',
    ):
        title = {'major': 'MAYOR', 'contraindicated': 'KONTRAINDIKASI'}[category]
        patient = ' '.join((patient_label or 'Nama pasien belum tersedia').split())
        hint = (test_label + ' · ' if is_mock and test_label else '') + f'Resep {no_resep}'
        hint += '\n' + ('Ada catatan pemeriksaan · ' if incomplete else '') + 'Klik untuk detail'
        message = clinical_message or 'Ditemukan interaksi obat.'
        level = 'CRITICAL' if category == 'contraindicated' else 'PERSISTENT'
        self.show_alert(title, f'Pasien: {patient}\n{message}', level, duration_ms,
            compact=True, hint=hint)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            self.open_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange and self.isVisible():
            self._force_native_topmost()
        super().changeEvent(event)

    def _apply_level(self, level: str, *, compact: bool = False) -> None:
        if level in {"CRITICAL", "ERROR"}:
            accent, background, title = "#DC2626", "#FFF1F2", "#991B1B"
        elif level == "PERSISTENT":
            accent, background, title = "#EA580C", "#FFF7ED", "#9A3412"
        else:
            accent, background, title = "#2563EB", "#EFF6FF", "#1E3A8A"
        self.card.setStyleSheet(
            "QFrame#fullscreenAlertCard {"
            f"background: {background}; border: 3px solid {accent}; "
            "border-radius: 12px;}"
            f"QLabel#fullscreenAlertTitle {{color: {title}; font-size: {22 if compact else 13}pt; font-weight: 800; border: none;}}"
            "QLabel#fullscreenAlertMessage {color: #111827; font-size: 10pt; border: none;}"
            "QLabel#fullscreenAlertHint {color: #475569; font-size: 9pt; border: none;}"
        )

    def _move_to_top_right(self) -> None:
        app = QApplication.instance()
        screen = app.screenAt(QCursor.pos()) if app is not None else None
        if screen is None and app is not None:
            screen = app.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 22, area.top() + 22)

    def _force_native_topmost(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd_topmost = -1
            swp_nosize = 0x0001
            swp_nomove = 0x0002
            swp_noactivate = 0x0010
            swp_showwindow = 0x0040
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()),
                hwnd_topmost,
                0,
                0,
                0,
                0,
                swp_nosize | swp_nomove | swp_noactivate | swp_showwindow,
            )
        except (AttributeError, OSError, TypeError):
            return
