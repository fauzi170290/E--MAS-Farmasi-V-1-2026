from __future__ import annotations

import csv
import io
import json
import hashlib
import zipfile
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.importexport.xlsx_writer import XlsxSheet, write_xlsx
from emss.database.intervention_models import PharmacistIntervention
from emss.database.knowledge_models import KnowledgeBaseVersion
from emss.database.models import AuditLog
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.database.validation_models import (
    AdvisoryPilotActivation,
    AdvisoryPilotSessionLedger,
    AdvisoryPilotSafetyControl,
    AdvisoryPilotShiftCloseout,
    PilotEvidenceVerification,
    UatChecklistItem,
    UatSession,
    ValidationCampaign,
)
from emss.services.clinical_validation import (
    ClinicalValidationError,
    ClinicalValidationPermissionError,
)
from emss.services.screening import DdiScreeningService
from emss.services.clinical_validation import DEFAULT_UAT_ITEMS, VALIDATION_HEADERS
from emss.utils.time import utc_now


def _admin(container):
    return container.users.create_first_admin(
        username="admin.validation",
        display_name="Admin Validasi",
        password="Validasi#Aman2026",
    )


def _published_knowledge_base(container, actor, code="KB-VALIDATION"):
    now = utc_now()
    with container.database.session() as session:
        version = KnowledgeBaseVersion(
            version_code=code,
            title=f"Knowledge Base {code}",
            status="PUBLISHED",
            created_by=actor.id,
            published_by=actor.id,
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(version)
        session.commit()
        return version.id


def _provenance_campaign(container, actor, suffix):
    knowledge_id = _published_knowledge_base(
        container, actor, f"KB-{suffix}"
    )
    now = utc_now()
    with container.database.session() as session:
        fingerprint = container.medication_safety.configuration_fingerprint(
            session
        )
        campaign = ValidationCampaign(
            name=f"Validasi {suffix}",
            source_filename=f"validation-{suffix}.xlsx",
            source_checksum=(suffix.casefold() * 64)[:64],
            application_version=__version__,
            screening_engine_version=DdiScreeningService.ENGINE_VERSION,
            knowledge_base_version_id=knowledge_id,
            safety_configuration_fingerprint=fingerprint,
            created_by=actor.id,
            created_at=now,
            updated_at=now,
        )
        session.add(campaign)
        session.commit()
        return campaign.id


def _row(case_id: str, severity: str, *, compound: bool = False, revision: bool = False):
    expected = {
        "case_id": case_id,
        "daftar_obat": "OBAT-A; OBAT-B",
        "context_klinis": "Kasus sintetis",
        "expected_pairs": "zat a || zat b",
        "expected_highest_severity": severity,
        "expected_duplicate_therapy": "TIDAK",
        "expected_polypharmacy": "TIDAK",
        "expected_high_alert": "TIDAK",
        "expected_lasa": "TIDAK",
        "expected_unmapped": "TIDAK",
        "expected_alert": "YA",
        "checks_compound": "YA" if compound else "TIDAK",
        "checks_revision": "YA" if revision else "TIDAK",
        "actual_result": "Hasil sesuai",
        "actual_highest_severity": severity,
        "actual_overall_status": severity,
        "actual_duplicate_therapy": "TIDAK",
        "actual_polypharmacy": "TIDAK",
        "actual_high_alert": "TIDAK",
        "actual_lasa": "TIDAK",
        "actual_unmapped": "TIDAK",
        "actual_alert": "YA",
        "duplicate_output_count": 0,
        "compound_pass": "YA" if compound else "",
        "revision_pass": "YA" if revision else "",
        "match": "",
        "reviewer": "Apoteker Uji",
        "review_date": date(2026, 8, 5),
        "notes": "Tanpa data pasien",
    }
    return [expected[name] for name in VALIDATION_HEADERS]


def _ready_advisory_gate(container, actor, tmp_path, suffix="ACTIVATION"):
    _published_knowledge_base(container, actor, f"KB-{suffix}")
    workbook = tmp_path / f"validation-{suffix.casefold()}.xlsx"
    write_xlsx(
        workbook,
        [
            XlsxSheet(
                "VALIDATION_CASES",
                [
                    VALIDATION_HEADERS,
                    _row(f"CRIT-{suffix}", "CRITICAL", compound=True),
                    _row(f"HR-{suffix}", "HIGH_RISK", revision=True),
                ],
                [20] * len(VALIDATION_HEADERS),
            )
        ],
    )
    imported = container.clinical_validation.import_workbook(
        workbook, actor.id
    )
    items = container.clinical_validation.uat_items(actor.id)
    for item in items:
        container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            actor.id,
            actor.display_name,
            actual_result="Sesuai",
        )
    container.clinical_validation.approve_uat("APOTEKER", actor.id)
    container.clinical_validation.approve_uat("IT", actor.id)
    assert container.clinical_validation.evaluate_gate(actor.id).ready
    return imported.campaign_id, items


def _activate_with_two_people(
    container, admin, suffix, duration_hours=24
):
    clinical = container.users.create_user(
        username=f"clinical.{suffix.casefold()}",
        display_name=f"Clinical {suffix}",
        password="Clinical#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    request = container.clinical_validation.request_advisory_pilot_activation(
        admin.id, duration_hours
    )
    active = container.clinical_validation.approve_advisory_pilot_activation(
        request.id, clinical.id
    )
    return active, clinical


@pytest.mark.integration
def test_validation_gate_requires_cases_uat_and_dual_signoff(app_container, tmp_path):
    admin = _admin(app_container)
    _published_knowledge_base(app_container, admin)
    workbook = tmp_path / "validation.xlsx"
    write_xlsx(
        workbook,
        [
            XlsxSheet(
                "VALIDATION_CASES",
                [VALIDATION_HEADERS, _row("CRIT-1", "CRITICAL", compound=True), _row("HR-1", "HIGH_RISK", revision=True)],
                [20] * len(VALIDATION_HEADERS),
            )
        ],
    )
    imported = app_container.clinical_validation.import_workbook(workbook, admin.id)
    assert imported.total_cases == imported.reviewed_cases == imported.matched_cases == 2

    before = app_container.clinical_validation.evaluate_gate(admin.id)
    assert not before.ready
    assert "Checklist UAT belum seluruhnya PASS" in before.blockers

    items = app_container.clinical_validation.uat_items(admin.id)
    assert len(items) == len(DEFAULT_UAT_ITEMS)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id, "PASS", admin.id, "Admin Validasi", actual_result="Sesuai"
        )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)

    final = app_container.clinical_validation.evaluate_gate(admin.id)
    assert final.ready
    assert final.blockers == ()
    assert final.status == "READY_FOR_ADVISORY_PILOT"


