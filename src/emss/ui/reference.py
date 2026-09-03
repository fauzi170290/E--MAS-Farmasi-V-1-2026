"""Simple master/pair forms backed by atomic named-user services."""
from datetime import date
import logging
from sqlalchemy.exc import SQLAlchemyError

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QScrollArea, QMessageBox, QInputDialog)

from emss.services.reference import DrugEdit, ReferenceService
from emss.services.knowledge import KnowledgeError, ManualDdiRule
from emss.ui.dialogs import fit_dialog_to_available_screen
from emss.ui.presentation import status_text


def can_manage(user):
    return bool(user and user.username.strip().casefold() != "mode.farmasi" and
                user.roles.intersection(ReferenceService.ROLES))


class DrugEditor(QDialog):
    def __init__(self, container, user, drug_id="", parent=None):
        super().__init__(parent)
        self.container, self.user, self.drug_id = container, user, drug_id
        self.saved_id = ""
        old = container.reference.drug_detail(drug_id) if drug_id else {}
        self.token = old.get("updated_at", "")
        self.setWindowTitle("Edit Obat & Kandungan" if drug_id else "Tambah Obat")
        self.name = QLineEdit(old.get("name", ""))
        self.code = QLineEdit(old.get("code", ""))
        self.code.setReadOnly(bool(drug_id))
        self.code.setPlaceholderText("Kode obat SIMRS; kosongkan untuk identitas LOCAL")
        self.kfa_product = QLineEdit(old.get("kfa_product_code", ""))
        self.kfa_product.setPlaceholderText("Opsional: 92/93/94xxxxxx")
        self.ingredients = QLineEdit("; ".join(old.get("ingredients", ())))
        self.ingredients.setPlaceholderText("Kandungan terverifikasi; pisahkan dengan titik koma")
        self.ingredient_kfa = QLineEdit("; ".join(old.get("ingredient_kfa_codes", ())))
        self.ingredient_kfa.setPlaceholderText("Kode BZA 91xxxxxx sesuai urutan kandungan; posisi boleh kosong")
        self.reference = QLineEdit(old.get("reference", ""))
        self.reference.setPlaceholderText("Referensi pemetaan/kandungan yang dapat ditelusuri")
        form = QFormLayout()
        for label, field in (("Nama obat*", self.name), ("Kode obat SIMRS", self.code),
                ("Kode produk KFA", self.kfa_product), ("Kandungan*", self.ingredients),
                ("Kode BZA KFA", self.ingredient_kfa), ("Sumber/referensi*", self.reference)):
            form.addRow(label, field)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.save_button = QPushButton("Simpan && Aktifkan")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(can_manage(user))
        self.save_button.clicked.connect(self.save)
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.message)
        layout.addLayout(actions)
        fit_dialog_to_available_screen(self, 780, 420)

    def save(self):
        try:
            self.saved_id = self.container.reference.save_drug(DrugEdit(
                name=self.name.text(), code=self.code.text(),
                ingredients=tuple(self.ingredients.text().split(";")),
                reference=self.reference.text(), drug_id=self.drug_id,
                expected_updated_at=self.token,
                kfa_product_code=self.kfa_product.text(),
                ingredient_kfa_codes=tuple(self.ingredient_kfa.text().split(";"))
                    if self.ingredient_kfa.text().strip() else ()), self.user.id)
        except (ValueError, KnowledgeError) as exc:
            self.message.setText(str(exc))
            return
        except SQLAlchemyError:
            logging.getLogger(__name__).exception("Drug save transaction failed")
            self.message.setText("Penyimpanan gagal atau database sedang sibuk. Tidak ada aktivasi; coba lagi setelah muat ulang.")
            return
        self.accept()


