from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.database.rollout_models import LimitedRolloutLedger, LimitedRolloutSession
from emss.services.limited_rollout import LimitedRolloutError, LimitedRolloutPermissionError
from emss.utils.time import utc_now


def _users(container):
    admin = container.users.create_first_admin(
        username="admin.rollout", display_name="Admin Rollout", password="Rollout#Aman2026"
    )
    clinical = container.users.create_user(
        username="clinical.rollout",
        display_name="Clinical Rollout",
        password="Clinical#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    director = container.users.create_user(
        username="director.rollout",
        display_name="Director Rollout",
        password="Director#Aman2026",
        roles=("DIREKTUR",),
        actor_user_id=admin.id,
    )
    viewer = container.users.create_user(
        username="viewer.rollout",
        display_name="Viewer Rollout",
        password="Viewer#Aman2026",
        roles=("VIEWER",),
        actor_user_id=admin.id,
    )
    return admin, clinical, director, viewer


def _go_acceptance(container, tmp_path, admin, clinical, director):
    installer = tmp_path / f"E-MAS-Farmasi-Setup-{__version__}-x64.exe"
    installer.write_bytes(b"qualified-rollout-installer")
    installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = tmp_path / "release-qualification.json"
    report.write_text(
        json.dumps(
            {
                "format": "EMSS_RELEASE_QUALIFICATION_V1",
                "status": "QUALIFIED",
                "application_version": __version__,
                "schema_revision": "0029_kfa_identity",
                "checks": [{"name": "ALL", "status": "PASS"}],
                "artifacts": [
                    {
                        "path": f"installer/{installer.name}",
                        "size_bytes": installer.stat().st_size,
                        "checksum_sha256": installer_hash,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "rollout-evidence.json"
    evidence.write_text('{"result":"PASS"}', encoding="utf-8")
    acceptance = container.go_live.create_session(
        report, installer, "LIMITED-PRODUCTION-RS", admin.id
    )
    for item in container.go_live.items(acceptance.id, admin.id):
        actor = admin if item.owner_type == "TECHNICAL" else clinical
        container.go_live.update_item(
            item.id,
            "PASS",
            actor.id,
            evidence_path=evidence,
            notes="Bukti rollout tervalidasi",
        )
    container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)
    container.go_live.attest(acceptance.id, "TECHNICAL", admin.id)
    return container.go_live.decide(
        acceptance.id,
        "GO",
        "Disetujui untuk limited production rollout",
        director.id,
    )


@pytest.mark.integration
def test_rollout_is_bound_to_valid_go_and_completes_with_three_independent_parties(
    app_container, tmp_path
):
    admin, clinical, director, viewer = _users(app_container)
    acceptance = _go_acceptance(app_container, tmp_path, admin, clinical, director)
    rollout = app_container.limited_rollout.create_session(
        acceptance.id,
        "Farmasi Rawat Inap - pilot terbatas",
        5,
        admin.id,
    )
    with pytest.raises(LimitedRolloutPermissionError):
        app_container.limited_rollout.waves(rollout.id, viewer.id)
    first = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal farmasi gelombang 1", 2, admin.id
    )
    second = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal farmasi gelombang 2", 3, admin.id
    )
    with pytest.raises(LimitedRolloutError, match="melampaui"):
        app_container.limited_rollout.add_wave(
            rollout.id, "Terminal tambahan", 1, admin.id
        )
    app_container.limited_rollout.start(rollout.id, admin.id)
    app_container.limited_rollout.activate_wave(first.id, admin.id)
    assert app_container.limited_rollout.operational_allowed(rollout.id)
    app_container.limited_rollout.complete_wave(first.id, admin.id)
    app_container.limited_rollout.activate_wave(second.id, admin.id)
    app_container.limited_rollout.complete_wave(second.id, admin.id)
    assert not app_container.limited_rollout.operational_allowed(rollout.id)

    app_container.limited_rollout.attest(rollout.id, "CLINICAL", clinical.id)
    app_container.limited_rollout.attest(rollout.id, "TECHNICAL", admin.id)
    readiness = app_container.limited_rollout.evaluate(rollout.id, director.id)
    assert readiness.ready_for_completion
    assert readiness.waves_completed == readiness.waves_total == 2
    with pytest.raises(LimitedRolloutError, match="independen"):
        app_container.limited_rollout.decide(
            rollout.id, "COMPLETE", "Closeout limited rollout disetujui", admin.id
        )
    final = app_container.limited_rollout.decide(
        rollout.id, "COMPLETE", "Closeout limited rollout disetujui", director.id
    )
    assert final.status == "COMPLETED"
    assert app_container.limited_rollout.verify_ledger(admin.id)


@pytest.mark.integration
def test_incident_threshold_auto_halts_and_resume_is_explicit(app_container, tmp_path):
    admin, clinical, director, _viewer = _users(app_container)
    acceptance = _go_acceptance(app_container, tmp_path, admin, clinical, director)
    rollout = app_container.limited_rollout.create_session(
        acceptance.id,
        "Farmasi IGD pilot",
        2,
        admin.id,
        incident_halt_threshold=2,
        critical_halt_threshold=1,
    )
    wave = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal farmasi IGD", 2, admin.id
    )
    app_container.limited_rollout.start(rollout.id, admin.id)
    app_container.limited_rollout.activate_wave(wave.id, admin.id)
    stopped = app_container.limited_rollout.record_incident(
        rollout.id,
        "CRITICAL",
        "Alert kritis gagal tampil pada terminal pilot",
        clinical.id,
        affected_workstations=1,
    )
    assert stopped.status == "HALTED"
    assert not app_container.limited_rollout.operational_allowed(rollout.id)
    assert [row.event_type for row in app_container.limited_rollout.ledger(admin.id)][-2:] == [
        "INCIDENT_RECORDED",
        "AUTO_HALT",
    ]
    still_halted = app_container.limited_rollout.pause(
        rollout.id,
        "Pause biasa tidak boleh menurunkan emergency halt aktif",
        clinical.id,
    )
    assert still_halted.status == "HALTED"
    resumed = app_container.limited_rollout.resume(
        rollout.id,
        "Insiden telah dimitigasi dan smoke test ulang lulus",
        admin.id,
    )
    assert resumed.status == "ACTIVE"
    assert app_container.limited_rollout.operational_allowed(rollout.id)


@pytest.mark.integration
def test_expired_rollout_and_invalid_go_fail_closed(app_container, tmp_path, monkeypatch):
    admin, clinical, director, _viewer = _users(app_container)
    acceptance = _go_acceptance(app_container, tmp_path, admin, clinical, director)
    rollout = app_container.limited_rollout.create_session(
        acceptance.id, "Farmasi rawat jalan pilot", 1, admin.id, validity_days=1
    )
    wave = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal rawat jalan", 1, admin.id
    )
    app_container.limited_rollout.start(rollout.id, admin.id)
    app_container.limited_rollout.activate_wave(wave.id, admin.id)
    monkeypatch.setattr(
        "emss.services.limited_rollout.utc_now",
        lambda: utc_now() + timedelta(days=2),
    )
    readiness = app_container.limited_rollout.evaluate(rollout.id, director.id)
    assert not readiness.operational_allowed
    assert "kedaluwarsa" in "; ".join(readiness.blockers)
    with pytest.raises(LimitedRolloutError, match="fail-closed"):
        app_container.limited_rollout.complete_wave(wave.id, admin.id)


