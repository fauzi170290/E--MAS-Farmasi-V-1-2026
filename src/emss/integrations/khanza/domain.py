from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol


def aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, order=True)
class KhanzaCursor:
    changed_at: datetime
    no_resep: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_at", aware_utc(self.changed_at))

    def serialize(self) -> str:
        return f"{self.changed_at.isoformat()}|{self.no_resep}"


@dataclass(frozen=True)
class PrescriptionReference:
    no_resep: str
    no_rawat: str
    changed_at: datetime
    service_unit: str = ""
    status: str = ""

    @property
    def cursor(self) -> KhanzaCursor:
        return KhanzaCursor(self.changed_at, self.no_resep)


@dataclass(frozen=True)
class PrescriptionHeader:
    no_resep: str
    no_rawat: str
    patient_id: str = ""
    patient_name: str = ""
    service_unit: str = ""
    prescriber_name: str = ""
    status: str = ""
    changed_at: datetime | None = None
    validation_token: str = ""
    item_basis: str = "UNVERIFIED"
    composition_complete: bool = False
    care_setting: str = 'UNKNOWN'


@dataclass(frozen=True)
class PrescriptionItem:
    source_item_key: str
    khanza_code: str
    display_name: str
    quantity: str = ""
    directions: str = ""
    route: str = ""
    compound_group: str = ""


@dataclass(frozen=True)
class DrugMasterRow:
    khanza_code: str
    display_name: str
    active: bool = True


@dataclass(frozen=True)
class PrescriptionSnapshot:
    header: PrescriptionHeader
    regular_items: tuple[PrescriptionItem, ...]
    compounded_items: tuple[PrescriptionItem, ...]
    revision: str

    @property
    def items(self) -> tuple[PrescriptionItem, ...]:
        return self.regular_items + self.compounded_items

    def fingerprint(self) -> str:
        payload = {
            "header": asdict(self.header),
            "items": [asdict(row) for row in self.items],
            "revision": self.revision,
        }
        payload["header"]["changed_at"] = (
            self.header.changed_at.isoformat() if self.header.changed_at else None
        )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class KhanzaConnectionError(ConnectionError):
    pass


class KhanzaDataError(ValueError):
    pass


class KhanzaScopeError(KhanzaDataError):
    pass


class KhanzaScopeMismatch(KhanzaScopeError):
    pass


class KhanzaPrescriptionAdapter(Protocol):
    code: str

    def test_connection(self) -> None: ...
    def check_health(self) -> None: ...
    def get_new_prescriptions(
        self, cursor: KhanzaCursor | None, limit: int
    ) -> tuple[PrescriptionReference, ...]: ...
    def latest_cursor(self) -> KhanzaCursor | None: ...
    def get_prescription_header(self, no_resep: str) -> PrescriptionHeader: ...
    def get_prescription_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]: ...
    def get_compounded_items(self, no_resep: str) -> tuple[PrescriptionItem, ...]: ...
    def get_prescription_revision(self, no_resep: str) -> str: ...
    def get_active_drug_master(
        self, cursor_code: str = "", limit: int = 500
    ) -> tuple[DrugMasterRow, ...]: ...
    def get_clinical_context(self, no_rawat: str) -> dict[str, str]: ...
    def close(self) -> None: ...


def read_snapshot(
    adapter: KhanzaPrescriptionAdapter, no_resep: str
) -> PrescriptionSnapshot:
    atomic_reader = getattr(adapter, "get_snapshot", None)
    if atomic_reader is not None:
        return atomic_reader(no_resep)
    return PrescriptionSnapshot(
        header=adapter.get_prescription_header(no_resep),
        regular_items=adapter.get_prescription_items(no_resep),
        compounded_items=adapter.get_compounded_items(no_resep),
        revision=adapter.get_prescription_revision(no_resep),
    )
