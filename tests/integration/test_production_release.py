from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.database.queue_models import ProcessingQueue
from emss.database.production_release_models import (
    ProductionChangeApproval,
    ProductionReleaseEvidence,
)
from emss.database.production_evidence_models import (
    ProductionDeploymentCeremony,
    ProductionEvidencePackageVerification,
)
from emss.services.production_evidence import ProductionEvidenceError
from emss.services.production_release import (
    ProductionReleaseError,
    ProductionReleasePermissionError,
)
from emss.utils.time import utc_now


HEAD = "0029_kfa_identity"


def _users(container):
    admin = container.users.create_first_admin(
        username="admin.production", display_name="Admin Production", password="Admin#Aman2026"
    )
    clinical = container.users.create_user(
        username="clinical.production", display_name="Clinical Production",
        password="Clinical#Aman2026", roles=("APOTEKER",), actor_user_id=admin.id,
    )
    approver = container.users.create_user(
        username="approver.production", display_name="Change Approver",
        password="Approver#Aman2026", roles=("DIREKTUR",), actor_user_id=admin.id,
    )
    decision = container.users.create_user(
        username="decision.production", display_name="Production Decision",
        password="Decision#Aman2026", roles=("DIREKTUR",), actor_user_id=admin.id,
    )
    return admin, clinical, approver, decision


def _users_for_additional_record(container, actor, suffix):
    admin = container.users.create_user(
        username=f"admin.{suffix}", display_name=f"Admin {suffix}",
        password="Admin#Aman2026", roles=("IT_ADMIN",), actor_user_id=actor.id,
    )
    clinical = container.users.create_user(
        username=f"clinical.{suffix}", display_name=f"Clinical {suffix}",
        password="Clinical#Aman2026", roles=("APOTEKER",), actor_user_id=actor.id,
    )
    approver = container.users.create_user(
        username=f"approver.{suffix}", display_name=f"Approver {suffix}",
        password="Approver#Aman2026", roles=("DIREKTUR",), actor_user_id=actor.id,
    )
    decision = container.users.create_user(
        username=f"decision.{suffix}", display_name=f"Decision {suffix}",
        password="Decision#Aman2026", roles=("DIREKTUR",), actor_user_id=actor.id,
    )
    return admin, clinical, approver, decision


def _promoted_surveillance(container, tmp_path, monkeypatch, users):
    admin, clinical, approver, _decision = users
    installer = tmp_path / f"E-MAS-Farmasi-Setup-{__version__}-x64.exe"
    installer.write_bytes(b"sprint-19-qualified-installer-fixture")
    installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = tmp_path / "release-qualification.json"
    report.write_text(json.dumps({
        "format": "EMSS_RELEASE_QUALIFICATION_V1", "status": "QUALIFIED",
        "application_version": __version__, "schema_revision": HEAD,
        "checks": [{"name": "ALL", "status": "PASS"}],
        "artifacts": [{
            "path": f"installer/{installer.name}", "size_bytes": installer.stat().st_size,
            "checksum_sha256": installer_hash,
        }],
    }), encoding="utf-8")
    evidence = tmp_path / "upstream-evidence.json"
    evidence.write_text('{"result":"PASS"}', encoding="utf-8")
    acceptance = container.go_live.create_session(report, installer, "SPRINT-19-TEST", admin.id)
    for item in container.go_live.items(acceptance.id, admin.id):
        actor = admin if item.owner_type == "TECHNICAL" else clinical
        container.go_live.update_item(
            item.id, "PASS", actor.id, evidence_path=evidence, notes="Synthetic test fixture"
        )
    container.go_live.attest(acceptance.id, "CLINICAL", clinical.id)
    container.go_live.attest(acceptance.id, "TECHNICAL", admin.id)
    container.go_live.decide(
        acceptance.id, "GO", "Fixture limited rollout disetujui", approver.id
    )
    rollout = container.limited_rollout.create_session(
        acceptance.id, "Sprint 19 fixture rollout", 1, admin.id
    )
    wave = container.limited_rollout.add_wave(rollout.id, "Fixture terminal", 1, admin.id)
    container.limited_rollout.start(rollout.id, admin.id)
    container.limited_rollout.activate_wave(wave.id, admin.id)
    container.limited_rollout.complete_wave(wave.id, admin.id)
    container.limited_rollout.attest(rollout.id, "CLINICAL", clinical.id)
    container.limited_rollout.attest(rollout.id, "TECHNICAL", admin.id)
    container.limited_rollout.decide(
        rollout.id, "COMPLETE", "Fixture rollout selesai tanpa blocker", approver.id
    )
    surveillance = container.surveillance.create_session(
        rollout.id, "Production release fixture", admin.id,
        minimum_observation_hours=1, maximum_snapshot_age_hours=4,
    )
    with container.database.session() as session:
        session.add(ProcessingQueue(
            source_no_resep="PRODUCTION-RELEASE-FIXTURE", is_mock=False,
            processing_status="COMPLETED", review_status="REVIEWED", risk_status="SAFE",
            completeness_status="COMPLETE", overall_status="SAFE", alert_level="SAFE",
            detected_at=utc_now(),
        ))
        session.commit()
    first = container.surveillance.capture_snapshot(surveillance.id, admin.id)
    later = first.captured_at + timedelta(hours=2)
    monkeypatch.setattr("emss.services.surveillance.utc_now", lambda: later)
    container.surveillance.capture_snapshot(surveillance.id, admin.id)
    container.surveillance.attest(surveillance.id, "CLINICAL", clinical.id)
    container.surveillance.attest(surveillance.id, "TECHNICAL", admin.id)
    return container.surveillance.decide(
        surveillance.id, "PROMOTE", "Fixture promotion setelah observasi", approver.id
    ), installer_hash


