from __future__ import annotations

import json
from types import SimpleNamespace

from emss.main import main


def test_health_command_writes_atomic_machine_readable_report(
    tmp_path, monkeypatch
):
    output = tmp_path / "reports" / "health.json"
    closed = []
    result = SimpleNamespace(
        state=SimpleNamespace(value="READY"),
        to_dict=lambda: {
            "state": "READY",
            "schema_revision": "0029_kfa_identity",
        },
    )
    container = SimpleNamespace(
        health=SimpleNamespace(check=lambda: result),
        close=lambda: closed.append(True),
    )
    monkeypatch.setattr("emss.main.load_settings", lambda _path: object())
    monkeypatch.setattr("emss.main.build_application", lambda _settings: container)

    exit_code = main(["health", "--output", str(output)])

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "state": "READY",
        "schema_revision": "0029_kfa_identity",
    }
    assert not output.with_name(f".{output.name}.tmp").exists()
    assert closed == [True]


def test_health_command_records_safe_initialization_failure(
    tmp_path, monkeypatch
):
    output = tmp_path / "health-error.json"
    monkeypatch.setattr("emss.main.load_settings", lambda _path: object())

    def fail_build(_settings):
        raise ModuleNotFoundError(name="alembic.runtime.migration")

    monkeypatch.setattr("emss.main.build_application", fail_build)

    assert main(["health", "--output", str(output)]) == 3
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "state": "ERROR",
        "error_type": "ModuleNotFoundError",
        "missing_module": "alembic.runtime.migration",
    }


def test_gui_smoke_rejects_external_config_before_loading(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError("operational config must not be read")
    monkeypatch.setattr("emss.main.load_settings", forbidden)
    output = tmp_path / "gui.json"
    assert main(["--config", str(tmp_path / "operational.toml"), "gui-smoke", "--output", str(output)]) == 2
    assert json.loads(output.read_text())["error_type"] == "CONFIG_NOT_ALLOWED"


def test_gui_smoke_reports_import_failure_without_error_dialog(tmp_path, monkeypatch):
    def broken(settings):
        assert settings.environment == "test"
        assert settings.khanza_adapter == "disabled"
        assert not settings.khanza_polling_enabled
        raise ImportError("DLL load failed while importing QtCore")
    monkeypatch.setattr("emss.release.gui_smoke.build_application", broken)
    output = tmp_path / "gui.json"
    assert main(["gui-smoke", "--output", str(output)]) == 1
    assert json.loads(output.read_text()) == {"state": "ERROR", "error_type": "ImportError"}


