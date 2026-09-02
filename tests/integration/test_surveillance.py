from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.database.integration_models import PollingRun
from emss.database.intervention_models import PharmacistIntervention
from emss.database.queue_models import AlertEvent, ProcessingQueue
from emss.services.surveillance import SurveillanceError, SurveillancePermissionError
from emss.utils.time import utc_now


def _users(container):
    admin = container.users.create_first_admin(
        username="admin.surveillance", display_name="Admin Surveillance", password="Admin#Aman2026"
    )
    clinical = container.users.create_user(
        username="clinical.surveillance", display_name="Clinical Surveillance",
        password="Clinical#Aman2026", roles=("APOTEKER",), actor_user_id=admin.id,
    )
    director = container.users.create_user(
        username="director.surveillance", display_name="Director Surveillance",
        password="Director#Aman2026", roles=("DIREKTUR",), actor_user_id=admin.id,
    )
    return admin, clinical, director


def _completed_rollout(container, tmp_path, admin, clinical, director):
    installer = tmp_path / f"E-MAS-Farmasi-Setup-{__version__}-x64.exe"
    installer.write_bytes(b"surveillance-qualified-installer")
    installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = tmp_path / "release-qualification.json"
    report.write_text(json.dumps({
        "format": "EMSS_RELEASE_QUALIFICATION_V1", "status": "QUALIFIED",
        "application_version": __version__, "schema_revision": "0029_kfa_identity",
        "checks": [{"name": "ALL", "status": "PASS"}],
        "artifacts": [{"path": f"installer/{installer.name}", "size_bytes": installer.stat().st_size, "checksum_sha256": installer_hash}],
    }), encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"result":"PASS"}', encoding="utf-8")
    acceptance = container.go_live.create_session(report, installer, "SURVEILLANCE-STAGING", admin.id)
    for item in container.go_live.items(acceptance.id, admin.id):
        actor = admin if item.owner_type == "TECHNICAL" else clinical
        container.go_live.update_item(item.id, "PASS", actor.id, evidence_path=evidence, notes="Bukti surveillance valid")
    container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)
    container.go_live.attest(acceptance.id, "TECHNICAL", admin.id)
    container.go_live.decide(acceptance.id, "GO", "Limited rollout disetujui untuk surveillance", director.id)
    rollout = container.limited_rollout.create_session(acceptance.id, "Limited rollout surveillance", 1, admin.id)
    wave = container.limited_rollout.add_wave(rollout.id, "Satu terminal surveillance", 1, admin.id)
    container.limited_rollout.start(rollout.id, admin.id)
    container.limited_rollout.activate_wave(wave.id, admin.id)
    container.limited_rollout.complete_wave(wave.id, admin.id)
    container.limited_rollout.attest(rollout.id, "CLINICAL", clinical.id)
    container.limited_rollout.attest(rollout.id, "TECHNICAL", admin.id)
    return container.limited_rollout.decide(rollout.id, "COMPLETE", "Limited rollout selesai tanpa blocker", director.id)


def _seed_non_mock(container):
    with container.database.session() as session:
        session.add(ProcessingQueue(
            source_no_resep="SURVEILLANCE-AGGREGATE-1", is_mock=False,
            processing_status="COMPLETED", review_status="REVIEWED",
            risk_status="SAFE", completeness_status="COMPLETE",
            overall_status="SAFE", alert_level="SAFE", detected_at=utc_now(),
        ))
        session.commit()


def _two_snapshots(container, surveillance_id, admin, monkeypatch):
    first = container.surveillance.capture_snapshot(surveillance_id, admin.id)
    later = first.captured_at + timedelta(hours=2)
    monkeypatch.setattr("emss.services.surveillance.utc_now", lambda: later)
    second = container.surveillance.capture_snapshot(surveillance_id, admin.id)
    return first, second


