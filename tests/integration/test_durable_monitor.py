from dataclasses import replace
from datetime import timedelta
import json

import pytest
from sqlalchemy import select, func, text
from alembic import command

from test_screening_engine import _seed, _admin
from emss.integrations.khanza import KhanzaScopeError, MockKhanzaAdapter, PrescriptionSnapshot, PrescriptionHeader, PrescriptionItem
from emss.services.khanza_polling import KhanzaPollingService
from emss.database.monitoring_models import MonitorEvent, MonitorInbox, MonitorCheckpoint
from emss.database.integration_models import IntegrationState
from emss.database.screening_models import Screening
from emss.database.knowledge_models import DdiRule
from emss.integrations.khanza.domain import aware_utc
from emss.utils.time import utc_now


class SyntheticCommittedAdapter(MockKhanzaAdapter):
    # Synthetic source, REAL screening path: inactive rules must stay inactive.
    code = 'synthetic-committed'


def monitor_fixture(container, **seed_options):
    actor = _admin(container)
    version, codes = _seed(container, actor.id, **seed_options)
    adapter = SyntheticCommittedAdapter()
    clock = [utc_now()]
    adapter.source_time = lambda: clock[0]
    container.settings.khanza_stability_interval_seconds = 2
    container.settings.khanza_poll_interval_seconds = 3
    service = KhanzaPollingService(container.database, container.settings, adapter, container.screening, container.queue)
    service.monitor.clock = lambda: clock[0]
    snapshot = PrescriptionSnapshot(PrescriptionHeader(no_resep='RX-SYNTH-001', no_rawat='VISIT-SYNTH',
        patient_id='PATIENT-SYNTH', patient_name='PASIEN SINTETIS', service_unit='UNIT UJI', status='DIPROSES_FARMASI', care_setting='RALAN',
        changed_at=clock[0], validation_token='validation-1', item_basis='FINAL', composition_complete=True),
        tuple(PrescriptionItem(str(i), code, 'Obat Sintetis', '1') for i, code in enumerate(codes[:2])), (), '')
    adapter.add_snapshot(snapshot)
    return actor, service, adapter, clock, snapshot


def finish(actor, service, clock, callback=None):
    first = service.monitor.cycle(actor.id, on_result=callback)
    if first.processed or first.failed or first.incomplete:
        return first
    clock[0] += timedelta(seconds=3)
    return service.monitor.cycle(actor.id, on_result=callback)


