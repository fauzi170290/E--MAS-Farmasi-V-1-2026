from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from sqlalchemy import select

from emss.config.settings import AppSettings, KhanzaAdapterMode
from emss.database.engine import DatabaseManager
from emss.database.integration_models import IntegrationState, PollingRun
from emss.database.catalog_models import DrugMaster
from emss.integrations.khanza import (
    KhanzaConnectionError,
    KhanzaCursor,
    KhanzaPrescriptionAdapter,
    MockKhanzaAdapter,
    MySQLKhanzaAdapter,
    PrescriptionSnapshot,
    read_snapshot,
    PrescriptionHeader,
    PrescriptionItem,
    PrescriptionSnapshot,
)
from emss.services.queue import ProcessingQueueService
from emss.services.screening import (
    DdiScreeningService,
    PrescriptionInput,
    PrescriptionItemInput,
)
from emss.utils.time import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollingResult:
    status: str
    detected: int = 0
    stable: int = 0
    processed: int = 0
    incomplete: int = 0
    failed: int = 0
    screening_ids: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class IntegrationStatus:
    adapter: str
    connection_status: str
    cursor: str
    consecutive_failures: int
    next_retry_at: str
    last_success_at: str
    last_error: str


def exponential_backoff(attempt: int, base: int, maximum: int) -> int:
    return min(maximum, base * (2 ** max(0, attempt - 1)))


def build_khanza_adapter(
    settings: AppSettings,
) -> KhanzaPrescriptionAdapter | None:
    if settings.khanza_adapter is KhanzaAdapterMode.DISABLED:
        return None
    if settings.khanza_adapter is KhanzaAdapterMode.MOCK:
        return MockKhanzaAdapter()
    if settings.khanza_adapter is KhanzaAdapterMode.MYSQL_DUMMY:
        from emss.integrations.khanza.local_dummy import LocalDummyKhanzaAdapter
        return LocalDummyKhanzaAdapter(settings)
    return MySQLKhanzaAdapter(settings)


