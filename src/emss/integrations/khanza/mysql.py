from __future__ import annotations

import hashlib
from contextvars import ContextVar
from datetime import timedelta
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import URL, Engine, DateTime, bindparam, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

from emss.config.settings import AppSettings
from emss.integrations.khanza.credentials import connection_password
from emss.integrations.khanza.domain import (
    DrugMasterRow,
    KhanzaConnectionError,
    KhanzaCursor,
    KhanzaDataError,
    KhanzaScopeError,
    KhanzaScopeMismatch,
    PrescriptionHeader,
    PrescriptionItem,
    PrescriptionReference,
    PrescriptionSnapshot,
    aware_utc,
)


class MySQLKhanzaAdapter:
    """Adapter SELECT-only terhadap view integrasi yang disediakan IT."""

    code = "mysql"

    def __init__(self, settings: AppSettings, *, engine: Engine | None = None) -> None:
        self.settings = settings
        self._header = settings.khanza_header_view
        self._item = settings.khanza_item_view
        self._compound = settings.khanza_compound_view
        self._drug = settings.khanza_drug_view
        self._password_available = bool(self._connection_password())
        self.engine = engine or self._create_engine()
        self._snapshot_connection = ContextVar('khanza_snapshot_connection', default=None)

    def _connection_password(self):
        return connection_password()

    def _create_engine(self) -> Engine:
        password = self._connection_password()
        password = password or ""
        url = URL.create(
            "mysql+pymysql",
            username=self.settings.khanza_username,
            password=password,
            host=self.settings.khanza_host,
            port=self.settings.khanza_port,
            database=self.settings.khanza_database,
            query={"charset": "utf8mb4"},
        )
        timeout = self.settings.khanza_query_timeout_seconds
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=300,
            isolation_level="REPEATABLE READ",
            connect_args={
                "connect_timeout": self.settings.khanza_connect_timeout_seconds,
                "read_timeout": timeout,
                "write_timeout": timeout,
            },
        )

        @event.listens_for(engine, "connect")
        def enforce_read_only(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
            finally:
                cursor.close()

        return engine

    def test_connection(self) -> None:
        if not self._password_available:
            raise KhanzaConnectionError(
                "EMSS_KHANZA_PASSWORD belum tersedia di environment Windows"
            )
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
                for view in (self._header, self._item, self._compound, self._drug):
                    connection.execute(text(f"SELECT 1 FROM `{view}` LIMIT 1"))
                if self.settings.pharmacy_scope_required:
                    try:
                        connection.execute(text(f'SELECT asal_layanan FROM `{self._header}` LIMIT 0'))
                    except SQLAlchemyError as exc:
                        raise KhanzaScopeError('View Khanza harus menyediakan asal_layanan (ralan/ranap). Minta IT memasang pembaruan view integrasi.') from exc
        except SQLAlchemyError as exc:
            raise KhanzaConnectionError(type(exc).__name__) from exc

    def check_health(self) -> None:
        """Cheap read-only liveness probe for the one-second monitor loop.

        The complete view contract is verified at startup, reconnect, and a
        bounded interval by the monitor.  Repeating its four view probes every
        second makes the health check itself dominate polling latency.
        """
        if not self._password_available:
            raise KhanzaConnectionError(
                "EMSS_KHANZA_PASSWORD belum tersedia di environment Windows"
            )
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as exc:
            raise KhanzaConnectionError(type(exc).__name__) from exc

    def _scope_filter(self, params, prefix=''):
        if not self.settings.pharmacy_scope_required:
            return ''
        if self.settings.pharmacy_care_setting not in {'RALAN', 'RANAP'}:
            raise KhanzaScopeError('Pilih layanan instalasi melalui Mode Farmasi terlebih dahulu.')
        params['care_setting'] = self.settings.pharmacy_care_setting
        return f' AND UPPER({prefix}asal_layanan) = :care_setting'

    def get_new_prescriptions(
        self, cursor: KhanzaCursor | None, limit: int
    ) -> tuple[PrescriptionReference, ...]:
        limit = max(1, min(limit, 500))
        where = "WHERE 1=1"
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            where = (
                "WHERE (changed_at > :changed_at OR "
                "(changed_at = :changed_at AND no_resep > :no_resep))"
            )
            params.update(
                changed_at=cursor.changed_at.replace(tzinfo=None),
                no_resep=cursor.no_resep,
            )
        where += self._scope_filter(params)
        rows = self._rows(
            f"SELECT no_resep, no_rawat, changed_at, unit_depo, status_resep "
            f"FROM `{self._header}` {where} "
            "ORDER BY changed_at, no_resep LIMIT :limit",
            params,
        )
        return tuple(
            PrescriptionReference(
                no_resep=str(row["no_resep"]),
                no_rawat=str(row.get("no_rawat") or ""),
                changed_at=self._datetime(row["changed_at"]),
                service_unit=str(row.get("unit_depo") or ""),
                status=str(row.get("status_resep") or ""),
            )
            for row in rows
        )

    def latest_cursor(self) -> KhanzaCursor | None:
        params: dict[str, Any] = {}
        scope = self._scope_filter(params)
        rows = self._rows(
            f"SELECT no_resep, changed_at FROM `{self._header}` "
            f"WHERE 1=1{scope} ORDER BY changed_at DESC, no_resep DESC LIMIT 1",
            params,
        )
        if not rows:
            return None
        return KhanzaCursor(self._datetime(rows[0]["changed_at"]), str(rows[0]["no_resep"]))

    def get_prescription_header(self, no_resep: str) -> PrescriptionHeader:
        params = {'no_resep': no_resep}
        scope = self._scope_filter(params)
        rows = self._rows(
            f"SELECT * FROM `{self._header}` "
            f"WHERE no_resep = :no_resep{scope} LIMIT 1",
            params,
        )
        if not rows:
            if self.settings.pharmacy_scope_required:
                raise KhanzaScopeMismatch('Resep tidak tersedia dalam cakupan layanan instalasi ini.')
            raise KhanzaDataError("Header resep tidak ditemukan")
        row = rows[0]
        return PrescriptionHeader(
            no_resep=str(row["no_resep"]),
            no_rawat=str(row.get("no_rawat") or ""),
            patient_id=str(row.get("no_rm") or ""),
            patient_name=str(row.get("nama_pasien") or ""),
            service_unit=str(row.get("unit_depo") or ""),
            prescriber_name=str(row.get("dokter") or ""),
            status=str(row.get("status_resep") or ""),
            changed_at=self._datetime(row["changed_at"]),
            validation_token=str(row.get('validation_token') or ''),
            item_basis=str(row.get('item_basis') or 'UNVERIFIED'),
            composition_complete=str(row.get('composition_complete', '0')) == '1',
            care_setting=str(row.get('asal_layanan') or 'UNKNOWN').upper(),
        )

    def get_prescription_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]:
        return self._get_items(self._item, no_resep, compounded=False)

    def get_compounded_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]:
        return self._get_items(self._compound, no_resep, compounded=True)

    def _get_items(
        self, view: str, no_resep: str, *, compounded: bool
    ) -> tuple[PrescriptionItem, ...]:
        group = ", no_racik" if compounded else ""
        params = {'no_resep': no_resep}
        scope = self._scope_filter(params, 'h.')
        restriction = (f' AND EXISTS (SELECT 1 FROM `{self._header}` h WHERE h.no_resep = `{view}`.no_resep{scope})' if scope else '')
        rows = self._rows(
            f"SELECT source_item_key, kode_brng, nama_brng, jumlah, "
            f"aturan_pakai, rute{group} FROM `{view}` "
            f"WHERE no_resep = :no_resep{restriction} ORDER BY source_item_key LIMIT 1001",
            params,
        )
        if len(rows) > 1000:
            raise KhanzaDataError('Jumlah item melebihi batas; skrining tidak lengkap')
        return tuple(
            PrescriptionItem(
                source_item_key=str(row["source_item_key"]),
                khanza_code=str(row["kode_brng"]),
                display_name=str(row.get("nama_brng") or row["kode_brng"]),
                quantity=str(row.get("jumlah") or ""),
                directions=str(row.get("aturan_pakai") or ""),
                route=str(row.get("rute") or ""),
                compound_group=(str(row.get("no_racik") or "") if compounded else ""),
            )
            for row in rows
        )

    def get_prescription_revision(self, no_resep: str) -> str:
        header = self.get_prescription_header(no_resep)
        items = self.get_prescription_items(no_resep) + self.get_compounded_items(no_resep)
        payload = "|".join(
            [header.changed_at.isoformat() if header.changed_at else ""]
            + [repr(row) for row in items]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_snapshot(self, no_resep: str) -> PrescriptionSnapshot:
        # One repeatable-read transaction prevents a mixture of different commits.
        with self.engine.connect() as connection, connection.begin():
            token = self._snapshot_connection.set(connection)
            try:
                return PrescriptionSnapshot(self.get_prescription_header(no_resep),
                    self.get_prescription_items(no_resep),
                    self.get_compounded_items(no_resep), '')
            finally:
                self._snapshot_connection.reset(token)

    def source_time(self) -> datetime:
        return self._datetime(self._rows('SELECT CURRENT_TIMESTAMP AS now', {})[0]['now'])

    def scan_prescriptions(self, after_key: str, limit: int, *, since=None):
        params = {'key': after_key, 'limit': max(1, min(limit, 500))}
        where = 'no_resep > :key'
        if since is not None:
            where += ' AND changed_at >= :since'
            params['since'] = since.replace(tzinfo=None)
        where += self._scope_filter(params)
        rows = self._rows(f'SELECT no_resep, no_rawat, changed_at, unit_depo, status_resep '
            f'FROM `{self._header}` WHERE {where} ORDER BY no_resep LIMIT :limit', params)
        return tuple(PrescriptionReference(str(r['no_resep']), str(r['no_rawat']),
            self._datetime(r['changed_at']), str(r.get('unit_depo') or ''),
            str(r.get('status_resep') or '')) for r in rows)

    def get_active_drug_master(
        self, cursor_code: str = "", limit: int = 500
    ) -> tuple[DrugMasterRow, ...]:
        rows = self._rows(
            f"SELECT kode_brng, nama_brng, aktif FROM `{self._drug}` "
            "WHERE kode_brng > :cursor AND aktif = 1 "
            "ORDER BY kode_brng LIMIT :limit",
            {"cursor": cursor_code, "limit": max(1, min(limit, 500))},
        )
        return tuple(
            DrugMasterRow(str(row["kode_brng"]), str(row["nama_brng"]), True)
            for row in rows
        )

    def get_clinical_context(self, no_rawat: str) -> dict[str, str]:
        return {"no_rawat": no_rawat}

    def close(self) -> None:
        self.engine.dispose()

    def _rows(self, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not statement.lstrip().upper().startswith("SELECT"):
            raise KhanzaDataError("Adapter Khanza hanya mengizinkan SELECT")
        query = text(statement)
        for name, value in params.items():
            if isinstance(value, datetime):
                query = query.bindparams(bindparam(name, type_=DateTime()))
        try:
            snapshot_connection = self._snapshot_connection.get()
            if snapshot_connection is not None:
                return [dict(row) for row in snapshot_connection.execute(query, params).mappings()]
            with self.engine.connect() as connection:
                return [dict(row) for row in connection.execute(query, params).mappings()]
        except SQLAlchemyError as exc:
            raise KhanzaConnectionError(type(exc).__name__) from exc

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if not isinstance(value, datetime):
            raise KhanzaDataError("changed_at dari view harus DATETIME")
        return aware_utc(value)