def _evidence_payload(kind, installer_hash, *, now=None, waiver_expiry=None):
    now = now or utc_now()
    payload = {
        "format": "EMSS_PRODUCTION_EVIDENCE_V1",
        "evidence_type": kind,
        "status": "PASS",
        "application_version": __version__,
        "schema_revision": HEAD,
        "installer_checksum_sha256": installer_hash,
        "observed_at": now.isoformat(),
    }
    if kind == "AUTHENTICODE":
        payload["signature_status"] = "Valid"
    elif kind == "FORMAL_WAIVER":
        payload.update({
            "waiver_id": "CAB-WAIVER-TEST-001",
            "approved_by_external": "Synthetic External Approver",
            "valid_until": (waiver_expiry or now + timedelta(days=2)).isoformat(),
        })
    elif kind.startswith("CLEAN_"):
        payload.update({"clean_host": True, "host_fingerprint_sha256": "a" * 64})
    elif kind == "DATA_PRESERVATION":
        payload.update({
            "data_preserved": True,
            "data_checksum_before_sha256": "b" * 64,
            "data_checksum_after_sha256": "b" * 64,
        })
    elif kind == "ROLLBACK_RESTORE":
        payload.update({"rollback_tested": True, "restore_verified": True})
    return payload


def _write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _record_required_evidence(container, tmp_path, record, installer_hash, admin, signature="AUTHENTICODE"):
    kinds = (
        signature, "CLEAN_INSTALL", "CLEAN_UPGRADE", "CLEAN_UNINSTALL",
        "DATA_PRESERVATION", "ROLLBACK_RESTORE",
    )
    for kind in kinds:
        path = _write_json(tmp_path, f"{kind.lower()}.json", _evidence_payload(kind, installer_hash))
        container.production_release.record_evidence(record.id, kind, path, admin.id)


def _change_approval(tmp_path, installer_hash, *, start=None, end=None):
    now = utc_now()
    return _write_json(tmp_path, "change-approval.json", {
        "format": "EMSS_PRODUCTION_CHANGE_APPROVAL_V1",
        "status": "APPROVED",
        "application_version": __version__,
        "schema_revision": HEAD,
        "installer_checksum_sha256": installer_hash,
        "approval_reference": "CAB-TEST-2026-001",
        "approved_by_external": "Synthetic Hospital Change Board",
        "deployment_window_start": (start or now - timedelta(minutes=5)).isoformat(),
        "deployment_window_end": (end or now + timedelta(hours=2)).isoformat(),
    })


def _build_evidence_package(container, tmp_path, record):
    with container.database.session() as session:
        evidence = list(session.scalars(
            select(ProductionReleaseEvidence).where(
                ProductionReleaseEvidence.release_record_id == record.id
            )
        ).all())
        approval = session.scalar(
            select(ProductionChangeApproval).where(
                ProductionChangeApproval.release_record_id == record.id
            )
        )
        snapshot = container.production_release.evidence_snapshot_hash(evidence, approval)
        manifest = {
            "format": "EMSS_PRODUCTION_EVIDENCE_PACKAGE_V1",
            "release_record_id": record.id,
            "application_version": record.application_version,
            "schema_revision": record.schema_revision,
            "installer_checksum_sha256": record.installer_checksum_sha256,
            "evidence_snapshot_sha256": snapshot,
            "evidence": [
                {
                    "evidence_type": row.evidence_type,
                    "filename": row.evidence_filename,
                    "checksum_sha256": row.evidence_checksum_sha256,
                    "path": f"evidence/{row.evidence_type.lower()}.json",
                }
                for row in sorted(evidence, key=lambda item: item.evidence_type)
            ],
            "change_approval": {
                "filename": approval.evidence_filename,
                "checksum_sha256": approval.evidence_checksum_sha256,
                "path": "change/change-approval.json",
            },
        }
    package = tmp_path / "production-evidence-package.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for entry in manifest["evidence"]:
            archive.write(tmp_path / entry["filename"], entry["path"])
        archive.write(tmp_path / approval.evidence_filename, manifest["change_approval"]["path"])
    return package


