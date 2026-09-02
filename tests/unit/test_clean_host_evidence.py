from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from emss.release.clean_host import (
    CleanHostCheck,
    CleanHostEvidenceResult,
    DataPreservationFacts,
    collect_clean_host_evidence,
    main,
    write_clean_host_report,
)


def _release(tmp_path: Path):
    installer = tmp_path / "E-MAS-Farmasi-Setup-0.25.0-x64.exe"
    installer.write_bytes(b"installer")
    checksum = hashlib.sha256(installer.read_bytes()).hexdigest()
    report = tmp_path / "release.json"
    report.write_text(
        json.dumps(
            {
                "format": "EMSS_RELEASE_QUALIFICATION_V1",
                "status": "QUALIFIED",
                "application_version": "0.25.0",
                "schema_revision": "0029_kfa_identity",
                "checks": [{"name": "ALL", "status": "PASS"}],
                "artifacts": [
                    {
                        "path": f"installer/{installer.name}",
                        "checksum_sha256": checksum,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return report, installer


def _layout(tmp_path: Path):
    install = tmp_path / "Program Files/eMSS"
    install.mkdir(parents=True)
    (install / "E-MAS Farmasi.exe").write_bytes(b"binary")
    data = tmp_path / "ProgramData/eMSSFarmasi"
    (data / "Database").mkdir(parents=True)
    (data / "Backups").mkdir()
    (data / "config.toml").write_text("environment='test'", encoding="utf-8")
    (data / "Database/emss.db").write_bytes(b"database")
    return install, data


def _ready(_executable, _config, _output):
    return 0, {
        "state": "READY",
        "schema_revision": "0029_kfa_identity",
        "audit_chain_valid": True,
    }


def test_install_upgrade_and_uninstall_evidence_chain(tmp_path, monkeypatch):
    monkeypatch.setattr("emss.release.clean_host.os.name", "nt")
    monkeypatch.setattr("emss.release.clean_host.struct.calcsize", lambda _fmt: 8)
    report, installer = _release(tmp_path)
    install, data = _layout(tmp_path)

    installed = collect_clean_host_evidence(
        "INSTALL",
        report,
        installer,
        install,
        data,
        health_runner=_ready,
    )
    assert installed.status == "PASS"
    baseline = write_clean_host_report(installed, tmp_path / "install.json")

    (data / "Backups/pre-upgrade.db").write_bytes(b"backup")
    upgraded = collect_clean_host_evidence(
        "UPGRADE",
        report,
        installer,
        install,
        data,
        baseline_path=baseline,
        health_runner=_ready,
    )
    assert upgraded.status == "PASS"
    upgrade_report = write_clean_host_report(upgraded, tmp_path / "upgrade.json")

    (install / "E-MAS Farmasi.exe").unlink()
    uninstalled = collect_clean_host_evidence(
        "UNINSTALL",
        report,
        installer,
        install,
        data,
        baseline_path=upgrade_report,
    )
    assert uninstalled.status == "PASS"
    assert uninstalled.data.database_present
    assert uninstalled.data.config_present
    assert uninstalled.data.backup_files == 1


def test_collector_fails_closed_for_health_data_and_release_mismatch(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("emss.release.clean_host.os.name", "nt")
    monkeypatch.setattr("emss.release.clean_host.struct.calcsize", lambda _fmt: 8)
    report, installer = _release(tmp_path)
    install, data = _layout(tmp_path)

    bad_health = collect_clean_host_evidence(
        "INSTALL",
        report,
        installer,
        install,
        data,
        health_runner=lambda *_args: (
            0,
            {
                "state": "READY",
                "schema_revision": "wrong",
                "audit_chain_valid": True,
            },
        ),
    )
    assert bad_health.status == "FAIL"
    assert not next(
        check for check in bad_health.checks if check.name == "INSTALLED_HEALTH"
    ).passed

    (data / "Database/emss.db").unlink()
    missing_data = collect_clean_host_evidence(
        "INSTALL",
        report,
        installer,
        install,
        data,
        health_runner=_ready,
    )
    assert missing_data.status == "FAIL"

    installer.write_bytes(b"tampered")
    tampered = collect_clean_host_evidence(
        "INSTALL",
        report,
        installer,
        install,
        data,
        health_runner=_ready,
    )
    assert tampered.status == "FAIL"
    release_check = next(
        check for check in tampered.checks if check.name == "RELEASE_BINDING"
    )
    assert release_check.detail == "INSTALLER_CHECKSUM_MISMATCH"


def test_upgrade_and_uninstall_require_valid_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("emss.release.clean_host.os.name", "nt")
    monkeypatch.setattr("emss.release.clean_host.struct.calcsize", lambda _fmt: 8)
    report, installer = _release(tmp_path)
    install, data = _layout(tmp_path)

    for phase in ("UPGRADE", "UNINSTALL"):
        if phase == "UNINSTALL":
            (install / "E-MAS Farmasi.exe").unlink(missing_ok=True)
        result = collect_clean_host_evidence(
            phase,
            report,
            installer,
            install,
            data,
            baseline_path=None,
            health_runner=_ready,
        )
        assert result.status == "FAIL"
        baseline = next(
            check for check in result.checks if check.name == "BASELINE_CHAIN"
        )
        assert not baseline.passed


def test_invalid_phase_raises(tmp_path):
    report, installer = _release(tmp_path)
    install, data = _layout(tmp_path)
    with pytest.raises(ValueError, match="PHASE_INVALID"):
        collect_clean_host_evidence(
            "FORMAT",
            report,
            installer,
            install,
            data,
        )


def test_clean_host_cli_writes_report_and_fails_safely(tmp_path, monkeypatch):
    result = CleanHostEvidenceResult(
        status="PASS",
        phase="INSTALL",
        application_version="0.25.0",
        schema_revision="0029_kfa_identity",
        installer_checksum_sha256="a" * 64,
        captured_at="2026-08-11T00:00:00+00:00",
        windows_64bit=True,
        data=DataPreservationFacts(True, True, 0),
        checks=(CleanHostCheck("ALL", True, "PASS"),),
    )
    monkeypatch.setattr(
        "emss.release.clean_host.collect_clean_host_evidence",
        lambda *_args, **_kwargs: result,
    )
    output = tmp_path / "evidence.json"
    arguments = [
        "INSTALL",
        "--release-report",
        str(tmp_path / "release.json"),
        "--installer",
        str(tmp_path / "installer.exe"),
        "--install-dir",
        str(tmp_path / "install"),
        "--data-dir",
        str(tmp_path / "data"),
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"

    monkeypatch.setattr(
        "emss.release.clean_host.collect_clean_host_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("RELEASE_NOT_QUALIFIED")
        ),
    )
    assert main(arguments) == 2


