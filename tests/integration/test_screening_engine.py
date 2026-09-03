from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from emss.app import build_application
from emss.config.settings import AppEnvironment
from emss.database.catalog_models import (
    ActiveIngredient,
    DrugComponentMapping,
    DrugMaster,
)
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.database.models import AuditLog
from emss.database.monitoring_models import MonitorEvent
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.database.screening_models import PrescriptionRevision, Screening
from emss.domain.knowledge import canonical_pair
from emss.services.screening import (
    PrescriptionInput,
    PrescriptionItemInput,
    ScreeningUnavailableError,
)
from emss.services.queue import QueueError
from emss.utils.time import utc_now


def _admin(container):
    return container.users.create_first_admin(
        username="admin.screening",
        display_name="Admin Screening",
        password="Frasa aman admin screening!",
    )


def _seed(
    container,
    admin_id: str,
    *,
    version_status: str = "PUBLISHED",
    rule_status: str = "INTERACTION_FOUND",
    severity_code: str = "CONTRAINDICATED",
    severity_rank: int = 4,
    app_severity: str | None = "CRITICAL",
    validation_status: str = "CONFIRMED",
    approved_mapping: bool = True,
    combination: bool = False,
) -> tuple[str, tuple[str, ...]]:
    with container.database.session() as session:
        ingredients = {}
        for name in ("zat a", "zat b", "zat c"):
            row = ActiveIngredient(
                standard_name=name, normalized_name=name
            )
            session.add(row)
            session.flush()
            ingredients[name] = row
        version = KnowledgeBaseVersion(
            version_code=f"KB-{version_status}-{rule_status}-{severity_code}",
            title="KB uji",
            status=version_status,
            created_by=admin_id,
        )
        session.add(version)
        session.flush()
        low, high, pair_key = canonical_pair("zat a", "zat b")
        rule = DdiRule(
            knowledge_base_version_id=version.id,
            ingredient_low_id=ingredients[low].id,
            ingredient_high_id=ingredients[high].id,
            pair_key=pair_key,
            interaction_status=rule_status,
            severity_code=severity_code,
            severity_rank=severity_rank,
            app_severity=app_severity,
            clinical_effect="Efek klinis uji",
            recommendation="Rekomendasi uji",
            monitoring="Monitoring uji",
            source_name="Sumber uji",
            source_validation_status=validation_status,
            activation_status=(
                "ACTIVE" if version_status == "PUBLISHED" else "DRAFT"
            ),
            clinical_review_required=False,
            clinical_review_resolved=True,
            record_status=version_status,
            is_enabled=version_status == "PUBLISHED",
            created_by=admin_id,
            updated_by=admin_id,
        )
        session.add(rule)

        codes = []
        drug_specs = (
            (("zat a", "zat c"), "KOMBO")
            if combination
            else (("zat a",), "OBAT-A")
        )
        specs = [(drug_specs[1], drug_specs[0]), ("OBAT-B", ("zat b",))]
        for code, component_names in specs:
            drug = DrugMaster(
                khanza_code=code,
                display_name=code,
                normalized_name=code.casefold(),
                source_version="TEST",
                source_mapping_status="MAPPED",
                review_status=(
                    "APPROVED" if approved_mapping else "PENDING_REVIEW"
                ),
                mapping_method="TEST",
                component_count=len(component_names),
            )
            session.add(drug)
            session.flush()
            for order, name in enumerate(component_names, start=1):
                session.add(
                    DrugComponentMapping(
                        drug_id=drug.id,
                        ingredient_id=ingredients[name].id,
                        component_order=order,
                        source_mapping_status="MAPPED",
                        mapping_method="TEST",
                        review_status=(
                            "APPROVED"
                            if approved_mapping
                            else "PENDING_REVIEW"
                        ),
                        is_active=approved_mapping,
                        source_version="TEST",
                    )
                )
            codes.append(code)
        session.commit()
        return version.id, tuple(codes)


def _prescription(
    codes: tuple[str, ...], *, no_resep: str = "RX-001", quantity: str = "1"
) -> PrescriptionInput:
    return PrescriptionInput(
        no_resep=no_resep,
        patient_id="RM-001",
        patient_name="Pasien Uji",
        items=tuple(
            PrescriptionItemInput(
                source_item_key=str(index),
                khanza_code=code,
                display_name=code,
                quantity=quantity,
                directions="1 x 1",
                route="oral",
            )
            for index, code in enumerate(codes, start=1)
        ),
    )