@pytest.mark.integration
def test_surveillance_promotion_requires_fresh_aggregate_observation_and_three_parties(app_container, tmp_path, monkeypatch):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)
    surveillance = app_container.surveillance.create_session(
        rollout.id, "Early-life production observation", admin.id,
        minimum_observation_hours=1, maximum_snapshot_age_hours=3,
    )
    _seed_non_mock(app_container)
    _two_snapshots(app_container, surveillance.id, admin, monkeypatch)
    readiness = app_container.surveillance.evaluate(surveillance.id, director.id)
    assert readiness.snapshots_total == 2
    assert readiness.observation_hours == 2
    assert not readiness.ready_for_promotion
    app_container.surveillance.attest(surveillance.id, "CLINICAL", clinical.id)
    app_container.surveillance.attest(surveillance.id, "TECHNICAL", admin.id)
    assert app_container.surveillance.evaluate(surveillance.id, director.id).ready_for_promotion
    with pytest.raises(SurveillanceError, match="independen"):
        app_container.surveillance.decide(surveillance.id, "PROMOTE", "Promosi release disetujui", admin.id)
    final = app_container.surveillance.decide(surveillance.id, "PROMOTE", "Promosi release disetujui setelah observasi", director.id)
    assert final.status == "PROMOTED"
    assert app_container.surveillance.ledger(admin.id)[-1].event_type == "DECISION_PROMOTE"


@pytest.mark.integration
def test_issue_is_hashed_blocks_attestation_and_closure_revokes_prior_attestation(app_container, tmp_path, monkeypatch):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)
    surveillance = app_container.surveillance.create_session(
        rollout.id, "Issue remediation observation", admin.id,
        minimum_observation_hours=1, maximum_snapshot_age_hours=4,
    )
    _seed_non_mock(app_container)
    _two_snapshots(app_container, surveillance.id, admin, monkeypatch)
    issue = app_container.surveillance.record_issue(
        surveillance.id, "CRITICAL", "Gangguan alert pada terminal tanpa data pasien", clinical.id
    )
    assert len(issue.summary_hash_sha256) == 64
    with pytest.raises(SurveillanceError, match="isu surveillance terbuka"):
        app_container.surveillance.attest(surveillance.id, "CLINICAL", clinical.id)
    closed = app_container.surveillance.close_issue(
        issue.id, "Konfigurasi diperbaiki dan smoke test ulang lulus", admin.id
    )
    assert closed.status == "CLOSED" and len(closed.resolution_hash_sha256 or "") == 64
    app_container.surveillance.attest(surveillance.id, "CLINICAL", clinical.id)
    app_container.surveillance.attest(surveillance.id, "TECHNICAL", admin.id)
    new_issue = app_container.surveillance.record_issue(
        surveillance.id, "WARNING", "Observasi lanjutan memerlukan tindak lanjut teknis", admin.id
    )
    current = app_container.surveillance.evaluate(surveillance.id, director.id)
    assert current.session.clinical_attested_by is None
    assert current.session.technical_attested_by is None
    assert current.open_issues == 1
    assert new_issue.status == "OPEN"


@pytest.mark.integration
def test_stale_snapshot_and_upstream_ledger_tamper_fail_closed(app_container, tmp_path, monkeypatch):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)
    surveillance = app_container.surveillance.create_session(
        rollout.id, "Stale snapshot observation", admin.id,
        minimum_observation_hours=1, maximum_snapshot_age_hours=1,
    )
    _seed_non_mock(app_container)
    _first, second = _two_snapshots(app_container, surveillance.id, admin, monkeypatch)
    monkeypatch.setattr("emss.services.surveillance.utc_now", lambda: second.captured_at + timedelta(hours=2))
    stale = app_container.surveillance.evaluate(surveillance.id, director.id)
    assert "basi" in "; ".join(stale.blockers)
    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_rollout_ledger_no_update"))
        session.execute(text("UPDATE limited_rollout_ledger SET payload_json='{}' WHERE id=1"))
        session.commit()
    broken = app_container.surveillance.evaluate(surveillance.id, director.id)
    assert not broken.ledger_valid
    with pytest.raises(SurveillanceError, match="Ledger"):
        app_container.surveillance.capture_snapshot(surveillance.id, admin.id)


