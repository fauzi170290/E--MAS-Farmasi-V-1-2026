"""Regression for the reported workflow; all writes use disposable test databases."""
from dataclasses import replace, asdict
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func
from test_screening_engine import _admin, _seed, _prescription
from emss.database.models import AppUser
from emss.database.monitoring_models import MonitorEvent
from emss.database.screening_models import Prescription, PrescriptionRevision
from emss.database.queue_models import ProcessingQueue
from emss.database.intervention_models import PharmacistIntervention
from emss.database.catalog_models import DrugMaster, DrugComponentMapping
from emss.services.screening import PrescriptionInput, PrescriptionItemInput
from emss.services.queue import QueueError
from emss.utils.time import utc_now


def source_event(container, number, sequence=1, screening_id=None, prescription=None):
    payload = {'header': {'care_setting': 'RALAN'}}
    if prescription:
        payload = {'header': {'care_setting': 'RALAN', 'no_resep': number, 'no_rawat': 'VISIT-SYNTH',
            'patient_id': prescription.patient_id, 'changed_at': prescription.source_changed_at.isoformat(),
            'item_basis': 'FINAL', 'composition_complete': True, 'status': prescription.source_status},
            'regular_items': [asdict(item) for item in prescription.items], 'compounded_items': [],
            'revision': str(sequence)}
    with container.database.session() as session:
        row = MonitorEvent(adapter_code='mysql', no_resep=number, sequence=sequence,
            event_type='VALIDATION', fingerprint=str(sequence)*64, source_status='DIPROSES_FARMASI',
            snapshot_json=json.dumps(payload),
            screening_id=screening_id, state='COMPLETED')
        session.add(row)
        session.commit()
        return row.id


def attach(container, event_id, screening_id):
    with container.database.session() as session:
        session.get(MonitorEvent, event_id).screening_id = screening_id
        session.commit()


def test_local_source_reuses_legacy_identity_without_renaming_audit_or_creating_self_duplicate(app_container):
    actor = _admin(app_container)
    _, codes = _seed(app_container, actor.id)
    original = replace(_prescription(codes, no_resep='RX-NATIVE'), source_status='DIPROSES_FARMASI',
        source_changed_at=utc_now())
    old = app_container.screening.screen(original, actor.id, mock_mode=True)
    event_id = source_event(app_container, 'RX-NATIVE', screening_id=old.screening_id)
    old_queue = app_container.queue.enqueue_screening(old.screening_id)
    new = app_container.screening.screen(replace(original, source_event_id=event_id), actor.id, mock_mode=True)
    attach(app_container, event_id, new.screening_id)
    current = app_container.queue.enqueue_screening(new.screening_id)
    assert new.revision_number == 2
    assert not any(i.issue_type == 'DUPLICATE_THERAPY' for i in new.issues)
    assert current.item.no_resep == 'RX-NATIVE'
    assert current.item.is_mock and current.item.source_adapter == 'mysql'
    assert app_container.queue.get_detail(old_queue.item.id).item.no_resep == 'RX-NATIVE'
    with app_container.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Prescription)) == 1
        assert session.scalar(select(Prescription.source_no_resep)) == 'MOCK-RX-NATIVE'


def test_review_is_scoped_to_seen_revisions_and_service_without_intervention(app_container):
    actor = _admin(app_container)
    _, codes = _seed(app_container, actor.id)
    ids = []
    for number, care in [(1, 'RALAN'), (2, 'RALAN'), (3, 'RALAN'), (4, 'RANAP')]:
        result = app_container.screening.screen(_prescription(codes, quantity=str(number)), actor.id)
        queue = app_container.queue.enqueue_screening(result.screening_id)
        ids.append(queue.item.id)
        with app_container.database.session() as session:
            session.get(ProcessingQueue, queue.item.id).care_setting = care
            session.commit()
    app_container.queue.acknowledge(ids[1], actor.id)
    with app_container.database.session() as session:
        assert [session.get(ProcessingQueue, key).review_status for key in ids] == ['REVIEWED','REVIEWED','NEW','NEW']
        assert session.scalar(select(func.count()).select_from(PharmacistIntervention)) == 0
        assert app_container.audit.verify_chain(session)
    app_container.settings.allow_workstation_mode = True
    mode = app_container.workstation_access.enter_mode(care_setting='RALAN')
    with pytest.raises(QueueError):
        app_container.queue.acknowledge(ids[2], mode.id)


def test_uat_guard_denies_workstation_even_if_account_is_mistakenly_activated(app_container):
    _admin(app_container)
    app_container.settings.allow_workstation_mode = True
    mode = app_container.workstation_access.enter_mode(care_setting='RALAN')
    with app_container.database.session() as session:
        session.get(AppUser, mode.id).is_active = True
        session.commit()
    with pytest.raises(ValueError):
        app_container.clinical_validation.uat_items(mode.id)
    with pytest.raises(ValueError):
        app_container.uat_release.candidates(mode.id)