@pytest.mark.integration
def test_emergency_rollback_and_database_immutability(app_container, tmp_path):
    admin, clinical, director, _viewer = _users(app_container)
    acceptance = _go_acceptance(app_container, tmp_path, admin, clinical, director)
    rollout = app_container.limited_rollout.create_session(
        acceptance.id, "Farmasi emergency rollback", 1, admin.id
    )
    wave = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal rollback", 1, admin.id
    )
    app_container.limited_rollout.start(rollout.id, admin.id)
    app_container.limited_rollout.activate_wave(wave.id, admin.id)
    app_container.limited_rollout.pause(
        rollout.id,
        "Emergency halt karena risiko keselamatan terdeteksi",
        clinical.id,
        emergency=True,
    )
    final = app_container.limited_rollout.decide(
        rollout.id,
        "ROLLBACK",
        "Rollback ke rilis tervalidasi sebelumnya",
        director.id,
    )
    assert final.status == "ROLLED_BACK"
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(
                text("UPDATE limited_rollout_session SET scope_label='tampered' WHERE id=:id"),
                {"id": rollout.id},
            )
    with app_container.database.session() as session:
        ledger = session.query(LimitedRolloutLedger).first()
        assert ledger is not None
        with pytest.raises(DatabaseError):
            session.execute(
                text("DELETE FROM limited_rollout_ledger WHERE id=:id"),
                {"id": ledger.id},
            )


@pytest.mark.integration
def test_go_live_ledger_tamper_forces_rollout_auto_halt(app_container, tmp_path):
    admin, clinical, director, _viewer = _users(app_container)
    acceptance = _go_acceptance(app_container, tmp_path, admin, clinical, director)
    rollout = app_container.limited_rollout.create_session(
        acceptance.id, "Farmasi ledger quarantine", 1, admin.id
    )
    wave = app_container.limited_rollout.add_wave(
        rollout.id, "Terminal ledger quarantine", 1, admin.id
    )
    app_container.limited_rollout.start(rollout.id, admin.id)
    app_container.limited_rollout.activate_wave(wave.id, admin.id)
    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_go_live_ledger_no_update"))
        session.execute(
            text("UPDATE go_live_decision_ledger SET payload_json='{}' WHERE id=1")
        )
        session.commit()
    assert not app_container.limited_rollout.operational_allowed(rollout.id)
    halted = app_container.limited_rollout.record_incident(
        rollout.id,
        "WARNING",
        "Ledger acceptance terdeteksi tidak valid saat observasi",
        clinical.id,
    )
    assert halted.status == "HALTED"
    assert app_container.limited_rollout.ledger(admin.id)[-1].event_type == "AUTO_HALT"


@pytest.mark.integration
def test_rollout_migration_downgrade_and_reupgrade_preserve_prior_data(app_container):
    admin, _clinical, _director, _viewer = _users(app_container)
    command.downgrade(app_container.database._alembic_config(), "0019_go_live_acceptance")
    assert app_container.database.current_revision() == "0019_go_live_acceptance"
    assert "limited_rollout_session" not in inspect(app_container.database.engine).get_table_names()
    with app_container.database.session() as session:
        assert session.get(type(admin), admin.id).username == "admin.rollout"
    app_container.database.migrate()
    assert app_container.database.current_revision() == "0029_kfa_identity"
    assert "limited_rollout_session" in inspect(app_container.database.engine).get_table_names()