@pytest.mark.integration
def test_uat_evidence_change_revokes_only_owning_approval(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _published_knowledge_base(app_container, admin)
    workbook = tmp_path / "validation-reapproval.xlsx"
    write_xlsx(
        workbook,
        [
            XlsxSheet(
                "VALIDATION_CASES",
                [
                    VALIDATION_HEADERS,
                    _row("CRIT-REAPPROVE", "CRITICAL", compound=True),
                    _row("HR-REAPPROVE", "HIGH_RISK", revision=True),
                ],
                [20] * len(VALIDATION_HEADERS),
            )
        ],
    )
    app_container.clinical_validation.import_workbook(workbook, admin.id)
    items = app_container.clinical_validation.uat_items(admin.id)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            admin.id,
            "Admin Validasi",
            actual_result="Sesuai",
        )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)
    assert app_container.clinical_validation.evaluate_gate(admin.id).ready

    clinical_item = next(row for row in items if row.owner_role == "APOTEKER")
    clinical_revocation = app_container.clinical_validation.update_uat_item(
        clinical_item.id,
        "FAIL",
        admin.id,
        "Admin Validasi",
        actual_result="Perlu uji ulang",
    )
    clinical_revoked = app_container.clinical_validation.evaluate_gate(admin.id)
    assert clinical_revocation == "APOTEKER"
    assert not clinical_revoked.ready
    assert not clinical_revoked.pharmacist_approved
    assert clinical_revoked.it_approved
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        assert uat.pharmacist_approved_by is None
        assert uat.pharmacist_approved_at is None
        assert uat.pharmacist_approved_version is None
        assert uat.pharmacist_approved_campaign_id is None
        assert uat.it_approved_by == admin.id
        assert uat.it_approved_at is not None
        assert uat.it_approved_version == __version__
        assert uat.it_approved_campaign_id is not None

    app_container.clinical_validation.update_uat_item(
        clinical_item.id,
        "PASS",
        admin.id,
        "Admin Validasi",
        actual_result="Sesuai setelah uji ulang",
    )
    assert not app_container.clinical_validation.evaluate_gate(admin.id).ready
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    assert app_container.clinical_validation.evaluate_gate(admin.id).ready

    it_item = next(row for row in items if row.owner_role == "IT")
    it_revocation = app_container.clinical_validation.update_uat_item(
        it_item.id,
        "PASS",
        admin.id,
        "Admin Validasi",
        actual_result="Bukti IT diperbarui",
    )
    it_revoked = app_container.clinical_validation.evaluate_gate(admin.id)
    assert it_revocation == "IT"
    assert not it_revoked.ready
    assert it_revoked.pharmacist_approved
    assert not it_revoked.it_approved
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        assert uat.pharmacist_approved_by == admin.id
        assert uat.pharmacist_approved_at is not None
        assert uat.pharmacist_approved_version == __version__
        assert uat.pharmacist_approved_campaign_id is not None
        assert uat.it_approved_by is None
        assert uat.it_approved_at is None
        assert uat.it_approved_version is None
        assert uat.it_approved_campaign_id is None

    app_container.clinical_validation.approve_uat("IT", admin.id)
    assert app_container.clinical_validation.evaluate_gate(admin.id).ready
    unchanged = app_container.clinical_validation.update_uat_item(
        it_item.id,
        "PASS",
        admin.id,
        "Admin Validasi",
        actual_result="Bukti IT diperbarui",
    )
    assert unchanged is None
    assert app_container.clinical_validation.evaluate_gate(admin.id).ready

    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        revocations = session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "UAT_APPROVAL_REVOKED")
            .order_by(AuditLog.occurred_at)
        ).all()
        assert uat.pharmacist_approved_by == admin.id
        assert uat.it_approved_by == admin.id
        details = [json.loads(row.details_json) for row in revocations]
        assert [detail["approval_type"] for detail in details] == [
            "APOTEKER",
            "IT",
        ]
        assert all(
            detail["reason"] == "CHECKLIST_EVIDENCE_CHANGED"
            for detail in details
        )
        assert all(
            set(detail) == {"approval_type", "item_code", "reason"}
            for detail in details
        )
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_gate_rejects_stale_or_incomplete_legacy_uat_approval(app_container):
    admin = _admin(app_container)
    _provenance_campaign(app_container, admin, "FRESHNESS")
    items = app_container.clinical_validation.uat_items(admin.id)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            admin.id,
            "Admin Validasi",
            actual_result="Sesuai",
        )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)

    baseline = app_container.clinical_validation.evaluate_gate(admin.id)
    assert baseline.pharmacist_approved
    assert baseline.it_approved

    clinical_item_id = next(
        item.id for item in items if item.owner_role == "APOTEKER"
    )
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        clinical_item = session.get(UatChecklistItem, clinical_item_id)
        uat.pharmacist_approved_at = clinical_item.tested_at - timedelta(
            seconds=1
        )
        session.commit()

    stale = app_container.clinical_validation.evaluate_gate(admin.id)
    assert not stale.pharmacist_approved
    assert stale.it_approved
    assert (
        "Persetujuan UAT Apoteker tidak lagi sesuai bukti terbaru"
        in stale.blockers
    )
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        assert uat.pharmacist_approved

    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    refreshed = app_container.clinical_validation.evaluate_gate(admin.id)
    assert refreshed.pharmacist_approved
    assert refreshed.it_approved

    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        uat.it_approved_by = None
        session.commit()

    incomplete = app_container.clinical_validation.evaluate_gate(admin.id)
    assert incomplete.pharmacist_approved
    assert not incomplete.it_approved
    assert "Persetujuan UAT IT tidak lagi sesuai bukti terbaru" in incomplete.blockers

    app_container.clinical_validation.approve_uat("IT", admin.id)
    repaired = app_container.clinical_validation.evaluate_gate(admin.id)
    assert repaired.pharmacist_approved
    assert repaired.it_approved