def test_explicit_retry_requires_named_authorized_actor(app_container):
    from emss.database.models import UserRole
    from emss.database.monitoring_models import MonitorInbox
    actor = _admin(app_container)
    app_container.settings.allow_workstation_mode = True
    mode = app_container.workstation_access.enter_mode(care_setting='RALAN')
    monitor = app_container.khanza_polling.monitor
    with app_container.database.session() as session:
        session.get(AppUser, mode.id).is_active = True
        session.commit()
    with pytest.raises(ValueError, match='akun petugas'):
        monitor.request_retry('UAT-RETRY', mode.id, 'Uji sintetis')
    with app_container.database.session() as session:
        assert session.scalar(select(func.count()).select_from(MonitorInbox)) == 0
    monitor.request_retry('UAT-RETRY', actor.id, 'Pemetaan diperbaiki; uji sintetis')
    with app_container.database.session() as session:
        assert session.get(MonitorInbox, (monitor.code, 'UAT-RETRY')).state == 'PENDING'
        assert app_container.audit.verify_chain(session)
        for role in session.scalars(select(UserRole).where(UserRole.user_id == actor.id)).all():
            session.delete(role)
        session.commit()
    with pytest.raises(ValueError, match='akun petugas'):
        monitor.request_retry('UAT-OTHER', actor.id, 'Uji tanpa peran')


def test_three_reported_prescriptions_keep_all_pairs_and_pending_mapping(app_container):
    actor = _admin(app_container)
    app_container.bundled_ddi.apply_if_eligible(actor.id)
    app_container.bundled_mapping.apply_if_eligible(actor.id)
    codes = [('000001035','000001330','000003210','000003211'),
        ('000003212','000003895'), ('000000761','000004629','000005759')]
    results = []
    for index, group in enumerate(codes, 1):
        number = f'UAT-SYNTH-{index}'
        value = PrescriptionInput(no_resep=number, patient_id='PATIENT-SYNTH',
            source_changed_at=utc_now(), source_status='DIPROSES_FARMASI',
            items=tuple(PrescriptionItemInput(str(i), code, code) for i, code in enumerate(group)))
        event_id = source_event(app_container, number, prescription=value)
        result = app_container.screening.screen(replace(value, source_event_id=event_id),
            actor.id, mock_mode=True)
        attach(app_container, event_id, result.screening_id)
        queue = app_container.queue.enqueue_screening(result.screening_id)
        detail = app_container.queue.get_detail(queue.item.id)
        assert len(detail.pairs) == result.pair_count
        results.append(result)
    assert [sum(p.provenance is None for p in r.pairs) for r in results] == [6, 1, 3]
    assert any(p.provenance for p in results[1].pairs)
    assert {p.provenance['previous']['no_resep'] for p in results[2].pairs if p.provenance} == {'UAT-SYNTH-1', 'UAT-SYNTH-2'}
    assert any(i.issue_type == 'DUPLICATE_THERAPY' for i in results[1].issues)
    assert results[2].unmapped_drug_count == 0
    assert sum(p.classification == 'PAIR_NOT_ASSESSED' for p in results[2].pairs if p.provenance is None) == 1
    assert {p.pair_key for p in results[2].pairs if p.provenance is None} == {
        'febuxostat || theophylline', 'febuxostat || warfarin', 'theophylline || warfarin'}
    with app_container.database.session() as session:
        drug = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == '000004629'))
        component = session.scalar(select(DrugComponentMapping).where(DrugComponentMapping.drug_id == drug.id))
        assert drug.review_status == component.review_status == 'PENDING_REVIEW'
        assert not component.is_active


def test_duplicate_does_not_override_contraindication_popup():
    from emss.alerts.notification import notification_decision
    screen = SimpleNamespace(risk_status='CRITICAL', completeness_status='COMPLETE')
    pair = SimpleNamespace(classification='INTERACTION_FOUND', severity_code='CONTRAINDICATED')
    issue = SimpleNamespace(issue_type='DUPLICATE_THERAPY', message='Resep terkait UAT-1')
    decision, category = notification_decision(screen, [pair], [issue], validated=True, validated_high_only=True)
    assert category == 'contraindicated' and decision.title == 'KONTRAINDIKASI'


def test_mapping_upgrade_adds_only_supplement_preserving_legacy_deletion(app_container, monkeypatch):
    import gzip
    import emss.services.bundled_mapping as module
    from emss.utils.resources import bundled_resource
    actor = _admin(app_container)
    root = bundled_resource('seed')
    manifest = json.loads((root/'mapping-khanza-20260828.manifest.json').read_text())
    payload = json.loads(gzip.decompress((root/'mapping-khanza-20260828.json.gz').read_bytes()))
    with monkeypatch.context() as patch:
        patch.setattr(module, '_read_bundle', lambda: (manifest,payload,payload['drugs']+payload['corrections']))
        for constant,key in [('BUNDLE_ID','bundle_id'),('EXPECTED_SOURCE_SHA256','source_sha256'),
                ('EXPECTED_BUNDLE_SHA256','bundle_sha256'),('EXPECTED_SEMANTIC_SHA256','semantic_sha256')]:
            patch.setattr(module,constant,manifest[key])
        app_container.bundled_mapping.apply_if_eligible(actor.id)
    with app_container.database.session() as session:
        session.delete(session.scalar(select(DrugMaster).where(DrugMaster.khanza_code=='000001074')))
        session.commit()
    result = app_container.bundled_mapping.apply_if_eligible(actor.id)
    assert result.inserted == 1 and result.preserved == 413
    with app_container.database.session() as session:
        assert session.scalar(select(DrugMaster).where(DrugMaster.khanza_code=='000001074')) is None
        assert session.scalar(select(DrugMaster).where(DrugMaster.khanza_code=='000004629')) is not None
