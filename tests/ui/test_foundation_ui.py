from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTextBrowser

from emss.desktop import SingleInstanceGuard
from emss import __version__
from emss.services.queue import QueueDetail, QueueItem, QueueSummary
from emss.services.authentication import AuthenticatedUser
from emss.services.knowledge import DdiRuleDetail
from emss.ui.application import (
    APP_STYLESHEET,
    ChangePasswordDialog,
    DrugCatalogTab,
    DrugImportTab,
    FirstAdminDialog,
    LoginDialog,
    MainWindow,
)
from emss.ui.knowledge.management import (
    DdiInputDialog,
    DdiImportTab,
    DdiRuleDetailDialog,
    KnowledgeBaseTab,
)
from emss.ui.intervention import InterventionDialog
from emss.ui.queue import QueuePanel
from emss.ui.screening.simulator import ScreeningSimulatorTab
from emss.ui.tray import FullscreenAlertPopup, SystemTrayController
from emss.ui.integration import KhanzaIntegrationPanel
from emss.ui.icons import (
    CLINICAL_ICON_FILES,
    NAVIGATION_ICON_KEYS,
    application_icon,
    clinical_icon,
    icon_path,
)
from emss.ui.interactions import HOVER_DURATION_MS, install_hover_feedback
from emss.ui.backup import BackupPanel
from emss.config.settings import AppEnvironment


def test_workflow_page_stays_light_with_windows_dark_palette(qtbot, qapp):
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtWidgets import QWidget
    from emss.ui.navigation import ScrollableTabs
    old = qapp.palette()
    dark = QPalette(old)
    dark.setColor(QPalette.ColorRole.Window, QColor('#202020'))
    qapp.setPalette(dark)
    try:
        tabs = ScrollableTabs()
        qtbot.addWidget(tabs)
        page = QWidget()
        tabs.addTab(page, 'Antrean')
        tabs.resize(500, 350)
        tabs.show()
        qapp.processEvents()
        assert page.grab().toImage().pixelColor(2, 2).name() == '#f4f7fa'
    finally:
        qapp.setPalette(old)


def test_compact_popup_supports_explicit_simulation_label(qtbot):
    popup = FullscreenAlertPopup()
    qtbot.addWidget(popup)
    popup.show_interaction('Pasien Uji', 'major', 'MOCK-RX-LOCAL', is_mock=True,
        incomplete=True, test_label='UJI SIMULASI')
    assert 'UJI SIMULASI' in popup.hint.text()
    assert 'DUMMY' not in popup.hint.text()
    assert 'Resep MOCK-RX-LOCAL' in popup.hint.text()
    popup.hide()


def test_monitoring_banner_reports_worker_and_partial_failures(qtbot, app_container):
    from emss.services.khanza_polling import PollingResult
    user = AuthenticatedUser(id='dummy-status',username='apoteker',display_name='Petugas Uji',roles=frozenset({'APOTEKER'}),must_change_password=False)
    panel = KhanzaIntegrationPanel(app_container, user)
    qtbot.addWidget(panel)
    seen = []
    panel.monitoring_changed.connect(seen.append)
    panel._poll_failed('Sumber tidak dapat dibaca')
    assert 'Pemeriksaan gagal: Sumber tidak dapat dibaca' in seen[-1]
    panel._poll_succeeded(PollingResult(status='PARTIAL', failed=1, message='Periksa data resep'))
    assert '1 resep gagal diperiksa' in seen[-1]
    assert 'Periksa data resep' in seen[-1]


@pytest.mark.parametrize('category,title', [('major','MAYOR'),('contraindicated','KONTRAINDIKASI')])
def test_compact_interaction_popup_patient_severity_and_plain_text(qtbot, category, title):
    popup = FullscreenAlertPopup()
    qtbot.addWidget(popup)
    popup.show_interaction('Pasien Uji A <b>literal</b>',category,'MOCK-UJI-01',
        is_mock=True,incomplete=True)
    assert popup.isVisible() and popup.title.text() == title and popup.width() == 400
    assert popup.message.text() == 'Pasien: Pasien Uji A <b>literal</b>\nDitemukan interaksi obat.'
    assert popup.message.textFormat() == Qt.TextFormat.PlainText
    assert '22pt' in popup.card.styleSheet() and 'font-weight: 800' in popup.card.styleSheet()
    assert 'UJI DUMMY' in popup.hint.text() and 'Ada catatan pemeriksaan' in popup.hint.text()
    assert 'belum lengkap' not in popup.hint.text().lower()
    popup.hide()


def test_compact_major_popup_keeps_combined_clinical_summary(qtbot):
    popup = FullscreenAlertPopup()
    qtbot.addWidget(popup)
    popup.show_interaction(
        'Pasien Uji', 'major', 'RX-COMBINED', is_mock=False, incomplete=False,
        clinical_message='Ditemukan interaksi mayor.\nTemuan tambahan: potensi duplikasi obat.',
    )

    assert popup.title.text() == 'MAYOR'
    assert 'Temuan tambahan: potensi duplikasi obat.' in popup.message.text()
    assert 'background: #FFF7ED' in popup.card.styleSheet()
    popup.hide()


