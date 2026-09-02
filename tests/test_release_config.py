from pathlib import Path
import tomllib

from emss import __version__


PROJECT = Path(__file__).resolve().parents[1]


def test_release_version_is_aligned_across_package_installer_and_changelog():
    metadata = tomllib.loads(
        (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
    )
    version = metadata["project"]["version"]
    installer = (PROJECT / "installer" / "emss-farmasi.iss").read_text(
        encoding="utf-8"
    )
    changelog = (PROJECT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f'#define MyAppVersion "{version}"' in installer
    assert f"## {version} - " in changelog
    assert __version__ == version


def test_production_config_contains_no_password_and_enables_backup():
    config = (PROJECT / "installer" / "config.production.toml").read_text(
        encoding="utf-8"
    )
    assert "backup_daily_enabled = true" in config
    assert "backup_retention_days = 30" in config
    assert "khanza_adapter = \"disabled\"" in config
    assert "khanza_poll_interval_seconds = 1" in config
    assert "khanza_password =" not in config.lower()
    assert "EMSS_KHANZA_PASSWORD" in config


def test_installer_preserves_program_data_on_upgrade_and_uninstall():
    installer = (PROJECT / "installer" / "emss-farmasi.iss").read_text(
        encoding="utf-8"
    )
    assert "onlyifdoesntexist" in installer
    assert "uninsneveruninstall" in installer
    assert "{commonappdata}\\eMSSFarmasi\\Database" in installer
    assert "{commonappdata}\\eMSSFarmasi\\Backups" in installer
    assert "deleteafterinstall" not in installer.lower()


def test_pyinstaller_is_onedir_and_packages_migrations():
    spec = (PROJECT / "emss-farmasi.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert 'str(project / "migrations")' in spec
    assert 'str(project / "seed")' in spec
    assert 'prefix="seed"' in spec
    assert 'exclude_binaries=True' in spec
    assert 'excludes=["__pycache__", "*.pyc"]' in spec
    assert '"ddi_import_template.xlsx.inspect.ndjson"' in spec
    assert 'not name.startswith("alembic.testing")' in spec
    assert '["logging.config"]' in spec


def test_installer_copies_complete_dist_including_qualified_seed_bundle():
    installer = (PROJECT / "installer" / "emss-farmasi.iss").read_text(
        encoding="utf-8"
    )
    assert 'Source: "{#AppDistDir}\\*"' in installer
    assert "recursesubdirs" in installer
    assert "createallsubdirs" in installer
    qualification = (PROJECT / "src/emss/release/qualification.py").read_text(
        encoding="utf-8"
    )
    assert '"seed/ddi-khanza-v1.0.0.json.gz"' in qualification
    assert '"seed/ddi-khanza-v1.0.0.manifest.json"' in qualification
    assert '"bundle-smoke"' in qualification


def test_release_scripts_fail_closed_through_machine_readable_qualification():
    release_script = (PROJECT / "scripts" / "build_release.bat").read_text(
        encoding="utf-8"
    )
    installer_script = (
        PROJECT / "scripts" / "build_installer.bat"
    ).read_text(encoding="utf-8")

    assert "emss.release.qualification preflight" in release_script
    assert "binary-qualification.json" in release_script
    assert "data-lifecycle-drill.json" in release_script
    assert "emss.release.drill" in release_script
    assert "emss.release.qualification qualify" in release_script
    assert "installer-preflight.json" in installer_script
    assert "--require-installer" in installer_script
    assert "release-qualification.json" in installer_script
    assert "app-version.txt" in installer_script
    assert "set /p APP_VERSION" in installer_script
    assert "EMSS_REQUIRE_SIGNATURE" in installer_script
    assert "--require-signature" in installer_script
    assert ".venv-build313" in release_script
    assert "EMSS_BUILD_PYTHON" in release_script
    assert "toolchain\\Inno Setup 6\\ISCC.exe" in installer_script
    test_script = (PROJECT / "scripts" / "run_tests.bat").read_text(
        encoding="utf-8"
    )
    assert "EMSS_BUILD_PYTHON" in test_script
    assert ".venv-build313" in test_script
    assert "if errorlevel 1" in release_script
    assert "if errorlevel 1" in installer_script
    clean_host_script = (
        PROJECT / "scripts" / "collect_clean_host_evidence.bat"
    ).read_text(encoding="utf-8")
    assert "emss.release.clean_host" in clean_host_script
    assert "EMSS_BUILD_PYTHON" in clean_host_script
