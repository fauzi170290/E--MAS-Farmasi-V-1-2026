"""Synthetic identities/rules only: no clinical efficacy assertions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta
import json

import pytest
from sqlalchemy import select, func
from test_screening_engine import _admin, _seed, _prescription
from test_durable_monitor import monitor_fixture, finish
from emss.database.monitoring_models import MonitorEvent, MonitorInbox
from emss.database.screening_models import Screening, ScreeningPair
from emss.database.queue_models import ProcessingQueue
from emss.integrations.khanza.domain import PrescriptionHeader, PrescriptionItem, PrescriptionSnapshot
from emss.services.khanza_polling import KhanzaPollingService
from emss.services.reference import DrugEdit
from emss.utils.time import utc_now


def observed(c, codes, number, *, patient="PATIENT-67", care="RALAN", unit="POLI A", doctor="Dokter A",
             when=None, visit="VISIT-67", sequence=1, status="DIPROSES_FARMASI", adapter="synthetic-67"):
    when = when or utc_now()
    value = replace(_prescription(codes, no_resep=number), patient_id=patient, patient_name="NAMA SAMA UJI",
        service_unit=unit, prescriber_name=doctor, source_changed_at=when, source_status=status)
    snap = PrescriptionSnapshot(PrescriptionHeader(number, visit, patient_id=patient, patient_name=value.patient_name,
        service_unit=unit, prescriber_name=doctor, status=status, changed_at=when, validation_token="UAT",
        item_basis="FINAL", composition_complete=True, care_setting=care),
        tuple(PrescriptionItem(**asdict(x)) for x in value.items), (), f"source-{sequence}")
    with c.database.session() as s:
        event = MonitorEvent(adapter_code=adapter, no_resep=number, sequence=sequence,
            event_type="NEW" if sequence == 1 else "REVISION", fingerprint=snap.fingerprint(),
            source_status=status, snapshot_json=json.dumps(asdict(snap), default=str))
        s.add(event)
        s.commit()
        return replace(value, source_event_id=event.id)


def test_three_prescriptions_cross_only_pair_provenance_retry_and_history(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    at = utc_now()
    inputs = [observed(c, (code,), f"RX-FULL-{n:03}", when=at + timedelta(minutes=45*n),
        unit=f"POLI {n}", doctor=f"Dokter {n}") for n, code in ((1, a), (2, b), (3, a))]
    results = [c.screening.screen(value, actor.id) for value in inputs]
    assert results[0].pair_count == 0
    assert results[1].interaction_count == 1 and results[1].risk_status == "CRITICAL"
    assert results[2].interaction_count == 1
    assert any(i.issue_type == "DUPLICATE_THERAPY" for i in results[2].issues)
    for result, previous in ((results[1], "RX-FULL-001"), (results[2], "RX-FULL-002")):
        p = result.pairs[0].provenance
        assert p["previous"]["no_resep"] == previous
        assert p["current"]["revision_id"] == result.revision_id
        assert p["previous"]["revision_id"]
        assert p["occurrences"][0]["current"]["khanza_code"]
        assert p["use_status"] == "UNKNOWN_RECONCILIATION_REQUIRED"
        queued = c.queue.enqueue_screening(result.screening_id)
        assert c.queue.get_detail(queued.item.id).pairs[0].provenance == p
    repeated = c.screening.screen(inputs[2], actor.id)
    assert repeated.reused and repeated.screening_id == results[2].screening_id
    # Re-evaluating an older owner must not create a mirrored copy of 001–002.
    assert c.screening.screen(inputs[0], actor.id).pair_count == 0
    with c.database.session() as s:
        assert s.scalar(select(func.count()).select_from(ScreeningPair)) == 2
        assert c.audit.verify_chain(s)
    summary = c.dashboard.summary("ALL")
    assert summary.contraindicated_pairs == 2
    assert summary.unique_ddi_pairs == 1
    assert summary.cross_prescription_findings == 2


@pytest.mark.parametrize("change", [{"patient": "OTHER"}, {"care": "RANAP"},
    {"adapter": "other-source"}, {"visit": "OTHER", "hours": 25}])
def test_patient_care_adapter_and_window_isolation(app_container, change):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    at = utc_now()
    first = observed(c, (a,), "SAME-SUFFIX-001", when=at)
    c.screening.screen(first, actor.id)
    options = dict(change)
    hours = options.pop("hours", 1)
    second = observed(c, (b,), "OTHER-PREFIX-001", when=at + timedelta(hours=hours), **options)
    assert c.screening.screen(second, actor.id).pair_count == 0


def test_previous_calendar_day_is_not_cross_prescription_context_after_restart(app_container):
    from emss.app import build_application
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    at = utc_now()
    c.screening.screen(observed(c, (a,), "ARRIVED-FIRST", when=at), actor.id)
    c.database.engine.dispose()
    restarted = build_application(c.settings)
    try:
        late = observed(restarted, (b,), "ARRIVED-LATE", when=at - timedelta(days=2))
        result = restarted.screening.screen(late, actor.id)
        assert result.interaction_count == 0
        assert restarted.screening.screen(late, actor.id).reused
    finally:
        restarted.close()


def test_same_local_day_is_context_but_previous_local_day_isolated(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    local_now = utc_now().astimezone()
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    first = observed(c, (a,), "RX-DAY-001", when=(day_start + timedelta(hours=1)).astimezone())
    c.screening.screen(first, actor.id)
    same_day = observed(c, (b,), "RX-DAY-002", when=(day_start + timedelta(hours=23)).astimezone())
    assert c.screening.screen(same_day, actor.id).interaction_count == 1

    previous_day = observed(c, (a,), "RX-YESTERDAY", patient="PATIENT-OTHER-DAY",
        when=(day_start - timedelta(minutes=1)).astimezone())
    c.screening.screen(previous_day, actor.id)
    current_day = observed(c, (b,), "RX-TODAY", patient="PATIENT-OTHER-DAY",
        when=(day_start + timedelta(minutes=1)).astimezone())
    assert c.screening.screen(current_day, actor.id).interaction_count == 0


def test_latest_cancel_and_revision_do_not_fall_back_to_old_final(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    first = observed(c, (a,), "RX-001")
    c.screening.screen(first, actor.id)
    second = observed(c, (b,), "RX-002")
    original = c.screening.screen(second, actor.id)
    assert original.interaction_count == 1
    observed(c, (a,), "RX-001", sequence=2, status="DIBATALKAN")
    cancelled = c.screening.screen(second, actor.id)
    assert cancelled.interaction_count == 0 and not cancelled.reused
    assert cancelled.completeness_status == "INCOMPLETE"
    observed(c, (b,), "RX-001", sequence=3)
    revised = c.screening.screen(second, actor.id)
    assert revised.interaction_count == 0
    assert any(i.issue_type == "DUPLICATE_THERAPY" for i in revised.issues)
    with c.database.session() as s:
        assert s.get(Screening, original.screening_id).interaction_count == 1


def test_unknown_pairs_mapping_identity_are_not_safe(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id, combination=True)
    c.screening.screen(observed(c, (a,), "RX-COMBO"), actor.id)
    result = c.screening.screen(observed(c, (b,), "RX-B"), actor.id)
    assert result.interaction_count == 1 and result.not_assessed_count == 1
    assert result.completeness_status == "NOT_ASSESSED"
    missing = c.screening.screen(observed(c, (b,), "RX-NO-ID", patient=""), actor.id)
    assert missing.completeness_status == "INCOMPLETE"
    c.screening.screen(observed(c, ("UNKNOWN-CODE",), "RX-UNMAPPED"), actor.id)
    result = c.screening.screen(observed(c, (b,), "RX-AFTER-UNMAPPED"), actor.id)
    assert any(i.issue_type == "DRUG_UNMAPPED" and "RX-UNMAPPED" in i.message for i in result.issues)


def test_concurrent_arrivals_and_retry_are_serialized(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    inputs = [observed(c, (a,), "RX-A"), observed(c, (b,), "RX-B")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: c.screening.screen(x, actor.id), inputs))
    assert sorted(r.interaction_count for r in results) == [0, 1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        retries = list(pool.map(lambda x: c.screening.screen(x, actor.id), inputs))
    assert all(r.reused for r in retries)
    with c.database.session() as s:
        assert s.scalar(select(func.count()).select_from(Screening)) == 2
        assert s.scalar(select(func.count()).select_from(ScreeningPair)) == 1


def test_monitor_revision_schedules_local_dependents_without_source_reread(app_container):
    c = app_container
    actor, service, adapter, clock, snap = monitor_fixture(c)
    snap = replace(snap, header=replace(snap.header, patient_id="PATIENT-67", care_setting="RALAN"),
        regular_items=snap.regular_items[:1])
    adapter.add_snapshot(snap)
    assert service.monitor.cycle(actor.id).processed == 1
    clock[0] += timedelta(seconds=3)
    second = replace(snap, header=replace(snap.header, no_resep="RX-SYNTH-002", changed_at=clock[0]),
        regular_items=(replace(snap.regular_items[0], khanza_code="OBAT-B"),))
    adapter.add_snapshot(second)
    result = service.monitor.cycle(actor.id)
    assert result.processed == 1
    with c.database.session() as s:
        assert s.get(Screening, result.screening_ids[0]).interaction_count == 1
    _assert_local_cancel_replay(c, actor, service, adapter, clock, snap, second, result)


def _assert_local_cancel_replay(c, actor, service, adapter, clock, snap, second, result):
    clock[0] += timedelta(seconds=3)
    adapter.add_snapshot(replace(snap, header=replace(snap.header, status="DIBATALKAN", changed_at=clock[0])))
    service.monitor.cycle(actor.id)
    with c.database.session() as s:
        assert s.get(MonitorInbox, (service.adapter_code, second.header.no_resep)).state == "CONTEXT_PENDING"
    resumed = KhanzaPollingService(c.database, c.settings, adapter, c.screening, c.queue)
    resumed.monitor.clock = lambda: clock[0]
    original_reader = adapter.get_snapshot
    def no_second_read(number):
        assert number != second.header.no_resep, "Completed dependent was reread from source"
        return original_reader(number)
    adapter.get_snapshot = no_second_read
    clock[0] += timedelta(seconds=3)
    updated = resumed.monitor.cycle(actor.id)
    assert updated.failed == 0 and updated.processed >= 1
    with c.database.session() as s:
        inbox = s.get(MonitorInbox, (service.adapter_code, second.header.no_resep))
        assert inbox.state == "COMPLETED"
        assert s.get(Screening, inbox.screening_id).interaction_count == 0
        assert s.get(Screening, result.screening_ids[0]).interaction_count == 1


def test_empty_context_after_cancellation_is_new_revision_not_old_review(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    c.screening.screen(observed(c, (a,), "RX-OLD", status="DIRESEPKAN"), actor.id)
    second = observed(c, (b,), "RX-OWNER")
    clear = c.screening.screen(second, actor.id)
    c.queue.enqueue_screening(clear.screening_id)
    observed(c, (a,), "RX-OLD", sequence=2)
    positive = c.screening.screen(second, actor.id)
    c.queue.enqueue_screening(positive.screening_id)
    observed(c, (a,), "RX-OLD", sequence=3, status="DIBATALKAN")
    changed = c.screening.screen(second, actor.id)
    queued = c.queue.enqueue_screening(changed.screening_id)
    assert not changed.reused and changed.revision_number == 3
    assert queued.item.review_status == "NEW" and not queued.item.reviewed_at
    assert c.dashboard.summary("ALL").contraindicated_pairs == 0


def test_identical_full_number_across_sources_has_separate_identity(app_container):
    from emss.database.screening_models import Prescription
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    one = observed(c, (a,), "RX-SAME", adapter="source-a")
    two = observed(c, (b,), "RX-SAME", adapter="source-b")
    first, second = [c.screening.screen(v, actor.id) for v in (one, two)]
    assert first.revision_number == second.revision_number == 1
    assert c.screening.screen(two, actor.id).reused
    assert c.queue.enqueue_screening(second.screening_id).item.no_resep == "RX-SAME"
    with c.database.session() as s:
        assert s.scalar(select(func.count()).select_from(Prescription)) == 2


def test_missing_identity_never_plays_clear_confirmation(app_container):
    c = app_container
    actor = _admin(c)
    _, codes = _seed(c, actor.id, rule_status="ASSESSED_NO_INTERACTION", severity_code="NONE", severity_rank=0, app_severity=None)
    result = c.screening.screen(observed(c, codes, "RX-NO-PATIENT", patient=""), actor.id)
    assert result.completeness_status == "INCOMPLETE"
    assert c.queue.enqueue_screening(result.screening_id).audio_category != "screening-clear"


def test_patient_correction_does_not_restore_old_clear_revision(app_container):
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    c.screening.screen(observed(c, (a,), "RX-CORRECTED", status="DIRESEPKAN"), actor.id)
    second = observed(c, (b,), "RX-OWNER")
    clear = c.screening.screen(second, actor.id)
    c.screening.screen(observed(c, (a,), "RX-CORRECTED", sequence=2), actor.id)
    assert c.screening.screen(second, actor.id).interaction_count == 1
    c.screening.screen(observed(c, (a,), "RX-CORRECTED", sequence=3, patient="OTHER-PATIENT"), actor.id)
    changed = c.screening.screen(second, actor.id)
    assert changed.screening_id != clear.screening_id and changed.revision_number == 3
    assert changed.interaction_count == 0 and changed.completeness_status == "INCOMPLETE"


def test_empty_cancel_preserves_history_suppresses_old_delivery_and_stops_polling(app_container):
    from emss.database.queue_models import AlertEvent
    c = app_container
    actor, service, adapter, clock, snap = monitor_fixture(c)
    original = service.monitor.cycle(actor.id)
    assert original.processed == 1
    old_queued = c.queue.enqueue_screening(original.screening_ids[0])
    clock[0] += timedelta(seconds=3)
    adapter.add_snapshot(replace(snap, header=replace(snap.header, status="DIBATALKAN", changed_at=clock[0]),
        regular_items=(), compounded_items=()))
    service.monitor.cycle(actor.id)
    clock[0] += timedelta(seconds=3)
    result = service.monitor.cycle(actor.id)
    assert result.processed == 1 and result.failed == 0
    with c.database.session() as s:
        latest = s.get(Screening, result.screening_ids[0])
        assert latest.pair_count == 0 and latest.completeness_status == "INCOMPLETE"
        assert s.get(Screening, original.screening_ids[0]).interaction_count == 1
        assert s.get(AlertEvent, old_queued.alert_id).status == "SUPPRESSED"
        assert s.get(ProcessingQueue, old_queued.item.id).review_status == "NEW"
        assert s.get(MonitorInbox, (service.adapter_code, snap.header.no_resep)).state == "COMPLETED"
    clock[0] += timedelta(seconds=3)
    assert service.monitor.cycle(actor.id).processed == 0


def test_third_prescription_compares_both_previous_doctors(app_container):
    from emss.services.knowledge import ManualDdiRule
    c = app_container
    actor = _admin(c)
    _, (a, b) = _seed(c, actor.id)
    third_drug = c.reference.save_drug(DrugEdit("Obat C sintetis", ("zat c",), "UAT komposisi"), actor.id)
    code_c = c.reference.drug_detail(third_drug)["code"]
    for ingredient in ("zat a", "zat b"):
        c.reference.save_pair(ManualDdiRule(version_id="", ingredient_a=ingredient, ingredient_b="zat c",
            interaction_status="INTERACTION_FOUND", severity_code="SERIOUS", source_name="UAT sintetis",
            source_reference="UAT 3 resep / 3 dokter"), actor.id, expected_version_id=c.reference.active_version_id())
    values = [observed(c, (code,), f"RX-DOCTOR-{n}", doctor=f"Dokter {n}", unit=f"POLI {n}")
        for n, code in enumerate((a, b, code_c), 1)]
    results = [c.screening.screen(v, actor.id) for v in values]
    assert [r.interaction_count for r in results] == [0, 1, 2]
    assert {p.provenance["previous"]["no_resep"] for p in results[2].pairs} == {"RX-DOCTOR-1", "RX-DOCTOR-2"}
    assert c.screening.screen(values[2], actor.id).reused


def test_internal_and_cross_same_ingredient_pair_do_not_overwrite_each_other(app_container):
    c = app_container
    actor = _admin(c)
    _, codes = _seed(c, actor.id)
    c.screening.screen(observed(c, codes, "RX-BOTH-1"), actor.id)
    result = c.screening.screen(observed(c, codes, "RX-BOTH-2"), actor.id)
    assert result.interaction_count == 2
    assert sum(p.provenance is None for p in result.pairs) == 1
    cross = next(p for p in result.pairs if p.provenance)
    assert len(cross.provenance["occurrences"]) == 2
