from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from emss.utils.time import utc_now

from emss.integrations.khanza.domain import (
    DrugMasterRow,
    KhanzaConnectionError,
    KhanzaCursor,
    PrescriptionHeader,
    PrescriptionItem,
    PrescriptionReference,
    PrescriptionSnapshot,
    aware_utc,
)


class MockKhanzaAdapter:
    code = "mock"

    def __init__(self) -> None:
        self._snapshots: dict[str, PrescriptionSnapshot] = {}
        self._connected = True
        self._mutations: dict[str, list[PrescriptionSnapshot]] = {}

    def add_snapshot(self, snapshot: PrescriptionSnapshot) -> None:
        self._snapshots[snapshot.header.no_resep] = snapshot

    def set_connected(self, connected: bool) -> None:
        self._connected = connected

    def set_read_sequence(
        self, no_resep: str, snapshots: list[PrescriptionSnapshot]
    ) -> None:
        self._mutations[no_resep] = list(snapshots)

    def test_connection(self) -> None:
        self._require_connection()

    def check_health(self) -> None:
        self._require_connection()

    def get_new_prescriptions(
        self, cursor: KhanzaCursor | None, limit: int
    ) -> tuple[PrescriptionReference, ...]:
        self._require_connection()
        rows = []
        for snapshot in self._snapshots.values():
            header = snapshot.header
            changed_at = header.changed_at or datetime.min
            reference = PrescriptionReference(
                no_resep=header.no_resep,
                no_rawat=header.no_rawat,
                changed_at=aware_utc(changed_at),
                service_unit=header.service_unit,
                status=header.status,
            )
            if cursor is None or reference.cursor > cursor:
                rows.append(reference)
        rows.sort(key=lambda row: row.cursor)
        return tuple(rows[: max(1, limit)])

    def latest_cursor(self) -> KhanzaCursor | None:
        self._require_connection()
        references = self.get_new_prescriptions(None, max(1, len(self._snapshots)))
        return max((row.cursor for row in references), default=None)

    def _snapshot(self, no_resep: str) -> PrescriptionSnapshot:
        self._require_connection()
        sequence = self._mutations.get(no_resep)
        if sequence:
            snapshot = sequence.pop(0)
            self._snapshots[no_resep] = snapshot
            if not sequence:
                self._mutations.pop(no_resep, None)
            return snapshot
        try:
            return self._snapshots[no_resep]
        except KeyError as exc:
            raise ValueError(f"Resep mock tidak ditemukan: {no_resep}") from exc

    def get_snapshot(self, no_resep: str) -> PrescriptionSnapshot:
        return self._snapshot(no_resep)

    def source_time(self):
        return utc_now()

    def scan_prescriptions(self, after_key, limit, *, since=None):
        self._require_connection()
        threshold = aware_utc(since) if since is not None else None
        rows = []
        for snapshot in self._snapshots.values():
            header = snapshot.header
            changed_at = aware_utc(header.changed_at or datetime.min)
            if header.no_resep <= after_key or (threshold is not None and changed_at < threshold):
                continue
            rows.append(PrescriptionReference(header.no_resep, header.no_rawat, changed_at,
                header.service_unit, header.status))
        return tuple(sorted(rows, key=lambda row: row.no_resep)[:max(1, limit)])

    def get_prescription_header(self, no_resep: str) -> PrescriptionHeader:
        return self._snapshot(no_resep).header

    def get_prescription_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]:
        return self._snapshots[no_resep].regular_items

    def get_compounded_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]:
        return self._snapshots[no_resep].compounded_items

    def get_prescription_revision(self, no_resep: str) -> str:
        return self._snapshots[no_resep].revision

    def get_active_drug_master(
        self, cursor_code: str = "", limit: int = 500
    ) -> tuple[DrugMasterRow, ...]:
        unique: dict[str, DrugMasterRow] = {}
        for snapshot in self._snapshots.values():
            for item in snapshot.items:
                unique[item.khanza_code] = DrugMasterRow(
                    item.khanza_code, item.display_name
                )
        return tuple(
            unique[key]
            for key in sorted(unique)
            if key > cursor_code
        )[:limit]

    def get_clinical_context(self, no_rawat: str) -> dict[str, str]:
        self._require_connection()
        return {"no_rawat": no_rawat}

    def close(self) -> None:
        return None

    def _require_connection(self) -> None:
        if not self._connected:
            raise KhanzaConnectionError("Koneksi mock Khanza diputus")


def changed_snapshot(
    snapshot: PrescriptionSnapshot, *, revision: str
) -> PrescriptionSnapshot:
    return replace(snapshot, revision=revision)