@pytest.mark.integration
def test_engine_finds_interaction_reuses_hash_and_creates_revision(
    app_container,
) -> None:
    admin = _admin(app_container)
    version_id, codes = _seed(app_container, admin.id)
    original = _prescription(codes)

    first = app_container.screening.screen(
        original, admin.id, version_id=version_id
    )
    repeated = app_container.screening.screen(
        original, admin.id, version_id=version_id
    )
    changed = app_container.screening.screen(
        replace(
            original,
            items=(
                replace(original.items[0], quantity="2"),
                original.items[1],
            ),
        ),
        admin.id,
        version_id=version_id,
    )

    assert first.risk_status == "CRITICAL"
    assert first.completeness_status == "COMPLETE"
    assert first.pairs[0].classification == "INTERACTION_FOUND"
    assert repeated.screening_id == first.screening_id and repeated.reused
    assert changed.revision_number == 2
    assert changed.prescription_hash != first.prescription_hash
    with app_container.database.session() as session:
        assert (
            session.scalar(select(func.count()).select_from(PrescriptionRevision))
            == 2
        )
        assert session.scalar(select(func.count()).select_from(Screening)) == 2
        assert "DDI_SCREENING_REUSED" in set(
            session.scalars(select(AuditLog.action)).all()
        )


@pytest.mark.integration
def test_unmapped_and_quick_closure_are_not_safe(app_container) -> None:
    admin = _admin(app_container)
    version_id, codes = _seed(
        app_container,
        admin.id,
        rule_status="ASSESSED_NO_INTERACTION",
        severity_code="NONE",
        severity_rank=0,
        app_severity=None,
        validation_status="NO_INTERACTION_QUICK_CLOSURE",
    )
    quick = app_container.screening.screen(
        _prescription(codes), admin.id, version_id=version_id
    )
    unmapped = app_container.screening.screen(
        PrescriptionInput(
            no_resep="RX-UNMAPPED",
            items=(
                PrescriptionItemInput("1", "TIDAK-ADA", "Tidak Ada"),
            ),
        ),
        admin.id,
        version_id=version_id,
    )

    assert quick.risk_status == "SAFE"
    assert quick.completeness_status == "NOT_ASSESSED"
    assert quick.overall_status == "NOT_ASSESSED"
    assert quick.pairs[0].classification == "PAIR_NOT_ASSESSED"
    assert unmapped.completeness_status == "UNMAPPED"
    assert unmapped.unmapped_drug_count == 1


@pytest.mark.integration
def test_final_prescription_detects_recent_duplicate_from_internal_history(app_container) -> None:
    admin = _admin(app_container)
    version_id, codes = _seed(
        app_container, admin.id, rule_status='ASSESSED_NO_INTERACTION',
        severity_code='NONE', severity_rank=0, app_severity=None,
    )
    now = utc_now()
    first = app_container.screening.screen(
        replace(_prescription(codes, no_resep='RX-PRIOR'), source_changed_at=now - timedelta(minutes=5),
            source_status='DIPROSES_FARMASI', source_verified=True),
        admin.id, version_id=version_id,
    )
    with app_container.database.session() as session:
        session.add(MonitorEvent(adapter_code='mysql', no_resep='RX-PRIOR',
            sequence=1, event_type='NEW', fingerprint='a' * 64,
            source_status='DIPROSES_FARMASI', snapshot_json='{}', state='COMPLETED',
            screening_id=first.screening_id, completed_at=now - timedelta(minutes=4)))
        session.commit()
    latest = app_container.screening.screen(
        PrescriptionInput(no_resep='RX-LATEST', patient_id='RM-001', patient_name='Pasien Uji',
            source_changed_at=now, source_status='DIPROSES_FARMASI', source_verified=True,
            items=(PrescriptionItemInput('1', codes[0], codes[0], directions='1 x 1'),)),
        admin.id, version_id=version_id,
    )
    duplicates = [issue for issue in latest.issues if issue.issue_type == 'DUPLICATE_THERAPY']
    assert latest.risk_status == 'REVIEW'
    assert duplicates and 'RX-PRIOR' in duplicates[0].message


