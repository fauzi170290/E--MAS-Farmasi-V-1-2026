from __future__ import annotations
from emss.ui.navigation import ActionLayout

import shutil

from PySide6.QtCore import Qt, Slot
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
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from emss.app import ApplicationContainer
from emss.services.authentication import AuthenticatedUser
from emss.services.clinical_validation import ClinicalValidationError
from emss.services.go_live import GoLiveError
from emss.services.limited_rollout import LimitedRolloutError
from emss.services.surveillance import SurveillanceError
from emss.ui.production_release import ProductionReleasePanel
from emss.ui.uat_release import UatReleasePanel
from emss.utils.resources import bundled_resource


class ClinicalValidationPanel(QWidget):
    def __init__(self, container: ApplicationContainer, user: AuthenticatedUser) -> None:
        if user.username == 'mode.farmasi':
            raise ValueError('Mode Farmasi tidak berwenang membuka Validasi Klinis & UAT')
        super().__init__()
        self.container = container
        self.user = user
        self.setObjectName("clinicalValidationPanel")

        title = QLabel("Validasi Klinis, UAT & Gate Pilot")
        title.setStyleSheet("font-size: 16pt; font-weight: 700; color: #123B5D;")
        notice = QLabel(
            "Gunakan kasus sintetis/anonim. Import dan evaluasi di menu ini tidak "
            "mempublikasikan DDI dan tidak menulis ke Khanza. Aktivasi Advisory "
            "hanya membuka alert rekomendasi setelah seluruh gate lulus."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("background: #EAF2FF; border: 1px solid #93C5FD; padding: 10px; border-radius: 6px;")
        self.gate_label = QLabel()
        self.gate_label.setObjectName("pilotGateStatus")
        self.gate_label.setWordWrap(True)
        self.activation_label = QLabel()
        self.activation_label.setObjectName("advisoryActivationStatus")
        self.activation_label.setWordWrap(True)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)

        self.download_validation_button = QPushButton("Unduh Template Validasi Klinis")
        self.download_validation_button.setObjectName("downloadClinicalValidationTemplate")
        self.download_validation_button.clicked.connect(self._download_validation)
        self.download_uat_button = QPushButton("Unduh Template UAT")
        self.download_uat_button.setObjectName("downloadUatTemplate")
        self.download_uat_button.clicked.connect(self._download_uat)
        self.import_button = QPushButton("Import Hasil Validasi Klinis")
        self.import_button.setObjectName("importClinicalValidation")
        self.import_button.clicked.connect(self._import_validation)
        self.refresh_button = QPushButton("Evaluasi Ulang Gate")
        self.refresh_button.setObjectName("refreshPilotGate")
        self.refresh_button.clicked.connect(self.refresh)
        self.authorization_duration = QComboBox()
        self.authorization_duration.setObjectName("advisoryAuthorizationDuration")
        for label, hours in (
            ("4 jam", 4),
            ("8 jam", 8),
            ("12 jam", 12),
            ("24 jam", 24),
            ("3 hari", 72),
            ("7 hari", 168),
        ):
            self.authorization_duration.addItem(label, hours)
        self.authorization_duration.setCurrentIndex(3)
        self.activate_button = QPushButton("Ajukan Aktivasi IT")
        self.activate_button.setObjectName("activateAdvisoryPilot")
        self.activate_button.clicked.connect(self._activate_advisory)
        self.deactivate_button = QPushButton("Nonaktifkan Advisory Pilot")
        self.deactivate_button.setObjectName("deactivateAdvisoryPilot")
        self.deactivate_button.clicked.connect(self._deactivate_advisory)
        self.approve_activation_button = QPushButton("Setujui Aktivasi Klinis")
        self.approve_activation_button.setObjectName(
            "approveAdvisoryActivationClinical"
        )
        self.approve_activation_button.clicked.connect(
            self._approve_advisory_activation
        )
        self.request_handover_button = QPushButton("Ambil Alih Shift Klinis")
        self.request_handover_button.setObjectName("requestAdvisoryShiftHandover")
        self.request_handover_button.clicked.connect(self._request_shift_handover)
        self.attest_outgoing_button = QPushButton("Attestasi Outgoing Shift")
        self.attest_outgoing_button.setObjectName(
            "attestOutgoingAdvisoryShiftHandover"
        )
        self.attest_outgoing_button.clicked.connect(
            self._attest_outgoing_handover
        )
        self.close_shift_button = QPushButton("Tutup Shift Klinis")
        self.close_shift_button.setObjectName("closeAdvisoryClinicalShift")
        self.close_shift_button.clicked.connect(self._close_clinical_shift)
        self.approve_handover_button = QPushButton("Sahkan Handover IT")
        self.approve_handover_button.setObjectName("approveAdvisoryShiftHandover")
        self.approve_handover_button.clicked.connect(self._approve_shift_handover)
        self.emergency_stop_button = QPushButton("EMERGENCY STOP")
        self.emergency_stop_button.setObjectName("advisoryEmergencyStop")
        self.emergency_stop_button.setStyleSheet(
            "background: #B91C1C; color: white; font-weight: 700;"
        )
        self.emergency_stop_button.clicked.connect(self._emergency_stop)
        self.reset_emergency_button = QPushButton("Buka Emergency Stop")
        self.reset_emergency_button.setObjectName("resetAdvisoryEmergencyStop")
        self.reset_emergency_button.clicked.connect(self._reset_emergency_stop)
        actions = ActionLayout()
        for button in (
            self.download_validation_button,
            self.download_uat_button,
            self.import_button,
            self.refresh_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        pilot_controls = ActionLayout()
        pilot_controls.addWidget(QLabel("Masa aktivasi:"))
        pilot_controls.addWidget(self.authorization_duration)
        pilot_controls.addWidget(self.activate_button)
        pilot_controls.addWidget(self.approve_activation_button)
        pilot_controls.addWidget(self.deactivate_button)
        pilot_controls.addStretch()
        pilot_controls.addWidget(self.emergency_stop_button)
        pilot_controls.addWidget(self.reset_emergency_button)
        shift_controls = ActionLayout()
        shift_controls.addWidget(QLabel("Closeout & handover shift:"))
        shift_controls.addWidget(self.request_handover_button)
        shift_controls.addWidget(self.attest_outgoing_button)
        shift_controls.addWidget(self.approve_handover_button)
        shift_controls.addWidget(self.close_shift_button)
        shift_controls.addStretch()

        self.case_table = QTableWidget(0, 7)
        self.case_table.setHorizontalHeaderLabels(["Case ID", "Daftar obat", "Expected", "Actual", 'Tinjauan', "Match", "Reviewer"])
        self.case_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.case_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.case_table.horizontalHeader().setStretchLastSection(True)

        self.uat_table = QTableWidget(0, 7)
        self.uat_table.setHorizontalHeaderLabels(["Kode", "Kategori", "Pengujian", "Pemilik", "Status", "Tester", "ID"])
        self.uat_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.uat_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.uat_table.setColumnHidden(6, True)
        self.uat_table.horizontalHeader().setStretchLastSection(True)
        self.pass_button = QPushButton("Tandai PASS Terpilih")
        self.pass_button.clicked.connect(lambda: self._mark_uat("PASS"))
        self.fail_button = QPushButton("Tandai FAIL Terpilih")
        self.fail_button.clicked.connect(lambda: self._mark_uat("FAIL"))
        self.block_button = QPushButton("Tandai BLOCKED Terpilih")
        self.block_button.clicked.connect(lambda: self._mark_uat("BLOCKED"))
        self.approve_clinical_button = QPushButton("Persetujuan UAT Apoteker")
        self.approve_clinical_button.clicked.connect(lambda: self._approve("APOTEKER"))
        self.approve_it_button = QPushButton("Persetujuan UAT IT")
        self.approve_it_button.clicked.connect(lambda: self._approve("IT"))
        uat_actions = ActionLayout()
        for button in (self.pass_button, self.fail_button, self.block_button, self.approve_clinical_button, self.approve_it_button):
            uat_actions.addWidget(button)
        uat_actions.addStretch()
        uat_page = QWidget()
        uat_layout = QVBoxLayout(uat_page)
        uat_layout.setContentsMargins(0, 8, 0, 0)
        uat_layout.addLayout(uat_actions)
        uat_layout.addWidget(self.uat_table)
        case_page = QWidget()
        case_layout = QVBoxLayout(case_page)
        case_layout.setContentsMargins(0, 8, 0, 0)
        case_layout.addWidget(self.case_table)

        pilot_notice = QLabel(
            "Monitoring ini hanya memakai data agregat resep non-MOCK. Angka "
            "membantu evaluasi alert fatigue, tetapi tidak mengaktifkan mode advisory."
        )
        pilot_notice.setWordWrap(True)
        pilot_notice.setStyleSheet(
            "background: #ECFEFF; color: #155E75; border: 1px solid #67E8F9; "
            "padding: 9px; border-radius: 6px;"
        )
        self.pilot_period = QComboBox()
        self.pilot_period.setObjectName("pilotMonitoringPeriod")
        for label, days in (
            ("7 hari", 7),
            ("30 hari", 30),
            ("90 hari", 90),
            ("1 tahun", 365),
        ):
            self.pilot_period.addItem(label, days)
        self.pilot_period.setCurrentIndex(1)
        self.pilot_period.currentIndexChanged.connect(self._refresh_pilot)
        self.refresh_pilot_button = QPushButton("Muat Ulang Monitoring")
        self.refresh_pilot_button.setObjectName("refreshPilotMonitoring")
        self.refresh_pilot_button.clicked.connect(self._refresh_pilot)
        self.export_pilot_button = QPushButton("Ekspor CSV Agregat")
        self.export_pilot_button.setObjectName("exportPilotMonitoring")
        self.export_pilot_button.clicked.connect(self._export_pilot)
        pilot_actions = ActionLayout()
        pilot_actions.addWidget(QLabel("Periode:"))
        pilot_actions.addWidget(self.pilot_period)
        pilot_actions.addWidget(self.refresh_pilot_button)
        pilot_actions.addWidget(self.export_pilot_button)
        pilot_actions.addStretch()
        self.pilot_status = QLabel()
        self.pilot_status.setObjectName("pilotMonitoringStatus")
        self.pilot_status.setWordWrap(True)
        self.pilot_table = QTableWidget(0, 3)
        self.pilot_table.setObjectName("pilotMonitoringTable")
        self.pilot_table.setHorizontalHeaderLabels(
            ["Indikator", "Nilai", "Makna operasional"]
        )
        self.pilot_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.pilot_table.horizontalHeader().setStretchLastSection(True)
        pilot_page = QWidget()
        pilot_layout = QVBoxLayout(pilot_page)
        pilot_layout.setContentsMargins(0, 8, 0, 0)
        pilot_layout.addWidget(pilot_notice)
        pilot_layout.addLayout(pilot_actions)
        pilot_layout.addWidget(self.pilot_status)
        pilot_layout.addWidget(self.pilot_table)

        ledger_notice = QLabel(
            "Ledger sesi pilot bersifat append-only dan berantai SHA-256. "
            "Ringkasan closeout hanya memuat angka agregat tanpa identitas pasien."
        )
        ledger_notice.setWordWrap(True)
        ledger_notice.setStyleSheet(
            "background: #F0FDFA; color: #115E59; border: 1px solid #5EEAD4; "
            "padding: 9px; border-radius: 6px;"
        )
        self.ledger_status = QLabel()
        self.ledger_status.setObjectName("pilotSessionLedgerStatus")
        self.export_evidence_button = QPushButton("Ekspor Paket Bukti")
        self.export_evidence_button.setObjectName("exportPilotSessionEvidence")
        self.export_evidence_button.clicked.connect(
            self._export_pilot_evidence
        )
        self.verify_evidence_button = QPushButton("Verifikasi Paket Bukti")
        self.verify_evidence_button.setObjectName("verifyPilotEvidencePackage")
        self.verify_evidence_button.clicked.connect(
            self._verify_pilot_evidence
        )
        self.reset_ledger_quarantine_button = QPushButton(
            "Buka Karantina Ledger"
        )
        self.reset_ledger_quarantine_button.setObjectName(
            "resetPilotLedgerQuarantine"
        )
        self.reset_ledger_quarantine_button.clicked.connect(
            self._reset_ledger_quarantine
        )
        ledger_actions = ActionLayout()
        ledger_actions.addWidget(self.export_evidence_button)
        ledger_actions.addWidget(self.verify_evidence_button)
        ledger_actions.addWidget(self.reset_ledger_quarantine_button)
        ledger_actions.addStretch()
        self.ledger_table = QTableWidget(0, 6)
        self.ledger_table.setObjectName("pilotSessionLedgerTable")
        self.ledger_table.setHorizontalHeaderLabels(
            ["Urutan", "Waktu", "Event", "Aktivasi", "Aktor", "Hash"]
        )
        self.ledger_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.ledger_table.horizontalHeader().setStretchLastSection(True)
        verification_title = QLabel("Riwayat chain of custody paket bukti")
        verification_title.setStyleSheet("font-weight: 700; color: #123B5D;")
        self.evidence_verification_table = QTableWidget(0, 6)
        self.evidence_verification_table.setObjectName(
            "pilotEvidenceVerificationTable"
        )
        self.evidence_verification_table.setHorizontalHeaderLabels(
            ["Waktu", "Paket", "Hasil", "Versi", "Ledger", "Checksum"]
        )
        self.evidence_verification_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.evidence_verification_table.horizontalHeader().setStretchLastSection(
            True
        )
        ledger_page = QWidget()
        ledger_layout = QVBoxLayout(ledger_page)
        ledger_layout.setContentsMargins(0, 8, 0, 0)
        ledger_layout.addWidget(ledger_notice)
        ledger_layout.addLayout(ledger_actions)
        ledger_layout.addWidget(self.ledger_status)
        ledger_layout.addWidget(self.ledger_table)
        ledger_layout.addWidget(verification_title)
        ledger_layout.addWidget(self.evidence_verification_table)

        go_live_notice = QLabel(
            "Go-live acceptance terikat pada checksum release dan installer. "
            "GO memerlukan seluruh evidence PASS, attestation klinis dan teknis "
            "oleh pengguna berbeda, lalu keputusan independen Direktur/Super Admin."
        )
        go_live_notice.setWordWrap(True)
        go_live_notice.setStyleSheet(
            "background: #F5F3FF; color: #5B21B6; border: 1px solid #C4B5FD; "
            "padding: 9px; border-radius: 6px;"
        )
        self.go_live_session = QComboBox()
        self.go_live_session.setObjectName("goLiveAcceptanceSession")
        self.go_live_session.currentIndexChanged.connect(
            self._refresh_go_live_selection
        )
        self.create_go_live_button = QPushButton("Buat Sesi Acceptance")
        self.create_go_live_button.setObjectName("createGoLiveAcceptance")
        self.create_go_live_button.clicked.connect(self._create_go_live_session)
        self.attest_go_live_clinical_button = QPushButton("Attestasi Klinis")
        self.attest_go_live_clinical_button.setObjectName(
            "attestGoLiveClinical"
        )
        self.attest_go_live_clinical_button.clicked.connect(
            lambda: self._attest_go_live("CLINICAL")
        )
        self.attest_go_live_technical_button = QPushButton("Attestasi Teknis")
        self.attest_go_live_technical_button.setObjectName(
            "attestGoLiveTechnical"
        )
        self.attest_go_live_technical_button.clicked.connect(
            lambda: self._attest_go_live("TECHNICAL")
        )
        self.go_live_button = QPushButton("Keputusan GO")
        self.go_live_button.setObjectName("decideGoLiveGo")
        self.go_live_button.setStyleSheet(
            "background: #166534; color: white; font-weight: 700;"
        )
        self.go_live_button.clicked.connect(lambda: self._decide_go_live("GO"))
        self.no_go_button = QPushButton("Keputusan NO-GO")
        self.no_go_button.setObjectName("decideGoLiveNoGo")
        self.no_go_button.setStyleSheet(
            "background: #991B1B; color: white; font-weight: 700;"
        )
        self.no_go_button.clicked.connect(
            lambda: self._decide_go_live("NO_GO")
        )
        go_live_actions = ActionLayout()
        go_live_actions.addWidget(QLabel("Sesi:"))
        go_live_actions.addWidget(self.go_live_session)
        go_live_actions.addWidget(self.create_go_live_button)
        go_live_actions.addWidget(self.attest_go_live_clinical_button)
        go_live_actions.addWidget(self.attest_go_live_technical_button)
        go_live_actions.addWidget(self.go_live_button)
        go_live_actions.addWidget(self.no_go_button)
        go_live_actions.addStretch()
        self.go_live_status = QLabel()
        self.go_live_status.setObjectName("goLiveAcceptanceStatus")
        self.go_live_status.setWordWrap(True)
        self.go_live_blockers = QTextBrowser()
        self.go_live_blockers.setObjectName("goLiveAcceptanceBlockers")
        self.go_live_blockers.setMaximumHeight(90)
        self.go_live_table = QTableWidget(0, 8)
        self.go_live_table.setObjectName("goLiveAcceptanceTable")
        self.go_live_table.setHorizontalHeaderLabels(
            [
                "Kode",
                "Pemilik",
                "Kategori",
                "Pengujian",
                "Status",
                "Bukti",
                "Checksum",
                "ID",
            ]
        )
        self.go_live_table.setColumnHidden(7, True)
        self.go_live_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.go_live_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.go_live_table.horizontalHeader().setStretchLastSection(True)
        self.pass_go_live_item_button = QPushButton("Tandai PASS + Bukti")
        self.pass_go_live_item_button.setObjectName("passGoLiveEvidence")
        self.pass_go_live_item_button.clicked.connect(
            lambda: self._update_go_live_item("PASS")
        )
        self.fail_go_live_item_button = QPushButton("Tandai FAIL")
        self.fail_go_live_item_button.setObjectName("failGoLiveEvidence")
        self.fail_go_live_item_button.clicked.connect(
            lambda: self._update_go_live_item("FAIL")
        )
        self.block_go_live_item_button = QPushButton("Tandai BLOCKED")
        self.block_go_live_item_button.setObjectName("blockGoLiveEvidence")
        self.block_go_live_item_button.clicked.connect(
            lambda: self._update_go_live_item("BLOCKED")
        )
        go_live_item_actions = ActionLayout()
        go_live_item_actions.addWidget(self.pass_go_live_item_button)
        go_live_item_actions.addWidget(self.fail_go_live_item_button)
        go_live_item_actions.addWidget(self.block_go_live_item_button)
        go_live_item_actions.addStretch()
        self.go_live_ledger_table = QTableWidget(0, 5)
        self.go_live_ledger_table.setObjectName("goLiveDecisionLedgerTable")
        self.go_live_ledger_table.setHorizontalHeaderLabels(
            ["Urutan", "Waktu", "Event", "Sesi", "Hash"]
        )
        self.go_live_ledger_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.go_live_ledger_table.horizontalHeader().setStretchLastSection(True)
        go_live_page = QWidget()
        go_live_layout = QVBoxLayout(go_live_page)
        go_live_layout.setContentsMargins(0, 8, 0, 0)
        go_live_layout.addWidget(go_live_notice)
        go_live_layout.addLayout(go_live_actions)
        go_live_layout.addWidget(self.go_live_status)
        go_live_layout.addWidget(self.go_live_blockers)
        go_live_layout.addLayout(go_live_item_actions)
        go_live_layout.addWidget(self.go_live_table)
        go_live_layout.addWidget(QLabel("Immutable decision ledger"))
        go_live_layout.addWidget(self.go_live_ledger_table)

        rollout_notice = QLabel(
            "Limited production hanya dapat berjalan dari acceptance GO yang masih "
            "valid. Satu wave aktif pada satu waktu; expiry, ledger invalid, atau "
            "ambang insiden membuat operasi fail-closed. Detail insiden disimpan "
            "sebagai hash, tanpa identitas pasien."
        )
        rollout_notice.setWordWrap(True)
        rollout_notice.setStyleSheet(
            "background: #EFF6FF; color: #1E3A8A; border: 1px solid #93C5FD; "
            "padding: 9px; border-radius: 6px;"
        )
        self.rollout_session = QComboBox()
        self.rollout_session.setObjectName("limitedRolloutSession")
        self.rollout_session.currentIndexChanged.connect(
            self._render_rollout_selection
        )
        self.create_rollout_button = QPushButton("Buat Rollout")
        self.create_rollout_button.setObjectName("createLimitedRollout")
        self.create_rollout_button.clicked.connect(self._create_rollout)
        self.add_rollout_wave_button = QPushButton("Tambah Wave")
        self.add_rollout_wave_button.setObjectName("addLimitedRolloutWave")
        self.add_rollout_wave_button.clicked.connect(self._add_rollout_wave)
        self.start_rollout_button = QPushButton("Mulai Rollout")
        self.start_rollout_button.setObjectName("startLimitedRollout")
        self.start_rollout_button.clicked.connect(
            lambda: self._rollout_action("START")
        )
        self.activate_rollout_wave_button = QPushButton("Aktifkan Wave")
        self.activate_rollout_wave_button.setObjectName("activateLimitedRolloutWave")
        self.activate_rollout_wave_button.clicked.connect(
            lambda: self._rollout_action("ACTIVATE_WAVE")
        )
        self.complete_rollout_wave_button = QPushButton("Selesaikan Wave")
        self.complete_rollout_wave_button.setObjectName("completeLimitedRolloutWave")
        self.complete_rollout_wave_button.clicked.connect(
            lambda: self._rollout_action("COMPLETE_WAVE")
        )
        self.pause_rollout_button = QPushButton("Pause")
        self.pause_rollout_button.setObjectName("pauseLimitedRollout")
        self.pause_rollout_button.clicked.connect(
            lambda: self._rollout_action("PAUSE")
        )
        self.halt_rollout_button = QPushButton("EMERGENCY HALT")
        self.halt_rollout_button.setObjectName("haltLimitedRollout")
        self.halt_rollout_button.setStyleSheet(
            "background: #B91C1C; color: white; font-weight: 700;"
        )
        self.halt_rollout_button.clicked.connect(
            lambda: self._rollout_action("HALT")
        )
        self.resume_rollout_button = QPushButton("Resume")
        self.resume_rollout_button.setObjectName("resumeLimitedRollout")
        self.resume_rollout_button.clicked.connect(
            lambda: self._rollout_action("RESUME")
        )
        rollout_actions = ActionLayout()
        rollout_actions.addWidget(QLabel("Sesi:"))
        rollout_actions.addWidget(self.rollout_session)
        for button in (
            self.create_rollout_button,
            self.add_rollout_wave_button,
            self.start_rollout_button,
            self.activate_rollout_wave_button,
            self.complete_rollout_wave_button,
            self.pause_rollout_button,
            self.resume_rollout_button,
            self.halt_rollout_button,
        ):
            rollout_actions.addWidget(button)
        rollout_actions.addStretch()
        self.rollout_status = QLabel()
        self.rollout_status.setObjectName("limitedRolloutStatus")
        self.rollout_status.setWordWrap(True)
        self.rollout_blockers = QTextBrowser()
        self.rollout_blockers.setObjectName("limitedRolloutBlockers")
        self.rollout_blockers.setMaximumHeight(80)
        self.rollout_wave_table = QTableWidget(0, 6)
        self.rollout_wave_table.setObjectName("limitedRolloutWaveTable")
        self.rollout_wave_table.setHorizontalHeaderLabels(
            ["Wave", "Cohort", "Workstation", "Status", "Aktivasi", "ID"]
        )
        self.rollout_wave_table.setColumnHidden(5, True)
        self.rollout_wave_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.rollout_wave_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.rollout_wave_table.horizontalHeader().setStretchLastSection(True)
        self.record_rollout_incident_button = QPushButton("Catat Insiden")
        self.record_rollout_incident_button.setObjectName("recordLimitedRolloutIncident")
        self.record_rollout_incident_button.clicked.connect(
            self._record_rollout_incident
        )
        self.attest_rollout_clinical_button = QPushButton("Attestasi Klinis")
        self.attest_rollout_clinical_button.setObjectName("attestRolloutClinical")
        self.attest_rollout_clinical_button.clicked.connect(
            lambda: self._attest_rollout("CLINICAL")
        )
        self.attest_rollout_technical_button = QPushButton("Attestasi Teknis")
        self.attest_rollout_technical_button.setObjectName("attestRolloutTechnical")
        self.attest_rollout_technical_button.clicked.connect(
            lambda: self._attest_rollout("TECHNICAL")
        )
        self.complete_rollout_button = QPushButton("Keputusan COMPLETE")
        self.complete_rollout_button.setObjectName("decideRolloutComplete")
        self.complete_rollout_button.clicked.connect(
            lambda: self._decide_rollout("COMPLETE")
        )
        self.rollback_rollout_button = QPushButton("Keputusan ROLLBACK")
        self.rollback_rollout_button.setObjectName("decideRolloutRollback")
        self.rollback_rollout_button.setStyleSheet(
            "background: #991B1B; color: white; font-weight: 700;"
        )
        self.rollback_rollout_button.clicked.connect(
            lambda: self._decide_rollout("ROLLBACK")
        )
        rollout_closeout_actions = ActionLayout()
        for button in (
            self.record_rollout_incident_button,
            self.attest_rollout_clinical_button,
            self.attest_rollout_technical_button,
            self.complete_rollout_button,
            self.rollback_rollout_button,
        ):
            rollout_closeout_actions.addWidget(button)
        rollout_closeout_actions.addStretch()
        self.rollout_ledger_table = QTableWidget(0, 6)
        self.rollout_ledger_table.setObjectName("limitedRolloutLedgerTable")
        self.rollout_ledger_table.setHorizontalHeaderLabels(
            ["Urutan", "Waktu", "Event", 'Tingkat keparahan', "Wave", "Hash"]
        )
        self.rollout_ledger_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.rollout_ledger_table.horizontalHeader().setStretchLastSection(True)
        rollout_page = QWidget()
        rollout_layout = QVBoxLayout(rollout_page)
        rollout_layout.setContentsMargins(0, 8, 0, 0)
        rollout_layout.addWidget(rollout_notice)
        rollout_layout.addLayout(rollout_actions)
        rollout_layout.addWidget(self.rollout_status)
        rollout_layout.addWidget(self.rollout_blockers)
        rollout_layout.addLayout(rollout_closeout_actions)
        rollout_layout.addWidget(self.rollout_wave_table)
        rollout_layout.addWidget(QLabel("Immutable operational ledger"))
        rollout_layout.addWidget(self.rollout_ledger_table)

        surveillance_notice = QLabel(
            "Early-life surveillance hanya menerima limited rollout COMPLETED. "
            "Snapshot berisi metrik agregat non-MOCK; promotion membutuhkan data "
            "fresh, isu tertutup, attestation klinis dan teknis berbeda, lalu "
            "keputusan independen. PROMOTE tidak mengubah konfigurasi otomatis."
        )
        surveillance_notice.setWordWrap(True)
        surveillance_notice.setStyleSheet(
            "background: #F0FDFA; color: #115E59; border: 1px solid #5EEAD4; "
            "padding: 9px; border-radius: 6px;"
        )
        self.surveillance_session = QComboBox()
        self.surveillance_session.setObjectName("earlyLifeSurveillanceSession")
        self.surveillance_session.currentIndexChanged.connect(
            self._render_surveillance_selection
        )
        self.create_surveillance_button = QPushButton("Buat Surveillance")
        self.create_surveillance_button.setObjectName("createEarlyLifeSurveillance")
        self.create_surveillance_button.clicked.connect(self._create_surveillance)
        self.capture_surveillance_button = QPushButton("Capture Snapshot")
        self.capture_surveillance_button.setObjectName("captureSurveillanceSnapshot")
        self.capture_surveillance_button.clicked.connect(self._capture_surveillance)
        self.record_surveillance_issue_button = QPushButton("Catat Isu")
        self.record_surveillance_issue_button.setObjectName("recordSurveillanceIssue")
        self.record_surveillance_issue_button.clicked.connect(
            self._record_surveillance_issue
        )
        self.close_surveillance_issue_button = QPushButton("Tutup Isu")
        self.close_surveillance_issue_button.setObjectName("closeSurveillanceIssue")
        self.close_surveillance_issue_button.clicked.connect(
            self._close_surveillance_issue
        )
        self.attest_surveillance_clinical_button = QPushButton("Attestasi Klinis")
        self.attest_surveillance_clinical_button.setObjectName("attestSurveillanceClinical")
        self.attest_surveillance_clinical_button.clicked.connect(
            lambda: self._attest_surveillance("CLINICAL")
        )
        self.attest_surveillance_technical_button = QPushButton("Attestasi Teknis")
        self.attest_surveillance_technical_button.setObjectName("attestSurveillanceTechnical")
        self.attest_surveillance_technical_button.clicked.connect(
            lambda: self._attest_surveillance("TECHNICAL")
        )
        self.promote_surveillance_button = QPushButton("Keputusan PROMOTE")
        self.promote_surveillance_button.setObjectName("decideSurveillancePromote")
        self.promote_surveillance_button.clicked.connect(
            lambda: self._decide_surveillance("PROMOTE")
        )
        self.rollback_surveillance_button = QPushButton("Keputusan ROLLBACK")
        self.rollback_surveillance_button.setObjectName("decideSurveillanceRollback")
        self.rollback_surveillance_button.setStyleSheet(
            "background: #991B1B; color: white; font-weight: 700;"
        )
        self.rollback_surveillance_button.clicked.connect(
            lambda: self._decide_surveillance("ROLLBACK")
        )
        surveillance_actions = ActionLayout()
        surveillance_actions.addWidget(QLabel("Sesi:"))
        surveillance_actions.addWidget(self.surveillance_session)
        for button in (
            self.create_surveillance_button,
            self.capture_surveillance_button,
            self.record_surveillance_issue_button,
            self.close_surveillance_issue_button,
            self.attest_surveillance_clinical_button,
            self.attest_surveillance_technical_button,
            self.promote_surveillance_button,
            self.rollback_surveillance_button,
        ):
            surveillance_actions.addWidget(button)
        surveillance_actions.addStretch()
        self.surveillance_status = QLabel()
        self.surveillance_status.setObjectName("earlyLifeSurveillanceStatus")
        self.surveillance_status.setWordWrap(True)
        self.surveillance_blockers = QTextBrowser()
        self.surveillance_blockers.setObjectName("earlyLifeSurveillanceBlockers")
        self.surveillance_blockers.setMaximumHeight(80)
        self.surveillance_snapshot_table = QTableWidget(0, 8)
        self.surveillance_snapshot_table.setObjectName("surveillanceSnapshotTable")
        self.surveillance_snapshot_table.setHorizontalHeaderLabels(
            ["Waktu", "Resep", "CRITICAL", "CRIT unack", "Intervensi", "Polling", "Health", "Audit"]
        )
        self.surveillance_snapshot_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.surveillance_snapshot_table.horizontalHeader().setStretchLastSection(True)
        self.surveillance_issue_table = QTableWidget(0, 6)
        self.surveillance_issue_table.setObjectName("surveillanceIssueTable")
        self.surveillance_issue_table.setHorizontalHeaderLabels(
            ["No", 'Tingkat keparahan', "Status", "Summary hash", "Resolution hash", "ID"]
        )
        self.surveillance_issue_table.setColumnHidden(5, True)
        self.surveillance_issue_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.surveillance_issue_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.surveillance_issue_table.horizontalHeader().setStretchLastSection(True)
        self.surveillance_ledger_table = QTableWidget(0, 5)
        self.surveillance_ledger_table.setObjectName("surveillanceLedgerTable")
        self.surveillance_ledger_table.setHorizontalHeaderLabels(
            ["Urutan", "Waktu", "Event", "Aktor", "Hash"]
        )
        self.surveillance_ledger_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.surveillance_ledger_table.horizontalHeader().setStretchLastSection(True)
        surveillance_page = QWidget()
        surveillance_layout = QVBoxLayout(surveillance_page)
        surveillance_layout.setContentsMargins(0, 8, 0, 0)
        surveillance_layout.addWidget(surveillance_notice)
        surveillance_layout.addLayout(surveillance_actions)
        surveillance_layout.addWidget(self.surveillance_status)
        surveillance_layout.addWidget(self.surveillance_blockers)
        surveillance_layout.addWidget(QLabel("Snapshot agregat immutable"))
        surveillance_layout.addWidget(self.surveillance_snapshot_table)
        surveillance_layout.addWidget(QLabel("Isu dan remediasi"))
        surveillance_layout.addWidget(self.surveillance_issue_table)
        surveillance_layout.addWidget(QLabel("Immutable surveillance ledger"))
        surveillance_layout.addWidget(self.surveillance_ledger_table)
        self.production_release_panel = ProductionReleasePanel(container, user)
        self.uat_release_panel = UatReleasePanel(container, user)
        inner_tabs = QTabWidget()
        inner_tabs.addTab(case_page, "Kasus Validasi")
        inner_tabs.addTab(uat_page, "Checklist UAT")
        inner_tabs.addTab(pilot_page, "Monitoring Pilot")
        inner_tabs.addTab(ledger_page, "Ledger Sesi Pilot")
        inner_tabs.addTab(go_live_page, "Go-Live Readiness")
        inner_tabs.addTab(rollout_page, "Limited Rollout")
        inner_tabs.addTab(surveillance_page, "Early-Life Surveillance")
        inner_tabs.addTab(self.production_release_panel, "Production Release")
        inner_tabs.addTab(self.uat_release_panel, "UAT Release Candidate")

        blocker_title = QLabel("Gate yang belum terpenuhi")
        blocker_title.setStyleSheet("font-weight: 700; color: #123B5D;")
        self.blockers = QTextBrowser()
        self.blockers.setMaximumHeight(120)
        self.feedback = QLabel()
        self.feedback.setObjectName("validationFeedback")
        self.feedback.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(notice)
        layout.addWidget(self.gate_label)
        layout.addWidget(self.activation_label)
        layout.addWidget(self.stats_label)
        layout.addLayout(actions)
        layout.addLayout(pilot_controls)
        layout.addLayout(shift_controls)
        layout.addWidget(inner_tabs, 1)
        layout.addWidget(blocker_title)
        layout.addWidget(self.blockers)
        layout.addWidget(self.feedback)
        self.refresh()

    def _selected_go_live_session_id(self) -> str | None:
        value = self.go_live_session.currentData()
        return str(value) if value else None

    @Slot()
    def _refresh_go_live_selection(self) -> None:
        self._render_go_live_selection()

    def _refresh_go_live(self) -> None:
        selected = self._selected_go_live_session_id()
        try:
            sessions = self.container.go_live.sessions(self.user.id)
            ledger = self.container.go_live.ledger(self.user.id)
        except GoLiveError as exc:
            self.go_live_status.setText(f"Go-live evidence tidak tersedia: {exc}")
            self.go_live_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            return
        self.go_live_session.blockSignals(True)
        self.go_live_session.clear()
        for record in sessions:
            self.go_live_session.addItem(
                f"{record.application_version} · {record.environment_label} · {record.status}",
                record.id,
            )
        if selected:
            index = self.go_live_session.findData(selected)
            if index >= 0:
                self.go_live_session.setCurrentIndex(index)
        self.go_live_session.blockSignals(False)
        self.go_live_ledger_table.setRowCount(len(ledger))
        for row_index, entry in enumerate(ledger):
            values = (
                entry.sequence,
                entry.occurred_at.isoformat(timespec="seconds"),
                entry.event_type,
                entry.session_id,
                entry.entry_hash,
            )
            for column, value in enumerate(values):
                self.go_live_ledger_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._render_go_live_selection()

    def _render_go_live_selection(self) -> None:
        session_id = self._selected_go_live_session_id()
        if session_id is None:
            self.go_live_status.setText(
                "Belum ada sesi go-live acceptance untuk release aktif."
            )
            self.go_live_status.setStyleSheet(
                "background: #FFF7D6; color: #854D0E; padding: 8px;"
            )
            self.go_live_blockers.setPlainText(
                "Buat sesi dari release-qualification.json dan installer final."
            )
            self.go_live_table.setRowCount(0)
            self._set_go_live_controls(None)
            return
        try:
            readiness = self.container.go_live.evaluate(session_id, self.user.id)
            items = self.container.go_live.items(session_id, self.user.id)
        except GoLiveError as exc:
            self.go_live_status.setText(f"Sesi tidak dapat dievaluasi: {exc}")
            self.go_live_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            self._set_go_live_controls(None)
            return
        record = readiness.session
        if record.status == "GO":
            headline = "KEPUTUSAN GO TERCATAT — bukti final immutable"
            colors = "background: #DCFCE7; color: #166534;"
        elif record.status == "NO_GO":
            headline = "KEPUTUSAN NO-GO TERCATAT — bukti final immutable"
            colors = "background: #FEE2E2; color: #991B1B;"
        elif readiness.ready_for_go_decision:
            headline = "READY FOR GO/NO-GO DECISION"
            colors = "background: #DBEAFE; color: #1E3A8A;"
        else:
            headline = "GO-LIVE BELUM SIAP"
            colors = "background: #FFF7D6; color: #854D0E;"
        self.go_live_status.setText(
            f"{headline} · evidence {readiness.items_passed}/{readiness.items_total} PASS · "
            f"expiry {record.expires_at.isoformat(timespec='minutes')} · "
            f"ledger {'VALID' if readiness.ledger_valid else 'INVALID'}"
        )
        self.go_live_status.setStyleSheet(
            colors + " font-weight: 700; padding: 8px; border-radius: 5px;"
        )
        self.go_live_blockers.setPlainText(
            "\n".join(f"• {item}" for item in readiness.blockers)
            or "Tidak ada blocker."
        )
        self.go_live_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            values = (
                item.item_code,
                item.owner_type,
                item.category,
                item.description,
                item.status,
                item.evidence_filename or "-",
                item.evidence_checksum_sha256 or "-",
                item.id,
            )
            for column, value in enumerate(values):
                self.go_live_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._set_go_live_controls(readiness)

    def _set_go_live_controls(self, readiness) -> None:
        roles = self.user.roles
        can_technical = bool(roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        can_clinical = bool(
            roles.intersection(
                {"CLINICAL_REVIEWER", "APOTEKER", "KFT", "KEPALA_INSTALASI"}
            )
        )
        can_decide = bool(roles.intersection({"SUPER_ADMIN", "DIREKTUR"}))
        open_session = bool(
            readiness is not None and readiness.session.status == "IN_PROGRESS"
        )
        self.create_go_live_button.setVisible(can_technical)
        self.attest_go_live_clinical_button.setVisible(can_clinical)
        self.attest_go_live_technical_button.setVisible(can_technical)
        self.go_live_button.setVisible(can_decide)
        self.no_go_button.setVisible(can_decide)
        self.attest_go_live_clinical_button.setEnabled(open_session and can_clinical)
        self.attest_go_live_technical_button.setEnabled(open_session and can_technical)
        self.go_live_button.setEnabled(
            open_session
            and can_decide
            and bool(readiness and readiness.ready_for_go_decision)
        )
        self.no_go_button.setEnabled(open_session and can_decide)
        self.pass_go_live_item_button.setEnabled(
            open_session and (can_technical or can_clinical)
        )
        self.fail_go_live_item_button.setEnabled(
            open_session and (can_technical or can_clinical)
        )
        self.block_go_live_item_button.setEnabled(
            open_session and (can_technical or can_clinical)
        )

    def _create_go_live_session(self) -> None:
        report, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih release qualification final",
            str(self.container.settings.export_dir),
            "JSON (*.json)",
        )
        if not report:
            return
        installer, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih installer yang terikat manifest",
            str(self.container.settings.export_dir),
            "Executable (*.exe)",
        )
        if not installer:
            return
        label, accepted = QInputDialog.getText(
            self,
            "Environment Acceptance",
            "Label staging/clean-host (wajib 3-120 karakter):",
        )
        if not accepted:
            return
        days, accepted = QInputDialog.getInt(
            self,
            "Masa Acceptance",
            "Berlaku berapa hari (1-30):",
            7,
            1,
            30,
        )
        if not accepted:
            return
        try:
            record = self.container.go_live.create_session(
                report, installer, label, self.user.id, days
            )
            self._refresh_go_live()
            index = self.go_live_session.findData(record.id)
            if index >= 0:
                self.go_live_session.setCurrentIndex(index)
            self.feedback.setText(
                "Sesi go-live acceptance dibuat dan terikat checksum release."
            )
        except GoLiveError as exc:
            QMessageBox.warning(self, "Sesi acceptance gagal", str(exc))

    def _selected_go_live_item_id(self) -> str | None:
        row = self.go_live_table.currentRow()
        if row < 0:
            return None
        item = self.go_live_table.item(row, 7)
        return item.text() if item else None

    def _update_go_live_item(self, status: str) -> None:
        item_id = self._selected_go_live_item_id()
        if item_id is None:
            QMessageBox.information(
                self, "Pilih evidence", "Pilih satu baris checklist terlebih dahulu."
            )
            return
        evidence = None
        if status == "PASS":
            evidence, _ = QFileDialog.getOpenFileName(
                self,
                "Pilih file bukti PASS",
                str(self.container.settings.export_dir),
                "Semua file (*.*)",
            )
            if not evidence:
                return
        prompt = (
            "Catatan evidence (opsional, maksimal 300 karakter):"
            if status == "PASS"
            else "Alasan wajib (minimal 10, maksimal 300 karakter):"
        )
        notes, accepted = QInputDialog.getText(
            self, f"Evidence {status}", prompt
        )
        if not accepted:
            return
        try:
            self.container.go_live.update_item(
                item_id,
                status,
                self.user.id,
                evidence_path=evidence,
                notes=notes,
            )
            self._refresh_go_live()
        except GoLiveError as exc:
            QMessageBox.warning(self, "Evidence tidak tersimpan", str(exc))

    def _attest_go_live(self, attestation_type: str) -> None:
        session_id = self._selected_go_live_session_id()
        if session_id is None:
            return
        confirmed = QMessageBox.question(
            self,
            f"Attestation {attestation_type}",
            "Saya menyatakan seluruh evidence milik fungsi ini telah ditinjau "
            "dan sesuai dengan release/checksum yang ditampilkan. Lanjutkan?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.go_live.attest(
                session_id, attestation_type, self.user.id
            )
            self._refresh_go_live()
        except GoLiveError as exc:
            QMessageBox.warning(self, "Attestation ditolak", str(exc))

    def _decide_go_live(self, decision: str) -> None:
        session_id = self._selected_go_live_session_id()
        if session_id is None:
            return
        reason, accepted = QInputDialog.getText(
            self,
            f"Keputusan {decision}",
            "Alasan keputusan wajib 10-300 karakter:",
        )
        if not accepted:
            return
        confirmed = QMessageBox.question(
            self,
            "Konfirmasi keputusan final",
            f"Keputusan {decision} bersifat immutable dan tidak mengubah mode "
            "aplikasi secara otomatis. Catat keputusan?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.go_live.decide(
                session_id, decision, reason, self.user.id
            )
            self._refresh_go_live()
        except GoLiveError as exc:
            QMessageBox.warning(self, "Keputusan ditolak", str(exc))

    def _selected_rollout_id(self) -> str | None:
        value = self.rollout_session.currentData()
        return str(value) if value else None

    def _selected_rollout_wave_id(self) -> str | None:
        row = self.rollout_wave_table.currentRow()
        if row < 0:
            return None
        item = self.rollout_wave_table.item(row, 5)
        return item.text() if item else None

    @Slot()
    def _refresh_rollout(self) -> None:
        selected = self._selected_rollout_id()
        try:
            sessions = self.container.limited_rollout.sessions(self.user.id)
            ledger = self.container.limited_rollout.ledger(self.user.id)
        except LimitedRolloutError as exc:
            self.rollout_status.setText(f"Rollout dikarantina/tidak tersedia: {exc}")
            self.rollout_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            return
        self.rollout_session.blockSignals(True)
        self.rollout_session.clear()
        for record in sessions:
            self.rollout_session.addItem(
                f"{record.scope_label} · {record.status} · maks {record.max_workstations}",
                record.id,
            )
        if selected:
            index = self.rollout_session.findData(selected)
            if index >= 0:
                self.rollout_session.setCurrentIndex(index)
        self.rollout_session.blockSignals(False)
        self.rollout_ledger_table.setRowCount(len(ledger))
        for row_index, entry in enumerate(ledger):
            values = (
                entry.sequence,
                entry.occurred_at.isoformat(timespec="seconds"),
                entry.event_type,
                entry.severity,
                entry.wave_id or "-",
                entry.entry_hash,
            )
            for column, value in enumerate(values):
                self.rollout_ledger_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._render_rollout_selection()

    @Slot()
    def _render_rollout_selection(self) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            self.rollout_status.setText(
                "Belum ada limited rollout. Pilih acceptance GO lalu buat scope terbatas."
            )
            self.rollout_status.setStyleSheet(
                "background: #FFF7D6; color: #854D0E; padding: 8px;"
            )
            self.rollout_blockers.setPlainText("Acceptance GO yang valid wajib tersedia.")
            self.rollout_wave_table.setRowCount(0)
            self._set_rollout_controls(None)
            return
        try:
            readiness = self.container.limited_rollout.evaluate(
                rollout_id, self.user.id
            )
            waves = self.container.limited_rollout.waves(rollout_id, self.user.id)
        except LimitedRolloutError as exc:
            self.rollout_status.setText(f"Rollout tidak dapat dievaluasi: {exc}")
            self.rollout_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            self._set_rollout_controls(None)
            return
        record = readiness.session
        if record.status == "COMPLETED":
            headline = "LIMITED ROLLOUT COMPLETED — keputusan immutable"
            colors = "background: #DCFCE7; color: #166534;"
        elif record.status == "ROLLED_BACK":
            headline = "ROLLOUT ROLLED BACK — keputusan immutable"
            colors = "background: #FEE2E2; color: #991B1B;"
        elif record.status == "HALTED":
            headline = "ROLLOUT HALTED — operasi fail-closed"
            colors = "background: #7F1D1D; color: white;"
        elif readiness.operational_allowed:
            headline = "WAVE AKTIF — limited production diizinkan"
            colors = "background: #DBEAFE; color: #1E3A8A;"
        else:
            headline = f"ROLLOUT {record.status} — tidak ada wave operasional"
            colors = "background: #FFF7D6; color: #854D0E;"
        self.rollout_status.setText(
            f"{headline} · wave {readiness.waves_completed}/{readiness.waves_total} selesai · "
            f"insiden {readiness.incidents_total} (CRITICAL {readiness.critical_incidents}) · "
            f"expiry {record.expires_at.isoformat(timespec='minutes')} · "
            f"ledger {'VALID' if readiness.ledger_valid else 'INVALID'}"
        )
        self.rollout_status.setStyleSheet(
            colors + " font-weight: 700; padding: 8px; border-radius: 5px;"
        )
        self.rollout_blockers.setPlainText(
            "\n".join(f"• {item}" for item in readiness.blockers)
            or "Tidak ada blocker closeout."
        )
        self.rollout_wave_table.setRowCount(len(waves))
        for row_index, wave in enumerate(waves):
            values = (
                wave.wave_number,
                wave.cohort_label,
                wave.planned_workstations,
                wave.status,
                wave.activated_at.isoformat(timespec="minutes")
                if wave.activated_at
                else "-",
                wave.id,
            )
            for column, value in enumerate(values):
                self.rollout_wave_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._set_rollout_controls(readiness)

    def _set_rollout_controls(self, readiness) -> None:
        roles = self.user.roles
        can_technical = bool(roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        can_clinical = bool(
            roles.intersection(
                {"CLINICAL_REVIEWER", "APOTEKER", "KFT", "KEPALA_INSTALASI"}
            )
        )
        can_decide = bool(roles.intersection({"SUPER_ADMIN", "DIREKTUR"}))
        status = readiness.session.status if readiness is not None else ""
        non_final = status not in {"COMPLETED", "ROLLED_BACK"}
        self.create_rollout_button.setVisible(can_technical)
        self.add_rollout_wave_button.setVisible(can_technical)
        self.start_rollout_button.setVisible(can_technical)
        self.activate_rollout_wave_button.setVisible(can_technical)
        self.complete_rollout_wave_button.setVisible(can_technical)
        self.resume_rollout_button.setVisible(can_technical)
        self.pause_rollout_button.setVisible(can_technical or can_clinical or can_decide)
        self.halt_rollout_button.setVisible(can_technical or can_clinical or can_decide)
        self.record_rollout_incident_button.setVisible(
            can_technical or can_clinical or can_decide
        )
        self.attest_rollout_clinical_button.setVisible(can_clinical)
        self.attest_rollout_technical_button.setVisible(can_technical)
        self.complete_rollout_button.setVisible(can_decide)
        self.rollback_rollout_button.setVisible(can_decide)
        self.add_rollout_wave_button.setEnabled(can_technical and status == "PLANNED")
        self.start_rollout_button.setEnabled(can_technical and status == "PLANNED")
        self.activate_rollout_wave_button.setEnabled(can_technical and status == "ACTIVE")
        self.complete_rollout_wave_button.setEnabled(can_technical and status == "ACTIVE")
        self.resume_rollout_button.setEnabled(can_technical and status in {"PAUSED", "HALTED"})
        self.pause_rollout_button.setEnabled(non_final and status in {"ACTIVE", "PAUSED", "HALTED"})
        self.halt_rollout_button.setEnabled(non_final and status in {"ACTIVE", "PAUSED", "HALTED"})
        self.record_rollout_incident_button.setEnabled(
            non_final and status in {"ACTIVE", "PAUSED", "HALTED"}
        )
        self.attest_rollout_clinical_button.setEnabled(
            can_clinical and status in {"ACTIVE", "PAUSED"}
        )
        self.attest_rollout_technical_button.setEnabled(
            can_technical and status in {"ACTIVE", "PAUSED"}
        )
        self.complete_rollout_button.setEnabled(
            can_decide and bool(readiness and readiness.ready_for_completion)
        )
        self.rollback_rollout_button.setEnabled(can_decide and non_final and bool(status))

    def _create_rollout(self) -> None:
        acceptance_id = self._selected_go_live_session_id()
        if acceptance_id is None:
            QMessageBox.information(
                self, "Pilih acceptance GO", "Pilih sesi acceptance GO terlebih dahulu."
            )
            return
        label, accepted = QInputDialog.getText(
            self,
            "Scope Limited Rollout",
            "Unit/cohort pilot (wajib 3-120 karakter):",
        )
        if not accepted:
            return
        maximum, accepted = QInputDialog.getInt(
            self, "Batas Rollout", "Maksimum workstation (1-500):", 5, 1, 500
        )
        if not accepted:
            return
        days, accepted = QInputDialog.getInt(
            self, "Masa Rollout", "Berlaku berapa hari (1-30):", 7, 1, 30
        )
        if not accepted:
            return
        try:
            record = self.container.limited_rollout.create_session(
                acceptance_id,
                label,
                maximum,
                self.user.id,
                validity_days=days,
            )
            self._refresh_rollout()
            index = self.rollout_session.findData(record.id)
            if index >= 0:
                self.rollout_session.setCurrentIndex(index)
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Rollout tidak dapat dibuat", str(exc))

    def _add_rollout_wave(self) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            return
        label, accepted = QInputDialog.getText(
            self, "Cohort Wave", "Label cohort/workstation group:"
        )
        if not accepted:
            return
        count, accepted = QInputDialog.getInt(
            self, "Workstation Wave", "Jumlah workstation:", 1, 1, 500
        )
        if not accepted:
            return
        try:
            self.container.limited_rollout.add_wave(
                rollout_id, label, count, self.user.id
            )
            self._refresh_rollout()
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Wave tidak dapat ditambah", str(exc))

    def _rollout_action(self, action: str) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            return
        try:
            if action == "START":
                self.container.limited_rollout.start(rollout_id, self.user.id)
            elif action in {"ACTIVATE_WAVE", "COMPLETE_WAVE"}:
                wave_id = self._selected_rollout_wave_id()
                if wave_id is None:
                    raise LimitedRolloutError("Pilih satu wave terlebih dahulu")
                if action == "ACTIVATE_WAVE":
                    self.container.limited_rollout.activate_wave(wave_id, self.user.id)
                else:
                    self.container.limited_rollout.complete_wave(wave_id, self.user.id)
            else:
                reason, accepted = QInputDialog.getText(
                    self,
                    action,
                    "Alasan/tindakan mitigasi wajib 10-300 karakter:",
                )
                if not accepted:
                    return
                if action == "PAUSE":
                    self.container.limited_rollout.pause(
                        rollout_id, reason, self.user.id
                    )
                elif action == "HALT":
                    self.container.limited_rollout.pause(
                        rollout_id, reason, self.user.id, emergency=True
                    )
                elif action == "RESUME":
                    self.container.limited_rollout.resume(
                        rollout_id, reason, self.user.id
                    )
            self._refresh_rollout()
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Aksi rollout ditolak", str(exc))

    def _record_rollout_incident(self) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            return
        severity, accepted = QInputDialog.getItem(
            self,
            "Severity Insiden",
            "Severity:",
            ["WARNING", "CRITICAL"],
            0,
            False,
        )
        if not accepted:
            return
        summary, accepted = QInputDialog.getText(
            self,
            "Ringkasan Insiden",
            "Ringkasan tanpa identitas pasien (10-300 karakter):",
        )
        if not accepted:
            return
        affected, accepted = QInputDialog.getInt(
            self, "Dampak", "Workstation terdampak (0-500):", 0, 0, 500
        )
        if not accepted:
            return
        try:
            self.container.limited_rollout.record_incident(
                rollout_id,
                severity,
                summary,
                self.user.id,
                affected_workstations=affected,
            )
            self._refresh_rollout()
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Insiden tidak dapat dicatat", str(exc))

    def _attest_rollout(self, kind: str) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            return
        confirmed = QMessageBox.question(
            self,
            f"Attestation {kind}",
            "Saya telah meninjau seluruh wave dan operational ledger untuk scope ini.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.limited_rollout.attest(
                rollout_id, kind, self.user.id
            )
            self._refresh_rollout()
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Attestation ditolak", str(exc))

    def _decide_rollout(self, decision: str) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            return
        reason, accepted = QInputDialog.getText(
            self,
            f"Keputusan {decision}",
            "Alasan keputusan final wajib 10-300 karakter:",
        )
        if not accepted:
            return
        confirmed = QMessageBox.question(
            self,
            "Konfirmasi keputusan final",
            f"Catat {decision} secara immutable? Keputusan ini tidak mengubah "
            "konfigurasi workstation secara otomatis.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.limited_rollout.decide(
                rollout_id, decision, reason, self.user.id
            )
            self._refresh_rollout()
        except LimitedRolloutError as exc:
            QMessageBox.warning(self, "Keputusan rollout ditolak", str(exc))

    def _selected_surveillance_id(self) -> str | None:
        value = self.surveillance_session.currentData()
        return str(value) if value else None

    def _selected_surveillance_issue_id(self) -> str | None:
        row = self.surveillance_issue_table.currentRow()
        if row < 0:
            return None
        item = self.surveillance_issue_table.item(row, 5)
        return item.text() if item else None

    @Slot()
    def _refresh_surveillance(self) -> None:
        selected = self._selected_surveillance_id()
        try:
            sessions = self.container.surveillance.sessions(self.user.id)
            ledger = self.container.surveillance.ledger(self.user.id)
        except SurveillanceError as exc:
            self.surveillance_status.setText(f"Surveillance dikarantina: {exc}")
            self.surveillance_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            return
        self.surveillance_session.blockSignals(True)
        self.surveillance_session.clear()
        for record in sessions:
            self.surveillance_session.addItem(
                f"{record.environment_label} · {record.status} · {record.application_version}",
                record.id,
            )
        if selected:
            index = self.surveillance_session.findData(selected)
            if index >= 0:
                self.surveillance_session.setCurrentIndex(index)
        self.surveillance_session.blockSignals(False)
        self.surveillance_ledger_table.setRowCount(len(ledger))
        for row_index, entry in enumerate(ledger):
            values = (
                entry.sequence,
                entry.occurred_at.isoformat(timespec="seconds"),
                entry.event_type,
                entry.actor_user_id or "SYSTEM",
                entry.entry_hash,
            )
            for column, value in enumerate(values):
                self.surveillance_ledger_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._render_surveillance_selection()

    @Slot()
    def _render_surveillance_selection(self) -> None:
        surveillance_id = self._selected_surveillance_id()
        if surveillance_id is None:
            self.surveillance_status.setText(
                "Belum ada early-life surveillance untuk rollout COMPLETED."
            )
            self.surveillance_status.setStyleSheet(
                "background: #FFF7D6; color: #854D0E; padding: 8px;"
            )
            self.surveillance_blockers.setPlainText(
                "Pilih limited rollout COMPLETED, lalu buat sesi surveillance."
            )
            self.surveillance_snapshot_table.setRowCount(0)
            self.surveillance_issue_table.setRowCount(0)
            self._set_surveillance_controls(None)
            return
        try:
            readiness = self.container.surveillance.evaluate(
                surveillance_id, self.user.id
            )
            snapshots = self.container.surveillance.snapshots(
                surveillance_id, self.user.id
            )
            issues = self.container.surveillance.issues(
                surveillance_id, self.user.id
            )
        except SurveillanceError as exc:
            self.surveillance_status.setText(f"Surveillance tidak dapat dievaluasi: {exc}")
            self.surveillance_status.setStyleSheet("color: #991B1B; font-weight: 700;")
            self._set_surveillance_controls(None)
            return
        record = readiness.session
        if record.status == "PROMOTED":
            headline = "RELEASE PROMOTED — keputusan immutable"
            colors = "background: #DCFCE7; color: #166534;"
        elif record.status == "ROLLED_BACK":
            headline = "RELEASE ROLLED BACK — keputusan immutable"
            colors = "background: #FEE2E2; color: #991B1B;"
        elif readiness.ready_for_promotion:
            headline = "READY FOR PROMOTION DECISION"
            colors = "background: #DBEAFE; color: #1E3A8A;"
        else:
            headline = "EARLY-LIFE OBSERVATION BELUM LENGKAP"
            colors = "background: #FFF7D6; color: #854D0E;"
        self.surveillance_status.setText(
            f"{headline} · snapshot {readiness.snapshots_total}/{record.minimum_snapshots} · "
            f"observasi {readiness.observation_hours:.1f}/{record.minimum_observation_hours} jam · "
            f"isu terbuka {readiness.open_issues} (CRITICAL {readiness.open_critical_issues}) · "
            f"ledger {'VALID' if readiness.ledger_valid else 'INVALID'}"
        )
        self.surveillance_status.setStyleSheet(
            colors + " font-weight: 700; padding: 8px; border-radius: 5px;"
        )
        self.surveillance_blockers.setPlainText(
            "\n".join(f"• {item}" for item in readiness.blockers)
            or "Tidak ada blocker promotion."
        )
        self.surveillance_snapshot_table.setRowCount(len(snapshots))
        for row_index, snapshot in enumerate(snapshots):
            values = (
                snapshot.captured_at.isoformat(timespec="minutes"),
                snapshot.prescriptions_total,
                snapshot.critical_total,
                snapshot.unacknowledged_critical_alerts,
                snapshot.open_interventions,
                snapshot.polling_failures,
                snapshot.health_state,
                "VALID" if snapshot.audit_chain_valid else "INVALID",
            )
            for column, value in enumerate(values):
                self.surveillance_snapshot_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self.surveillance_issue_table.setRowCount(len(issues))
        for row_index, issue in enumerate(issues):
            values = (
                issue.issue_number,
                issue.severity,
                issue.status,
                issue.summary_hash_sha256,
                issue.resolution_hash_sha256 or "-",
                issue.id,
            )
            for column, value in enumerate(values):
                self.surveillance_issue_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._set_surveillance_controls(readiness)

    def _set_surveillance_controls(self, readiness) -> None:
        roles = self.user.roles
        can_technical = bool(roles.intersection({"SUPER_ADMIN", "IT_ADMIN"}))
        can_clinical = bool(
            roles.intersection(
                {"CLINICAL_REVIEWER", "APOTEKER", "KFT", "KEPALA_INSTALASI"}
            )
        )
        can_decide = bool(roles.intersection({"SUPER_ADMIN", "DIREKTUR"}))
        can_issue = can_technical or can_clinical or can_decide
        observing = bool(readiness and readiness.session.status == "OBSERVING")
        self.create_surveillance_button.setVisible(can_technical)
        self.capture_surveillance_button.setVisible(can_technical)
        self.record_surveillance_issue_button.setVisible(can_issue)
        self.close_surveillance_issue_button.setVisible(can_issue)
        self.attest_surveillance_clinical_button.setVisible(can_clinical)
        self.attest_surveillance_technical_button.setVisible(can_technical)
        self.promote_surveillance_button.setVisible(can_decide)
        self.rollback_surveillance_button.setVisible(can_decide)
        self.capture_surveillance_button.setEnabled(observing and can_technical)
        self.record_surveillance_issue_button.setEnabled(observing and can_issue)
        self.close_surveillance_issue_button.setEnabled(observing and can_issue)
        self.attest_surveillance_clinical_button.setEnabled(observing and can_clinical)
        self.attest_surveillance_technical_button.setEnabled(observing and can_technical)
        self.promote_surveillance_button.setEnabled(
            can_decide and bool(readiness and readiness.ready_for_promotion)
        )
        self.rollback_surveillance_button.setEnabled(observing and can_decide)

    def _create_surveillance(self) -> None:
        rollout_id = self._selected_rollout_id()
        if rollout_id is None:
            QMessageBox.information(
                self, "Pilih rollout", "Pilih limited rollout COMPLETED terlebih dahulu."
            )
            return
        label, accepted = QInputDialog.getText(
            self, "Early-Life Surveillance", "Label environment produksi terbatas:"
        )
        if not accepted:
            return
        days, accepted = QInputDialog.getInt(
            self, "Masa Surveillance", "Berlaku berapa hari (1-30):", 14, 1, 30
        )
        if not accepted:
            return
        try:
            record = self.container.surveillance.create_session(
                rollout_id, label, self.user.id, validity_days=days
            )
            self._refresh_surveillance()
            index = self.surveillance_session.findData(record.id)
            if index >= 0:
                self.surveillance_session.setCurrentIndex(index)
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Surveillance tidak dapat dibuat", str(exc))

    def _capture_surveillance(self) -> None:
        surveillance_id = self._selected_surveillance_id()
        if surveillance_id is None:
            return
        try:
            self.container.surveillance.capture_snapshot(
                surveillance_id, self.user.id
            )
            self._refresh_surveillance()
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Snapshot gagal", str(exc))

    def _record_surveillance_issue(self) -> None:
        surveillance_id = self._selected_surveillance_id()
        if surveillance_id is None:
            return
        severity, accepted = QInputDialog.getItem(
            self, "Severity Isu", "Severity:", ["WARNING", "CRITICAL"], 0, False
        )
        if not accepted:
            return
        summary, accepted = QInputDialog.getText(
            self, "Isu Surveillance", "Ringkasan tanpa identitas pasien (10-300 karakter):"
        )
        if not accepted:
            return
        try:
            self.container.surveillance.record_issue(
                surveillance_id, severity, summary, self.user.id
            )
            self._refresh_surveillance()
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Isu tidak dapat dicatat", str(exc))

    def _close_surveillance_issue(self) -> None:
        issue_id = self._selected_surveillance_issue_id()
        if issue_id is None:
            QMessageBox.information(self, "Pilih isu", "Pilih satu isu terlebih dahulu.")
            return
        resolution, accepted = QInputDialog.getText(
            self, "Tutup Isu", "Ringkasan remediasi (10-300 karakter):"
        )
        if not accepted:
            return
        try:
            self.container.surveillance.close_issue(
                issue_id, resolution, self.user.id
            )
            self._refresh_surveillance()
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Isu tidak dapat ditutup", str(exc))

    def _attest_surveillance(self, kind: str) -> None:
        surveillance_id = self._selected_surveillance_id()
        if surveillance_id is None:
            return
        confirmed = QMessageBox.question(
            self, f"Attestation {kind}",
            "Saya telah meninjau snapshot agregat, freshness, dan seluruh remediasi isu."
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.surveillance.attest(
                surveillance_id, kind, self.user.id
            )
            self._refresh_surveillance()
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Attestation ditolak", str(exc))

    def _decide_surveillance(self, decision: str) -> None:
        surveillance_id = self._selected_surveillance_id()
        if surveillance_id is None:
            return
        reason, accepted = QInputDialog.getText(
            self, f"Keputusan {decision}", "Alasan keputusan final 10-300 karakter:"
        )
        if not accepted:
            return
        confirmed = QMessageBox.question(
            self, "Konfirmasi keputusan final",
            f"Catat {decision} secara immutable? Tidak ada konfigurasi yang diubah otomatis."
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.surveillance.decide(
                surveillance_id, decision, reason, self.user.id
            )
            self._refresh_surveillance()
        except SurveillanceError as exc:
            QMessageBox.warning(self, "Keputusan surveillance ditolak", str(exc))

    @Slot()
    def refresh(self) -> None:
        try:
            uat = self.container.clinical_validation.uat_items(self.user.id)
            gate = self.container.clinical_validation.evaluate_gate(self.user.id)
            activation = self.container.clinical_validation.advisory_pilot_status(
                self.user.id
            )
            pending = (
                self.container.clinical_validation.pending_advisory_authorization(
                    self.user.id
                )
            )
            ledger_error = None
            try:
                ledger = (
                    self.container.clinical_validation.pilot_session_ledger(
                        self.user.id
                    )
                )
            except ClinicalValidationError as exc:
                ledger = ()
                ledger_error = str(exc)
            try:
                evidence_verifications = (
                    self.container.clinical_validation.pilot_evidence_verifications(
                        self.user.id
                    )
                )
            except ClinicalValidationError:
                evidence_verifications = ()
            cases = self.container.clinical_validation.latest_cases()
        except ClinicalValidationError as exc:
            self.feedback.setText(f"Gagal memuat validasi: {exc}")
            return
        self.gate_label.setText("SIAP ADVISORY PILOT — seluruh gate lulus" if gate.ready else "VALIDASI BELUM LENGKAP — mode advisory belum direkomendasikan")
        self.gate_label.setStyleSheet(("background: #DCFCE7; color: #166534;" if gate.ready else "background: #FFF7D6; color: #854D0E;") + "font-size: 12pt; font-weight: 700; padding: 10px; border-radius: 6px;")
        if activation.reason == "LEDGER_QUARANTINED":
            self.activation_label.setText(
                "KARANTINA LEDGER AKTIF — seluruh alert Advisory ditahan. "
                "Pulihkan backup terverifikasi, validasi rantai, lalu buka "
                "karantina sebagai IT/Super Admin."
            )
            activation_colors = "background: #581C87; color: white;"
        elif activation.emergency_stop:
            self.activation_label.setText(
                "EMERGENCY STOP AKTIF — seluruh alert Advisory ditahan sampai "
                "IT Admin/Super Admin membuka latch dan mengaktifkan ulang."
            )
            activation_colors = "background: #7F1D1D; color: white;"
        elif pending is not None:
            waiting_for = {
                "PENDING_CLINICAL": "persetujuan klinis",
                "PENDING_OUTGOING": "attestasi pemilik shift outgoing",
                "PENDING_TECHNICAL": "pengesahan IT",
            }.get(pending.status, "tindak lanjut")
            handover_counts = (
                f" Ringkasan: {pending.unresolved_alerts or 0} alert, "
                f"{pending.unresolved_critical_alerts or 0} CRITICAL, "
                f"{pending.unresolved_interventions or 0} intervensi terbuka."
                if pending.purpose == "HANDOVER"
                else ""
            )
            self.activation_label.setText(
                f"OTORISASI MENUNGGU {waiting_for.upper()} — "
                f"tujuan {pending.purpose}, durasi {pending.duration_hours} jam."
                + handover_counts
            )
            activation_colors = "background: #DBEAFE; color: #1E3A8A;"
        elif activation.active:
            expiry_text = (
                activation.expires_at.isoformat(timespec="minutes")
                if activation.expires_at
                else "tidak valid"
            )
            shift_expiry_text = (
                activation.shift_expires_at.isoformat(timespec="minutes")
                if activation.shift_expires_at
                else "tidak valid"
            )
            self.activation_label.setText(
                "ADVISORY PILOT AKTIF — otorisasi terikat pada kampanye dan "
                f"dual sign-off terbaru; aktivasi sampai {expiry_text}, "
                f"shift klinis sampai {shift_expiry_text}."
            )
            activation_colors = "background: #DCFCE7; color: #166534;"
        elif gate.ready:
            self.activation_label.setText(
                "MENUNGGU AKTIVASI — gate lulus, tetapi IT/Super Admin belum "
                "mengaktifkan Advisory Pilot."
            )
            activation_colors = "background: #FFF7D6; color: #854D0E;"
        else:
            self.activation_label.setText(
                "ADVISORY TERKUNCI — aktivasi hanya dapat dilakukan setelah "
                "seluruh gate lulus."
            )
            activation_colors = "background: #FEE2E2; color: #991B1B;"
        self.activation_label.setStyleSheet(
            activation_colors
            + " font-weight: 700; padding: 9px; border-radius: 6px;"
        )
        can_control = bool(
            self.user.roles.intersection({"SUPER_ADMIN", "IT_ADMIN"})
        )
        can_clinical = bool(
            self.user.roles.intersection(
                {"CLINICAL_REVIEWER", "APOTEKER", "KFT"}
            )
        )
        self.activate_button.setVisible(can_control)
        self.deactivate_button.setVisible(can_control)
        self.authorization_duration.setVisible(can_control or can_clinical)
        self.reset_emergency_button.setVisible(can_control)
        self.activate_button.setEnabled(
            can_control
            and gate.ready
            and not activation.active
            and not activation.emergency_stop
            and pending is None
        )
        self.deactivate_button.setEnabled(can_control and activation.active)
        self.authorization_duration.setEnabled(
            can_control and not activation.active and not activation.emergency_stop
        )
        self.emergency_stop_button.setEnabled(not activation.emergency_stop)
        self.reset_emergency_button.setEnabled(
            can_control and activation.emergency_stop
        )
        self.export_evidence_button.setEnabled(ledger_error is None)
        self.reset_ledger_quarantine_button.setVisible(can_control)
        self.reset_ledger_quarantine_button.setEnabled(
            can_control
            and activation.reason == "LEDGER_QUARANTINED"
            and ledger_error is None
        )
        self.approve_activation_button.setVisible(can_clinical)
        self.approve_activation_button.setEnabled(
            can_clinical
            and pending is not None
            and pending.status == "PENDING_CLINICAL"
        )
        self.request_handover_button.setVisible(can_clinical)
        self.request_handover_button.setEnabled(
            can_clinical
            and activation.active
            and activation.clinical_owner_id != self.user.id
            and pending is None
        )
        self.attest_outgoing_button.setVisible(can_clinical)
        self.attest_outgoing_button.setEnabled(
            can_clinical
            and activation.active
            and activation.clinical_owner_id == self.user.id
            and pending is not None
            and pending.status == "PENDING_OUTGOING"
        )
        self.close_shift_button.setVisible(can_clinical)
        self.close_shift_button.setEnabled(
            can_clinical
            and activation.active
            and activation.clinical_owner_id == self.user.id
        )
        self.approve_handover_button.setVisible(can_control)
        self.approve_handover_button.setEnabled(
            can_control
            and pending is not None
            and pending.status == "PENDING_TECHNICAL"
        )
        self.stats_label.setText(
            f"Kampanye: {gate.campaign_name} · Kasus ditinjau {gate.cases_reviewed}/{gate.cases_total} · "
            f"Cocok {gate.cases_matched}/{gate.cases_total} · CRITICAL {gate.critical_detected}/{gate.critical_total} · "
            f"HIGH_RISK {gate.high_risk_detected}/{gate.high_risk_total} · UAT PASS {gate.uat_passed}/{gate.uat_total} · "
            f"Sign-off Apoteker {'YA' if gate.pharmacist_approved else 'BELUM'} · IT {'YA' if gate.it_approved else 'BELUM'}"
        )
        displayed_blockers = (
            activation.blockers
            if gate.ready and not activation.active
            else gate.blockers
        )
        self.blockers.setPlainText(
            "\n".join(f"• {item}" for item in displayed_blockers)
            or "Tidak ada blocker."
        )
        self.case_table.setRowCount(len(cases))
        for row_index, case in enumerate(cases):
            values = (case.case_code, case.drug_list, case.expected_severity, case.actual_severity, case.review_status, "YA" if case.match is True else "TIDAK" if case.match is False else "-", case.reviewer)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 5:
                    item.setForeground(Qt.GlobalColor.darkGreen if case.match is True else Qt.GlobalColor.darkRed)
                self.case_table.setItem(row_index, column, item)
        self.uat_table.setRowCount(len(uat))
        for row_index, item in enumerate(uat):
            for column, value in enumerate((item.item_code, item.category, item.description, item.owner_role, item.status, item.tester, item.id)):
                self.uat_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        if ledger_error is None:
            self.ledger_status.setText(
                f"Rantai ledger valid — {len(ledger)} entri terbaru ditampilkan."
            )
            self.ledger_status.setStyleSheet(
                "color: #166534; font-weight: 700;"
            )
        else:
            self.ledger_status.setText(
                f"Ledger tidak dapat diverifikasi: {ledger_error}"
            )
            self.ledger_status.setStyleSheet(
                "color: #991B1B; font-weight: 700;"
            )
        self.ledger_table.setRowCount(len(ledger))
        for row_index, entry in enumerate(ledger):
            values = (
                entry.sequence,
                entry.occurred_at.isoformat(timespec="seconds"),
                entry.event_type,
                entry.activation_id,
                entry.actor_user_id or "SYSTEM",
                entry.entry_hash,
            )
            for column, value in enumerate(values):
                self.ledger_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self.evidence_verification_table.setRowCount(
            len(evidence_verifications)
        )
        for row_index, verification in enumerate(evidence_verifications):
            result_text = (
                "VALID"
                if verification.valid
                else "INVALID: " + ", ".join(verification.errors)
            )
            values = (
                verification.verified_at.isoformat(timespec="seconds"),
                verification.package_filename,
                result_text,
                verification.application_version or "-",
                verification.ledger_head_hash or "-",
                verification.checksum_sha256 or "-",
            )
            for column, value in enumerate(values):
                self.evidence_verification_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self._refresh_pilot()
        self._refresh_go_live()
        self._refresh_rollout()
        self._refresh_surveillance()
        self.production_release_panel.refresh()
        self.uat_release_panel.refresh()
        self.feedback.setText(
            "Gate dan otorisasi Advisory Pilot berhasil dievaluasi ulang."
        )

    @Slot()
    def _refresh_pilot(self) -> None:
        days = int(self.pilot_period.currentData() or 30)
        try:
            summary = self.container.clinical_validation.pilot_monitoring(
                self.user.id, days
            )
        except ClinicalValidationError as exc:
            self.pilot_status.setText(f"Monitoring tidak dapat dimuat: {exc}")
            return
        if summary.has_operational_data:
            self.pilot_status.setText(
                f"Data operasional tersedia: {summary.prescriptions_total} resep "
                f"non-MOCK dalam {days} hari. Interpretasi dan batas alert fatigue "
                "tetap harus disetujui apoteker/KFT."
            )
            self.pilot_status.setStyleSheet(
                "background: #DCFCE7; color: #166534; padding: 8px; "
                "border-radius: 5px;"
            )
        else:
            self.pilot_status.setText(
                f"Belum ada resep non-MOCK dalam {days} hari. Jalankan silent pilot "
                "sebelum menilai beban alert."
            )
            self.pilot_status.setStyleSheet(
                "background: #FFF7D6; color: #854D0E; padding: 8px; "
                "border-radius: 5px;"
            )
        median_ack = (
            f"{summary.median_acknowledgement_minutes:.1f} menit"
            if summary.median_acknowledgement_minutes is not None
            else "—"
        )
        acceptance = (
            f"{summary.acceptance_rate:.1f}%"
            if summary.acceptance_rate is not None
            else "—"
        )
        rows = (
            ("Resep diskrining", summary.prescriptions_total, "Resep riil/non-MOCK"),
            ("CRITICAL", summary.critical_prescriptions, "Memerlukan review segera"),
            ("HIGH_RISK", summary.high_risk_prescriptions, "Memerlukan review apoteker"),
            ("Alert dibuat", summary.alerts_total, "Satu alert gabungan per resep"),
            ("Beban alert", f"{summary.alert_rate_per_100:.1f}/100 resep", "Dasar evaluasi alert fatigue"),
            ("Alert ditampilkan", summary.alerts_shown, "Notifikasi benar-benar dikirim"),
            ("Alert diakui", f"{summary.alerts_acknowledged} ({summary.acknowledgement_rate:.1f}%)", "Dibuka/ditinjau petugas"),
            ("Median waktu acknowledgement", median_ack, "Kecepatan respons operasional"),
            ("CRITICAL belum diakui", summary.critical_unacknowledged, "Harus ditelaah selama pilot"),
            ("Intervensi selesai", f"{summary.interventions_completed}/{summary.interventions_total}", "Kelengkapan dokumentasi"),
            ("Rekomendasi diterima", f"{summary.accepted_interventions}/{summary.assessable_interventions} ({acceptance})", "Hanya outcome diterima/tidak diterima"),
        )
        self.pilot_table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                self.pilot_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )

    @Slot()
    def _export_pilot(self) -> None:
        days = int(self.pilot_period.currentData() or 30)
        filename = f"MONITORING_PILOT_EMSS_{days}_HARI.csv"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Ekspor monitoring pilot agregat",
            str(self.container.settings.export_dir / filename),
            "CSV (*.csv)",
        )
        if not target:
            return
        try:
            saved = self.container.clinical_validation.export_pilot_monitoring(
                target, self.user.id, days
            )
            self.feedback.setText(
                f"Monitoring agregat berhasil diekspor: {saved}"
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Ekspor monitoring gagal", str(exc))

    def _export_pilot_evidence(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Ekspor paket bukti sesi pilot",
            str(
                self.container.settings.export_dir
                / "BUKTI_SESI_PILOT_EMSS.zip"
            ),
            "ZIP Archive (*.zip)",
        )
        if not target:
            return
        try:
            result = (
                self.container.clinical_validation.export_pilot_session_evidence(
                    target, self.user.id
                )
            )
            self.feedback.setText(
                "Paket bukti berhasil diekspor: "
                f"{result.path} · checksum {result.checksum_sha256}"
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Ekspor bukti pilot gagal", str(exc))

    def _verify_pilot_evidence(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Verifikasi paket bukti sesi pilot",
            str(self.container.settings.export_dir),
            "ZIP Archive (*.zip)",
        )
        if not source:
            return
        try:
            result = (
                self.container.clinical_validation.verify_pilot_evidence_package(
                    source, self.user.id
                )
            )
            self.refresh()
            if result.valid:
                self.feedback.setText(
                    "Paket bukti VALID dan hasil verifikasi telah dicatat "
                    f"secara immutable. Checksum: {result.checksum_sha256}"
                )
            else:
                self.feedback.setText(
                    "Paket bukti INVALID; hasil tetap dicatat secara immutable. "
                    f"Kode: {', '.join(result.errors)}"
                )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Verifikasi bukti gagal", str(exc))

    def _reset_ledger_quarantine(self) -> None:
        reference, accepted = QInputDialog.getText(
            self,
            "Buka Karantina Ledger",
            "Referensi backup/insiden pemulihan (wajib 10-300 karakter):",
        )
        if not accepted:
            return
        confirmed = QMessageBox.question(
            self,
            "Konfirmasi Integritas Ledger",
            "Buka karantina hanya jika backup telah dipulihkan dan rantai "
            "ledger kembali valid. Aktivasi ulang tetap wajib. Lanjutkan?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.clinical_validation.reset_pilot_ledger_quarantine(
                self.user.id, reference
            )
            self.refresh()
            self.feedback.setText(
                "Karantina ledger dibuka; aktivasi Advisory baru tetap wajib."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Karantina tidak dapat dibuka", str(exc))

    def _download_validation(self) -> None:
        self._download("TEMPLATE_VALIDASI_KLINIS_EMSS_SPRINT10.xlsx")

    def _download_uat(self) -> None:
        self._download("TEMPLATE_UAT_EMSS_SPRINT10.xlsx")

    def _download(self, filename: str) -> None:
        source = bundled_resource("templates", filename)
        target, _ = QFileDialog.getSaveFileName(self, "Simpan template", str(self.container.settings.export_dir / filename), "Excel Workbook (*.xlsx)")
        if not target:
            return
        try:
            shutil.copy2(source, target)
            self.feedback.setText(f"Template berhasil disimpan: {target}")
        except OSError as exc:
            QMessageBox.warning(self, "Template gagal disimpan", str(exc))

    def _import_validation(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pilih hasil validasi klinis", "", "Excel Workbook (*.xlsx)")
        if not path:
            return
        self.import_button.setEnabled(False)
        self.import_button.setText("Mengimpor…")
        try:
            result = self.container.clinical_validation.import_workbook(path, self.user.id)
            self.feedback.setText(f"Import selesai: {result.total_cases} kasus, {result.reviewed_cases} ditinjau, {result.matched_cases} cocok.")
            self.refresh()
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Import validasi gagal", str(exc))
            self.feedback.setText(f"Import gagal: {exc}")
        finally:
            self.import_button.setEnabled(True)
            self.import_button.setText("Import Hasil Validasi Klinis")

    def _selected_uat_id(self) -> str | None:
        row = self.uat_table.currentRow()
        return self.uat_table.item(row, 6).text() if row >= 0 and self.uat_table.item(row, 6) else None

    def _mark_uat(self, status: str) -> None:
        item_id = self._selected_uat_id()
        if not item_id:
            QMessageBox.information(self, "Pilih item UAT", "Pilih satu baris checklist terlebih dahulu.")
            return
        try:
            revoked = self.container.clinical_validation.update_uat_item(item_id, status, self.user.id, self.user.display_name, actual_result=f"Ditandai {status} melalui aplikasi")
            self.refresh()
            message = f"Item UAT berhasil ditandai {status}."
            if revoked:
                message += f" Persetujuan {revoked} dicabut; sign-off ulang wajib dilakukan."
            self.feedback.setText(message)
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "UAT tidak dapat diubah", str(exc))

    def _approve(self, kind: str) -> None:
        try:
            self.container.clinical_validation.approve_uat(kind, self.user.id)
            self.refresh()
            self.feedback.setText(f"Persetujuan UAT {kind} berhasil dicatat dan diaudit.")
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Persetujuan belum dapat diberikan", str(exc))

    def _activate_advisory(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Aktifkan Advisory Pilot",
            "Aktifkan alert rekomendasi Advisory Pilot untuk kampanye dan "
            "dual sign-off saat ini?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            duration_hours = int(
                self.authorization_duration.currentData() or 24
            )
            request = self.container.clinical_validation.request_advisory_pilot_activation(
                self.user.id, duration_hours
            )
            self.refresh()
            self.feedback.setText(
                "Permintaan aktivasi dicatat; petugas klinis berbeda harus "
                f"menyetujui dalam 30 menit. ID: {request.id}"
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Aktivasi Advisory gagal", str(exc))

    def _approve_advisory_activation(self) -> None:
        try:
            pending = (
                self.container.clinical_validation.pending_advisory_authorization(
                    self.user.id
                )
            )
            if pending is None or pending.status != "PENDING_CLINICAL":
                raise ClinicalValidationError(
                    "Tidak ada permintaan aktivasi yang menunggu persetujuan klinis"
                )
            self.container.clinical_validation.approve_advisory_pilot_activation(
                pending.id, self.user.id
            )
            self.refresh()
            self.feedback.setText(
                "Aktivasi dua-person berhasil; Anda tercatat sebagai pemilik shift klinis."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Persetujuan aktivasi gagal", str(exc))

    def _request_shift_handover(self) -> None:
        try:
            duration_hours = int(
                self.authorization_duration.currentData() or 24
            )
            request = self.container.clinical_validation.request_advisory_shift_handover(
                self.user.id, duration_hours
            )
            self.refresh()
            self.feedback.setText(
                "Incoming attestation tercatat; pemilik shift outgoing harus "
                "menyetujui ringkasan sebelum IT mengesahkan. "
                f"ID: {request.id}"
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Handover tidak dapat diajukan", str(exc))

    def _attest_outgoing_handover(self) -> None:
        try:
            pending = (
                self.container.clinical_validation.pending_advisory_authorization(
                    self.user.id
                )
            )
            if pending is None or pending.status != "PENDING_OUTGOING":
                raise ClinicalValidationError(
                    "Tidak ada handover yang menunggu outgoing attestation"
                )
            confirmed = QMessageBox.question(
                self,
                "Attestasi Outgoing Shift",
                "Saya mengonfirmasi ringkasan handover: "
                f"{pending.unresolved_alerts or 0} alert belum selesai, "
                f"{pending.unresolved_critical_alerts or 0} CRITICAL, dan "
                f"{pending.unresolved_interventions or 0} intervensi terbuka.",
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return
            self.container.clinical_validation.attest_advisory_shift_handover(
                pending.id, self.user.id
            )
            self.refresh()
            self.feedback.setText(
                "Outgoing attestation tercatat; handover menunggu pengesahan IT."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Attestasi outgoing gagal", str(exc))

    def _close_clinical_shift(self) -> None:
        note, accepted = QInputDialog.getText(
            self,
            "Closeout Shift Klinis",
            "Catatan closeout/attestation (wajib 10-300 karakter):",
        )
        if not accepted:
            return
        confirmed = QMessageBox.question(
            self,
            "Konfirmasi Closeout Shift",
            "Tutup shift dan hentikan aktivasi Advisory Pilot sekarang?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.clinical_validation.close_advisory_shift(
                self.user.id, note
            )
            self.refresh()
            self.feedback.setText(
                "Shift ditutup; ringkasan closeout dan ledger audit telah disimpan."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Closeout shift gagal", str(exc))

    def _approve_shift_handover(self) -> None:
        try:
            pending = (
                self.container.clinical_validation.pending_advisory_authorization(
                    self.user.id
                )
            )
            if pending is None or pending.status != "PENDING_TECHNICAL":
                raise ClinicalValidationError(
                    "Tidak ada handover yang menunggu pengesahan IT"
                )
            self.container.clinical_validation.approve_advisory_shift_handover(
                pending.id, self.user.id
            )
            self.refresh()
            self.feedback.setText(
                "Handover disahkan; aktivasi kini dimiliki petugas klinis pengganti."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Pengesahan handover gagal", str(exc))

    def _deactivate_advisory(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Nonaktifkan Advisory Pilot",
            "Nonaktifkan alert rekomendasi Advisory Pilot sekarang?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.clinical_validation.deactivate_advisory_pilot(
                self.user.id
            )
            self.refresh()
            self.feedback.setText(
                "Advisory Pilot dinonaktifkan dan dicatat pada audit."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Penonaktifan Advisory gagal", str(exc))

    def _emergency_stop(self) -> None:
        reason, accepted = QInputDialog.getText(
            self,
            "Emergency Stop Advisory Pilot",
            "Alasan penghentian darurat (wajib 10-300 karakter):",
        )
        if not accepted:
            return
        try:
            self.container.clinical_validation.trigger_advisory_emergency_stop(
                self.user.id, reason
            )
            self.refresh()
            self.feedback.setText(
                "Emergency stop aktif; seluruh alert Advisory ditahan."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Emergency stop gagal", str(exc))

    def _reset_emergency_stop(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Buka Emergency Stop",
            "Buka latch emergency stop? Advisory tetap nonaktif sampai "
            "diaktifkan ulang secara eksplisit.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.container.clinical_validation.reset_advisory_emergency_stop(
                self.user.id
            )
            self.refresh()
            self.feedback.setText(
                "Emergency stop dibuka; aktivasi ulang Advisory masih wajib."
            )
        except ClinicalValidationError as exc:
            QMessageBox.warning(self, "Reset emergency stop gagal", str(exc))
