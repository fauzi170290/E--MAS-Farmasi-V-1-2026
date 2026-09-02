from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.backup import BackupRecord, RestoreResult


class _Signals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _Worker(QRunnable):
    def __init__(self, function: Callable[[], object]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.function = function
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                # The application can be closing after the operation itself
                # has safely completed.
                pass
        else:
            try:
                self.signals.succeeded.emit(result)
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass


class BackupPanel(QWidget):
    restart_required = Signal()

    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
        restore_guard: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.restore_guard = restore_guard
        self.thread_pool = QThreadPool.globalInstance()
        self._worker: _Worker | None = None
        self._operation = ""
        self._authorized = bool(user.roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))

        title = QLabel('Pencadangan & Pemulihan')
        title.setStyleSheet("font-size: 15pt; font-weight: 700; color: #123B5D;")
        explanation = QLabel(
            "Backup menyimpan database lokal, checksum SHA-256, dan snapshot "
            "konfigurasi nonsensitif. Password Khanza tidak pernah disalin."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(
            "background: #EAF2FF; border: 1px solid #A9C4ED; padding: 10px; "
            "border-radius: 6px;"
        )
        self.status_label = QLabel("Siap.")
        self.status_label.setObjectName("backupStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background: white; border: 1px solid #CBD5E1; padding: 10px; "
            "border-radius: 6px;"
        )

        self.manual_button = QPushButton('Buat Cadangan Sekarang')
        self.manual_button.setObjectName("createManualBackup")
        self.manual_button.clicked.connect(self.create_manual)
        self.verify_button = QPushButton("Verifikasi Terpilih")
        self.verify_button.setObjectName("verifyBackup")
        self.verify_button.clicked.connect(self.verify_selected)
        self.restore_button = QPushButton('Pulihkan Cadangan Terpilih')
        self.restore_button.setObjectName("restoreBackup")
        self.restore_button.clicked.connect(self.restore_selected)
        self.refresh_button = QPushButton("Muat Ulang Riwayat")
        self.refresh_button.setObjectName("refreshBackups")
        self.refresh_button.clicked.connect(self.refresh)

        actions = QHBoxLayout()
        actions.addWidget(self.manual_button)
        actions.addWidget(self.verify_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch()

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("backupHistory")
        self.table.setHorizontalHeaderLabels(
            ["Waktu", "Alasan", "Ukuran", "Schema", "Checksum", "File"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_actions)
        header = self.table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        warning = QLabel(
            "Restore mengganti database aktif. Sistem otomatis membuat safety "
            "backup sebelum restore dan aplikasi harus dijalankan ulang sesudahnya."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; padding: 10px; "
            "border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(self.status_label)
        layout.addLayout(actions)
        layout.addWidget(self.table, 1)
        layout.addWidget(warning)
        self.manual_button.setProperty('primaryAction', True)
        self.restore_button.setProperty('danger', True)
        layout.addWidget(self.restore_button)

        self.refresh()
        QTimer.singleShot(0, self._create_daily_if_due)

    @Slot()
    def refresh(self) -> None:
        records = self.container.backup.list_backups()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            checksum = record.checksum_sha256
            values = [
                record.created_at.replace("T", " ")[:19],
                record.reason,
                self._format_size(record.size_bytes),
                record.schema_revision or "-",
                f"{checksum[:12]}…" if checksum else "-",
                record.database_path.name,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(record.database_path))
                self.table.setItem(row, column, item)
        self._update_actions()

    @Slot()
    def create_manual(self) -> None:
        self._start(
            "BACKUP",
            "Membuat backup dan menghitung checksum…",
            lambda: self.container.backup.create_backup("MANUAL", self.user.id),
        )

    @Slot()
    def verify_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        self._start(
            "VERIFY",
            "Memverifikasi checksum, schema, dan integritas…",
            lambda: self.container.backup.verify_backup(path, self.user.id),
        )

    @Slot()
    def restore_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        answer = QMessageBox.warning(
            self,
            "Konfirmasi Restore",
            "Database aktif akan diganti dengan backup terpilih. Perubahan "
            "setelah waktu backup akan hilang dari database aktif, tetapi safety "
            "backup dibuat terlebih dahulu. Lanjutkan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.restore_guard is not None and not self.restore_guard():
            QMessageBox.information(
                self,
                "Restore belum dapat dimulai",
                "Polling Khanza masih berjalan. Tunggu hingga selesai lalu coba lagi.",
            )
            return
        self._start(
            "RESTORE",
            "Memverifikasi dan memulihkan database…",
            lambda: self.container.backup.restore_backup(path, self.user.id),
        )

    @Slot()
    def _create_daily_if_due(self) -> None:
        if self._worker is None:
            self._start(
                "DAILY",
                "Memeriksa jadwal backup harian…",
                self.container.backup.create_daily_if_due,
            )

    def _start(self, operation: str, message: str, function: Callable[[], object]) -> None:
        if self._worker is not None:
            return
        self._operation = operation
        self.status_label.setText(message)
        self._set_busy(True)
        worker = _Worker(function)
        worker.signals.succeeded.connect(self._succeeded)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finished)
        self._worker = worker
        self.thread_pool.start(worker)

    @Slot(object)
    def _succeeded(self, result: object) -> None:
        if self._operation == "DAILY" and result is None:
            self.status_label.setText("Backup harian hari ini sudah tersedia.")
        elif isinstance(result, RestoreResult):
            self.status_label.setText(
                f"Restore berhasil. Safety backup: {result.safety_backup.name}."
            )
            QMessageBox.information(
                self,
                "Restore berhasil",
                "Database berhasil dipulihkan dan diverifikasi. Aplikasi akan "
                "ditutup; jalankan kembali E-MAS untuk memakai data hasil restore.",
            )
            self.restart_required.emit()
        elif isinstance(result, BackupRecord) and self._operation == "VERIFY":
            self.status_label.setText(
                f"Valid: checksum dan integritas {result.database_path.name} sesuai."
            )
        elif isinstance(result, BackupRecord):
            self.status_label.setText(
                f"Backup selesai: {result.database_path.name} "
                f"({self._format_size(result.size_bytes)})."
            )
        self.refresh()

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.status_label.setText(f"Operasi gagal: {message}")
        QMessageBox.critical(self, "Backup & Restore gagal", message)

    @Slot()
    def _finished(self) -> None:
        self._worker = None
        self._operation = ""
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.manual_button.setEnabled(self._authorized and not busy)
        self.refresh_button.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self._update_actions(busy=busy)

    @Slot()
    def _update_actions(self, *, busy: bool = False) -> None:
        selected = self._selected_path() is not None
        enabled = self._authorized and selected and not busy and self._worker is None
        self.verify_button.setEnabled(enabled)
        self.restore_button.setEnabled(enabled)

    def _selected_path(self) -> Path | None:
        model = self.table.selectionModel()
        selected = model.selectedRows() if model else []
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return Path(str(value)) if value else None

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"