def _rewrite_package(source, target, *, manifest_transform=None, member_transform=None):
    with zipfile.ZipFile(source, "r") as archive:
        members = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    manifest = json.loads(members["manifest.json"])
    if manifest_transform:
        manifest_transform(manifest)
    members["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    if member_transform:
        member_transform(members, manifest)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return target


def _verify_and_attest(container, tmp_path, record, admin, clinical, approver):
    verification = container.production_evidence.verify_package(
        record.id, _build_evidence_package(container, tmp_path, record), approver.id
    )
    assert verification.status == "VALID"
    container.production_evidence.start_ceremony(record.id, approver.id)
    container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)
    ceremony = container.production_evidence.attest_ceremony(
        record.id, "CLINICAL", clinical.id
    )
    assert ceremony.status == "ATTESTED"
    return verification, ceremony


@pytest.mark.integration
def test_authenticode_path_authorizes_only_inside_window_with_independent_decision(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, clinical, approver, decision = users
    surveillance, installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    _record_required_evidence(app_container, tmp_path, record, installer_hash, admin)
    start = utc_now() + timedelta(minutes=30)
    end = start + timedelta(hours=1)
    app_container.production_release.record_change_approval(
        record.id, _change_approval(tmp_path, installer_hash, start=start, end=end), approver.id
    )
    verification = app_container.production_evidence.verify_package(
        record.id, _build_evidence_package(app_container, tmp_path, record), approver.id
    )
    assert verification.status == "VALID"
    early = app_container.production_release.evaluate(record.id, decision.id)
    assert not early.ready_for_authorization
    assert "belum dimulai" in "; ".join(early.blockers)
    inside = start + timedelta(minutes=5)
    monkeypatch.setattr("emss.services.production_release.utc_now", lambda: inside)
    monkeypatch.setattr("emss.services.production_evidence.utc_now", lambda: inside)
    app_container.production_evidence.start_ceremony(record.id, approver.id)
    app_container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)
    app_container.production_evidence.attest_ceremony(record.id, "CLINICAL", clinical.id)
    assert app_container.production_release.evaluate(record.id, decision.id).ready_for_authorization
    with pytest.raises(ProductionReleaseError, match="independen"):
        app_container.production_release.decide(
            record.id, "AUTHORIZE", "Authorization fixture harus independen", approver.id
        )
    final = app_container.production_release.decide(
        record.id, "AUTHORIZE", "Manual deployment fixture diotorisasi", decision.id
    )
    assert final.status == "AUTHORIZED"
    readiness = app_container.production_release.evaluate(record.id, decision.id)
    assert readiness.manual_deployment_authorized
    assert readiness.signature_basis == "AUTHENTICODE"
    assert app_container.production_release.ledger(admin.id)[-1].event_type == "DECISION_AUTHORIZE"