def test_global_controls_have_visible_dropdown_and_press_feedback():
    assert "QComboBox::down-arrow" in APP_STYLESHEET
    assert "combo-chevron-down.svg" not in APP_STYLESHEET
    assert "__COMBO_ARROW_PATH__" in APP_STYLESHEET
    assert "QPushButton:pressed" in APP_STYLESHEET
    assert "QPushButton:focus" in APP_STYLESHEET
    assert "background: #2563EB" in APP_STYLESHEET
    assert "QPlainTextEdit, QTextEdit, QTextBrowser" in APP_STYLESHEET
    assert "QMenu::item:selected" in APP_STYLESHEET
    assert "QMenuBar::item:pressed" in APP_STYLESHEET
    assert "QScrollArea QWidget#qt_scrollarea_viewport" in APP_STYLESHEET


def test_clinical_icon_registry_is_bundled_semantic_and_has_safe_fallback():
    assert set(NAVIGATION_ICON_KEYS.values()).issubset(CLINICAL_ICON_FILES)
    for key in CLINICAL_ICON_FILES:
        assert icon_path(key) is not None
        assert not clinical_icon(key).isNull()
    assert icon_path('../outside') is None
    assert clinical_icon('../outside').isNull()


def test_hover_feedback_keeps_geometry_and_gives_buttons_pointer_feedback(qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    button = QPushButton('Simpan', root)
    button.move(15, 20)
    button.resize(120, 36)
    original_geometry = button.geometry()
    qtbot.addWidget(root)
    root.show()
    install_hover_feedback(root)

    assert button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert button.geometry() == original_geometry
    assert button.graphicsEffect() is not None
    assert HOVER_DURATION_MS == 180
    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    qtbot.wait(HOVER_DURATION_MS + 30)
    assert button.geometry() == original_geometry


@pytest.mark.ui
def test_login_dialog_disables_login_without_user(qtbot, app_container):
    dialog = LoginDialog(app_container)
    qtbot.addWidget(dialog)

    assert "Belum ada pengguna" in dialog.message.text()
    assert dialog.windowTitle() == "Masuk — E-MAS Farmasi"
    assert dialog.findChild(QLabel, "loginBrandLogo").pixmap() is not None
    assert dialog.findChild(QLabel, "loginProductName").text() == "electronic Medication Alert System"
    assert dialog.create_admin_button.isVisibleTo(dialog)


@pytest.mark.ui
def test_first_admin_wizard_creates_account_and_triggers_ddi_seed(
    qtbot, app_container, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        app_container.bundled_ddi,
        "apply_if_eligible",
        lambda actor: calls.append(actor) or SimpleNamespace(status="APPLIED"),
    )
    dialog = FirstAdminDialog(app_container)
    qtbot.addWidget(dialog)
    dialog.username.setText("admin.gui")
    dialog.display_name.setText("Administrator GUI")
    dialog.password.setText("Password#Admin2026")
    dialog.confirm_password.setText("berbeda")
    dialog._submit()
    assert "tidak sama" in dialog.message.text()

    dialog.password.setText("Password#Admin2026")
    dialog.confirm_password.setText("Password#Admin2026")
    dialog._submit()

    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.authenticated_user is not None
    assert dialog.authenticated_user.username == "admin.gui"
    assert calls == [dialog.authenticated_user.id]


@pytest.mark.ui
def test_main_window_shows_ready_health(qtbot, app_container):
    user = AuthenticatedUser(
        id="test-user",
        username="apoteker",
        display_name="Apoteker Uji",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "E-MAS Farmasi"
    assert list(window.navigation.groups) == ['Pelayanan harian', 'Penelusuran', 'Data referensi', 'Pengaturan']
    assert window.tabs.currentWidget() is window.queue_tab
    assert not window.queue_tab.refresh_button.icon().isNull()
    assert not window.knowledge_tab.new_button.icon().isNull()
    assert all(window.navigation.groups['Pelayanan harian'].child(i).text(0) != 'Perlu Perhatian'
        for i in range(window.navigation.groups['Pelayanan harian'].childCount()))
    window.queue_tab.status_filter.setCurrentIndex(window.queue_tab.status_filter.findData('ATTENTION'))
    assert window.queue_tab.status_filter.currentData() == 'ATTENTION'
    window.open_alert_queue()
    assert window.navigation.heading.text() == 'Antrean Resep'
    assert window.queue_tab.status_filter.currentData() == ''
    history = window.navigation.groups['Penelusuran'].child(0)
    window.navigation.tree.setCurrentItem(history)
    assert window.queue_tab.status_filter.currentData() == ''
    assert window.navigation.heading.text() == 'Riwayat Pemeriksaan'
    assert window.findChild(QLabel, "mainBrandLogo").pixmap() is not None
    assert "electronic Medication Alert System" in window.findChild(QLabel, "mainProductName").text()
    assert window.validation_tab.pilot_period.currentData() == 30
    assert window.validation_tab.pilot_table.columnCount() == 3
    assert window.validation_tab.ledger_table.columnCount() == 6
    assert window.findChild(
        QPushButton, "attestOutgoingAdvisoryShiftHandover"
    ) is not None
    assert window.findChild(
        QPushButton, "closeAdvisoryClinicalShift"
    ) is not None
    assert window.findChild(
        QPushButton, "exportPilotSessionEvidence"
    ) is not None
    assert window.findChild(
        QPushButton, "verifyPilotEvidencePackage"
    ) is not None
    assert window.validation_tab.evidence_verification_table.columnCount() == 6
    assert window.validation_tab.go_live_table.columnCount() == 8
    assert window.validation_tab.go_live_ledger_table.columnCount() == 5
    assert window.findChild(QPushButton, "createGoLiveAcceptance") is not None
    assert window.findChild(QPushButton, "attestGoLiveClinical") is not None
    assert window.findChild(QPushButton, "decideGoLiveGo") is not None
    assert window.validation_tab.rollout_wave_table.columnCount() == 6
    assert window.validation_tab.rollout_ledger_table.columnCount() == 6
    assert window.findChild(QPushButton, "createLimitedRollout") is not None
    assert window.findChild(QPushButton, "haltLimitedRollout") is not None
    assert window.findChild(QPushButton, "recordLimitedRolloutIncident") is not None
    assert window.findChild(QPushButton, "decideRolloutRollback") is not None
    assert window.validation_tab.surveillance_snapshot_table.columnCount() == 8
    assert window.validation_tab.surveillance_issue_table.columnCount() == 6
    assert window.validation_tab.surveillance_ledger_table.columnCount() == 5
    assert window.findChild(QPushButton, "createEarlyLifeSurveillance") is not None
    assert window.findChild(QPushButton, "captureSurveillanceSnapshot") is not None
    assert window.findChild(QPushButton, "decideSurveillancePromote") is not None
    assert window.validation_tab.production_release_panel.evidence_table.columnCount() == 6
    assert window.validation_tab.production_release_panel.package_table.columnCount() == 5
    assert window.validation_tab.production_release_panel.ledger_table.columnCount() == 5
    assert window.findChild(QPushButton, "createProductionReleaseRecord") is not None
    assert window.findChild(QPushButton, "recordProductionEvidence") is not None
    assert window.findChild(QPushButton, "recordProductionChangeApproval") is not None
    assert window.findChild(QPushButton, "authorizeProductionRelease") is not None
    assert window.findChild(QPushButton, "revokeProductionRelease") is not None
    assert window.findChild(QPushButton, "orderProductionEmergencyRollback") is not None
    assert window.findChild(QPushButton, "verifyProductionEvidencePackage") is not None
    assert window.findChild(QPushButton, "startProductionDeploymentCeremony") is not None
    assert window.findChild(QPushButton, "attestProductionCeremonyTechnical") is not None
    assert window.findChild(QPushButton, "attestProductionCeremonyClinical") is not None
    assert window.findChild(QPushButton, "abortProductionDeploymentCeremony") is not None
    assert window.findChild(QPushButton, "exportProductionAuthorizationReceipt") is not None
    assert window.validation_tab.uat_release_panel.evidence_table.columnCount() == 6
    assert window.validation_tab.uat_release_panel.result_table.columnCount() == 6
    assert window.validation_tab.uat_release_panel.issue_table.columnCount() == 6
    assert window.validation_tab.uat_release_panel.ledger_table.columnCount() == 6
    assert window.findChild(QPushButton, "createUatReleaseCandidate") is not None
    assert window.findChild(QPushButton, "recordUatReadinessEvidence") is not None
    assert window.findChild(QPushButton, "exportUatExecutionKit") is not None
    assert window.findChild(QPushButton, "startUatExecution") is not None
    assert window.findChild(QPushButton, "recordUatExecutionResult") is not None
    assert window.findChild(QPushButton, "signUatExecutionClinical") is not None
    assert window.findChild(QPushButton, "signUatExecutionTechnical") is not None
    assert window.findChild(QPushButton, "acceptUatExecution") is not None
    assert window.findChild(QPushButton, "exportUatAcceptanceReceipt") is not None
    assert window.findChild(
        QPushButton, "resetPilotLedgerQuarantine"
    ) is not None
    assert window.state_label.text() == "Status pelayanan"
    assert "Koneksi Khanza belum diatur" in window.detail_label.text()
    assert "Schema:" not in window.detail_label.text()
    assert window.catalog_tab.summary_label.text().startswith("Total obat: 0")
    assert window.knowledge_tab.summary_label.text().startswith("Belum ada")
    assert window.queue_tab.summary_label.text().startswith("Total 0")
    assert window.screening_tab.simulate_button.text() == (
        "Simulasikan Resep Masuk"
    )
    window.open_simulator_button.click()
    assert window.tabs.currentWidget() is window.screening_tab
    assert isinstance(window.integration_tab, KhanzaIntegrationPanel)
    assert "READ ONLY" in window.integration_tab.findChildren(type(window.state_label))[0].text()
    assert not window.dashboard_authorized
    assert window.tabs.indexOf(window.dashboard_tab) == -1
    assert window.safety_tab.poly.value() == 5
    assert window.safety_tab.hyper.value() == 10
    assert isinstance(window.backup_tab, BackupPanel)
    assert window.tabs.indexOf(window.backup_tab) == -1
    assert window.tabs.indexOf(window.validation_tab) >= 0
    assert not window.test_fullscreen_alert_button.isHidden()
    window.open_alert_queue()
    assert window.tabs.currentWidget() is window.queue_tab


@pytest.mark.ui
def test_about_menu_is_separate_from_help_and_shows_approved_identity(qtbot, app_container, monkeypatch):
    user = AuthenticatedUser('about-user', 'apoteker.about', 'Apoteker Uji', frozenset({'APOTEKER'}), False)
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)
    action = window.findChild(QAction, 'aboutEmasFarmasi')
    assert action is not None
    assert action.parent().title() == 'Tentang'
    captured = {}
    original_exec = QDialog.exec
    def inspect(dialog):
        captured['title'] = dialog.findChild(QLabel, 'aboutEmasTitle').text()
        captured['release'] = dialog.findChild(QLabel, 'aboutEmasRelease').text()
        captured['team'] = dialog.findChild(QLabel, 'aboutEmasTeam').text()
        captured['validator'] = dialog.findChild(QLabel, 'aboutEmasValidator').text()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog, 'exec', inspect)
    window._show_about()
    assert captured['title'] == 'E-MAS Farmasi'
    assert f'v{__version__}' in captured['release'] and 'Ke-2' in captured['release']
    assert 'Nuur Hanifah' in captured['team'] and "Achmad Fauzi" in captured['team']
    assert 'Komite Farmasi dan Terapi' in captured['validator']


