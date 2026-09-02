from __future__ import annotations

import json

import pytest

from emss.release.drill import (
    main,
    run_data_lifecycle_drill,
    write_drill_report,
)


@pytest.mark.integration
def test_release_data_lifecycle_drill_passes_and_writes_safe_report(tmp_path):
    result = run_data_lifecycle_drill(tmp_path / "work")

    assert result.status == "PASS"
    assert result.starting_revision == "0020_limited_rollout"
    assert result.final_revision == "0029_kfa_identity"
    assert len(result.backup_checksum_sha256 or "") == 64
    assert {check.name for check in result.checks} == {
        "LEGACY_FIXTURE",
        "BACKUP_VERIFICATION",
        "UPGRADE_TO_HEAD",
        "RESTORE_AND_FORWARD_MIGRATE",
        "ROLLBACK_COMPATIBILITY",
        "REUPGRADE_HEALTH",
    }
    assert all(check.passed for check in result.checks)
    output = write_drill_report(result, tmp_path / "drill/report.json")
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["format"] == "EMSS_DATA_LIFECYCLE_DRILL_V1"
    assert report["status"] == "PASS"
    assert "password" not in output.read_text(encoding="utf-8").casefold()


@pytest.mark.integration
def test_release_data_lifecycle_drill_cli_uses_explicit_workdir(tmp_path):
    output = tmp_path / "cli-report.json"
    assert main(
        [
            "--output",
            str(output),
            "--work-dir",
            str(tmp_path / "cli-work"),
        ]
    ) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"