@pytest.mark.integration
def test_formal_waiver_is_expiring_alternative_and_missing_evidence_fails_closed(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, clinical, approver, decision = users
    surveillance, installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    invalid = _evidence_payload("AUTHENTICODE", installer_hash)
    invalid["signature_status"] = "NotSigned"
    with pytest.raises(ProductionReleaseError, match="Valid"):
        app_container.production_release.record_evidence(
            record.id, "AUTHENTICODE", _write_json(tmp_path, "invalid-signature.json", invalid), admin.id
        )
    waiver_expiry = utc_now() + timedelta(hours=3)
    _record_required_evidence(
        app_container, tmp_path, record, installer_hash, admin, signature="FORMAL_WAIVER"
    )
    app_container.production_release.record_change_approval(
        record.id, _change_approval(tmp_path, installer_hash), approver.id
    )
    _verify_and_attest(app_container, tmp_path, record, admin, clinical, approver)
    ready = app_container.production_release.evaluate(record.id, decision.id)
    assert ready.ready_for_authorization and ready.signature_basis == "FORMAL_WAIVER"
    monkeypatch.setattr(
        "emss.services.production_release.utc_now", lambda: waiver_expiry + timedelta(days=2)
    )
    expired = app_container.production_release.evaluate(record.id, decision.id)
    assert not expired.ready_for_authorization
    assert "kedaluwarsa" in "; ".join(expired.blockers)


@pytest.mark.integration
def test_evidence_binding_duplicate_permission_and_immutable_controls(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, clinical, _approver, _decision = users
    surveillance, installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    path = _write_json(
        tmp_path, "clean-install.json", _evidence_payload("CLEAN_INSTALL", installer_hash)
    )
    with pytest.raises(ProductionReleasePermissionError):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", path, clinical.id
        )
    evidence = app_container.production_release.record_evidence(
        record.id, "CLEAN_INSTALL", path, admin.id
    )
    with pytest.raises(ProductionReleaseError, match="immutable"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", path, admin.id
        )
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(
                text("DELETE FROM production_release_evidence WHERE id=:id"), {"id": evidence.id}
            )


@pytest.mark.integration
def test_revocation_and_emergency_rollback_are_manual_fail_closed_actions(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, clinical, approver, decision = users
    surveillance, installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    _record_required_evidence(app_container, tmp_path, record, installer_hash, admin)
    app_container.production_release.record_change_approval(
        record.id, _change_approval(tmp_path, installer_hash), approver.id
    )
    _verify_and_attest(app_container, tmp_path, record, admin, clinical, approver)
    app_container.production_release.decide(
        record.id, "AUTHORIZE", "Authorization untuk uji revocation", decision.id
    )
    revoked = app_container.production_release.revoke(
        record.id, "Authorization dicabut oleh otoritas produksi", approver.id
    )
    assert revoked.status == "REVOKED"
    assert not app_container.production_release.evaluate(record.id, decision.id).manual_deployment_authorized

    # A separate draft can record an emergency order even after ledger tampering;
    # it never invokes an installer or production endpoint.
    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_production_ledger_no_update"))
        session.execute(text("UPDATE production_release_ledger SET payload_json='{}' WHERE id=1"))
        session.commit()
    with pytest.raises(ProductionReleaseError, match="Ledger"):
        app_container.production_release.ledger(admin.id)
    with pytest.raises(ProductionReleaseError, match="terminal"):
        app_container.production_release.order_emergency_rollback(
            record.id, "Rollback darurat setelah authorization dicabut", admin.id
        )


@pytest.mark.integration
def test_emergency_rollback_can_be_ordered_from_draft_without_deployment(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, _clinical, _approver, _decision = users
    surveillance, _installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    ordered = app_container.production_release.order_emergency_rollback(
        record.id, "Rollback darurat manual sebelum deployment", admin.id
    )
    assert ordered.status == "ROLLBACK_ORDERED"
    readiness = app_container.production_release.evaluate(record.id, admin.id)
    assert not readiness.manual_deployment_authorized
    assert "ROLLBACK_ORDERED" in "; ".join(readiness.blockers)


@pytest.mark.integration
def test_production_release_downgrade_and_reupgrade_preserves_all_upstream_ledgers(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, _clinical, _approver, _decision = users
    surveillance, _installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    app_container.production_release.create_record(surveillance.id, admin.id)
    with app_container.database.session() as session:
        upstream_counts = tuple(session.execute(text(query)).scalar_one() for query in (
            "SELECT count(*) FROM go_live_decision_ledger",
            "SELECT count(*) FROM limited_rollout_ledger",
            "SELECT count(*) FROM surveillance_ledger",
        ))
    command.downgrade(app_container.database._alembic_config(), "0021_early_life_surveillance")
    assert app_container.database.current_revision() == "0021_early_life_surveillance"
    assert "production_release_record" not in inspect(app_container.database.engine).get_table_names()
    app_container.database.migrate()
    assert app_container.database.current_revision() == HEAD
    with app_container.database.session() as session:
        assert upstream_counts == tuple(session.execute(text(query)).scalar_one() for query in (
            "SELECT count(*) FROM go_live_decision_ledger",
            "SELECT count(*) FROM limited_rollout_ledger",
            "SELECT count(*) FROM surveillance_ledger",
        ))


@pytest.mark.integration
def test_evidence_and_change_contract_negative_paths_fail_closed(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, _clinical, approver, _decision = users
    surveillance, installer_hash = _promoted_surveillance(app_container, tmp_path, monkeypatch, users)
    record = app_container.production_release.create_record(surveillance.id, admin.id)

    with pytest.raises(ProductionReleaseError, match="tidak dikenal"):
        app_container.production_release.record_evidence(
            record.id, "UNKNOWN", tmp_path / "missing.json", admin.id
        )
    with pytest.raises(ProductionReleaseError, match="tidak ditemukan"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", tmp_path / "missing.json", admin.id
        )
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(ProductionReleaseError, match="Ukuran"):
        app_container.production_release.record_evidence(record.id, "CLEAN_INSTALL", empty, admin.id)
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(ProductionReleaseError, match="JSON UTF-8"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", invalid_json, admin.id
        )
    array_json = _write_json(tmp_path, "array.json", ["not", "an", "object"])
    with pytest.raises(ProductionReleaseError, match="object"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", array_json, admin.id
        )

    now = utc_now()
    cases = []
    wrong_format = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    wrong_format["format"] = "WRONG"
    cases.append(("CLEAN_INSTALL", wrong_format, "Format"))
    wrong_type = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    wrong_type["evidence_type"] = "CLEAN_UPGRADE"
    cases.append(("CLEAN_INSTALL", wrong_type, "tidak cocok"))
    failed = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    failed["status"] = "FAIL"
    cases.append(("CLEAN_INSTALL", failed, "PASS"))
    unbound = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    unbound["application_version"] = "9.9.9"
    cases.append(("CLEAN_INSTALL", unbound, "tidak terikat"))
    future = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now + timedelta(minutes=10))
    cases.append(("CLEAN_INSTALL", future, "masa depan"))
    naive = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    naive["observed_at"] = now.replace(tzinfo=None).isoformat()
    cases.append(("CLEAN_INSTALL", naive, "timezone"))
    expired = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    expired["valid_until"] = (now - timedelta(minutes=1)).isoformat()
    cases.append(("CLEAN_INSTALL", expired, "kedaluwarsa"))
    bad_clean = _evidence_payload("CLEAN_INSTALL", installer_hash, now=now)
    bad_clean["host_fingerprint_sha256"] = "not-a-hash"
    cases.append(("CLEAN_INSTALL", bad_clean, "clean-host"))
    bad_data = _evidence_payload("DATA_PRESERVATION", installer_hash, now=now)
    bad_data["data_checksum_after_sha256"] = "c" * 64
    cases.append(("DATA_PRESERVATION", bad_data, "preservasi"))
    bad_rollback = _evidence_payload("ROLLBACK_RESTORE", installer_hash, now=now)
    bad_rollback["restore_verified"] = False
    cases.append(("ROLLBACK_RESTORE", bad_rollback, "rollback/restore"))
    waiver_no_reference = _evidence_payload("FORMAL_WAIVER", installer_hash, now=now)
    waiver_no_reference["waiver_id"] = ""
    cases.append(("FORMAL_WAIVER", waiver_no_reference, "referensi"))
    waiver_no_approver = _evidence_payload("FORMAL_WAIVER", installer_hash, now=now)
    waiver_no_approver["approved_by_external"] = ""
    cases.append(("FORMAL_WAIVER", waiver_no_approver, "approver"))
    waiver_no_expiry = _evidence_payload("FORMAL_WAIVER", installer_hash, now=now)
    waiver_no_expiry.pop("valid_until")
    cases.append(("FORMAL_WAIVER", waiver_no_expiry, "expiry"))
    for index, (kind, payload, message) in enumerate(cases):
        with pytest.raises(ProductionReleaseError, match=message):
            app_container.production_release.record_evidence(
                record.id, kind, _write_json(tmp_path, f"bad-{index}.json", payload), admin.id
            )

    change_base = json.loads(_change_approval(tmp_path, installer_hash).read_text(encoding="utf-8"))
    change_cases = []
    bad = dict(change_base); bad["format"] = "WRONG"
    change_cases.append((bad, "tidak valid"))
    bad = dict(change_base); bad["schema_revision"] = "wrong"
    change_cases.append((bad, "tidak terikat"))
    bad = dict(change_base); bad["approval_reference"] = ""
    change_cases.append((bad, "Referensi"))
    bad = dict(change_base); bad["deployment_window_start"] = bad["deployment_window_end"]
    change_cases.append((bad, "window tidak valid"))
    bad = dict(change_base); bad["deployment_window_end"] = (now - timedelta(minutes=1)).isoformat()
    change_cases.append((bad, "telah berakhir"))
    bad = dict(change_base); bad["deployment_window_end"] = (now + timedelta(days=20)).isoformat()
    change_cases.append((bad, "melewati expiry"))
    bad = dict(change_base); bad["deployment_window_start"] = "not-a-date"
    change_cases.append((bad, "ISO-8601"))
    for index, (payload, message) in enumerate(change_cases):
        with pytest.raises(ProductionReleaseError, match=message):
            app_container.production_release.record_change_approval(
                record.id,
                _write_json(tmp_path, f"bad-change-{index}.json", payload),
                approver.id,
            )

    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_production_ledger_no_update"))
        session.execute(text("UPDATE production_release_ledger SET payload_json='{}' WHERE id=1"))
        session.commit()
    broken = app_container.production_release.evaluate(record.id, admin.id)
    assert not broken.ledger_valid
    valid = _write_json(
        tmp_path, "valid-after-tamper.json", _evidence_payload("CLEAN_INSTALL", installer_hash)
    )
    with pytest.raises(ProductionReleaseError, match="Ledger"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", valid, admin.id
        )
    assert app_container.production_release.order_emergency_rollback(
        record.id, "Rollback darurat walau ledger terdeteksi rusak", admin.id
    ).status == "ROLLBACK_ORDERED"


@pytest.mark.integration
def test_record_validation_listing_reject_and_terminal_state_controls(
    app_container, tmp_path, monkeypatch
):
    admin, clinical, approver, decision = users = _users(app_container)
    with pytest.raises(ProductionReleaseError, match="1-30"):
        app_container.production_release.create_record("missing", admin.id, validity_days=0)
    with pytest.raises(ProductionReleasePermissionError, match="aktif"):
        app_container.production_release.create_record("missing", "missing-user")
    with pytest.raises(ProductionReleaseError, match="Surveillance tidak ditemukan"):
        app_container.production_release.create_record("missing", admin.id)
    surveillance, _installer_hash = _promoted_surveillance(
        app_container, tmp_path, monkeypatch, users
    )
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    assert app_container.production_release.records(clinical.id)[0].id == record.id
    assert app_container.production_release.evidence(record.id, clinical.id) == ()
    assert app_container.production_release.evaluate(record.id).record.status == "DRAFT"
    with pytest.raises(ProductionReleaseError, match="sudah memiliki"):
        app_container.production_release.create_record(surveillance.id, admin.id)
    with pytest.raises(ProductionReleaseError, match="tidak ditemukan"):
        app_container.production_release.evidence("missing", admin.id)
    with pytest.raises(ProductionReleaseError, match="10-300"):
        app_container.production_release.decide(record.id, "REJECT", "singkat", decision.id)
    with pytest.raises(ProductionReleaseError, match="AUTHORIZE atau REJECT"):
        app_container.production_release.decide(
            record.id, "HOLD", "Alasan keputusan fixture cukup panjang", decision.id
        )
    with pytest.raises(ProductionReleaseError, match="authorization aktif"):
        app_container.production_release.revoke(
            record.id, "Belum ada authorization untuk dicabut", approver.id
        )
    rejected = app_container.production_release.decide(
        record.id, "REJECT", "Evidence eksternal fixture belum lengkap", decision.id
    )
    assert rejected.status == "REJECTED"
    unused = _write_json(
        tmp_path,
        "unused.json",
        _evidence_payload("CLEAN_INSTALL", record.installer_checksum_sha256),
    )
    with pytest.raises(ProductionReleaseError, match="bukan DRAFT"):
        app_container.production_release.record_evidence(
            record.id, "CLEAN_INSTALL", unused, admin.id
        )
    with pytest.raises(ProductionReleaseError, match="terminal"):
        app_container.production_release.order_emergency_rollback(
            record.id, "Rollback tidak dapat mengubah state terminal", admin.id
        )


def _prepared_sprint20_release(app_container, tmp_path, monkeypatch):
    users = _users(app_container)
    admin, clinical, approver, decision = users
    surveillance, installer_hash = _promoted_surveillance(
        app_container, tmp_path, monkeypatch, users
    )
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    _record_required_evidence(app_container, tmp_path, record, installer_hash, admin)
    app_container.production_release.record_change_approval(
        record.id, _change_approval(tmp_path, installer_hash), approver.id
    )
    package = _build_evidence_package(app_container, tmp_path, record)
    return users, record, installer_hash, package


@pytest.mark.integration
def test_verified_package_ceremony_and_authorization_receipt_are_bound_and_manual_only(
    app_container, tmp_path, monkeypatch
):
    (admin, clinical, approver, decision), record, _hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )
    before = app_container.production_release.evaluate(record.id, decision.id)
    assert not before.ready_for_authorization
    assert "belum diverifikasi" in "; ".join(before.blockers)
    verification = app_container.production_evidence.verify_package(
        record.id, package, approver.id
    )
    assert verification.status == "VALID" and verification.entry_count == 7
    assert len(verification.evidence_snapshot_sha256 or "") == 64
    ceremony = app_container.production_evidence.start_ceremony(record.id, approver.id)
    assert ceremony.status == "OPEN"
    app_container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)
    ceremony = app_container.production_evidence.attest_ceremony(
        record.id, "CLINICAL", clinical.id
    )
    assert ceremony.status == "ATTESTED"
    assert app_container.production_release.evaluate(record.id, decision.id).ready_for_authorization
    app_container.production_release.decide(
        record.id, "AUTHORIZE", "Authorization setelah package dan ceremony", decision.id
    )
    receipt_path = tmp_path / "authorization-receipt.json"
    receipt = app_container.production_evidence.export_authorization_receipt(
        record.id, receipt_path, decision.id
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["format"] == "EMSS_PRODUCTION_AUTHORIZATION_RECEIPT_V1"
    assert payload["deployment_execution"] == "NOT_PERFORMED_BY_EMSS"
    assert payload["package_checksum_sha256"] == verification.package_checksum_sha256
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == receipt.checksum_sha256
    with pytest.raises(ProductionEvidenceError, match="sudah ada"):
        app_container.production_evidence.export_authorization_receipt(
            record.id, receipt_path, decision.id
        )


@pytest.mark.integration
def test_latest_invalid_package_supersedes_valid_and_verification_is_immutable(
    app_container, tmp_path, monkeypatch
):
    (_admin, _clinical, approver, decision), record, _hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )
    valid = app_container.production_evidence.verify_package(record.id, package, approver.id)
    assert valid.status == "VALID"
    invalid_package = tmp_path / "evidence-with-extra.zip"
    with zipfile.ZipFile(package, "r") as source, zipfile.ZipFile(
        invalid_package, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info.filename))
        target.writestr("undeclared.json", "{}")
    invalid = app_container.production_evidence.verify_package(
        record.id, invalid_package, approver.id
    )
    assert invalid.status == "INVALID" and invalid.error_code == "UNDECLARED_MEMBER"
    rows = app_container.production_evidence.verifications(record.id, decision.id)
    assert [row.status for row in rows] == ["VALID", "INVALID"]
    readiness = app_container.production_release.evaluate(record.id, decision.id)
    assert "terbaru INVALID" in "; ".join(readiness.blockers)
    with pytest.raises(ProductionEvidenceError, match="belum VALID"):
        app_container.production_evidence.start_ceremony(record.id, approver.id)
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(
                text("DELETE FROM production_evidence_package_verification WHERE id=:id"),
                {"id": valid.id},
            )


@pytest.mark.integration
def test_package_rejects_unsafe_zip_and_patient_identity_keys(
    app_container, tmp_path, monkeypatch
):
    users = _users(app_container)
    admin, _clinical, approver, _decision = users
    surveillance, installer_hash = _promoted_surveillance(
        app_container, tmp_path, monkeypatch, users
    )
    record = app_container.production_release.create_record(surveillance.id, admin.id)
    kinds = (
        "AUTHENTICODE", "CLEAN_INSTALL", "CLEAN_UPGRADE", "CLEAN_UNINSTALL",
        "DATA_PRESERVATION", "ROLLBACK_RESTORE",
    )
    for kind in kinds:
        payload = _evidence_payload(kind, installer_hash)
        if kind == "CLEAN_INSTALL":
            payload["patient_name"] = "SYNTHETIC MUST STILL BE REJECTED"
        path = _write_json(tmp_path, f"{kind.lower()}.json", payload)
        app_container.production_release.record_evidence(record.id, kind, path, admin.id)
    app_container.production_release.record_change_approval(
        record.id, _change_approval(tmp_path, installer_hash), approver.id
    )
    sensitive = app_container.production_evidence.verify_package(
        record.id, _build_evidence_package(app_container, tmp_path, record), approver.id
    )
    assert sensitive.status == "INVALID" and sensitive.error_code == "SENSITIVE_KEY"
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.json", "{}")
    unsafe_result = app_container.production_evidence.verify_package(
        record.id, unsafe, approver.id
    )
    assert unsafe_result.status == "INVALID" and unsafe_result.error_code == "UNSAFE_MEMBER"


@pytest.mark.integration
def test_ceremony_permissions_abort_and_terminal_immutability(
    app_container, tmp_path, monkeypatch
):
    (admin, clinical, approver, _decision), record, _hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )
    with pytest.raises(ProductionEvidenceError, match="belum VALID"):
        app_container.production_evidence.start_ceremony(record.id, approver.id)
    app_container.production_evidence.verify_package(record.id, package, approver.id)
    ceremony = app_container.production_evidence.start_ceremony(record.id, approver.id)
    with pytest.raises(ProductionReleasePermissionError):
        app_container.production_evidence.attest_ceremony(
            record.id, "TECHNICAL", clinical.id
        )
    with pytest.raises(ProductionEvidenceError, match="TECHNICAL atau CLINICAL"):
        app_container.production_evidence.attest_ceremony(record.id, "LEGAL", approver.id)
    app_container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)
    with pytest.raises(ProductionEvidenceError, match="sudah tersedia"):
        app_container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)
    aborted = app_container.production_evidence.abort_ceremony(
        record.id, "Ceremony dihentikan sebelum perubahan produksi", admin.id
    )
    assert aborted.status == "ABORTED"
    with pytest.raises(ProductionEvidenceError, match="terminal"):
        app_container.production_evidence.attest_ceremony(record.id, "CLINICAL", clinical.id)
    with app_container.database.session() as session:
        with pytest.raises(DatabaseError):
            session.execute(
                text("DELETE FROM production_deployment_ceremony WHERE id=:id"),
                {"id": ceremony.id},
            )