@pytest.mark.integration
def test_gate_requires_uat_signoff_for_running_application_version(
    app_container,
):
    admin = _admin(app_container)
    campaign_id = _provenance_campaign(app_container, admin, "VERSION")
    items = app_container.clinical_validation.uat_items(admin.id)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            admin.id,
            "Admin Validasi",
            actual_result="Sesuai",
        )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)

    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        assert uat.pharmacist_approved_version == __version__
        assert uat.it_approved_version == __version__
        uat.pharmacist_approved_version = "0.12.4"
        session.commit()

    old_version = app_container.clinical_validation.evaluate_gate(admin.id)
    assert not old_version.pharmacist_approved
    assert old_version.it_approved
    assert (
        f"Persetujuan UAT Apoteker bukan untuk versi aplikasi {__version__}"
        in old_version.blockers
    )

    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        uat.it_approved_version = None
        session.commit()

    legacy = app_container.clinical_validation.evaluate_gate(admin.id)
    assert legacy.pharmacist_approved
    assert not legacy.it_approved
    assert (
        f"Persetujuan UAT IT bukan untuk versi aplikasi {__version__}"
        in legacy.blockers
    )

    app_container.clinical_validation.approve_uat("IT", admin.id)
    repaired = app_container.clinical_validation.evaluate_gate(admin.id)
    assert repaired.pharmacist_approved
    assert repaired.it_approved

    with app_container.database.session() as session:
        approval_audits = session.scalars(
            select(AuditLog).where(
                AuditLog.action.in_(("UAT_APOTEKER_APPROVED", "UAT_IT_APPROVED"))
            )
        ).all()
        assert approval_audits
        assert all(
            json.loads(row.details_json)["application_version"] == __version__
            and json.loads(row.details_json)["validation_campaign_id"]
            == campaign_id
            and set(json.loads(row.details_json))
            == {
                "application_version",
                "validation_campaign_id",
                "validation_source_checksum",
            }
            for row in approval_audits
        )
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_uat_signoff_is_bound_to_latest_validation_campaign(app_container):
    admin = _admin(app_container)
    first_campaign_id = _provenance_campaign(
        app_container, admin, "CAMPAIGN-FIRST"
    )
    items = app_container.clinical_validation.uat_items(admin.id)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            admin.id,
            "Admin Validasi",
            actual_result="Sesuai",
        )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)
    first = app_container.clinical_validation.evaluate_gate(admin.id)
    assert first.pharmacist_approved
    assert first.it_approved

    second_campaign_id = _provenance_campaign(
        app_container, admin, "CAMPAIGN-SECOND"
    )
    assert second_campaign_id != first_campaign_id
    superseded = app_container.clinical_validation.evaluate_gate(admin.id)
    assert not superseded.pharmacist_approved
    assert not superseded.it_approved
    assert (
        "Persetujuan UAT Apoteker bukan untuk kampanye validasi terbaru"
        in superseded.blockers
    )
    assert (
        "Persetujuan UAT IT bukan untuk kampanye validasi terbaru"
        in superseded.blockers
    )

    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    app_container.clinical_validation.approve_uat("IT", admin.id)
    rebound = app_container.clinical_validation.evaluate_gate(admin.id)
    assert rebound.pharmacist_approved
    assert rebound.it_approved
    with app_container.database.session() as session:
        uat = session.scalar(
            select(UatSession).order_by(UatSession.created_at.desc())
        )
        assert uat.pharmacist_approved_campaign_id == second_campaign_id
        assert uat.it_approved_campaign_id == second_campaign_id
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_uat_signoff_requires_a_validation_campaign(app_container):
    admin = _admin(app_container)
    items = app_container.clinical_validation.uat_items(admin.id)
    for item in items:
        app_container.clinical_validation.update_uat_item(
            item.id,
            "PASS",
            admin.id,
            "Admin Validasi",
            actual_result="Sesuai",
        )

    with pytest.raises(ValueError, match="Kampanye validasi klinis"):
        app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    with pytest.raises(ValueError, match="Gate Advisory Pilot belum lulus"):
        app_container.clinical_validation.request_advisory_pilot_activation(
            admin.id
        )


