from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.integrations.khanza import MockKhanzaAdapter
from emss.services.authentication import AuthenticatedUser
from emss.services.khanza_polling import PollingResult
from emss.services.catalog_sync import CatalogSyncService
from emss.integrations.khanza.credentials import credential_diagnostic
from pathlib import Path
from sqlalchemy import select, func
from emss.ui.presentation import monitoring_text
from emss.database.knowledge_models import KnowledgeBaseVersion, DdiRule


class _Signals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()
    screening_ready = Signal(str)


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
            self.signals.failed.emit(f"{type(exc).__name__}: operasi gagal")
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


class KhanzaIntegrationPanel(QWidget):
    polling_completed = Signal(object)
    screening_ready = Signal(str)
    catalog_changed = Signal()
    monitoring_changed = Signal(str)

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.technical_authorized = user.username != 'mode.farmasi' and bool(
            user.roles.intersection({'SUPER_ADMIN', 'IT_ADMIN'}))
        self.thread_pool = QThreadPool.globalInstance()
        self._busy = False
        self._worker: _Worker | None = None
        self.catalog_sync = CatalogSyncService(container.database, container.audit, container.khanza_adapter)

        title = QLabel("Integrasi SIMRS Khanza — READ ONLY")
        title.setStyleSheet("font-size: 15pt; font-weight: 700; color: #123B5D;")
        safety = QLabel(
            "E-MAS hanya menjalankan SELECT melalui view integrasi. Tidak ada "
            "INSERT, UPDATE, DELETE, perubahan stok, billing, atau resep Khanza."
        )
        safety.setWordWrap(True)
        safety.setStyleSheet(
            "background: #EAF2FF; border: 1px solid #A9C4ED; padding: 10px; "
            "border-radius: 6px;"
        )
        self.status_label = QLabel()
        self.status_label.setObjectName("khanzaStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background: white; border: 1px solid #CBD5E1; padding: 12px; "
            "border-radius: 6px;"
        )
        self.poll_button = QPushButton('Periksa Resep Sekarang')
        self.poll_button.setObjectName("primary")
        self.poll_button.clicked.connect(lambda: self.poll(force=True))
        self.auto_button = QPushButton('Mulai Pemeriksaan Otomatis')
        self.auto_button.setCheckable(True)
        self.auto_button.toggled.connect(self._toggle_auto)
        self.mock_button = QPushButton("Tambahkan Resep Uji ke Adapter")
        self.mock_button.setVisible(isinstance(container.khanza_adapter, MockKhanzaAdapter))
        self.mock_button.clicked.connect(self._seed_mock)

        actions = QHBoxLayout()
        actions.addWidget(self.poll_button)
        actions.addWidget(self.auto_button)
        actions.addWidget(self.mock_button)
        actions.addStretch()

        note = QLabel(
            "Mode MySQL memerlukan empat view: vw_emss_prescription_header, "
            "vw_emss_prescription_item, vw_emss_compound_item, dan "
            "vw_emss_drug_master. Password hanya dibaca dari environment "
            "EMSS_KHANZA_PASSWORD."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(title)
        layout.addWidget(safety)
        layout.addWidget(self.status_label)
        self.progress_table = QTableWidget(0, 5)
        self.progress_table.setHorizontalHeaderLabels(['Resep', 'Status Khanza', 'Proses E-MAS', 'Retry', 'Keterangan'])
        self.progress_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.progress_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.progress_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.progress_table.setMinimumHeight(160)
        layout.addWidget(self.progress_table)
        layout.addLayout(actions)
        layout.addWidget(note)
        self.retry_number = QLineEdit()
        self.retry_number.setPlaceholderText('Nomor resep untuk retry terarah (tidak menggeser cursor histori)')
        self.retry_reason = QLineEdit()
        self.retry_reason.setPlaceholderText('Alasan retry — tanpa nama pasien')
        self.retry_button = QPushButton('Jadwalkan Pemeriksaan Ulang Resep')
        self.retry_button.clicked.connect(self._retry)
        layout.addWidget(self.retry_number)
        layout.addWidget(self.retry_reason)
        layout.addWidget(self.retry_button)
        self.sync_button = QPushButton('1. Ambil Data Obat Khanza (pemetaan belum diaktifkan)')
        self.export_button = QPushButton('2. Simpan Pemetaan untuk Ditinjau')
        self.sync_button.clicked.connect(self._sync_master)
        self.export_button.clicked.connect(self._export_mapping)
        authorized = bool(user.roles.intersection({'SUPER_ADMIN', 'KNOWLEDGE_ADMIN', 'CLINICAL_REVIEWER'}))
        self.sync_button.setEnabled(authorized)
        self.export_button.setEnabled(authorized)
        layout.addWidget(self.sync_button)
        layout.addWidget(self.export_button)
        guide = QLabel('Isi workbook → tab Import: Preview → Commit PENDING_REVIEW → persetujuan reviewer. '
            'Publikasi KB dilakukan terpisah. Tutup ke tray tetap memantau; Keluar penuh menghentikan pemantauan. '
            'Polling internal bukan push dan tidak menahan validasi/cetak Khanza.')
        guide.setWordWrap(True)
        layout.addWidget(guide)
        if user.username == 'mode.farmasi':
            for widget in (note, self.progress_table, self.retry_number, self.retry_reason,
                    self.retry_button, self.sync_button, self.export_button, guide):
                widget.hide()
        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(container.settings.khanza_poll_interval_seconds * 1000)
        self.timer.timeout.connect(lambda: self.poll(force=False))
        self.refresh_status()
        if container.settings.khanza_polling_enabled and container.settings.khanza_internal_polling_consent:
            QTimer.singleShot(0, lambda: self.auto_button.setChecked(True))

    @Slot()
    def refresh_status(self) -> None:
        status = self.container.khanza_polling.status()
        self.monitoring_changed.emit(monitoring_text(status, self.auto_button.isChecked()))
        if not self.technical_authorized:
            self.status_label.setText(monitoring_text(status, self.auto_button.isChecked()))
            return
        monitoring = self.container.khanza_polling.monitor.summary()
        catalog = self.container.catalog.summary()
        with self.container.database.session() as session:
            published = session.scalar(select(func.count()).select_from(KnowledgeBaseVersion).where(KnowledgeBaseVersion.status == 'PUBLISHED'))
        self.status_label.setText(
            f"Adapter: {status.adapter.upper()}\n"
            f"Layanan instalasi: {self.container.settings.pharmacy_care_setting or 'BELUM DIPILIH — buka Mode Farmasi'}\n"
            f"Koneksi: {status.connection_status}\n"
            f"Pemantauan: {'AKTIF (pemeriksaan berkala)' if self.auto_button.isChecked() else 'BERHENTI'}\n"
            f"Interval penemuan resep: {self.container.settings.khanza_poll_interval_seconds} detik; "
            f"jeda baca stabil: {max(2, self.container.settings.khanza_stability_interval_seconds):g} detik\n"
            f"Checkpoint replay histori: {'tersedia' if status.cursor else 'belum ada'}\n"
            f"KB PUBLISHED: {published}; master: {catalog.total_drugs}; mapping disetujui: {catalog.approved}\n"
            f"Antrean: {monitoring['states']}; backlog lokal: {monitoring['backlog']} (bukan total sumber)\n"
            f"Hasil terakhir: {monitoring['last_result']}\n"
            f"Kegagalan beruntun: {status.consecutive_failures}\n"
            f"Reconnect berikutnya: {status.next_retry_at or '-'}\n"
            f"Sukses terakhir: {status.last_success_at or '-'}\n"
            f"Pesan: {status.last_error or '-'}"
            + '\n' + '\n'.join(monitoring['errors'])
            + ('\n' + credential_diagnostic() if status.adapter == 'mysql' else '')
            + ('\nUJI DUMMY: DRAFT dan mapping sumber dipakai hanya untuk pengujian; '
               'angka PUBLISHED/disetujui di atas tetap status klinis aslinya. '
               + ('Resep acuan pasien dummy (resep barunya ikut dipantau): ' if self.container.settings.khanza_dummy_follow_patients
                else 'Daftar resep: ') + ', '.join(self.container.settings.khanza_dummy_prescriptions)
               if status.adapter == 'mysql_dummy' else '')
        )
        progress = self.container.khanza_polling.monitor.progress()
        self.progress_table.setRowCount(len(progress))
        for i, row in enumerate(progress):
            for j, value in enumerate(row):
                self.progress_table.setItem(i, j, QTableWidgetItem(value))

    @Slot(bool)
    def _toggle_auto(self, enabled: bool) -> None:
        if enabled and not self.container.settings.khanza_internal_polling_consent:
            self.auto_button.blockSignals(True)
            self.auto_button.setChecked(False)
            self.auto_button.blockSignals(False)
            self.status_label.setText('Persetujuan polling internal belum dicatat di konfigurasi. Prototipe tidak diaktifkan otomatis.')
            return
        self.auto_button.setText(
            'Hentikan Pemeriksaan Otomatis' if enabled else 'Mulai Pemeriksaan Otomatis'
        )
        if enabled:
            self.timer.start()
            self.poll(force=True)
        else:
            self.timer.stop()
        self.refresh_status()

    def _retry(self):
        try:
            self.container.khanza_polling.monitor.request_retry(self.retry_number.text().strip(), self.user.id, self.retry_reason.text())
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText('Retry tersimpan. Dua pembacaan stabil tetap wajib; histori tidak dihapus.')

    def _sync_master(self):
        if self._busy:
            return
        self._busy = True
        self._poll_started_at = monotonic()
        self.sync_button.setEnabled(False)
        worker = _Worker(lambda: self.catalog_sync.sync(self.user.id))
        worker.signals.succeeded.connect(self._synced)
        worker.signals.failed.connect(self._poll_failed)
        worker.signals.finished.connect(self._finish_poll)
        self._worker = worker
        self.thread_pool.start(worker)

    def _synced(self, result):
        self.catalog_changed.emit()
        self.status_label.setText(f'Master terbaca {result.read}, baru {result.inserted}, dipreservasi {result.preserved}. '
            'Belum ada mapping yang diaktifkan. Simpan workbook lalu isi zat aktif dan lakukan preview/import.')

    def _export_mapping(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'Simpan Workbook Mapping',
            str(self.container.settings.export_dir / 'mapping-review.xlsx'), 'Workbook (*.xlsx)')
        if filename:
            try:
                self.catalog_sync.export_mapping_workbook(Path(filename), self.user.id)
                self.status_label.setText('Workbook tersimpan. Baca sheet PETUNJUK lalu gunakan tab Import.')
            except (ValueError, OSError):
                self.status_label.setText('Workbook gagal disimpan; periksa izin folder dan role pengguna.')

    @Slot()
    def _seed_mock(self) -> None:
        try:
            no_resep = self.container.khanza_polling.seed_mock_prescription()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText(
            f"Resep {no_resep} ditambahkan. Klik Periksa Resep Sekarang."
        )

    def poll(self, *, force: bool) -> None:
        if self._busy:
            return
        self._busy = True
        self._poll_started_at = monotonic()
        self.poll_button.setEnabled(False)
        self.poll_button.setText("Membaca Khanza…")
        self.auto_button.setEnabled(False)
        self.status_label.setText("Membaca Khanza di latar belakang…")
        worker = _Worker(
            lambda: self.container.khanza_polling.monitor.cycle(
                self.user.id, force=force, on_result=worker.signals.screening_ready.emit
            )
        )
        worker.signals.screening_ready.connect(self.screening_ready)
        worker.signals.succeeded.connect(self._poll_succeeded)
        worker.signals.failed.connect(self._poll_failed)
        worker.signals.finished.connect(self._finish_poll)
        self._worker = worker
        self.thread_pool.start(worker)

    def prepare_for_restore(self) -> bool:
        """Stop scheduled polling before the local database is replaced."""
        if self._busy:
            return False
        if self.auto_button.isChecked():
            self.auto_button.setChecked(False)
        self.timer.stop()
        return True

    @Slot()
    def _finish_poll(self) -> None:
        self._busy = False
        self.poll_button.setEnabled(True)
        self.poll_button.setText('Periksa Resep Sekarang')
        self.auto_button.setEnabled(True)
        self._worker = None
        self.sync_button.setEnabled(bool(self.user.roles.intersection({'SUPER_ADMIN', 'KNOWLEDGE_ADMIN', 'CLINICAL_REVIEWER'})))
        if self.auto_button.isChecked():
            try:
                delay = self.container.khanza_polling.monitor.next_poll_delay_ms()
            except Exception:
                delay = self.container.settings.khanza_poll_interval_seconds * 1000
            # Account for worker/UI time, so a 1-second period does not drift to
            # 1 second plus processing time on every observation. Never overlap.
            elapsed = int((monotonic() - getattr(self, '_poll_started_at', monotonic())) * 1000)
            period_remaining = max(100, self.container.settings.khanza_poll_interval_seconds * 1000 - elapsed)
            delay = min(delay, period_remaining)
            self.timer.start(delay)

    @Slot(object)
    def _poll_succeeded(self, result: PollingResult) -> None:
        self.refresh_status()
        if result.status == 'SCOPE_NOT_READY':
            self.status_label.setText(self.status_label.text() + '\n' + result.message)
            self.monitoring_changed.emit('Pemantauan belum siap: ' + result.message)
        if result.failed:
            self.monitoring_changed.emit(
                monitoring_text(self.container.khanza_polling.status(), self.auto_button.isChecked())
                + f'\n{result.failed} resep gagal diperiksa. '
                + (result.message or 'Lihat keterangan pada Koneksi Khanza.')
            )
        self.status_label.setText(
            self.status_label.text()
            + f"\nHasil terakhir: {result.status}; terdeteksi {result.detected}, "
            f"stabil {result.stable}, diproses {result.processed}, "
            f"menunggu data resep {result.incomplete}, gagal {result.failed}."
        )
        self.polling_completed.emit(result)

    @Slot(str)
    def _poll_failed(self, message: str) -> None:
        self.refresh_status()
        self.status_label.setText(self.status_label.text() + f"\n{message}")
        self.monitoring_changed.emit(
            monitoring_text(self.container.khanza_polling.status(), self.auto_button.isChecked())
            + '\nPemeriksaan gagal: ' + message
        )