@pytest.mark.integration
def test_package_manifest_failure_matrix_is_persisted_fail_closed(
    app_container, tmp_path, monkeypatch
):
    (_admin, _clinical, approver, _decision), record, _hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )

    cases = []

    def add_case(name, code, transform):
        cases.append((name, code, transform))

    add_case("format", "FORMAT_INVALID", lambda value: value.update(format="WRONG"))
    add_case("binding", "BINDING_MISMATCH", lambda value: value.update(application_version="0.0.0"))
    add_case("structure", "MANIFEST_STRUCTURE", lambda value: value.update(evidence={}))
    add_case("count", "EVIDENCE_SET_MISMATCH", lambda value: value["evidence"].pop())
    add_case("entry", "ENTRY_INVALID", lambda value: value["evidence"].__setitem__(0, "bad"))
    add_case(
        "duplicate-kind",
        "EVIDENCE_SET_MISMATCH",
        lambda value: value["evidence"][1].update(
            evidence_type=value["evidence"][0]["evidence_type"]
        ),
    )
    add_case(
        "member-binding",
        "MEMBER_BINDING",
        lambda value: value["evidence"][0].update(path="missing.json"),
    )
    add_case(
        "checksum-binding",
        "CHECKSUM_BINDING",
        lambda value: value["evidence"][0].update(filename="wrong.json"),
    )
    add_case(
        "snapshot",
        "SNAPSHOT_MISMATCH",
        lambda value: value.update(evidence_snapshot_sha256="0" * 64),
    )
    for name, expected, transform in cases:
        result = app_container.production_evidence.verify_package(
            record.id,
            _rewrite_package(package, tmp_path / f"invalid-{name}.zip", manifest_transform=transform),
            approver.id,
        )
        assert result.status == "INVALID" and result.error_code == expected

    bad_zip = tmp_path / "not-a-zip.zip"
    bad_zip.write_bytes(b"not zip")
    assert app_container.production_evidence.verify_package(
        record.id, bad_zip, approver.id
    ).error_code == "ZIP_INVALID"
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w"):
        pass
    assert app_container.production_evidence.verify_package(
        record.id, empty_zip, approver.id
    ).error_code == "MEMBER_COUNT"
    no_manifest = tmp_path / "no-manifest.zip"
    with zipfile.ZipFile(no_manifest, "w") as archive:
        archive.writestr("evidence.json", "{}")
    assert app_container.production_evidence.verify_package(
        record.id, no_manifest, approver.id
    ).error_code == "MANIFEST_MISSING"


