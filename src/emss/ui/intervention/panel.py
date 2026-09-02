from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.interventions import (
    COMMUNICATION_METHODS,
    COMMUNICATION_RESULTS,
    DECISIONS,
    INTERVENTION_TYPES,
    InterventionError,
    InterventionRecord,
)
from emss.services.queue import QueueDetail
from emss.ui.dialogs import fit_dialog_to_available_screen


class InterventionDialog(QDialog):
    def __init__(
        self,
        container: ApplicationContainer,
        user: AuthenticatedUser,
        detail: QueueDetail,
        existing: InterventionRecord | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.container = container
        self.user = user
        self.detail = detail
        self.saved_record: InterventionRecord | None = None
        self.setWindowTitle(f"Intervensi Apoteker — {detail.item.no_resep}")
        self.setObjectName("interventionDialog")
        # Keep this theme local. The intervention form must stay readable even
        # when a Windows palette or a shared stylesheet changes the scroll area.
        self.setStyleSheet(
            "QDialog#interventionDialog { background: #F8FAFC; }"
            "QLabel#interventionTitle { color: #123B5D; }"
            "QLabel#interventionWarning { color: #713F12; background: #FFFBEB; "
            "border: 1px solid #F4C95D; border-radius: 6px; padding: 9px; }"
            "QScrollArea#interventionFormScroll, "
            "QScrollArea#interventionFormScroll QWidget#qt_scrollarea_viewport, "
            "QWidget#interventionFormPage { background: #F8FAFC; border: none; }"
            "QWidget#interventionFormPage QLabel { color: #1E293B; font-weight: 600; }"
            "QWidget#interventionFormPage QLineEdit, "
            "QWidget#interventionFormPage QPlainTextEdit, "
            "QWidget#interventionFormPage QComboBox { color: #111827; background: #FFFFFF; "
            "border: 1px solid #94A3B8; }"
            "QWidget#interventionFormPage QLineEdit:focus, "
            "QWidget#interventionFormPage QPlainTextEdit:focus, "
            "QWidget#interventionFormPage QComboBox:focus { border: 2px solid #2563EB; }"
            "QWidget#interventionFormPage QCheckBox { color: #1E293B; font-weight: 600; spacing: 7px; }"
            "QWidget#interventionFormPage QCheckBox::indicator { width: 18px; height: 18px; "
            "border: 1px solid #64748B; border-radius: 4px; background: #FFFFFF; }"
            "QWidget#interventionFormPage QCheckBox::indicator:checked { "
            "background: #0F766E; border-color: #0F766E; }"
            "QWidget#interventionFormPage QCheckBox::indicator:focus { border: 2px solid #2563EB; }"
        )

        title = QLabel(
            f"Resep {detail.item.no_resep} · Risiko {detail.item.risk_status} · "
            f"Unit {detail.item.service_unit or '-'}"
        )
        title.setObjectName("interventionTitle")
        title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #123B5D;")
        title.setWordWrap(True)
        warning = QLabel(
            "HIGH_RISK/CRITICAL wajib mencatat keputusan, media dan hasil "
            "komunikasi, pihak yang dihubungi, serta alasan bila terapi diteruskan."
        )
        warning.setObjectName("interventionWarning")
        warning.setWordWrap(True)

        self.intervention_type = self._coded_combo(INTERVENTION_TYPES)
        self.decision = self._coded_combo(DECISIONS)
        self.communication_method = self._coded_combo(
            COMMUNICATION_METHODS, blank="Belum dipilih"
        )
        self.communication_result = self._coded_combo(
            COMMUNICATION_RESULTS, blank="Belum dipilih"
        )
        self.contacted_party = QLineEdit()
        self.contacted_party.setPlaceholderText("Nama dokter/pihak yang dihubungi")
        self.reason_if_continued = QPlainTextEdit()
        self.reason_if_continued.setPlaceholderText(
            "Wajib bila terapi dilanjutkan; tuliskan pertimbangan klinis dan monitoring"
        )
        self.reason_if_continued.setMaximumHeight(90)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Catatan intervensi lain")
        self.notes.setMaximumHeight(100)
        self.complete = QCheckBox("Tandai intervensi selesai")
        self.message = QLabel("")
        self.message.setObjectName("interventionValidationMessage")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #B42318; font-weight: 600;")

        if existing is not None:
            self._select_code(self.intervention_type, existing.intervention_type)
            self._select_code(self.decision, existing.decision)
            self._select_code(
                self.communication_method, existing.communication_method
            )
            self._select_code(
                self.communication_result, existing.communication_result
            )
            self.contacted_party.setText(existing.contacted_party)
            self.reason_if_continued.setPlainText(existing.reason_if_continued)
            self.notes.setPlainText(existing.notes)
            self.complete.setChecked(existing.status == "COMPLETED")

        form_page = QWidget()
        form_page.setObjectName("interventionFormPage")
        form = QFormLayout(form_page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Jenis intervensi*", self.intervention_type)
        form.addRow("Keputusan*", self.decision)
        form.addRow("Media komunikasi", self.communication_method)
        form.addRow("Hasil komunikasi", self.communication_result)
        form.addRow("Dokter/pihak dihubungi", self.contacted_party)
        form.addRow("Alasan terapi diteruskan", self.reason_if_continued)
        form.addRow("Catatan", self.notes)
        form.addRow("", self.complete)

        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("interventionFormScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.form_scroll.setWidget(form_page)

        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton(
            "Simpan Intervensi", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save_button.setObjectName("primary")
        self.cancel_button = buttons.addButton(
            "Batal", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(warning)
        layout.addWidget(self.form_scroll, 1)
        layout.addWidget(self.message)
        layout.addWidget(buttons)
        fit_dialog_to_available_screen(self, 720, 650)

    @staticmethod
    def _coded_combo(values, blank: str | None = None) -> QComboBox:
        combo = QComboBox()
        if blank is not None:
            combo.addItem(blank, "")
        for code, label in values:
            combo.addItem(label, code)
        return combo

    @staticmethod
    def _select_code(combo: QComboBox, code: str) -> None:
        index = combo.findData(code)
        if index >= 0:
            combo.setCurrentIndex(index)

    @Slot()
    def _save(self) -> None:
        try:
            self.saved_record = self.container.interventions.save(
                queue_item_id=self.detail.item.id,
                actor_user_id=self.user.id,
                intervention_type=str(self.intervention_type.currentData() or ""),
                decision=str(self.decision.currentData() or ""),
                communication_method=str(
                    self.communication_method.currentData() or ""
                ),
                communication_result=str(
                    self.communication_result.currentData() or ""
                ),
                contacted_party=self.contacted_party.text(),
                reason_if_continued=self.reason_if_continued.toPlainText(),
                notes=self.notes.toPlainText(),
                complete=self.complete.isChecked(),
            )
        except InterventionError as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class InterventionPanel(QWidget):
    changed = Signal()

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.summary = QLabel()
        self.summary.setObjectName("interventionSummary")
        self.summary.setStyleSheet(
            "background: #EAF2FF; border: 1px solid #A9C4ED; "
            "padding: 10px; border-radius: 6px; font-weight: 600;"
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari nomor resep, unit, atau apoteker")
        self.search.returnPressed.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Semua status", "")
        self.status_filter.addItem("Belum selesai", "OPEN")
        self.status_filter.addItem("Selesai", "COMPLETED")
        self.status_filter.currentIndexChanged.connect(self.refresh)
        refresh = QPushButton("Muat Ulang")
        refresh.clicked.connect(self.refresh)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 2)
        filters.addWidget(self.status_filter, 1)
        filters.addWidget(refresh)

        self.table = QTableWidget(0, 9)
        self.table.setObjectName("interventionHistory")
        self.table.setHorizontalHeaderLabels(
            [
                "Diperbarui",
                "No. Resep",
                "Unit/Depo",
                "Risiko",
                "Apoteker",
                "Jenis",
                "Keputusan",
                "Komunikasi",
                "Status",
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        note = QLabel(
            "Intervensi dibuat dari tab Antrean & Alert setelah memilih resep. "
            "Mode Farmasi tanpa password tidak dapat mencatat identitas apoteker."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #526372;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.summary)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addWidget(note)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        rows = self.container.interventions.list_records(
            status=str(self.status_filter.currentData() or ""),
            search=self.search.text(),
        )
        total = self.container.interventions.list_records(limit=2000)
        completed = sum(row.status == "COMPLETED" for row in total)
        self.summary.setText(
            f"Total {len(total)} · Belum selesai {len(total) - completed} · "
            f"Selesai {completed} · Menampilkan {len(rows)}"
        )
        labels = dict(INTERVENTION_TYPES)
        decisions = dict(DECISIONS)
        communication = dict(COMMUNICATION_RESULTS)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.updated_at.replace("T", " "),
                row.no_resep,
                row.service_unit,
                row.risk_status,
                row.pharmacist_name,
                labels.get(row.intervention_type, row.intervention_type),
                decisions.get(row.decision, row.decision),
                communication.get(
                    row.communication_result, row.communication_result or "-"
                ),
                "SELESAI" if row.status == "COMPLETED" else "BELUM SELESAI",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row.queue_item_id)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
