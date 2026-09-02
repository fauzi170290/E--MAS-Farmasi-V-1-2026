from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from sqlalchemy import select

from emss import __version__
from emss.audit.service import AuditService
from emss.config.settings import AppEnvironment, AppSettings
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser
from emss.health.service import HealthService, HealthState
from emss.security.passwords import PasswordService
from emss.services.backup import BackupService
from emss.services.users import UserService


@dataclass(frozen=True)
class DrillCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DataLifecycleDrillResult:
    status: str
    application_version: str
    generated_at: str
    starting_revision: str
    final_revision: str | None
    backup_checksum_sha256: str | None
    checks: tuple[DrillCheck, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["format"] = "EMSS_DATA_LIFECYCLE_DRILL_V1"
        return payload


def run_data_lifecycle_drill(work_dir: Path | str) -> DataLifecycleDrillResult:
    root = Path(work_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(
        environment=AppEnvironment.TEST,
        data_dir=root / "data",
        log_level="ERROR",
        backup_retention_count=10,
        backup_retention_days=30,
    )
    settings.ensure_directories()
    database = DatabaseManager(settings)
    audit = AuditService()
    checks: list[DrillCheck] = []
    checksum: str | None = None
    final_revision: str | None = None
    starting_revision = "0020_limited_rollout"
    try:
        database.migrate(starting_revision)
        user = UserService(database, PasswordService(), audit).create_first_admin(
            username="qualification.admin",
            display_name="Qualification Admin",
            password="Qualification#Aman2026",
        )
        checks.append(
            DrillCheck(
                "LEGACY_FIXTURE",
                database.current_revision() == starting_revision,
                starting_revision,
            )
        )

        backup_service = BackupService(settings, database, audit)
        backup = backup_service.create_backup("RELEASE_DRILL", user.id)
        checksum = backup.checksum_sha256
        verified = backup_service.verify_backup(backup.database_path, user.id)
        checks.append(
            DrillCheck(
                "BACKUP_VERIFICATION",
                verified.checksum_sha256 == checksum and verified.integrity_ok,
                verified.schema_revision,
            )
        )

        database.migrate()
        upgraded_revision = database.current_revision()
        checks.append(
            DrillCheck(
                "UPGRADE_TO_HEAD",
                upgraded_revision == "0029_kfa_identity",
                upgraded_revision or "NONE",
            )
        )

        restored = backup_service.restore_backup(backup.database_path, user.id)
        with database.session() as session:
            preserved_after_restore = session.scalar(
                select(AppUser.username).where(AppUser.id == user.id)
            )
        checks.append(
            DrillCheck(
                "RESTORE_AND_FORWARD_MIGRATE",
                restored.schema_revision == "0029_kfa_identity"
                and preserved_after_restore == "qualification.admin",
                restored.schema_revision,
            )
        )

        command.downgrade(database._alembic_config(), starting_revision)
        with database.session() as session:
            preserved_after_rollback = session.scalar(
                select(AppUser.username).where(AppUser.id == user.id)
            )
        checks.append(
            DrillCheck(
                "ROLLBACK_COMPATIBILITY",
                database.current_revision() == starting_revision
                and preserved_after_rollback == "qualification.admin",
                database.current_revision() or "NONE",
            )
        )

        database.migrate()
        final_revision = database.current_revision()
        health = HealthService(settings, database, audit).check()
        checks.append(
            DrillCheck(
                "REUPGRADE_HEALTH",
                final_revision == "0029_kfa_identity"
                and health.state == HealthState.READY
                and health.audit_chain_valid,
                final_revision or "NONE",
            )
        )
    except Exception as exc:
        checks.append(
            DrillCheck("UNEXPECTED_ERROR", False, type(exc).__name__)
        )
    finally:
        database.dispose()
    passed = bool(checks) and all(check.passed for check in checks)
    return DataLifecycleDrillResult(
        status="PASS" if passed else "FAIL",
        application_version=__version__,
        generated_at=datetime.now(UTC).isoformat(),
        starting_revision=starting_revision,
        final_revision=final_revision,
        backup_checksum_sha256=checksum,
        checks=tuple(checks),
    )


def write_drill_report(
    result: DataLifecycleDrillResult, output: Path | str
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emss-data-lifecycle-drill")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args(argv)
    if args.work_dir is None:
        with tempfile.TemporaryDirectory(prefix="emss-release-drill-") as temp:
            result = run_data_lifecycle_drill(temp)
    else:
        result = run_data_lifecycle_drill(args.work_dir)
    output = write_drill_report(result, args.output)
    print(f"{result.status}: {output}")
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