class DrugPicker(QWidget):
    def __init__(self, container, drug_id="", parent=None):
        super().__init__(parent)
        self.container = container
        self.search = QLineEdit()
        self.search.setPlaceholderText("Nama obat / kode lalu Enter")
        self.products, self.ingredient = QComboBox(), QComboBox()
        self.products.setMinimumContentsLength(12)
        self.products.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search.returnPressed.connect(self.reload)
        find = QPushButton("Cari")
        find.clicked.connect(self.reload)
        self.products.currentIndexChanged.connect(self.components)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        search = QHBoxLayout()
        search.addWidget(self.search)
        search.addWidget(find)
        layout.addLayout(search)
        layout.addWidget(self.products)
        layout.addWidget(self.ingredient)
        self.reload()
        if drug_id:
            self.select_drug(drug_id)

    def reload(self):
        self.products.blockSignals(True)
        self.products.clear()
        self.products.addItem("Pilih obat dari master", None)
        for drug in self.container.catalog.list_drugs(self.search.text(), limit=100):
            self.products.addItem(f"{drug.display_name} [{drug.khanza_code}]", drug)
        self.products.blockSignals(False)
        self.components()

    def select_drug(self, drug_id):
        drug = self.container.reference.drug_detail(drug_id)
        self.search.setText(drug["code"])
        self.reload()
        for index in range(1, self.products.count()):
            if self.products.itemData(index).id == drug_id:
                self.products.setCurrentIndex(index)
                break

    def components(self, *_):
        self.ingredient.clear()
        self.ingredient.addItem("Pilih kandungan yang dinilai", "")
        drug = self.products.currentData()
        if drug:
            records = self.container.reference.drug_detail(drug.id)["usable_ingredient_records"]
            for record in records:
                label = record["name"] + (f" [{record['kfa_bza_code']}]" if record["kfa_bza_code"] else "")
                self.ingredient.addItem(label, record["name"])
            if len(records) == 1:
                self.ingredient.setCurrentIndex(1)
            elif not records:
                self.ingredient.setItemText(0, "Periksa/aktifkan pemetaan di Master Obat")