@pytest.mark.integration
def test_prescription_matches_zero_padded_khanza_code_with_name_variant(app_container):
    admin = _admin(app_container)
    version_id, codes = _seed(app_container, admin.id)
    with app_container.database.session() as session:
        drugs = session.scalars(select(DrugMaster).where(DrugMaster.khanza_code.in_(codes))).all()
        by_code = {drug.khanza_code: drug for drug in drugs}
        first, second = by_code[codes[0]], by_code[codes[1]]
        first.khanza_code, first.display_name, first.normalized_name = '03795', 'Obat A', 'obat a'
        second.khanza_code, second.display_name, second.normalized_name = '00012', 'Obat B', 'obat b'
        session.commit()
    matched = PrescriptionInput(no_resep='RX-PADDED', items=(
        PrescriptionItemInput('1', '000003795', 'Obat A', '1', '', '', ''),
        PrescriptionItemInput('2', '12', 'Obat B', '1', '', '', ''),
    ))
    screening = app_container.screening.screen(matched, admin.id, version_id=version_id)
    assert screening.completeness_status == 'COMPLETE'

    conflict = PrescriptionInput(no_resep='RX-PADDED-CONFLICT', items=(
        PrescriptionItemInput('1', '3795', 'Obat Lain', '1', '', '', ''),
        PrescriptionItemInput('2', '12', 'Obat B', '1', '', '', ''),
    ))
    result = app_container.screening.screen(conflict, admin.id, version_id=version_id)
    assert result.completeness_status == 'COMPLETE'


@pytest.mark.integration
def test_combination_components_are_not_checked_against_each_other(
    app_container,
) -> None:
    admin = _admin(app_container)
    version_id, codes = _seed(
        app_container, admin.id, combination=True
    )

    result = app_container.screening.screen(
        _prescription(codes), admin.id, version_id=version_id
    )

    assert result.ingredient_count == 3
    assert result.pair_count == 2
    assert {pair.pair_key for pair in result.pairs} == {
        "zat a || zat b",
        "zat b || zat c",
    }
    assert result.completeness_status == "NOT_ASSESSED"
    assert result.risk_status == "CRITICAL"


@pytest.mark.integration
def test_mock_allows_draft_pending_mapping_but_production_blocks(
    settings,
) -> None:
    container = build_application(settings)
    try:
        admin = _admin(container)
        version_id, codes = _seed(
            container,
            admin.id,
            version_status="DRAFT",
            approved_mapping=False,
        )
        mock = container.screening.screen(
            _prescription(codes, no_resep="MOCK-DRAFT"),
            admin.id,
            mock_mode=True,
            version_id=version_id,
        )
        assert mock.is_mock and mock.risk_status == "CRITICAL"

        container.settings.environment = AppEnvironment.PRODUCTION
        with pytest.raises(ScreeningUnavailableError, match="development/test"):
            container.screening.screen(
                _prescription(codes, no_resep="MOCK-PROD"),
                admin.id,
                mock_mode=True,
                version_id=version_id,
            )
    finally:
        container.close()


@pytest.mark.integration
def test_normal_mode_treats_pending_mapping_as_unmapped(app_container) -> None:
    admin = _admin(app_container)
    version_id, codes = _seed(
        app_container, admin.id, approved_mapping=False
    )

    result = app_container.screening.screen(
        _prescription(codes), admin.id, version_id=version_id
    )

    assert result.completeness_status == "UNMAPPED"
    assert result.unmapped_drug_count == 2


@pytest.mark.integration
def test_mock_service_runs_critical_revision_and_unmapped(app_container) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        approved_mapping=False,
    )

    critical = app_container.mock_prescriptions.simulate("CRITICAL", admin.id)
    revision = app_container.mock_prescriptions.simulate("REVISION", admin.id)
    unmapped = app_container.mock_prescriptions.simulate("UNMAPPED", admin.id)

    assert critical.risk_status == "CRITICAL"
    assert revision.revision_number == 2
    assert unmapped.completeness_status == "UNMAPPED"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "rule_status", "severity_code", "rank", "app_status", "expected"),
    [
        (
            "HIGH_RISK",
            "INTERACTION_FOUND",
            "SERIOUS",
            3,
            "HIGH_RISK",
            "HIGH_RISK",
        ),
        (
            "NOT_ASSESSED",
            "NOT_ASSESSABLE",
            "NONE",
            0,
            None,
            "NOT_ASSESSED",
        ),
    ],
)
def test_mock_service_selects_requested_scenario(
    app_container,
    scenario,
    rule_status,
    severity_code,
    rank,
    app_status,
    expected,
) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        rule_status=rule_status,
        severity_code=severity_code,
        severity_rank=rank,
        app_severity=app_status,
        approved_mapping=False,
    )

    result = app_container.mock_prescriptions.simulate(scenario, admin.id)

    assert expected in {result.risk_status, result.completeness_status}


