from __future__ import annotations

from datetime import UTC, timedelta

from emss.database.queue_models import ProcessingQueue
from emss.utils.time import utc_now
from test_screening_engine import _admin, _prescription, _seed


def _row(number, revision, detected_at, *, prescription_id=None):
    return ProcessingQueue(
        prescription_id=prescription_id,
        source_no_resep=number,
        revision_number=revision,
        service_unit='UNIT UJI',
        care_setting='RALAN',
        processing_status='COMPLETED',
        review_status='NEW',
        risk_status='CRITICAL' if revision == 2 else 'HIGH_RISK',
        completeness_status='COMPLETE',
        overall_status='CRITICAL',
        alert_level='CRITICAL',
        priority=100,
        hold_recommended=True,
        attempts=1,
        max_attempts=3,
        is_mock=True,
        detected_at=detected_at,
    )


def test_operational_queue_excludes_old_revisions_but_history_keeps_them(app_container):
    now = utc_now()
    with app_container.database.session() as session:
        session.add_all((
            _row('RX-001', 1, now - timedelta(days=2)),
            _row('RX-001', 2, now),
        ))
        session.commit()

    effective = app_container.queue.list_items()
    history = app_container.queue.list_items(include_history=True)
    assert [row.revision_number for row in effective] == [2]
    assert [row.revision_number for row in history] == [2, 1]
    assert history[0].is_effective and not history[1].is_effective
    assert app_container.queue.summary().total == 1
    assert app_container.queue.summary(include_history=True).total == 2


def test_operational_queue_and_units_are_scoped_to_today(app_container):
    from emss.database.queue_models import AlertEvent

    now = utc_now()
    with app_container.database.session() as session:
        old = _row('RX-YESTERDAY', 1, now - timedelta(days=2))
        old.service_unit = 'UNIT LAMA'
        current = _row('RX-TODAY', 1, now)
        current.service_unit = 'UNIT HARI INI'
        session.add_all((old, current))
        session.flush()
        session.add_all((
            AlertEvent(queue_item_id=old.id, screening_id=None, level='CRITICAL', status='NEW',
                title='Lama', message='Tidak boleh dikirim ulang'),
            AlertEvent(queue_item_id=current.id, screening_id=None, level='CRITICAL', status='NEW',
                title='Hari ini', message='Tetap antrean operasional'),
        ))
        session.commit()

    assert [row.no_resep for row in app_container.queue.list_items()] == ['RX-TODAY']
    assert {row.no_resep for row in app_container.queue.list_items(include_history=True)} == {
        'RX-TODAY', 'RX-YESTERDAY'
    }
    assert app_container.queue.list_units() == ('UNIT HARI INI',)
    assert set(app_container.queue.list_units(include_history=True)) == {'UNIT HARI INI', 'UNIT LAMA'}


def test_pending_delivery_does_not_replay_yesterday_alert(app_container):
    actor = _admin(app_container)
    _, codes = _seed(app_container, actor.id)
    old_result = app_container.screening.screen(
        _prescription(codes, no_resep='RX-ALERT-YESTERDAY'), actor.id
    )
    current_result = app_container.screening.screen(
        _prescription(codes, no_resep='RX-ALERT-TODAY'), actor.id
    )
    old = app_container.queue.enqueue_screening(old_result.screening_id)
    app_container.queue.enqueue_screening(current_result.screening_id)
    with app_container.database.session() as session:
        session.get(ProcessingQueue, old.item.id).detected_at = utc_now() - timedelta(days=2)
        session.commit()

    assert app_container.queue.pending_screening_ids() == (current_result.screening_id,)


def test_dashboard_and_export_state_the_effective_metric_basis(app_container, tmp_path):
    admin = app_container.users.create_first_admin(
        username='admin.batch8', display_name='Admin Batch 8',
        password='Frasa aman batch delapan!',
    )
    now = utc_now()
    with app_container.database.session() as session:
        session.add_all((
            _row('RX-002', 1, now - timedelta(minutes=2)),
            _row('RX-002', 2, now),
        ))
        session.commit()

    summary = app_container.dashboard.summary('ALL')
    assert summary.prescriptions_screened == 1
    report = app_container.dashboard.export_aggregate_csv(tmp_path / 'batch8.csv', admin.id)
    content = report.read_text(encoding='utf-8-sig')
    assert 'Basis metrik' in content
    assert 'tidak dihitung ganda' in content
    assert 'Temuan pDDI lintas resep' in content
