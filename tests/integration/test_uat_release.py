from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from emss import __version__
from emss.services.uat_release import (
    UatReleaseError,
    UatReleasePermissionError,
    UatReleaseService,
)
from emss.utils.time import utc_now


HEAD = "0029_kfa_identity"


def _users(container):
    admin = container.users.create_first_admin(
        username="admin.uat.release", display_name="Admin UAT Release", password="Admin#Aman2026"
    )

    def user(name, roles):
        return container.users.create_user(
            username=f"{name}.uat.release",
            display_name=name.replace(".", " ").title(),
            password="User#Aman2026",
            roles=roles,
            actor_user_id=admin.id,
        )

    return {
        "admin": admin,
        "technical_attestor": user("technical.attestor", ("IT_ADMIN",)),
        "technical_tester": user("technical.tester", ("IT_ADMIN",)),
        "technical_signer": user("technical.signer", ("IT_ADMIN",)),
        "clinical_attestor": user("clinical.attestor", ("APOTEKER",)),
        "clinical_tester": user("clinical.tester", ("APOTEKER",)),
        "clinical_signer": user("clinical.signer", ("KFT",)),
        "execution_creator": user("execution.creator", ("DIREKTUR",)),
        "decision": user("uat.decision", ("DIREKTUR",)),
    }


def _write_json(root, name, payload):
    path = root / name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _release_files(container, root):
    installer = root / f"E-MAS-Farmasi-Setup-{__version__}-x64.exe"
    installer.write_bytes(b"qualified-uat-release-candidate-fixture")
    checksum = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = _write_json(root, "release-qualification.json", {
        "format": "EMSS_RELEASE_QUALIFICATION_V1",
        "status": "QUALIFIED",
        "application_version": __version__,
        "schema_revision": HEAD,
        "artifacts": [{
            "path": f"installer/{installer.name}",
            "size_bytes": installer.stat().st_size,
            "checksum_sha256": checksum,
        }],
    })
    return report, installer, checksum


def _evidence_payload(kind, checksum, **extra):
    payload = {
        "format": UatReleaseService.EVIDENCE_FORMAT,
        "evidence_type": kind,
        "status": "PASS",
        "application_version": __version__,
        "schema_revision": HEAD,
        "installer_checksum_sha256": checksum,
        "observed_at": utc_now().isoformat(),
        UatReleaseService.EVIDENCE_CONTROL_FIELDS[kind]: True,
    }
    payload.update(extra)
    return payload


def _prepared_candidate(container, root):
    users = _users(container)
    report, installer, checksum = _release_files(container, root)
    candidate = container.uat_release.create_candidate(
        report, installer, "RS-UAT-STAGING", users["admin"].id
    )
    for kind in sorted(UatReleaseService.EVIDENCE_TYPES):
        path = _write_json(root, f"readiness-{kind.lower()}.json", _evidence_payload(kind, checksum))
        container.uat_release.record_readiness_evidence(
            candidate.id, kind, path, users["admin"].id
        )
    container.uat_release.attest_candidate(
        candidate.id, "CLINICAL", users["clinical_attestor"].id
    )
    candidate = container.uat_release.attest_candidate(
        candidate.id, "TECHNICAL", users["technical_attestor"].id
    )
    assert candidate.status == "SEALED"
    return users, candidate, checksum


def _result_payload(candidate, execution, scenario, owner, checksum, status="PASS"):
    return {
        "format": UatReleaseService.RESULT_FORMAT,
        "candidate_id": candidate.id,
        "session_id": execution.id,
        "application_version": candidate.application_version,
        "schema_revision": candidate.schema_revision,
        "installer_checksum_sha256": checksum,
        "scenario_code": scenario,
        "owner_type": owner,
        "status": status,
        "result_summary": f"Hasil aktual eksternal untuk {scenario} tercatat tanpa identitas pasien",
        "observed_at": utc_now().isoformat(),
    }


def _record_all_results(container, root, users, candidate, execution, checksum):
    for scenario, owner in sorted(UatReleaseService.SCENARIOS.items()):
        actor = users["clinical_tester"] if owner == "CLINICAL" else users["technical_tester"]
        path = _write_json(
            root,
            f"result-{scenario.lower()}.json",
            _result_payload(candidate, execution, scenario, owner, checksum),
        )
        container.uat_release.record_result(execution.id, path, actor.id)