@pytest.mark.integration
def test_advisory_pilot_requires_explicit_authorized_activation(
    app_container, tmp_path
):
    admin = _admin(app_container)
    campaign_id, _ = _ready_advisory_gate(
        app_container, admin, tmp_path, "PILOT-CONTROL"
    )
    pharmacist = app_container.users.create_user(
        username="apoteker.pilot",
        display_name="Apoteker Pilot",
        password="Pilot#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )

    pending = app_container.clinical_validation.advisory_pilot_status(admin.id)
    assert pending.gate_ready
    assert not pending.active
    assert pending.reason == "NOT_ACTIVATED"
    with pytest.raises(
        ClinicalValidationPermissionError, match="IT Admin atau Super Admin"
    ):
        app_container.clinical_validation.request_advisory_pilot_activation(
            pharmacist.id
        )

    request = app_container.clinical_validation.request_advisory_pilot_activation(
        admin.id
    )
    with pytest.raises(
        ClinicalValidationPermissionError, match="Apoteker, KFT"
    ):
        app_container.clinical_validation.approve_advisory_pilot_activation(
            request.id, admin.id
        )
    activated = app_container.clinical_validation.approve_advisory_pilot_activation(
        request.id, pharmacist.id
    )
    assert activated.active
    assert activated.campaign_id == campaign_id
    assert app_container.clinical_validation.advisory_pilot_status().active
    with pytest.raises(ValueError, match="sudah aktif"):
        app_container.clinical_validation.request_advisory_pilot_activation(
            admin.id
        )

    with app_container.database.session() as session:
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ADVISORY_PILOT_ACTIVATED"
            )
        )
        details = json.loads(audit.details_json)
        assert record.status == "ACTIVE"
        assert record.validation_campaign_id == campaign_id
        assert record.application_version == __version__
        assert record.technical_authorizer_id == admin.id
        assert record.clinical_owner_id == pharmacist.id
        assert record.authorization_request_id == request.id
        assert details["validation_campaign_id"] == campaign_id
        assert details["technical_authorizer_id"] == admin.id
        assert details["clinical_owner_id"] == pharmacist.id
        assert app_container.audit.verify_chain(session)

    deactivated = (
        app_container.clinical_validation.deactivate_advisory_pilot(admin.id)
    )
    assert not deactivated.active
    assert deactivated.reason == "MANUAL_DEACTIVATION"
    assert not app_container.clinical_validation.advisory_pilot_status().active
    with app_container.database.session() as session:
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        assert record.status == "REVOKED"
        assert record.revoked_by == admin.id
        assert record.revoked_at is not None
        assert record.revocation_reason == "MANUAL_DEACTIVATION"
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_advisory_activation_is_revoked_when_signoff_binding_changes(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _, items = _ready_advisory_gate(
        app_container, admin, tmp_path, "PILOT-REBIND"
    )
    activated, clinical = _activate_with_two_people(
        app_container, admin, "rebind"
    )
    clinical_item = next(
        item for item in items if item.owner_role == "APOTEKER"
    )

    app_container.clinical_validation.update_uat_item(
        clinical_item.id,
        "PASS",
        admin.id,
        admin.display_name,
        actual_result="Bukti diperbarui setelah aktivasi",
    )
    app_container.clinical_validation.approve_uat("APOTEKER", admin.id)
    assert app_container.clinical_validation.evaluate_gate(admin.id).ready

    revoked = app_container.clinical_validation.advisory_pilot_status(admin.id)
    assert not revoked.active
    assert revoked.gate_ready
    assert revoked.reason == "ACTIVATION_BINDING_CHANGED"
    assert "tidak lagi sesuai bukti terbaru" in revoked.blockers[0]
    still_revoked = app_container.clinical_validation.advisory_pilot_status(
        admin.id
    )
    assert not still_revoked.active
    assert still_revoked.reason == "NOT_ACTIVATED"

    with app_container.database.session() as session:
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        audits = session.scalars(
            select(AuditLog).where(
                AuditLog.action == "ADVISORY_PILOT_AUTO_REVOKED"
            )
        ).all()
        assert record.status == "REVOKED"
        assert record.revoked_by is None
        assert record.revocation_reason == "ACTIVATION_BINDING_CHANGED"
        assert len(audits) == 1
        assert app_container.audit.verify_chain(session)

    request = app_container.clinical_validation.request_advisory_pilot_activation(
        admin.id
    )
    reactivated = app_container.clinical_validation.approve_advisory_pilot_activation(
        request.id, clinical.id
    )
    assert reactivated.active
    assert reactivated.activation_id != activated.activation_id


@pytest.mark.integration
def test_two_person_authorization_rejects_same_dual_role_user(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-DUAL-ROLE")
    dual_role = app_container.users.create_user(
        username="pilot.dual.role",
        display_name="Pilot Dual Role",
        password="DualRole#Aman2026",
        roles=("IT_ADMIN", "APOTEKER"),
        actor_user_id=admin.id,
    )
    request = app_container.clinical_validation.request_advisory_pilot_activation(
        dual_role.id, 4
    )
    with pytest.raises(
        ClinicalValidationPermissionError, match="pengguna berbeda"
    ):
        app_container.clinical_validation.approve_advisory_pilot_activation(
            request.id, dual_role.id
        )
    assert not app_container.clinical_validation.advisory_pilot_status().active


@pytest.mark.integration
def test_advisory_activation_expires_and_requires_fresh_activation(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-EXPIRY")
    with pytest.raises(ValueError, match="Durasi aktivasi"):
        app_container.clinical_validation.request_advisory_pilot_activation(
            admin.id, 2
        )

    activated, clinical = _activate_with_two_people(
        app_container, admin, "expiry", 4
    )
    assert activated.expires_at is not None
    assert activated.expires_at > activated.activated_at
    with app_container.database.session() as session:
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        record.expires_at = utc_now() - timedelta(seconds=1)
        session.commit()

    expired = app_container.clinical_validation.advisory_pilot_status(admin.id)
    assert not expired.active
    assert expired.gate_ready
    assert expired.reason == "ACTIVATION_EXPIRED"
    assert "masa berlaku" in expired.blockers[0].casefold()
    second_check = app_container.clinical_validation.advisory_pilot_status(
        admin.id
    )
    assert second_check.reason == "NOT_ACTIVATED"
    with app_container.database.session() as session:
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ADVISORY_PILOT_AUTO_REVOKED"
            )
        )
        assert record.status == "REVOKED"
        assert record.revocation_reason == "ACTIVATION_EXPIRED"
        assert json.loads(audit.details_json)["reason"] == "ACTIVATION_EXPIRED"
        assert app_container.audit.verify_chain(session)

    request = app_container.clinical_validation.request_advisory_pilot_activation(
        admin.id, 8
    )
    renewed = app_container.clinical_validation.approve_advisory_pilot_activation(
        request.id, clinical.id
    )
    assert renewed.active
    assert renewed.activation_id != activated.activation_id


@pytest.mark.integration
def test_emergency_stop_is_persistent_and_only_it_can_reset(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-STOP")
    pharmacist = app_container.users.create_user(
        username="apoteker.emergency",
        display_name="Apoteker Emergency",
        password="Emergency#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    request = app_container.clinical_validation.request_advisory_pilot_activation(
        admin.id
    )
    activated = app_container.clinical_validation.approve_advisory_pilot_activation(
        request.id, pharmacist.id
    )
    with pytest.raises(ValueError, match="10-300"):
        app_container.clinical_validation.trigger_advisory_emergency_stop(
            pharmacist.id, "singkat"
        )

    stopped = (
        app_container.clinical_validation.trigger_advisory_emergency_stop(
            pharmacist.id, "Alert tidak konsisten dengan penilaian klinis"
        )
    )
    assert stopped.emergency_stop
    assert not stopped.active
    persisted = app_container.clinical_validation.advisory_pilot_status()
    assert persisted.reason == "EMERGENCY_STOP"
    with pytest.raises(ValueError, match="Emergency stop masih aktif"):
        app_container.clinical_validation.request_advisory_pilot_activation(
            admin.id
        )
    with pytest.raises(
        ClinicalValidationPermissionError, match="IT Admin atau Super Admin"
    ):
        app_container.clinical_validation.reset_advisory_emergency_stop(
            pharmacist.id
        )

    with app_container.database.session() as session:
        control = session.get(AdvisoryPilotSafetyControl, "GLOBAL")
        record = session.get(AdvisoryPilotActivation, activated.activation_id)
        assert control.emergency_stop
        assert control.stopped_by == pharmacist.id
        assert record.status == "REVOKED"
        assert record.revocation_reason == "EMERGENCY_STOP"
        assert app_container.audit.verify_chain(session)

    reset = app_container.clinical_validation.reset_advisory_emergency_stop(
        admin.id
    )
    assert not reset.emergency_stop
    assert not reset.active
    assert reset.reason == "NOT_ACTIVATED"
    request = app_container.clinical_validation.request_advisory_pilot_activation(
        admin.id
    )
    reactivated = app_container.clinical_validation.approve_advisory_pilot_activation(
        request.id, pharmacist.id
    )
    assert reactivated.active
    with app_container.database.session() as session:
        control = session.get(AdvisoryPilotSafetyControl, "GLOBAL")
        actions = set(
            session.scalars(
                select(AuditLog.action).where(
                    AuditLog.action.in_(
                        (
                            "ADVISORY_EMERGENCY_STOP_TRIGGERED",
                            "ADVISORY_EMERGENCY_STOP_RESET",
                        )
                    )
                )
            ).all()
        )
        assert not control.emergency_stop
        assert control.restored_by == admin.id
        assert actions == {
            "ADVISORY_EMERGENCY_STOP_TRIGGERED",
            "ADVISORY_EMERGENCY_STOP_RESET",
        }
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_shift_handover_requires_new_clinical_owner_and_it_approval(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-HANDOVER")
    initial, outgoing = _activate_with_two_people(
        app_container, admin, "outgoing"
    )
    incoming = app_container.users.create_user(
        username="clinical.incoming",
        display_name="Clinical Incoming",
        password="Incoming#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    with pytest.raises(ValueError, match="dirinya"):
        app_container.clinical_validation.request_advisory_shift_handover(
            outgoing.id
        )

    handover = (
        app_container.clinical_validation.request_advisory_shift_handover(
            incoming.id, 8
        )
    )
    assert handover.purpose == "HANDOVER"
    assert handover.status == "PENDING_OUTGOING"
    assert app_container.clinical_validation.advisory_pilot_status().active
    with pytest.raises(ClinicalValidationError, match="tidak tersedia"):
        app_container.clinical_validation.approve_advisory_shift_handover(
            handover.id, admin.id
        )
    with pytest.raises(
        ClinicalValidationPermissionError, match="IT Admin atau Super Admin"
    ):
        app_container.clinical_validation.approve_advisory_shift_handover(
            handover.id, incoming.id
        )

    attested = (
        app_container.clinical_validation.attest_advisory_shift_handover(
            handover.id, outgoing.id
        )
    )
    assert attested.status == "PENDING_TECHNICAL"
    assert attested.outgoing_attested_by == outgoing.id

    completed = app_container.clinical_validation.approve_advisory_shift_handover(
        handover.id, admin.id
    )
    assert completed.active
    assert completed.activation_id != initial.activation_id
    with app_container.database.session() as session:
        previous = session.get(
            AdvisoryPilotActivation, initial.activation_id
        )
        current = session.get(
            AdvisoryPilotActivation, completed.activation_id
        )
        closeout = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id
                == initial.activation_id
            )
        )
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "ADVISORY_SHIFT_HANDOVER_COMPLETED"
            )
        )
        details = json.loads(audit.details_json)
        assert previous.status == "REVOKED"
        assert previous.revocation_reason == "SHIFT_HANDOVER"
        assert current.clinical_owner_id == incoming.id
        assert current.technical_authorizer_id == admin.id
        assert current.shift_expires_at <= current.expires_at
        assert closeout.closeout_type == "HANDOVER"
        assert closeout.outgoing_attested_by == outgoing.id
        assert closeout.incoming_attested_by == incoming.id
        assert details["prior_activation_id"] == initial.activation_id
        assert details["clinical_owner_id"] == incoming.id
        assert app_container.audit.verify_chain(session)
    assert app_container.clinical_validation.verify_pilot_session_ledger(
        admin.id
    )


