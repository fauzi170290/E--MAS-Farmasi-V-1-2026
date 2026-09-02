from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.medication_safety import MedicationSafetyError


def _line(hint: str) -> QLineEdit:
    widget = QLineEdit()
    widget.setPlaceholderText(hint)
    return widget


def _table(headers: tuple[str, ...]) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.verticalHeader().setVisible(False)
    return widget


class MedicationSafetyPanel(QWidget):
    WRITER_ROLES = {"SUPER_ADMIN", "KNOWLEDGE_ADMIN", "CLINICAL_REVIEWER", "KFT"}

    def __init__(self, container: ApplicationContainer, user: AuthenticatedUser) -> None:
        super().__init__()
        self.container = container
        self.user = user
        self.can_write = user.username != "mode.farmasi" and bool(user.roles.intersection(self.WRITER_ROLES))
        title = QLabel("Master Keselamatan Obat — Sprint 8")
        title.setStyleSheet("font-size: 16pt; font-weight: 700; color: #123B5D;")
        notice = QLabel(
            "Konfigurasi tersimpan di SQLite lokal E-MAS. High-alert dan LASA baru "
            "memengaruhi skrining setelah divalidasi; Khanza tetap READ ONLY."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("background: #E0F2FE; color: #075985; border: 1px solid #7DD3FC; padding: 10px; border-radius: 5px;")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        pages = QTabWidget()
        pages.addTab(self._policy_page(), "Kebijakan Polifarmasi")
        pages.addTab(self._therapy_page(), "Kelas Terapi")
        pages.addTab(self._high_page(), "High-Alert")
        pages.addTab(self._lasa_page(), "LASA")
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(notice)
        layout.addWidget(self.status)
        layout.addWidget(pages, 1)
        if not self.can_write:
            self.status.setText("Mode lihat saja. Login sebagai admin/validator klinis untuk mengubah master.")
        self.refresh()

    def _policy_page(self) -> QWidget:
        page = QWidget()
        self.poly = QSpinBox(); self.poly.setRange(2, 49)
        self.hyper = QSpinBox(); self.hyper.setRange(3, 50)
        self.policy_active = QCheckBox("Aktifkan pemantauan")
        button = QPushButton("Simpan & Validasi Kebijakan"); button.setObjectName("primary")
        button.setEnabled(self.can_write); button.clicked.connect(self._save_policy)
        form = QFormLayout(page)
        form.addRow("Polifarmasi mulai", self.poly)
        form.addRow("Hiperpolifarmasi mulai", self.hyper)
        form.addRow("Status", self.policy_active)
        form.addRow("", button)
        form.addRow("", QLabel("Perhitungan memakai jumlah zat aktif unik, bukan jumlah baris obat."))
        return page

    def _therapy_page(self) -> QWidget:
        page = QWidget()
        self.therapy_ingredient = _line("Nama zat aktif pada master")
        self.therapy_class = _line("Kelas terapi")
        self.therapy_subclass = _line("Opsional")
        self.therapy_atc = _line("Opsional")
        self.therapy_route = _line("Kosong = semua rute")
        self.therapy_source = _line("Kebijakan/sumber")
        self.therapy_active = QCheckBox("Aktif"); self.therapy_active.setChecked(True)
        button = QPushButton("Simpan Profil Kelas Terapi"); button.setObjectName("primary")
        button.setEnabled(self.can_write); button.clicked.connect(self._save_therapy)
        form = QFormLayout()
        for label, field in (("Zat aktif", self.therapy_ingredient), ("Kelas", self.therapy_class), ("Subkelas", self.therapy_subclass), ("ATC", self.therapy_atc), ("Konteks rute", self.therapy_route), ("Sumber", self.therapy_source), ("Status", self.therapy_active)):
            form.addRow(label, field)
        form.addRow("", button)
        self.therapy_table = _table(("Zat aktif", "Kelas", "Subkelas", "ATC", "Rute", "Aktif"))
        layout = QVBoxLayout(page); layout.addLayout(form); layout.addWidget(self.therapy_table, 1)
        return page

    def _high_page(self) -> QWidget:
        page = QWidget()
        self.high_code = _line("Kode obat Khanza")
        self.high_category = _line("Kategori high-alert")
        self.high_unit = _line("* atau nama unit/depo"); self.high_unit.setText("*")
        self.high_severity = QComboBox(); self.high_severity.addItems(("REVIEW", "INFO", "HIGH_RISK"))
        self.high_double = QCheckBox("Wajib double-check"); self.high_double.setChecked(True)
        self.high_recommendation = _line("Tindakan/rekomendasi")
        self.high_source = _line("Kebijakan/sumber")
        self.high_active = QCheckBox("Aktif"); self.high_active.setChecked(True)
        button = QPushButton("Simpan & Setujui High-Alert"); button.setObjectName("primary")
        button.setEnabled(self.can_write); button.clicked.connect(self._save_high)
        form = QFormLayout()
        for label, field in (("Kode obat", self.high_code), ("Kategori", self.high_category), ("Unit/depo", self.high_unit), ('Tingkat keparahan', self.high_severity), ("Double-check", self.high_double), ("Rekomendasi", self.high_recommendation), ("Sumber", self.high_source), ("Status", self.high_active)):
            form.addRow(label, field)
        form.addRow("", button)
        self.high_table = _table(("Kode", "Obat", "Kategori", "Unit", 'Tingkat keparahan', "Double-check", "Aktif"))
        layout = QVBoxLayout(page); layout.addLayout(form); layout.addWidget(self.high_table, 1)
        return page

    def _lasa_page(self) -> QWidget:
        page = QWidget()
        self.lasa_a = _line("Kode obat pertama")
        self.lasa_b = _line("Kode obat kedua")
        self.lasa_type = QComboBox()
        for code, label in (("LOOK_ALIKE", "Look-Alike"), ("SOUND_ALIKE", "Sound-Alike"), ("PACKAGING_SIMILAR", "Kemasan mirip"), ("STRENGTH_SIMILAR", "Kekuatan mirip"), ("GENERIC_NAME_SIMILAR", "Nama generik mirip"), ("BRAND_NAME_SIMILAR", "Nama merek mirip")):
            self.lasa_type.addItem(label, code)
        self.lasa_unit = _line("* atau nama unit/depo"); self.lasa_unit.setText("*")
        self.lasa_severity = QComboBox(); self.lasa_severity.addItems(("REVIEW", "HIGH_RISK", "INFO"))
        self.lasa_double = QCheckBox("Wajib double-check"); self.lasa_double.setChecked(True)
        self.lasa_recommendation = _line("Tindakan/rekomendasi")
        self.lasa_source = _line("Kebijakan/sumber")
        self.lasa_active = QCheckBox("Aktif"); self.lasa_active.setChecked(True)
        button = QPushButton("Simpan & Setujui Pasangan LASA"); button.setObjectName("primary")
        button.setEnabled(self.can_write); button.clicked.connect(self._save_lasa)
        form = QFormLayout()
        for label, field in (("Kode obat A", self.lasa_a), ("Kode obat B", self.lasa_b), ("Jenis", self.lasa_type), ("Unit/depo", self.lasa_unit), ('Tingkat keparahan', self.lasa_severity), ("Double-check", self.lasa_double), ("Rekomendasi", self.lasa_recommendation), ("Sumber", self.lasa_source), ("Status", self.lasa_active)):
            form.addRow(label, field)
        form.addRow("", button)
        self.lasa_table = _table(("Obat A", "Obat B", "Jenis", "Unit", 'Tingkat keparahan', "Double-check", "Aktif"))
        layout = QVBoxLayout(page); layout.addLayout(form); layout.addWidget(self.lasa_table, 1)
        return page

    @Slot()
    def refresh(self) -> None:
        policy = self.container.medication_safety.get_policy()
        self.poly.setValue(policy.polypharmacy_threshold)
        self.hyper.setValue(policy.hyperpolypharmacy_threshold)
        self.policy_active.setChecked(policy.is_active)
        self._fill(self.therapy_table, ((r.ingredient_name, r.therapeutic_class, r.therapeutic_subclass or "—", r.atc_code or "—", r.route_context or "Semua", "YA" if r.is_active else "TIDAK") for r in self.container.medication_safety.list_therapy_profiles()))
        self._fill(self.high_table, ((r.drug_code, r.drug_name, r.category, r.unit_scope, r.app_severity, "YA" if r.requires_double_check else "TIDAK", "YA" if r.is_active else "TIDAK") for r in self.container.medication_safety.list_high_alerts()))
        self._fill(self.lasa_table, ((f"{r.drug_code_a} · {r.drug_name_a}", f"{r.drug_code_b} · {r.drug_name_b}", r.lasa_type, r.unit_scope, r.app_severity, "YA" if r.requires_double_check else "TIDAK", "YA" if r.is_active else "TIDAK") for r in self.container.medication_safety.list_lasa_pairs()))

    @staticmethod
    def _fill(table: QTableWidget, rows: Iterable[tuple[object, ...]]) -> None:
        values = list(rows); table.setRowCount(len(values))
        for row_index, row in enumerate(values):
            for column, value in enumerate(row):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _run(self, action: Callable[[], None], message: str) -> None:
        try:
            action()
        except (MedicationSafetyError, PermissionError) as exc:
            self.status.setStyleSheet("color: #B42318;"); self.status.setText(f"Gagal: {exc}"); return
        self.refresh()
        self.status.setStyleSheet("color: #166534; font-weight: 600;")
        self.status.setText(f"✓ {message}. Berlaku pada skrining berikutnya.")

    @Slot()
    def _save_policy(self) -> None:
        self._run(lambda: self.container.medication_safety.update_policy(self.user.id, self.poly.value(), self.hyper.value(), self.policy_active.isChecked()), "Kebijakan polifarmasi tersimpan")

    @Slot()
    def _save_therapy(self) -> None:
        self._run(lambda: self.container.medication_safety.upsert_therapy_profile(self.user.id, self.therapy_ingredient.text(), self.therapy_class.text(), therapeutic_subclass=self.therapy_subclass.text(), atc_code=self.therapy_atc.text(), route_context=self.therapy_route.text(), source=self.therapy_source.text(), is_active=self.therapy_active.isChecked()), "Profil kelas terapi tersimpan")

    @Slot()
    def _save_high(self) -> None:
        self._run(lambda: self.container.medication_safety.upsert_high_alert(self.user.id, self.high_code.text(), self.high_category.text(), self.high_recommendation.text(), unit_scope=self.high_unit.text(), app_severity=self.high_severity.currentText(), requires_double_check=self.high_double.isChecked(), source=self.high_source.text(), is_active=self.high_active.isChecked()), "Master high-alert tersimpan")

    @Slot()
    def _save_lasa(self) -> None:
        self._run(lambda: self.container.medication_safety.upsert_lasa_pair(self.user.id, self.lasa_a.text(), self.lasa_b.text(), str(self.lasa_type.currentData()), self.lasa_recommendation.text(), unit_scope=self.lasa_unit.text(), app_severity=self.lasa_severity.currentText(), requires_double_check=self.lasa_double.isChecked(), source=self.lasa_source.text(), is_active=self.lasa_active.isChecked()), "Pasangan LASA tersimpan")
