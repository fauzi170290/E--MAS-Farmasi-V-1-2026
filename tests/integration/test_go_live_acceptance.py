from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.database.deployment_models import (
    GoLiveAcceptanceItem,
    GoLiveAcceptanceSession,
    GoLiveDecisionLedger,
)
from emss.services.go_live import GoLiveError, GoLivePermissionError
from emss.utils.time import utc_now


def _release_files(tmp_path, *, version=__version__, schema="0029_kfa_identity"):
    installer = tmp_path / f"E-MAS-Farmasi-Setup-{version}-x64.exe"
    installer.write_bytes(b"qualified-installer")
    installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = tmp_path / "release-qualification.json"
    report.write_text(
        json.dumps(
            {
                "format": "EMSS_RELEASE_QUALIFICATION_V1",
                "status": "QUALIFIED",
                "application_version": version,
                "schema_revision": schema,
                "checks": [
                    {"name": "VERSION_CONTRACT", "status": "PASS"},
                    {"name": "BINARY_SMOKE", "status": "PASS"},
                    {"name": "INSTALLER_ARTIFACT", "status": "PASS"},
                ],
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
    return report, installer


def _users(container):
    admin = container.users.create_first_admin(
        username="admin.golive",
        display_name="Admin Go Live",
        password="GoLive#Aman2026",
    )
    clinical = container.users.create_user(
        username="clinical.golive",
        display_name="Clinical Go Live",
        password="Clinical#Aman2026",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    director = container.users.create_user(
        username="director.golive",
        display_name="Director Go Live",
        password="Director#Aman2026",
        roles=("DIREKTUR",),
        actor_user_id=admin.id,
    )
    viewer = container.users.create_user(
        username="viewer.golive",
        display_name="Viewer Go Live",
        password="Viewer#Aman2026",
        roles=("VIEWER",),
        actor_user_id=admin.id,
    )
    return admin, clinical, director, viewer


def _complete_items(container, session_id, admin, clinical, evidence):
    for item in container.go_live.items(session_id, admin.id):
        actor = admin if item.owner_type == "TECHNICAL" else clinical
        container.go_live.update_item(
            item.id,
            "PASS",
            actor.id,
            evidence_path=evidence,
            notes="Bukti sintetis tervalidasi",
        )


@pytest.mark.integration
def test_go_live_requires_bound_release_dual_attestation_and_independent_decision(
    app_container, tmp_path
):
    admin, clinical, director, viewer = _users(app_container)
    report, installer = _release_files(tmp_path)
    evidence = tmp_path / "clean-host-evidence.json"
    evidence.write_text('{"result":"PASS"}', encoding="utf-8")

    acceptance = app_container.go_live.create_session(
        report, installer, "STAGING-RS-CLEAN-01", admin.id
    )

    assert acceptance.application_version == __version__
    assert acceptance.schema_revision == "0029_kfa_identity"
    assert len(app_container.go_live.items(acceptance.id, director.id)) == 8
    with pytest.raises(GoLivePermissionError):
        app_container.go_live.items(acceptance.id, viewer.id)
    with pytest.raises(GoLiveError, match="wajib PASS"):
        app_container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)

    _complete_items(app_container, acceptance.id, admin, clinical, evidence)
    app_container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)
    app_container.go_live.attest(acceptance.id, "TECHNICAL", admin.id)
    readiness = app_container.go_live.evaluate(acceptance.id, director.id)
    assert readiness.ready_for_go_decision
    assert readiness.items_passed == readiness.items_total == 8
    assert readiness.ledger_valid

    with pytest.raises(GoLiveError, match="independen"):
        app_container.go_live.decide(
            acceptance.id,
            "GO",
            "Seluruh bukti siap untuk limited production",
            admin.id,
        )
    final = app_container.go_live.decide(
        acceptance.id,
        "GO",
        "Seluruh bukti siap untuk limited production",
        director.id,
    )
    assert final.status == "GO"
    assert final.decided_by == director.id
    assert app_container.go_live.verify_ledger(admin.id)
    assert [row.event_type for row in app_container.go_live.ledger(admin.id)][-3:] == [
        "CLINICAL_ATTESTED",
        "TECHNICAL_ATTESTED",
        "DECISION_GO",
    ]

    first_item = app_container.go_live.items(acceptance.id, admin.id)[0]
    with pytest.raises(GoLiveError, match="final"):
        app_container.go_live.update_item(
            first_item.id,
            "PASS",
            admin.id,
            evidence_path=evidence,
        )
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(
                text(
                    "UPDATE go_live_acceptance_session "
                    "SET decision_reason='tampered' WHERE id=:id"
                ),
                {"id": acceptance.id},
            )


@pytest.mark.integration
def test_evidence_change_revokes_only_matching_attestation(app_container, tmp_path):
    admin, clinical, director, _viewer = _users(app_container)
    report, installer = _release_files(tmp_path)
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence-v1", encoding="utf-8")
    acceptance = app_container.go_live.create_session(
        report, installer, "STAGING-RS-02", admin.id
    )
    _complete_items(app_container, acceptance.id, admin, clinical, evidence)
    app_container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)
    app_container.go_live.attest(acceptance.id, "TECHNICAL", admin.id)

    clinical_item = next(
        item
        for item in app_container.go_live.items(acceptance.id, director.id)
        if item.owner_type == "CLINICAL"
    )
    app_container.go_live.update_item(
        clinical_item.id,
        "PASS",
        clinical.id,
        evidence_path=evidence,
    )
    refreshed = app_container.go_live.evaluate(acceptance.id, director.id)
    assert refreshed.session.clinical_attested_by is None
    assert refreshed.session.technical_attested_by == admin.id
    assert "Attestation klinis belum tersedia" in refreshed.blockers


@pytest.mark.integration
def test_go_live_rejects_unqualified_mismatched_or_tampered_release(
    app_container, tmp_path
):
    admin, _clinical, _director, _viewer = _users(app_container)
    report, installer = _release_files(tmp_path, version="9.9.9")
    with pytest.raises(GoLiveError, match="versi aplikasi aktif"):
        app_container.go_live.create_session(
            report, installer, "STAGING-RS-03", admin.id
        )

    report, installer = _release_files(tmp_path)
    installer.write_bytes(b"tampered")
    with pytest.raises(GoLiveError, match="Checksum installer"):
        app_container.go_live.create_session(
            report, installer, "STAGING-RS-03", admin.id
        )

    report, installer = _release_files(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["checks"][1]["status"] = "FAIL"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GoLiveError, match="tidak lulus"):
        app_container.go_live.create_session(
            report, installer, "STAGING-RS-03", admin.id
        )


@pytest.mark.integration
def test_expiry_and_ledger_tamper_fail_closed(app_container, tmp_path):
    admin, clinical, director, _viewer = _users(app_container)
    report, installer = _release_files(tmp_path)
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("safe evidence", encoding="utf-8")
    acceptance = app_container.go_live.create_session(
        report, installer, "STAGING-RS-04", admin.id
    )
    _complete_items(app_container, acceptance.id, admin, clinical, evidence)
    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_go_live_session_binding_immutable"))
        session.execute(
            text(
                "UPDATE go_live_acceptance_session SET expires_at=:expired "
                "WHERE id=:id"
            ),
            {"expired": utc_now() - timedelta(minutes=1), "id": acceptance.id},
        )
        session.commit()
    expired = app_container.go_live.evaluate(acceptance.id, director.id)
    assert not expired.ready_for_go_decision
    assert "Sesi acceptance telah kedaluwarsa" in expired.blockers
    with pytest.raises(GoLiveError, match="kedaluwarsa"):
        app_container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)

    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_go_live_ledger_no_update"))
        first = session.scalar(
            select(GoLiveDecisionLedger).order_by(GoLiveDecisionLedger.id)
        )
        assert first is not None
        first.payload_json = '{"tampered":true}'
        session.commit()
    assert not app_container.go_live.verify_ledger(admin.id)
    tampered = app_container.go_live.evaluate(acceptance.id, director.id)
    assert not tampered.ledger_valid
    assert "Ledger keputusan go-live tidak valid" in tampered.blockers


