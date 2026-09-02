from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from emss.audit.service import AuditEvent, AuditService
from emss.config.settings import AppSettings
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser
from emss.utils.time import utc_now


class BackupError(ValueError):
    pass


@dataclass(frozen=True)
class BackupRecord:
    database_path: Path
    manifest_path: Path
    config_snapshot_path: Path | None
    created_at: str
    reason: str
    checksum_sha256: str
    size_bytes: int
    schema_revision: str
    integrity_ok: bool


@dataclass(frozen=True)
class RestoreResult:
    restored_from: Path
    safety_backup: Path
    schema_revision: str
    restart_required: bool = True


_SAFE_REASON = re.compile(r"[^A-Z0-9_-]+")


class BackupService:
    MANIFEST_SUFFIX = ".manifest.json"

    def __init__(
        self,
        settings: AppSettings,
        database: DatabaseManager,
        audit: AuditService,
    ) -> None:
        self.settings = settings
        self.database = database
        self.audit = audit

    def create_backup(
        self,
        reason: str,
        actor_user_id: str | None = None,
    ) -> BackupRecord:
        source = self.settings.database_path.resolve()
        if not source.is_file():
            raise BackupError("Database aktif tidak ditemukan")
        backup_dir = self.settings.backup_dir.resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        reason_code = _SAFE_REASON.sub("_", reason.strip().upper()).strip("_")
        if not reason_code:
            raise BackupError("Alasan backup wajib diisi")
        timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
        stem = f"emss-{timestamp}-{reason_code.lower()}-{uuid.uuid4().hex[:8]}"
        target = backup_dir / f"{stem}.db"
        temporary = backup_dir / f".{stem}.tmp"
        manifest_path = backup_dir / f"{stem}{self.MANIFEST_SUFFIX}"
        config_path = backup_dir / f"{stem}.config.json"

        try:
            with closing(sqlite3.connect(source)) as source_db:
                self._require_integrity(source_db, "Database aktif")
                with closing(sqlite3.connect(temporary)) as target_db:
                    source_db.backup(target_db)
                    self._require_integrity(target_db, "Hasil backup")
            temporary.replace(target)
            checksum = self._sha256(target)
            schema_revision = self._schema_revision(target)
            created_at = utc_now().isoformat()
            config_snapshot = {
                "created_at": created_at,
                "note": (
                    "Snapshot konfigurasi nonsensitif. Password integrasi "
                    "tidak disimpan."
                ),
                "settings": self.settings.safe_summary(),
            }
            self._write_json_atomic(config_path, config_snapshot)
            manifest = {
                "format_version": 1,
                "created_at": created_at,
                "reason": reason_code,
                "database_filename": target.name,
                "config_snapshot_filename": config_path.name,
                "checksum_sha256": checksum,
                "size_bytes": target.stat().st_size,
                "schema_revision": schema_revision,
                "integrity_ok": True,
                "actor_user_id": actor_user_id,
            }
            self._write_json_atomic(manifest_path, manifest)
        except (OSError, sqlite3.Error, BackupError) as exc:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            raise BackupError(f"Backup gagal: {exc}") from exc

        self._append_audit(
            "BACKUP_CREATED",
            actor_user_id,
            target,
            {
                "reason": reason_code,
                "checksum_sha256": checksum,
                "schema_revision": schema_revision,
                "size_bytes": target.stat().st_size,
            },
        )
        self.prune_retention()
        return BackupRecord(
            database_path=target,
            manifest_path=manifest_path,
            config_snapshot_path=config_path,
            created_at=created_at,
            reason=reason_code,
            checksum_sha256=checksum,
            size_bytes=target.stat().st_size,
            schema_revision=schema_revision,
            integrity_ok=True,
        )

    def create_daily_if_due(self) -> BackupRecord | None:
        if not self.settings.backup_daily_enabled:
            return None
        today = utc_now().date()
        if any(
            record.reason == "DAILY"
            and datetime.fromisoformat(record.created_at).date() == today
            for record in self.list_backups()
        ):
            return None
        return self.create_backup("DAILY")

    def list_backups(self) -> list[BackupRecord]:
        result: list[BackupRecord] = []
        backup_dir = self.settings.backup_dir.resolve()
        if not backup_dir.is_dir():
            return result
        for manifest_path in backup_dir.glob(f"*{self.MANIFEST_SUFFIX}"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                database_path = backup_dir / str(manifest["database_filename"])
                config_name = manifest.get("config_snapshot_filename")
                config_path = backup_dir / str(config_name) if config_name else None
                if not database_path.is_file():
                    continue
                result.append(
                    BackupRecord(
                        database_path=database_path,
                        manifest_path=manifest_path,
                        config_snapshot_path=(
                            config_path if config_path and config_path.is_file() else None
                        ),
                        created_at=str(manifest["created_at"]),
                        reason=str(manifest["reason"]),
                        checksum_sha256=str(manifest["checksum_sha256"]),
                        size_bytes=int(manifest["size_bytes"]),
                        schema_revision=str(manifest.get("schema_revision") or ""),
                        integrity_ok=bool(manifest.get("integrity_ok")),
                    )
                )
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item.created_at, reverse=True)

    def verify_backup(
        self,
        database_path: Path | str,
        actor_user_id: str | None = None,
    ) -> BackupRecord:
        path = Path(database_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".db":
            raise BackupError("File backup database tidak ditemukan")
        manifest_path = path.with_name(path.stem + self.MANIFEST_SUFFIX)
        if not manifest_path.is_file():
            raise BackupError("Manifest backup tidak ditemukan")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackupError("Manifest backup rusak") from exc
        if manifest.get("database_filename") != path.name:
            raise BackupError("Manifest tidak sesuai file database")
        checksum = self._sha256(path)
        if checksum != manifest.get("checksum_sha256"):
            raise BackupError("Checksum backup tidak sesuai")
        try:
            with closing(
                sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            ) as db:
                self._require_integrity(db, "Backup")
        except sqlite3.Error as exc:
            raise BackupError(f"Backup tidak dapat dibaca: {exc}") from exc
        schema_revision = self._schema_revision(path)
        if schema_revision != str(manifest.get("schema_revision") or ""):
            raise BackupError("Revisi schema backup tidak sesuai manifest")
        config_name = manifest.get("config_snapshot_filename")
        config_path = path.parent / str(config_name) if config_name else None
        record = BackupRecord(
            database_path=path,
            manifest_path=manifest_path,
            config_snapshot_path=(
                config_path if config_path and config_path.is_file() else None
            ),
            created_at=str(manifest["created_at"]),
            reason=str(manifest["reason"]),
            checksum_sha256=checksum,
            size_bytes=path.stat().st_size,
            schema_revision=schema_revision,
            integrity_ok=True,
        )
        self._append_audit(
            "BACKUP_VERIFIED",
            actor_user_id,
            path,
            {"checksum_sha256": checksum, "schema_revision": schema_revision},
        )
        return record

    def restore_backup(
        self,
        database_path: Path | str,
        actor_user_id: str | None,
    ) -> RestoreResult:
        selected = self.verify_backup(database_path, actor_user_id)
        if selected.database_path == self.settings.database_path.resolve():
            raise BackupError("Database aktif tidak boleh dipilih sebagai backup")
        safety = self.create_backup("PRE_RESTORE", actor_user_id)
        active = self.settings.database_path.resolve()
        self.database.dispose()
        try:
            self._copy_sqlite_database(selected.database_path, active)
            self.database.migrate()
            with closing(sqlite3.connect(active)) as restored:
                self._require_integrity(restored, "Database hasil restore")
            schema_revision = self.database.current_revision() or ""
            effective_actor = self._existing_actor(actor_user_id)
            self._append_audit(
                "DATABASE_RESTORED",
                effective_actor,
                selected.database_path,
                {
                    "source_checksum_sha256": selected.checksum_sha256,
                    "safety_backup": safety.database_path.name,
                    "schema_revision": schema_revision,
                },
            )
        except Exception as exc:
            self.database.dispose()
            try:
                self._copy_sqlite_database(safety.database_path, active)
            except Exception as rollback_exc:
                raise BackupError(
                    "Restore gagal dan pemulihan safety backup juga gagal: "
                    f"{type(rollback_exc).__name__}"
                ) from exc
            raise BackupError(f"Restore gagal; safety backup dipulihkan: {exc}") from exc
        return RestoreResult(
            restored_from=selected.database_path,
            safety_backup=safety.database_path,
            schema_revision=schema_revision,
        )

    def prune_retention(self) -> int:
        records = self.list_backups()
        cutoff = utc_now() - timedelta(days=self.settings.backup_retention_days)
        keep_count = self.settings.backup_retention_count
        removed = 0
        for index, record in enumerate(records):
            try:
                created = datetime.fromisoformat(record.created_at)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                should_remove = index >= keep_count or created < cutoff
            except ValueError:
                should_remove = True
            if not should_remove:
                continue
            for path in (
                record.database_path,
                record.manifest_path,
                record.config_snapshot_path,
            ):
                if path is not None and self._inside_backup_dir(path):
                    path.unlink(missing_ok=True)
            removed += 1
        return removed

    def _append_audit(
        self,
        action: str,
        actor_user_id: str | None,
        entity_path: Path,
        details: dict[str, Any],
    ) -> None:
        with self.database.session() as session:
            self.audit.append(
                session,
                AuditEvent(
                    category="SYSTEM_AUDIT",
                    action=action,
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="LOCAL_BACKUP",
                    entity_id=entity_path.name,
                    details=details,
                ),
            )
            session.commit()

    def _existing_actor(self, actor_user_id: str | None) -> str | None:
        if not actor_user_id:
            return None
        with self.database.session() as session:
            return session.scalar(
                select(AppUser.id).where(AppUser.id == actor_user_id)
            )

    def _inside_backup_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.settings.backup_dir.resolve())
        except ValueError:
            return False
        return True

    @staticmethod
    def _copy_sqlite_database(source: Path, target: Path) -> None:
        with closing(
            sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        ) as source_db:
            with closing(sqlite3.connect(target)) as target_db:
                source_db.backup(target_db)

    @staticmethod
    def _require_integrity(database: sqlite3.Connection, label: str) -> None:
        integrity = database.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise BackupError(f"{label} gagal integrity_check")
        foreign_key_issues = database.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            raise BackupError(f"{label} mempunyai pelanggaran foreign key")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _schema_revision(path: Path) -> str:
        with closing(
            sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        ) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='schema_version'"
            ).fetchone()
            if not exists:
                return ""
            row = db.execute("SELECT version_num FROM schema_version LIMIT 1").fetchone()
            return str(row[0]) if row else ""

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        # Keep the temporary name deliberately short. Windows installations can
        # still enforce MAX_PATH, while backup directories are often nested
        # below ProgramData or a long test/workspace path.
        temporary = path.parent / f"._{uuid.uuid4().hex[:8]}.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