@pytest.mark.integration
def test_handover_snapshots_unresolved_work_and_ledger_is_immutable(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-LEDGER")
    initial, outgoing = _activate_with_two_people(
        app_container, admin, "ledger-outgoing"
    )
    incoming = app_container.users.create_user(
        username="clinical.ledger.incoming",
        display_name="Clinical Ledger Incoming",
        password="Incoming#Ledger2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    now = utc_now()
    with app_container.database.session() as session:
        queue = ProcessingQueue(
            source_no_resep="HANDOVER-AGGREGATE-ONLY",
            processing_status="COMPLETED",
            review_status="INTERVENTION_OPEN",
            risk_status="CRITICAL",
            completeness_status="COMPLETE",
            overall_status="CRITICAL",
            alert_level="CRITICAL",
            priority=100,
            hold_recommended=True,
            is_mock=False,
            detected_at=now,
        )
        session.add(queue)
        session.flush()
        session.add(
            AlertEvent(
                queue_item_id=queue.id,
                level="CRITICAL",
                status="NEW",
                title="Ringkasan agregat",
                message="Tidak menyimpan identitas pasien pada ledger",
                hold_recommended=True,
                created_at=now,
            )
        )
        session.add(
            PharmacistIntervention(
                queue_item_id=queue.id,
                pharmacist_user_id=outgoing.id,
                status="OPEN",
                intervention_type="Klarifikasi",
                decision="MENUNGGU_DOKTER",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    handover = app_container.clinical_validation.request_advisory_shift_handover(
        incoming.id, 8
    )
    assert handover.unresolved_alerts == 1
    assert handover.unresolved_critical_alerts == 1
    assert handover.unresolved_interventions == 1
    with pytest.raises(
        ClinicalValidationPermissionError, match="pemilik shift saat ini"
    ):
        app_container.clinical_validation.attest_advisory_shift_handover(
            handover.id, incoming.id
        )
    app_container.clinical_validation.attest_advisory_shift_handover(
        handover.id, outgoing.id
    )
    app_container.clinical_validation.approve_advisory_shift_handover(
        handover.id, admin.id
    )

    ledger = app_container.clinical_validation.pilot_session_ledger(admin.id)
    event_types = {entry.event_type for entry in ledger}
    assert {
        "SHIFT_OPENED",
        "HANDOVER_INCOMING_ATTESTED",
        "HANDOVER_OUTGOING_ATTESTED",
        "SHIFT_CLOSED",
    } <= event_types
    with app_container.database.session() as session:
        closeout = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id
                == initial.activation_id
            )
        )
        summary = json.loads(closeout.summary_json)
        assert summary["scope"] == "ALL_NON_MOCK_OUTSTANDING"
        assert "patient" not in closeout.summary_json.casefold()
        with pytest.raises(DatabaseError, match="immutable"):
            session.execute(
                text(
                    "UPDATE advisory_pilot_session_ledger "
                    "SET event_type = 'TAMPERED' WHERE id = 1"
                )
            )
        session.rollback()
    assert app_container.clinical_validation.verify_pilot_session_ledger(
        admin.id
    )


@pytest.mark.integration
def test_only_current_clinical_owner_can_close_shift(app_container, tmp_path):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-CLOSEOUT")
    active, owner = _activate_with_two_people(
        app_container, admin, "closeout-owner"
    )
    other = app_container.users.create_user(
        username="clinical.closeout.other",
        display_name="Clinical Closeout Other",
        password="Other#Closeout2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    with pytest.raises(
        ClinicalValidationPermissionError, match="pemilik klinis aktif"
    ):
        app_container.clinical_validation.close_advisory_shift(
            other.id, "Petugas lain mencoba closeout shift"
        )

    closed = app_container.clinical_validation.close_advisory_shift(
        owner.id, "Seluruh outstanding telah diserahterimakan sesuai prosedur"
    )
    assert not closed.active
    assert closed.reason == "SHIFT_CLOSED_BY_OWNER"
    assert not app_container.clinical_validation.advisory_pilot_status().active
    with app_container.database.session() as session:
        activation = session.get(AdvisoryPilotActivation, active.activation_id)
        closeout = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id
                == active.activation_id
            )
        )
        assert activation.revocation_reason == "SHIFT_CLOSED_BY_OWNER"
        assert closeout.closeout_type == "OWNER_CLOSEOUT"
        assert closeout.outgoing_attested_by == owner.id
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_expired_shift_revokes_still_valid_activation_fail_safe(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-SHIFT-EXPIRY")
    active, _owner = _activate_with_two_people(
        app_container, admin, "shift-expiry", duration_hours=24
    )
    with app_container.database.session() as session:
        activation = session.get(AdvisoryPilotActivation, active.activation_id)
        activation.shift_expires_at = utc_now() - timedelta(seconds=1)
        activation.expires_at = utc_now() + timedelta(hours=6)
        session.commit()

    expired = app_container.clinical_validation.advisory_pilot_status(admin.id)
    assert not expired.active
    assert expired.reason == "SHIFT_EXPIRED"
    with app_container.database.session() as session:
        activation = session.get(AdvisoryPilotActivation, active.activation_id)
        closeout = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id
                == active.activation_id
            )
        )
        assert activation.status == "REVOKED"
        assert activation.revocation_reason == "SHIFT_EXPIRED"
        assert closeout.closeout_type == "SHIFT_EXPIRED"
        assert session.scalar(select(AdvisoryPilotSessionLedger.id)) is not None
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_tampered_pilot_ledger_quarantines_advisory_until_recovered(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-QUARANTINE")
    active, _owner = _activate_with_two_people(
        app_container, admin, "quarantine-owner"
    )
    with app_container.database.session() as session:
        entry = session.scalar(
            select(AdvisoryPilotSessionLedger).order_by(
                AdvisoryPilotSessionLedger.id
            )
        )
        original_payload = entry.payload_json
        session.execute(
            text("DROP TRIGGER trg_pilot_session_ledger_no_update")
        )
        session.execute(
            text(
                "UPDATE advisory_pilot_session_ledger "
                "SET payload_json = :payload WHERE id = :id"
            ),
            {"id": entry.id, "payload": '{"tampered":true}'},
        )
        session.commit()

    quarantined = app_container.clinical_validation.advisory_pilot_status(
        admin.id
    )
    assert not quarantined.active
    assert quarantined.reason == "LEDGER_QUARANTINED"
    with pytest.raises(ClinicalValidationError, match="dikarantina"):
        app_container.clinical_validation.request_advisory_pilot_activation(
            admin.id, 4
        )
    with pytest.raises(ClinicalValidationError, match="masih tidak valid"):
        app_container.clinical_validation.reset_pilot_ledger_quarantine(
            admin.id, "INC-2026-001 restore sedang diverifikasi"
        )
    with app_container.database.session() as session:
        activation = session.get(AdvisoryPilotActivation, active.activation_id)
        control = session.get(AdvisoryPilotSafetyControl, "GLOBAL")
        closeout = session.scalar(
            select(AdvisoryPilotShiftCloseout).where(
                AdvisoryPilotShiftCloseout.activation_id
                == active.activation_id
            )
        )
        assert activation.revocation_reason == (
            "PILOT_LEDGER_INTEGRITY_FAILURE"
        )
        assert control.ledger_quarantine
        assert control.ledger_detected_head_hash is not None
        assert closeout.closeout_type == "PILOT_LEDGER_INTEGRITY_FAILURE"
        assert app_container.audit.verify_chain(session)

        session.execute(
            text(
                "UPDATE advisory_pilot_session_ledger "
                "SET payload_json = :payload WHERE id = :id"
            ),
            {"payload": original_payload, "id": entry.id},
        )
        session.execute(
            text(
                "CREATE TRIGGER trg_pilot_session_ledger_no_update "
                "BEFORE UPDATE ON advisory_pilot_session_ledger "
                "BEGIN SELECT RAISE(ABORT, "
                "'pilot session ledger is immutable'); END"
            )
        )
        session.commit()

    assert app_container.clinical_validation.verify_pilot_session_ledger(
        admin.id
    )
    recovered = (
        app_container.clinical_validation.reset_pilot_ledger_quarantine(
            admin.id, "INC-2026-001 backup terverifikasi telah dipulihkan"
        )
    )
    assert not recovered.active
    assert recovered.reason == "NOT_ACTIVATED"
    with app_container.database.session() as session:
        control = session.get(AdvisoryPilotSafetyControl, "GLOBAL")
        assert not control.ledger_quarantine
        assert control.ledger_quarantine_cleared_by == admin.id
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_pilot_evidence_export_is_checksummed_and_contains_no_phi(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "PILOT-EVIDENCE")
    active, owner = _activate_with_two_people(
        app_container, admin, "evidence-owner"
    )
    app_container.clinical_validation.close_advisory_shift(
        owner.id, "Closeout untuk paket bukti pilot tanpa identitas pasien"
    )
    result = app_container.clinical_validation.export_pilot_session_evidence(
        tmp_path / "pilot-evidence", admin.id
    )
    assert result.path.suffix == ".zip"
    assert result.path.is_file()
    assert result.ledger_entries >= 2
    assert result.closeouts == 1
    assert result.checksum_sha256 == hashlib.sha256(
        result.path.read_bytes()
    ).hexdigest()
    with zipfile.ZipFile(result.path) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "pilot_session_ledger.csv",
            "pilot_shift_closeouts.csv",
        }
        manifest = json.loads(archive.read("manifest.json"))
        ledger_csv = archive.read("pilot_session_ledger.csv")
        closeout_csv = archive.read("pilot_shift_closeouts.csv")
    assert manifest["format"] == "EMSS_PILOT_EVIDENCE_V1"
    assert manifest["contains_patient_identity"] is False
    assert manifest["schema_revision"] == "0029_kfa_identity"
    assert manifest["ledger_head_hash"] == result.ledger_head_hash
    assert manifest["files"]["pilot_session_ledger.csv"] == (
        hashlib.sha256(ledger_csv).hexdigest()
    )
    assert manifest["files"]["pilot_shift_closeouts.csv"] == (
        hashlib.sha256(closeout_csv).hexdigest()
    )
    exported_text = (ledger_csv + closeout_csv).decode("utf-8").casefold()
    assert "patient_name" not in exported_text
    assert "patient_id" not in exported_text
    assert "source_no_resep" not in exported_text
    with app_container.database.session() as session:
        activation = session.get(AdvisoryPilotActivation, active.activation_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "PILOT_SESSION_EVIDENCE_EXPORTED"
            )
        )
        assert activation.status == "REVOKED"
        assert audit is not None
        assert app_container.audit.verify_chain(session)

    verification = (
        app_container.clinical_validation.verify_pilot_evidence_package(
            result.path, admin.id
        )
    )
    assert verification.valid
    assert verification.errors == ()
    assert verification.checksum_sha256 == result.checksum_sha256
    assert verification.ledger_head_hash == result.ledger_head_hash
    assert verification.schema_revision == "0029_kfa_identity"
    history = app_container.clinical_validation.pilot_evidence_verifications(
        admin.id
    )
    assert len(history) == 1
    assert history[0].record_id == verification.record_id
    assert history[0].checksum_sha256 == verification.checksum_sha256
    with app_container.database.session() as session:
        stored = session.get(PilotEvidenceVerification, verification.record_id)
        verification_audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "PILOT_EVIDENCE_PACKAGE_VERIFIED"
            )
        )
        assert stored.outcome == "VALID"
        assert verification_audit.outcome == "SUCCESS"
        with pytest.raises(DatabaseError, match="immutable"):
            session.execute(
                text(
                    "UPDATE pilot_evidence_verification "
                    "SET outcome = 'INVALID' WHERE id = :id"
                ),
                {"id": verification.record_id},
            )
        session.rollback()
        with pytest.raises(DatabaseError, match="immutable"):
            session.execute(
                text(
                    "DELETE FROM pilot_evidence_verification WHERE id = :id"
                ),
                {"id": verification.record_id},
            )
        session.rollback()


