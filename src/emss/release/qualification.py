from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class RuntimeFacts:
    python_version: str
    python_bits: int
    pyinstaller_available: bool
    inno_setup_path: str | None

    @classmethod
    def detect(cls) -> RuntimeFacts:
        inno = shutil.which("ISCC.exe") or shutil.which("iscc")
        if inno is None:
            candidates = (
                Path(os.environ.get("ProgramFiles(x86)", ""))
                / "Inno Setup 6"
                / "ISCC.exe",
                Path(os.environ.get("ProgramFiles", ""))
                / "Inno Setup 6"
                / "ISCC.exe",
            )
            inno = next(
                (str(candidate) for candidate in candidates if candidate.is_file()),
                None,
            )
        return cls(
            python_version=(
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}"
            ),
            python_bits=struct.calcsize("P") * 8,
            pyinstaller_available=(
                importlib.util.find_spec("PyInstaller") is not None
            ),
            inno_setup_path=inno,
        )


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True)
class QualificationResult:
    status: str
    application_version: str | None
    schema_revision: str | None
    generated_at: str
    runtime: RuntimeFacts
    checks: tuple[CheckResult, ...]
    artifacts: tuple[ArtifactFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": "EMSS_RELEASE_QUALIFICATION_V1",
            "status": self.status,
            "application_version": self.application_version,
            "schema_revision": self.schema_revision,
            "generated_at": self.generated_at,
            "runtime": asdict(self.runtime),
            "checks": [asdict(check) for check in self.checks],
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
        }


SmokeRunner = Callable[[Path, str], CheckResult]
SignatureRunner = Callable[[Path, str], CheckResult]


