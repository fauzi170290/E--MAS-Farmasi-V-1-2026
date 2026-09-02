from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    SILENT_PILOT = "silent_pilot"
    ADVISORY_PILOT = "advisory_pilot"
    PRODUCTION = "production"


class KhanzaAdapterMode(StrEnum):
    DISABLED = "disabled"
    MOCK = "mock"
    MYSQL = "mysql"
    MYSQL_DUMMY = "mysql_dummy"


def default_data_dir() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "eMSSFarmasi"
    return Path.home() / ".emss-farmasi"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMSS_",
        case_sensitive=False,
        extra="forbid",
    )

    environment: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_name: str = "E-MAS Farmasi"
    data_dir: Path = Field(default_factory=default_data_dir)
    database_filename: str = "emss.db"
    log_level: str = "INFO"
    session_timeout_minutes: int = Field(default=15, ge=1, le=240)
    login_max_attempts: int = Field(default=5, ge=3, le=20)
    login_lock_minutes: int = Field(default=15, ge=1, le=1440)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1000, le=60000)
    allow_workstation_mode: bool = False
    workstation_label: str = "Farmasi"
    # Loaded from pharmacy_installation, never inferred from poli/IP/user name.
    pharmacy_care_setting: str = Field(default='', exclude=True)
    tray_enabled: bool = True
    minimize_to_tray: bool = True
    single_instance: bool = True
    backup_daily_enabled: bool = True
    backup_retention_days: int = Field(default=30, ge=1, le=3650)
    backup_retention_count: int = Field(default=30, ge=1, le=1000)
    khanza_adapter: KhanzaAdapterMode = KhanzaAdapterMode.DISABLED
    khanza_dummy_prescriptions: tuple[str, ...] = ()
    khanza_dummy_consent: bool = False
    khanza_dummy_follow_patients: bool = False
    khanza_dummy_show_patient_name: bool = False
    khanza_polling_enabled: bool = False
    # Separate explicit consent: never silently convert a no-polling requirement.
    khanza_internal_polling_consent: bool = False
    khanza_recent_days: int = Field(default=2, ge=1, le=30)
    khanza_monitor_batch_size: int = Field(default=30, ge=1, le=100)
    khanza_poll_interval_seconds: int = Field(default=1, ge=1, le=300)
    khanza_page_size: int = Field(default=100, ge=1, le=500)
    khanza_stability_interval_seconds: float = Field(default=2.0, ge=0, le=30)
    khanza_stability_max_attempts: int = Field(default=3, ge=2, le=10)
    khanza_reconnect_base_seconds: int = Field(default=5, ge=1, le=300)
    khanza_reconnect_max_seconds: int = Field(default=300, ge=5, le=3600)
    khanza_host: str = "127.0.0.1"
    khanza_port: int = Field(default=3306, ge=1, le=65535)
    khanza_database: str = "sik"
    khanza_username: str = "emss_readonly"
    khanza_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    khanza_query_timeout_seconds: int = Field(default=10, ge=1, le=120)
    khanza_header_view: str = "vw_emss_prescription_header"
    khanza_item_view: str = "vw_emss_prescription_item"
    khanza_compound_view: str = "vw_emss_compound_item"
    khanza_drug_view: str = "vw_emss_drug_master"

    @property
    def pharmacy_scope_required(self) -> bool:
        return bool(self.pharmacy_care_setting) or self.khanza_adapter in {
            KhanzaAdapterMode.MYSQL, KhanzaAdapterMode.MYSQL_DUMMY}

    @model_validator(mode="after")
    def validate_dummy_scope(self):
        if self.khanza_adapter == KhanzaAdapterMode.MYSQL_DUMMY:
            import re
            ids = self.khanza_dummy_prescriptions
            if self.environment != AppEnvironment.TEST or not self.khanza_dummy_consent:
                raise ValueError("Adapter dummy memerlukan environment TEST dan persetujuan eksplisit")
            if self.khanza_host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Uji dummy hanya boleh membaca Khanza lokal")
            if not 1 <= len(ids) <= 10 or len(set(ids)) != len(ids) or not all(
                re.fullmatch(r"[A-Za-z0-9/_-]{1,80}", key) for key in ids
            ):
                raise ValueError("Isi 1-10 nomor resep dummy unik yang telah dikonfirmasi")
            if self.data_dir.resolve() == default_data_dir().resolve():
                raise ValueError("Uji dummy wajib menggunakan direktori terpisah")
        return self

    @field_validator("database_filename")
    @classmethod
    def validate_database_filename(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.name != value or candidate.suffix.lower() != ".db":
            raise ValueError("database_filename harus berupa nama file .db")
        return value

    @field_validator('app_name', mode='before')
    @classmethod
    def migrate_legacy_display_name(cls, value):
        # Presentation only. Keep EMSS_ env keys, data_dir, filename and config untouched.
        if isinstance(value, str) and value.startswith('e-MSS'):
            return 'E-MAS Farmasi' + (' — UJI DUMMY LOKAL' if 'UJI DUMMY' in value else '')
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level tidak valid")
        return normalized

    @field_validator(
        "khanza_header_view", "khanza_item_view", "khanza_compound_view",
        "khanza_drug_view"
    )
    @classmethod
    def validate_khanza_identifier(cls, value: str) -> str:
        if not value or not value.replace("_", "a").isalnum():
            raise ValueError("Nama view Khanza hanya boleh huruf, angka, underscore")
        return value

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "Database"

    @property
    def database_path(self) -> Path:
        return self.database_dir / self.database_filename

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "Backups"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "Exports"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "Logs"

    @property
    def database_url(self) -> str:
        resolved = self.database_path.resolve()
        return f"sqlite+pysqlite:///{resolved.as_posix()}"

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.database_dir,
            self.backup_dir,
            self.export_dir,
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, Any]:
        return {
            "environment": self.environment.value,
            "app_name": self.app_name,
            "data_dir": str(self.data_dir),
            "database_path": str(self.database_path),
            "log_level": self.log_level,
            "session_timeout_minutes": self.session_timeout_minutes,
            "allow_workstation_mode": self.allow_workstation_mode,
            "tray_enabled": self.tray_enabled,
            "single_instance": self.single_instance,
            "backup_daily_enabled": self.backup_daily_enabled,
            "backup_retention_days": self.backup_retention_days,
            "backup_retention_count": self.backup_retention_count,
            "khanza_adapter": self.khanza_adapter.value,
            "khanza_polling_enabled": self.khanza_polling_enabled,
            "khanza_endpoint": f"{self.khanza_host}:{self.khanza_port}",
            "khanza_database": self.khanza_database,
            "khanza_username": self.khanza_username,
        }


def load_settings(config_path: Path | str | None = None) -> AppSettings:
    if config_path is None:
        return AppSettings()

    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"File konfigurasi tidak ditemukan: {path}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    if not isinstance(raw, dict):
        raise ValueError("Konfigurasi TOML harus berupa tabel utama")

    # Retire the former one-second local-test mode safely. Existing local
    # configuration is preserved on disk, but it must not start polling or be
    # silently redirected to a production Khanza endpoint.
    if raw.get("khanza_adapter") == "mysql_local_test":
        raw = dict(raw)
        raw["khanza_adapter"] = "disabled"
        for key in (
            "khanza_local_test_consent", "khanza_local_test_use_machine_credential",
            "khanza_local_test_since",
        ):
            raw.pop(key, None)
    settings = AppSettings(**raw)
    if not settings.data_dir.is_absolute():
        settings.data_dir = (path.parent / settings.data_dir).resolve()
    return settings