@pytest.mark.integration
def test_no_go_is_available_without_false_positive_readiness(app_container, tmp_path):
    admin, _clinical, director, _viewer = _users(app_container)
    report, installer = _release_files(tmp_path)
    acceptance = app_container.go_live.create_session(
        report, installer, "STAGING-RS-05", admin.id
    )
    final = app_container.go_live.decide(
        acceptance.id,
        "NO_GO",
        "Clean-host validation masih memiliki blocker",
        director.id,
    )
    assert final.status == "NO_GO"
    assert not app_container.go_live.evaluate(acceptance.id, director.id).ready_for_go_decision
    with app_container.database.session() as session:
        record = session.get(GoLiveAcceptanceSession, acceptance.id)
        items = session.scalars(
            select(GoLiveAcceptanceItem).where(
                GoLiveAcceptanceItem.session_id == acceptance.id
            )
        ).all()
        assert record is not None and record.status == "NO_GO"
        assert all(item.status == "NOT_TESTED" for item in items)


@pytest.mark.integration
def test_go_live_migration_downgrade_and_reupgrade_preserve_prior_data(
    app_container,
):
    admin, _clinical, _director, _viewer = _users(app_container)

    command.downgrade(
        app_container.database._alembic_config(),
        "0018_evidence_verification",
    )

    assert app_container.database.current_revision() == "0018_evidence_verification"
    assert "go_live_acceptance_session" not in inspect(
        app_container.database.engine
    ).get_table_names()
    with app_container.database.session() as session:
        assert session.get(type(admin), admin.id).username == "admin.golive"

    app_container.database.migrate()
    assert app_container.database.current_revision() == "0029_kfa_identity"
    assert "go_live_acceptance_session" in inspect(
        app_container.database.engine
    ).get_table_names()
    assert "limited_rollout_session" in inspect(
        app_container.database.engine
    ).get_table_names()