class PairEditor(QDialog):
    def __init__(self, container, user, rule_id="", drug_id="", parent=None):
        super().__init__(parent)
        self.container, self.user, self.rule_id = container, user, rule_id
        self.version = container.reference.active_version_id()
        old = container.reference.pair_detail(rule_id) if rule_id else {}
        self.setWindowTitle("Edit Pasangan Interaksi Obat" if rule_id else "Tambah Pasangan Interaksi Obat")
        self.old = old
        outer = QVBoxLayout(self)
        body = QWidget()
        body.setObjectName("referenceFormBody")
        body.setStyleSheet("QWidget#referenceFormBody { background: #F4F7FA; }")
        layout = QVBoxLayout(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        if rule_id:
            low, high = old["pair_key"].split(" || ", 1)
            self.names = (low, high)
            label = QLabel(f"{low} vs {high}")
            label.setWordWrap(True)
            layout.addWidget(label)
        else:
            self.left, self.right = DrugPicker(container, drug_id), DrugPicker(container)
            pickers = QHBoxLayout()
            pickers.addWidget(self.left)
            pickers.addWidget(QLabel("VS"))
            pickers.addWidget(self.right)
            layout.addLayout(pickers)
            add = QPushButton("Tambah Obat Baru")
            add.clicked.connect(self.add_drug)
            layout.addWidget(add)
        self.status, self.severity = QComboBox(), QComboBox()
        for code in ("INTERACTION_FOUND", "ASSESSED_NO_INTERACTION", "NOT_ASSESSABLE", "EXCLUDED"):
            self.status.addItem(status_text(code), code)
        for code in ("MINOR", "SIGNIFICANT", "SERIOUS", "CONTRAINDICATED", "NONE"):
            self.severity.addItem(status_text(code), code)
        self.status.setCurrentIndex(max(0, self.status.findData(old.get("interaction_status", "INTERACTION_FOUND"))))
        self.severity.setCurrentIndex(max(0, self.severity.findData(old.get("severity_code", "SIGNIFICANT"))))
        self.status.currentIndexChanged.connect(self.status_changed)
        self.source = QLineEdit(old.get("source_name", ""))
        self.reference = QLineEdit(old.get("source_reference") or "")
        self.effect = QLineEdit(old.get("clinical_effect") or "")
        self.recommendation = QLineEdit(old.get("recommendation") or "")
        self.monitoring = QLineEdit(old.get("monitoring") or "")
        form = QFormLayout()
        for label, field in (("Status interaksi*", self.status), ("Severity*", self.severity),
                ("Sumber*", self.source), ("Referensi / DOI / URL*", self.reference),
                ("Efek klinis", self.effect), ("Rekomendasi", self.recommendation),
                ("Monitoring", self.monitoring)):
            form.addRow(label, field)
        layout.addLayout(form)
        note = QLabel("Satu pair menilai satu pasangan kandungan. Obat kombinasi: pilih kandungan yang dinilai; "
                      "hasil tidak otomatis berlaku bagi semua komponen. Aktivasi dicatat atas akun Anda.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        for field in (self.source, self.reference, self.effect, self.recommendation, self.monitoring):
            field.textChanged.connect(self.message.clear)
        actions = QHBoxLayout()
        self.save_button = QPushButton("Simpan && Aktifkan")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(can_manage(user))
        self.save_button.clicked.connect(lambda: self.save(True))
        actions.addWidget(self.save_button)
        if rule_id:
            self.deactivate = QPushButton("Nonaktifkan Pair")
            self.deactivate.setEnabled(can_manage(user))
            self.deactivate.clicked.connect(lambda: self.save(False))
            actions.addWidget(self.deactivate)
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        outer.addLayout(actions)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        fit_dialog_to_available_screen(self, 850, 680)

    def status_changed(self):
        if self.status.currentData() != "INTERACTION_FOUND":
            self.severity.setCurrentIndex(self.severity.findData("NONE"))
        elif self.severity.currentData() == "NONE":
            self.severity.setCurrentIndex(self.severity.findData("SIGNIFICANT"))

    def add_drug(self):
        dialog = DrugEditor(self.container, self.user, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.left.select_drug(dialog.saved_id)

    def save(self, active):
        names = self.names if self.rule_id else (self.left.ingredient.currentData(),
                                                 self.right.ingredient.currentData())
        try:
            if not all(names):
                raise KnowledgeError("Pilih kedua obat dan kandungan yang dinilai.")
            self.container.reference.save_pair(ManualDdiRule(
                version_id=self.version, ingredient_a=names[0], ingredient_b=names[1],
                interaction_status=self.status.currentData(), severity_code=self.severity.currentData(),
                source_name=self.source.text(), source_reference=self.reference.text(),
                source_accessed_at=date.today(), clinical_effect=self.effect.text(),
                recommendation=self.recommendation.text(), monitoring=self.monitoring.text(),
                mechanism=self.old.get("mechanism") or "", population_risk=self.old.get("population_risk") or "",
                notes=self.old.get("notes") or ""), self.user.id,
                expected_version_id=self.version, edit_rule_id=self.rule_id, active=active,
                selected_drug_ids=() if self.rule_id else (self.left.products.currentData().id, self.right.products.currentData().id))
        except (ValueError, KnowledgeError) as exc:
            self.message.setText(str(exc))
            return
        except SQLAlchemyError:
            logging.getLogger(__name__).exception("Pair activation transaction failed")
            self.message.setText("Aktivasi gagal atau database sedang sibuk. Muat ulang sebelum mencoba kembali.")
            return
        self.accept()


class ReferencePairsPanel(QWidget):
    changed = Signal()

    def __init__(self, container, user):
        super().__init__()
        self.container, self.user = container, user
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari pasangan atau referensi")
        self.search.returnPressed.connect(self.refresh)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Pasangan kandungan", "Penilaian", "Severity", "Status"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda *_: self.edit_pair() if can_manage(user) else self.view_pair())
        self.new_button = QPushButton("Tambah Pasangan DDI")
        self.new_button.setEnabled(can_manage(user))
        self.new_button.clicked.connect(lambda: self.add_pair())
        self.edit_button = QPushButton("Edit / Nonaktifkan")
        self.edit_button.setEnabled(can_manage(user))
        self.edit_button.clicked.connect(self.edit_pair)
        self.activate_button = QPushButton("Validasi KFT && Aktifkan yang Memenuhi Syarat")
        self.activate_button.setObjectName("primary")
        self.activate_button.clicked.connect(self.activate_h3)
        self.activate_hold_button = QPushButton("Aktifkan 175 Pair HOLD (Keputusan KFT)")
        self.activate_hold_button.setObjectName("primary")
        self.activate_hold_button.clicked.connect(self.activate_h5_hold)
        self.activate_reference_basis_button = QPushButton("Aktifkan Basis Referensi Aman (3.646 Pair)")
        self.activate_reference_basis_button.clicked.connect(self.activate_reference_basis)
        refresh = QPushButton("Muat Ulang")
        refresh.clicked.connect(self.refresh)
        detail = QPushButton("Lihat Referensi")
        detail.clicked.connect(self.view_pair)
        archive = QPushButton("Arsip versi / draft lama")
        archive.clicked.connect(self.archive)
        actions = QHBoxLayout()
        for button in (self.activate_button, self.activate_hold_button, self.activate_reference_basis_button, self.new_button,
                       self.edit_button, detail, refresh, archive):
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addLayout(actions)
        layout.addWidget(self.search)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        version = self.container.reference.display_version()
        rows = self.container.knowledge.list_rules(version["id"], self.search.text(), limit=10000) if version else []
        published = bool(version and version["status"] == "PUBLISHED")
        self.edit_button.setEnabled(can_manage(self.user) and published)
        self.activate_button.setEnabled(can_manage(self.user) and bool(version) and not published)
        active_count = sum(
            row.interaction_status == "INTERACTION_FOUND"
            and row.is_enabled and row.activation_status == "ACTIVE"
            for row in rows
        )
        active_reference_count = sum(
            row.interaction_status == "ASSESSED_NO_INTERACTION"
            and row.is_enabled and row.activation_status == "ACTIVE"
            for row in rows
        )
        hold_count = sum(
            row.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED" for row in rows
        )
        reference_basis_count = sum(
            row.interaction_status == "ASSESSED_NO_INTERACTION"
            and row.severity_code == "NONE"
            and not (row.is_enabled and row.activation_status == "ACTIVE")
            for row in rows
        )
        self.activate_hold_button.setEnabled(can_manage(self.user) and published and hold_count > 0)
        self.activate_reference_basis_button.setEnabled(
            can_manage(self.user) and published and reference_basis_count > 0
        )
        self.summary_label.setText(
            (f"Master aktif · {active_count} pair positif aktif; "
             f"{active_reference_count} pair basis aman dari {len(rows)} pair. "
             "Aktif / Nonaktif tidak mengubah hasil lama."
                if published else
             f"Katalog bawaan terpulihkan · {len(rows)} pair ditampilkan · status DRAFT/Belum aktif. "
             "Super Admin/KFT dapat menjalankan validasi terkendali; HOLD dan DRAFT tetap nonaktif.")
            if version else "Belum ada master pasangan. Tambahkan pair atau lihat arsip/draft lama.")
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((row.pair_key.replace(" || ", " vs "),
                    status_text(row.interaction_status), status_text(row.severity_code),
                    "Aktif" if row.is_enabled and row.activation_status == "ACTIVE" else
                    ("Draft bawaan" if not published else "Nonaktif"))):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.id)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

    def activate_h3(self):
        if not can_manage(self.user):
            return
        try:
            preview = self.container.h3_activation.preview()
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Aktivasi H3 dihentikan", str(exc))
            return
        confirmation = (
            f"Akan divalidasi dan diaktifkan:\n"
            f"• {preview.eligible_pairs} pair positif memenuhi syarat\n"
            f"• {preview.mapping_eligible} pemetaan obat Khanza valid\n\n"
            f"Tetap nonaktif: {preview.held_pairs} HOLD, {preview.draft_pairs} DRAFT, "
            f"dan {preview.mapping_blocked} pemetaan bermasalah.\n\n"
            "Lanjutkan atas nama akun Anda?"
        )
        if QMessageBox.question(
            self,
            "Validasi KFT dan aktivasi terkendali",
            confirmation,
        ) != QMessageBox.StandardButton.Yes:
            return
        reason, accepted = QInputDialog.getText(
            self,
            "Catatan validasi KFT",
            "Dasar validasi/keputusan aktivasi (minimal 8 karakter):",
        )
        if not accepted:
            return
        try:
            result = self.container.h3_activation.activate(self.user.id, reason)
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Aktivasi H3 dihentikan", str(exc))
            return
        self.refresh()
        self.changed.emit()
        QMessageBox.information(
            self,
            "Aktivasi H3 selesai",
            f"{result.active_pairs} pair positif aktif dan "
            f"{result.mapping_eligible} pemetaan Khanza disetujui.\n"
            f"{result.held_pairs} HOLD serta {result.draft_pairs} DRAFT tetap nonaktif.\n"
            f"Validator: {result.activated_by}",
        )

    def activate_h5_hold(self):
        if not can_manage(self.user):
            return
        try:
            preview = self.container.h3_activation.preview_hold_cohort()
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Validasi HOLD dihentikan", str(exc))
            return
        missing = len(preview.missing_source_reference_pairs)
        confirmation = (
            f"Akan diaktifkan {preview.hold_pairs} pair HOLD setelah validasi H5-B.\n"
            f"Profil severity: {dict(preview.severity_counts)}.\n\n"
            + (
                f"PERHATIAN: {missing} pair belum memiliki referensi sumber pada bundle. "
                "Persetujuan ini dicatat sebagai keputusan KFT dan pair tetap ditandai dalam audit.\n\n"
                if missing else ""
            )
            + "Lanjutkan atas nama akun Anda?"
        )
        if QMessageBox.question(
            self,
            "Aktivasi cohort HOLD — keputusan KFT",
            confirmation,
        ) != QMessageBox.StandardButton.Yes:
            return
        reason, accepted = QInputDialog.getText(
            self,
            "Catatan keputusan KFT",
            "Dasar keputusan aktivasi cohort HOLD (minimal 8 karakter):",
        )
        if not accepted:
            return
        try:
            self.container.h3_activation.validate_hold_cohort(self.user.id, reason)
            result = self.container.h3_activation.activate_hold_cohort(self.user.id, reason)
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Aktivasi HOLD dihentikan", str(exc))
            return
        self.refresh()
        self.changed.emit()
        reference_note = (
            f" {len(result.missing_source_reference_pairs)} pair tanpa referensi "
            "tetap tercatat untuk tindak lanjut KFT."
            if result.missing_source_reference_pairs else ""
        )
        QMessageBox.information(
            self,
            "Aktivasi HOLD selesai",
            f"{result.activated_hold_pairs} pair HOLD telah aktif. "
            f"Total pair aktif: {result.active_pairs}.\n"
            f"Validator: {result.activated_by}.{reference_note}",
        )

    def activate_reference_basis(self):
        if not can_manage(self.user):
            return
        confirmation = (
            "Aktifkan 3.646 pair yang sudah dinilai TIDAK BERINTERAKSI sebagai "
            "basis pemeriksaan aman?\n\nPair ini tidak membuat popup DDI atau "
            "alarm risiko. Hasil skrining akan dapat menyatakan bahwa tidak ditemukan "
            "interaksi pada basis yang dinilai."
        )
        if QMessageBox.question(
            self, "Aktivasi basis referensi DDI", confirmation
        ) != QMessageBox.StandardButton.Yes:
            return
        reason, accepted = QInputDialog.getText(
            self,
            "Catatan keputusan KFT",
            "Dasar aktivasi basis referensi aman (minimal 8 karakter):",
        )
        if not accepted:
            return
        try:
            result = self.container.h3_activation.activate_no_interaction_reference_basis(
                self.user.id, reason
            )
        except KnowledgeError as exc:
            QMessageBox.warning(self, "Aktivasi basis dihentikan", str(exc))
            return
        self.refresh()
        self.changed.emit()
        QMessageBox.information(
            self,
            "Basis referensi aktif",
            f"{result.activated_reference_pairs} pair tanpa interaksi telah aktif "
            f"sebagai basis pemeriksaan tanpa alert. Validator: {result.activated_by}.",
        )

    def add_pair(self, drug_id=""):
        if can_manage(self.user):
            if PairEditor(self.container, self.user, drug_id=drug_id, parent=self).exec() == QDialog.DialogCode.Accepted:
                self.refresh()
                self.changed.emit()

    def edit_pair(self):
        selected = self.table.selectionModel().selectedRows()
        version = self.container.reference.display_version()
        if selected and can_manage(self.user) and version and version["status"] == "PUBLISHED":
            rule = self.table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            if PairEditor(self.container, self.user, rule_id=rule, parent=self).exec() == QDialog.DialogCode.Accepted:
                self.refresh()
                self.changed.emit()
        elif selected and version and version["status"] != "PUBLISHED":
            self.view_pair()

    def archive(self):
        from emss.ui.knowledge.management import KnowledgeBaseTab
        dialog = QDialog(self)
        dialog.setWindowTitle("Arsip versi dan draft lama — pengelolaan lanjutan")
        layout = QVBoxLayout(dialog)
        layout.addWidget(KnowledgeBaseTab(self.container, self.user))
        fit_dialog_to_available_screen(dialog, 1100, 760)
        dialog.exec()
        self.refresh()

    def view_pair(self):
        from emss.ui.knowledge.management import DdiRuleDetailDialog
        selected = self.table.selectionModel().selectedRows()
        if selected:
            rule = self.table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            DdiRuleDetailDialog(self.container.knowledge.get_rule_detail(rule), self).exec()
