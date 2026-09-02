from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from sqlalchemy import select

from emss.database.intervention_models import PharmacistIntervention
from emss.database.models import AuditLog
from emss.database.queue_models import ProcessingQueue
from emss.services.interventions import InterventionError
from emss.utils.time import utc_now


def _critical_queue(app_container) -> tuple[str, str]:
    admin = app_container.users.create_first_admin(
        username="admin.sprint7",
        display_name="Apoteker Admin Sprint 7",
        password="Frasa aman admin sprint tujuh!",
    )
    with app_container.database.session() as session:
        queue = ProcessingQueue(
            source_no_resep="RX-SPRINT7-001",
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
            max_attempts=3,
            is_mock=True,
            detected_at=utc_now(),
        )
        session.add(queue)
        session.commit()
        return admin.id, queue.id


def test_attention_filter_includes_incomplete_and_failed_even_after_review(app_container):
    _critical_queue(app_container)
    with app_container.database.session() as session:
        for number, completeness, processing in [('PARTIAL','UNMAPPED','COMPLETED'),('BROKEN','COMPLETE','FAILED'),('CLEAR','COMPLETE','COMPLETED')]:
            session.add(ProcessingQueue(source_no_resep=number,service_unit='UNIT UJI',processing_status=processing,
                review_status='REVIEWED',risk_status='SAFE',completeness_status=completeness,overall_status=completeness,
                alert_level='NONE',priority=0,hold_recommended=False,attempts=1,max_attempts=3,is_mock=True,detected_at=utc_now()))
        session.commit()
    rows = app_container.queue.list_items(status='ATTENTION')
    assert {row.no_resep for row in rows} == {'RX-SPRINT7-001','PARTIAL','BROKEN'}
    assert [row.no_resep for row in app_container.queue.list_items(status='ATTENTION',search='PARTIAL')] == ['PARTIAL']


@pytest.mark.integration
def test_critical_intervention_requires_complete_communication(app_container):
    actor_id, queue_id = _critical_queue(app_container)

    with pytest.raises(InterventionError, match="Media komunikasi wajib"):
        app_container.interventions.save(
            queue_item_id=queue_id,
            actor_user_id=actor_id,
            intervention_type="DRUG_SUBSTITUTION",
            decision="CHANGE_MEDICATION",
            complete=True,
        )

    with pytest.raises(InterventionError, match="Alasan wajib"):
        app_container.interventions.save(
            queue_item_id=queue_id,
            actor_user_id=actor_id,
            intervention_type="CLINICAL_MONITORING",
            decision="CONTINUE_WITH_MONITORING",
            communication_method="PHONE",
            communication_result="ACCEPTED_FULL",
            contacted_party="Dokter DPJP",
            complete=True,
        )


@pytest.mark.integration
def test_completed_intervention_updates_queue_dashboard_and_audit(
    app_container, tmp_path
):
    actor_id, queue_id = _critical_queue(app_container)

    record = app_container.interventions.save(
        queue_item_id=queue_id,
        actor_user_id=actor_id,
        intervention_type="DRUG_SUBSTITUTION",
        decision="CHANGE_MEDICATION",
        communication_method="WHATSAPP_CALL",
        communication_result="ACCEPTED_FULL",
        contacted_party="Dokter DPJP",
        notes="Dokter menyetujui penggantian obat.",
        complete=True,
    )

    assert record.status == "COMPLETED"
    assert record.risk_status == "CRITICAL"
    with app_container.database.session() as session:
        queue = session.get(ProcessingQueue, queue_id)
        assert queue.review_status == "INTERVENTION_COMPLETED"
        assert session.scalar(
            select(PharmacistIntervention).where(
                PharmacistIntervention.queue_item_id == queue_id
            )
        ) is not None
        audit = session.scalars(
            select(AuditLog).where(AuditLog.action == "INTERVENTION_CREATED")
        ).one()
        assert json.loads(audit.details_json)["status"] == "COMPLETED"

    summary = app_container.dashboard.summary()
    assert summary.prescriptions_screened == 1
    assert summary.critical == 1
    assert summary.interventions_completed == 1
    assert summary.acceptance_rate == 100
    units = app_container.dashboard.by_unit()
    assert units[0].service_unit == "DEPO FARMASI"
    assert units[0].interventions == 1

    exported = app_container.dashboard.export_aggregate_csv(
        tmp_path / "laporan-sprint7.csv", actor_id
    )
    content = exported.read_text(encoding="utf-8-sig")
    assert "DASHBOARD KAJIAN POTENSI INTERAKSI OBAT" in content
    assert "bukan bukti kesalahan dokter atau apoteker" in content
    assert "DEPO FARMASI" in content
    assert "pasien" not in content.casefold()


@pytest.mark.integration
def test_dashboard_supports_month_quarter_year_and_percentages(app_container):
    with app_container.database.session() as session:
        for no_resep, detected_at, risk in (
            ("RX-JAN", datetime(2026, 1, 10), "CRITICAL"),
            ("RX-FEB", datetime(2026, 2, 10), "HIGH_RISK"),
            ("RX-APR", datetime(2026, 4, 10), "SAFE"),
            ("RX-OLD", datetime(2025, 12, 10), "REVIEW"),
        ):
            session.add(
                ProcessingQueue(
                    source_no_resep=no_resep,
                    service_unit="DEPO UJI",
                    processing_status="COMPLETED",
                    review_status="NEW",
                    risk_status=risk,
                    completeness_status="COMPLETE",
                    overall_status=risk,
                    alert_level="NONE",
                    priority=0,
                    hold_recommended=risk == "CRITICAL",
                    attempts=1,
                    max_attempts=3,
                    is_mock=True,
                    detected_at=detected_at,
                )
            )
        session.commit()

    january = app_container.dashboard.summary("MONTH", date(2026, 1, 1))
    first_quarter = app_container.dashboard.summary(
        "QUARTER", date(2026, 2, 1)
    )
    year = app_container.dashboard.summary("YEAR", date(2026, 8, 1))
    all_data = app_container.dashboard.summary("ALL", date(2026, 8, 1))
    trend = app_container.dashboard.monthly_trend(2026)

    assert january.period_label == "Januari 2026"
    assert january.prescriptions_screened == 1
    assert january.critical_rate == 100
    assert first_quarter.period_label == "Triwulan I 2026"
    assert first_quarter.prescriptions_screened == 2
    assert first_quarter.high_risk_rate == 100
    assert year.prescriptions_screened == 3
    assert all_data.prescriptions_screened == 4
    assert len(trend) == 12
    assert trend[0].critical_rate == 100
    assert trend[1].high_risk_rate == 100
