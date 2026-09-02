from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.dashboard import MONTH_NAMES, DashboardSummary
from emss.utils.time import utc_now


class DashboardPanel(QWidget):
    EXPORT_ROLES = {"SUPER_ADMIN"}

    CARD_DEFINITIONS = (
        (
            "screened",
            "Resep diskrining",
            "Jumlah resep yang diperiksa E-MAS",
            "#1D4ED8",
            "#EFF6FF",
        ),
        (
            "high_risk",
            "Risiko tinggi",
            "HIGH_RISK + CRITICAL",
            "#C2410C",
            "#FFF7ED",
        ),
        (
            "critical",
            "CRITICAL",
            "Perlu perhatian klinis segera",
            "#B91C1C",
            "#FEF2F2",
        ),
        (
            "completed",
            "Tindak lanjut selesai",
            "Intervensi sudah didokumentasikan",
            "#15803D",
            "#F0FDF4",
        ),
        (
            "acceptance",
            "Rekomendasi diterima",
            "Diterima penuh atau sebagian",
            "#0F766E",
            "#F0FDFA",
        ),
        (
            "complete_data",
            "Cakupan penilaian DDI",
            "Resep final dengan semua obat/pasangan dapat dinilai",
            "#6D28D9",
            "#F5F3FF",
        ),
    )

    def __init__(
        self, container: ApplicationContainer, user: AuthenticatedUser
    ) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.card_values: dict[str, QLabel] = {}
        self.card_context: dict[str, QLabel] = {}

        heading = QLabel("Dashboard Kajian Potensi Interaksi Obat (pDDI)")
        heading.setStyleSheet(
            "font-size: 18pt; font-weight: 750; color: #123B5D;"
        )
        subtitle = QLabel(
            "Ringkasan agregat resep final terbaru, seluruh tingkat pDDI, "
            "tindak lanjut, dan distribusi per unit layanan."
        )
        subtitle.setStyleSheet("color: #526372; font-size: 10.5pt;")
        subtitle.setWordWrap(True)

        self.period_combo = QComboBox()
        self.period_combo.setObjectName("dashboardPeriod")
        self.period_combo.insertItem(0, "Hari ini (hasil efektif)", "DAY")
        self.period_combo.addItem("Bulanan", "MONTH")
        self.period_combo.addItem("Triwulanan", "QUARTER")
        self.period_combo.addItem("Tahunan", "YEAR")
        self.period_combo.addItem("Seluruh data", "ALL")
        self.period_combo.setCurrentIndex(0)
        self.period_combo.currentIndexChanged.connect(self.refresh)

        self.month_combo = QComboBox()
        self.month_combo.setObjectName("dashboardMonth")
        for month, label in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(label, month)
        self.month_combo.setCurrentIndex(utc_now().month - 1)
        self.month_combo.currentIndexChanged.connect(self.refresh)

        self.year_combo = QComboBox()
        self.year_combo.setObjectName("dashboardYear")
        for year in container.dashboard.available_years():
            self.year_combo.addItem(str(year), year)
        current_year_index = self.year_combo.findData(utc_now().year)
        if current_year_index >= 0:
            self.year_combo.setCurrentIndex(current_year_index)
        self.year_combo.currentIndexChanged.connect(self.refresh)

        self.day_edit = QDateEdit(QDate.currentDate())
        self.day_edit.setObjectName("dashboardDay")
        self.day_edit.setCalendarPopup(True)
        self.day_edit.dateChanged.connect(self.refresh)

        refresh = QPushButton("Muat Ulang")
        refresh.setObjectName("refreshDashboard")
        refresh.clicked.connect(self.refresh)
        self.export_button = QPushButton("Ekspor Laporan CSV")
        self.export_button.setObjectName("primary")
        self.export_button.setEnabled(
            bool(user.roles.intersection(self.EXPORT_ROLES))
            and user.username != "mode.farmasi"
        )
        self.export_button.clicked.connect(self.export_csv)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Periode:"))
        filters.addWidget(self.period_combo)
        filters.addWidget(QLabel("Bulan:"))
        filters.addWidget(self.month_combo)
        filters.addWidget(QLabel("Tahun:"))
        filters.addWidget(self.year_combo)
        filters.addWidget(QLabel("Tanggal:"))
        filters.addWidget(self.day_edit)
        filters.addWidget(refresh)
        filters.addWidget(self.export_button)
        filters.addStretch()

        self.period_label = QLabel()
        self.period_label.setObjectName("dashboardPeriodSummary")
        self.period_label.setWordWrap(True)
        self.period_label.setStyleSheet(
            "background: #E0F2FE; color: #0C4A6E; border: 1px solid #7DD3FC; "
            "padding: 10px; border-radius: 6px; font-weight: 650;"
        )

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        cards.setVerticalSpacing(10)
        for index, definition in enumerate(self.CARD_DEFINITIONS):
            card = self._build_card(*definition)
            cards.addWidget(card, index // 3, index % 3)

        safety_card = QFrame()
        safety_card.setObjectName("card")
        safety_layout = QGridLayout(safety_card)
        safety_title = QLabel("Spektrum hasil pDDI dan temuan rekonsiliasi")
        safety_title.setStyleSheet("font-size: 11pt; font-weight: 700; color: #123B5D;")
        safety_layout.addWidget(safety_title, 0, 0, 1, 4)
        self.safety_values: dict[str, QLabel] = {}
        safety_definitions = (
            ('contraindicated_pairs', 'Kontraindikasi'), ('serious_pairs', 'Mayor/serius'),
            ('significant_pairs', 'Signifikan'), ('minor_pairs', 'Minor'),
            ('assessed_no_interaction_pairs', 'Dinilai: tidak ditemukan pDDI'),
            ('not_assessed_pairs', 'Belum dinilai'), ('unique_ddi_pairs', 'Pasangan pDDI unik'),
            ('cross_prescription_findings', 'Temuan lintas resep'),
            ("duplicate_therapy", "Potensi duplikasi"), ("polypharmacy", "Polifarmasi"),
            ("high_alert", "High-alert"), ("lasa", "LASA"),
        )
        for index, (key, label) in enumerate(safety_definitions):
            column, block = index % 4, index // 4
            value = QLabel("0\n0,0% resep")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet("background: #F8FAFC; color: #0F3D5E; border: 1px solid #CBD5E1; border-radius: 6px; padding: 8px; font-weight: 700;")
            value.setToolTip(label)
            self.safety_values[key] = value
            safety_layout.addWidget(QLabel(label), 1 + block * 2, column, alignment=Qt.AlignmentFlag.AlignCenter)
            safety_layout.addWidget(value, 2 + block * 2, column)

        self.open_alert = QLabel()
        self.open_alert.setObjectName("dashboardOpenInterventions")
        self.open_alert.setWordWrap(True)

        performance = QFrame()
        performance.setObjectName("card")
        performance_layout = QVBoxLayout(performance)
        performance_title = QLabel("Indikator kinerja periode terpilih")
        performance_title.setStyleSheet(
            "font-size: 11pt; font-weight: 700; color: #123B5D;"
        )
        performance_layout.addWidget(performance_title)
        self.coverage_bar = self._progress_bar("Tindak lanjut risiko tinggi")
        self.acceptance_bar = self._progress_bar("Penerimaan rekomendasi")
        self.completeness_bar = self._progress_bar("Cakupan penilaian DDI")
        performance_layout.addWidget(self.coverage_bar)
        performance_layout.addWidget(self.acceptance_bar)
        performance_layout.addWidget(self.completeness_bar)

        self.trend_table = QTableWidget(0, 8)
        self.trend_table.setObjectName("managementDashboardMonthlyTrend")
        self.trend_table.setHorizontalHeaderLabels(
            [
                "Bulan",
                "Resep",
                "CRITICAL",
                "CRITICAL %",
                "HIGH_RISK",
                "HIGH_RISK %",
                "Intervensi selesai",
                "Diterima %",
            ]
        )
        self._configure_table(self.trend_table)

        self.unit_table = QTableWidget(0, 6)
        self.unit_table.setObjectName("managementDashboardByUnit")
        self.unit_table.setHorizontalHeaderLabels(
            [
                "Unit/Depo",
                "Resep",
                "CRITICAL",
                "HIGH_RISK",
                "Risiko tinggi %",
                "Intervensi",
            ]
        )
        self._configure_table(self.unit_table)
        self.table = self.unit_table

        trend_page = QWidget()
        trend_page.setStyleSheet("background: #F4F7FA;")
        trend_layout = QVBoxLayout(trend_page)
        trend_note = QLabel(
            "Persentase dihitung terhadap seluruh resep pada bulan yang sama."
        )
        trend_note.setStyleSheet("color: #526372;")
        trend_layout.addWidget(trend_note)
        trend_layout.addWidget(self.trend_table)

        unit_page = QWidget()
        unit_page.setStyleSheet("background: #F4F7FA;")
        unit_layout = QVBoxLayout(unit_page)
        unit_note = QLabel(
            "Gunakan tabel ini untuk melihat unit dengan proporsi risiko tinggi "
            "yang perlu evaluasi lebih lanjut."
        )
        unit_note.setWordWrap(True)
        unit_note.setStyleSheet("color: #526372;")
        unit_layout.addWidget(unit_note)
        unit_layout.addWidget(self.unit_table)

        detail_tabs = QTabWidget()
        detail_tabs.setObjectName("dashboardDetailTabs")
        detail_tabs.setMinimumHeight(330)
        detail_tabs.addTab(trend_page, "Tren Bulanan")
        detail_tabs.addTab(unit_page, "Per Unit/Depo")

        definitions = QLabel(
            "Cara membaca: Risiko tinggi adalah gabungan HIGH_RISK dan CRITICAL. "
            "Tindak lanjut adalah intervensi selesai pada resep berisiko tinggi. "
            "Rekomendasi diterima mencakup diterima seluruhnya atau sebagian. "
            "Angka adalah potensi interaksi berbasis pasangan obat pada basis aktif, bukan bukti "
            "kesalahan dokter atau apoteker. Keputusan terapi tetap memerlukan konteks klinis, "
            "manfaat-risiko, rekonsiliasi, dan penilaian profesional. Dashboard tidak menampilkan "
            "identitas pasien atau peringkat tenaga kesehatan."
        )
        definitions.setWordWrap(True)
        definitions.setStyleSheet(
            "background: #F8FAFC; color: #334155; border: 1px solid #CBD5E1; "
            "padding: 9px; border-radius: 5px;"
        )

        content = QWidget()
        content.setObjectName("dashboardContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(
            "QWidget#dashboardContent { background: #F4F7FA; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addLayout(filters)
        layout.addWidget(self.period_label)
        layout.addLayout(cards)
        layout.addWidget(safety_card)
        layout.addWidget(self.open_alert)
        layout.addWidget(performance)
        layout.addWidget(detail_tabs, 1)
        layout.addWidget(definitions)

        scroll = QScrollArea()
        scroll.setObjectName("dashboardScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background: #F4F7FA;")
        scroll.setWidget(content)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)
        self.refresh()

    def _build_card(
        self, key: str, title: str, description: str, accent: str, background: str
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("dashboardMetricCard")
        card.setStyleSheet(
            f"QFrame#dashboardMetricCard {{ background: {background}; "
            f"border: 1px solid {accent}; border-radius: 8px; }}"
        )
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {accent}; font-weight: 700;")
        value = QLabel("0")
        value.setObjectName(f"dashboardMetric_{key}")
        value.setStyleSheet(
            f"color: {accent}; font-size: 21pt; font-weight: 800;"
        )
        context = QLabel("Belum ada data")
        context.setWordWrap(True)
        context.setStyleSheet("color: #475569; font-size: 9pt;")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: #64748B; font-size: 8.5pt;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 9, 12, 9)
        card_layout.addWidget(title_label)
        card_layout.addWidget(value)
        card_layout.addWidget(context)
        card_layout.addWidget(description_label)
        self.card_values[key] = value
        self.card_context[key] = context
        return card

    @staticmethod
    def _progress_bar(name: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat(f"{name}: 0.0%")
        bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; color: #0F172A; "
            "border: 1px solid #CBD5E1; border-radius: 6px; text-align: center; "
            "min-height: 22px; font-weight: 600; }"
            "QProgressBar::chunk { background: #2563EB; border-radius: 5px; }"
        )
        return bar

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(False)

    def _anchor(self) -> date:
        if str(self.period_combo.currentData() or "DAY") == "DAY":
            selected = self.day_edit.date()
            return date(selected.year(), selected.month(), selected.day())
        year = int(self.year_combo.currentData() or utc_now().year)
        month = int(self.month_combo.currentData() or 1)
        return date(year, month, 1)

    @Slot()
    def refresh(self) -> None:
        period_code = str(self.period_combo.currentData() or "YEAR")
        self.month_combo.setEnabled(period_code in {"MONTH", "QUARTER"})
        self.day_edit.setEnabled(period_code == "DAY")
        anchor = self._anchor()
        summary = self.container.dashboard.summary(period_code, anchor)
        self._render_summary(summary)
        self._render_units(period_code, anchor)
        self._render_trend(anchor.year)
        self.period_label.setToolTip(
            "Periode DAY memakai hari operasional PC dan hasil skrining efektif terbaru per resep. "
            "Tanggal pelayanan sumber tidak disimpulkan bila belum tersedia."
        )

    def _render_summary(self, summary: DashboardSummary) -> None:
        comparison = self._comparison_text(summary)
        self.period_label.setText(
            f"Periode: {summary.period_label} · {comparison}"
        )
        self.card_values["screened"].setText(
            f"{summary.prescriptions_screened:,}".replace(",", ".")
        )
        self.card_context["screened"].setText(comparison)
        self.card_values["high_risk"].setText(str(summary.high_risk_total))
        self.card_context["high_risk"].setText(
            f"{summary.high_risk_rate:.1f}% dari seluruh resep"
        )
        self.card_values["critical"].setText(str(summary.critical))
        self.card_context["critical"].setText(
            f"{summary.critical_rate:.1f}% dari seluruh resep"
        )
        self.card_values["completed"].setText(
            str(summary.interventions_completed)
        )
        self.card_context["completed"].setText(
            f"Cakupan risiko tinggi {summary.intervention_coverage_rate:.1f}%"
        )
        self.card_values["acceptance"].setText(
            f"{summary.acceptance_rate:.1f}%"
            if summary.communicated
            else "—"
        )
        self.card_context["acceptance"].setText(
            f"{summary.accepted} dari {summary.communicated} hasil komunikasi"
            if summary.communicated
            else "Belum ada hasil komunikasi terdokumentasi"
        )
        self.card_values["complete_data"].setText(
            f"{summary.completeness_rate:.1f}%"
        )
        self.card_context["complete_data"].setText(
            f"{summary.incomplete} resep memiliki obat/pasangan belum dapat dinilai; ini bukan status belum ditinjau"
        )
        for key, count in (
            ('contraindicated_pairs', summary.contraindicated_pairs),
            ('serious_pairs', summary.serious_pairs),
            ('significant_pairs', summary.significant_pairs),
            ('minor_pairs', summary.minor_pairs),
            ('assessed_no_interaction_pairs', summary.assessed_no_interaction_pairs),
            ('not_assessed_pairs', summary.not_assessed_pairs),
            ('unique_ddi_pairs', summary.unique_ddi_pairs),
            ('cross_prescription_findings', summary.cross_prescription_findings),
            ("duplicate_therapy", summary.duplicate_therapy),
            ("polypharmacy", summary.polypharmacy),
            ("high_alert", summary.high_alert),
            ("lasa", summary.lasa),
        ):
            rate = (count / summary.prescriptions_screened * 100) if summary.prescriptions_screened else 0.0
            self.safety_values[key].setText(f"{count}\n{rate:.1f} per 100 resep")

        if summary.interventions_open:
            self.open_alert.setText(
                f"PERLU TINDAK LANJUT: {summary.interventions_open} intervensi "
                "masih berstatus belum selesai."
            )
            self.open_alert.setStyleSheet(
                "background: #FEF3C7; color: #92400E; border: 1px solid #F59E0B; "
                "padding: 9px; border-radius: 5px; font-weight: 700;"
            )
        else:
            self.open_alert.setText(
                "Tidak ada intervensi terbuka pada periode terpilih."
            )
            self.open_alert.setStyleSheet(
                "background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; "
                "padding: 9px; border-radius: 5px; font-weight: 650;"
            )

        self._set_progress(
            self.coverage_bar,
            "Tindak lanjut risiko tinggi",
            summary.intervention_coverage_rate,
        )
        self._set_progress(
            self.acceptance_bar,
            "Penerimaan rekomendasi",
            summary.acceptance_rate,
        )
        self._set_progress(
            self.completeness_bar,
            "Cakupan penilaian DDI",
            summary.completeness_rate,
        )

    def _render_units(self, period_code: str, anchor: date) -> None:
        rows = self.container.dashboard.by_unit(period_code, anchor)
        self.unit_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.service_unit,
                row.prescriptions,
                row.critical,
                row.high_risk,
                f"{row.risk_rate:.1f}%",
                row.interventions,
            )
            for column, value in enumerate(values):
                self.unit_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self.unit_table.resizeColumnsToContents()

    def _render_trend(self, year: int) -> None:
        rows = self.container.dashboard.monthly_trend(year)
        self.trend_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.month_label,
                row.prescriptions,
                row.critical,
                f"{row.critical_rate:.1f}%",
                row.high_risk,
                f"{row.high_risk_rate:.1f}%",
                row.interventions_completed,
                f"{row.acceptance_rate:.1f}%" if row.communicated else "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if row.prescriptions == 0:
                    item.setForeground(Qt.GlobalColor.gray)
                self.trend_table.setItem(row_index, column, item)
        self.trend_table.resizeColumnsToContents()

    @staticmethod
    def _comparison_text(summary: DashboardSummary) -> str:
        change = summary.prescription_change_percent
        if summary.period_code == "ALL":
            return "ringkasan seluruh periode tersimpan"
        if change is None:
            return "belum ada data pada periode pembanding sebelumnya"
        direction = "naik" if change > 0 else ("turun" if change < 0 else "tetap")
        return (
            f"volume {direction} {abs(change):.1f}% dibanding periode sebelumnya "
            f"({summary.previous_prescriptions} resep)"
        )

    @staticmethod
    def _set_progress(bar: QProgressBar, name: str, value: float) -> None:
        safe_value = max(0.0, min(value, 100.0))
        bar.setValue(round(safe_value * 10))
        bar.setFormat(f"{name}: {value:.1f}%")

    @Slot()
    def export_csv(self) -> None:
        anchor = self._anchor()
        period_code = str(self.period_combo.currentData() or "YEAR")
        period = self.container.dashboard.period_bounds(period_code, anchor)
        safe_period = period.label.lower().replace(" ", "-")
        initial = str(
            self.container.settings.export_dir
            / f"laporan-agregat-emss-{safe_period}.csv"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Ekspor laporan agregat",
            initial,
            "CSV (*.csv)",
        )
        if not filename:
            return
        try:
            path = self.container.dashboard.export_aggregate_csv(
                filename,
                self.user.id,
                period_code,
                anchor,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Ekspor gagal", str(exc))
            return
        QMessageBox.information(
            self,
            "Ekspor selesai",
            f"Laporan {period.label} tersimpan di:\n{path}",
        )