def test_settling_deadline_wakes_before_ten_second_poll_without_weakening_stability(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    adapter.add_snapshot(replace(snap, header=replace(
        snap.header, status='DIRESEPKAN', validation_token='', item_basis='PRESCRIBED'
    )))
    app_container.settings.khanza_poll_interval_seconds = 10
    assert service.monitor.next_poll_delay_ms() == 10000
    assert service.monitor.cycle(actor.id).processed == 0
    assert 2000 <= service.monitor.next_poll_delay_ms() <= 2001
    clock[0] += timedelta(seconds=1)
    assert service.monitor.cycle(actor.id).processed == 0
    assert 1000 <= service.monitor.next_poll_delay_ms() <= 1001
    clock[0] += timedelta(seconds=1.01)
    assert service.monitor.cycle(actor.id).processed == 1
    assert service.monitor.next_poll_delay_ms() == 10000
    adapter.set_connected(False)
    assert service.monitor.cycle(actor.id).status == 'DISCONNECTED'
    assert service.monitor.next_poll_delay_ms() == 10000
    assert service.monitor.cycle(actor.id).status == 'BACKOFF'


def test_committed_final_is_processed_in_first_cycle_and_not_reread_each_second(app_container):
    actor, service, _adapter, clock, _snap = monitor_fixture(app_container)
    first = service.monitor.cycle(actor.id)
    assert first.processed == 1
    clock[0] += timedelta(seconds=3)
    second = service.monitor.cycle(actor.id)
    assert second.processed == 0 and second.detected == 0
    with app_container.database.session() as session:
        row = session.get(MonitorInbox, (service.adapter_code, 'RX-SYNTH-001'))
        assert row.state == 'COMPLETED'
        assert aware_utc(row.next_attempt_at) > clock[0] + timedelta(hours=23)


def test_fast_poll_uses_lightweight_health_check_after_contract_validation(app_container):
    actor, service, adapter, clock, _snap = monitor_fixture(app_container)
    calls = {'contract': 0, 'health': 0}
    original_contract = adapter.test_connection

    def contract_check():
        calls['contract'] += 1
        original_contract()

    def health_check():
        calls['health'] += 1
        original_contract()

    adapter.test_connection = contract_check
    adapter.check_health = health_check

    service.monitor.cycle(actor.id)
    clock[0] += timedelta(seconds=3)
    service.monitor.cycle(actor.id)

    assert calls == {'contract': 1, 'health': 1}
    service.monitor._last_contract_check -= 301
    clock[0] += timedelta(seconds=3)
    service.monitor.cycle(actor.id)
    assert calls == {'contract': 2, 'health': 1}


def test_scope_diagnostic_is_preserved_in_durable_connection_status(app_container):
    actor, service, adapter, _clock, _snap = monitor_fixture(app_container)
    message = ('View Khanza harus menyediakan asal_layanan (ralan/ranap). '
               'Minta IT memasang pembaruan view integrasi.')

    def reject_old_view():
        raise KhanzaScopeError(message)

    adapter.test_connection = reject_old_view
    result = service.monitor.cycle(actor.id)

    assert result.status == 'SCOPE_NOT_READY'
    assert result.message == message
    assert service.status().last_error == message


@pytest.mark.ui
@pytest.mark.parametrize('arrival_delay_ms', [50, 450, 900])
def test_fast_poll_validation_to_popup_latency_and_no_duplicate(app_container, qtbot, arrival_delay_ms):
    from time import perf_counter
    import os
    from pathlib import Path
    from emss.ui.integration.panel import KhanzaIntegrationPanel
    from emss.ui.tray.controller import SystemTrayController
    from emss.services.authentication import AuthenticatedUser
    actor, service, adapter, clock, snap = monitor_fixture(app_container,
        severity_code='CONTRAINDICATED', severity_rank=4, app_severity='CRITICAL')
    # Keep the actual worker, durable queue, and Qt popup; only source is synthetic.
    adapter.add_snapshot(replace(snap, header=replace(snap.header, status='DIRESEPKAN', validation_token='')))
    service.monitor.clock = utc_now
    adapter.source_time = utc_now
    app_container.khanza_adapter, app_container.khanza_polling = adapter, service
    app_container.settings.khanza_poll_interval_seconds = 1
    app_container.settings.khanza_polling_enabled = True
    app_container.settings.khanza_internal_polling_consent = True
    user = AuthenticatedUser(actor.id, actor.username, actor.display_name, frozenset({'SUPER_ADMIN'}), False)
    panel = KhanzaIntegrationPanel(app_container, user)
    qtbot.addWidget(panel)
    tray = SystemTrayController()
    qtbot.addWidget(tray.fullscreen_alert)
    displayed = []
    tray.alert_displayed.connect(lambda alert_id: (app_container.queue.mark_alert_shown(alert_id), displayed.append(perf_counter())))
    panel.screening_ready.connect(lambda screening_id: tray.show_screening_alert(app_container.queue.enqueue_screening(screening_id)))
    try:
        qtbot.wait(arrival_delay_ms)
        committed = perf_counter()
        adapter.add_snapshot(snap)
        qtbot.waitUntil(lambda: bool(displayed), timeout=6000)
        elapsed = displayed[0] - committed
        # A committed validation skips draft stabilization and is re-read promptly.
        assert 0.1 <= elapsed < 3
        assert tray.fullscreen_alert.title.text() == 'KONTRAINDIKASI'
        assert tray.fullscreen_alert.isVisible()
        qtbot.wait(1300)
        assert len(displayed) == 1
        path = os.environ.get('EMAS_LATENCY_REPORT')
        if path:
            with Path(path).open('a', encoding='utf-8') as f:
                f.write(json.dumps({'source':'synthetic', 'arrival_delay_ms':arrival_delay_ms,
                    'commit_to_popup_seconds':elapsed, 'speaker_verified':False})+'\n')
    finally:
        panel.auto_button.setChecked(False)
        qtbot.waitUntil(lambda: not panel._busy, timeout=10000)
        assert not panel.timer.isActive()
        tray.hide()


@pytest.mark.parametrize('status,severity,rank,risk,category', [
    ('INTERACTION_FOUND', 'CONTRAINDICATED', 4, 'CRITICAL', 'contraindicated'),
    ('INTERACTION_FOUND', 'SERIOUS', 3, 'HIGH_RISK', 'major'),
    ('INTERACTION_FOUND', 'SIGNIFICANT', 2, 'REVIEW', 'significant-review'),
    ('INTERACTION_FOUND', 'MINOR', 1, 'INFO', ''),
    ('ASSESSED_NO_INTERACTION', 'NONE', 0, None, 'screening-clear'),
])
def test_monitor_real_screening_classification_and_validation_popup(app_container, status, severity, rank, risk, category):
    actor, service, adapter, clock, snapshot = monitor_fixture(app_container,
        rule_status=status, severity_code=severity, severity_rank=rank, app_severity=risk)
    emitted = []
    result = finish(actor, service, clock, emitted.append)
    assert result.processed == 1 and emitted == list(result.screening_ids)
    queued = app_container.queue.enqueue_screening(emitted[0])
    assert queued.notify and queued.audio_category == category
    assert queued.item.is_mock is False
    clock[0] += timedelta(seconds=3)
    assert service.monitor.cycle(actor.id).processed == 0
    assert len(app_container.queue.list_items()) == 1


def test_validation_same_second_cancel_revalidate_and_restart_preserve_events(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    adapter.add_snapshot(replace(snap, header=replace(snap.header, status='DIRESEPKAN', item_basis='PRESCRIBED', validation_token='')))
    assert finish(actor, service, clock).processed == 1
    for status, token in [('DIPROSES_FARMASI', 'v1'), ('DIRESEPKAN', ''), ('DIPROSES_FARMASI', 'v2')]:
        adapter.add_snapshot(replace(snap, header=replace(snap.header, status=status, validation_token=token)))
        clock[0] += timedelta(seconds=61)
        assert finish(actor, service, clock).processed == 1
    restarted = KhanzaPollingService(app_container.database, app_container.settings, adapter, app_container.screening, app_container.queue)
    restarted.monitor.clock = lambda: clock[0]
    clock[0] += timedelta(seconds=3)
    assert restarted.monitor.cycle(actor.id).processed == 0
    with app_container.database.session() as s:
        events = s.scalars(select(MonitorEvent).order_by(MonitorEvent.sequence)).all()
        assert [e.event_type for e in events] == ['NEW', 'VALIDATION', 'VALIDATION_CANCELLED', 'VALIDATION']
        assert len({e.screening_id for e in events}) == 4


def test_recent_bypasses_22000_history_without_dropping_cursor_or_failures(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    for i in range(22000):
        adapter.add_snapshot(replace(snap, header=replace(snap.header, no_resep=f'H-{i:06d}',
            changed_at=clock[0] - timedelta(days=900)), regular_items=(), compounded_items=()))
    result = finish(actor, service, clock)
    assert result.processed == 1
    assert result.incomplete == 0
    with app_container.database.session() as s:
        state = s.get(IntegrationState, service.adapter_code)
        assert state.cursor_no_resep == snap.header.no_resep
        assert s.scalar(select(func.count()).select_from(MonitorInbox)) == 1
        assert s.scalar(select(func.count()).select_from(MonitorInbox).where(MonitorInbox.state == 'INCOMPLETE')) == 0


def test_stale_cursor_fast_forwards_without_adopting_old_pages(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    old_time = clock[0] - timedelta(days=900)
    adapter.add_snapshot(replace(snap, header=replace(
        snap.header, no_resep='OLD-001', changed_at=old_time
    )))
    adapter.add_snapshot(replace(snap, header=replace(
        snap.header, no_resep='OLD-002', changed_at=old_time + timedelta(seconds=1)
    )))
    with app_container.database.session() as session:
        state = session.get(IntegrationState, service.adapter_code)
        state.cursor_changed_at = old_time - timedelta(seconds=1)
        state.cursor_no_resep = 'BEFORE-OLD'
        session.commit()

    service.monitor._discover()

    with app_container.database.session() as session:
        recent = session.get(MonitorInbox, (service.adapter_code, snap.header.no_resep))
        assert session.get(MonitorInbox, (service.adapter_code, 'OLD-001')) is None
        assert (recent.lane, recent.priority) == ('RECENT', 70)
        state = session.get(IntegrationState, service.adapter_code)
        assert state.cursor_no_resep == snap.header.no_resep


def test_existing_historical_inbox_is_deferred_and_same_timestamp_change_is_caught(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    old_time = clock[0] - timedelta(days=900)
    with app_container.database.session() as session:
        session.add(MonitorInbox(adapter_code=service.adapter_code, no_resep='LEGACY-HISTORY',
            lane='HISTORY', priority=90, state='PENDING', next_attempt_at=clock[0]))
        session.add(MonitorInbox(adapter_code=service.adapter_code, no_resep=snap.header.no_resep,
            lane='HISTORY', priority=90, state='PENDING', next_attempt_at=clock[0]))
        state = session.get(IntegrationState, service.adapter_code)
        state.cursor_changed_at = old_time
        state.cursor_no_resep = 'LEGACY-CURSOR'
        session.commit()

    assert service.monitor.cycle(actor.id).processed == 1
    with app_container.database.session() as session:
        deferred = session.get(MonitorInbox, (service.adapter_code, 'LEGACY-HISTORY'))
        assert (deferred.lane, deferred.state, deferred.priority) == (
            'DEFERRED_HISTORY', 'DEFERRED_HISTORY', 0
        )
        watermark = session.get(IntegrationState, service.adapter_code)
        assert watermark.cursor_no_resep == snap.header.no_resep
        assert session.get(MonitorInbox, (service.adapter_code, snap.header.no_resep)).lane == 'RECENT'

    same_time = replace(snap, header=replace(snap.header, no_resep='ZZ-SAME-TIME'))
    adapter.add_snapshot(same_time)
    clock[0] += timedelta(seconds=3)
    result = service.monitor.cycle(actor.id)
    assert result.processed == 1
    with app_container.database.session() as session:
        assert session.get(MonitorInbox, (service.adapter_code, 'LEGACY-HISTORY')).state == 'DEFERRED_HISTORY'
        assert session.get(IntegrationState, service.adapter_code).cursor_no_resep == 'ZZ-SAME-TIME'


def test_revision_without_timestamp_backdated_racikan_and_substitution(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    finish(actor, service, clock)
    changed = replace(snap, regular_items=snap.regular_items[:1],
        compounded_items=(replace(snap.regular_items[1], source_item_key='C:1:B', compound_group='1', quantity='2'),),
        header=replace(snap.header, changed_at=snap.header.changed_at - timedelta(days=1000)))
    adapter.add_snapshot(changed)
    clock[0] += timedelta(seconds=301)
    assert finish(actor, service, clock).processed == 1
    with app_container.database.session() as s:
        event = s.scalar(select(MonitorEvent).order_by(MonitorEvent.sequence.desc()))
        assert json.loads(event.snapshot_json)['compounded_items'][0]['quantity'] == '2'


@pytest.mark.parametrize('defect', ['unmapped', 'inactive_rule', 'unverified', 'empty', 'draft'])
def test_monitor_never_confirms_incomplete_or_unavailable(app_container, defect):
    opts = dict(rule_status='ASSESSED_NO_INTERACTION', severity_code='NONE', severity_rank=0, app_severity=None)
    if defect == 'unmapped': opts['approved_mapping'] = False
    if defect == 'draft': opts['version_status'] = 'DRAFT'
    actor, service, adapter, clock, snap = monitor_fixture(app_container, **opts)
    if defect == 'unverified':
        adapter.add_snapshot(replace(snap, header=replace(snap.header, composition_complete=False)))
    elif defect == 'empty':
        adapter.add_snapshot(replace(snap, regular_items=()))
    elif defect == 'inactive_rule':
        with app_container.database.session() as s:
            s.scalar(select(DdiRule)).is_enabled = False
            s.commit()
    result = finish(actor, service, clock)
    for screening_id in result.screening_ids:
        queued = app_container.queue.enqueue_screening(screening_id)
        assert queued.audio_category != 'screening-clear'
        assert queued.item.completeness_status != 'COMPLETE'
    if defect == 'draft':
        assert result.failed == 1 and service.monitor.summary()['states']['RETRY'] == 1
    if defect == 'empty': assert result.incomplete == 1


def test_disconnect_retry_and_callback_failure_leave_outbox(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    adapter.set_connected(False)
    assert service.monitor.cycle(actor.id).status == 'DISCONNECTED'
    assert service.monitor.cycle(actor.id).status == 'BACKOFF'
    adapter.set_connected(True)
    clock[0] += timedelta(seconds=6)
    def broken_callback(_): raise RuntimeError('synthetic transport failure')
    result = finish(actor, service, clock, broken_callback)
    assert result.processed == 1
    assert app_container.queue.pending_screening_ids() == result.screening_ids
    service.monitor.request_retry(snap.header.no_resep, actor.id, 'Uji retry sintetis')
    clock[0] += timedelta(seconds=61)
    assert finish(actor, service, clock).processed == 1
    assert len(app_container.queue.list_items()) == 1  # Same source event, no duplicate clinical result.


def test_monitor_migration_downgrade_reupgrade_preserves_observations(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    finish(actor, service, clock)
    with app_container.database.session() as s:
        original = s.execute(text('SELECT id, fingerprint, snapshot_json FROM monitor_event')).all()
    command.downgrade(app_container.database._alembic_config(), '0026_bundled_ddi_master')
    app_container.database.migrate()
    with app_container.database.session() as s:
        assert s.execute(text('SELECT id, fingerprint, snapshot_json FROM monitor_event')).all() == original


@pytest.mark.ui
def test_automatic_start_hidden_window_and_per_recipe_delivery(app_container, qtbot):
    from emss.ui.integration.panel import KhanzaIntegrationPanel
    from emss.services.authentication import AuthenticatedUser
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    # Use actual elapsed time here, not the deterministic service-test clock.
    service.monitor.clock = utc_now
    adapter.source_time = utc_now
    app_container.khanza_adapter, app_container.khanza_polling = adapter, service
    app_container.settings.khanza_polling_enabled = True
    app_container.settings.khanza_internal_polling_consent = True
    user = AuthenticatedUser(actor.id, actor.username, actor.display_name, frozenset({'SUPER_ADMIN'}), False)
    panel = KhanzaIntegrationPanel(app_container, user)
    qtbot.addWidget(panel)
    observed = []
    panel.screening_ready.connect(observed.append)
    panel.hide()
    qtbot.waitUntil(lambda: len(observed) == 1, timeout=12000)
    assert panel.timer.isActive() and not panel.isVisible()
    assert app_container.queue.list_items()[0].screening_id == observed[0]
    panel.auto_button.setChecked(False)
    qtbot.waitUntil(lambda: not panel._busy, timeout=10000)


@pytest.mark.ui
def test_popup_priority_dedup_and_visual_audio_failure(app_container, qtbot):
    from emss.ui.tray.controller import SystemTrayController
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    result = finish(actor, service, clock)
    queued = app_container.queue.enqueue_screening(result.screening_ids[0])
    tray = SystemTrayController()
    qtbot.addWidget(tray.fullscreen_alert)
    shown = []
    tray.alert_displayed.connect(shown.append)
    low = replace(queued, alert_id='synthetic-clear', audio_category='screening-clear')
    tray.show_screening_alert(low)
    tray.show_screening_alert(queued)
    tray.show_screening_alert(queued)
    qtbot.waitUntil(lambda: bool(shown), timeout=3000)
    assert shown == [queued.alert_id]
    assert tray.fullscreen_alert.isVisible()
    # Original audio is now bundled, while the visual recipe fallback remains visible.
    assert 'Resep RX-SYNTH-001' in tray.fullscreen_alert.hint.text()
    assert len(tray._pending) == 1
    tray.delivery_allowed = lambda _: False
    tray._check_active()
    assert not tray.fullscreen_alert.isVisible()
    tray.hide()


def test_monitor_lock_invalid_actor_and_retry_validation(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    assert service.monitor._process_lock.acquire()
    other = KhanzaPollingService(app_container.database, app_container.settings, adapter, app_container.screening, app_container.queue)
    try:
        assert other.monitor.cycle(actor.id).status == 'BUSY'
    finally:
        service.monitor._process_lock.release()
    with pytest.raises(ValueError): service.monitor.cycle('missing')
    with pytest.raises(ValueError): service.monitor.request_retry('invalid recipe!', actor.id, 'x')
    with pytest.raises(ValueError): service.monitor.request_retry('RX-A', actor.id, '')
    with pytest.raises(ValueError): service.monitor.request_retry('RX-A', 'missing', 'x')


def test_retry_is_serialized_and_stability_floor_is_not_weakened(app_container):
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    adapter.add_snapshot(replace(snap, header=replace(
        snap.header, status='DIRESEPKAN', validation_token='', item_basis='PRESCRIBED'
    )))
    service.monitor._lock.acquire()
    try:
        with pytest.raises(ValueError, match='Worker sedang'): service.monitor.request_retry(snap.header.no_resep, actor.id, 'Uji')
        assert service.monitor.cycle(actor.id).status == 'BUSY'
    finally:
        service.monitor._lock.release()
    other = KhanzaPollingService(app_container.database, app_container.settings, adapter, app_container.screening, app_container.queue)
    other.monitor._process_lock.acquire()
    try:
        with pytest.raises(ValueError, match='Worker lain'): service.monitor.request_retry(snap.header.no_resep, actor.id, 'Uji')
    finally:
        other.monitor._process_lock.release()
    app_container.settings.khanza_stability_interval_seconds = 0
    assert service.monitor.cycle(actor.id).processed == 0
    clock[0] += timedelta(seconds=1)
    assert service.monitor._observe(snap.header.no_resep, actor.id) == ('PENDING', None)
    clock[0] += timedelta(seconds=1.1)
    assert service.monitor.cycle(actor.id).processed == 1


def test_unstable_events_immutable_and_backup_restores_monitor(app_container):
    from sqlalchemy.exc import DatabaseError
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    service.monitor.cycle(actor.id)
    changed = replace(snap,
        header=replace(snap.header, changed_at=clock[0] + timedelta(seconds=61)),
        regular_items=(replace(snap.regular_items[0], quantity='3'), snap.regular_items[1]))
    adapter.add_snapshot(changed)
    clock[0] += timedelta(seconds=61)
    assert finish(actor, service, clock).processed == 1
    with app_container.database.session() as session:
        rows = session.scalars(select(MonitorEvent).order_by(MonitorEvent.sequence)).all()
        assert [r.state for r in rows] == ['COMPLETED', 'COMPLETED']
        originals = [(r.id, r.fingerprint, r.snapshot_json) for r in rows]
    for sql in ["UPDATE monitor_event SET fingerprint='modified'", 'DELETE FROM monitor_event']:
        with app_container.database.session() as session:
            with pytest.raises(DatabaseError): session.execute(text(sql))
            session.rollback()
    backup = app_container.backup.create_backup('MONITOR_SYNTHETIC', actor.id)
    app_container.backup.restore_backup(backup.database_path, actor.id)
    with app_container.database.session() as session:
        assert session.execute(text('SELECT id, fingerprint, snapshot_json FROM monitor_event ORDER BY sequence')).all() == originals
    assert app_container.health.check().audit_chain_valid


def test_source_verification_change_cannot_reuse_complete_result_without_event_id(app_container):
    from test_screening_engine import _prescription
    actor = _admin(app_container)
    _, codes = _seed(app_container, actor.id, rule_status='ASSESSED_NO_INTERACTION', severity_code='NONE', severity_rank=0, app_severity=None)
    value = _prescription(codes)
    complete = app_container.screening.screen(value, actor.id)
    incomplete = app_container.screening.screen(replace(value, source_verified=False), actor.id)
    assert complete.screening_id != incomplete.screening_id
    assert incomplete.completeness_status != 'COMPLETE'


@pytest.mark.ui
def test_delivery_rechecks_actor_connection_latest_source_and_mode(app_container, qtbot):
    from emss.ui.application import MainWindow
    from emss.services.authentication import AuthenticatedUser
    from emss.config.settings import AppEnvironment
    from emss.database.models import AppUser
    actor, service, adapter, clock, snap = monitor_fixture(app_container)
    app_container.khanza_adapter, app_container.khanza_polling = adapter, service
    result = finish(actor, service, clock)
    queued = app_container.queue.enqueue_screening(result.screening_ids[0])
    user = AuthenticatedUser(actor.id, actor.username, 'Uji', frozenset({'SUPER_ADMIN'}), False)
    window = MainWindow(app_container, user)
    qtbot.addWidget(window)
    assert window._delivery_allowed(queued) is True
    service._mark_disconnected('SYNTHETIC')
    assert window._delivery_allowed(queued) is None
    service._mark_connected()
    app_container.settings.environment = AppEnvironment.SILENT_PILOT
    assert window._delivery_allowed(queued) is False
    app_container.settings.environment = AppEnvironment.PRODUCTION
    assert window._delivery_allowed(queued) is False
    app_container.settings.environment = AppEnvironment.TEST
    with app_container.database.session() as s:
        s.get(AppUser, actor.id).is_active = False
        s.commit()
    assert window._delivery_allowed(queued) is False
    with app_container.database.session() as s:
        s.get(AppUser, actor.id).is_active = True
        s.get(MonitorInbox, (service.adapter_code, snap.header.no_resep)).state = 'STABILIZING'
        s.commit()
    assert window._delivery_allowed(queued) is False
    window.queue_tab.refresh()
    assert 'Hasil tersedia' in window.queue_tab.detail_label.text()
    window.outbox_timer.stop()