class ReleaseQualifier:
    REQUIRED_DIST_PATHS = (
        "E-MAS Farmasi.exe",
        "alembic.ini",
        "migrations/versions",
        "templates",
        "seed/ddi-khanza-v1.0.0.json.gz",
        "seed/ddi-khanza-v1.0.0.manifest.json",
        "seed/mapping-khanza-20260831.json.gz",
        "seed/mapping-khanza-20260831.manifest.json",
        "seed/mapping-khanza-20260831.provenance.json",
        "emss/assets",
    )
    SENSITIVE_FILENAMES = frozenset(
        {".env", "id_rsa", "id_ed25519", "secrets.toml"}
    )

    def __init__(
        self, project_dir: Path | str, runtime: RuntimeFacts | None = None
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        detected = runtime or RuntimeFacts.detect()
        portable_inno = self.project_dir / "toolchain/Inno Setup 6/ISCC.exe"
        if detected.inno_setup_path is None and portable_inno.is_file():
            detected = RuntimeFacts(
                python_version=detected.python_version,
                python_bits=detected.python_bits,
                pyinstaller_available=detected.pyinstaller_available,
                inno_setup_path=str(portable_inno),
            )
        self.runtime = detected

    def preflight(self, require_inno: bool = False) -> QualificationResult:
        checks, version, schema = self._base_checks(require_inno)
        return self._result(checks, version, schema, ())

    def qualify(
        self,
        dist_dir: Path | str,
        installer_path: Path | str | None = None,
        *,
        require_installer: bool = False,
        require_signature: bool = False,
        smoke_runner: SmokeRunner | None = None,
        signature_runner: SignatureRunner | None = None,
    ) -> QualificationResult:
        checks, version, schema = self._base_checks(require_installer)
        dist = Path(dist_dir).resolve()
        artifacts: list[ArtifactFile] = []
        if not dist.is_dir():
            checks.append(
                CheckResult("DIST_DIRECTORY", CheckStatus.FAIL, "NOT_FOUND")
            )
        else:
            missing = [
                relative
                for relative in self.REQUIRED_DIST_PATHS
                if not (dist / relative).exists()
            ]
            checks.append(
                CheckResult(
                    "DIST_CONTENTS",
                    CheckStatus.FAIL if missing else CheckStatus.PASS,
                    "MISSING:" + ",".join(missing) if missing else "COMPLETE",
                )
            )
            foreign_icu = sorted(
                str(path.relative_to(dist)) for path in dist.rglob("*")
                if path.is_file() and path.name.lower() == "icuuc.dll"
            )
            checks.append(CheckResult(
                "QT_SYSTEM_ICU", CheckStatus.FAIL if foreign_icu else CheckStatus.PASS,
                "APP_LOCAL_ICU:" + ",".join(foreign_icu) if foreign_icu else "SYSTEM_ICU_ONLY",
            ))
            artifact_check, dist_artifacts = self._collect_artifacts(
                dist, "dist"
            )
            checks.append(artifact_check)
            artifacts.extend(dist_artifacts)
            executable = dist / self.REQUIRED_DIST_PATHS[0]
            if executable.is_file() and not missing and not foreign_icu:
                runner = smoke_runner or self._run_binary_smoke
                checks.append(runner(executable, schema or ""))
                if require_signature:
                    verifier = signature_runner or self._run_signature_check
                    checks.append(verifier(executable, "BINARY"))

        installer = Path(installer_path).resolve() if installer_path else None
        if installer is not None and installer.is_file():
            artifacts.append(self._artifact(installer, f"installer/{installer.name}"))
            checks.append(
                CheckResult("INSTALLER_ARTIFACT", CheckStatus.PASS, "FOUND")
            )
            if require_signature:
                verifier = signature_runner or self._run_signature_check
                checks.append(verifier(installer, "INSTALLER"))
        elif require_installer:
            checks.append(
                CheckResult("INSTALLER_ARTIFACT", CheckStatus.FAIL, "NOT_FOUND")
            )
        if not require_signature:
            checks.append(
                CheckResult(
                    "AUTHENTICODE_POLICY",
                    CheckStatus.PASS,
                    "NOT_REQUIRED_BY_BUILD_POLICY",
                )
            )
        return self._result(checks, version, schema, tuple(artifacts))

    def write_report(
        self, result: QualificationResult, output: Path | str
    ) -> Path:
        target = Path(output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(
            json.dumps(
                result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def _base_checks(
        self, require_inno: bool
    ) -> tuple[list[CheckResult], str | None, str | None]:
        checks: list[CheckResult] = []
        version = self._version_contract(checks)
        schema = self._schema_head(checks)
        self._bundled_ddi_contract(checks)
        self._bundled_mapping_contract(checks)
        python_ok = self.runtime.python_version.startswith("3.13.")
        checks.append(
            CheckResult(
                "PYTHON_VERSION",
                CheckStatus.PASS if python_ok else CheckStatus.BLOCKED,
                self.runtime.python_version,
            )
        )
        checks.append(
            CheckResult(
                "PYTHON_ARCHITECTURE",
                CheckStatus.PASS
                if self.runtime.python_bits == 64
                else CheckStatus.BLOCKED,
                f"{self.runtime.python_bits}-BIT",
            )
        )
        checks.append(
            CheckResult(
                "PYINSTALLER",
                CheckStatus.PASS
                if self.runtime.pyinstaller_available
                else CheckStatus.BLOCKED,
                "AVAILABLE"
                if self.runtime.pyinstaller_available
                else "NOT_AVAILABLE",
            )
        )
        if require_inno:
            checks.append(
                CheckResult(
                    "INNO_SETUP_6",
                    CheckStatus.PASS
                    if self.runtime.inno_setup_path
                    else CheckStatus.BLOCKED,
                    "AVAILABLE"
                    if self.runtime.inno_setup_path
                    else "NOT_AVAILABLE",
                )
            )
        return checks, version, schema

    def _bundled_ddi_contract(self, checks: list[CheckResult]) -> None:
        try:
            from emss.services.bundled_ddi import verify_bundled_ddi_seed

            manifest, _payload = verify_bundled_ddi_seed(
                self.project_dir / "seed"
            )
            detail = (
                f"{manifest['bundle_id']}:{manifest['rule_count']} RULES:"
                f"{manifest['bundle_sha256']}"
            )
            passed = True
        except (OSError, ValueError, KeyError) as exc:
            detail = type(exc).__name__
            passed = False
        checks.append(
            CheckResult(
                "BUNDLED_DDI_CONTRACT",
                CheckStatus.PASS if passed else CheckStatus.FAIL,
                detail,
            )
        )

    def _version_contract(self, checks: list[CheckResult]) -> str | None:
        try:
            metadata = tomllib.loads(
                (self.project_dir / "pyproject.toml").read_text(encoding="utf-8")
            )
            version = str(metadata["project"]["version"])
            package = (self.project_dir / "src/emss/__init__.py").read_text(
                encoding="utf-8"
            )
            installer = (self.project_dir / "installer/emss-farmasi.iss").read_text(
                encoding="utf-8"
            )
            changelog = (self.project_dir / "CHANGELOG.md").read_text(
                encoding="utf-8"
            )
            aligned = (
                f'__version__ = "{version}"' in package
                and f'#define MyAppVersion "{version}"' in installer
                and f"## {version} - " in changelog
            )
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
            version = None
            aligned = False
        checks.append(
            CheckResult(
                "VERSION_CONTRACT",
                CheckStatus.PASS if aligned else CheckStatus.FAIL,
                version or "INVALID",
            )
        )
        return version

    def _bundled_mapping_contract(self, checks):
        try:
            from emss.services.bundled_mapping import _read_bundle
            manifest, _, _ = _read_bundle(self.project_dir / 'seed')
            detail = f"{manifest['drug_count']} source + {manifest['correction_count']} pending corrections: {manifest['bundle_sha256']}"
            status = CheckStatus.PASS
        except (OSError, ValueError, KeyError) as exc:
            detail = type(exc).__name__
            status = CheckStatus.FAIL
        checks.append(CheckResult('BUNDLED_MAPPING_CONTRACT', status, detail))

    def _schema_head(self, checks: list[CheckResult]) -> str | None:
        revisions: set[str] = set()
        referenced: set[str] = set()
        try:
            for path in (self.project_dir / "migrations/versions").glob("*.py"):
                values: dict[str, object] = {}
                for node in ast.parse(path.read_text(encoding="utf-8")).body:
                    if isinstance(node, ast.Assign) and len(node.targets) == 1:
                        target = node.targets[0]
                        if isinstance(target, ast.Name) and target.id in {
                            "revision",
                            "down_revision",
                        }:
                            values[target.id] = ast.literal_eval(node.value)
                revision = values.get("revision")
                down = values.get("down_revision")
                if isinstance(revision, str):
                    revisions.add(revision)
                if isinstance(down, str):
                    referenced.add(down)
            heads = revisions - referenced
        except (OSError, SyntaxError, ValueError):
            heads = set()
        head = next(iter(heads)) if len(heads) == 1 else None
        checks.append(
            CheckResult(
                "ALEMBIC_SINGLE_HEAD",
                CheckStatus.PASS if head else CheckStatus.FAIL,
                head or "INVALID",
            )
        )
        return head

    def _collect_artifacts(
        self, root: Path, prefix: str
    ) -> tuple[CheckResult, list[ArtifactFile]]:
        artifacts: list[ArtifactFile] = []
        try:
            files = sorted(path for path in root.rglob("*") if path.is_file())
            if len(files) > 20_000:
                raise ValueError("TOO_MANY_FILES")
            for path in files:
                if path.is_symlink():
                    raise ValueError("SYMLINK_REJECTED")
                if path.name.casefold() in self.SENSITIVE_FILENAMES or path.suffix.casefold() in {
                    ".key",
                    ".pem",
                    ".pfx",
                }:
                    raise ValueError("SENSITIVE_FILE_REJECTED")
                relative = path.relative_to(root).as_posix()
                artifacts.append(self._artifact(path, f"{prefix}/{relative}"))
        except (OSError, ValueError) as exc:
            return (
                CheckResult("ARTIFACT_MANIFEST", CheckStatus.FAIL, str(exc)),
                [],
            )
        return (
            CheckResult(
                "ARTIFACT_MANIFEST",
                CheckStatus.PASS,
                f"{len(artifacts)} FILES",
            ),
            artifacts,
        )

    @staticmethod
    def _artifact(path: Path, display_path: str) -> ArtifactFile:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return ArtifactFile(display_path, path.stat().st_size, digest.hexdigest())

    def _run_binary_smoke(
        self, executable: Path, expected_schema: str
    ) -> CheckResult:
        try:
            with tempfile.TemporaryDirectory(prefix="emss-release-smoke-") as temp:
                temp_path = Path(temp)
                config = temp_path / "smoke.toml"
                config.write_text(
                    "environment = \"test\"\n"
                    f"data_dir = \"{temp_path.as_posix()}/data\"\n"
                    "khanza_adapter = \"disabled\"\n"
                    "khanza_polling_enabled = false\n"
                    "tray_enabled = false\n"
                    "single_instance = false\n",
                    encoding="utf-8",
                )
                health_report = temp_path / "health.json"
                completed = subprocess.run(
                    [
                        str(executable),
                        "--config",
                        str(config),
                        "health",
                        "--output",
                        str(health_report),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if os.name == "nt"
                        else 0
                    ),
                )
                if not health_report.is_file() or health_report.is_symlink():
                    raise ValueError("HEALTH_REPORT_MISSING")
                if health_report.stat().st_size > 64 * 1024:
                    raise ValueError("HEALTH_REPORT_TOO_LARGE")
                payload = json.loads(health_report.read_text(encoding="utf-8"))
                valid = (
                    completed.returncode == 0
                    and payload.get("state") == "READY"
                    and payload.get("schema_revision") == expected_schema
                )
                if not valid:
                    return CheckResult("BINARY_SMOKE", CheckStatus.FAIL, "HEALTH_NOT_READY")
                gui_report = temp_path / "gui.json"
                gui_completed = subprocess.run(
                    [str(executable), "gui-smoke", "--output", str(gui_report)],
                    capture_output=True, text=True, timeout=120, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    env={**os.environ, "QT_QPA_PLATFORM": "windows" if os.name == "nt" else "offscreen"},
                )
                if not gui_report.is_file() or gui_report.is_symlink() or gui_report.stat().st_size > 65536:
                    raise ValueError("GUI_REPORT_MISSING_OR_INVALID")
                gui = json.loads(gui_report.read_text(encoding="utf-8"))
                valid = (
                    gui_completed.returncode == 0 and gui.get("state") == "READY"
                    and gui.get("login_visible") is True
                    and gui.get("schema_revision") == expected_schema
                    and gui.get("platform") == ("windows" if os.name == "nt" else "offscreen")
                )
                if valid:
                    bundle_report = temp_path / "bundle.json"
                    bundle_completed = subprocess.run(
                        [
                            str(executable),
                            "bundle-smoke",
                            "--output",
                            str(bundle_report),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                        creationflags=(
                            subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                        ),
                    )
                    if (
                        not bundle_report.is_file()
                        or bundle_report.is_symlink()
                        or bundle_report.stat().st_size > 64 * 1024
                    ):
                        raise ValueError("BUNDLE_REPORT_MISSING_OR_INVALID")
                    bundle = json.loads(bundle_report.read_text(encoding="utf-8"))
                    valid = (
                        bundle_completed.returncode == 0
                        and bundle.get("state") == "READY"
                        and bundle.get("schema_revision") == expected_schema
                        and bundle.get("counts")
                        == {
                            "ddi_rule": 5432,
                            "drug_master": 414,
                            "drug_component_mapping": 444,
                        }
                        and bundle.get("enabled_ddi") == 0
                        and bundle.get("non_pending_mappings") == 0
                        and bundle.get("h3_active_ddi") == 379
                        and bundle.get("h3_approved_mappings") == 414
                        and bundle.get("h3_held_ddi") == 175
                        and bundle.get("h3_draft_ddi") == 11
                        and bundle.get("ledger_recovered") is True
                        and bundle.get("local_master_preserved") is True
                        and bundle.get("clinical_review_preserved") is True
                        and bundle.get("mapping_correction_preserved") is True
                        and bundle.get("user_files_preserved") is True
                        and bundle.get("operational_data_accessed") is False
                    )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            return CheckResult(
                "BINARY_SMOKE", CheckStatus.FAIL, type(exc).__name__
            )
        return CheckResult(
            "BINARY_SMOKE",
            CheckStatus.PASS if valid else CheckStatus.FAIL,
            "HEALTH_GUI_AND_UPGRADE_READY" if valid else "SMOKE_NOT_READY",
        )

    @staticmethod
    def _run_signature_check(path: Path, label: str) -> CheckResult:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if os.name != "nt" or powershell is None:
            return CheckResult(
                f"AUTHENTICODE_{label}",
                CheckStatus.BLOCKED,
                "WINDOWS_POWERSHELL_REQUIRED",
            )
        returncode = -1
        try:
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-AuthenticodeSignature -LiteralPath "
                    "$env:EMSS_SIGNATURE_TARGET).Status.ToString()",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env={**os.environ, "EMSS_SIGNATURE_TARGET": str(path)},
            )
            status = completed.stdout.strip()
            returncode = completed.returncode
        except (OSError, subprocess.SubprocessError):
            status = "CHECK_FAILED"
        valid = returncode == 0 and status == "Valid"
        return CheckResult(
            f"AUTHENTICODE_{label}",
            CheckStatus.PASS if valid else CheckStatus.FAIL,
            status or "NO_STATUS",
        )

    def _result(
        self,
        checks: list[CheckResult],
        version: str | None,
        schema: str | None,
        artifacts: tuple[ArtifactFile, ...],
    ) -> QualificationResult:
        statuses = {check.status for check in checks}
        status = (
            "FAILED"
            if CheckStatus.FAIL in statuses
            else "BLOCKED"
            if CheckStatus.BLOCKED in statuses
            else "QUALIFIED"
        )
        return QualificationResult(
            status=status,
            application_version=version,
            schema_revision=schema,
            generated_at=datetime.now(UTC).isoformat(),
            runtime=self.runtime,
            checks=tuple(checks),
            artifacts=artifacts,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emss-release-qualification")
    parser.add_argument("command", choices=("preflight", "qualify"))
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--require-installer", action="store_true")
    parser.add_argument("--require-signature", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    qualifier = ReleaseQualifier(args.project_dir)
    if args.command == "preflight":
        result = qualifier.preflight(args.require_installer)
    else:
        if args.dist_dir is None:
            print("--dist-dir wajib untuk qualify", file=sys.stderr)
            return 2
        result = qualifier.qualify(
            args.dist_dir,
            args.installer,
            require_installer=args.require_installer,
            require_signature=args.require_signature,
        )
    output = qualifier.write_report(result, args.output)
    print(f"{result.status}: {output}")
    return 0 if result.status == "QUALIFIED" else 2 if result.status == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