@pytest.mark.integration
def test_evidence_verifier_rejects_tamper_and_records_safe_error_codes(
    app_container, tmp_path
):
    admin = _admin(app_container)
    _ready_advisory_gate(app_container, admin, tmp_path, "VERIFY-TAMPER")
    _activate_with_two_people(app_container, admin, "verify-owner")
    exported = app_container.clinical_validation.export_pilot_session_evidence(
        tmp_path / "source.zip", admin.id
    )
    with zipfile.ZipFile(exported.path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}

    ledger_reader = csv.reader(
        io.StringIO(contents["pilot_session_ledger.csv"].decode("utf-8"))
    )
    ledger_rows = list(ledger_reader)
    ledger_rows[1][6] = "{}"
    ledger_buffer = io.StringIO(newline="")
    csv.writer(ledger_buffer, lineterminator="\n").writerows(ledger_rows)
    contents["pilot_session_ledger.csv"] = ledger_buffer.getvalue().encode()
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in contents.items():
            archive.writestr(name, payload)

    result = app_container.clinical_validation.verify_pilot_evidence_package(
        tampered, admin.id
    )
    assert not result.valid
    assert "FILE_CHECKSUM_MISMATCH" in result.errors
    assert "LEDGER_CHAIN_INVALID" in result.errors
    assert result.package_filename == "tampered.zip"
    with app_container.database.session() as session:
        stored = session.get(PilotEvidenceVerification, result.record_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == result.record_id,
                AuditLog.action == "PILOT_EVIDENCE_PACKAGE_VERIFIED",
            )
        )
        assert stored.outcome == "INVALID"
        assert json.loads(stored.errors_json) == list(result.errors)
        assert audit.outcome == "FAILURE"
        assert "{}" not in audit.details_json
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_evidence_verifier_fails_closed_for_untrusted_zip_shapes(
    app_container, tmp_path, monkeypatch
):
    admin = _admin(app_container)
    service = app_container.clinical_validation

    invalid_zip = tmp_path / "invalid.zip"
    invalid_zip.write_bytes(b"not-a-zip")
    invalid_result = service.verify_pilot_evidence_package(
        invalid_zip, admin.id
    )
    assert invalid_result.errors == ("INVALID_ZIP",)

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in service.EVIDENCE_FILES:
            archive.writestr(name, b"x")
        archive.writestr("../escape.txt", b"blocked")
    traversal_result = service.verify_pilot_evidence_package(
        traversal, admin.id
    )
    assert "TOO_MANY_ENTRIES" in traversal_result.errors
    assert "UNEXPECTED_ENTRIES" in traversal_result.errors

    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in service.EVIDENCE_FILES:
            info = zipfile.ZipInfo(name)
            if name == "manifest.json":
                info.create_system = 3
                info.external_attr = 0o120777 << 16
            archive.writestr(info, b"x")
    symlink_result = service.verify_pilot_evidence_package(symlink, admin.id)
    assert "UNSAFE_ENTRY" in symlink_result.errors

    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in service.EVIDENCE_FILES:
            archive.writestr(name, b"0" * 200_000)
    bomb_result = service.verify_pilot_evidence_package(bomb, admin.id)
    assert "SUSPICIOUS_COMPRESSION" in bomb_result.errors

    wrong_extension = tmp_path / "evidence.dat"
    wrong_extension.write_bytes(invalid_zip.read_bytes())
    extension_result = service.verify_pilot_evidence_package(
        wrong_extension, admin.id
    )
    assert extension_result.errors == ("INVALID_EXTENSION",)

    missing_result = service.verify_pilot_evidence_package(
        tmp_path / "missing.zip", admin.id
    )
    assert missing_result.errors == ("FILE_NOT_FOUND",)
    assert missing_result.checksum_sha256 is None

    monkeypatch.setattr(type(service), "MAX_EVIDENCE_PACKAGE_BYTES", 1)
    oversized_result = service.verify_pilot_evidence_package(
        invalid_zip, admin.id
    )
    assert oversized_result.errors == ("PACKAGE_TOO_LARGE",)
    assert len(service.pilot_evidence_verifications(admin.id)) == 7
    with pytest.raises(ClinicalValidationError, match="1-200"):
        service.pilot_evidence_verifications(admin.id, 0)