@pytest.mark.integration
def test_rollback_is_fail_safe_and_snapshots_are_database_immutable(app_container, tmp_path):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)
    surveillance = app_container.surveillance.create_session(rollout.id, "Rollback observation", admin.id)
    _seed_non_mock(app_container)
    snapshot = app_container.surveillance.capture_snapshot(surveillance.id, admin.id)
    final = app_container.surveillance.decide(
        surveillance.id, "ROLLBACK", "Rollback dipilih karena observasi belum memadai", director.id
    )
    assert final.status == "ROLLED_BACK"
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(text("DELETE FROM surveillance_snapshot WHERE id=:id"), {"id": snapshot.id})


@pytest.mark.integration
def test_surveillance_migration_downgrade_and_reupgrade_preserves_rollout_data(app_container):
    admin, _clinical, _director = _users(app_container)
    command.downgrade(app_container.database._alembic_config(), "0020_limited_rollout")
    assert app_container.database.current_revision() == "0020_limited_rollout"
    assert "early_life_surveillance_session" not in inspect(app_container.database.engine).get_table_names()
    with app_container.database.session() as session:
        assert session.get(type(admin), admin.id).username == "admin.surveillance"
    app_container.database.migrate()
    assert app_container.database.current_revision() == "0029_kfa_identity"
    assert "early_life_surveillance_session" in inspect(app_container.database.engine).get_table_names()


@pytest.mark.integration
def test_surveillance_validation_permissions_and_final_state_fail_closed(app_container, tmp_path):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)

    invalid_parameters = (
        {"environment_label": "x"},
        {"environment_label": "Valid environment", "validity_days": 0},
        {"environment_label": "Valid environment", "minimum_snapshots": 1},
        {"environment_label": "Valid environment", "minimum_observation_hours": 0},
        {"environment_label": "Valid environment", "maximum_snapshot_age_hours": 73},
    )
    for parameters in invalid_parameters:
        with pytest.raises(SurveillanceError):
            app_container.surveillance.create_session(rollout.id, actor_user_id=admin.id, **parameters)
    with pytest.raises(SurveillancePermissionError, match="Pengguna aktif"):
        app_container.surveillance.create_session(rollout.id, "Valid environment", "missing-user")
    with pytest.raises(SurveillanceError, match="Limited rollout tidak ditemukan"):
        app_container.surveillance.create_session("missing-rollout", "Valid environment", admin.id)

    surveillance = app_container.surveillance.create_session(
        rollout.id, "Fail-closed validation environment", admin.id
    )
    with pytest.raises(SurveillanceError, match="sudah memiliki"):
        app_container.surveillance.create_session(rollout.id, "Duplicate environment", admin.id)
    assert app_container.surveillance.sessions(admin.id)[0].id == surveillance.id
    assert app_container.surveillance.snapshots(surveillance.id, admin.id) == ()
    assert app_container.surveillance.issues(surveillance.id, admin.id) == ()
    assert not app_container.surveillance.evaluate(surveillance.id).ready_for_promotion

    with pytest.raises(SurveillanceError, match="10-300"):
        app_container.surveillance.record_issue(surveillance.id, "WARNING", "singkat", admin.id)
    with pytest.raises(SurveillanceError, match="Severity"):
        app_container.surveillance.record_issue(
            surveillance.id, "INFO", "Ringkasan isu dengan panjang yang valid", admin.id
        )
    with pytest.raises(SurveillanceError, match="tidak ditemukan"):
        app_container.surveillance.close_issue("missing-issue", "Resolusi cukup panjang dan valid", admin.id)
    with pytest.raises(SurveillanceError, match="Jenis attestation"):
        app_container.surveillance.attest(surveillance.id, "LEGAL", admin.id)
    with pytest.raises(SurveillanceError, match="Keputusan harus"):
        app_container.surveillance.decide(surveillance.id, "HOLD", "Keputusan surveillance ditahan", director.id)
    with pytest.raises(SurveillanceError, match="Promotion ditolak"):
        app_container.surveillance.decide(surveillance.id, "PROMOTE", "Bukti belum memenuhi promosi", director.id)

    final = app_container.surveillance.decide(
        surveillance.id, "ROLLBACK", "Rollback aman sebelum bukti observasi lengkap", director.id
    )
    assert final.status == "ROLLED_BACK"
    readiness = app_container.surveillance.evaluate(surveillance.id, admin.id)
    assert any("final" in blocker for blocker in readiness.blockers)
    with pytest.raises(SurveillanceError, match="final"):
        app_container.surveillance.capture_snapshot(surveillance.id, admin.id)
    with pytest.raises(SurveillancePermissionError, match="Pengguna aktif"):
        app_container.surveillance.ledger("missing-user")


