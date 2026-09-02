from __future__ import annotations
from emss.ui.navigation import ActionLayout
from emss.ui.presentation import status_text

import shutil
from datetime import date
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    Qt,
    QObject,
    QRunnable,
    QThreadPool,
    QTime,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from emss.app import ApplicationContainer
from emss.importexport.ddi_import import (
    DdiCommitResult,
    DdiImportPreview,
)
from emss.importexport.ddi_export import DdiExportResult
from emss.services.authentication import AuthenticatedUser
from emss.services.knowledge import (
    DdiRuleDetail,
    KnowledgeError,
    ManualDdiRule,
)
from emss.ui.dialogs import fit_dialog_to_available_screen
from emss.utils.time import utc_now


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.function = function
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as exc:  # noqa: BLE001 - boundary worker UI
            self.signals.failed.emit(str(exc))
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


class DdiInputDialog(QDialog):
    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
        version_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.container = container
        self.user = user
        self.version_id = version_id
        self.setWindowTitle("Tambah Pasangan Interaksi Obat")

        self.ingredient_a = QComboBox()
        self.ingredient_b = QComboBox()
        for selector in (self.ingredient_a, self.ingredient_b):
            selector.setEditable(True)
            selector.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            selector.setObjectName("ddiIngredientSelector")
        try:
            ingredients = container.catalog.list_active_ingredients()
        except Exception:  # noqa: BLE001 - keep dialog usable if catalog is unavailable
            ingredients = []
        for ingredient in ingredients:
            self.ingredient_a.addItem(ingredient, ingredient)
            self.ingredient_b.addItem(ingredient, ingredient)
        self.interaction_status = QComboBox()
        self.interaction_status.addItems(
            [
                "INTERACTION_FOUND",
                "ASSESSED_NO_INTERACTION",
                "NOT_ASSESSABLE",
                "EXCLUDED",
            ]
        )
        self.severity = QComboBox()
        self.severity.addItems(
            ["NONE", "MINOR", "SIGNIFICANT", "SERIOUS", "CONTRAINDICATED"]
        )
        self.severity.setCurrentText("SIGNIFICANT")
        self.severity_label = QLineEdit()
        self.clinical_effect = QPlainTextEdit()
        self.mechanism = QPlainTextEdit()
        self.recommendation = QPlainTextEdit()
        self.monitoring = QPlainTextEdit()
        self.population_risk = QPlainTextEdit()
        self.source_name = QLineEdit()
        self.source_reference = QLineEdit()
        self.accessed_at = QLineEdit(date.today().isoformat())
        self.validated_by = QLineEdit(user.display_name)
        self.review_resolved = QCheckBox(
            "Review klinis rule ini telah diselesaikan"
        )
        self.notes = QPlainTextEdit()

        for field in (
            self.clinical_effect,
            self.mechanism,
            self.recommendation,
            self.monitoring,
            self.population_risk,
            self.notes,
        ):
            field.setMinimumHeight(72)
            field.setMaximumHeight(92)

        form_page = QWidget()
        form = QFormLayout(form_page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Obat/kandungan A*", self.ingredient_a)
        form.addRow("Obat/kandungan B*", self.ingredient_b)
        form.addRow("Status interaksi*", self.interaction_status)
        form.addRow('Tingkat keparahan*', self.severity)
        form.addRow('Label keparahan', self.severity_label)
        form.addRow("Efek klinis", self.clinical_effect)
        form.addRow("Mekanisme", self.mechanism)
        form.addRow("Rekomendasi", self.recommendation)
        form.addRow('Pemantauan', self.monitoring)
        form.addRow("Populasi berisiko", self.population_risk)
        form.addRow("Sumber*", self.source_name)
        form.addRow("Referensi", self.source_reference)
        form.addRow("Tanggal akses (YYYY-MM-DD)", self.accessed_at)
        form.addRow("Validator", self.validated_by)
        form.addRow("", self.review_resolved)
        form.addRow("Catatan", self.notes)

        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("ddiInputFormScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.form_scroll.setWidget(form_page)

        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton(
            "Simpan Pair (Draft)", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save_button.setObjectName("saveDdiDraft")
        self.cancel_button = buttons.addButton(
            "Batal", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        warning = QLabel(
            "Pair baru disimpan sebagai DRAFT pada Batch 5. Aktivasi langsung "
            "menunggu layanan berwenang Batch 6."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; padding: 8px;"
        )
        layout.addWidget(warning)
        layout.addWidget(self.form_scroll, 1)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(self, 760, 680)

    @Slot()
    def _save(self) -> None:
        try:
            accessed_at = date.fromisoformat(self.accessed_at.text().strip())
            self.container.knowledge.save_manual_rule(
                ManualDdiRule(
                    version_id=self.version_id,
                    ingredient_a=self.ingredient_a.currentText(),
                    ingredient_b=self.ingredient_b.currentText(),
                    interaction_status=self.interaction_status.currentText(),
                    severity_code=self.severity.currentText(),
                    severity_label=self.severity_label.text(),
                    clinical_effect=self.clinical_effect.toPlainText(),
                    mechanism=self.mechanism.toPlainText(),
                    recommendation=self.recommendation.toPlainText(),
                    monitoring=self.monitoring.toPlainText(),
                    population_risk=self.population_risk.toPlainText(),
                    source_name=self.source_name.text(),
                    source_reference=self.source_reference.text(),
                    source_accessed_at=accessed_at,
                    validated_by=self.validated_by.text(),
                    validated_at=utc_now(),
                    clinical_review_resolved=self.review_resolved.isChecked(),
                    notes=self.notes.toPlainText(),
                ),
                self.user.id,
            )
        except (ValueError, KnowledgeError) as exc:
            QMessageBox.warning(self, "Input DDI belum valid", str(exc))
            return
        self.accept()


class DdiRuleDetailDialog(QDialog):
    def __init__(
        self,
        detail: DdiRuleDetail,
        parent: QWidget | None = None,
        *,
        review_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Detail Klinis DDI — {detail.pair_key}")
        self.resize(820, 680)

        hold_status = (
            "SELESAI"
            if detail.clinical_review_resolved
            else ("WAJIB — BELUM SELESAI" if detail.clinical_review_required else "-")
        )
        content = "\n\n".join(
            (
                f"PASANGAN KANONIK\n{detail.pair_key}",
                "KLASIFIKASI\n"
                f"Status: {detail.interaction_status}\n"
                f"Severity: {detail.severity_code}"
                f"{f' ({detail.severity_label})' if detail.severity_label else ''}\n"
                f"Level aplikasi: {detail.app_severity or '-'}\n"
                f"HOLD: {hold_status}",
                f"EFEK KLINIS\n{detail.clinical_effect or '-'}",
                f"MEKANISME\n{detail.mechanism or '-'}",
                f"REKOMENDASI\n{detail.recommendation or '-'}",
                f"MONITORING\n{detail.monitoring or '-'}",
                f"POPULASI BERISIKO\n{detail.population_risk or '-'}",
                "SUMBER\n"
                f"Nama: {detail.source_name or '-'}\n"
                f"Referensi: {detail.source_reference or '-'}\n"
                f"Tanggal akses: {detail.source_accessed_at or '-'}\n"
                f"Jumlah bukti: {detail.source_evidence_count}\n"
                f"Status validasi: {detail.source_validation_status or '-'}\n"
                f"Kode akhir: {detail.source_final_code or '-'}",
                "VALIDASI KLINIS\n"
                f"Validator: {detail.validated_by_name or '-'}\n"
                f"Waktu: {detail.validated_at or '-'}\n"
                f"Catatan: {detail.notes or '-'}",
            )
        )
        browser = QTextBrowser()
        browser.setObjectName("ddiRuleDetail")
        browser.setStyleSheet(
            "QTextBrowser {"
            " background: #FFFFFF;"
            " color: #111827;"
            " border: 1px solid #CBD5E1;"
            " border-radius: 5px;"
            " padding: 10px;"
            " selection-background-color: #BFDBFE;"
            " selection-color: #111827;"
            "}"
        )
        browser.setPlainText(content)

        buttons = QDialogButtonBox()
        close_button = buttons.addButton(
            "Tutup",
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        close_button.setObjectName("closeDdiRuleDetail")
        close_button.clicked.connect(self.reject)
        if review_mode:
            proceed = buttons.addButton(
                "Lanjutkan Review Klinis",
                QDialogButtonBox.ButtonRole.AcceptRole,
            )
            proceed.setObjectName("proceedClinicalReview")
            proceed.clicked.connect(self.accept)

        warning = QLabel(
            "Pastikan efek klinis, rekomendasi, monitoring, dan sumber telah "
            "ditelaah sebelum HOLD ditandai selesai."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; padding: 8px;"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addWidget(browser, 1)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(self, 820, 680)


class KnowledgeBaseTab(QWidget):
    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.current_version_id: str | None = None
        self.current_status: str | None = None
        self._writer = bool(
            user.roles.intersection({"SUPER_ADMIN", "KNOWLEDGE_ADMIN"})
        )
        self._reviewer = bool(
            user.roles.intersection({"SUPER_ADMIN", "CLINICAL_REVIEWER"})
        )
        self._approver = bool(user.roles.intersection({"SUPER_ADMIN", "KFT"}))

        self.version_combo = QComboBox()
        self.version_combo.setObjectName("knowledgeVersionCombo")
        self.version_combo.currentIndexChanged.connect(self._select_version)
        self.summary_label = QLabel("Belum ada versi knowledge base.")
        self.summary_label.setObjectName("knowledgeSummary")
        self.summary_label.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari pasangan, efek klinis, atau sumber")
        self.search.returnPressed.connect(self.refresh_rules)
        self.rule_filter = QComboBox()
        self.rule_filter.setObjectName("knowledgeRuleFilter")
        for label, code in (
            ('Semua aturan', "ALL"),
            ("HOLD belum selesai", "UNRESOLVED_HOLD"),
            ("HOLD selesai", "RESOLVED_HOLD"),
            ("CRITICAL", "CRITICAL"),
            ("HIGH_RISK", "HIGH_RISK"),
            ("Semua interaksi", "INTERACTION_FOUND"),
        ):
            self.rule_filter.addItem(label, code)
        self.rule_filter.currentIndexChanged.connect(self.refresh_rules)
        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.setObjectName("refreshKnowledge")
        self.refresh_button.clicked.connect(self.request_refresh)
        self.action_feedback = QLabel("Siap.")
        self.action_feedback.setObjectName("knowledgeActionFeedback")
        self.action_feedback.setStyleSheet("color: #526372;")

        self.new_button = QPushButton("Versi Baru")
        self.new_button.clicked.connect(self.create_version)
        self.duplicate_button = QPushButton("Duplikasi Versi")
        self.duplicate_button.clicked.connect(self.duplicate_version)
        self.input_button = QPushButton('Tambah Pasangan DDI')
        self.input_button.clicked.connect(self.input_rule)
        self.review_button = QPushButton('Setujui Tinjauan Klinis')
        self.review_button.clicked.connect(self.review_version)
        self.resolve_hold_button = QPushButton("Selesaikan HOLD Terpilih")
        self.resolve_hold_button.clicked.connect(self.resolve_selected_hold)
        self.detail_button = QPushButton("Lihat Detail Klinis")
        self.detail_button.clicked.connect(self.view_selected_detail)
        self.next_hold_button = QPushButton("HOLD Berikutnya")
        self.next_hold_button.clicked.connect(self.focus_next_hold)
        self.approve_button = QPushButton('Persetujuan KFT')
        self.approve_button.clicked.connect(self.approve_version)
        self.publish_button = QPushButton("Publikasikan")
        self.publish_button.clicked.connect(self.publish_version)
        self.retire_button = QPushButton('Nonaktifkan Versi')
        self.retire_button.clicked.connect(self.retire_version)
        self.rollback_button = QPushButton('Kembali ke Versi Ini')
        self.rollback_button.clicked.connect(self.rollback_version)

        top = QHBoxLayout()
        top.addWidget(QLabel("Versi:"))
        top.addWidget(self.version_combo, 1)
        top.addWidget(self.refresh_button)
        management_actions = ActionLayout()
        for button in (
            self.new_button,
            self.duplicate_button,
            self.input_button,
        ):
            management_actions.addWidget(button)
        management_actions.addStretch()
        workflow_actions = ActionLayout()
        for button in (
            self.detail_button,
            self.next_hold_button,
            self.resolve_hold_button,
        ):
            workflow_actions.addWidget(button)
        workflow_actions.addStretch()
        approval_actions = ActionLayout()
        for button in (self.review_button, self.approve_button, self.publish_button):
            approval_actions.addWidget(button)
        approval_actions.addStretch()
        risk_actions = ActionLayout()
        risk_actions.addStretch()
        for button in (self.retire_button, self.rollback_button):
            button.setProperty('danger', True)
            risk_actions.addWidget(button)
        self.detail_button.setProperty('primaryAction', True)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.rule_filter)
        search_button = QPushButton("Cari")
        search_button.clicked.connect(self.refresh_rules)
        search_row.addWidget(search_button)

        self.table = QTableWidget(0, 9)
        self.table.setObjectName("ddiRuleTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Pasangan kanonik",
                "Status interaksi",
                'Tingkat keparahan',
                "Status aplikasi",
                "Efek klinis",
                "Rekomendasi",
                "HOLD",
                'Tahap peninjauan',
                "Aktif",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(
            lambda _item: self.view_selected_detail()
        )
        header = self.table.horizontalHeader()
        for column in (0, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 6, 7, 8):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        note = QLabel(
            "Quick-closure, NOT_ASSESSABLE, EXCLUDED, dan rule HOLD tetap "
            "dipertahankan sebagai dimensi kelengkapan; tidak berubah menjadi SAFE."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; padding: 8px;"
        )

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(management_actions)
        layout.addLayout(workflow_actions)
        layout.addLayout(approval_actions)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.action_feedback)
        layout.addLayout(search_row)
        layout.addWidget(note)
        layout.addWidget(self.table, 1)
        layout.addLayout(risk_actions)
        self.refresh()

    @Slot()
    def request_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Memuat…")
        self.action_feedback.setText("Memuat Data Interaksi…")
        QTimer.singleShot(0, self._complete_requested_refresh)

    @Slot()
    def _complete_requested_refresh(self) -> None:
        try:
            self.refresh()
        finally:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("✓ Selesai")
            self.action_feedback.setText(
                "Data Interaksi diperbarui pukul "
                f"{QTime.currentTime().toString('HH:mm:ss')}."
            )

    @Slot()
    def refresh(self) -> None:
        previous = self.current_version_id
        versions = self.container.knowledge.list_versions()
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItem("— belum ada versi —", None)
        selected = 0
        for version in versions:
            label = (
                f"{version.version_code} · {status_text(version.status)} · "
                f"{version.rule_count} aturan · HOLD {version.unresolved_holds}"
            )
            self.version_combo.addItem(label, (version.id, version.status))
            if version.id == previous:
                selected = self.version_combo.count() - 1
        if selected == 0 and versions:
            selected = 1
        self.version_combo.setCurrentIndex(selected)
        self.version_combo.blockSignals(False)
        self._select_version(selected)

    @Slot(int)
    def _select_version(self, index: int) -> None:
        data = self.version_combo.itemData(index)
        if data:
            self.current_version_id, self.current_status = data
        else:
            self.current_version_id = self.current_status = None
        self._update_buttons()
        self.refresh_rules()

    @Slot()
    def refresh_rules(self) -> None:
        if not self.current_version_id:
            self.summary_label.setText("Belum ada versi knowledge base.")
            self.table.setRowCount(0)
            return
        summary = self.container.knowledge.summary(self.current_version_id)
        self.summary_label.setText(
            f"Total {summary.total_rules} · Interaksi {summary.interactions} · "
            f"Tidak ada interaksi dilaporkan {summary.assessed_no_interaction} · "
            f"Belum dapat dinilai {summary.not_assessable} · Dikecualikan "
            f"{summary.excluded} · HOLD selesai "
            f"{summary.required_holds - summary.unresolved_holds}/"
            f"{summary.required_holds} · HOLD belum selesai "
            f"{summary.unresolved_holds} · Aktif {summary.enabled_rules}"
        )
        rows = self.container.knowledge.list_rules(
            self.current_version_id,
            self.search.text(),
            filter_code=str(self.rule_filter.currentData() or "ALL"),
        )
        self.action_feedback.setText(
            f"Menampilkan {len(rows)} aturan · Filter: "
            f"{self.rule_filter.currentText()}."
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.pair_key,
                row.interaction_status,
                row.severity_code,
                row.app_severity or "-",
                row.clinical_effect,
                row.recommendation,
                (
                    "SELESAI"
                    if row.clinical_review_resolved
                    else ("WAJIB" if row.clinical_review_required else "-")
                ),
                row.record_status,
                "YA" if row.is_enabled else "TIDAK",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(status_text(value) if column in (1, 2, 3, 7) else value)
                item.setToolTip(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.id)
                if column == 2:
                    colors = {
                        "CONTRAINDICATED": "#F8B4B4",
                        "SERIOUS": "#FDE2B8",
                        "SIGNIFICANT": "#FFF2CC",
                        "MINOR": "#DDF7E8",
                    }
                    if value in colors:
                        item.setBackground(QBrush(QColor(colors[value])))
                if column == 6 and value == "WAJIB":
                    item.setBackground(QBrush(QColor("#FDE7E7")))
                self.table.setItem(row_index, column, item)

    def _update_buttons(self) -> None:
        status = self.current_status
        self.new_button.setEnabled(self._writer)
        self.duplicate_button.setEnabled(self._writer and bool(status))
        self.input_button.setEnabled(self._writer and status == "DRAFT")
        self.detail_button.setEnabled(bool(status))
        self.next_hold_button.setEnabled(self._reviewer and status == "DRAFT")
        self.review_button.setEnabled(self._reviewer and status == "DRAFT")
        self.resolve_hold_button.setEnabled(
            self._reviewer and status == "DRAFT"
        )
        self.approve_button.setEnabled(self._approver and status == "REVIEWED")
        self.publish_button.setEnabled(self._approver and status == "APPROVED")
        self.retire_button.setEnabled(self._approver and status == "PUBLISHED")
        self.rollback_button.setEnabled(
            self._approver and status in {"APPROVED", "RETIRED"}
        )

    @Slot()
    def create_version(self) -> None:
        code, ok = QInputDialog.getText(self, "Versi Baru", "Kode versi:")
        if not ok:
            return
        title, ok = QInputDialog.getText(self, "Versi Baru", "Judul:")
        if not ok:
            return
        try:
            self.container.knowledge.create_version(
                code, title, self.user.id
            )
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Gagal membuat versi", str(exc))
            return
        self.refresh()

    @Slot()
    def duplicate_version(self) -> None:
        if not self.current_version_id:
            return
        code, ok = QInputDialog.getText(
            self, "Duplikasi Versi", "Kode versi baru:"
        )
        if not ok:
            return
        title, ok = QInputDialog.getText(
            self, "Duplikasi Versi", "Judul versi baru:"
        )
        if not ok:
            return
        try:
            self.container.knowledge.duplicate_version(
                self.current_version_id, code, title, self.user.id
            )
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Duplikasi gagal", str(exc))
            return
        self.refresh()

    @Slot()
    def input_rule(self) -> None:
        if not self.current_version_id:
            return
        dialog = DdiInputDialog(
            self.container, self.user, self.current_version_id, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _transition(
        self, title: str, callback: Callable[[str, str, str], None]
    ) -> None:
        if not self.current_version_id:
            return
        reason, ok = QInputDialog.getText(
            self, title, "Alasan/catatan keputusan:"
        )
        if not ok:
            return
        try:
            callback(self.current_version_id, self.user.id, reason)
        except KnowledgeError as exc:
            self.action_feedback.setText(f"{title} gagal: {exc}")
            QMessageBox.warning(self, f"{title} gagal", str(exc))
            return
        self.refresh()
        self.action_feedback.setText(
            f"{title} berhasil diproses pukul "
            f"{QTime.currentTime().toString('HH:mm:ss')}."
        )

    @Slot()
    def review_version(self) -> None:
        self._transition("Review Klinis", self.container.knowledge.review_version)

    def _selected_rule_id(self) -> str | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        rule_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return str(rule_id) if rule_id else None

    @Slot()
    def view_selected_detail(self) -> None:
        rule_id = self._selected_rule_id()
        if not rule_id:
            QMessageBox.information(
                self, "Pilih rule", "Pilih satu baris untuk melihat detail klinis."
            )
            return
        try:
            detail = self.container.knowledge.get_rule_detail(rule_id)
        except KnowledgeError as exc:
            self.action_feedback.setText(f"Gagal membuka detail: {exc}")
            QMessageBox.warning(self, "Detail rule gagal", str(exc))
            return
        DdiRuleDetailDialog(detail, self).exec()

    @Slot()
    def focus_next_hold(self) -> None:
        index = self.rule_filter.findData("UNRESOLVED_HOLD")
        if index >= 0 and self.rule_filter.currentIndex() != index:
            self.rule_filter.setCurrentIndex(index)
        else:
            self.refresh_rules()
        if self.table.rowCount() == 0:
            self.action_feedback.setText("Semua HOLD klinis telah diselesaikan.")
            return
        self.table.selectRow(0)
        self.table.scrollToItem(self.table.item(0, 0))
        self.action_feedback.setText(
            "HOLD berikutnya dipilih. Buka detail klinis sebelum menyelesaikan review."
        )

    @Slot()
    def resolve_selected_hold(self) -> None:
        rule_id = self._selected_rule_id()
        if not rule_id:
            QMessageBox.information(
                self, "Pilih rule", "Pilih satu baris HOLD yang telah ditinjau."
            )
            return
        try:
            detail = self.container.knowledge.get_rule_detail(rule_id)
        except KnowledgeError as exc:
            self.action_feedback.setText(f"Gagal membuka detail HOLD: {exc}")
            QMessageBox.warning(self, "Review HOLD gagal", str(exc))
            return
        review_dialog = DdiRuleDetailDialog(detail, self, review_mode=True)
        if review_dialog.exec() != QDialog.DialogCode.Accepted:
            self.action_feedback.setText("Review HOLD dibatalkan; tidak ada perubahan.")
            return
        reason, ok = QInputDialog.getText(
            self, "Selesaikan HOLD", "Catatan hasil review klinis:"
        )
        if not ok:
            return
        try:
            self.container.knowledge.resolve_rule_review(
                rule_id, self.user.id, reason
            )
        except KnowledgeError as exc:
            self.action_feedback.setText(f"Review HOLD gagal: {exc}")
            QMessageBox.warning(self, "Review HOLD gagal", str(exc))
            return
        self.refresh()
        self.action_feedback.setText(
            "HOLD terpilih berhasil diselesaikan pukul "
            f"{QTime.currentTime().toString('HH:mm:ss')}."
        )

    @Slot()
    def approve_version(self) -> None:
        self._transition('Persetujuan KFT', self.container.knowledge.approve_version)

    @Slot()
    def publish_version(self) -> None:
        self._transition("Publikasi", self.container.knowledge.publish_version)

    @Slot()
    def retire_version(self) -> None:
        self._transition("Retire", self.container.knowledge.retire_version)

    @Slot()
    def rollback_version(self) -> None:
        self._transition("Rollback", self.container.knowledge.rollback_to)


class DdiImportTab(QWidget):
    knowledge_changed = Signal()

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.thread_pool = QThreadPool.globalInstance()
        self.current_batch_id: str | None = None
        self._worker: _Worker | None = None
        self._active_button: QPushButton | None = None
        self._active_button_text = ""
        self._button_states: dict[QPushButton, bool] = {}
        self._authorized = bool(
            user.roles.intersection({"SUPER_ADMIN", "KNOWLEDGE_ADMIN"})
        )
        self._export_authorized = bool(
            user.roles.intersection(
                {
                    "SUPER_ADMIN",
                    "KNOWLEDGE_ADMIN",
                    "CLINICAL_REVIEWER",
                    "KFT",
                    "IT_ADMIN",
                }
            )
        )

        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText(
            "Pilih workbook DDI .xlsx atau file .csv"
        )
        self.choose_button = QPushButton('Pilih Berkas')
        self.choose_button.clicked.connect(self.choose_file)
        self.template_button = QPushButton('Unduh Format Impor DDI')
        self.template_button.setObjectName("downloadDdiTemplate")
        self.template_button.setToolTip(
            "Template siap isi dengan referensi kode obat Khanza dan kandidat "
            "DDI baru yang telah disaring dari pasangan yang sudah ada."
        )
        self.template_button.clicked.connect(self.download_template)
        self.export_button = QPushButton('Ekspor Data Interaksi Lengkap')
        self.export_button.setObjectName("exportCompleteDdiMaster")
        self.export_button.setToolTip(
            "Ekspor seluruh rule versi terbaru, sheet pemulihan DRAFT, arsip "
            "lengkap, master zat aktif, mapping Khanza, codebook, dan checksum."
        )
        self.export_button.clicked.connect(self.export_complete_master)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_path, 1)
        file_row.addWidget(self.choose_button)
        file_row.addWidget(self.template_button)
        file_row.addWidget(self.export_button)

        self.preview_button = QPushButton('1. Periksa Isi Berkas')
        self.preview_button.setObjectName("previewDdiImport")
        self.preview_button.clicked.connect(self.preview_import)
        self.commit_button = QPushButton("2. Simpan sebagai Draft")
        self.commit_button.setObjectName("commitDdiImport")
        self.commit_button.clicked.connect(self.commit_import)
        self.commit_button.setEnabled(False)
        actions = ActionLayout()
        actions.addWidget(self.preview_button)
        actions.addWidget(self.commit_button)
        actions.addStretch()

        self.progress = QProgressBar()
        self.progress.setObjectName("ddiImportProgress")
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.status_label = QLabel(
            "Preview tidak mengubah master DDI. Commit membuat backup terlebih dahulu."
        )
        self.status_label.setObjectName("ddiImportStatus")
        self.status_label.setWordWrap(True)
        self.issue_table = QTableWidget(0, 4)
        self.issue_table.setHorizontalHeaderLabels(
            ["Sheet", "Baris", "Field", "Pesan"]
        )
        self.issue_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.issue_table.verticalHeader().setVisible(False)
        header = self.issue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        note = QLabel(
            "Import tidak mempublikasikan rule. Seluruh data masuk sebagai DRAFT; "
            "workflow klinis dilakukan di tab Knowledge Base."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "background: #FFF7D6; border: 1px solid #E8C85A; padding: 8px;"
        )
        layout = QVBoxLayout(self)
        layout.addLayout(file_row)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(note)
        layout.addWidget(self.issue_table, 1)

        if not self._authorized:
            self.choose_button.setEnabled(False)
            self.template_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            self.status_label.setText(
                "Role Anda tidak berwenang mengimpor master DDI."
            )
        self.export_button.setEnabled(self._export_authorized)

    @Slot()
    def choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Pilih master DDI", "", "Data DDI (*.xlsx *.csv)"
        )
        if selected:
            self.file_path.setText(selected)
            self.current_batch_id = None
            self.commit_button.setEnabled(False)

    @Slot()
    def download_template(self) -> None:
        project_root = Path(__file__).resolve().parents[4]
        source = project_root / "templates" / "ddi_import_template.xlsx"
        if not source.is_file():
            QMessageBox.warning(
                self, "Template tidak tersedia", f"File tidak ditemukan: {source}"
            )
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Template DDI",
            "ddi_import_template.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if target:
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                QMessageBox.warning(self, "Gagal menyimpan template", str(exc))
                return
            self.status_label.setText(f"Template disimpan: {target}")

    @Slot()
    def export_complete_master(self) -> None:
        versions = self.container.knowledge.list_versions()
        if not versions:
            self.status_label.setText("Belum ada versi master DDI untuk diekspor.")
            return
        version = versions[0]
        safe_version = "".join(
            character if character.isalnum() or character in "-_." else "_"
            for character in version.version_code
        )
        suggested = (
            f"MASTER_DDI_EXPORT_LENGKAP_{safe_version}_{date.today().isoformat()}.xlsx"
        )
        target, _ = QFileDialog.getSaveFileName(
            self,
            'Ekspor Data Interaksi Lengkap',
            suggested,
            "Excel Workbook (*.xlsx)",
        )
        if not target:
            return
        self._start(
            lambda: self.container.ddi_export.export_version(
                version.id, Path(target), self.user.id
            ),
            self._export_succeeded,
            f"Mengekspor {version.rule_count} rule dan menghitung checksum…",
            self.export_button,
        )

    @Slot()
    def preview_import(self) -> None:
        path = self.file_path.text().strip()
        if not path:
            self.status_label.setText("Pilih file terlebih dahulu.")
            return
        self._start(
            lambda: self.container.ddi_import.preview(Path(path), self.user.id),
            self._preview_succeeded,
            "Memvalidasi master DDI tanpa mengubah rule…",
            self.preview_button,
        )

    @Slot()
    def commit_import(self) -> None:
        if not self.current_batch_id:
            return
        batch_id = self.current_batch_id
        self._start(
            lambda: self.container.ddi_import.commit(batch_id, self.user.id),
            self._commit_succeeded,
            "Membuat backup dan menyimpan rule sebagai DRAFT…",
            self.commit_button,
        )

    def _start(
        self,
        function: Callable[[], Any],
        success: Callable[[Any], None],
        message: str,
        active_button: QPushButton,
    ) -> None:
        buttons = (
            self.choose_button,
            self.template_button,
            self.export_button,
            self.preview_button,
            self.commit_button,
        )
        self._button_states = {button: button.isEnabled() for button in buttons}
        self._active_button = active_button
        self._active_button_text = active_button.text()
        active_button.setText("Memproses…")
        self.progress.setVisible(True)
        for button in buttons:
            button.setEnabled(False)
        self.status_label.setText(message)
        worker = _Worker(function)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finish)
        self._worker = worker
        self.thread_pool.start(worker)

    @Slot()
    def _finish(self) -> None:
        self.progress.setVisible(False)
        if self._active_button is not None:
            self._active_button.setText(self._active_button_text)
        self.choose_button.setEnabled(self._authorized)
        self.template_button.setEnabled(self._authorized)
        self.export_button.setEnabled(self._export_authorized)
        self.preview_button.setEnabled(self._authorized)
        self._active_button = None
        self._active_button_text = ""
        self._worker = None

    @Slot(object)
    def _preview_succeeded(self, preview: DdiImportPreview) -> None:
        self.current_batch_id = preview.batch_id
        self.status_label.setText(
            f"Preview {preview.version_code or '-'}: {preview.total_rows} baris, "
            f"{preview.valid_rows} valid, {preview.invalid_rows} invalid; "
            f"insert {preview.proposed_inserts}, update "
            f"{preview.proposed_updates}."
        )
        self.issue_table.setRowCount(len(preview.issues))
        for row_index, issue in enumerate(preview.issues):
            for column, value in enumerate(
                (issue.sheet, str(issue.row), issue.field, issue.message)
            ):
                item = QTableWidgetItem(value)
                item.setBackground(QBrush(QColor("#FDE7E7")))
                self.issue_table.setItem(row_index, column, item)
        self.commit_button.setEnabled(preview.commit_allowed)

    @Slot(object)
    def _commit_succeeded(self, result: DdiCommitResult) -> None:
        self.commit_button.setEnabled(False)
        self.status_label.setText(
            f"Commit selesai ke {result.version_code} sebagai DRAFT: "
            f"insert {result.inserted}, update {result.updated}, unchanged "
            f"{result.unchanged}. Backup: {Path(result.backup_path).name}"
        )
        self.knowledge_changed.emit()

    @Slot(object)
    def _export_succeeded(self, result: DdiExportResult) -> None:
        self.status_label.setText(
            f"Export lengkap selesai: {result.rule_count} rule versi "
            f"{result.version_code}; checksum SHA-256 disimpan di "
            f"{result.checksum_path.name}."
        )
        QMessageBox.information(
            self,
            "Export Master DDI selesai",
            f"Workbook berhasil dibuat:\n{result.path}\n\n"
            f"Jumlah rule: {result.rule_count}\n"
            f"HOLD belum selesai: {result.unresolved_holds}\n"
            f"Checksum: {result.checksum_sha256}",
        )

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.status_label.setText(f"Operasi gagal: {message}")
        for button, enabled in self._button_states.items():
            button.setEnabled(enabled)
