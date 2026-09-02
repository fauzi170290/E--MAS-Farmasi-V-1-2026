from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.config.settings import AppEnvironment
from emss.services.authentication import AuthenticatedUser
from emss.services.screening import ScreeningError, ScreeningResult


class ScreeningSimulatorTab(QWidget):
    screening_completed = Signal(str)

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user

        banner = QLabel(
            "MODE MOCK — hanya data simulasi. Hasil tidak boleh digunakan "
            "untuk keputusan klinis atau pasien nyata."
        )
        banner.setObjectName("mockBanner")
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "background: #7F1D1D; color: white; font-weight: 700; "
            "padding: 12px; border-radius: 6px;"
        )

        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("mockScenario")
        for scenario in container.mock_prescriptions.scenarios():
            self.scenario_combo.addItem(scenario.label, scenario.code)
            index = self.scenario_combo.count() - 1
            self.scenario_combo.setItemData(
                index, scenario.description, Qt.ItemDataRole.ToolTipRole
            )
        self.simulate_button = QPushButton("Simulasikan Resep Masuk")
        self.simulate_button.setObjectName("simulatePrescription")
        self.simulate_button.clicked.connect(self.simulate)
        allowed = container.settings.environment in {
            AppEnvironment.DEVELOPMENT,
            AppEnvironment.TEST,
        }
        self.simulate_button.setEnabled(allowed)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Skenario:"))
        controls.addWidget(self.scenario_combo, 1)
        controls.addWidget(self.simulate_button)

        self.risk_label = QLabel("Risiko klinis: —")
        self.risk_label.setObjectName("screeningRisk")
        self.completeness_label = QLabel("Kelengkapan asesmen: —")
        self.completeness_label.setObjectName("screeningCompleteness")
        self.identity_label = QLabel("Belum ada simulasi.")
        self.identity_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.addWidget(self.risk_label)
        status_layout.addWidget(self.completeness_label)
        status_layout.addWidget(self.identity_label)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setObjectName("screeningResults")
        self.result_table.setHorizontalHeaderLabels(
            ["Jenis", "Pasangan/Kode", "Klasifikasi", 'Tingkat keparahan', "Keterangan"]
        )
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setStretchLastSection(True)

        self.status_label = QLabel(
            "Pilih skenario untuk menguji engine terhadap master lokal."
            if allowed
            else "Mode MOCK dinonaktifkan di luar development/test."
        )
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(banner)
        layout.addLayout(controls)
        layout.addWidget(status_card)
        layout.addWidget(self.result_table, 1)
        layout.addWidget(self.status_label)

    @Slot()
    def simulate(self) -> None:
        scenario = self.scenario_combo.currentData()
        if not scenario:
            return
        self.simulate_button.setEnabled(False)
        self.status_label.setText("Menjalankan simulasi lokal…")
        try:
            result = self.container.mock_prescriptions.simulate(
                str(scenario), self.user.id
            )
        except ScreeningError as exc:
            self.status_label.setText(f"Simulasi gagal: {exc}")
        else:
            self._render(result)
        finally:
            self.simulate_button.setEnabled(True)

    def _render(self, result: ScreeningResult) -> None:
        risk_colors = {
            "SAFE": "#166534",
            "INFO": "#1D4ED8",
            "REVIEW": "#A16207",
            "HIGH_RISK": "#C2410C",
            "CRITICAL": "#991B1B",
        }
        self.risk_label.setText(f"Risiko klinis: {result.risk_status}")
        self.risk_label.setStyleSheet(
            f"font-size: 15pt; font-weight: 700; "
            f"color: {risk_colors.get(result.risk_status, '#1F2937')};"
        )
        self.completeness_label.setText(
            f"Kelengkapan asesmen: {result.completeness_status}"
        )
        self.completeness_label.setStyleSheet(
            "font-size: 13pt; font-weight: 700;"
        )
        reuse = "hasil lama digunakan ulang" if result.reused else "hasil baru"
        self.identity_label.setText(
            f"KB {result.knowledge_base_version} · revisi "
            f"{result.revision_number} · {reuse} · hash "
            f"{result.prescription_hash[:12]}…"
        )
        rows: list[tuple[str, str, str, str, str]] = []
        rows.extend(
            (
                "PAIR",
                pair.pair_key,
                pair.classification,
                pair.app_severity or pair.severity_code or "—",
                pair.recommendation
                or pair.clinical_effect
                or "Tidak ada keterangan",
            )
            for pair in result.pairs
        )
        rows.extend(
            (
                "ISSUE",
                issue.pair_key or issue.khanza_code or issue.display_name,
                issue.issue_type,
                "—",
                issue.message,
            )
            for issue in result.issues
        )
        self.result_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(value)
                if row[0] == "ISSUE":
                    item.setBackground(QColor("#FEF3C7"))
                self.result_table.setItem(row_index, column_index, item)
        self.result_table.resizeColumnsToContents()
        self.status_label.setText(
            f"Selesai: {result.ingredient_count} zat aktif, "
            f"{result.pair_count} pasangan, "
            f"{result.interaction_count} interaksi, "
            f"{result.not_assessed_count} belum dinilai. "
            "Risiko dan kelengkapan ditampilkan sebagai dua dimensi."
        )
        self.screening_completed.emit(result.screening_id)