@pytest.mark.integration
def test_evidence_verifier_rejects_malformed_manifest_without_trusting_fields(
    app_container, tmp_path
):
    admin = _admin(app_container)
    service = app_container.clinical_validation
    ledger = ",".join(service.EVIDENCE_LEDGER_HEADERS).encode() + b"\n"
    closeouts = ",".join(service.EVIDENCE_CLOSEOUT_HEADERS).encode() + b"\n"
    manifest = {
        "format": "UNTRUSTED",
        "application_version": None,
        "schema_revision": "",
        "contains_patient_identity": True,
        "ledger_entries": True,
        "closeouts": -1,
        "ledger_head_hash": "bad",
        "files": {},
    }
    package = tmp_path / "bad-manifest.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("pilot_session_ledger.csv", ledger)
        archive.writestr("pilot_shift_closeouts.csv", closeouts)
    result = service.verify_pilot_evidence_package(package, admin.id)
    assert not result.valid
    assert {
        "UNSUPPORTED_FORMAT",
        "PATIENT_IDENTITY_DECLARED",
        "INVALID_APPLICATION_VERSION",
        "INVALID_SCHEMA_REVISION",
        "INVALID_HEAD_HASH",
        "INVALID_LEDGER_COUNT",
        "INVALID_CLOSEOUT_COUNT",
        "INVALID_EXPORTED_AT",
        "INVALID_FILE_DIGESTS",
    }.issubset(result.errors)