@pytest.mark.integration
def test_evidence_and_ceremony_boundary_controls(
    app_container, tmp_path, monkeypatch
):
    (admin, clinical, approver, decision), record, installer_hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )
    with pytest.raises(ProductionEvidenceError, match="tidak ditemukan"):
        app_container.production_evidence.verify_package(
            record.id, tmp_path / "missing.zip", approver.id
        )
    empty = tmp_path / "zero.zip"
    empty.write_bytes(b"")
    with pytest.raises(ProductionEvidenceError, match="Ukuran"):
        app_container.production_evidence.verify_package(record.id, empty, approver.id)
    assert app_container.production_evidence.ceremony(record.id, decision.id) is None
    with pytest.raises(ProductionEvidenceError, match="belum tersedia"):
        app_container.production_evidence.attest_ceremony(record.id, "CLINICAL", clinical.id)
    with pytest.raises(ProductionEvidenceError, match="authorization aktif"):
        app_container.production_evidence.export_authorization_receipt(
            record.id, tmp_path / "blocked-receipt.json", decision.id
        )
    with pytest.raises(ProductionEvidenceError, match="Tujuan receipt"):
        app_container.production_evidence.export_authorization_receipt(
            record.id, tmp_path / "receipt.txt", decision.id
        )

    app_container.production_evidence.verify_package(record.id, package, approver.id)
    app_container.production_evidence.start_ceremony(record.id, approver.id)
    with pytest.raises(ProductionEvidenceError, match="immutable"):
        app_container.production_evidence.start_ceremony(record.id, approver.id)
    invalid = tmp_path / "invalid-after-start.zip"
    with zipfile.ZipFile(invalid, "w") as archive:
        archive.writestr("manifest.json", "[]")
    assert app_container.production_evidence.verify_package(
        record.id, invalid, approver.id
    ).status == "INVALID"
    with pytest.raises(ProductionEvidenceError, match="Binding verifikasi"):
        app_container.production_evidence.attest_ceremony(record.id, "TECHNICAL", admin.id)

    # A newly added alternative signature basis makes the previously valid snapshot stale.
    second_users = _users_for_additional_record(app_container, admin, suffix="stale")
    second_admin, _second_clinical, second_approver, _second_decision = second_users
    stale_root = tmp_path / "stale"
    stale_root.mkdir()
    monkeypatch.setattr("emss.services.surveillance.utc_now", utc_now)
    surveillance, second_hash = _promoted_surveillance(
        app_container, stale_root, monkeypatch, second_users
    )
    stale_record = app_container.production_release.create_record(surveillance.id, second_admin.id)
    _record_required_evidence(
        app_container, stale_root, stale_record, second_hash, second_admin
    )
    app_container.production_release.record_change_approval(
        stale_record.id,
        _change_approval(stale_root, second_hash),
        second_approver.id,
    )
    stale_package = _build_evidence_package(
        app_container, stale_root, stale_record
    )
    app_container.production_evidence.verify_package(
        stale_record.id, stale_package, second_approver.id
    )
    waiver = _write_json(
        stale_root,
        "formal_waiver.json",
        _evidence_payload("FORMAL_WAIVER", second_hash),
    )
    app_container.production_release.record_evidence(
        stale_record.id, "FORMAL_WAIVER", waiver, second_admin.id
    )
    with pytest.raises(ProductionEvidenceError, match="stale"):
        app_container.production_evidence.start_ceremony(stale_record.id, second_approver.id)


@pytest.mark.integration
def test_sprint20_migration_downgrade_and_reupgrade_preserves_sprint19_release_data(
    app_container, tmp_path, monkeypatch
):
    (admin, _clinical, approver, _decision), record, _hash, package = _prepared_sprint20_release(
        app_container, tmp_path, monkeypatch
    )
    app_container.production_evidence.verify_package(record.id, package, approver.id)
    command.downgrade(
        app_container.database._alembic_config(), "0022_production_release_authorization"
    )
    assert app_container.database.current_revision() == "0022_production_release_authorization"
    tables = inspect(app_container.database.engine).get_table_names()
    assert "production_evidence_package_verification" not in tables
    with app_container.database.session() as session:
        assert session.execute(
            text("SELECT count(*) FROM production_release_record WHERE id=:id"),
            {"id": record.id},
        ).scalar_one() == 1
        assert session.execute(text("SELECT count(*) FROM production_release_ledger")).scalar_one() > 0
    app_container.database.migrate()
    assert app_container.database.current_revision() == HEAD
    assert "production_evidence_package_verification" in inspect(
        app_container.database.engine
    ).get_table_names()


