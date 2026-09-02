from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class CleanHostCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DataPreservationFacts:
    database_present: bool
    config_present: bool
    backup_files: int


@dataclass(frozen=True)
class CleanHostEvidenceResult:
    status: str
    phase: str
    application_version: str | None
    schema_revision: str | None
    installer_checksum_sha256: str | None
    captured_at: str
    windows_64bit: bool
    data: DataPreservationFacts
    checks: tuple[CleanHostCheck, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["format"] = "EMSS_CLEAN_HOST_EVIDENCE_V1"
        return payload


HealthRunner = Callable[[Path, Path, Path], tuple[int, dict[str, object]]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(path: Path | str, maximum: int) -> Path:
    source = Path(path)
    if source.is_symlink():
        raise ValueError("SYMLINK_REJECTED")
    candidate = source.resolve()
    if not candidate.is_file():
        raise ValueError("FILE_NOT_FOUND")
    if not 0 < candidate.stat().st_size <= maximum:
        raise ValueError("FILE_SIZE_INVALID")
    return candidate


def _release_binding(
    report_path: Path | str, installer_path: Path | str
) -> tuple[str, str, str]:
    report = _safe_file(Path(report_path), 25 * 1024 * 1024)
    installer = _safe_file(Path(installer_path), 2 * 1024 * 1024 * 1024)
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("RELEASE_REPORT_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("RELEASE_REPORT_INVALID")
    if (
        payload.get("format") != "EMSS_RELEASE_QUALIFICATION_V1"
        or payload.get("status") != "QUALIFIED"
    ):
        raise ValueError("RELEASE_NOT_QUALIFIED")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(check, dict) or check.get("status") != "PASS"
        for check in checks
    ):
        raise ValueError("RELEASE_CHECK_FAILED")
    artifacts = payload.get("artifacts")
    matches = (
        [
            item
            for item in artifacts
            if isinstance(item, dict)
            and item.get("path") == f"installer/{installer.name}"
        ]
        if isinstance(artifacts, list)
        else []
    )
    checksum = _sha256(installer)
    if len(matches) != 1 or matches[0].get("checksum_sha256") != checksum:
        raise ValueError("INSTALLER_CHECKSUM_MISMATCH")
    version = payload.get("application_version")
    schema = payload.get("schema_revision")
    if not isinstance(version, str) or not isinstance(schema, str):
        raise ValueError("RELEASE_BINDING_INVALID")
    return version, schema, checksum


def _data_facts(data_dir: Path) -> DataPreservationFacts:
    database_dir = data_dir / "Database"
    backup_dir = data_dir / "Backups"
    return DataPreservationFacts(
        database_present=any(database_dir.glob("*.db"))
        if database_dir.is_dir()
        else False,
        config_present=(data_dir / "config.toml").is_file(),
        backup_files=sum(1 for path in backup_dir.glob("*.db") if path.is_file())
        if backup_dir.is_dir()
        else 0,
    )


def _run_health(
    executable: Path, config: Path, output: Path
) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(
        [
            str(executable),
            "--config",
            str(config),
            "health",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if not output.is_file() or output.is_symlink() or output.stat().st_size > 64 * 1024:
        return completed.returncode, {}
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    return completed.returncode, payload if isinstance(payload, dict) else {}


def _read_baseline(path: Path | str | None) -> dict[str, object] | None:
    if path is None:
        return None
    baseline = _safe_file(Path(path), 1024 * 1024)
    try:
        payload = json.loads(baseline.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("BASELINE_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "EMSS_CLEAN_HOST_EVIDENCE_V1"
        or payload.get("status") != "PASS"
        or payload.get("phase") not in {"INSTALL", "UPGRADE"}
    ):
        raise ValueError("BASELINE_INVALID")
    return payload


def collect_clean_host_evidence(
    phase: str,
    release_report_path: Path | str,
    installer_path: Path | str,
    install_dir: Path | str,
    data_dir: Path | str,
    *,
    baseline_path: Path | str | None = None,
    health_runner: HealthRunner | None = None,
) -> CleanHostEvidenceResult:
    phase = phase.strip().upper()
    if phase not in {"INSTALL", "UPGRADE", "UNINSTALL"}:
        raise ValueError("PHASE_INVALID")
    checks: list[CleanHostCheck] = []
    version: str | None = None
    schema: str | None = None
    installer_checksum: str | None = None
    try:
        version, schema, installer_checksum = _release_binding(
            release_report_path, installer_path
        )
        checks.append(CleanHostCheck("RELEASE_BINDING", True, "QUALIFIED"))
    except ValueError as exc:
        checks.append(CleanHostCheck("RELEASE_BINDING", False, str(exc)))

    windows_64bit = os.name == "nt" and struct.calcsize("P") * 8 == 64
    checks.append(
        CleanHostCheck(
            "WINDOWS_64BIT",
            windows_64bit,
            "64-BIT" if windows_64bit else "WINDOWS_64_BIT_REQUIRED",
        )
    )
    install_root = Path(install_dir).resolve()
    executable = install_root / "E-MAS Farmasi.exe"
    data_root = Path(data_dir).resolve()
    config = data_root / "config.toml"
    expected_binary = phase != "UNINSTALL"
    binary_state_ok = executable.is_file() == expected_binary
    checks.append(
        CleanHostCheck(
            "INSTALLED_BINARY_STATE",
            binary_state_ok,
            "PRESENT" if executable.is_file() else "ABSENT",
        )
    )

    baseline: dict[str, object] | None = None
    if phase in {"UPGRADE", "UNINSTALL"}:
        try:
            if baseline_path is None:
                raise ValueError("BASELINE_REQUIRED")
            baseline = _read_baseline(baseline_path)
            checks.append(CleanHostCheck("BASELINE_CHAIN", True, "VALID"))
        except ValueError as exc:
            checks.append(CleanHostCheck("BASELINE_CHAIN", False, str(exc)))

    health_payload: dict[str, object] = {}
    if expected_binary and executable.is_file() and config.is_file():
        runner = health_runner or _run_health
        with tempfile.TemporaryDirectory(prefix="emss-clean-host-") as temp:
            returncode, health_payload = runner(
                executable, config, Path(temp) / "health.json"
            )
        health_ok = (
            returncode == 0
            and health_payload.get("state") == "READY"
            and health_payload.get("schema_revision") == schema
            and health_payload.get("audit_chain_valid") is True
        )
        checks.append(
            CleanHostCheck(
                "INSTALLED_HEALTH",
                health_ok,
                str(health_payload.get("state") or "NO_REPORT"),
            )
        )
    elif expected_binary:
        checks.append(CleanHostCheck("INSTALLED_HEALTH", False, "NOT_RUN"))

    facts = _data_facts(data_root)
    preservation_ok = facts.database_present and facts.config_present
    if phase == "UPGRADE":
        preservation_ok = preservation_ok and facts.backup_files >= 1
    if baseline is not None:
        baseline_data = baseline.get("data")
        if not isinstance(baseline_data, dict):
            preservation_ok = False
        else:
            preservation_ok = (
                preservation_ok
                and bool(baseline_data.get("database_present"))
                and bool(baseline_data.get("config_present"))
                and facts.backup_files >= int(baseline_data.get("backup_files", 0))
            )
    checks.append(
        CleanHostCheck(
            "PROGRAMDATA_PRESERVATION",
            preservation_ok,
            f"DB={facts.database_present};CONFIG={facts.config_present};BACKUPS={facts.backup_files}",
        )
    )
    passed = bool(checks) and all(check.passed for check in checks)
    return CleanHostEvidenceResult(
        status="PASS" if passed else "FAIL",
        phase=phase,
        application_version=version,
        schema_revision=schema,
        installer_checksum_sha256=installer_checksum,
        captured_at=datetime.now(UTC).isoformat(),
        windows_64bit=windows_64bit,
        data=facts,
        checks=tuple(checks),
    )


def write_clean_host_report(
    result: CleanHostEvidenceResult, output: Path | str
) -> Path:
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emss-clean-host-evidence")
    parser.add_argument("phase", choices=("INSTALL", "UPGRADE", "UNINSTALL"))
    parser.add_argument("--release-report", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = collect_clean_host_evidence(
            args.phase,
            args.release_report,
            args.installer,
            args.install_dir,
            args.data_dir,
            baseline_path=args.baseline,
        )
    except ValueError as exc:
        print(f"Clean-host evidence gagal: {exc}", file=sys.stderr)
        return 2
    output = write_clean_host_report(result, args.output)
    print(f"{result.status}: {output}")
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
