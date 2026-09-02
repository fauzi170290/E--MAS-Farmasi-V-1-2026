from __future__ import annotations

import logging
import sys
from sqlalchemy.exc import SQLAlchemyError
from time import monotonic
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    QTime,
    QTimer,
    Qt,
    Signal,
    Slot,
    QUrl,
)
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.desktop import SingleInstanceGuard
from emss.health.service import HealthCheckResult, HealthState
from emss.importexport.drug_import import DrugImportError, ImportPreview
from emss.services.authentication import (
    AccountLockedError,
    AuthenticatedUser,
    AuthenticationError,
)
from emss.ui.dialogs import fit_dialog_to_available_screen
from emss.ui.knowledge.management import DdiImportTab, KnowledgeBaseTab
from emss.ui.reference import ReferencePairsPanel, DrugEditor, can_manage
from emss.ui.queue import QueuePanel
from emss.ui.integration import KhanzaIntegrationPanel
from emss.ui.screening.simulator import ScreeningSimulatorTab
from emss.ui.tray import SystemTrayController
from emss.ui.tray.audio_panel import AudioSettingsPanel
from emss.ui.icons import application_icon, apply_contextual_icons, configure_windows_app_identity
from emss.ui.interactions import install_hover_feedback
from emss.ui.intervention import InterventionPanel
from emss.ui.dashboard import DashboardPanel
from emss.ui.safety import MedicationSafetyPanel
from emss.ui.backup import BackupPanel
from emss.ui.validation import ClinicalValidationPanel
from emss.config.settings import AppEnvironment
from emss.ui.navigation import WorkflowNavigation, ScrollableTabs
from emss.ui.presentation import status_text
from emss import __version__


LOGGER = logging.getLogger(__name__)


APP_STYLESHEET = """
QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
    color: #1E293B;
}
QMainWindow, QDialog {
    background: #F5F8FB;
}
QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport {
    background: #F5F8FB;
    border: none;
}
QWidget#queuePanel {
    background: #F4F8FB;
}
QWidget#interventionFormPage {
    background: #F4F8FB;
    color: #172B4D;
}
QWidget#interventionFormPage QLabel {
    color: #172B4D;
}
QScrollArea#interventionFormScroll {
    background: #F4F8FB;
}
QAbstractScrollArea::corner {
    background: #F4F7FA;
}
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #DCE6EE;
    border-radius: 12px;
}
QLineEdit {
    min-height: 36px;
    padding: 0 10px;
    color: #111827;
    border: 1px solid #AAB7C4;
    border-radius: 8px;
    background: white;
}
QLineEdit:focus {
    border: 2px solid #2563EB;
}
QPlainTextEdit, QTextEdit, QTextBrowser {
    color: #111827;
    background: #FFFFFF;
    selection-color: #111827;
    selection-background-color: #BFDBFE;
    border: 1px solid #AAB7C4;
    border-radius: 8px;
    padding: 8px;
}
QPlainTextEdit:focus, QTextEdit:focus, QTextBrowser:focus {
    border: 2px solid #2563EB;
}
QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit {
    min-height: 34px;
    color: #111827;
    background: #FFFFFF;
    border: 1px solid #AAB7C4;
    border-radius: 5px;
    padding: 0 8px;
}
QMenuBar {
    color: #1F2937;
    background: #F4F7FA;
    border-bottom: 1px solid #D8E0E8;
}
QMenuBar::item {
    color: #1F2937;
    background: transparent;
    padding: 6px 12px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    color: #1E3A8A;
    background: #DBEAFE;
}
QMenu {
    color: #111827;
    background: #FFFFFF;
    border: 1px solid #94A3B8;
    padding: 5px;
}
QMenu::item {
    color: #111827;
    background: transparent;
    padding: 8px 28px 8px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    color: #1E3A8A;
    background: #DBEAFE;
}
QMenu::item:disabled {
    color: #94A3B8;
}
QToolTip {
    color: #111827;
    background: #FFFFFF;
    border: 1px solid #64748B;
    padding: 5px;
}
QComboBox {
    min-height: 36px;
    padding: 0 40px 0 10px;
    color: #111827;
    background: #FFFFFF;
    border: 1px solid #94A3B8;
    border-radius: 8px;
}
QComboBox:hover {
    border-color: #2563EB;
}
QComboBox:focus {
    border: 2px solid #2563EB;
}
QComboBox::drop-down {
    width: 32px;
    background: #F1F5F9;
    border: none;
    border-left: 1px solid #CBD5E1;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}
QComboBox::down-arrow {
    image: url("__COMBO_ARROW_PATH__");
    width: 14px;
    height: 9px;
}
QComboBox::down-arrow:on {
    top: 2px;
}
QComboBox QAbstractItemView {
    color: #111827;
    background: #FFFFFF;
    border: 1px solid #64748B;
    selection-color: #1E3A8A;
    selection-background-color: #DBEAFE;
    outline: 0;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 34px;
    padding: 4px 8px;
}
QPushButton {
    min-height: 36px;
    padding: 0 16px;
    color: #1F2937;
    border: 1px solid #CBD5E1;
    border-radius: 10px;
    background: #E8EEF3;
}
QPushButton:hover {
    background: #D1D5DB;
    border-color: #64748B;
}
QPushButton:disabled:hover {
    color: #94A3B8;
    background: #E5E7EB;
    border-color: #D1D5DB;
}
QPushButton:focus {
    color: #1E3A8A;
    background: #DBEAFE;
    border: 2px solid #2563EB;
}
QPushButton:pressed {
    color: #FFFFFF;
    background: #2563EB;
    border: 2px solid #1E40AF;
    padding-top: 2px;
}
QPushButton:disabled {
    color: #94A3B8;
    background: #E5E7EB;
    border-color: #D1D5DB;
}
QPushButton#primary {
    color: white;
    background: #0F766E;
    font-weight: 600;
}
QPushButton[primaryAction="true"] {
    color: white; background: #1D4ED8; font-weight: 600;
}
QPushButton[danger="true"] {
    color: #991B1B; background: #FFF1F2; border: 1px solid #BE123C;
}
QPushButton#openSimulator {
    color: white;
    background: #1D4ED8;
    font-weight: 600;
}
QPushButton#primary:hover {
    background: #0D5F59;
}
QPushButton#openSimulator:hover {
    background: #1E40AF;
}
QPushButton#primary:focus,
QPushButton#openSimulator:focus {
    color: #FFFFFF;
    background: #1D4ED8;
    border: 2px solid #60A5FA;
}
QPushButton#primary:pressed,
QPushButton#openSimulator:pressed {
    color: #FFFFFF;
    background: #172554;
    border: 2px solid #0F172A;
    padding-top: 2px;
}
QTableWidget {
    background: #FFFFFF;
    border: 1px solid #DCE6EE;
    border-radius: 10px;
    alternate-background-color: #F7FAFC;
    gridline-color: #E8EEF3;
}
QHeaderView::section {
    background: #EAF1F5;
    color: #243B53;
    padding: 7px;
    border: none;
    border-right: 1px solid #CFD9E3;
    font-weight: 600;
}
QHeaderView {
    color: #243B53;
    background: #E8EEF4;
}
QTableCornerButton::section {
    background: #E8EEF4;
    border: none;
}
QTabWidget::pane {
    border: 1px solid #DCE6EE;
    background: #F5F8FB;
}
QTabBar::tab {
    color: #334155;
    background: #EAF1F5;
    border: 1px solid #D6E2EA;
    border-bottom: none;
    padding: 10px 14px;
    min-width: 105px;
}
QTabBar::tab:hover {
    color: #0F172A;
    background: #F1F5F9;
}
QTabBar::tab:selected {
    color: #FFFFFF;
    background: #0F766E;
    font-weight: 700;
}
QTableWidget::item:hover, QTreeWidget::item:hover, QListWidget::item:hover {
    background: #EAF2FF;
    color: #172554;
}
QTabBar::tab:selected:hover { background: #0D5F59; }
QCheckBox { color: #1E293B; spacing: 7px; }
QCheckBox:hover { color: #0F766E; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #64748B; border-radius: 4px; background: #FFFFFF; }
QCheckBox::indicator:checked { background: #0F766E; border-color: #0F766E; }
QScrollBar:vertical { width: 12px; background: #EEF4F7; margin: 3px; border-radius: 6px; }
QScrollBar::handle:vertical { min-height: 34px; background: #94A3B8; border-radius: 6px; }
QScrollBar::handle:vertical:hover { background: #64748B; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #F5F8FB; color: #475569; border-top: 1px solid #DCE6EE; }
"""