@pytest.mark.ui
def test_catalog_has_persistent_scrollbar_and_fast_navigation(qtbot, app_container):
    user = AuthenticatedUser('catalog-user', 'apoteker.catalog', 'Apoteker Uji', frozenset({'APOTEKER'}), False)
    tab = DrugCatalogTab(app_container, user)
    qtbot.addWidget(tab)
    assert tab.table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert tab.findChild(QPushButton, 'catalogScrollTop') is not None
    assert tab.findChild(QPushButton, 'catalogScrollBottom') is not None
    assert 'PENDING_REVIEW berarti' in tab.summary_label.text()


@pytest.mark.ui
def test_silent_pilot_hides_operational_alerts_for_routine_pharmacist(
    qtbot, app_container, monkeypatch
):
    app_container.settings.environment = AppEnvironment.SILENT_PILOT
    user = AuthenticatedUser(
        id="silent-pharmacist",
        username="apoteker.silent",
        display_name="Apoteker Silent",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    assert window.tabs.indexOf(window.queue_tab) == -1
    assert window.tabs.indexOf(window.intervention_tab) == -1
    assert window.tabs.indexOf(window.screening_tab) == -1
    assert window.findChild(QLabel, "silentPilotBanner") is not None
    assert window.test_fullscreen_alert_button.isHidden()

    class SilentTray:
        shown = False
        updated = False

        class TrayIcon:
            @staticmethod
            def isVisible():
                return False

        tray = TrayIcon()

        def show_screening_alert(self, _queued):
            self.shown = True
            return True

        def update_summary(self, _summary):
            self.updated = True

    tray = SilentTray()
    suppression_reasons = []
    monkeypatch.setattr(
        app_container.queue,
        "enqueue_screening",
        lambda _screening_id: SimpleNamespace(alert_id="alert-silent"),
    )
    monkeypatch.setattr(
        app_container.queue,
        "suppress_alert",
        lambda _alert_id, reason: suppression_reasons.append(reason),
    )
    window.configure_tray(tray)
    window._screening_completed("screening-silent")

    assert not tray.shown
    assert tray.updated
    assert suppression_reasons == ["SILENT_PILOT"]


@pytest.mark.ui
def test_advisory_pilot_suppresses_alert_until_gate_is_ready(
    qtbot, app_container, monkeypatch
):
    app_container.settings.environment = AppEnvironment.ADVISORY_PILOT
    user = AuthenticatedUser(
        id="advisory-pharmacist",
        username="apoteker.advisory",
        display_name="Apoteker Advisory",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    assert window.advisory_blocked
    assert window.findChild(QLabel, "advisoryPilotBlockedBanner") is not None

    class AdvisoryTray:
        shown = False
        updated = False

        class TrayIcon:
            @staticmethod
            def isVisible():
                return False

        tray = TrayIcon()

        def show_screening_alert(self, _queued):
            self.shown = True
            return True

        def update_summary(self, _summary):
            self.updated = True

    tray = AdvisoryTray()
    suppression_reasons = []
    monkeypatch.setattr(
        app_container.queue,
        "enqueue_screening",
        lambda _screening_id: SimpleNamespace(alert_id="alert-blocked"),
    )
    monkeypatch.setattr(
        app_container.queue,
        "suppress_alert",
        lambda _alert_id, reason: suppression_reasons.append(reason),
    )
    window.configure_tray(tray)
    window._screening_completed("screening-advisory-blocked")

    assert not tray.shown
    assert tray.updated
    assert suppression_reasons == ["ADVISORY_GATE_BLOCKED"]


@pytest.mark.ui
@pytest.mark.parametrize(
    ("runtime_reason", "expected_suppression", "banner_text"),
    (
        ("NOT_ACTIVATED", "ADVISORY_NOT_ACTIVATED", "belum diaktifkan"),
        (
            "ACTIVATION_EXPIRED",
            "ADVISORY_AUTHORIZATION_EXPIRED",
            "masa berlaku aktivasi",
        ),
        (
            "SHIFT_EXPIRED",
            "ADVISORY_SHIFT_EXPIRED",
            "masa tugas pemilik shift",
        ),
        (
            "LEDGER_QUARANTINED",
            "ADVISORY_LEDGER_QUARANTINED",
            "integritas ledger sesi pilot",
        ),
        (
            "EMERGENCY_STOP",
            "ADVISORY_EMERGENCY_STOP",
            "emergency stop",
        ),
    ),
)
def test_advisory_pilot_suppression_reason_follows_runtime_control(
    qtbot,
    app_container,
    monkeypatch,
    runtime_reason,
    expected_suppression,
    banner_text,
):
    app_container.settings.environment = AppEnvironment.ADVISORY_PILOT
    monkeypatch.setattr(
        app_container.clinical_validation,
        "advisory_pilot_status",
        lambda: SimpleNamespace(active=False, reason=runtime_reason),
    )
    user = AuthenticatedUser(
        id="advisory-awaiting-activation",
        username="apoteker.awaiting.activation",
        display_name="Apoteker Menunggu Aktivasi",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    class AdvisoryTray:
        shown = False

        class TrayIcon:
            @staticmethod
            def isVisible():
                return False

        tray = TrayIcon()

        def show_screening_alert(self, _queued):
            self.shown = True
            return True

        def update_summary(self, _summary):
            return None

    tray = AdvisoryTray()
    suppression_reasons = []
    monkeypatch.setattr(
        app_container.queue,
        "enqueue_screening",
        lambda _screening_id: SimpleNamespace(alert_id="alert-not-activated"),
    )
    monkeypatch.setattr(
        app_container.queue,
        "suppress_alert",
        lambda _alert_id, reason: suppression_reasons.append(reason),
    )
    window.configure_tray(tray)
    window._screening_completed("screening-not-activated")

    assert not tray.shown
    assert window.advisory_blocked
    assert banner_text in window.advisory_banner.text().casefold()
    assert suppression_reasons == [expected_suppression]


@pytest.mark.ui
def test_advisory_pilot_rechecks_gate_before_each_alert(
    qtbot, app_container, monkeypatch
):
    app_container.settings.environment = AppEnvironment.ADVISORY_PILOT
    activation_states = iter(
        (
            SimpleNamespace(active=True, reason="ACTIVE"),
            SimpleNamespace(active=True, reason="ACTIVE"),
            SimpleNamespace(active=False, reason="GATE_NOT_READY"),
            RuntimeError("authorization unavailable"),
        )
    )

    def advisory_pilot_status():
        state = next(activation_states)
        if isinstance(state, Exception):
            raise state
        return state

    monkeypatch.setattr(
        app_container.clinical_validation,
        "advisory_pilot_status",
        advisory_pilot_status,
    )
    user = AuthenticatedUser(
        id="advisory-runtime-pharmacist",
        username="apoteker.advisory.runtime",
        display_name="Apoteker Advisory Runtime",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    class AdvisoryTray:
        shown = 0
        updated = 0

        class TrayIcon:
            @staticmethod
            def isVisible():
                return False

        tray = TrayIcon()

        def show_screening_alert(self, _queued):
            self.shown += 1
            return True

        def update_summary(self, _summary):
            self.updated += 1

    tray = AdvisoryTray()
    suppression_reasons = []
    monkeypatch.setattr(
        app_container.queue,
        "enqueue_screening",
        lambda screening_id: SimpleNamespace(alert_id=f"alert-{screening_id}"),
    )
    monkeypatch.setattr(
        app_container.queue,
        "suppress_alert",
        lambda _alert_id, reason: suppression_reasons.append(reason),
    )
    window.configure_tray(tray)

    window._screening_completed("screening-advisory-ready")
    assert tray.shown == 1
    assert not window.advisory_blocked

    window._screening_completed("screening-advisory-revoked")
    assert tray.shown == 1
    assert window.advisory_blocked

    window._screening_completed("screening-advisory-check-failed")
    assert tray.shown == 1
    assert tray.updated == 3
    assert window.advisory_blocked
    assert window.advisory_gate_check_failed
    assert window.findChild(QLabel, "advisoryPilotBlockedBanner") is not None
    assert suppression_reasons == [
        "ADVISORY_GATE_BLOCKED",
        "ADVISORY_GATE_UNAVAILABLE",
    ]


@pytest.mark.ui
def test_admin_has_backup_tab_and_manual_backup_feedback(qtbot, app_container):
    created = app_container.users.create_first_admin(
        username="backup.admin",
        display_name="Backup Admin",
        password="Backup#Aman2026",
    )
    user = AuthenticatedUser(
        id=created.id,
        username=created.username,
        display_name=created.display_name,
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    assert window.tabs.indexOf(window.backup_tab) >= 0
    qtbot.waitUntil(lambda: window.backup_tab._worker is None, timeout=5000)
    window.backup_tab.manual_button.click()
    assert "Membuat backup" in window.backup_tab.status_label.text()
    qtbot.waitUntil(lambda: window.backup_tab._worker is None, timeout=5000)
    assert "Backup selesai" in window.backup_tab.status_label.text()
    assert window.backup_tab.table.rowCount() >= 1


@pytest.mark.ui
def test_apoteker_import_tab_is_read_only(qtbot, app_container):
    user = AuthenticatedUser(
        id="test-user",
        username="apoteker",
        display_name="Apoteker Uji",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    tab = DrugImportTab(app_container, user)
    qtbot.addWidget(tab)

    assert not tab.preview_button.isEnabled()
    assert "tidak berwenang" in tab.status_label.text()


@pytest.mark.ui
def test_catalog_refresh_gives_visible_completion_feedback(qtbot, app_container):
    user = AuthenticatedUser(
        id="admin-feedback",
        username="admin.feedback",
        display_name="Admin Feedback",
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)

    assert window.change_admin_password_action.isVisible()
    assert window.change_admin_password_action.text() == 'Ganti Kata Sandi Admin'
    assert window.change_password_button.text() == 'Ganti Kata Sandi Admin'

    window.catalog_tab.refresh_button.click()

    qtbot.waitUntil(
        lambda: "berhasil diperbarui" in window.catalog_tab.refresh_feedback.text(),
        timeout=2000,
    )
    assert window.catalog_tab.refresh_button.isEnabled()
    assert window.catalog_tab.refresh_button.text() == "✓ Selesai"


@pytest.mark.ui
def test_drug_import_worker_always_stops_busy_indicator(qtbot, app_container):
    user = AuthenticatedUser(
        id="admin-import-feedback",
        username="admin.import.feedback",
        display_name="Admin Import Feedback",
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    tab = DrugImportTab(app_container, user)
    qtbot.addWidget(tab)

    tab._start_worker(
        lambda: "ok",
        lambda _result: tab.status_label.setText("Operasi selesai."),
        "Memproses data…",
        tab.preview_button,
    )

    qtbot.waitUntil(
        lambda: tab.status_label.text() == "Operasi selesai.", timeout=5000
    )
    assert tab.progress.isHidden()
    assert tab.status_label.text() == "Operasi selesai."
    assert tab.preview_button.text() == '1. Periksa Isi Berkas'
    assert tab.preview_button.isEnabled()


@pytest.mark.ui
def test_ddi_import_failure_always_stops_busy_indicator(qtbot, app_container):
    user = AuthenticatedUser(
        id="admin-ddi-feedback",
        username="admin.ddi.feedback",
        display_name="Admin DDI Feedback",
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    tab = DdiImportTab(app_container, user)
    qtbot.addWidget(tab)

    assert tab.template_button.text() == 'Unduh Format Impor DDI'
    assert "kode obat Khanza" in tab.template_button.toolTip()
    assert tab.export_button.text() == 'Ekspor Data Interaksi Lengkap'
    assert tab.export_button.isEnabled()

    def fail() -> object:
        raise ValueError("data uji tidak valid")

    tab._start(
        fail,
        lambda _result: None,
        "Memproses DDI…",
        tab.preview_button,
    )

    qtbot.waitUntil(
        lambda: "Operasi gagal" in tab.status_label.text(), timeout=5000
    )
    assert tab.progress.isHidden()
    assert "Operasi gagal" in tab.status_label.text()
    assert tab.preview_button.text() == '1. Periksa Isi Berkas'
    assert tab.preview_button.isEnabled()


@pytest.mark.ui
def test_apoteker_ddi_import_is_read_only(qtbot, app_container):
    user = AuthenticatedUser(
        id="test-user",
        username="apoteker",
        display_name="Apoteker Uji",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    tab = DdiImportTab(app_container, user)
    qtbot.addWidget(tab)

    assert not tab.preview_button.isEnabled()
    assert not tab.export_button.isEnabled()
    assert "tidak berwenang" in tab.status_label.text()


@pytest.mark.ui
def test_knowledge_tab_has_no_workflow_without_version(qtbot, app_container):
    user = AuthenticatedUser(
        id="test-user",
        username="viewer",
        display_name="Viewer",
        roles=frozenset({"VIEWER"}),
        must_change_password=False,
    )
    tab = KnowledgeBaseTab(app_container, user)
    qtbot.addWidget(tab)

    assert tab.summary_label.text().startswith("Belum ada")
    assert not tab.publish_button.isEnabled()
    assert not tab.input_button.isEnabled()
    assert tab.rule_filter.findData("UNRESOLVED_HOLD") >= 0
    assert tab.rule_filter.findData("RESOLVED_HOLD") >= 0


@pytest.mark.ui
def test_ddi_rule_detail_dialog_shows_clinical_review_fields(qtbot):
    detail = DdiRuleDetail(
        id="rule-1",
        pair_key="obat a || obat b",
        interaction_status="INTERACTION_FOUND",
        severity_code="SERIOUS",
        severity_label="Serious",
        app_severity="HIGH_RISK",
        clinical_effect="Efek klinis uji",
        mechanism="Mekanisme uji",
        recommendation="Rekomendasi uji",
        monitoring="Monitoring uji",
        population_risk="Populasi uji",
        source_name="Sumber uji",
        source_reference="Referensi uji",
        source_accessed_at="2026-08-04",
        source_evidence_count=2,
        source_validation_status="VALID",
        source_final_code="FINAL",
        clinical_review_required=True,
        clinical_review_resolved=False,
        validated_by_name="",
        validated_at="",
        notes="Catatan uji",
    )
    dialog = DdiRuleDetailDialog(detail, review_mode=True)
    qtbot.addWidget(dialog)

    browser = dialog.findChild(QTextBrowser, "ddiRuleDetail")
    assert browser is not None
    text = browser.toPlainText()
    assert "background: #FFFFFF" in browser.styleSheet()
    assert "color: #111827" in browser.styleSheet()
    close_button = dialog.findChild(QPushButton, "closeDdiRuleDetail")
    assert close_button is not None
    assert close_button.text() == "Tutup"
    assert "Efek klinis uji" in text
    assert "Mekanisme uji" in text
    assert "Rekomendasi uji" in text
    assert "WAJIB — BELUM SELESAI" in text


@pytest.mark.ui
def test_long_ddi_input_dialog_keeps_actions_visible(qtbot, app_container):
    user = AuthenticatedUser(
        id="admin-ddi-dialog",
        username="admin.ddi.dialog",
        display_name="Admin DDI Dialog",
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    dialog = DdiInputDialog(app_container, user, "version-test")
    qtbot.addWidget(dialog)
    dialog.resize(700, 480)
    dialog.show()
    qtbot.wait(20)

    assert dialog.form_scroll.verticalScrollBar().maximum() > 0
    assert dialog.save_button.isVisible()
    assert dialog.cancel_button.isVisible()
    save_bottom = dialog.save_button.mapTo(
        dialog, QPoint(0, dialog.save_button.height())
    ).y()
    assert save_bottom <= dialog.contentsRect().bottom()


@pytest.mark.ui
def test_long_intervention_dialog_keeps_actions_visible(
    qtbot, app_container
):
    user = AuthenticatedUser(
        id="pharmacist-dialog",
        username="pharmacist.dialog",
        display_name="Apoteker Dialog",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    item = QueueItem(
        id="queue-dialog",
        screening_id=None,
        no_resep="RX-DIALOG",
        revision_number=1,
        patient_label="Pasien Uji",
        service_unit="DEPO FARMASI",
        processing_status="COMPLETED",
        review_status="NEW",
        risk_status="CRITICAL",
        completeness_status="COMPLETE",
        overall_status="CRITICAL",
        alert_level="CRITICAL",
        priority=100,
        hold_recommended=True,
        attempts=1,
        error_message="",
        is_mock=True,
        detected_at="2026-08-04T12:00:00",
    )
    dialog = InterventionDialog(
        app_container,
        user,
        QueueDetail(item=item, pairs=(), issues=()),
    )
    qtbot.addWidget(dialog)
    dialog.resize(650, 480)
    dialog.show()
    qtbot.wait(20)

    assert dialog.save_button.isVisible()
    assert dialog.cancel_button.isVisible()
    save_bottom = dialog.save_button.mapTo(
        dialog, QPoint(0, dialog.save_button.height())
    ).y()
    assert save_bottom <= dialog.contentsRect().bottom()


@pytest.mark.ui
def test_mock_simulator_is_clearly_labelled(qtbot, app_container):
    user = AuthenticatedUser(
        id="test-user",
        username="apoteker",
        display_name="Apoteker Uji",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    tab = ScreeningSimulatorTab(app_container, user)
    qtbot.addWidget(tab)

    assert "MODE MOCK" in tab.findChild(
        type(tab.status_label), "mockBanner"
    ).text()
    assert tab.simulate_button.isEnabled()
    assert tab.scenario_combo.count() >= 5
    assert not tab.result_table.verticalHeader().isVisible()


@pytest.mark.ui
def test_change_password_dialog_rejects_mismatched_confirmation(
    qtbot, app_container
):
    user = AuthenticatedUser(
        id="test-user",
        username="apoteker",
        display_name="Apoteker Uji",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    dialog = ChangePasswordDialog(app_container, user)
    qtbot.addWidget(dialog)
    dialog.current_password.setText('Kata sandi saat ini')
    dialog.new_password.setText("Password baru yang aman!")
    dialog.confirm_password.setText("Berbeda dari password baru")

    dialog._submit()

    assert "tidak sama" in dialog.message.text()


@pytest.mark.ui
def test_login_can_enter_workstation_mode_without_password(
    qtbot, app_container
):
    app_container.users.create_first_admin(
        username="admin.mode",
        display_name="Admin Mode",
        password="Frasa aman admin mode!",
    )
    app_container.settings.allow_workstation_mode = True
    app_container.settings.pharmacy_care_setting = 'RALAN'
    dialog = LoginDialog(app_container)
    qtbot.addWidget(dialog)

    dialog._enter_workstation_mode()

    assert dialog.authenticated_user is not None
    assert dialog.authenticated_user.username == "mode.farmasi"
    assert app_container.settings.pharmacy_care_setting == 'RALAN'
    assert dialog.result() == dialog.DialogCode.Accepted


@pytest.mark.ui
def test_workstation_queue_panel_cannot_record_review(qtbot, app_container):
    user = AuthenticatedUser(
        id="workstation",
        username="mode.farmasi",
        display_name="Mode Farmasi",
        roles=frozenset({"APOTEKER"}),
        must_change_password=False,
    )
    panel = QueuePanel(app_container, user)
    qtbot.addWidget(panel)

    assert panel.summary_label.text().startswith("Total 0")
    assert panel.mock_critical_button.isVisibleTo(panel)
    assert not panel.review_button.isEnabled()
    assert not panel.retry_button.isEnabled()
    assert not panel.intervention_button.isEnabled()


@pytest.mark.ui
def test_critical_queue_allows_review_without_forcing_intervention(
    qtbot, app_container
):
    user = AuthenticatedUser(
        id="admin-critical",
        username="admin.critical",
        display_name="Admin Critical",
        roles=frozenset({"SUPER_ADMIN"}),
        must_change_password=False,
    )
    panel = QueuePanel(app_container, user)
    qtbot.addWidget(panel)
    item = QueueItem(
        id="queue-critical",
        screening_id=None,
        no_resep="RX-CRITICAL",
        revision_number=1,
        patient_label="Pasien Uji",
        service_unit="DEPO FARMASI",
        processing_status="COMPLETED",
        review_status="NEW",
        risk_status="CRITICAL",
        completeness_status="COMPLETE",
        overall_status="CRITICAL",
        alert_level="CRITICAL",
        priority=100,
        hold_recommended=True,
        attempts=1,
        error_message="",
        is_mock=True,
        detected_at="2026-08-04T12:00:00",
    )

    panel._render_detail(QueueDetail(item=item, pairs=(), issues=()))

    assert panel.intervention_button.isEnabled()
    assert panel.review_button.isEnabled()
    assert "tidak membuat intervensi" in panel.review_button.toolTip().casefold()

    panel._render_rows([item])
    assert panel.table.columnCount() == 7
    assert 'Kelengkapan' not in [panel.table.horizontalHeaderItem(i).text() for i in range(7)]
    assert 'Mode' not in [panel.table.horizontalHeaderItem(i).text() for i in range(7)]
    assert 'lengkap' not in panel.summary_label.text().casefold()
    assert 'lengkap' not in panel.detail_label.text().casefold()
    from dataclasses import replace
    from emss.services.queue import QueueIssueDetail
    uncertain = replace(item, risk_status='SAFE', completeness_status='INCOMPLETE', overall_status='INCOMPLETE')
    panel._render_rows([uncertain])
    assert panel.table.item(0, 4).text() == 'Belum dapat disimpulkan'
    issue = QueueIssueDetail('DATA_INCOMPLETE', '', '', 'Komposisi akhir sumber belum terverifikasi.')
    panel._render_detail(QueueDetail(item=uncertain, pairs=(), issues=(issue,)))
    assert 'Belum dapat disimpulkan' in panel.detail_label.text()
    assert panel.detail_table.item(0, 3).text() == issue.message


@pytest.mark.ui
def test_fast_idle_poll_keeps_selected_recipe_and_throttles_health(qtbot, app_container, monkeypatch):
    from emss.services.khanza_polling import PollingResult
    user = AuthenticatedUser('ui-idle','ui.idle','Uji UI',frozenset({'APOTEKER'}),False)
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)
    refreshed, checked = [], []
    monkeypatch.setattr(window.queue_tab, 'refresh', lambda: refreshed.append(True))
    monkeypatch.setattr(window, 'refresh_health', lambda: checked.append(True))
    window._polling_completed(PollingResult(status='SUCCESS'))
    window._polling_completed(PollingResult(status='SUCCESS'))
    assert not refreshed and len(checked) == 1
    window._polling_completed(PollingResult(status='PARTIAL', failed=1))
    assert len(refreshed) == 1 and len(checked) == 2
    window.outbox_timer.stop()


@pytest.mark.ui
def test_single_instance_second_guard_requests_activation(qtbot, tmp_path):
    first = SingleInstanceGuard(tmp_path / "single-instance")
    second = SingleInstanceGuard(tmp_path / "single-instance")
    activated: list[bool] = []
    first.activation_requested.connect(lambda: activated.append(True))
    try:
        assert first.acquire()
        assert not second.acquire()
        qtbot.waitUntil(lambda: bool(activated), timeout=2000)
    finally:
        second.close()
        first.close()


@pytest.mark.ui
def test_system_tray_has_operational_menu_and_summary(qtbot):
    controller = SystemTrayController()
    qtbot.addWidget(controller.tray.contextMenu())
    controller.update_summary(
        QueueSummary(
            total=5,
            new=2,
            high_risk=1,
            critical=1,
            incomplete=2,
            dead_letter=0,
        )
    )

    actions = [
        action.text()
        for action in controller.tray.contextMenu().actions()
        if not action.isSeparator()
    ]
    assert actions == [
        'Buka E-MAS Farmasi',
        "Sembunyikan Panel",
        'Keluar dari E-MAS Farmasi',
    ]
    assert "CRITICAL: 1" in controller.tray.toolTip()
    assert not controller.tray.icon().isNull()
    assert "color: #EAF8FF" in controller.tray.contextMenu().styleSheet()


@pytest.mark.ui
def test_official_application_icons_are_loadable():
    assert not application_icon().isNull()
    assert not application_icon(tray=True).isNull()
    available = application_icon().availableSizes()
    assert QSize(16, 16) in available
    assert QSize(32, 32) in available
    assert QSize(256, 256) in available


@pytest.mark.ui
def test_fullscreen_alert_is_topmost_nonactivating_and_readable(qtbot):
    popup = FullscreenAlertPopup()
    qtbot.addWidget(popup)

    popup.show_alert(
        "Risiko kritis",
        "HOLD RECOMMENDED — lakukan review sebelum obat disiapkan.",
        "CRITICAL",
        5000,
    )
    qtbot.wait(20)

    assert popup.isVisible()
    assert popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert popup.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert popup.title.text() == "Risiko kritis"
    assert "HOLD RECOMMENDED" in popup.message.text()
    assert "background: #FFF1F2" in popup.card.styleSheet()


@pytest.mark.ui
def test_release_gui_smoke_opens_actual_login_in_isolated_database(qtbot):
    from emss.release.gui_smoke import run_gui_smoke
    payload = run_gui_smoke()
    assert payload["state"] == "READY"
    assert payload["login_visible"] is True
    assert payload["schema_revision"] == "0029_kfa_identity"

