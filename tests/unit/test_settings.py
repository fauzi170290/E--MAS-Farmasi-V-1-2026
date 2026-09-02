from __future__ import annotations


def test_rebranding_preserves_legacy_storage_and_config(tmp_path, monkeypatch):
    from emss.config.settings import AppSettings, default_data_dir, load_settings
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path))
    assert default_data_dir() == tmp_path / 'eMSSFarmasi'
    settings = AppSettings(app_name='e-MSS Farmasi — DDI Checker', data_dir=tmp_path/'custom')
    assert settings.app_name == 'E-MAS Farmasi'
    assert settings.database_path == tmp_path/'custom'/'Database'/'emss.db'
    config = tmp_path/'legacy.toml'
    original = 'app_name="e-MSS Farmasi — DDI Checker"\ndata_dir="custom"\ndatabase_filename="legacy.db"\n'
    config.write_text(original, encoding='utf-8')
    loaded = load_settings(config)
    assert loaded.database_path == tmp_path/'custom'/'Database'/'legacy.db'
    assert config.read_text(encoding='utf-8') == original

from pathlib import Path

import pytest
from pydantic import ValidationError

from emss.config.settings import AppEnvironment, AppSettings, load_settings


def test_settings_build_expected_directories(tmp_path):
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=tmp_path / "data",
    )
    settings.ensure_directories()

    assert settings.database_path == tmp_path / "data" / "Database" / "emss.db"
    assert settings.database_dir.is_dir()
    assert settings.backup_dir.is_dir()
    assert settings.export_dir.is_dir()
    assert settings.log_dir.is_dir()
    assert settings.database_url.startswith("sqlite+pysqlite:///")


def test_toml_relative_data_dir_resolves_from_config(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        'environment = "test"\ndata_dir = "runtime-data"\n',
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.data_dir == (tmp_path / "runtime-data").resolve()


@pytest.mark.parametrize(
    "filename",
    ["../emss.db", "folder/emss.db", "emss.sqlite", "emss"],
)
def test_database_filename_rejects_unsafe_value(filename: str, tmp_path):
    with pytest.raises(ValidationError):
        AppSettings(data_dir=tmp_path, database_filename=filename)


def test_safe_summary_does_not_expose_database_url(tmp_path):
    settings = AppSettings(data_dir=Path(tmp_path))

    summary = settings.safe_summary()

    assert "database_url" not in summary
    assert "password" not in str(summary).lower()


def test_khanza_view_identifier_rejects_sql_fragment(tmp_path):
    with pytest.raises(ValidationError):
        AppSettings(
            data_dir=tmp_path,
            khanza_header_view="view_header; DROP TABLE resep",
        )


def test_legacy_local_test_configuration_is_disabled_without_mutating_data(tmp_path):
    config = tmp_path / 'config.toml'
    original = ('data_dir = "existing-data"\ndatabase_filename = "custom.db"\n'
                'khanza_adapter = "mysql_local_test"\nkhanza_local_test_consent = true\n'
                'khanza_local_test_since = "2026-08-28"\n')
    config.write_text(original, encoding='utf-8')
    data = tmp_path / 'existing-data' / 'Database'
    data.mkdir(parents=True)
    sentinel = data / 'custom.db'
    sentinel.write_bytes(b'untouched database marker')

    settings = load_settings(config)

    assert settings.khanza_adapter.value == 'disabled'
    assert settings.database_path == sentinel
    assert sentinel.read_bytes() == b'untouched database marker'
    assert config.read_text(encoding='utf-8') == original


def test_poll_interval_allows_one_second_but_not_busy_loop(tmp_path):
    assert AppSettings(data_dir=tmp_path, khanza_poll_interval_seconds=1).khanza_poll_interval_seconds == 1
    with pytest.raises(ValueError):
        AppSettings(data_dir=tmp_path, khanza_poll_interval_seconds=0)