@pytest.mark.integration
def test_snapshot_excludes_mock_intervention_and_blocks_real_operational_backlog(
    app_container, tmp_path, monkeypatch
):
    admin, clinical, director = _users(app_container)
    rollout = _completed_rollout(app_container, tmp_path, admin, clinical, director)
    surveillance = app_container.surveillance.create_session(
        rollout.id, "Operational backlog observation", admin.id,
        minimum_observation_hours=1, maximum_snapshot_age_hours=4,
    )
    now = utc_now()
    with app_container.database.session() as session:
        real = ProcessingQueue(
            source_no_resep="SURVEILLANCE-REAL-CRITICAL", is_mock=False,
            processing_status="COMPLETED", review_status="NEW", risk_status="CRITICAL",
            completeness_status="COMPLETE", overall_status="CRITICAL", alert_level="CRITICAL",
            detected_at=now,
        )
        mock = ProcessingQueue(
            source_no_resep="SURVEILLANCE-MOCK-CRITICAL", is_mock=True,
            processing_status="COMPLETED", review_status="NEW", risk_status="CRITICAL",
            completeness_status="COMPLETE", overall_status="CRITICAL", alert_level="CRITICAL",
            detected_at=now,
        )
        session.add_all((real, mock))
        session.flush()
        session.add_all((
            AlertEvent(
                queue_item_id=real.id, level="CRITICAL", status="NEW",
                title="Alert nyata", message="Alert nyata belum diakui", created_at=now,
            ),
            AlertEvent(
                queue_item_id=mock.id, level="CRITICAL", status="NEW",
                title="Alert mock", message="Alert mock tidak dihitung", created_at=now,
            ),
            PharmacistIntervention(
                queue_item_id=real.id, pharmacist_user_id=clinical.id, status="OPEN",
                intervention_type="CLINICAL_MONITORING", decision="CONTACT_PRESCRIBER",
                created_at=now, updated_at=now,
            ),
            PharmacistIntervention(
                queue_item_id=mock.id, pharmacist_user_id=clinical.id, status="OPEN",
                intervention_type="CLINICAL_MONITORING", decision="CONTACT_PRESCRIBER",
                created_at=now, updated_at=now,
            ),
            PollingRun(
                adapter_code="KHANZA", status="FAILED", detected_count=0, stable_count=0,
                processed_count=0, incomplete_count=0, failed_count=1,
                error_code="SURVEILLANCE_TEST_FAILURE", started_at=now, completed_at=now,
            ),
        ))
        session.commit()

    first, second = _two_snapshots(app_container, surveillance.id, admin, monkeypatch)
    assert first.prescriptions_total == 1
    assert first.critical_total == 1
    assert first.unacknowledged_critical_alerts == 1
    assert first.open_interventions == 1
    assert first.polling_failures == 1
    assert second.open_interventions == 1
    readiness = app_container.surveillance.evaluate(surveillance.id, director.id)
    blockers = "; ".join(readiness.blockers)
    assert "alert CRITICAL" in blockers
    assert "intervensi terbuka" in blockers
    assert "kegagalan polling" in blockers