class KhanzaPollingService:
    def __init__(
        self,
        database: DatabaseManager,
        settings: AppSettings,
        adapter: KhanzaPrescriptionAdapter | None,
        screening: DdiScreeningService,
        queue: ProcessingQueueService,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database = database
        self.settings = settings
        self.adapter = adapter
        self.screening = screening
        self.queue = queue
        self.sleeper = sleeper
        self._ensure_state()
        from emss.services.khanza_monitor import KhanzaMonitor
        self.monitor = KhanzaMonitor(self)

    @property
    def adapter_code(self) -> str:
        return self.adapter.code if self.adapter else "disabled"

    def status(self) -> IntegrationStatus:
        with self.database.session() as session:
            row = session.get(IntegrationState, self.adapter_code)
            if row is None:
                return IntegrationStatus(
                    self.adapter_code, "NOT_CONFIGURED", "", 0, "", "", ""
                )
            cursor = ""
            if row.cursor_changed_at and row.cursor_no_resep:
                cursor = KhanzaCursor(
                    row.cursor_changed_at, row.cursor_no_resep
                ).serialize()
            return IntegrationStatus(
                adapter=row.adapter_code,
                connection_status=row.connection_status,
                cursor=cursor,
                consecutive_failures=row.consecutive_failures,
                next_retry_at=(row.next_retry_at.isoformat() if row.next_retry_at else ""),
                last_success_at=(row.last_success_at.isoformat() if row.last_success_at else ""),
                last_error=row.last_error_message or "",
            )

    def poll_once(self, actor_user_id: str, *, force: bool = False) -> PollingResult:
        if self.adapter is None:
            return PollingResult("NOT_CONFIGURED", message="Adapter Khanza belum diaktifkan")
        if self.settings.pharmacy_scope_required and self.settings.pharmacy_care_setting not in {'RALAN', 'RANAP'}:
            return PollingResult('SCOPE_NOT_READY', message='Pilih layanan instalasi melalui Mode Farmasi.')
        state = self._state()
        now = utc_now()
        if not force and state.next_retry_at:
            retry = state.next_retry_at
            if retry.tzinfo is None:
                retry = retry.replace(tzinfo=now.tzinfo)
            if retry > now:
                return PollingResult("BACKOFF", message="Menunggu jadwal reconnect")

        cursor = (
            KhanzaCursor(state.cursor_changed_at, state.cursor_no_resep)
            if state.cursor_changed_at and state.cursor_no_resep
            else None
        )
        run = self._start_run(cursor)
        detected = stable = processed = incomplete = failed = 0
        screening_ids: list[str] = []
        try:
            self.adapter.test_connection()
            references = self.adapter.get_new_prescriptions(
                cursor, self.settings.khanza_page_size
            )
            detected = len(references)
            for reference in references:
                try:
                    snapshot = self._wait_until_stable(reference.no_resep)
                    if snapshot and not self.queue.allows(snapshot.header.care_setting):
                        continue
                    if snapshot is None or not snapshot.items:
                        incomplete += 1
                        self.queue.record_incomplete(
                            no_resep=reference.no_resep,
                            service_unit=reference.service_unit,
                        )
                    else:
                        stable += 1
                        screening = self.screening.screen(
                            self._to_input(snapshot),
                            actor_user_id,
                            mock_mode=self.adapter.code in {"mock", "mysql_dummy"},
                        )
                        self.queue.enqueue_screening(screening.screening_id)
                        screening_ids.append(screening.screening_id)
                        processed += 1
                except KhanzaConnectionError:
                    raise
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "Khanza prescription processing failed type=%s",
                        type(exc).__name__,
                    )
                    self.queue.record_failure(
                        no_resep=reference.no_resep,
                        service_unit=reference.service_unit,
                        error_message=f"{type(exc).__name__}: proses integrasi gagal",
                    )
                self._advance_cursor(reference.cursor)
            self._mark_connected()
            status = "SUCCESS" if failed == 0 and incomplete == 0 else "PARTIAL"
            result = PollingResult(
                status, detected, stable, processed, incomplete, failed,
                tuple(screening_ids),
            )
            self._finish_run(run, result, None)
            return result
        except KhanzaConnectionError as exc:
            self._mark_disconnected(type(exc).__name__)
            result = PollingResult(
                "DISCONNECTED", detected, stable, processed, incomplete, failed,
                tuple(screening_ids), "Koneksi Khanza terputus; tidak ada resep dinyatakan SAFE",
            )
            self._finish_run(run, result, "KHANZA_DISCONNECTED")
            return result

    def seed_mock_prescription(self) -> str:
        if not isinstance(self.adapter, MockKhanzaAdapter):
            raise ValueError("Penambahan resep uji hanya tersedia pada adapter mock")
        with self.database.session() as session:
            drugs = session.scalars(
                select(DrugMaster)
                .where(DrugMaster.is_active.is_(True))
                .order_by(DrugMaster.khanza_code)
                .limit(2)
            ).all()
        if len(drugs) >= 2:
            pairs = [(row.khanza_code, row.display_name) for row in drugs]
        else:
            pairs = [
                ("MOCK-OBAT-A", "Obat Mock A"),
                ("MOCK-OBAT-B", "Obat Mock B"),
            ]
        now = utc_now()
        no_resep = f"POLL-MOCK-{uuid.uuid4().hex[:8].upper()}"
        items = tuple(
            PrescriptionItem(
                source_item_key=str(index),
                khanza_code=code,
                display_name=name,
                quantity="1",
                directions="Simulasi adapter Sprint 6",
                route="Oral",
            )
            for index, (code, name) in enumerate(pairs, start=1)
        )
        snapshot = PrescriptionSnapshot(
            header=PrescriptionHeader(
                no_resep=no_resep,
                no_rawat=f"MOCK-RAWAT-{uuid.uuid4().hex[:6]}",
                patient_id="RM-MOCK",
                patient_name="PASIEN SIMULASI ADAPTER",
                service_unit="FARMASI MOCK",
                prescriber_name="DOKTER SIMULASI",
                status="BARU",
                changed_at=now,
            ),
            regular_items=items,
            compounded_items=(),
            revision=now.isoformat(),
        )
        self.adapter.add_snapshot(snapshot)
        return no_resep

    def _wait_until_stable(self, no_resep: str) -> PrescriptionSnapshot | None:
        previous = read_snapshot(self.adapter, no_resep)  # type: ignore[arg-type]
        for _attempt in range(1, self.settings.khanza_stability_max_attempts):
            self.sleeper(self.settings.khanza_stability_interval_seconds)
            current = read_snapshot(self.adapter, no_resep)  # type: ignore[arg-type]
            if current.fingerprint() == previous.fingerprint():
                return current
            previous = current
        return None

    @staticmethod
    def _to_input(snapshot: PrescriptionSnapshot) -> PrescriptionInput:
        header = snapshot.header
        return PrescriptionInput(
            no_resep=header.no_resep,
            patient_id=header.patient_id,
            patient_name=header.patient_name,
            service_unit=header.service_unit,
            prescriber_name=header.prescriber_name,
            source_changed_at=header.changed_at,
            items=tuple(
                PrescriptionItemInput(
                    source_item_key=row.source_item_key,
                    khanza_code=row.khanza_code,
                    display_name=row.display_name,
                    quantity=row.quantity,
                    directions=row.directions,
                    route=row.route,
                    compound_group=row.compound_group,
                )
                for row in snapshot.items
            ),
        )

    def _ensure_state(self) -> None:
        with self.database.session() as session:
            if session.get(IntegrationState, self.adapter_code) is None:
                session.add(
                    IntegrationState(
                        adapter_code=self.adapter_code,
                        connection_status=(
                            "NOT_CONFIGURED" if self.adapter is None else "NOT_TESTED"
                        ),
                    )
                )
                session.commit()

    def _state(self) -> IntegrationState:
        with self.database.session() as session:
            row = session.get(IntegrationState, self.adapter_code)
            if row is None:
                raise RuntimeError("Integration state tidak tersedia")
            session.expunge(row)
            return row

    def _advance_cursor(self, cursor: KhanzaCursor) -> None:
        with self.database.session() as session:
            row = session.get(IntegrationState, self.adapter_code)
            row.cursor_changed_at = cursor.changed_at
            row.cursor_no_resep = cursor.no_resep
            row.updated_at = utc_now()
            session.commit()

    def _mark_connected(self) -> None:
        with self.database.session() as session:
            row = session.get(IntegrationState, self.adapter_code)
            row.connection_status = "CONNECTED"
            row.consecutive_failures = 0
            row.next_retry_at = None
            row.last_success_at = utc_now()
            row.last_error_code = None
            row.last_error_message = None
            row.updated_at = utc_now()
            session.commit()

    def _mark_disconnected(self, error_code: str, message: str | None = None) -> None:
        with self.database.session() as session:
            row = session.get(IntegrationState, self.adapter_code)
            row.consecutive_failures += 1
            delay = exponential_backoff(
                row.consecutive_failures,
                self.settings.khanza_reconnect_base_seconds,
                self.settings.khanza_reconnect_max_seconds,
            )
            row.connection_status = "DISCONNECTED"
            row.next_retry_at = utc_now() + timedelta(seconds=delay)
            row.last_error_code = error_code
            row.last_error_message = message or "Koneksi Khanza gagal; reconnect dijadwalkan"
            row.updated_at = utc_now()
            session.commit()

    def _start_run(self, cursor: KhanzaCursor | None) -> str:
        with self.database.session() as session:
            row = PollingRun(
                adapter_code=self.adapter_code,
                status="RUNNING",
                cursor_before=cursor.serialize() if cursor else None,
            )
            session.add(row)
            session.commit()
            return row.id

    def _finish_run(
        self, run_id: str, result: PollingResult, error_code: str | None
    ) -> None:
        status = self.status()
        with self.database.session() as session:
            row = session.get(PollingRun, run_id)
            row.status = result.status
            row.detected_count = result.detected
            row.stable_count = result.stable
            row.processed_count = result.processed
            row.incomplete_count = result.incomplete
            row.failed_count = result.failed
            row.cursor_after = status.cursor or None
            row.error_code = error_code
            row.completed_at = utc_now()
            session.commit()
