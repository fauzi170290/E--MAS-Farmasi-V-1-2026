from dataclasses import replace
import pytest
from emss.services.authentication import AuthenticatedUser
from emss.services.queue import QueueItem, QueueDetail, QueuePairDetail, QueueIssueDetail
from emss.ui.queue import QueuePanel
from emss.ui.validation import ClinicalValidationPanel
from emss.ui.action_identity import ActionIdentityDialog


def item(key='q1'):
    return QueueItem(id=key, screening_id='screen-'+key, no_resep='RX-'+key, revision_number=2,
        patient_label='Pasien Sintetis', service_unit='Poli Uji', processing_status='COMPLETED',
        review_status='NEW', risk_status='CRITICAL', completeness_status='UNMAPPED', overall_status='CRITICAL',
        alert_level='CRITICAL', priority=300, hold_recommended=True, attempts=1, error_message='',
        is_mock=True, detected_at='2026-08-31T01:00:00', care_setting='RALAN', source_adapter='mysql')


def mode():
    return AuthenticatedUser('mode-id', 'mode.farmasi', 'Mode Farmasi', frozenset({'APOTEKER'}), False)


def test_mode_review_requires_explicit_actor_and_does_not_change_session(qtbot, app_container, monkeypatch):
    panel = QueuePanel(app_container, mode())
    qtbot.addWidget(panel)
    panel.current_item_id = 'q1'
    panel._render_detail(QueueDetail(item(), (), ()))
    assert panel.review_button.isEnabled() and panel.retry_button.isEnabled()
    calls = []
    monkeypatch.setattr(app_container.queue, 'acknowledge', lambda *args: calls.append(args))
    monkeypatch.setattr(panel, '_action_actor', lambda roles: None)
    panel._acknowledge()
    assert calls == []
    actor = AuthenticatedUser('named-id', 'petugas', 'Petugas Uji', frozenset({'APOTEKER'}), False)
    monkeypatch.setattr(panel, '_action_actor', lambda roles: actor)
    panel._acknowledge()
    assert calls == [('q1', 'named-id')]
    assert panel.user.username == 'mode.farmasi'


def test_refresh_keeps_identity_and_renders_all_categories_and_mapping_separately(qtbot, app_container, monkeypatch):
    panel = QueuePanel(app_container, mode())
    qtbot.addWidget(panel)
    rows = [item('q1'), item('q2')]
    details = {row.id: QueueDetail(row, (), ()) for row in rows}
    monkeypatch.setattr(app_container.queue, 'get_detail', lambda key: details[key])
    panel._render_rows(rows)
    panel.focus_item('q1')
    panel._render_rows(list(reversed(rows)))
    assert panel.current_item_id == 'q1'
    assert panel.current_detail.item.id == 'q1'
    pairs = tuple(QueuePairDetail('a || '+str(i), 'INTERACTION_FOUND', code, 'Catatan')
        for i, code in enumerate(['CONTRAINDICATED','SERIOUS','SIGNIFICANT','MINOR']))
    issue = QueueIssueDetail('DRUG_UNMAPPED','000004629','KELENGKAPAN','Belum dipetakan','WARFARIN 1 MG')
    panel._render_detail(QueueDetail(rows[0], pairs, (issue,)))
    assert panel.detail_table.rowCount() == 4
    assert [panel.detail_table.item(i,2).text() for i in range(4)] == ['Kontraindikasi','Mayor','Signifikan','Minor']
    assert panel.detail_table.item(0,2).font().bold() and panel.detail_table.item(1,2).font().bold()
    assert not panel.detail_table.item(2,2).font().bold()
    assert ' vs ' in panel.detail_table.item(0,1).text()
    assert panel.mapping_table.rowCount() == 1
    assert panel.mapping_table.item(0,1).text() == 'WARFARIN 1 MG'
    panel._render_rows([replace(rows[0], review_status='REVIEWED')])
    assert panel.table.item(0,4).foreground().color().name() == '#b91c1c'
    panel.table.clearSelection()
    assert panel.current_item_id is None and panel.current_detail is None
    assert not panel.review_button.isEnabled() and not panel.retry_button.isEnabled()


def test_queue_detail_marks_history_and_pending_cross_prescription_context(qtbot, app_container):
    panel = QueuePanel(app_container, mode())
    qtbot.addWidget(panel)
    pending = replace(item(), is_effective=False, context_pending=True)
    panel._render_detail(QueueDetail(pending, (), ()))
    assert 'riwayat revisi' in panel.detail_label.text().casefold()
    assert 'evaluasi ulang konteks lintas resep' in panel.detail_label.text().casefold()


def test_history_view_defaults_to_today_but_keeps_explicit_all_data_option(qtbot, app_container):
    panel = QueuePanel(app_container, mode())
    qtbot.addWidget(panel)

    panel.set_view('history')

    assert panel.date_filter.currentData() == 'TODAY'
    assert panel.date_filter.findData('ALL') >= 0
    assert 'hasil efektif hari ini' in panel.summary_label.text().casefold()


def test_uat_cannot_be_constructed_indirectly_for_mode(app_container):
    with pytest.raises(ValueError, match='Mode Farmasi'):
        ClinicalValidationPanel(app_container, mode())


def test_action_authentication_rejects_nonclinical_account_and_clears_password(qtbot, app_container, monkeypatch):
    dialog = ActionIdentityDialog(app_container, {'APOTEKER'})
    qtbot.addWidget(dialog)
    dialog.password.setText('not-real')
    monkeypatch.setattr(app_container.authentication, 'authenticate', lambda *_:
        AuthenticatedUser('it','it.user','IT',frozenset({'IT_ADMIN'}),False))
    dialog._submit()
    assert dialog.actor is None and not dialog.password.text()
    assert 'tidak berwenang' in dialog.message.text()
