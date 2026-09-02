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
from emss.services.uat_release import UatReleaseError


class UatReleasePanel(QWidget):
    """Evidence-only UAT governance UI; no UAT or deployment executor."""

    def __init__(self, container: ApplicationContainer, user: AuthenticatedUser) -> None:
        super().__init__()
        self.container = container
        self.user = user
        notice = QLabel(
            "UAT Release Candidate hanya mengikat dan mengaudit evidence aktual. "
            "Aplikasi tidak menjalankan UAT, tidak membuat hasil PASS, dan tidak "
            "memberikan production authorization."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background: #FFF7ED; color: #9A3412; border: 1px solid #FDBA74; "
            "padding: 9px; border-radius: 6px;"
        )
        self.candidate_combo = QComboBox()
        self.candidate_combo.setObjectName("uatReleaseCandidate")
        self.candidate_combo.currentIndexChanged.connect(self._render)
        self.create_button = self._button("Buat Dossier RC", "createUatReleaseCandidate", self._create)
        self.evidence_type = QComboBox()
        self.evidence_type.setObjectName("uatReadinessEvidenceType")
        self.evidence_type.addItems(sorted(container.uat_release.EVIDENCE_TYPES))
        self.evidence_button = self._button("Intake Readiness JSON", "recordUatReadinessEvidence", self._record_evidence)
        self.candidate_clinical_button = self._button("Attest Dossier Klinis", "attestUatCandidateClinical", lambda: self._attest_candidate("CLINICAL"))
        self.candidate_technical_button = self._button("Attest Dossier Teknis", "attestUatCandidateTechnical", lambda: self._attest_candidate("TECHNICAL"))
        self.kit_button = self._button("Ekspor Kit UAT", "exportUatExecutionKit", self._export_kit)
        self.revoke_candidate_button = self._button("Cabut Dossier", "revokeUatCandidate", self._revoke_candidate)
        self.start_button = self._button("Mulai Execution Window", "startUatExecution", self._start)
        self.result_button = self._button("Intake Result JSON", "recordUatExecutionResult", self._record_result)
        self.issue_button = self._button("Catat Issue", "raiseUatExecutionIssue", self._raise_issue)
        self.resolve_button = self._button("Resolve Issue Terpilih", "resolveUatExecutionIssue", self._resolve_issue)
        self.sign_clinical_button = self._button("Sign-off Klinis", "signUatExecutionClinical", lambda: self._sign("CLINICAL"))
        self.sign_technical_button = self._button("Sign-off Teknis", "signUatExecutionTechnical", lambda: self._sign("TECHNICAL"))
        self.accept_button = self._button("Keputusan ACCEPT", "acceptUatExecution", lambda: self._decide("ACCEPT"))
        self.reject_button = self._button("Keputusan REJECT", "rejectUatExecution", lambda: self._decide("REJECT"))
        self.revoke_acceptance_button = self._button("Cabut UAT Acceptance", "revokeUatAcceptance", self._revoke_acceptance)
        self.receipt_button = self._button("Ekspor Acceptance Receipt", "exportUatAcceptanceReceipt", self._export_receipt)

        candidate_actions = ActionLayout()
        candidate_actions.addWidget(QLabel("Candidate:"))
        candidate_actions.addWidget(self.candidate_combo)
        for widget in (
            self.create_button, self.evidence_type, self.evidence_button,
            self.candidate_clinical_button, self.candidate_technical_button,
            self.kit_button, self.revoke_candidate_button,
        ):
            candidate_actions.addWidget(widget)
        candidate_actions.addStretch()
        execution_actions = ActionLayout()
        for widget in (
            self.start_button, self.result_button, self.issue_button, self.resolve_button,
            self.sign_clinical_button, self.sign_technical_button, self.accept_button,
            self.reject_button, self.revoke_acceptance_button, self.receipt_button,
        ):
            execution_actions.addWidget(widget)
        execution_actions.addStretch()

        self.status = QLabel()
        self.status.setObjectName("uatReleaseStatus")
        self.status.setWordWrap(True)
        self.blockers = QTextBrowser()
        self.blockers.setObjectName("uatReleaseBlockers")
        self.blockers.setMaximumHeight(90)
        self.evidence_table = self._table(
            "uatReadinessEvidenceTable", ["Jenis", "File", "Observed", "Valid sampai", "Recorder", "SHA-256"]
        )
        self.result_table = self._table(
            "uatExecutionResultTable", ["Scenario", "Owner", "Status", "File", "Tester", "SHA-256"]
        )
        self.issue_table = self._table(
            "uatExecutionIssueTable", ["No", 'Tingkat keparahan', "Status", "Summary hash", "Resolution hash", "ID"]
        )
        self.issue_table.setColumnHidden(5, True)
        self.issue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ledger_table = self._table(
            "uatReleaseLedgerTable", ["Sumber", "Urutan", "Waktu", "Event", "Aktor", "Hash"]
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(notice)
        layout.addLayout(candidate_actions)
        layout.addLayout(execution_actions)
        layout.addWidget(self.status)
        layout.addWidget(self.blockers)
        layout.addWidget(QLabel("Readiness evidence immutable — metadata/checksum saja"))
        layout.addWidget(self.evidence_table)
        layout.addWidget(QLabel("Execution result attempts append-only"))
        layout.addWidget(self.result_table)
        layout.addWidget(QLabel("Issue dan remediasi ber-hash"))
        layout.addWidget(self.issue_table)
        layout.addWidget(QLabel("Immutable UAT dossier/execution ledger"))
        layout.addWidget(self.ledger_table)
        self.refresh()

    @staticmethod
    def _button(label, name, callback):
        button = QPushButton(label)
        button.setObjectName(name)
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _table(name, headers):
        table = QTableWidget(0, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def refresh(self) -> None:
        selected = self._candidate_id()
        self.candidate_combo.blockSignals(True)
        self.candidate_combo.clear()
        try:
            rows = self.container.uat_release.candidates(self.user.id)
        except UatReleaseError as exc:
            self.candidate_combo.blockSignals(False)
            self.status.setText(f"UAT release tidak tersedia: {exc}")
            self._controls(None)
            return
        for row in rows:
            self.candidate_combo.addItem(
                f"{row.application_version} · {row.environment_label} · {row.status}", row.id
            )
        if selected:
            index = self.candidate_combo.findData(selected)
            if index >= 0:
                self.candidate_combo.setCurrentIndex(index)
        self.candidate_combo.blockSignals(False)
        self._render()

    def _render(self) -> None:
        candidate_id = self._candidate_id()
        if candidate_id is None:
            self.status.setText("Belum ada UAT release candidate. Evidence aktual rumah sakit tetap wajib.")
            self.blockers.setText("Fail-closed: dossier UAT belum tersedia.")
            for table in (self.evidence_table, self.result_table, self.issue_table, self.ledger_table):
                table.setRowCount(0)
            self._controls(None)
            return
        try:
            readiness = self.container.uat_release.evaluate(candidate_id, self.user.id)
            evidence = self.container.uat_release.readiness_evidence(candidate_id, self.user.id)
            ledger = self.container.uat_release.ledger(candidate_id, self.user.id)
            execution = readiness.execution
            results = self.container.uat_release.results(execution.id, self.user.id) if execution else ()
            issues = self.container.uat_release.issues(execution.id, self.user.id) if execution else ()
        except UatReleaseError as exc:
            self.status.setText(f"Fail-closed: {exc}")
            self.blockers.setText(str(exc))
            self._controls(None)
            return
        self.status.setText(
            f"Dossier {readiness.candidate.status} · execution "
            f"{execution.status if execution else 'BELUM ADA'} · accepted aktif: "
            f"{'YA' if readiness.uat_accepted_active else 'TIDAK'} · production authorization: TIDAK"
        )
        self.blockers.setText(
            "\n".join(f"• {item}" for item in readiness.blockers)
            if readiness.blockers else
            "Seluruh gate software/evidence terpenuhi. Keputusan tetap milik pihak rumah sakit."
        )
        self._fill(self.evidence_table, [(
            row.evidence_type, row.evidence_filename, row.observed_at.isoformat(),
            row.valid_until.isoformat() if row.valid_until else "-", row.recorded_by,
            row.evidence_checksum_sha256,
        ) for row in evidence])
        self._fill(self.result_table, [(
            row.scenario_code, row.owner_type, row.status, row.evidence_filename,
            row.tested_by, row.evidence_checksum_sha256,
        ) for row in results])
        self._fill(self.issue_table, [(
            row.issue_number, row.severity, row.status, row.summary_hash_sha256,
            row.resolution_hash_sha256 or "-", row.id,
        ) for row in issues])
        self._fill(self.ledger_table, [(
            row.source, row.sequence, row.occurred_at.isoformat(), row.event_type,
            row.actor_user_id or "SYSTEM", row.entry_hash,
        ) for row in ledger])
        self._controls(readiness)

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _controls(self, readiness) -> None:
        roles = self.user.roles
        technical = bool(roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        clinical = bool(roles.intersection({"APOTEKER", "CLINICAL_REVIEWER", "KFT"}))
        director = "DIREKTUR" in roles
        candidate = readiness.candidate if readiness else None
        execution = readiness.execution if readiness else None
        draft = bool(candidate and candidate.status == "DRAFT")
        sealed = bool(candidate and candidate.status == "SEALED")
        opened = bool(execution and execution.status == "OPEN")
        accepted = bool(execution and execution.status == "ACCEPTED")
        self.create_button.setVisible(technical)
        self.evidence_type.setVisible(technical)
        self.evidence_button.setVisible(technical)
        self.candidate_clinical_button.setVisible(clinical)
        self.candidate_technical_button.setVisible(technical)
        self.revoke_candidate_button.setVisible(technical or director)
        self.start_button.setVisible(director)
        self.result_button.setVisible(technical or clinical)
        self.issue_button.setVisible(technical or clinical)
        self.resolve_button.setVisible(technical or clinical)
        self.sign_clinical_button.setVisible(clinical)
        self.sign_technical_button.setVisible(technical)
        self.accept_button.setVisible(director)
        self.reject_button.setVisible(director)
        self.revoke_acceptance_button.setVisible(director)
        self.evidence_button.setEnabled(draft and technical)
        self.candidate_clinical_button.setEnabled(draft and clinical)
        self.candidate_technical_button.setEnabled(draft and technical)
        self.kit_button.setEnabled(bool(candidate and candidate.status != "REVOKED"))
        self.revoke_candidate_button.setEnabled(bool(candidate and candidate.status in {"DRAFT", "SEALED"}))
        self.start_button.setEnabled(sealed and execution is None and director)
        self.result_button.setEnabled(opened and (technical or clinical))
        self.issue_button.setEnabled(opened and (technical or clinical))
        self.resolve_button.setEnabled(opened and (technical or clinical))
        self.sign_clinical_button.setEnabled(opened and clinical)
        self.sign_technical_button.setEnabled(opened and technical)
        self.accept_button.setEnabled(opened and director and bool(readiness and readiness.ready_for_acceptance))
        self.reject_button.setEnabled(opened and director)
        self.revoke_acceptance_button.setEnabled(accepted and director)
        self.receipt_button.setEnabled(bool(readiness and readiness.uat_accepted_active))

    def _create(self) -> None:
        report, _ = QFileDialog.getOpenFileName(self, "Pilih qualification report", "", "JSON (*.json)")
        if not report:
            return
        installer, _ = QFileDialog.getOpenFileName(self, "Pilih installer RC", "", "Executable (*.exe)")
        if not installer:
            return
        environment, accepted = QInputDialog.getText(self, "Environment UAT", "Label environment UAT:")
        if not accepted:
            return
        days, accepted = QInputDialog.getInt(self, "Expiry Dossier", "Berlaku hari (1-30):", 14, 1, 30)
        if not accepted:
            return
        try:
            self.container.uat_release.create_candidate(
                Path(report), Path(installer), environment, self.user.id, validity_days=days
            )
            self.refresh()
        except UatReleaseError as exc:
            QMessageBox.warning(self, "Dossier ditolak", str(exc))

    def _record_evidence(self) -> None:
        candidate_id = self._candidate_id()
        path, _ = QFileDialog.getOpenFileName(self, "Pilih readiness evidence", "", "JSON (*.json)")
        if candidate_id and path:
            try:
                self.container.uat_release.record_readiness_evidence(
                    candidate_id, self.evidence_type.currentText(), Path(path), self.user.id
                )
                self.refresh()
            except UatReleaseError as exc:
                QMessageBox.warning(self, "Evidence ditolak", str(exc))

    def _attest_candidate(self, kind) -> None:
        self._call_candidate(lambda value: self.container.uat_release.attest_candidate(value, kind, self.user.id), "Attestation ditolak")

    def _revoke_candidate(self) -> None:
        reason = self._reason("Cabut Dossier UAT")
        if reason is not None:
            self._call_candidate(lambda value: self.container.uat_release.revoke_candidate(value, reason, self.user.id), "Revocation ditolak")

    def _export_kit(self) -> None:
        candidate_id = self._candidate_id()
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor kit UAT", "uat-execution-kit.zip", "ZIP (*.zip)")
        if candidate_id and path:
            try:
                result = self.container.uat_release.export_uat_kit(candidate_id, Path(path), self.user.id)
                QMessageBox.information(self, "Kit diekspor", f"SHA-256: {result.checksum_sha256}\nUAT belum dijalankan.")
                self.refresh()
            except UatReleaseError as exc:
                QMessageBox.warning(self, "Ekspor ditolak", str(exc))

    def _start(self) -> None:
        hours, accepted = QInputDialog.getInt(self, "Execution Window", "Durasi jam (1-168):", 8, 1, 168)
        if accepted:
            self._call_candidate(lambda value: self.container.uat_release.start_execution(value, self.user.id, duration_hours=hours), "Execution ditolak")

    def _record_result(self) -> None:
        execution_id = self._execution_id()
        path, _ = QFileDialog.getOpenFileName(self, "Pilih UAT result evidence", "", "JSON (*.json)")
        if execution_id and path:
            self._call(lambda: self.container.uat_release.record_result(execution_id, Path(path), self.user.id), "Result ditolak")

    def _raise_issue(self) -> None:
        execution_id = self._execution_id()
        severity, accepted = QInputDialog.getItem(self, "Issue UAT", "Severity:", ["WARNING", "CRITICAL"], 0, False)
        if not accepted:
            return
        reason = self._reason("Ringkasan Issue UAT")
        if execution_id and reason is not None:
            self._call(lambda: self.container.uat_release.raise_issue(execution_id, severity, reason, self.user.id), "Issue ditolak")

    def _resolve_issue(self) -> None:
        row = self.issue_table.currentRow()
        if row < 0:
            return
        item = self.issue_table.item(row, 5)
        reason = self._reason("Remediasi Issue UAT")
        if item and reason is not None:
            self._call(lambda: self.container.uat_release.resolve_issue(item.text(), reason, self.user.id), "Remediasi ditolak")

    def _sign(self, kind) -> None:
        execution_id = self._execution_id()
        if execution_id:
            self._call(lambda: self.container.uat_release.sign_execution(execution_id, kind, self.user.id), "Sign-off ditolak")

    def _decide(self, decision) -> None:
        execution_id = self._execution_id()
        reason = self._reason(f"Keputusan UAT {decision}")
        if execution_id and reason is not None:
            self._call(lambda: self.container.uat_release.decide_execution(execution_id, decision, reason, self.user.id), "Keputusan ditolak")

    def _revoke_acceptance(self) -> None:
        execution_id = self._execution_id()
        reason = self._reason("Cabut UAT Acceptance")
        if execution_id and reason is not None:
            self._call(lambda: self.container.uat_release.revoke_acceptance(execution_id, reason, self.user.id), "Revocation ditolak")

    def _export_receipt(self) -> None:
        execution_id = self._execution_id()
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor UAT receipt", "uat-acceptance-receipt.json", "JSON (*.json)")
        if execution_id and path:
            self._call(lambda: self.container.uat_release.export_acceptance_receipt(execution_id, Path(path), self.user.id), "Ekspor receipt ditolak")

    def _call_candidate(self, callback, title) -> None:
        candidate_id = self._candidate_id()
        if candidate_id:
            self._call(lambda: callback(candidate_id), title)

    def _call(self, callback, title) -> None:
        try:
            callback()
            self.refresh()
        except UatReleaseError as exc:
            QMessageBox.warning(self, title, str(exc))

    @staticmethod
    def _reason(title):
        value, accepted = QInputDialog.getText(None, title, "Alasan 10-300 karakter (disimpan sebagai SHA-256):")
        return value if accepted else None

    def _candidate_id(self):
        value = self.candidate_combo.currentData()
        return str(value) if value else None

    def _execution_id(self):
        candidate_id = self._candidate_id()
        if not candidate_id:
            return None
        try:
            row = self.container.uat_release.execution(candidate_id, self.user.id)
        except UatReleaseError:
            return None
        return row.id if row else None
