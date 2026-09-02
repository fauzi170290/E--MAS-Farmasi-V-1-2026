from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QTime, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.config.settings import AppEnvironment
from emss.services.authentication import AuthenticatedUser
from emss.services.queue import QueueDetail, QueueError, QueueItem
from emss.ui.intervention import InterventionDialog
from emss.ui.presentation import status_text, local_time
from emss.ui.action_identity import ActionIdentityDialog


class QueuePanel(QWidget):
    queue_changed = Signal()
    screening_completed = Signal(str)

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.setObjectName("queuePanel")
        self.container = container
        self.user = user
        self.current_item_id: str | None = None
        self.current_detail = None

        self.summary_label = QLabel()
        self.summary_label.setObjectName("queueSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background: #EAF2FF; border: 1px solid #A9C4ED; "
            "padding: 10px; border-radius: 6px; font-weight: 600;"
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari nomor resep, nomor RM, atau pasien")
        self.search.returnPressed.connect(self.refresh)
        self.unit_filter = QComboBox()
        self.unit_filter.addItem("Semua unit/depo", "")
        self.unit_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Semua status", "")
        for value in (
            "NEW",
            "REVIEWED",
            "CRITICAL",
            "HIGH_RISK",
            "UNMAPPED",
            "NOT_ASSESSED",
            "ERROR",
            "FAILED",
            "DEAD_LETTER",
        ):
            self.status_filter.addItem(status_text(value), value)
        self.status_filter.addItem('Semua yang perlu perhatian', 'ATTENTION')
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.date_filter = QComboBox()
        self.date_filter.setObjectName("queueDateFilter")
        self.date_filter.addItem("Hasil efektif hari ini", "TODAY")
        self.date_filter.addItem("Semua data / Riwayat", "ALL")
        self.date_filter.currentIndexChanged.connect(self.refresh)
        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.setObjectName("refreshQueue")
        self.refresh_button.clicked.connect(self.request_refresh)
        self.refresh_feedback = QLabel("Siap.")
        self.refresh_feedback.setObjectName("queueRefreshFeedback")
        self.refresh_feedback.setStyleSheet("color: #526372;")
        self.mock_critical_button = QPushButton('Simulasikan Risiko Kritis')
        self.mock_critical_button.setObjectName("simulateDummyQueue")
        self.mock_critical_button.setVisible(
            container.settings.environment
            in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}
        )
        self.mock_critical_button.clicked.connect(self._simulate_critical)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 2)
        filters.addWidget(self.date_filter, 1)
        filters.addWidget(self.unit_filter, 1)
        filters.addWidget(self.status_filter, 1)
        filters.addWidget(self.mock_critical_button)
        filters.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("processingQueue")
        self.table.setHorizontalHeaderLabels(
            [
                "Waktu",
                "No. Resep",
                "Pasien",
                "Unit/Depo",
                "Hasil pemeriksaan",
                'Peringatan',
                'Tinjauan',
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)

        self.detail_label = QLabel("Pilih resep untuk melihat hasil gabungan.")
        self.detail_label.setObjectName("queueDetail")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(
            "background: white; border: 1px solid #CBD5E1; "
            "padding: 10px; border-radius: 5px;"
        )
        self.detail_table = QTableWidget(0, 4)
        self.detail_table.setHorizontalHeaderLabels(
            ["Jenis Temuan", "Pasangan Obat", "Status", "Rekomendasi/Keterangan"]
        )
        self.detail_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.detail_table.horizontalHeader().setMinimumSectionSize(145)
        self.mapping_label = QLabel('Kendala Pemetaan Obat')
        self.mapping_label.setStyleSheet('font-weight: 700; color: #854D0E;')
        self.mapping_table = QTableWidget(0, 3)
        self.mapping_table.setHorizontalHeaderLabels(['Kode Obat', 'Nama Obat', 'Keterangan'])
        self.mapping_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.mapping_table.setMaximumHeight(140)
        self.mapping_label.hide()
        self.mapping_table.hide()

        self.review_button = QPushButton("Tandai Sudah Ditinjau")
        self.review_button.setObjectName("markReviewed")
        self.review_button.setToolTip('Mencatat bahwa hasil telah ditinjau; bukan persetujuan terapi.')
        self.review_button.clicked.connect(self._acknowledge)
        self.retry_button = QPushButton('Coba Periksa Ulang')
        self.retry_button.clicked.connect(self._retry)
        self.intervention_button = QPushButton("Catat Intervensi Apoteker")
        self.intervention_button.setObjectName("primary")
        self.intervention_button.clicked.connect(self._open_intervention)
        self.review_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.intervention_button.setEnabled(False)
        if user.username == "mode.farmasi":
            self.review_button.setToolTip(
                "Verifikasi akun petugas untuk mencatat tinjauan; Mode Farmasi tetap aktif."
            )

        actions = QHBoxLayout()
        actions.addWidget(self.intervention_button)
        actions.addWidget(self.review_button)
        actions.addWidget(self.retry_button)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.summary_label)
        safety = QLabel('Hasil berdasarkan obat yang terbaca. Kendala pembacaan, obat belum terpetakan, dan pasangan belum dinilai tersedia pada rincian resep.')
        safety.setWordWrap(True)
        safety.setStyleSheet('color: #854D0E; background: #FFF7D6; padding: 8px; font-weight: 600;')
        layout.addWidget(safety)
        layout.addLayout(filters)
        layout.addWidget(self.refresh_feedback)
        layout.addWidget(self.table, 3)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.detail_table, 2)
        layout.addWidget(self.mapping_label)
        layout.addWidget(self.mapping_table)
        layout.addLayout(actions)
        self.refresh()

    def set_view(self, mode: str) -> None:
        self.date_filter.blockSignals(True)
        self.date_filter.setCurrentIndex(
            # Riwayat Pemeriksaan is a place to inspect screening results, not
            # an instruction to load every historical row by default.  Keep
            # the operational-day boundary here; users can deliberately pick
            # "Semua data / Riwayat" when tracing an older prescription.
            self.date_filter.findData("TODAY")
        )
        self.date_filter.blockSignals(False)
        self.status_filter.blockSignals(True)
        self.status_filter.setCurrentIndex(self.status_filter.findData('ATTENTION' if mode == 'attention' else ''))
        self.status_filter.blockSignals(False)
        self.search.clear()
        self.refresh()
        if mode == 'history':
            self.search.setFocus()

    @Slot()
    def request_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Memuat…")
        self.refresh_feedback.setText("Memuat antrean dan alert…")
        QTimer.singleShot(0, self._complete_requested_refresh)

    @Slot()
    def _complete_requested_refresh(self) -> None:
        try:
            self.refresh()
        finally:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("✓ Selesai")
            self.refresh_feedback.setText(
                "Antrean berhasil diperbarui pukul "
                f"{QTime.currentTime().toString('HH:mm:ss')}."
            )

    @Slot()
    def refresh(self) -> None:
        selected_unit = self.unit_filter.currentData() or ""
        date_mode = self.date_filter.currentData() or "TODAY"
        detected_after = detected_before = None
        if date_mode == "TODAY":
            # The user sees the workstation's operational day.  Values remain
            # stored in UTC; only this display boundary is converted.
            local_now = datetime.now().astimezone()
            today = local_now.date()
            detected_after = datetime(today.year, today.month, today.day, tzinfo=local_now.tzinfo).astimezone(UTC)
            detected_before = detected_after + timedelta(days=1)
        include_history = date_mode == 'ALL'
        units = self.container.queue.list_units(
            detected_after=detected_after,
            detected_before=detected_before,
            include_history=include_history,
        )
        self.unit_filter.blockSignals(True)
        self.unit_filter.clear()
        self.unit_filter.addItem("Semua unit/depo", "")
        selected_index = 0
        for unit in units:
            self.unit_filter.addItem(unit, unit)
            if unit == selected_unit:
                selected_index = self.unit_filter.count() - 1
        self.unit_filter.setCurrentIndex(selected_index)
        self.unit_filter.blockSignals(False)
        summary = self.container.queue.summary(
            detected_after=detected_after,
            detected_before=detected_before,
            include_history=include_history,
        )
        self.summary_label.setText(
            f"Total {summary.total} {('hasil efektif hari ini' if date_mode == 'TODAY' else 'baris riwayat')} · Baru {summary.new} · "
            f"Risiko tinggi {summary.high_risk} · Kritis {summary.critical} · "
            f"Gagal berulang {summary.dead_letter}"
        )
        rows = self.container.queue.list_items(
            service_unit=self.unit_filter.currentData() or "",
            status=self.status_filter.currentData() or "",
            search=self.search.text(),
            detected_after=detected_after,
            detected_before=detected_before,
            include_history=include_history,
        )
        self._render_rows(rows)

    def _render_rows(self, rows: list[QueueItem]) -> None:
        selected_id = self.current_item_id
        self.table.blockSignals(True)
        colors = {
            "CRITICAL": "#FECACA",
            "HIGH_RISK": "#FED7AA",
            "REVIEW": "#FEF3C7",
            "INFO": "#DBEAFE",
            "SAFE": "#DCFCE7",
            "UNMAPPED": "#FDE68A",
            "INCOMPLETE": "#FDE68A",
            "ERROR": "#FCA5A5",
        }
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                local_time(row.detected_at),
                row.no_resep,
                row.patient_label,
                row.service_unit,
                ('Riwayat revisi · ' if not row.is_effective else '') + ('Belum dapat disimpulkan' if row.risk_status == 'SAFE' and row.completeness_status != 'COMPLETE' else status_text(row.risk_status)),
                status_text(row.alert_level),
                (f"✓ {status_text(row.review_status)} · {local_time(row.reviewed_at)}"
                 if row.review_status == 'REVIEWED' else status_text(row.review_status)),
            )
            background = colors.get(
                row.completeness_status
                if row.completeness_status != "COMPLETE"
                else row.risk_status
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, row.id)
                if background:
                    item.setBackground(QColor(background))
                if column == 6 and row.review_status == 'REVIEWED':
                    item.setBackground(QColor('#D1FAE5'))
                if column == 4 and row.risk_status in {'HIGH_RISK', 'CRITICAL'}:
                    item.setForeground(QColor('#B91C1C'))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row_index, column, item)
        self.table.clearSelection()
        self.table.blockSignals(False)
        if selected_id:
            self.focus_item(selected_id)
        self._fit_queue_columns()
        if rows and not self.table.selectedItems():
            self.current_item_id = None
            self.current_detail = None
            self.mapping_label.hide()
            self.mapping_table.hide()
            self.detail_label.setText('Hasil tersedia. Pilih satu resep untuk melihat rincian skrining dan tindakan.')
            self.detail_table.setRowCount(0)
            self.review_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.intervention_button.setEnabled(False)
        if not rows:
            self.current_item_id = None
            self.current_detail = None
            self.mapping_label.hide()
            self.mapping_table.hide()
            self.detail_label.setText(
                "Belum ada hasil yang sesuai filter. Periksa status pemantauan, "
                "kesiapan data interaksi dan pemetaan kandungan, dan progres pada halaman Koneksi Khanza."
            )
            self.detail_table.setRowCount(0)
            self.review_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.intervention_button.setEnabled(False)

    @Slot()
    def _selection_changed(self) -> None:
        selected = self.table.selectedItems()
        if not selected:
            self.current_item_id = None
            self.current_detail = None
            self.detail_table.setRowCount(0)
            self.mapping_label.hide()
            self.mapping_table.hide()
            self.detail_label.setText('Pilih resep untuk melihat hasil gabungan.')
            self.review_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.intervention_button.setEnabled(False)
            return
        item_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if not item_id:
            return
        self.current_item_id = str(item_id)
        try:
            detail = self.container.queue.get_detail(self.current_item_id)
        except QueueError as exc:
            self.current_item_id = None
            self.current_detail = None
            self.detail_table.setRowCount(0)
            self.mapping_label.hide()
            self.mapping_table.hide()
            self.review_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.intervention_button.setEnabled(False)
            self.detail_label.setText(str(exc))
            return
        self._render_detail(detail)

    def focus_item(self, item_id):
        for index in range(self.table.rowCount()):
            cell = self.table.item(index, 0)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == item_id:
                self.table.selectRow(index)
                self.table.scrollToItem(cell)
                return

    def _fit_queue_columns(self):
        self.table.setWordWrap(True)
        available = max(760, self.table.viewport().width())
        weights = (0.10, 0.15, 0.17, 0.11, 0.23, 0.11, 0.13)
        for col, weight in enumerate(weights):
            self.table.setColumnWidth(col, int(available * weight))
        self.table.resizeRowsToContents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_queue_columns()
        self._fit_detail_columns()

    def _fit_detail_columns(self):
        for table, weights in (
            (self.detail_table, (0.15, 0.25, 0.15, 0.45)),
            (self.mapping_table, (0.17, 0.25, 0.58)),
        ):
            available = max(760, table.viewport().width() - 2)
            table.setWordWrap(True)
            for column, weight in enumerate(weights[:-1]):
                table.setColumnWidth(column, int(available * weight))
            table.resizeRowsToContents()

    def _render_detail(self, detail: QueueDetail) -> None:
        self.current_detail = detail
        item = detail.item
        hold = " · Disarankan menunda untuk tinjauan" if item.hold_recommended else ""
        displayed_number = item.no_resep
        self.detail_label.setText(
            f"Resep {displayed_number} · revisi {item.revision_number or '-'} · "
            f"{'riwayat revisi · ' if not item.is_effective else ''}hasil {('Belum dapat disimpulkan' if item.risk_status == 'SAFE' and item.completeness_status != 'COMPLETE' else status_text(item.risk_status))}{hold}"
            + (f" · ✓ hasil revisi ini ditinjau {local_time(item.reviewed_at)}" if item.reviewed_at else '')
            + (" · Evaluasi ulang konteks lintas resep sedang dijadwalkan; hasil ini belum menjadi kesimpulan akhir." if item.context_pending else '')
        )
        rows = [
            (
                ("DDI lintas resep" if pair.classification == 'INTERACTION_FOUND' else "Penilaian lintas resep")
                if pair.provenance else ("Interaksi Obat" if pair.classification == 'INTERACTION_FOUND' else "Pasangan Dinilai"),
                pair.pair_key.replace(' || ', ' vs '),
                status_text(pair.severity) if pair.classification == 'INTERACTION_FOUND' else status_text(pair.classification),
                pair.recommendation + ("\n" + " ↔ ".join(
                    f"Resep {pair.provenance[side]['no_resep']} · {pair.provenance[side].get('changed_at') or 'waktu tidak diketahui'} · "
                    f"{pair.provenance[side].get('service_unit') or '-'} · dr. {pair.provenance[side].get('prescriber_name') or '-'}"
                    for side in ('current', 'previous')) + "\nPastikan obat masih digunakan; perlu rekonsiliasi."
                    if pair.provenance else ""),
            )
            for pair in detail.pairs
        ]
        rows.extend(
            (
                "Duplikasi Obat" if issue.issue_type == 'DUPLICATE_THERAPY' else "Kendala Pemeriksaan",
                issue.reference.replace(' || ', ' vs '),
                status_text(issue.severity) if issue.severity else status_text(issue.issue_type),
                issue.message,
            )
            for issue in detail.issues if issue.issue_type != 'DRUG_UNMAPPED'
        )
        self.detail_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                cell = QTableWidgetItem(value)
                if row[2] in {'Kontraindikasi', 'Mayor', 'Risiko kritis', 'Risiko tinggi'}:
                    cell.setForeground(QColor('#B91C1C'))
                    font = cell.font()
                    font.setBold(True)
                    cell.setFont(font)
                self.detail_table.setItem(row_index, column, cell)
        mapping = [issue for issue in detail.issues if issue.issue_type == 'DRUG_UNMAPPED']
        self.mapping_label.setVisible(bool(mapping))
        self.mapping_table.setVisible(bool(mapping))
        self.mapping_table.setRowCount(len(mapping))
        for index, issue in enumerate(mapping):
            for column, value in enumerate((issue.reference, issue.display_name or 'Nama belum tersedia', issue.message)):
                self.mapping_table.setItem(index, column, QTableWidgetItem(value))
        self._fit_detail_columns()
        can_review = (
            bool(self.user.roles.intersection({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN'}))
            and item.review_status == "NEW"
        )
        self.review_button.setEnabled(can_review)
        self.review_button.setToolTip('Catat tinjauan hasil; bukan persetujuan terapi dan tidak membuat intervensi.'
            + (' Akun petugas akan diverifikasi.' if self.user.username == 'mode.farmasi' else ''))
        self.intervention_button.setEnabled(
            self.user.username != "mode.farmasi"
            and bool(
                self.user.roles.intersection(
                    {"APOTEKER", "SUPER_ADMIN", "CLINICAL_REVIEWER"}
                )
            )
        )
        self.retry_button.setEnabled(
            bool(self.user.roles.intersection({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN', 'IT_ADMIN'}))
            and (item.processing_status in {"FAILED", "DEAD_LETTER"} or item.completeness_status != 'COMPLETE')
        )
        self.retry_button.setToolTip('Jadwalkan pembacaan ulang resep ini setelah kendala diperbaiki.'
            if self.retry_button.isEnabled() else 'Tidak ada kegagalan atau kendala pemeriksaan pada hasil ini.')

    def _action_actor(self, roles):
        if self.user.username != 'mode.farmasi':
            return self.user if self.user.roles.intersection(roles) else None
        dialog = ActionIdentityDialog(self.container, roles, self)
        return dialog.actor if dialog.exec() == dialog.DialogCode.Accepted else None

    @Slot()
    def _acknowledge(self) -> None:
        if not self.current_item_id:
            return
        selected_id = self.current_item_id
        actor = self._action_actor({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN'})
        if actor is None:
            return
        try:
            self.container.queue.acknowledge(
                selected_id, actor.id
            )
        except QueueError as exc:
            QMessageBox.warning(self, "Review gagal", str(exc))
            return
        self.refresh()
        self.detail_label.setText('✓ Hasil resep sampai revisi terpilih telah ditandai ditinjau. Ini bukan persetujuan terapi.')
        self.queue_changed.emit()

    @Slot()
    def _retry(self) -> None:
        if not self.current_item_id or self.current_detail is None:
            return
        source_number = self.current_detail.item.no_resep
        actor = self._action_actor({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN', 'IT_ADMIN'})
        if actor is None:
            return
        try:
            self.container.khanza_polling.monitor.request_retry(
                source_number, actor.id,
                'Pemeriksaan ulang terarah dari Antrean Resep setelah kendala ditinjau.'
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Retry gagal", str(exc))
            return
        self.refresh()
        self.detail_label.setText("Pemeriksaan ulang resep ini dijadwalkan; histori dan hasil sebelumnya dipertahankan.")
        self.queue_changed.emit()

    @Slot()
    def _open_intervention(self) -> None:
        if not self.current_item_id:
            return
        try:
            detail = self.container.queue.get_detail(self.current_item_id)
            existing = self.container.interventions.get_for_queue(
                self.current_item_id
            )
        except (QueueError, ValueError) as exc:
            QMessageBox.warning(self, "Intervensi gagal dibuka", str(exc))
            return
        dialog = InterventionDialog(
            self.container,
            self.user,
            detail,
            existing,
            self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        record = dialog.saved_record
        self.refresh()
        if record is not None:
            self.detail_label.setText(
                "Intervensi berhasil disimpan · Status: "
                + ("SELESAI" if record.status == "COMPLETED" else "BELUM SELESAI")
            )
        self.queue_changed.emit()

    @Slot()
    def _simulate_critical(self) -> None:
        self.mock_critical_button.setEnabled(False)
        try:
            result = self.container.mock_prescriptions.simulate(
                "CRITICAL", self.user.id
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Simulasi gagal", str(exc))
        else:
            self.screening_completed.emit(result.screening_id)
        finally:
            self.mock_critical_button.setEnabled(True)