@pytest.mark.integration
def test_validation_campaign_is_bound_to_runtime_provenance(
    app_container, tmp_path
):
    admin = _admin(app_container)
    knowledge_id = _published_knowledge_base(app_container, admin)
    workbook = tmp_path / "validation-provenance.xlsx"
    write_xlsx(
        workbook,
        [
            XlsxSheet(
                "VALIDATION_CASES",
                [
                    VALIDATION_HEADERS,
                    _row("CRIT-PROVENANCE", "CRITICAL", compound=True),
                    _row("HR-PROVENANCE", "HIGH_RISK", revision=True),
                ],
                [20] * len(VALIDATION_HEADERS),
            )
        ],
    )

    imported = app_container.clinical_validation.import_workbook(
        workbook, admin.id
    )
    with app_container.database.session() as session:
        campaign = session.get(ValidationCampaign, imported.campaign_id)
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "VALIDATION_WORKBOOK_IMPORTED"
            )
        )
        assert campaign.application_version == __version__
        assert (
            campaign.screening_engine_version
            == DdiScreeningService.ENGINE_VERSION
        )
        assert campaign.knowledge_base_version_id == knowledge_id
        assert len(campaign.safety_configuration_fingerprint) == 64
        details = json.loads(audit.details_json)
        assert details["application_version"] == __version__
        assert (
            details["screening_engine_version"]
            == DdiScreeningService.ENGINE_VERSION
        )
        assert details["knowledge_base_version"] == "KB-VALIDATION"
        assert details["safety_configuration_fingerprint"] == (
            campaign.safety_configuration_fingerprint
        )

    initial = app_container.clinical_validation.evaluate_gate(admin.id)
    assert not any("Kampanye validasi bukan" in row for row in initial.blockers)
    assert not any("Knowledge base" in row for row in initial.blockers)
    assert not any("Kebijakan keselamatan" in row for row in initial.blockers)

    app_container.medication_safety.update_policy(admin.id, 6, 11)
    changed_policy = app_container.clinical_validation.evaluate_gate(admin.id)
    assert (
        "Kebijakan keselamatan obat berubah setelah validasi"
        in changed_policy.blockers
    )

    app_container.medication_safety.update_policy(admin.id, 5, 10)
    restored_policy = app_container.clinical_validation.evaluate_gate(admin.id)
    assert (
        "Kebijakan keselamatan obat berubah setelah validasi"
        not in restored_policy.blockers
    )

    _published_knowledge_base(app_container, admin, "KB-NEWER")
    changed_knowledge = app_container.clinical_validation.evaluate_gate(admin.id)
    assert (
        "Knowledge base PUBLISHED berubah setelah validasi"
        in changed_knowledge.blockers
    )

    with app_container.database.session() as session:
        campaign = session.get(ValidationCampaign, imported.campaign_id)
        campaign.application_version = "0.13.0"
        campaign.screening_engine_version = "1.0.0"
        campaign.safety_configuration_fingerprint = None
        session.commit()

    legacy = app_container.clinical_validation.evaluate_gate(admin.id)
    assert "Kampanye validasi bukan untuk versi aplikasi saat ini" in legacy.blockers
    assert "Kampanye validasi bukan untuk screening engine saat ini" in legacy.blockers
    assert (
        "Kampanye validasi belum memiliki fingerprint kebijakan keselamatan"
        in legacy.blockers
    )


@pytest.mark.integration
def test_validation_import_requires_a_knowledge_base(app_container, tmp_path):
    admin = _admin(app_container)
    workbook = tmp_path / "validation-without-kb.xlsx"
    write_xlsx(
        workbook,
        [
            XlsxSheet(
                "VALIDATION_CASES",
                [
                    VALIDATION_HEADERS,
                    _row("CRIT-NO-KB", "CRITICAL", compound=True),
                    _row("HR-NO-KB", "HIGH_RISK", revision=True),
                ],
                [20] * len(VALIDATION_HEADERS),
            )
        ],
    )

    with pytest.raises(ValueError, match="Knowledge base DRAFT/PUBLISHED"):
        app_container.clinical_validation.import_workbook(workbook, admin.id)


@pytest.mark.integration
def test_validation_import_rejects_duplicate_case_ids(app_container, tmp_path):
    admin = _admin(app_container)
    workbook = tmp_path / "duplicate.xlsx"
    write_xlsx(
        workbook,
        [XlsxSheet("VALIDATION_CASES", [VALIDATION_HEADERS, _row("SAMA", "CRITICAL"), _row("SAMA", "HIGH_RISK")], [20] * len(VALIDATION_HEADERS))],
    )
    with pytest.raises(ValueError, match="case_id duplikat"):
        app_container.clinical_validation.import_workbook(workbook, admin.id)


@pytest.mark.integration
def test_pilot_monitoring_uses_only_aggregate_non_mock_data(
    app_container, tmp_path
):
    admin = _admin(app_container)
    now = utc_now()
    with app_container.database.session() as session:
        critical = ProcessingQueue(
            source_no_resep="PILOT-CRITICAL",
            risk_status="CRITICAL",
            is_mock=False,
            detected_at=now,
        )
        high_risk = ProcessingQueue(
            source_no_resep="PILOT-HIGH-RISK",
            risk_status="HIGH_RISK",
            is_mock=False,
            detected_at=now,
        )
        mock = ProcessingQueue(
            source_no_resep="MOCK-TIDAK-DIHITUNG",
            risk_status="CRITICAL",
            is_mock=True,
            detected_at=now,
        )
        session.add_all((critical, high_risk, mock))
        session.flush()
        session.add_all(
            (
                AlertEvent(
                    queue_item_id=critical.id,
                    level="CRITICAL",
                    title="Alert agregat",
                    message="Tanpa identitas pasien",
                    created_at=now,
                ),
                AlertEvent(
                    queue_item_id=high_risk.id,
                    level="HIGH_RISK",
                    title="Alert agregat",
                    message="Tanpa identitas pasien",
                    created_at=now - timedelta(minutes=5),
                    shown_at=now - timedelta(minutes=4),
                    acknowledged_at=now,
                    acknowledged_by=admin.id,
                ),
                AlertEvent(
                    queue_item_id=mock.id,
                    level="CRITICAL",
                    title="Mock",
                    message="Tidak dihitung",
                    created_at=now,
                ),
            )
        )
        session.add(
            PharmacistIntervention(
                queue_item_id=high_risk.id,
                pharmacist_user_id=admin.id,
                status="COMPLETED",
                intervention_type="DRUG_SUBSTITUTION",
                decision="CHANGE_MEDICATION",
                communication_result="ACCEPTED_FULL",
                completed_at=now,
            )
        )
        session.commit()

    summary = app_container.clinical_validation.pilot_monitoring(admin.id, 30)
    assert summary.prescriptions_total == 2
    assert summary.critical_prescriptions == 1
    assert summary.high_risk_prescriptions == 1
    assert summary.alerts_total == 2
    assert summary.alerts_acknowledged == 1
    assert summary.critical_unacknowledged == 1
    assert summary.median_acknowledgement_minutes == 5.0
    assert summary.acceptance_rate == 100.0

    output = app_container.clinical_validation.export_pilot_monitoring(
        tmp_path / "pilot.csv", admin.id, 30
    )
    exported = output.read_text(encoding="utf-8-sig")
    assert "alert_per_100_resep" in exported
    assert "PILOT-CRITICAL" not in exported
    assert "MOCK-TIDAK-DIHITUNG" not in exported


def test_pilot_monitoring_rejects_unapproved_period(app_container):
    admin = _admin(app_container)
    with pytest.raises(ValueError, match="Periode monitoring"):
        app_container.clinical_validation.pilot_monitoring(admin.id, 14)