@pytest.mark.integration
def test_uat_candidate_execution_acceptance_and_receipt_are_external_and_bound(
    app_container, tmp_path
):
    users, candidate, checksum = _prepared_candidate(app_container, tmp_path)
    readiness = app_container.uat_release.evaluate(candidate.id, users["decision"].id)
    assert readiness.ready_to_start and not readiness.ready_for_acceptance
    kit = app_container.uat_release.export_uat_kit(
        candidate.id, tmp_path / "uat-kit.zip", users["clinical_attestor"].id
    )
    assert hashlib.sha256(kit.path.read_bytes()).hexdigest() == kit.checksum_sha256
    with zipfile.ZipFile(kit.path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["execution_status"] == "NOT_STARTED"
    assert all(row["result"] == "NOT_RECORDED" for row in manifest["scenarios"])

    execution = app_container.uat_release.start_execution(
        candidate.id, users["execution_creator"].id
    )
    _record_all_results(app_container, tmp_path, users, candidate, execution, checksum)
    issue = app_container.uat_release.raise_issue(
        execution.id, "WARNING", "Temuan fixture perlu diverifikasi sebelum sign-off", users["clinical_tester"].id
    )
    assert app_container.uat_release.evaluate(candidate.id).open_issues == 1
    app_container.uat_release.resolve_issue(
        issue.id, "Remediasi fixture diverifikasi secara independen", users["technical_tester"].id
    )
    app_container.uat_release.sign_execution(
        execution.id, "CLINICAL", users["clinical_signer"].id
    )
    app_container.uat_release.sign_execution(
        execution.id, "TECHNICAL", users["technical_signer"].id
    )
    assert app_container.uat_release.evaluate(candidate.id).ready_for_acceptance
    accepted = app_container.uat_release.decide_execution(
        execution.id, "ACCEPT", "UAT fixture diterima setelah seluruh evidence aktual diverifikasi", users["decision"].id
    )
    assert accepted.status == "ACCEPTED"
    assert app_container.uat_release.evaluate(candidate.id).uat_accepted_active
    receipt = app_container.uat_release.export_acceptance_receipt(
        execution.id, tmp_path / "uat-acceptance-receipt.json", users["decision"].id
    )
    payload = json.loads(receipt.path.read_text(encoding="utf-8"))
    assert payload["execution_origin"] == "EXTERNAL_HOSPITAL_EVIDENCE"
    assert payload["production_authorization"] == "NOT_GRANTED_BY_UAT_ACCEPTANCE"
    assert payload["installer_checksum_sha256"] == checksum


@pytest.mark.integration
def test_uat_evidence_validation_permissions_and_independence_fail_closed(app_container, tmp_path):
    users = _users(app_container)
    report, installer, checksum = _release_files(app_container, tmp_path)
    with pytest.raises(UatReleaseError, match="1-30"):
        app_container.uat_release.create_candidate(
            report, installer, "RS-UAT", users["admin"].id, validity_days=0
        )
    with pytest.raises(UatReleasePermissionError):
        app_container.uat_release.create_candidate(
            report, installer, "RS-UAT", users["clinical_tester"].id
        )
    candidate = app_container.uat_release.create_candidate(
        report, installer, "RS-UAT", users["admin"].id
    )
    with pytest.raises(UatReleaseError, match="belum lengkap"):
        app_container.uat_release.attest_candidate(
            candidate.id, "CLINICAL", users["clinical_attestor"].id
        )
    for kind in sorted(UatReleaseService.EVIDENCE_TYPES):
        extra = {"patient_name": "MUST BE REJECTED"} if kind == "TEST_DATA_APPROVAL" else {}
        path = _write_json(tmp_path, f"bad-{kind}.json", _evidence_payload(kind, checksum, **extra))
        if extra:
            with pytest.raises(UatReleaseError, match="identitas pasien"):
                app_container.uat_release.record_readiness_evidence(
                    candidate.id, kind, path, users["admin"].id
                )
            path = _write_json(tmp_path, f"good-{kind}.json", _evidence_payload(kind, checksum))
        app_container.uat_release.record_readiness_evidence(
            candidate.id, kind, path, users["admin"].id
        )
    with pytest.raises(UatReleaseError, match="independen"):
        app_container.uat_release.attest_candidate(
            candidate.id, "TECHNICAL", users["admin"].id
        )
    app_container.uat_release.attest_candidate(
        candidate.id, "CLINICAL", users["clinical_attestor"].id
    )
    app_container.uat_release.attest_candidate(
        candidate.id, "TECHNICAL", users["technical_attestor"].id
    )
    with pytest.raises(UatReleaseError, match="sudah terminal|bukan DRAFT"):
        app_container.uat_release.record_readiness_evidence(
            candidate.id,
            "SITE_APPROVAL",
            _write_json(tmp_path, "duplicate.json", _evidence_payload("SITE_APPROVAL", checksum)),
            users["admin"].id,
        )


@pytest.mark.integration
def test_latest_failed_result_and_issue_revoke_signoffs_until_remediated(app_container, tmp_path):
    users, candidate, checksum = _prepared_candidate(app_container, tmp_path)
    execution = app_container.uat_release.start_execution(
        candidate.id, users["execution_creator"].id
    )
    _record_all_results(app_container, tmp_path, users, candidate, execution, checksum)
    failed_scenario = "CLINICAL_DDI_CRITICAL"
    failed = _write_json(
        tmp_path, "failed-result.json",
        _result_payload(candidate, execution, failed_scenario, "CLINICAL", checksum, "FAIL"),
    )
    app_container.uat_release.record_result(
        execution.id, failed, users["clinical_tester"].id
    )
    with pytest.raises(UatReleaseError, match="latest belum PASS"):
        app_container.uat_release.sign_execution(
            execution.id, "CLINICAL", users["clinical_signer"].id
        )
    fixed = _write_json(
        tmp_path, "fixed-result.json",
        _result_payload(candidate, execution, failed_scenario, "CLINICAL", checksum),
    )
    app_container.uat_release.record_result(
        execution.id, fixed, users["clinical_tester"].id
    )
    app_container.uat_release.sign_execution(
        execution.id, "CLINICAL", users["clinical_signer"].id
    )
    app_container.uat_release.sign_execution(
        execution.id, "TECHNICAL", users["technical_signer"].id
    )
    late_issue = app_container.uat_release.raise_issue(
        execution.id, "CRITICAL", "Isu kritis fixture membatalkan sign-off yang telah diberikan", users["clinical_tester"].id
    )
    state = app_container.uat_release.execution(candidate.id, users["decision"].id)
    assert state.clinical_signed_by is None and state.technical_signed_by is None
    with pytest.raises(UatReleaseError, match="issue UAT terbuka"):
        app_container.uat_release.sign_execution(
            execution.id, "CLINICAL", users["clinical_signer"].id
        )
    app_container.uat_release.resolve_issue(
        late_issue.id, "Isu kritis fixture telah diremediasi dan diverifikasi", users["technical_tester"].id
    )


@pytest.mark.integration
def test_uat_acceptance_revocation_and_immutable_ledgers(app_container, tmp_path):
    users, candidate, checksum = _prepared_candidate(app_container, tmp_path)
    execution = app_container.uat_release.start_execution(
        candidate.id, users["execution_creator"].id
    )
    _record_all_results(app_container, tmp_path, users, candidate, execution, checksum)
    app_container.uat_release.sign_execution(execution.id, "CLINICAL", users["clinical_signer"].id)
    app_container.uat_release.sign_execution(execution.id, "TECHNICAL", users["technical_signer"].id)
    with pytest.raises(UatReleaseError, match="independen"):
        app_container.uat_release.decide_execution(
            execution.id, "ACCEPT", "Creator tidak boleh menerima execution miliknya", users["execution_creator"].id
        )
    app_container.uat_release.decide_execution(
        execution.id, "ACCEPT", "Decision maker independen menerima seluruh hasil UAT", users["decision"].id
    )
    revoked = app_container.uat_release.revoke_acceptance(
        execution.id, "Acceptance dicabut karena perubahan eksternal material", users["decision"].id
    )
    assert revoked.status == "REVOKED"
    assert not app_container.uat_release.evaluate(candidate.id).uat_accepted_active
    with app_container.database.session() as session:
        for statement in (
            "DELETE FROM uat_readiness_evidence",
            "UPDATE uat_execution_result SET status='PASS'",
            "DELETE FROM uat_execution_ledger",
        ):
            with pytest.raises(DatabaseError):
                session.execute(text(statement))
            session.rollback()


@pytest.mark.integration
def test_uat_candidate_input_and_evidence_negative_matrix(app_container, tmp_path):
    users = _users(app_container)
    report, installer, checksum = _release_files(app_container, tmp_path)
    with pytest.raises(UatReleaseError, match="Label environment"):
        app_container.uat_release.create_candidate(report, installer, "x", users["admin"].id)
    with pytest.raises(UatReleaseError, match="tidak ditemukan"):
        app_container.uat_release.create_candidate(
            report, tmp_path / "missing.exe", "RS-UAT", users["admin"].id
        )
    for name, mutation, message in (
        ("bad-format", {"format": "WRONG"}, "Qualification"),
        ("bad-version", {"application_version": "0.0.0"}, "Qualification"),
        ("bad-artifacts", {"artifacts": []}, "Installer tidak terikat"),
    ):
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload.update(mutation)
        bad = _write_json(tmp_path, f"{name}.json", payload)
        with pytest.raises(UatReleaseError, match=message):
            app_container.uat_release.create_candidate(
                bad, installer, "RS-UAT", users["admin"].id
            )
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(UatReleaseError, match="JSON UTF-8"):
        app_container.uat_release.create_candidate(
            invalid_json, installer, "RS-UAT", users["admin"].id
        )
    list_json = tmp_path / "list.json"
    list_json.write_text("[]", encoding="utf-8")
    with pytest.raises(UatReleaseError, match="wajib object"):
        app_container.uat_release.create_candidate(
            list_json, installer, "RS-UAT", users["admin"].id
        )
    candidate = app_container.uat_release.create_candidate(
        report, installer, "RS-UAT", users["admin"].id
    )
    assert app_container.uat_release.candidates(users["decision"].id)[0].id == candidate.id
    with pytest.raises(UatReleaseError, match="dossier UAT aktif"):
        app_container.uat_release.create_candidate(
            report, installer, "RS-UAT-2", users["admin"].id
        )
    with pytest.raises(UatReleaseError, match="Jenis readiness"):
        app_container.uat_release.record_readiness_evidence(
            candidate.id, "UNKNOWN", report, users["admin"].id
        )
    base = _evidence_payload("SITE_APPROVAL", checksum)
    variants = (
        ({**base, "status": "FAIL"}, "tidak terikat"),
        ({**base, "site_approved": False}, "belum terverifikasi"),
        ({**base, "observed_at": (utc_now() - timedelta(days=91)).isoformat()}, "freshness"),
        ({**base, "valid_until": (utc_now() - timedelta(minutes=1)).isoformat()}, "Masa berlaku"),
        ({**base, "observed_at": "not-a-time"}, "ISO-8601"),
    )
    for index, (payload, message) in enumerate(variants):
        with pytest.raises(UatReleaseError, match=message):
            app_container.uat_release.record_readiness_evidence(
                candidate.id, "SITE_APPROVAL",
                _write_json(tmp_path, f"invalid-readiness-{index}.json", payload),
                users["admin"].id,
            )
    valid_site = _write_json(tmp_path, "valid-site.json", base)
    app_container.uat_release.record_readiness_evidence(
        candidate.id, "SITE_APPROVAL", valid_site, users["admin"].id
    )
    with pytest.raises(UatReleaseError, match="sudah tersedia"):
        app_container.uat_release.record_readiness_evidence(
            candidate.id, "SITE_APPROVAL", valid_site, users["admin"].id
        )
    assert len(app_container.uat_release.readiness_evidence(candidate.id, users["decision"].id)) == 1
    with pytest.raises(UatReleaseError, match="CLINICAL atau TECHNICAL"):
        app_container.uat_release.attest_candidate(candidate.id, "LEGAL", users["decision"].id)
    with pytest.raises(UatReleaseError, match="Tujuan kit"):
        app_container.uat_release.export_uat_kit(
            candidate.id, tmp_path / "kit.txt", users["decision"].id
        )
    kit_path = tmp_path / "draft-kit.zip"
    app_container.uat_release.export_uat_kit(candidate.id, kit_path, users["decision"].id)
    with pytest.raises(UatReleaseError, match="sudah ada"):
        app_container.uat_release.export_uat_kit(candidate.id, kit_path, users["decision"].id)
    revoked = app_container.uat_release.revoke_candidate(
        candidate.id, "Dossier fixture dicabut sebelum UAT dilaksanakan", users["admin"].id
    )
    assert revoked.status == "REVOKED"
    with pytest.raises(UatReleaseError, match="tidak aktif"):
        app_container.uat_release.export_uat_kit(
            candidate.id, tmp_path / "revoked-kit.zip", users["decision"].id
        )
    with pytest.raises(UatReleaseError, match="terminal"):
        app_container.uat_release.revoke_candidate(
            candidate.id, "Dossier fixture sudah dicabut sebelumnya", users["admin"].id
        )


@pytest.mark.integration
def test_uat_execution_negative_matrix_and_reject_terminal(app_container, tmp_path):
    users, candidate, checksum = _prepared_candidate(app_container, tmp_path)
    with pytest.raises(UatReleaseError, match="1-168"):
        app_container.uat_release.start_execution(
            candidate.id, users["execution_creator"].id, duration_hours=0
        )
    execution = app_container.uat_release.start_execution(
        candidate.id, users["execution_creator"].id
    )
    with pytest.raises(UatReleaseError, match="sudah memiliki"):
        app_container.uat_release.start_execution(
            candidate.id, users["decision"].id
        )
    with pytest.raises(UatReleaseError, match="tidak ditemukan"):
        app_container.uat_release.results("missing", users["decision"].id)
    base = _result_payload(
        candidate, execution, "CLINICAL_DDI_CRITICAL", "CLINICAL", checksum
    )
    result_cases = (
        ({**base, "scenario_code": "UNKNOWN"}, "Scenario UAT"),
        ({**base, "patient_name": "REJECT"}, "identitas pasien"),
        ({**base, "candidate_id": "wrong"}, "tidak terikat"),
        ({**base, "status": "UNKNOWN"}, "Status UAT"),
        ({**base, "result_summary": "short"}, "10-500"),
        ({**base, "observed_at": (utc_now() - timedelta(days=1)).isoformat()}, "execution window"),
    )
    for index, (payload, message) in enumerate(result_cases):
        with pytest.raises(UatReleaseError, match=message):
            app_container.uat_release.record_result(
                execution.id, _write_json(tmp_path, f"bad-result-{index}.json", payload),
                users["clinical_tester"].id,
            )
    with pytest.raises(UatReleasePermissionError):
        app_container.uat_release.record_result(
            execution.id, _write_json(tmp_path, "wrong-role.json", base),
            users["technical_tester"].id,
        )
    app_container.uat_release.record_result(
        execution.id, _write_json(tmp_path, "one-valid-result.json", base),
        users["clinical_tester"].id,
    )
    assert len(app_container.uat_release.results(execution.id, users["decision"].id)) == 1
    with pytest.raises(UatReleaseError, match="Severity"):
        app_container.uat_release.raise_issue(
            execution.id, "INFO", "Issue fixture dengan severity salah", users["clinical_tester"].id
        )
    with pytest.raises(UatReleaseError, match="10-300"):
        app_container.uat_release.raise_issue(
            execution.id, "WARNING", "short", users["clinical_tester"].id
        )
    with pytest.raises(UatReleaseError, match="OPEN tidak ditemukan"):
        app_container.uat_release.resolve_issue(
            "missing", "Remediasi fixture dengan panjang memadai", users["technical_tester"].id
        )
    assert app_container.uat_release.issues(execution.id, users["decision"].id) == ()
    with pytest.raises(UatReleaseError, match="Jenis sign-off"):
        app_container.uat_release.sign_execution(execution.id, "LEGAL", users["decision"].id)
    with pytest.raises(UatReleaseError, match="Scenario belum lengkap"):
        app_container.uat_release.sign_execution(
            execution.id, "CLINICAL", users["clinical_signer"].id
        )
    with pytest.raises(UatReleaseError, match="Keputusan"):
        app_container.uat_release.decide_execution(
            execution.id, "HOLD", "Keputusan fixture tidak dikenal sistem", users["decision"].id
        )
    with pytest.raises(UatReleaseError, match="Acceptance ditolak"):
        app_container.uat_release.decide_execution(
            execution.id, "ACCEPT", "Acceptance fixture belum memiliki seluruh bukti", users["decision"].id
        )
    rejected = app_container.uat_release.decide_execution(
        execution.id, "REJECT", "UAT fixture ditolak karena evidence belum lengkap", users["decision"].id
    )
    assert rejected.status == "REJECTED"
    with pytest.raises(UatReleaseError, match="bukan OPEN"):
        app_container.uat_release.record_result(
            execution.id, _write_json(tmp_path, "after-reject.json", base),
            users["clinical_tester"].id,
        )
    with pytest.raises(UatReleaseError, match="acceptance aktif"):
        app_container.uat_release.revoke_acceptance(
            execution.id, "Tidak ada acceptance aktif untuk dicabut", users["decision"].id
        )
    with pytest.raises(UatReleaseError, match="Tujuan receipt"):
        app_container.uat_release.export_acceptance_receipt(
            execution.id, tmp_path / "receipt.txt", users["decision"].id
        )
    with pytest.raises(UatReleaseError, match="acceptance aktif"):
        app_container.uat_release.export_acceptance_receipt(
            execution.id, tmp_path / "blocked-receipt.json", users["decision"].id
        )


@pytest.mark.integration
def test_uat_expiry_and_ledger_tamper_close_all_gates(app_container, tmp_path, monkeypatch):
    users, candidate, _checksum = _prepared_candidate(app_container, tmp_path)
    future = app_container.uat_release._as_utc(candidate.expires_at) + timedelta(minutes=1)
    monkeypatch.setattr("emss.services.uat_release.utc_now", lambda: future)
    expired = app_container.uat_release.evaluate(candidate.id)
    assert "kedaluwarsa" in "; ".join(expired.blockers)
    with pytest.raises(UatReleaseError, match="kedaluwarsa"):
        app_container.uat_release.start_execution(candidate.id, users["execution_creator"].id)
    monkeypatch.undo()
    with app_container.database.session() as session:
        session.execute(text("DROP TRIGGER trg_uat_candidate_ledger_no_update"))
        session.execute(text("UPDATE uat_candidate_ledger SET payload_json='{}' WHERE id=1"))
        session.commit()
    tampered = app_container.uat_release.evaluate(candidate.id)
    assert not tampered.candidate_ledger_valid
    with pytest.raises(UatReleaseError, match="ledger tidak valid"):
        app_container.uat_release.start_execution(candidate.id, users["execution_creator"].id)


@pytest.mark.integration
def test_uat_migrations_rollback_preserve_legacy_and_reupgrade(app_container, tmp_path):
    users, candidate, _checksum = _prepared_candidate(app_container, tmp_path)
    command.downgrade(app_container.database._alembic_config(), "0024_uat_release_candidate_dossier")
    assert app_container.database.current_revision() == "0024_uat_release_candidate_dossier"
    tables = inspect(app_container.database.engine).get_table_names()
    assert "uat_execution_session" not in tables
    with app_container.database.session() as session:
        assert session.execute(
            text("SELECT count(*) FROM uat_release_candidate WHERE id=:id"), {"id": candidate.id}
        ).scalar_one() == 1
    command.downgrade(app_container.database._alembic_config(), "0023_verified_evidence_ceremony")
    assert "uat_release_candidate" not in inspect(app_container.database.engine).get_table_names()
    with app_container.database.session() as session:
        assert session.execute(
            text("SELECT count(*) FROM app_user WHERE id=:id"), {"id": users["admin"].id}
        ).scalar_one() == 1
    app_container.database.migrate()
    assert app_container.database.current_revision() == HEAD
    assert "uat_execution_session" in inspect(app_container.database.engine).get_table_names()


