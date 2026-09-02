from __future__ import annotations

import hashlib
import json
import os
import pytest
import shutil
from pathlib import Path

from emss.release.qualification import (
    CheckResult,
    CheckStatus,
    ReleaseQualifier,
    RuntimeFacts,
    main,
)


def _project(tmp_path: Path, version: str = "0.25.0") -> Path:
    project = tmp_path / "project"
    (project / "src/emss").mkdir(parents=True)
    (project / "installer").mkdir()
    (project / "migrations/versions").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "emss-farmasi"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (project / "src/emss/__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (project / "installer/emss-farmasi.iss").write_text(
        f'#define MyAppVersion "{version}"\n', encoding="utf-8"
    )
    (project / "CHANGELOG.md").write_text(
        f"## {version} - Qualified Release\n", encoding="utf-8"
    )
    (project / "migrations/versions/0001.py").write_text(
        'revision = "0001"\ndown_revision = None\n', encoding="utf-8"
    )
    shutil.copytree(Path(__file__).resolve().parents[2] / "seed", project / "seed")
    return project


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist" / "E-MAS Farmasi"
    (dist / "migrations/versions").mkdir(parents=True)
    (dist / "templates").mkdir()
    (dist / "seed").mkdir()
    (dist / "emss/assets").mkdir(parents=True)
    (dist / "E-MAS Farmasi.exe").write_bytes(b"binary")
    (dist / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (dist / "migrations/versions/0001.py").write_text(
        'revision = "0001"\n', encoding="utf-8"
    )
    (dist / "templates/template.xlsx").write_bytes(b"xlsx")
    source_seed = Path(__file__).resolve().parents[2] / "seed"
    for source in source_seed.iterdir():
        shutil.copy2(source, dist / "seed" / source.name)
    (dist / "emss/assets/emss.ico").write_bytes(b"icon")
    return dist


def _runtime(
    version: str = "3.13.7",
    bits: int = 64,
    pyinstaller: bool = True,
    inno: str | None = "C:/Inno/ISCC.exe",
) -> RuntimeFacts:
    return RuntimeFacts(version, bits, pyinstaller, inno)


def _smoke(_executable: Path, schema: str) -> CheckResult:
    assert schema == "0001"
    return CheckResult("BINARY_SMOKE", CheckStatus.PASS, "READY")


def test_preflight_is_qualified_and_report_is_atomic(tmp_path):
    project = _project(tmp_path)
    qualifier = ReleaseQualifier(project, _runtime())

    result = qualifier.preflight(require_inno=True)

    assert result.status == "QUALIFIED"
    assert result.application_version == "0.25.0"
    assert result.schema_revision == "0001"
    assert all(check.status == CheckStatus.PASS for check in result.checks)
    output = qualifier.write_report(result, tmp_path / "reports/preflight.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["format"] == "EMSS_RELEASE_QUALIFICATION_V1"
    assert payload["status"] == "QUALIFIED"
    assert not output.with_name(f".{output.name}.tmp").exists()


def test_preflight_is_blocked_when_build_toolchain_is_wrong(tmp_path):
    qualifier = ReleaseQualifier(
        _project(tmp_path), _runtime("3.12.13", 32, False, None)
    )

    result = qualifier.preflight(require_inno=True)

    assert result.status == "BLOCKED"
    blocked = {
        check.name
        for check in result.checks
        if check.status == CheckStatus.BLOCKED
    }
    assert blocked == {
        "PYTHON_VERSION",
        "PYTHON_ARCHITECTURE",
        "PYINSTALLER",
        "INNO_SETUP_6",
    }


def test_preflight_discovers_project_local_inno_setup(tmp_path):
    project = _project(tmp_path)
    portable = project / "toolchain/Inno Setup 6/ISCC.exe"
    portable.parent.mkdir(parents=True)
    portable.write_bytes(b"compiler")
    qualifier = ReleaseQualifier(project, _runtime(inno=None))

    result = qualifier.preflight(require_inno=True)

    assert result.status == "QUALIFIED"
    assert qualifier.runtime.inno_setup_path == str(portable)


def test_qualify_hashes_onedir_and_installer_after_smoke(tmp_path):
    project = _project(tmp_path)
    dist = _dist(tmp_path)
    installer = tmp_path / "E-MAS-Farmasi-Setup-0.25.0-x64.exe"
    installer.write_bytes(b"installer")
    qualifier = ReleaseQualifier(project, _runtime())

    result = qualifier.qualify(
        dist,
        installer,
        require_installer=True,
        smoke_runner=_smoke,
    )

    assert result.status == "QUALIFIED"
    # Include the supplement bundle, manifest, and sanitized provenance.
    assert len(result.artifacts) == 13
    binary = next(
        item for item in result.artifacts if item.path.endswith("E-MAS Farmasi.exe")
    )
    assert binary.checksum_sha256 == hashlib.sha256(b"binary").hexdigest()
    assert any(item.path.startswith("installer/") for item in result.artifacts)
    assert {check.name for check in result.checks} >= {
        "DIST_CONTENTS",
        "ARTIFACT_MANIFEST",
        "BINARY_SMOKE",
        "INSTALLER_ARTIFACT",
        "AUTHENTICODE_POLICY",
        "BUNDLED_DDI_CONTRACT",
    }


def test_required_authenticode_signature_is_fail_closed(tmp_path):
    project = _project(tmp_path)
    dist = _dist(tmp_path)
    installer = tmp_path / "E-MAS-Farmasi-Setup-0.25.0-x64.exe"
    installer.write_bytes(b"installer")
    qualifier = ReleaseQualifier(project, _runtime())
    checked = []

    def signed(path: Path, label: str) -> CheckResult:
        checked.append((path.name, label))
        return CheckResult(f"AUTHENTICODE_{label}", CheckStatus.PASS, "Valid")

    qualified = qualifier.qualify(
        dist,
        installer,
        require_installer=True,
        require_signature=True,
        smoke_runner=_smoke,
        signature_runner=signed,
    )
    assert qualified.status == "QUALIFIED"
    assert {label for _name, label in checked} == {"BINARY", "INSTALLER"}
    assert all(check.name != "AUTHENTICODE_POLICY" for check in qualified.checks)

    failed = qualifier.qualify(
        dist,
        installer,
        require_installer=True,
        require_signature=True,
        smoke_runner=_smoke,
        signature_runner=lambda _path, label: CheckResult(
            f"AUTHENTICODE_{label}", CheckStatus.FAIL, "NotSigned"
        ),
    )
    assert failed.status == "FAILED"
    assert {
        check.name for check in failed.checks if check.status == CheckStatus.FAIL
    } == {"AUTHENTICODE_BINARY", "AUTHENTICODE_INSTALLER"}


def test_windows_authenticode_runner_reports_valid_and_check_failure(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "signed.exe"
    artifact.write_bytes(b"signed")
    monkeypatch.setattr(
        "emss.release.qualification.shutil.which",
        lambda _name: "powershell.exe",
    )

    def valid_run(command, **kwargs):
        assert command[0] == "powershell.exe"
        assert kwargs["env"]["EMSS_SIGNATURE_TARGET"] == str(artifact)
        return type(
            "Completed", (), {"returncode": 0, "stdout": "Valid\n"}
        )()

    monkeypatch.setattr(
        "emss.release.qualification.subprocess.run", valid_run
    )
    valid = ReleaseQualifier._run_signature_check(artifact, "INSTALLER")
    assert valid.status == CheckStatus.PASS
    assert valid.detail == "Valid"

    monkeypatch.setattr(
        "emss.release.qualification.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("failed")),
    )
    failed = ReleaseQualifier._run_signature_check(artifact, "BINARY")
    assert failed.status == CheckStatus.FAIL
    assert failed.detail == "CHECK_FAILED"


def test_qualify_fails_for_missing_or_sensitive_artifacts(tmp_path):
    project = _project(tmp_path)
    qualifier = ReleaseQualifier(project, _runtime())
    missing = qualifier.qualify(
        tmp_path / "missing", require_installer=True, smoke_runner=_smoke
    )
    assert missing.status == "FAILED"
    assert {check.name for check in missing.checks if check.status == CheckStatus.FAIL} == {
        "DIST_DIRECTORY",
        "INSTALLER_ARTIFACT",
    }

    dist = _dist(tmp_path)
    (dist / ".env").write_text("PASSWORD=secret", encoding="utf-8")
    sensitive = qualifier.qualify(dist, smoke_runner=_smoke)
    manifest_check = next(
        check for check in sensitive.checks if check.name == "ARTIFACT_MANIFEST"
    )
    assert sensitive.status == "FAILED"
    assert manifest_check.detail == "SENSITIVE_FILE_REJECTED"
    assert sensitive.artifacts == ()


def test_contract_and_schema_errors_fail_closed(tmp_path):
    project = _project(tmp_path)
    (project / "src/emss/__init__.py").write_text(
        '__version__ = "wrong"\n', encoding="utf-8"
    )
    (project / "migrations/versions/0002.py").write_text(
        'revision = "0002"\ndown_revision = None\n', encoding="utf-8"
    )

    result = ReleaseQualifier(project, _runtime()).preflight()

    assert result.status == "FAILED"
    failed = {
        check.name for check in result.checks if check.status == CheckStatus.FAIL
    }
    assert failed == {"VERSION_CONTRACT", "ALEMBIC_SINGLE_HEAD"}


def test_smoke_failure_and_missing_dist_member_fail_release(tmp_path):
    project = _project(tmp_path)
    dist = _dist(tmp_path)
    (dist / "templates/template.xlsx").unlink()
    (dist / "templates").rmdir()
    qualifier = ReleaseQualifier(project, _runtime())
    result = qualifier.qualify(
        dist,
        smoke_runner=lambda _path, _schema: CheckResult(
            "BINARY_SMOKE", CheckStatus.FAIL, "HEALTH_NOT_READY"
        ),
    )
    assert result.status == "FAILED"
    assert "MISSING:templates" in next(
        check.detail for check in result.checks if check.name == "DIST_CONTENTS"
    )
    assert all(check.name != "BINARY_SMOKE" for check in result.checks)


def test_binary_smoke_parses_ready_health_and_rejects_bad_output(
    tmp_path, monkeypatch
):
    qualifier = ReleaseQualifier(_project(tmp_path), _runtime())
    executable = tmp_path / "app.exe"
    executable.write_bytes(b"fake")
    def ready_run(command, **_kwargs):
        report = Path(command[command.index("--output") + 1])
        payload = {
            "state": "READY",
            "schema_revision": "0001",
            "login_visible": True,
            "platform": "windows" if os.name == "nt" else "offscreen",
        }
        if "bundle-smoke" in command:
            payload.update(
                counts={
                    "ddi_rule": 5432,
                    "drug_master": 414,
                    "drug_component_mapping": 444,
                },
                enabled_ddi=0,
                non_pending_mappings=0,
                h3_active_ddi=379,
                h3_approved_mappings=414,
                h3_held_ddi=175,
                h3_draft_ddi=11,
                ledger_recovered=True,
                local_master_preserved=True,
                clinical_review_preserved=True,
                mapping_correction_preserved=True,
                user_files_preserved=True,
                operational_data_accessed=False,
            )
        report.write_text(json.dumps(payload), encoding="utf-8")
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(
        "emss.release.qualification.subprocess.run", ready_run
    )
    assert qualifier._run_binary_smoke(executable, "0001").status == CheckStatus.PASS

    monkeypatch.setattr(
        "emss.release.qualification.subprocess.run",
        lambda *_args, **_kwargs: type(
            "Completed", (), {"returncode": 1}
        )(),
    )
    failed = qualifier._run_binary_smoke(executable, "0001")
    assert failed.status == CheckStatus.FAIL
    assert failed.detail == "ValueError"


def test_binary_smoke_rejects_failed_bundle_upgrade(tmp_path, monkeypatch):
    qualifier = ReleaseQualifier(_project(tmp_path), _runtime())

    def run(command, **_kwargs):
        report = Path(command[command.index("--output") + 1])
        payload = {"state": "READY", "schema_revision": "0001"}
        code = 0
        if "gui-smoke" in command:
            payload.update(
                login_visible=True,
                platform="windows" if os.name == "nt" else "offscreen",
            )
        elif "bundle-smoke" in command:
            payload = {"state": "ERROR", "ledger_recovered": False}
            code = 1
        report.write_text(json.dumps(payload), encoding="utf-8")
        return type("Completed", (), {"returncode": code})()

    monkeypatch.setattr("emss.release.qualification.subprocess.run", run)
    result = qualifier._run_binary_smoke(tmp_path / "app.exe", "0001")
    assert result.status == CheckStatus.FAIL
    assert result.detail == "SMOKE_NOT_READY"


def test_cli_writes_blocked_preflight_report(tmp_path, monkeypatch):
    project = _project(tmp_path)
    output = tmp_path / "preflight.json"
    monkeypatch.setattr(
        "emss.release.qualification.RuntimeFacts.detect",
        classmethod(lambda cls: _runtime("3.12.13", 64, False, None)),
    )

    exit_code = main(
        [
            "preflight",
            "--project-dir",
            str(project),
            "--output",
            str(output),
            "--require-installer",
        ]
    )

    assert exit_code == 2
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "BLOCKED"


@pytest.mark.parametrize("failure", ["import_error", "missing", "invisible", "wrong_platform", "wrong_schema"])
def test_health_success_cannot_mask_frozen_gui_failure(tmp_path, monkeypatch, failure):
    qualifier = ReleaseQualifier(_project(tmp_path), _runtime())
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        report = Path(command[command.index("--output") + 1])
        payload = {"state": "READY", "schema_revision": "0001"}
        code = 0
        if "gui-smoke" in command:
            payload.update(login_visible=True, platform="windows" if os.name == "nt" else "offscreen")
            if failure == "import_error":
                payload = {"state": "ERROR", "error_type": "ImportError"}
                code = 1
            elif failure == "missing":
                return type("Completed", (), {"returncode": 0})()
            elif failure == "invisible": payload["login_visible"] = False
            elif failure == "wrong_platform": payload["platform"] = "invalid"
            elif failure == "wrong_schema": payload["schema_revision"] = "wrong"
        report.write_text(json.dumps(payload), encoding="utf-8")
        return type("Completed", (), {"returncode": code})()
    monkeypatch.setattr("emss.release.qualification.subprocess.run", run)
    result = qualifier._run_binary_smoke(tmp_path / "app.exe", "0001")
    assert result.status == CheckStatus.FAIL
    assert len(calls) == 2


def test_foreign_icu_rejects_release_before_launch(tmp_path):
    qualifier = ReleaseQualifier(_project(tmp_path), _runtime())
    dist = _dist(tmp_path)
    (dist / "ICUUC.DLL").write_bytes(b"foreign ICU exports")
    def forbidden(*args):
        raise AssertionError("contaminated binary must not run")
    result = qualifier.qualify(dist, smoke_runner=forbidden)
    assert result.status == "FAILED"
    assert next(c for c in result.checks if c.name == "QT_SYSTEM_ICU").status == CheckStatus.FAIL