class FirstAdminDialog(QDialog):
    def __init__(
        self,
        container: ApplicationContainer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.container = container
        self.authenticated_user: AuthenticatedUser | None = None
        self.setWindowTitle("Buat Administrator Pertama")

        title = QLabel("Administrator Pertama")
        title.setStyleSheet("font-size: 17pt; font-weight: 700; color: #123B5D;")
        guidance = QLabel(
            "Buat akun individual untuk pengelolaan awal. Setelah akun berhasil "
            "dibuat, master DDI bundle akan dimuat sebagai DRAFT dan tidak aktif "
            "sebelum workflow klinis diselesaikan."
        )
        guidance.setWordWrap(True)
        self.username = QLineEdit()
        self.username.setObjectName("firstAdminUsername")
        self.username.setPlaceholderText("contoh: admin.farmasi")
        self.display_name = QLineEdit()
        self.display_name.setObjectName("firstAdminDisplayName")
        self.display_name.setPlaceholderText("Nama administrator")
        self.password = self._password("firstAdminPassword", 'Kata sandi baru')
        self.confirm_password = self._password(
            "firstAdminPasswordConfirmation", "Ulangi password"
        )
        self.confirm_password.returnPressed.connect(self._submit)
        form = QFormLayout()
        form.addRow('Nama pengguna', self.username)
        form.addRow("Nama tampilan", self.display_name)
        form.addRow('Kata sandi', self.password)
        form.addRow("Konfirmasi", self.confirm_password)
        self.message = QLabel()
        self.message.setObjectName("firstAdminMessage")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #B42318;")
        buttons = QDialogButtonBox()
        create_button = buttons.addButton(
            "Buat Administrator", QDialogButtonBox.ButtonRole.AcceptRole
        )
        create_button.setObjectName("primary")
        cancel_button = buttons.addButton(
            "Batal", QDialogButtonBox.ButtonRole.RejectRole
        )
        create_button.clicked.connect(self._submit)
        cancel_button.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(guidance)
        layout.addLayout(form)
        layout.addWidget(self.message)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(self, 580, 470)

    @staticmethod
    def _password(name: str, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName(name)
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    @Slot()
    def _submit(self) -> None:
        self.message.clear()
        if self.password.text() != self.confirm_password.text():
            self.message.setText("Konfirmasi password tidak sama")
            self.confirm_password.clear()
            self.confirm_password.setFocus()
            return
        try:
            user = self.container.users.create_first_admin(
                username=self.username.text(),
                display_name=self.display_name.text(),
                password=self.password.text(),
            )
            self.container.bundled_ddi.apply_if_eligible(user.id)
            self.container.bundled_mapping.apply_if_eligible(user.id)
            self.authenticated_user = self.container.authentication.authenticate(
                self.username.text(), self.password.text()
            )
        except ValueError as exc:
            self.password.clear()
            self.confirm_password.clear()
            self.message.setText(str(exc))
            return
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, container: ApplicationContainer) -> None:
        super().__init__()
        self.container = container
        self.authenticated_user: AuthenticatedUser | None = None
        self.setWindowTitle("Masuk — E-MAS Farmasi")
        if container.settings.khanza_adapter.value == 'mysql_dummy':
            self.setWindowTitle('Masuk — E-MAS Farmasi UJI DUMMY LOKAL')

        logo = QLabel()
        logo.setObjectName("loginBrandLogo")
        logo.setFixedSize(76, 76)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(application_icon(tray=True).pixmap(68, 68))
        title = QLabel("E-MAS Farmasi")
        title.setObjectName("loginBrandTitle")
        title.setStyleSheet("font-size: 18pt; font-weight: 700; color: #123B5D;")
        product_name = QLabel("electronic Medication Alert System")
        product_name.setObjectName("loginProductName")
        product_name.setStyleSheet(
            "font-size: 12pt; font-weight: 700; color: #087EA4;"
        )
        subtitle = QLabel("Sistem pendukung keselamatan obat untuk farmasi.")
        subtitle.setStyleSheet("color: #526372;")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        brand_text.addWidget(title)
        brand_text.addWidget(product_name)
        brand_text.addWidget(subtitle)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        brand_row.addWidget(logo)
        brand_row.addLayout(brand_text, 1)

        self.username = QLineEdit()
        self.username.setObjectName("username")
        self.username.setAccessibleName('Nama pengguna')
        self.username.setPlaceholderText('Nama pengguna')
        self.password = QLineEdit()
        self.password.setObjectName("password")
        self.password.setAccessibleName('Kata sandi')
        self.password.setPlaceholderText('Kata sandi')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self._authenticate)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow('Nama pengguna', self.username)
        form.addRow('Kata sandi', self.password)

        self.message = QLabel("")
        self.message.setObjectName("loginMessage")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #B42318;")

        buttons = QDialogButtonBox()
        login_button = buttons.addButton(
            "Masuk", QDialogButtonBox.ButtonRole.AcceptRole
        )
        login_button.setObjectName("primary")
        cancel_button = buttons.addButton(
            "Batal", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.workstation_button = buttons.addButton(
            'Mode Farmasi (tanpa kata sandi)',
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.workstation_button.setObjectName("openSimulator")
        self.create_admin_button = buttons.addButton(
            "Buat Administrator Pertama",
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.create_admin_button.setObjectName("createFirstAdmin")
        self.workstation_button.setVisible(
            self.container.settings.allow_workstation_mode
        )
        login_button.clicked.connect(self._authenticate)
        cancel_button.clicked.connect(self.reject)
        self.workstation_button.clicked.connect(
            self._enter_workstation_mode
        )
        self.create_admin_button.clicked.connect(self._create_first_admin)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)
        card_layout.addLayout(brand_row)
        card_layout.addLayout(form)
        card_layout.addWidget(self.message)
        card_layout.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(card)

        no_users = self.container.users.count_users() == 0
        self.create_admin_button.setVisible(no_users)
        if no_users:
            self.message.setText(
                "Belum ada pengguna. Buat administrator pertama untuk "
                "melanjutkan; master DDI bundle akan dimuat sebagai DRAFT."
            )
            login_button.setEnabled(False)
            self.workstation_button.setEnabled(False)

        fit_dialog_to_available_screen(self, 520, 380)

    def _authenticate(self) -> None:
        self.message.clear()
        try:
            self.authenticated_user = (
                self.container.authentication.authenticate(
                    self.username.text(), self.password.text()
                )
            )
        except (AuthenticationError, AccountLockedError) as exc:
            self.password.clear()
            self.message.setText(str(exc))
            self.password.setFocus()
            return
        self.accept()

    def _create_first_admin(self) -> None:
        dialog = FirstAdminDialog(self.container, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.authenticated_user = dialog.authenticated_user
        if self.authenticated_user is not None:
            self.accept()

    def _enter_workstation_mode(self) -> None:
        self.message.clear()
        care = self.container.settings.pharmacy_care_setting
        if not care:
            from emss.ui.workstation_setup import WorkstationSetupDialog
            setup = WorkstationSetupDialog(self)
            if setup.exec() != QDialog.DialogCode.Accepted:
                return
            care = setup.care_setting
        try:
            self.authenticated_user = (
                self.container.workstation_access.enter_mode(care_setting=care)
            )
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.container = container
        self.user = user
        self.setWindowTitle('Ubah Kata Sandi')

        title = QLabel(f"Ubah password akun {user.username}")
        title.setStyleSheet(
            "font-size: 15pt; font-weight: 700; color: #123B5D;"
        )
        guidance = QLabel(
            "Gunakan minimal 6 karakter. Password baru tidak boleh memuat "
            "username dan harus berbeda dari password saat ini."
        )
        guidance.setWordWrap(True)

        self.current_password = self._password_field('Kata sandi saat ini')
        self.new_password = self._password_field('Kata sandi baru')
        self.confirm_password = self._password_field(
            "Ulangi password baru"
        )
        self.confirm_password.returnPressed.connect(self._submit)

        form = QFormLayout()
        form.addRow('Kata sandi saat ini', self.current_password)
        form.addRow('Kata sandi baru', self.new_password)
        form.addRow("Konfirmasi", self.confirm_password)

        self.message = QLabel("")
        self.message.setObjectName("changePasswordMessage")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #B42318;")

        buttons = QDialogButtonBox()
        save_button = buttons.addButton(
            'Simpan Kata Sandi', QDialogButtonBox.ButtonRole.AcceptRole
        )
        save_button.setObjectName("primary")
        cancel_button = buttons.addButton(
            "Batal", QDialogButtonBox.ButtonRole.RejectRole
        )
        save_button.clicked.connect(self._submit)
        cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(guidance)
        layout.addLayout(form)
        layout.addWidget(self.message)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(self, 560, 420)

    @staticmethod
    def _password_field(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    @Slot()
    def _submit(self) -> None:
        self.message.clear()
        if self.new_password.text() != self.confirm_password.text():
            self.message.setText("Konfirmasi password baru tidak sama")
            self.confirm_password.clear()
            self.confirm_password.setFocus()
            return
        try:
            self.container.users.change_password(
                user_id=self.user.id,
                current_password=self.current_password.text(),
                new_password=self.new_password.text(),
            )
        except ValueError as exc:
            self.message.setText(str(exc))
            self.current_password.clear()
            self.new_password.clear()
            self.confirm_password.clear()
            return
        self.accept()


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _ServiceWorker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.function = function
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


class DrugCatalogTab(QWidget):
    pair_requested = Signal(str)

    def __init__(self, container: ApplicationContainer, user=None) -> None:
        super().__init__()
        self.container = container
        self.user = user

        self.summary_label = QLabel()
        self.summary_label.setObjectName("catalogSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background: #EAF2FF; border: 1px solid #A9C4ED; "
            "padding: 10px; border-radius: 6px;"
        )

        self.search = QLineEdit()
        self.search.setObjectName("catalogSearch")
        self.search.setPlaceholderText("Cari kode SIMRS, kode KFA, atau nama obat")
        self.search.returnPressed.connect(self.refresh)
        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.setObjectName("refreshCatalog")
        self.refresh_button.clicked.connect(self.request_refresh)
        self.refresh_feedback = QLabel("Siap.")
        self.refresh_feedback.setObjectName("catalogRefreshFeedback")
        self.refresh_feedback.setStyleSheet("color: #526372;")

        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.refresh_button)
        self.active_filter = QComboBox()
        self.active_filter.addItem("Obat aktif", False)
        self.active_filter.addItem("Termasuk nonaktif", True)
        self.active_filter.currentIndexChanged.connect(self.refresh)
        search_row.addWidget(self.active_filter)
        action_row = QHBoxLayout()
        for label, handler in (("Tambah Obat", self.add_drug), ("Edit Obat", self.edit_drug),
                ("Nonaktifkan", self.deactivate_drug), ("Tambahkan Pair DDI", self.add_pair)):
            button = QPushButton(label)
            button.setEnabled(can_manage(user))
            button.clicked.connect(handler)
            action_row.addWidget(button)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName("drugCatalogTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Kode SIMRS",
                "Kode KFA",
                "Nama obat",
                "Status sumber",
                'Tinjauan',
                "Komponen",
                "Zat aktif",
                "Metode",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.verticalScrollBar().setSingleStep(3)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.top_button = QPushButton('Ke Atas')
        self.top_button.setObjectName('catalogScrollTop')
        self.top_button.clicked.connect(lambda: self.table.verticalScrollBar().setValue(
            self.table.verticalScrollBar().minimum()))
        self.bottom_button = QPushButton('Ke Bawah')
        self.bottom_button.setObjectName('catalogScrollBottom')
        self.bottom_button.clicked.connect(lambda: self.table.verticalScrollBar().setValue(
            self.table.verticalScrollBar().maximum()))
        scroll_actions = QHBoxLayout()
        scroll_actions.addWidget(QLabel('Navigasi daftar:'))
        scroll_actions.addWidget(self.top_button)
        scroll_actions.addWidget(self.bottom_button)
        scroll_actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.summary_label)
        layout.addLayout(search_row)
        layout.addLayout(action_row)
        layout.addWidget(self.refresh_feedback)
        layout.addLayout(scroll_actions)
        layout.addWidget(self.table, 1)
        self.refresh()

    @Slot()
    def request_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Memuat…")
        self.refresh_feedback.setText("Memuat data master obat…")
        QTimer.singleShot(0, self._complete_requested_refresh)

    @Slot()
    def _complete_requested_refresh(self) -> None:
        try:
            self.refresh()
        finally:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("✓ Selesai")
            self.refresh_feedback.setText(
                "Data berhasil diperbarui pukul "
                f"{QTime.currentTime().toString('HH:mm:ss')}."
            )

    @Slot()
    def refresh(self) -> None:
        summary = self.container.catalog.summary()
        displayed_rows = self.container.catalog.list_drugs(
            self.search.text(), include_inactive=self.active_filter.currentData()
        )
        hidden = max(0, summary.total_drugs - len(displayed_rows))
        self.summary_label.setText(
            f"Total obat: {summary.total_drugs}  ·  "
            f"Tampil unik: {len(displayed_rows)}" + (f"  ·  Duplikasi kode disembunyikan: {hidden}" if hidden else "") + "  ·  "
            f"Terpetakan dari sumber: {summary.source_mapped}  ·  "
            f"Belum/parsial: {summary.source_unmapped}  ·  "
            f"Menunggu tinjauan: {summary.pending_review}  ·  "
            f"Disetujui: {summary.approved}  ·  "
            f"Komponen aktif: {summary.active_components}\n"
            "PENDING_REVIEW berarti pemetaan belum disetujui/diaktifkan; hasil tidak boleh dianggap lengkap sebelum tinjauan berwenang."
        )
        rows = displayed_rows
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.khanza_code,
                row.kfa_product_code or "—",
                row.display_name + (" [Nonaktif]" if not row.is_active else ""),
                row.source_mapping_status,
                row.review_status,
                str(row.component_count),
                "; ".join(name + (f" [{code}]" if code else "")
                    for name, code in zip(row.ingredients, row.ingredient_kfa_codes)),
                row.mapping_method,
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.id)
                if column_index == 4:
                    if value == "APPROVED":
                        item.setBackground(QBrush(QColor("#DDF7E8")))
                    else:
                        item.setBackground(QBrush(QColor("#FFF2CC")))
                self.table.setItem(row_index, column_index, item)

    def selected_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else ""

    def add_drug(self):
        if can_manage(self.user):
            dialog = DrugEditor(self.container, self.user, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh()
                self.pair_requested.emit(dialog.saved_id)

    def edit_drug(self):
        if self.selected_id() and can_manage(self.user):
            if DrugEditor(self.container, self.user, self.selected_id(), self).exec() == QDialog.DialogCode.Accepted:
                self.refresh()

    def deactivate_drug(self):
        if self.selected_id() and can_manage(self.user):
            detail = self.container.reference.drug_detail(self.selected_id())
            if QMessageBox.question(self, "Nonaktifkan obat", "Nonaktifkan obat terpilih? Hasil lama tetap tersimpan.") != QMessageBox.StandardButton.Yes:
                return
            try:
                self.container.reference.set_drug_active(detail['id'], self.user.id, detail['updated_at'])
            except ValueError as exc:
                QMessageBox.warning(self, "Perubahan belum disimpan", str(exc))
            except SQLAlchemyError:
                QMessageBox.warning(self, "Perubahan belum disimpan", "Database sedang sibuk atau penyimpanan gagal. Muat ulang lalu coba kembali.")
            self.refresh()

    def add_pair(self):
        if self.selected_id() and can_manage(self.user):
            self.pair_requested.emit(self.selected_id())


class DrugImportTab(QWidget):
    catalog_changed = Signal()

    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.thread_pool = QThreadPool.globalInstance()
        self.current_batch_id: str | None = None
        self._worker: _ServiceWorker | None = None
        self._active_button: QPushButton | None = None
        self._active_button_text = ""
        self._button_states: dict[QPushButton, bool] = {}
        self._authorized = bool(
            user.roles.intersection(
                {"SUPER_ADMIN", "KNOWLEDGE_ADMIN", "CLINICAL_REVIEWER"}
            )
        )

        self.file_path = QLineEdit()
        self.file_path.setObjectName("importFilePath")
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Pilih workbook .xlsx atau file .csv")
        self.choose_button = QPushButton('Pilih Berkas')
        self.choose_button.setObjectName("chooseImportFile")
        self.choose_button.clicked.connect(self.choose_file)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_path, 1)
        file_row.addWidget(self.choose_button)

        self.batch_combo = QComboBox()
        self.batch_combo.setObjectName("recentImportBatches")
        self.batch_combo.currentIndexChanged.connect(self._batch_selected)
        self.refresh_batches_button = QPushButton("Muat Riwayat")
        self.refresh_batches_button.setObjectName("refreshImportHistory")
        self.refresh_batches_button.clicked.connect(self.request_batch_refresh)
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("Lanjutkan batch:"))
        batch_row.addWidget(self.batch_combo, 1)
        batch_row.addWidget(self.refresh_batches_button)

        self.preview_button = QPushButton('1. Periksa Isi Berkas')
        self.preview_button.setObjectName("previewImport")
        self.preview_button.setStyleSheet(
            "color: white; background: #1D4ED8; font-weight: 600;"
        )
        self.preview_button.clicked.connect(self.preview_import)
        self.commit_button = QPushButton('2. Simpan ke Data Lokal')
        self.commit_button.setObjectName("commitImport")
        self.commit_button.clicked.connect(self.commit_import)
        self.commit_button.setEnabled(False)
        self.approve_button = QPushButton('3. Setujui Pemetaan Impor')
        self.approve_button.setObjectName("approveImport")
        self.approve_button.clicked.connect(self.approve_import)
        self.approve_button.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(self.preview_button)
        actions.addWidget(self.commit_button)
        actions.addWidget(self.approve_button)
        actions.addStretch()

        self.progress = QProgressBar()
        self.progress.setObjectName("importProgress")
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.status_label = QLabel(
            "Preview tidak mengubah master obat. Commit bersifat transaksional."
        )
        self.status_label.setObjectName("importStatus")
        self.status_label.setWordWrap(True)

        self.issue_table = QTableWidget(0, 4)
        self.issue_table.setObjectName("importIssueTable")
        self.issue_table.setHorizontalHeaderLabels(
            ["Sheet", "Baris", "Field", "Pesan validasi"]
        )
        self.issue_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.issue_table.verticalHeader().setVisible(False)
        issue_header = self.issue_table.horizontalHeader()
        issue_header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        issue_header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        issue_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        issue_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        safety_note = QLabel(
            "Mapping hasil import berstatus PENDING_REVIEW. Mapping baru aktif "
            "setelah persetujuan eksplisit oleh apoteker berwenang."
        )
        safety_note.setWordWrap(True)
        safety_note.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; "
            "padding: 10px; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addLayout(file_row)
        layout.addLayout(batch_row)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(safety_note)
        layout.addWidget(self.issue_table, 1)

        if not self._authorized:
            self.choose_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            self.status_label.setText(
                "Role Anda tidak berwenang mengimpor atau menyetujui mapping."
            )
        self.load_recent_batches()

    @Slot()
    def choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih master obat dan mapping",
            "",
            "Data obat (*.xlsx *.csv)",
        )
        if selected:
            self.file_path.setText(selected)
            self.current_batch_id = None
            self.commit_button.setEnabled(False)
            self.approve_button.setEnabled(False)

    @Slot()
    def preview_import(self) -> None:
        path = self.file_path.text().strip()
        if not path:
            self.status_label.setText("Pilih file terlebih dahulu.")
            return
        self._start_worker(
            lambda: self.container.drug_import.preview(
                Path(path), self.user.id
            ),
            self._preview_succeeded,
            "Memvalidasi workbook tanpa mengubah master obat…",
            self.preview_button,
        )

    @Slot()
    def commit_import(self) -> None:
        if not self.current_batch_id:
            return
        batch_id = self.current_batch_id
        self._start_worker(
            lambda: self.container.drug_import.commit(
                batch_id, self.user.id
            ),
            self._commit_succeeded,
            "Menyimpan master obat dan mapping sebagai PENDING_REVIEW…",
            self.commit_button,
        )

    @Slot()
    def approve_import(self) -> None:
        if not self.current_batch_id:
            return
        confirmation = QMessageBox.question(
            self,
            "Setujui Mapping",
            "Anda menyatakan telah meninjau mapping pada batch ini. "
            "Aktifkan seluruh mapping batch?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        batch_id = self.current_batch_id
        self._start_worker(
            lambda: self.container.drug_import.approve_batch(
                batch_id, self.user.id
            ),
            self._approve_succeeded,
            "Mengaktifkan mapping yang disetujui…",
            self.approve_button,
        )

    def _start_worker(
        self,
        function: Callable[[], Any],
        on_success: Callable[[Any], None],
        message: str,
        active_button: QPushButton,
    ) -> None:
        self._set_busy(active_button)
        self.status_label.setText(message)
        worker = _ServiceWorker(function)

        def finish_success(result: Any) -> None:
            self._finish_worker()
            on_success(result)

        def finish_failure(message: str) -> None:
            self._finish_worker()
            self._operation_failed(message)

        worker.signals.succeeded.connect(finish_success)
        worker.signals.failed.connect(finish_failure)
        self._worker = worker
        self.thread_pool.start(worker)

    def _set_busy(self, active_button: QPushButton) -> None:
        buttons = (
            self.choose_button,
            self.refresh_batches_button,
            self.preview_button,
            self.commit_button,
            self.approve_button,
        )
        self._button_states = {button: button.isEnabled() for button in buttons}
        self._active_button = active_button
        self._active_button_text = active_button.text()
        active_button.setText("Memproses…")
        for button in buttons:
            button.setEnabled(False)
        self.progress.setVisible(True)

    @Slot()
    def _finish_worker(self) -> None:
        self.progress.setVisible(False)
        if self._active_button is not None:
            self._active_button.setText(self._active_button_text)
        self.choose_button.setEnabled(self._authorized)
        self.refresh_batches_button.setEnabled(True)
        self.preview_button.setEnabled(self._authorized)
        self._active_button = None
        self._active_button_text = ""
        self._worker = None

    @Slot(object)
    def _preview_succeeded(self, preview: ImportPreview) -> None:
        self.current_batch_id = preview.batch_id
        self.status_label.setText(
            f"Preview selesai — versi {preview.source_version or '-'}; "
            f"{preview.total_rows} baris, {preview.valid_rows} valid, "
            f"{preview.invalid_rows} invalid; "
            f"insert {preview.proposed_inserts}, update "
            f"{preview.proposed_updates}, unchanged "
            f"{preview.proposed_unchanged}."
        )
        self._render_issues(preview)
        self.commit_button.setEnabled(preview.commit_allowed)
        self.load_recent_batches(select_batch_id=preview.batch_id)

    @Slot(object)
    def _commit_succeeded(self, result: object) -> None:
        counts = dict(result)
        self.status_label.setText(
            "Commit berhasil. Mapping masih PENDING_REVIEW — "
            f"inserted {counts.get('inserted', 0)}, "
            f"updated {counts.get('updated', 0)}, "
            f"unchanged {counts.get('unchanged', 0)}."
        )
        self.approve_button.setEnabled(True)
        self.catalog_changed.emit()
        self.load_recent_batches(select_batch_id=self.current_batch_id)

    @Slot(object)
    def _approve_succeeded(self, result: object) -> None:
        approved = int(result)
        self.approve_button.setEnabled(False)
        self.status_label.setText(
            f"Persetujuan selesai. {approved} master obat dalam batch "
            "telah berstatus APPROVED."
        )
        self.catalog_changed.emit()
        self.load_recent_batches(select_batch_id=self.current_batch_id)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self.status_label.setText(f"Operasi gagal: {message}")
        for button, enabled in self._button_states.items():
            button.setEnabled(enabled)

    @Slot()
    def request_batch_refresh(self) -> None:
        self.refresh_batches_button.setEnabled(False)
        self.refresh_batches_button.setText("Memuat…")
        self.status_label.setText("Memuat riwayat batch…")
        QTimer.singleShot(0, self._complete_batch_refresh)

    @Slot()
    def _complete_batch_refresh(self) -> None:
        try:
            self.load_recent_batches()
            self.status_label.setText(
                "Riwayat batch berhasil diperbarui pukul "
                f"{QTime.currentTime().toString('HH:mm:ss')}."
            )
        finally:
            self.refresh_batches_button.setEnabled(True)
            self.refresh_batches_button.setText("✓ Selesai")

    def _render_issues(self, preview: ImportPreview) -> None:
        self.issue_table.setRowCount(len(preview.issues))
        for row_index, issue in enumerate(preview.issues):
            for column_index, value in enumerate(
                (issue.sheet, str(issue.row), issue.field, issue.message)
            ):
                item = QTableWidgetItem(value)
                item.setBackground(QBrush(QColor("#FDE7E7")))
                self.issue_table.setItem(row_index, column_index, item)

    @Slot()
    def load_recent_batches(self, select_batch_id: str | None = None) -> None:
        batches = self.container.catalog.recent_batches()
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        self.batch_combo.addItem("— pilih batch sebelumnya —", None)
        selected_index = 0
        for batch in batches:
            label = (
                f"{batch.created_at} · {batch.status} · "
                f"{batch.filename} · invalid {batch.invalid_rows}"
            )
            self.batch_combo.addItem(label, (batch.id, batch.status))
            if batch.id == select_batch_id:
                selected_index = self.batch_combo.count() - 1
        self.batch_combo.setCurrentIndex(selected_index)
        self.batch_combo.blockSignals(False)

    @Slot(int)
    def _batch_selected(self, index: int) -> None:
        data = self.batch_combo.itemData(index)
        if not data:
            return
        batch_id, status = data
        try:
            preview = self.container.drug_import.get_preview(batch_id)
        except DrugImportError as exc:
            self.status_label.setText(f"Gagal membuka batch: {exc}")
            return
        self.current_batch_id = batch_id
        self._render_issues(preview)
        self.status_label.setText(
            f"Batch {status}: {preview.filename}; "
            f"{preview.valid_rows} valid, {preview.invalid_rows} invalid."
        )
        self.commit_button.setEnabled(
            self._authorized and status == "PREVIEWED" and preview.commit_allowed
        )
        self.approve_button.setEnabled(
            self._authorized and status == "COMMITTED"
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.tray_controller: SystemTrayController | None = None
        self._force_close = False
        self.advisory_banner: QLabel | None = None
        self.advisory_gate_check_failed = False
        self.advisory_block_reason: str | None = None
        self.advisory_blocked = self._refresh_advisory_gate()
        self.setWindowTitle("E-MAS Farmasi")
        if container.settings.khanza_adapter.value == 'mysql_dummy':
            self.setWindowTitle('E-MAS Farmasi — UJI DUMMY LOKAL')
        self.resize(1240, 940)

        brand_logo = QLabel()
        brand_logo.setObjectName("mainBrandLogo")
        brand_logo.setFixedSize(62, 62)
        brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_logo.setPixmap(application_icon(tray=True).pixmap(56, 56))
        title = QLabel("E-MAS Farmasi")
        title.setObjectName("mainBrandTitle")
        title.setStyleSheet("font-size: 20pt; font-weight: 700; color: #123B5D;")
        product_name = QLabel("electronic Medication Alert System")
        product_name.setObjectName("mainProductName")
        product_name.setStyleSheet(
            "font-size: 11pt; font-weight: 700; color: #087EA4;"
        )
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        brand_text.addWidget(title)
        brand_text.addWidget(product_name)
        brand_header = QHBoxLayout()
        brand_header.setSpacing(12)
        brand_header.addWidget(brand_logo)
        brand_header.addLayout(brand_text, 1)
        identity = QLabel(
            f"Pengguna: {user.display_name} · Role: "
            f"{', '.join(sorted(user.roles))}"
        )
        identity.setStyleSheet("color: #526372;")
        is_admin = bool(user.roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        self.technical_authorized = user.username != 'mode.farmasi' and is_admin
        password_label = 'Ganti Kata Sandi Admin' if is_admin else 'Ubah Kata Sandi'
        self.change_password_button = QPushButton(password_label)
        self.change_password_button.setObjectName("changePassword")
        self.change_password_button.clicked.connect(self._change_password)
        self.change_password_button.setVisible(user.username != "mode.farmasi")
        identity_row = QHBoxLayout()
        identity_row.addWidget(identity, 1)
        if user.username == "mode.farmasi":
            scope_label = {
                'RALAN': 'RAWAT JALAN', 'RANAP': 'RAWAT INAP'
            }.get(self.container.settings.pharmacy_care_setting, 'BELUM DIPILIH')
            mode_badge = QLabel(
                f"MODE FARMASI {scope_label} · perubahan master terkunci"
            )
            mode_badge.setStyleSheet(
                "background: #DBEAFE; color: #1E3A8A; font-weight: 700; "
                "padding: 6px 10px; border-radius: 5px;"
            )
            identity_row.addWidget(mode_badge)
        identity_row.addWidget(self.change_password_button)

        account_menu = self.menuBar().addMenu("Akun")
        self.change_admin_password_action = QAction(password_label, self)
        self.change_admin_password_action.setObjectName(
            "changeAdminPasswordAction"
        )
        self.change_admin_password_action.setVisible(
            user.username != "mode.farmasi"
        )
        self.change_admin_password_action.triggered.connect(
            self._change_password
        )
        account_menu.addAction(self.change_admin_password_action)
        if container.settings.khanza_adapter.value == 'mysql_dummy':
            exit_dummy = QAction('Keluar E-MAS Farmasi', self)
            exit_dummy.triggered.connect(self.quit_application)
            account_menu.addAction(exit_dummy)

        self.state_label = QLabel()
        self.state_label.setObjectName("healthState")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumHeight(56)
        self.detail_label = QLabel()
        self.detail_label.setObjectName("healthDetails")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        refresh = QPushButton("Periksa Ulang")
        refresh.setObjectName("refreshHealth")
        refresh.clicked.connect(self.refresh_health)

        health_card = QFrame()
        health_card.setObjectName("card")
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(20, 20, 20, 20)
        health_layout.addWidget(QLabel('Pemeriksaan Sistem Lokal'))
        health_layout.addWidget(self.state_label)
        health_layout.addWidget(self.detail_label)
        health_layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignRight)

        notice = QLabel(
            'Tidak ada alarm bukan berarti resep aman. Periksa kelengkapan '
            'kandungan obat dan pasangan yang belum dinilai. Menutup popup '
            'tidak menyetujui terapi. DDI DRAFT hanya untuk uji yang diizinkan.'
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; "
            "padding: 12px; border-radius: 6px;"
        )
        self.open_simulator_button = QPushButton(
            'Buka Simulasi Resep Dummy'
        )
        self.open_simulator_button.setObjectName("openSimulator")
        self.test_fullscreen_alert_button = QPushButton(
            'Uji Popup Dummy (3 detik)'
        )
        self.test_fullscreen_alert_button.setObjectName(
            "testFullscreenAlert"
        )
        self.test_fullscreen_alert_button.clicked.connect(
            self._test_fullscreen_alert
        )

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(16, 16, 16, 16)
        overview_layout.addWidget(health_card)
        overview_layout.addWidget(notice)
        overview_layout.addWidget(
            self.open_simulator_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        overview_layout.addWidget(
            self.test_fullscreen_alert_button,
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        overview_layout.addStretch()

        self.catalog_tab = DrugCatalogTab(container, user)
        self.import_tab = DrugImportTab(container, user)
        self.import_tab.catalog_changed.connect(self.catalog_tab.refresh)
        self.knowledge_tab = ReferencePairsPanel(container, user)
        self.catalog_tab.pair_requested.connect(self.knowledge_tab.add_pair)
        self.knowledge_tab.changed.connect(self.catalog_tab.refresh)
        self.ddi_import_tab = DdiImportTab(container, user)
        self.ddi_import_tab.knowledge_changed.connect(self.knowledge_tab.refresh)
        self.screening_tab = ScreeningSimulatorTab(container, user)
        self.queue_tab = QueuePanel(container, user)
        self.integration_tab = KhanzaIntegrationPanel(container, user)
        self.intervention_tab = InterventionPanel(container, user)
        self.dashboard_authorized = 'SUPER_ADMIN' in user.roles
        self.dashboard_tab = (
            DashboardPanel(container, user) if self.dashboard_authorized else QWidget()
        )
        self.safety_tab = MedicationSafetyPanel(container, user)
        self.backup_tab = BackupPanel(
            container,
            user,
            restore_guard=self.integration_tab.prepare_for_restore,
        )
        self.validation_authorized = user.username != 'mode.farmasi' and bool(user.roles.intersection(
            {'SUPER_ADMIN', 'IT_ADMIN', 'CLINICAL_REVIEWER', 'APOTEKER', 'KFT'}))
        self.validation_tab = ClinicalValidationPanel(container, user) if self.validation_authorized else QWidget()
        self.backup_tab.restart_required.connect(self.quit_application)
        self.integration_tab.polling_completed.connect(self._polling_completed)
        self.integration_tab.screening_ready.connect(self._screening_completed)
        self.integration_tab.catalog_changed.connect(self.catalog_tab.refresh)
        self.screening_tab.screening_completed.connect(
            self._screening_completed
        )
        self.queue_tab.screening_completed.connect(
            self._screening_completed
        )
        self.queue_tab.queue_changed.connect(self.intervention_tab.refresh)
        if self.dashboard_authorized:
            self.queue_tab.queue_changed.connect(self.dashboard_tab.refresh)

        self.tabs = ScrollableTabs()
        self.tabs.setObjectName("mainTabs")
        self.tabs.addTab(overview, 'Status Sistem & Diagnostik')
        silent_routine_user = (
            container.settings.environment == AppEnvironment.SILENT_PILOT
            and not user.roles.intersection(
                {"SUPER_ADMIN", "IT_ADMIN", "CLINICAL_REVIEWER", "KFT"}
            )
        )
        if not silent_routine_user:
            self.tabs.addTab(self.queue_tab, 'Antrean Resep')
            self.tabs.addTab(self.intervention_tab, "Intervensi Apoteker")
        if self.dashboard_authorized:
            self.tabs.addTab(self.dashboard_tab, 'Dashboard Kajian pDDI')
        if self.validation_authorized:
            self.tabs.addTab(self.validation_tab, "Validasi Klinis & UAT")
        self.tabs.addTab(self.safety_tab, "Keselamatan Obat")
        self.integration_scroll = QScrollArea()
        self.integration_scroll.setWidgetResizable(True)
        self.integration_scroll.setWidget(self.integration_tab)
        self.tabs.addTab(self.integration_scroll, 'Koneksi Khanza')
        self.audio_tab = AudioSettingsPanel(container, user)
        self.tabs.addTab(self.audio_tab, 'Suara Peringatan')
        self.tabs.addTab(self.catalog_tab, 'Master Obat')
        self.tabs.addTab(self.import_tab, 'Impor Pemetaan Obat')
        self.tabs.addTab(self.knowledge_tab, 'Pasangan Interaksi Obat')
        self.tabs.addTab(self.ddi_import_tab, 'Impor Data Interaksi')
        if container.settings.environment in {
            AppEnvironment.DEVELOPMENT,
            AppEnvironment.TEST,
        }:
            self.tabs.addTab(self.screening_tab, 'Simulasi Resep Dummy')
        if is_admin:
            self.tabs.addTab(self.backup_tab, 'Pencadangan & Pemulihan')
        self.open_simulator_button.clicked.connect(
            lambda: self.tabs.setCurrentWidget(self.screening_tab)
        )
        self.open_simulator_button.setVisible(
            container.settings.environment
            in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}
        )
        self.test_fullscreen_alert_button.setVisible(
            container.settings.environment
            in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}
        )
        if user.username == 'mode.farmasi':
            self.open_simulator_button.hide()
            self.test_fullscreen_alert_button.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addLayout(brand_header)
        layout.addLayout(identity_row)
        if container.settings.khanza_adapter.value == 'mysql_dummy':
            scope_label = ('Resep baru pasien dummy acuan ikut dipantau. ' if container.settings.khanza_dummy_follow_patients
                else 'Hanya resep dalam daftar uji. ')
            banner = QLabel('UJI DUMMY LOKAL — ' + scope_label +
                'Popup/suara: mayor atau kontraindikasi setelah validasi. DDI DRAFT; bukan keputusan klinis.')
            banner.setObjectName('localDummyBanner')
            banner.setWordWrap(True)
            banner.setStyleSheet('background: #FFF7D6; color: #854D0E; font-weight: 700; padding: 9px;')
            layout.addWidget(banner)
        if container.settings.environment == AppEnvironment.SILENT_PILOT:
            silent_banner = QLabel(
                "MODE SILENT PILOT — resep diproses dan dicatat untuk validasi, "
                "tetapi alert tray/popup operasional dinonaktifkan."
            )
            silent_banner.setObjectName("silentPilotBanner")
            silent_banner.setWordWrap(True)
            silent_banner.setStyleSheet(
                "background: #FFF7D6; color: #854D0E; font-weight: 700; "
                "padding: 9px; border: 1px solid #E8C85A; border-radius: 6px;"
            )
            layout.addWidget(silent_banner)
        elif container.settings.environment == AppEnvironment.ADVISORY_PILOT:
            self.advisory_banner = QLabel()
            self.advisory_banner.setWordWrap(True)
            self._render_advisory_banner()
            layout.addWidget(self.advisory_banner)
        self.monitoring_status = QLabel()
        self.monitoring_status.setObjectName('monitoringStatus')
        self.monitoring_status.setTextFormat(Qt.TextFormat.PlainText)
        self.monitoring_status.setWordWrap(True)
        self.monitoring_status.setStyleSheet('background: #EAF2FF; color: #123B5D; padding: 8px; border-radius: 5px;')
        self.integration_tab.monitoring_changed.connect(self.monitoring_status.setText)
        self.integration_tab.refresh_status()
        layout.addWidget(self.monitoring_status)
        self.navigation = WorkflowNavigation(self.tabs)
        def add(group, title, page, callback=None):
            if self.tabs.indexOf(page) >= 0:
                return self.navigation.add(group, title, page, callback)
        first = add('Pelayanan harian', 'Antrean Resep', self.queue_tab,
                    lambda: self.queue_tab.set_view('queue'))
        add('Pelayanan harian', 'Intervensi Apoteker', self.intervention_tab)
        add('Penelusuran', 'Riwayat Pemeriksaan', self.queue_tab,
            lambda: self.queue_tab.set_view('history'))
        add('Penelusuran', 'Riwayat Intervensi', self.intervention_tab)
        add('Penelusuran', 'Dashboard Kajian pDDI', self.dashboard_tab)
        add('Data referensi', 'Master Obat', self.catalog_tab)
        add('Data referensi', 'Impor Pemetaan Obat', self.import_tab)
        add('Data referensi', 'Pasangan Interaksi Obat', self.knowledge_tab)
        add('Data referensi', 'Impor Data Interaksi', self.ddi_import_tab)
        add('Data referensi', 'Keselamatan Obat', self.safety_tab)
        add('Pengaturan', 'Koneksi Khanza', self.integration_scroll)
        add('Pengaturan', 'Suara Peringatan', self.audio_tab)
        add('Pengaturan', 'Pencadangan & Pemulihan', self.backup_tab)
        add('Pengaturan', 'Status Sistem & Diagnostik', overview)
        add('Pengaturan', 'Validasi Klinis & UAT', self.validation_tab)
        add('Pengaturan', 'Simulasi Resep Dummy', self.screening_tab)
        if first is not None:
            self.navigation.tree.setCurrentItem(first)
        else:
            self.navigation._tab_changed(self.tabs.currentIndex())
        layout.addWidget(self.navigation, 1)
        help_menu = self.menuBar().addMenu('Bantuan')
        install_guide = help_menu.addAction('Panduan Instalasi Awal (PDF)')
        install_guide.triggered.connect(lambda: self._open_guide('Panduan-Instalasi-Awal-E-MAS-Farmasi.pdf'))
        usage_guide = help_menu.addAction('Panduan Penggunaan (PDF)')
        usage_guide.triggered.connect(lambda: self._open_guide('Panduan-Penggunaan-E-MAS-Farmasi.pdf'))
        about_menu = self.menuBar().addMenu('Tentang')
        about = about_menu.addAction('Tentang E-MAS Farmasi')
        about.setObjectName('aboutEmasFarmasi')
        about.triggered.connect(self._show_about)
        self.setCentralWidget(central)
        apply_contextual_icons(self)
        install_hover_feedback(self)

        self.refresh_health()
        self.outbox_timer = QTimer(self)
        self.outbox_timer.setInterval(3000)
        self.outbox_timer.timeout.connect(self._recover_outbox)
        self.outbox_timer.start()

    def _open_guide(self, filename: str) -> None:
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        guide = root / 'emss' / 'assets' / 'guides' / filename if hasattr(sys, '_MEIPASS') else root / 'assets' / 'guides' / filename
        if not guide.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide.resolve()))):
            QMessageBox.warning(self, 'Panduan tidak dapat dibuka',
                'File panduan tidak ditemukan atau tidak ada pembaca PDF yang tersedia.')

    def _show_about(self) -> None:
        """Present ownership and release identity separately from Help content."""
        dialog = QDialog(self)
        dialog.setObjectName('aboutEmasFarmasiDialog')
        dialog.setWindowTitle('Tentang E-MAS Farmasi')
        dialog.setMinimumWidth(620)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        title = QLabel('E-MAS Farmasi')
        title.setObjectName('aboutEmasTitle')
        title.setStyleSheet('font-size: 22pt; font-weight: 800; color: #123B5D;')
        subtitle = QLabel(
            'Sistem pendukung kajian resep dan potensi interaksi obat untuk '
            'membantu pelayanan kefarmasian yang aman dan bermutu.'
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet('color: #526372; font-size: 10.5pt;')
        release = QLabel(
            f'<b>Versi Saat Ini:</b> v{__version__}<br>'
            '<b>Tanggal Rilis Pertama:</b> 1 September 2026<br>'
            '<b>Pembaruan Terakhir:</b> 2 September 2026<br>'
            '<b>Pembaruan:</b> Ke-2'
        )
        release.setObjectName('aboutEmasRelease')
        release.setTextFormat(Qt.TextFormat.RichText)
        release.setStyleSheet('background: #EAF2FF; border: 1px solid #A9C4ED; '
                              'border-radius: 7px; padding: 12px; color: #123B5D;')
        team = QLabel('<b>Tim Pengembangan</b>')
        team.setStyleSheet('font-size: 13pt; color: #123B5D; margin-top: 6px;')
        people = QLabel(
            '<b>apt. Nuur Hanifah, S.Si., Sp.FRS.</b><br>'
            'Penggagas &amp; Penanggung Jawab Sistem<br><br>'
            '<b>apt. Achmad Fauzi Al\' Amrie, S.Farm.</b><br>'
            'Pengembang Aplikasi<br><br>'
            '<b>apt. Rini Purwandari, S.Far.</b><br>'
            'Koordinator Implementasi &amp; Evaluasi'
        )
        people.setObjectName('aboutEmasTeam')
        people.setTextFormat(Qt.TextFormat.RichText)
        people.setStyleSheet('color: #334155; padding-left: 4px;')
        validator = QLabel(
            '<b>Pengarah &amp; Validator Kefarmasian</b><br><br>'
            '<b>Komite Farmasi dan Terapi (KFT)</b><br>'
            'Pengarah dan Validator Aspek Kefarmasian'
        )
        validator.setObjectName('aboutEmasValidator')
        validator.setTextFormat(Qt.TextFormat.RichText)
        validator.setStyleSheet('background: #F8FAFC; border: 1px solid #CBD5E1; '
                                'border-radius: 7px; padding: 12px; color: #334155;')
        footer = QLabel(
            'E-MAS Farmasi © 2026\nDikembangkan untuk mendukung pelayanan '
            'kefarmasian yang efektif, terintegrasi, dan berorientasi pada mutu pelayanan.'
        )
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet('color: #526372; font-size: 9pt; margin-top: 4px;')
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(release)
        layout.addWidget(team)
        layout.addWidget(people)
        layout.addWidget(validator)
        layout.addWidget(footer)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(dialog, preferred_width=680, preferred_height=650)
        dialog.exec()

    def _recover_outbox(self):
        if self.tray_controller is not None:
            for screening_id in self.container.queue.pending_screening_ids():
                self._screening_completed(screening_id)

    def _delivery_allowed(self, queued):
        if not self.container.queue.allows(queued.item.care_setting):
            return False
        from emss.database.models import AppUser
        with self.container.database.session() as session:
            actor = session.get(AppUser, self.user.id)
            if not self.container.khanza_polling.monitor._actor_allowed(actor):
                return False
        if self.container.settings.environment == AppEnvironment.SILENT_PILOT or self._refresh_advisory_gate():
            return False
        if self.container.settings.environment == AppEnvironment.PRODUCTION:
            from sqlalchemy import select
            from emss.database.production_release_models import ProductionReleaseRecord
            with self.container.database.session() as session:
                latest = session.scalar(select(ProductionReleaseRecord).order_by(ProductionReleaseRecord.created_at.desc()).limit(1))
                release_id = latest.id if latest else None
            if not release_id or not self.container.production_release.evaluate(release_id).manual_deployment_authorized:
                return False
        from sqlalchemy import select
        from emss.database.monitoring_models import MonitorEvent, MonitorInbox
        with self.container.database.session() as session:
            event = session.scalar(select(MonitorEvent).where(MonitorEvent.screening_id == queued.item.screening_id))
            if event:
                import json
                if not self.container.queue.allows(json.loads(event.snapshot_json).get('header', {}).get('care_setting', 'UNKNOWN')):
                    return False
                current = session.get(MonitorInbox, (event.adapter_code, event.no_resep))
                if not current or current.event_id != event.id or current.state != 'COMPLETED':
                    return False
                if self.container.khanza_polling.status().connection_status != 'CONNECTED':
                    return None  # Defer NEW outbox messages until connection is rechecked.
        return True

    def _refresh_advisory_gate(self) -> bool:
        if self.container.settings.environment != AppEnvironment.ADVISORY_PILOT:
            self.advisory_gate_check_failed = False
            self.advisory_block_reason = None
            self.advisory_blocked = False
            return False
        try:
            status = self.container.clinical_validation.advisory_pilot_status()
            blocked = not status.active
        except Exception:
            LOGGER.exception(
                "Advisory authorization could not be evaluated; alerts blocked"
            )
            blocked = True
            self.advisory_gate_check_failed = True
            self.advisory_block_reason = "STATUS_UNAVAILABLE"
        else:
            self.advisory_gate_check_failed = False
            self.advisory_block_reason = status.reason
        self.advisory_blocked = blocked
        self._render_advisory_banner()
        return blocked

    def _render_advisory_banner(self) -> None:
        if self.advisory_banner is None:
            return
        if self.advisory_blocked:
            if self.advisory_gate_check_failed:
                reason = "otorisasi tidak dapat diverifikasi"
            elif self.advisory_block_reason == "EMERGENCY_STOP":
                reason = "emergency stop sedang aktif"
            elif self.advisory_block_reason == "ACTIVATION_EXPIRED":
                reason = "masa berlaku aktivasi telah berakhir"
            elif self.advisory_block_reason == "SHIFT_EXPIRED":
                reason = "masa tugas pemilik shift klinis telah berakhir"
            elif self.advisory_block_reason == "LEDGER_QUARANTINED":
                reason = "integritas ledger sesi pilot sedang dikarantina"
            elif self.advisory_block_reason == "NOT_ACTIVATED":
                reason = "gate lulus tetapi belum diaktifkan IT/Super Admin"
            else:
                reason = "gate atau ikatan otorisasi tidak lagi valid"
            self.advisory_banner.setText(
                f"MODE ADVISORY TERKUNCI — {reason}; hasil tetap disimpan "
                "tetapi alert operasional dinonaktifkan."
            )
            self.advisory_banner.setObjectName("advisoryPilotBlockedBanner")
            colors = (
                "background: #FEE2E2; color: #991B1B; "
                "border: 1px solid #FCA5A5;"
            )
        else:
            self.advisory_banner.setText(
                "MODE ADVISORY PILOT — gate validasi dan UAT telah lulus; "
                "alert bersifat rekomendasi dan tidak memblokir Khanza."
            )
            self.advisory_banner.setObjectName("advisoryPilotBanner")
            colors = (
                "background: #DCFCE7; color: #166534; "
                "border: 1px solid #86EFAC;"
            )
        self.advisory_banner.setStyleSheet(
            colors + " font-weight: 700; padding: 9px; border-radius: 6px;"
        )

    def configure_tray(
        self, controller: SystemTrayController | None
    ) -> None:
        self.tray_controller = controller
        if isinstance(controller, SystemTrayController):
            controller.preferences_path = self.container.settings.data_dir / 'audio-preferences.json'
            controller.delivery_allowed = self._delivery_allowed
            controller.alert_displayed.connect(self.container.queue.mark_alert_shown)
            controller.audio_delivered.connect(
                lambda alert_id: self.container.queue.mark_audio_outcome(alert_id, 'AUDIO_PLAYED')
            )
            controller.audio_failed.connect(
                lambda alert_id: self.container.queue.mark_audio_outcome(alert_id, 'AUDIO_FAILED')
            )
            controller.alert_suppressed.connect(lambda alert_id: self.container.queue.suppress_alert(alert_id, 'RUNTIME_GATE_BLOCKED'))

    @Slot()
    def _test_fullscreen_alert(self) -> None:
        if self.tray_controller is None:
            QMessageBox.information(
                self,
                "System tray belum aktif",
                "Aktifkan system tray lalu jalankan ulang aplikasi.",
            )
            return
        if self.tray_controller.schedule_fullscreen_test(3000):
            self.statusBar().showMessage(
                "Alert UJI akan muncul dalam 3 detik. Sekarang pindah ke "
                "aplikasi fullscreen.",
                8000,
            )

    @Slot(str)
    def _screening_completed(self, screening_id: str) -> None:
        try:
            queued = self.container.queue.enqueue_screening(screening_id)
        except ValueError as exc:
            self.statusBar().showMessage(
                f"Gagal memasukkan hasil ke antrean: {exc}", 10000
            )
            return
        self.queue_tab.refresh()
        self.intervention_tab.refresh()
        if self.dashboard_authorized:
            self.dashboard_tab.refresh()

        advisory_blocked = self._refresh_advisory_gate()
        suppression_reason = None
        if self.container.settings.environment == AppEnvironment.SILENT_PILOT:
            suppression_reason = "SILENT_PILOT"
        elif advisory_blocked:
            suppression_reason = (
                "ADVISORY_GATE_UNAVAILABLE"
                if self.advisory_gate_check_failed
                else (
                    "ADVISORY_EMERGENCY_STOP"
                    if self.advisory_block_reason == "EMERGENCY_STOP"
                    else (
                        "ADVISORY_AUTHORIZATION_EXPIRED"
                        if self.advisory_block_reason
                        == "ACTIVATION_EXPIRED"
                        else (
                            "ADVISORY_SHIFT_EXPIRED"
                            if self.advisory_block_reason == "SHIFT_EXPIRED"
                            else (
                            "ADVISORY_LEDGER_QUARANTINED"
                            if self.advisory_block_reason
                            == "LEDGER_QUARANTINED"
                            else (
                            "ADVISORY_NOT_ACTIVATED"
                            if self.advisory_block_reason == "NOT_ACTIVATED"
                            else "ADVISORY_GATE_BLOCKED"
                            )
                            )
                        )
                    )
                )
            )
        if suppression_reason and queued.alert_id:
            try:
                self.container.queue.suppress_alert(
                    queued.alert_id, suppression_reason
                )
            except Exception:
                LOGGER.exception(
                    "Operational alert was blocked but suppression state "
                    "could not be persisted"
                )

        if self.tray_controller is not None:
            if suppression_reason:
                self.tray_controller.update_summary(
                    self.container.queue.summary()
                )
                self.statusBar().showMessage(
                    (
                        (
                            "Advisory terkunci: gate tidak dapat diverifikasi; "
                            "hasil tersimpan dan alert tidak ditampilkan."
                            if self.advisory_gate_check_failed
                            else "Advisory terkunci: hasil tersimpan; alert "
                            "operasional tidak ditampilkan sampai gate lulus."
                        )
                        if advisory_blocked
                        else "Silent pilot: hasil tersimpan untuk validasi; "
                        "alert operasional tidak ditampilkan."
                    ),
                    10000,
                )
                return
            shown = self.tray_controller.show_screening_alert(queued)
            self.tray_controller.update_summary(self.container.queue.summary())
            if shown and queued.alert_id:
                self.container.queue.mark_alert_shown(queued.alert_id)

    @Slot(object)
    def _polling_completed(self, result: object) -> None:
        screening_ids = getattr(result, "screening_ids", ())
        # Each result is delivered from the worker immediately; no batch replay.
        # A fast idle poll must not rebuild the table and clear the recipe being read.
        changed = bool(screening_ids or getattr(result, 'failed', 0) or getattr(result, 'incomplete', 0))
        if not changed and monotonic() - getattr(self, '_last_poll_health_refresh', 0) < 10:
            return
        self._last_poll_health_refresh = monotonic()
        if not screening_ids and changed:
            self.queue_tab.refresh()
        self.refresh_health()
        if self.tray_controller is not None:
            self.tray_controller.update_summary(self.container.queue.summary())
        if screening_ids:
            self.statusBar().showMessage(
                f"Pemeriksaan Khanza memproses {len(screening_ids)} resep.", 8000
            )

    @Slot()
    def _change_password(self) -> None:
        dialog = ChangePasswordDialog(self.container, self.user, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self,
                "Password berhasil diubah",
                "Password baru sudah aktif dan akan digunakan pada login berikutnya.",
            )

    def refresh_health(self) -> None:
        result = self.container.health.check()
        self._render_health(result)

    def _render_health(self, result: HealthCheckResult) -> None:
        if not self.technical_authorized:
            from emss.ui.presentation import monitoring_text
            self.state_label.setText('Status pelayanan')
            self.detail_label.setText(monitoring_text(self.container.khanza_polling.status(),
                self.integration_tab.auto_button.isChecked())
                + ('\nGangguan sistem lokal; hubungi petugas IT.' if result.state is not HealthState.READY else ''))
            return
        if result.state is HealthState.READY:
            self.state_label.setText("READY")
            self.state_label.setStyleSheet(
                "background: #DDF7E8; color: #12633A; "
                "font-size: 16pt; font-weight: 700; border-radius: 6px;"
            )
        else:
            self.state_label.setText("ERROR")
            self.state_label.setStyleSheet(
                "background: #FDE7E7; color: #A10F18; "
                "font-size: 16pt; font-weight: 700; border-radius: 6px;"
            )
        details = [
            f"Database lokal: {'terhubung' if result.database_connected else 'gagal'}",
            f"Schema: {result.schema_revision or 'belum ada'}",
            f"Foreign keys: {'aktif' if result.foreign_keys_enabled else 'tidak aktif'}",
            f"Journal mode: {result.journal_mode or 'tidak diketahui'}",
            f"Rantai audit: {'valid' if result.audit_chain_valid else 'tidak valid'}",
            f"Khanza: {result.khanza_connection}",
        ]
        details.extend(result.details)
        self.detail_label.setText("\n".join(details))

    def restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def open_alert_queue(self) -> None:
        self.restore_window()
        if self.tabs.indexOf(self.queue_tab) >= 0:
            self.navigation.tree.setCurrentItem(
                self.navigation.groups['Pelayanan harian'].child(0)
            )
            self.queue_tab.set_view('queue')
            self.tabs.setCurrentWidget(self.queue_tab)
            if self.tray_controller is not None and self.tray_controller.current_queue_item_id:
                self.queue_tab.focus_item(self.tray_controller.current_queue_item_id)

    def quit_application(self) -> None:
        self.integration_tab.timer.stop()
        self.outbox_timer.stop()
        if self.tray_controller is not None:
            self.tray_controller.hide()
        self._force_close = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        should_hide = (
            not self._force_close
            and self.tray_controller is not None
            and self.tray_controller.tray.isVisible()
            and self.container.settings.minimize_to_tray
        )
        if should_hide:
            self.hide()
            event.ignore()
            self.statusBar().showMessage(
                "E-MAS tetap berjalan di system tray.", 5000
            )
            return
        event.accept()


def run_gui(container: ApplicationContainer) -> int:
    configure_windows_app_identity()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(container.settings.app_name)
    app.setOrganizationName("E-MAS Farmasi")
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    combo_arrow = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "combo-chevron-down.svg"
    )
    app.setStyleSheet(
        APP_STYLESHEET.replace(
            "__COMBO_ARROW_PATH__",
            combo_arrow.as_posix(),
        )
    )

    guard = (
        SingleInstanceGuard(container.settings.data_dir)
        if container.settings.single_instance
        else None
    )
    if guard is not None and not guard.acquire():
        return 0

    active_surface: dict[str, QWidget | None] = {"widget": None}

    def restore_active_surface() -> None:
        widget = active_surface["widget"]
        if widget is None:
            return
        widget.showNormal()
        widget.raise_()
        widget.activateWindow()

    if guard is not None:
        guard.activation_requested.connect(restore_active_surface)

    login = LoginDialog(container)
    active_surface["widget"] = login
    if login.exec() != QDialog.DialogCode.Accepted:
        if guard is not None:
            guard.close()
        return 0
    if login.authenticated_user is None:
        QMessageBox.critical(
            None, "Login gagal", "Sesi pengguna tidak berhasil dibuat."
        )
        if guard is not None:
            guard.close()
        return 1

    window = MainWindow(container, login.authenticated_user)
    active_surface["widget"] = window
    tray = SystemTrayController(window)
    window.configure_tray(tray)  # Visual fallback also works when Windows tray is unavailable.
    tray_enabled = container.settings.tray_enabled and tray.show()
    if tray_enabled:
        app.setQuitOnLastWindowClosed(False)
        tray.show_requested.connect(window.restore_window)
        tray.alert_open_requested.connect(window.open_alert_queue)
        tray.hide_requested.connect(window.hide)
        tray.quit_requested.connect(window.quit_application)
        tray.update_summary(container.queue.summary())
    if guard is not None:
        guard.activation_requested.connect(window.restore_window)
    window.show()
    try:
        return app.exec()
    finally:
        # Do not dispose the database while a backup, import, or polling
        # operation is still using it.
        QThreadPool.globalInstance().waitForDone(10000)
        tray.hide()
        if guard is not None:
            guard.close()
