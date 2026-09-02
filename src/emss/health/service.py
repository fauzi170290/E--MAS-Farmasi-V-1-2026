from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import text

from emss.audit.service import AuditService
from emss.config.settings import AppSettings
from emss.database.engine import DatabaseManager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emss.services.khanza_polling import KhanzaPollingService


class HealthState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class HealthCheckResult:
    state: HealthState
    database_connected: bool
    schema_revision: str | None
    foreign_keys_enabled: bool
    journal_mode: str | None
    data_directory_writable: bool
    audit_chain_valid: bool
    khanza_connection: str
    details: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state"] = self.state.value
        return result


class HealthService:
    def __init__(
        self,
        settings: AppSettings,
        database: DatabaseManager,
        audit: AuditService,
        khanza_polling: "KhanzaPollingService | None" = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.audit = audit
        self.khanza_polling = khanza_polling

    def check(self) -> HealthCheckResult:
        details: list[str] = []
        database_connected = False
        foreign_keys_enabled = False
        journal_mode: str | None = None
        schema_revision: str | None = None
        audit_chain_valid = False

        try:
            with self.database.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
                database_connected = True
                foreign_keys_enabled = (
                    connection.execute(text("PRAGMA foreign_keys")).scalar_one()
                    == 1
                )
                journal_mode = str(
                    connection.execute(text("PRAGMA journal_mode")).scalar_one()
                ).upper()
                schema_revision = self.database.current_revision()
            with self.database.session() as session:
                audit_chain_valid = self.audit.verify_chain(session)
        except Exception as exc:
            details.append(f"Database lokal gagal: {type(exc).__name__}")

        data_directory_writable = os.access(self.settings.data_dir, os.W_OK)
        if not data_directory_writable:
            details.append("Folder data tidak dapat ditulis")
        if not foreign_keys_enabled:
            details.append("SQLite foreign_keys tidak aktif")
        if journal_mode != "WAL":
            details.append("SQLite belum menggunakan WAL")
        if schema_revision is None:
            details.append("Migrasi database belum diterapkan")
        if not audit_chain_valid:
            details.append("Rantai audit tidak valid")

        critical_ok = (
            database_connected
            and foreign_keys_enabled
            and schema_revision is not None
            and data_directory_writable
            and audit_chain_valid
        )
        state = HealthState.READY if critical_ok else HealthState.ERROR

        khanza_connection = (
            self.khanza_polling.status().connection_status
            if self.khanza_polling is not None
            else "NOT_CONFIGURED"
        )
        return HealthCheckResult(
            state=state,
            database_connected=database_connected,
            schema_revision=schema_revision,
            foreign_keys_enabled=foreign_keys_enabled,
            journal_mode=journal_mode,
            data_directory_writable=data_directory_writable,
            audit_chain_valid=audit_chain_valid,
            khanza_connection=khanza_connection,
            details=tuple(details),
        )
