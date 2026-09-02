from __future__ import annotations
from emss.ui.navigation import ActionLayout

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.production_release import ProductionReleaseError
from emss.services.surveillance import SurveillanceError


class ProductionReleasePanel(QWidget):
    """Manual governance UI; intentionally has no deployment execution control."""

    EVIDENCE_TYPES = (
        "AUTHENTICODE",
        "FORMAL_WAIVER",
        "CLEAN_INSTALL",
        "CLEAN_UPGRADE",
        "CLEAN_UNINSTALL",
        "DATA_PRESERVATION",
        "ROLLBACK_RESTORE",
    )

    def __init__(self, container: ApplicationContainer, user: AuthenticatedUser) -> None:
        super().__init__()
        self.container = container
        self.user = user
        notice = QLabel(
            "Production Release Record hanya menerima Early-Life Surveillance PROMOTED. "
            "Otorisasi bersifat manual, terbatas deployment window, dapat dicabut, dan "
            "tidak pernah menjalankan installer atau mengubah sistem produksi otomatis."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background: #FFF7ED; color: #9A3412; border: 1px solid #FDBA74; "
            "padding: 9px; border-radius: 6px;"
        )
        self.record_combo = QComboBox()
        self.record_combo.setObjectName("productionReleaseRecord")
        self.record_combo.currentIndexChanged.connect(self._render_selection)
        self.create_button = QPushButton("Buat Production Release Record")
        self.create_button.setObjectName("createProductionReleaseRecord")
        self.create_button.clicked.connect(self._create_record)
        self.evidence_type = QComboBox()
        self.evidence_type.setObjectName("productionEvidenceType")
        self.evidence_type.addItems(self.EVIDENCE_TYPES)
        self.evidence_button = QPushButton("Intake Evidence JSON")
        self.evidence_button.setObjectName("recordProductionEvidence")
        self.evidence_button.clicked.connect(self._record_evidence)
        self.change_button = QPushButton("Catat Change Approval")
        self.change_button.setObjectName("recordProductionChangeApproval")
        self.change_button.clicked.connect(self._record_change_approval)
        self.authorize_button = QPushButton("Keputusan AUTHORIZE")
        self.authorize_button.setObjectName("authorizeProductionRelease")
        self.authorize_button.clicked.connect(lambda: self._decide("AUTHORIZE"))
        self.reject_button = QPushButton("Keputusan REJECT")
        self.reject_button.setObjectName("rejectProductionRelease")
        self.reject_button.clicked.connect(lambda: self._decide("REJECT"))
        self.revoke_button = QPushButton("Cabut Authorization")
        self.revoke_button.setObjectName("revokeProductionRelease")
        self.revoke_button.clicked.connect(self._revoke)
        self.rollback_button = QPushButton("Order Emergency Rollback")
        self.rollback_button.setObjectName("orderProductionEmergencyRollback")
        self.rollback_button.setStyleSheet(
            "background: #991B1B; color: white; font-weight: 700;"
        )
        self.rollback_button.clicked.connect(self._rollback)
        self.verify_package_button = QPushButton("Verifikasi Evidence Package ZIP")
        self.verify_package_button.setObjectName("verifyProductionEvidencePackage")
        self.verify_package_button.clicked.connect(self._verify_package)
        self.start_ceremony_button = QPushButton("Mulai Deployment Ceremony")
        self.start_ceremony_button.setObjectName("startProductionDeploymentCeremony")
        self.start_ceremony_button.clicked.connect(self._start_ceremony)
        self.technical_attest_button = QPushButton("Attest Teknis")
        self.technical_attest_button.setObjectName("attestProductionCeremonyTechnical")
        self.technical_attest_button.clicked.connect(lambda: self._attest_ceremony("TECHNICAL"))
        self.clinical_attest_button = QPushButton("Attest Klinis")
        self.clinical_attest_button.setObjectName("attestProductionCeremonyClinical")
        self.clinical_attest_button.clicked.connect(lambda: self._attest_ceremony("CLINICAL"))
        self.abort_ceremony_button = QPushButton("Abort Ceremony")
        self.abort_ceremony_button.setObjectName("abortProductionDeploymentCeremony")
        self.abort_ceremony_button.clicked.connect(self._abort_ceremony)
        self.export_receipt_button = QPushButton("Ekspor Authorization Receipt")
        self.export_receipt_button.setObjectName("exportProductionAuthorizationReceipt")
        self.export_receipt_button.clicked.connect(self._export_receipt)
        actions = ActionLayout()
        actions.addWidget(QLabel("Record:"))
        actions.addWidget(self.record_combo)
        for widget in (
            self.create_button,
            self.evidence_type,
            self.evidence_button,
            self.change_button,
            self.authorize_button,
            self.reject_button,
            self.revoke_button,
            self.rollback_button,
        ):
            actions.addWidget(widget)
        actions.addStretch()
        ceremony_actions = ActionLayout()
        for widget in (
            self.verify_package_button,
            self.start_ceremony_button,
            self.technical_attest_button,
            self.clinical_attest_button,
            self.abort_ceremony_button,
            self.export_receipt_button,
        ):
            ceremony_actions.addWidget(widget)
        ceremony_actions.addStretch()
        self.status = QLabel()
        self.status.setObjectName("productionReleaseStatus")
        self.status.setWordWrap(True)
        self.blockers = QTextBrowser()
        self.blockers.setObjectName("productionReleaseBlockers")
        self.blockers.setMaximumHeight(90)
        self.evidence_table = QTableWidget(0, 6)
        self.evidence_table.setObjectName("productionReleaseEvidenceTable")
        self.evidence_table.setHorizontalHeaderLabels(
            ["Jenis", "File", "Observed", "Valid sampai", "Recorder", "SHA-256"]
        )
        self.evidence_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.evidence_table.horizontalHeader().setStretchLastSection(True)
        self.package_table = QTableWidget(0, 5)
        self.package_table.setObjectName("productionEvidenceVerificationTable")
        self.package_table.setHorizontalHeaderLabels(
            ["Waktu", "Paket", "Status", "Error", "SHA-256"]
        )
        self.package_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.package_table.horizontalHeader().setStretchLastSection(True)
        self.ledger_table = QTableWidget(0, 5)
        self.ledger_table.setObjectName("productionReleaseLedgerTable")
        self.ledger_table.setHorizontalHeaderLabels(
            ["Urutan", "Waktu", "Event", "Aktor", "Hash"]
        )
        self.ledger_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ledger_table.horizontalHeader().setStretchLastSection(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(notice)
        layout.addLayout(actions)
        layout.addLayout(ceremony_actions)
        layout.addWidget(self.status)
        layout.addWidget(self.blockers)
        layout.addWidget(QLabel("Evidence metadata immutable — tidak menyimpan isi/identitas pasien"))
        layout.addWidget(self.evidence_table)
        layout.addWidget(QLabel("Riwayat verifikasi evidence package append-only"))
        layout.addWidget(self.package_table)
        layout.addWidget(QLabel("Immutable production release ledger"))
        layout.addWidget(self.ledger_table)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_id()
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        try:
            records = self.container.production_release.records(self.user.id)
        except ProductionReleaseError as exc:
            self.record_combo.blockSignals(False)
            self.status.setText(f"Production release tidak tersedia: {exc}")
            self._set_controls(None)
            return
        for record in records:
            self.record_combo.addItem(
                f"{record.application_version} · {record.environment_label} · {record.status}",
                record.id,
            )
        if selected:
            index = self.record_combo.findData(selected)
            if index >= 0:
                self.record_combo.setCurrentIndex(index)
        self.record_combo.blockSignals(False)
        self._render_selection()

    def _render_selection(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            self.status.setText(
                "Belum ada production release record. Bukti eksternal aktual tetap diperlukan."
            )
            self.blockers.setText("Fail-closed: tidak ada deployment authorization.")
            self.evidence_table.setRowCount(0)
            self.package_table.setRowCount(0)
            self.ledger_table.setRowCount(0)
            self._set_controls(None)
            return
        try:
            readiness = self.container.production_release.evaluate(record_id, self.user.id)
            evidence = self.container.production_release.evidence(record_id, self.user.id)
            verifications = self.container.production_evidence.verifications(record_id, self.user.id)
            ceremony = self.container.production_evidence.ceremony(record_id, self.user.id)
            ledger = tuple(
                row for row in self.container.production_release.ledger(self.user.id)
                if row.release_record_id == record_id
            )
        except ProductionReleaseError as exc:
            self.status.setText(f"Fail-closed: {exc}")
            self.blockers.setText(str(exc))
            self._set_controls(None)
            return
        record = readiness.record
        manual = "YA" if readiness.manual_deployment_authorized else "TIDAK"
        basis = readiness.signature_basis or "BELUM ADA"
        self.status.setText(
            f"Status {record.status} · versi {record.application_version} · schema "
            f"{record.schema_revision} · basis signature {basis} · manual deployment "
            f"authorized: {manual} · ceremony: {ceremony.status if ceremony else 'BELUM ADA'}"
        )
        self.blockers.setText(
            "\n".join(f"• {item}" for item in readiness.blockers)
            if readiness.blockers else
            "Seluruh gate terverifikasi untuk window aktif. Eksekusi deployment tetap manual di luar aplikasi."
        )
        self.evidence_table.setRowCount(len(evidence))
        for row_index, row in enumerate(evidence):
            values = (
                row.evidence_type,
                row.evidence_filename,
                row.observed_at.isoformat(),
                row.valid_until.isoformat() if row.valid_until else "-",
                row.recorded_by,
                row.evidence_checksum_sha256,
            )
            for column, value in enumerate(values):
                self.evidence_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.package_table.setRowCount(len(verifications))
        for row_index, row in enumerate(verifications):
            values = (
                row.verified_at.isoformat(), row.package_filename, row.status,
                row.error_code or "-", row.package_checksum_sha256,
            )
            for column, value in enumerate(values):
                self.package_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.ledger_table.setRowCount(len(ledger))
        for row_index, row in enumerate(ledger):
            values = (
                row.sequence, row.occurred_at.isoformat(), row.event_type,
                row.actor_user_id or "SYSTEM", row.entry_hash,
            )
            for column, value in enumerate(values):
                self.ledger_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self._set_controls(readiness, ceremony)

    def _set_controls(self, readiness, ceremony=None) -> None:
        technical = bool(self.user.roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        clinical = bool(self.user.roles.intersection({"APOTEKER", "CLINICAL_REVIEWER", "KFT"}))
        director = "DIREKTUR" in self.user.roles
        draft = bool(readiness and readiness.record.status == "DRAFT")
        authorized = bool(readiness and readiness.record.status == "AUTHORIZED")
        self.create_button.setVisible(technical)
        self.evidence_type.setVisible(technical)
        self.evidence_button.setVisible(technical)
        self.change_button.setVisible(director)
        self.authorize_button.setVisible(director)
        self.reject_button.setVisible(director)
        self.revoke_button.setVisible(director)
        self.rollback_button.setVisible(technical or director)
        self.verify_package_button.setVisible(technical or director)
        self.start_ceremony_button.setVisible(director)
        self.technical_attest_button.setVisible(technical)
        self.clinical_attest_button.setVisible(clinical)
        self.abort_ceremony_button.setVisible(technical or director)
        self.export_receipt_button.setVisible(True)
        self.evidence_button.setEnabled(draft and technical)
        self.change_button.setEnabled(draft and director)
        self.authorize_button.setEnabled(
            director and bool(readiness and readiness.ready_for_authorization)
        )
        self.reject_button.setEnabled(draft and director)
        self.revoke_button.setEnabled(authorized and director)
        self.rollback_button.setEnabled(bool(readiness) and (technical or director))
        open_ceremony = bool(ceremony and ceremony.status == "OPEN")
        self.verify_package_button.setEnabled(draft and (technical or director))
        self.start_ceremony_button.setEnabled(draft and director and ceremony is None)
        self.technical_attest_button.setEnabled(
            open_ceremony and technical and ceremony.technical_attested_by is None
        )
        self.clinical_attest_button.setEnabled(
            open_ceremony and clinical and ceremony.clinical_attested_by is None
        )
        self.abort_ceremony_button.setEnabled(open_ceremony and (technical or director))
        self.export_receipt_button.setEnabled(
            bool(readiness and readiness.manual_deployment_authorized)
        )

    def _verify_package(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih evidence package", "", "ZIP (*.zip)"
        )
        if not path:
            return
        try:
            result = self.container.production_evidence.verify_package(
                record_id, Path(path), self.user.id
            )
            self.refresh()
            if result.status != "VALID":
                QMessageBox.warning(
                    self,
                    "Paket INVALID",
                    f"Verifikasi ditolak fail-closed: {result.error_code}",
                )
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Verifikasi paket ditolak", str(exc))

    def _start_ceremony(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        try:
            self.container.production_evidence.start_ceremony(record_id, self.user.id)
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Ceremony ditolak", str(exc))

    def _attest_ceremony(self, kind: str) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        try:
            self.container.production_evidence.attest_ceremony(
                record_id, kind, self.user.id
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Attestation ditolak", str(exc))

    def _abort_ceremony(self) -> None:
        record_id = self._selected_id()
        reason = self._reason("Abort Deployment Ceremony")
        if record_id is None or reason is None:
            return
        try:
            self.container.production_evidence.abort_ceremony(
                record_id, reason, self.user.id
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Abort ditolak", str(exc))

    def _export_receipt(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Ekspor authorization receipt",
            "production-authorization-receipt.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            result = self.container.production_evidence.export_authorization_receipt(
                record_id, Path(path), self.user.id
            )
            QMessageBox.information(
                self,
                "Receipt diekspor",
                f"SHA-256: {result.checksum_sha256}\nDeployment tidak dijalankan.",
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Ekspor receipt ditolak", str(exc))

    def _create_record(self) -> None:
        try:
            candidates = [
                row for row in self.container.surveillance.sessions(self.user.id)
                if row.status == "PROMOTED"
            ]
        except (ProductionReleaseError, SurveillanceError) as exc:
            QMessageBox.warning(self, "Production release", str(exc))
            return
        if not candidates:
            QMessageBox.information(
                self, "Production release", "Belum ada Early-Life Surveillance PROMOTED."
            )
            return
        labels = [f"{row.application_version} · {row.environment_label} · {row.id}" for row in candidates]
        label, accepted = QInputDialog.getItem(
            self, "Production Release Record", "Surveillance PROMOTED:", labels, 0, False
        )
        if not accepted:
            return
        days, accepted = QInputDialog.getInt(
            self, "Expiry Record", "Berlaku berapa hari (1-30):", 14, 1, 30
        )
        if not accepted:
            return
        try:
            record = self.container.production_release.create_record(
                candidates[labels.index(label)].id, self.user.id, validity_days=days
            )
            self.refresh()
            index = self.record_combo.findData(record.id)
            if index >= 0:
                self.record_combo.setCurrentIndex(index)
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Record ditolak", str(exc))

    def _record_evidence(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih evidence JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.container.production_release.record_evidence(
                record_id, self.evidence_type.currentText(), Path(path), self.user.id
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Evidence ditolak", str(exc))

    def _record_change_approval(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih change approval JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.container.production_release.record_change_approval(
                record_id, Path(path), self.user.id
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Change approval ditolak", str(exc))

    def _decide(self, decision: str) -> None:
        record_id = self._selected_id()
        if record_id is None:
            return
        reason = self._reason(f"Keputusan {decision}")
        if reason is None:
            return
        warning = (
            "AUTHORIZE hanya memberi izin deployment manual selama window aktif; "
            "aplikasi tidak akan menjalankan deployment."
        )
        if QMessageBox.question(self, decision, warning) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.production_release.decide(record_id, decision, reason, self.user.id)
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Keputusan ditolak", str(exc))

    def _revoke(self) -> None:
        record_id = self._selected_id()
        reason = self._reason("Cabut Production Authorization")
        if record_id is None or reason is None:
            return
        try:
            self.container.production_release.revoke(record_id, reason, self.user.id)
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Revocation ditolak", str(exc))

    def _rollback(self) -> None:
        record_id = self._selected_id()
        reason = self._reason("Emergency Rollback Order")
        if record_id is None or reason is None:
            return
        if QMessageBox.question(
            self,
            "Emergency rollback",
            "Catat order rollback manual? Aplikasi tidak mengeksekusi rollback otomatis.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.production_release.order_emergency_rollback(
                record_id, reason, self.user.id
            )
            self.refresh()
        except ProductionReleaseError as exc:
            QMessageBox.warning(self, "Rollback order ditolak", str(exc))

    def _reason(self, title: str) -> str | None:
        reason, accepted = QInputDialog.getText(
            self, title, "Alasan 10-300 karakter (akan disimpan sebagai SHA-256):"
        )
        return reason if accepted else None

    def _selected_id(self) -> str | None:
        value = self.record_combo.currentData()
        return str(value) if value else None