@pytest.mark.integration
def test_mock_service_rejects_unknown_scenario(app_container) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        approved_mapping=False,
    )

    with pytest.raises(ScreeningUnavailableError, match="tidak dikenal"):
        app_container.mock_prescriptions.simulate("UNKNOWN", admin.id)


@pytest.mark.integration
def test_screening_enters_one_grouped_queue_alert_and_can_be_reviewed(
    app_container,
) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        approved_mapping=False,
    )
    screened = app_container.mock_prescriptions.simulate("CRITICAL", admin.id)

    queued = app_container.queue.enqueue_screening(screened.screening_id)
    repeated = app_container.queue.enqueue_screening(screened.screening_id)
    detail = app_container.queue.get_detail(queued.item.id)

    assert queued.item.risk_status == "CRITICAL"
    assert queued.item.hold_recommended
    assert queued.notify
    assert queued.alert_title == "Risiko kritis"
    assert repeated.reused and repeated.item.id == queued.item.id
    assert len(detail.pairs) == screened.pair_count
    with app_container.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(ProcessingQueue)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AlertEvent)
        ) == 1

    app_container.queue.mark_alert_shown(queued.alert_id)
    app_container.queue.acknowledge(queued.item.id, admin.id)
    reviewed = app_container.queue.get_detail(queued.item.id)
    assert reviewed.item.review_status == "REVIEWED"


@pytest.mark.integration
def test_runtime_suppression_is_persistent_audited_and_not_realerted(
    app_container,
) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        approved_mapping=False,
    )
    screened = app_container.mock_prescriptions.simulate("CRITICAL", admin.id)
    queued = app_container.queue.enqueue_screening(screened.screening_id)

    changed = app_container.queue.suppress_alert(
        queued.alert_id, "ADVISORY_GATE_BLOCKED"
    )
    repeated = app_container.queue.enqueue_screening(screened.screening_id)

    assert changed
    assert repeated.reused
    assert not repeated.notify
    with app_container.database.session() as session:
        alert = session.get(AlertEvent, queued.alert_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ALERT_SUPPRESSED_BY_RUNTIME_MODE"
            )
        )
        assert alert.status == "SUPPRESSED"
        assert json.loads(audit.details_json) == {
            "alert_level": "CRITICAL",
            "reason": "ADVISORY_GATE_BLOCKED",
        }
        assert app_container.audit.verify_chain(session)

    assert not app_container.queue.suppress_alert(
        queued.alert_id, "ADVISORY_GATE_BLOCKED"
    )
    with pytest.raises(QueueError, match="Alasan penahanan"):
        app_container.queue.suppress_alert(queued.alert_id, "UNKNOWN")


@pytest.mark.integration
def test_not_assessed_alert_is_not_safe_and_queue_filters_work(
    app_container,
) -> None:
    admin = _admin(app_container)
    _seed(
        app_container,
        admin.id,
        version_status="DRAFT",
        rule_status="NOT_ASSESSABLE",
        severity_code="NONE",
        severity_rank=0,
        app_severity=None,
        approved_mapping=False,
    )
    screened = app_container.mock_prescriptions.simulate(
        "NOT_ASSESSED", admin.id
    )
    queued = app_container.queue.enqueue_screening(screened.screening_id)

    assert queued.item.risk_status == "SAFE"
    assert queued.item.completeness_status == "NOT_ASSESSED"
    assert queued.item.alert_level == "TOAST"
    assert "belum dinilai" in queued.alert_message
    assert len(
        app_container.queue.list_items(
            service_unit="FARMASI MOCK", status="NOT_ASSESSED"
        )
    ) == 1
    assert app_container.queue.summary().incomplete == 1


@pytest.mark.integration
def test_failed_queue_supports_manual_retry_and_dead_letter(
    app_container,
) -> None:
    admin = _admin(app_container)
    item_id = app_container.queue.record_failure(
        no_resep="RX-ERROR",
        service_unit="DEPO IGD",
        error_message="Koneksi sumber terputus",
        max_attempts=1,
    )

    status = app_container.queue.retry(item_id, admin.id)

    assert status == "DEAD_LETTER"
    assert app_container.queue.summary().dead_letter == 1
    queued_id = app_container.queue.record_failure(
        no_resep="RX-RETRY",
        error_message="Gagal sementara",
        max_attempts=3,
    )
    assert app_container.queue.retry(queued_id, admin.id) == "QUEUED"
    with pytest.raises(QueueError, match="gagal/dead-letter"):
        app_container.queue.retry(queued_id, admin.id)
