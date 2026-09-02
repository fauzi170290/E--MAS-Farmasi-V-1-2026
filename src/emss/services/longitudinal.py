"""Local, bounded prescription context. No source queries or schema changes.

A cross-prescription case belongs to the prescription first screened later in
E-MAS. Source time controls eligibility, not ownership (late arrivals are valid).
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json

from sqlalchemy import select, func, case, or_
from emss.database.monitoring_models import MonitorEvent, MonitorInbox
from emss.database.screening_models import Prescription, PrescriptionRevision, Screening
from emss.integrations.khanza.domain import aware_utc

FINAL_STATUSES = frozenset({"DIPROSES_FARMASI", "DISERAHKAN"})
MAX_CONTEXT = 200
POLICY = "same-local-calendar-day-v1"


def is_cancelled(event):
    return bool(event and (event.event_type == "VALIDATION_CANCELLED" or
        event.source_status in {"DIBATALKAN", "DIBERHENTIKAN"}))


def snapshot(event):
    try:
        value = json.loads(event.snapshot_json)
        return value if isinstance(value, dict) and isinstance(value.get("header"), dict) else {}
    except (ValueError, TypeError):
        return {}


def timestamp(value):
    try:
        return aware_utc(datetime.fromisoformat(value)) if value else None
    except (ValueError, TypeError):
        return None


def local_day_bounds(value):
    """Return the workstation-local calendar day as UTC query bounds."""
    parsed = timestamp(value) if isinstance(value, str) else aware_utc(value)
    if parsed is None:
        return None
    local = parsed.astimezone()
    start_local = datetime(local.year, local.month, local.day, tzinfo=local.tzinfo)
    return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)


def eligible(current, prior):
    left, right = timestamp(current.get("changed_at")), timestamp(prior.get("changed_at"))
    return bool(left and right and left.astimezone().date() == right.astimezone().date())


def owner(session, event):
    return session.scalar(select(Prescription).join(PrescriptionRevision)
        .join(Screening).join(MonitorEvent, MonitorEvent.screening_id == Screening.id)
        .where(MonitorEvent.adapter_code == event.adapter_code, MonitorEvent.no_resep == event.no_resep)
        .order_by(PrescriptionRevision.revision_number.desc()).limit(1))


@dataclass(frozen=True)
class Context:
    event: MonitorEvent
    payload: dict
    prescription: Prescription


def contexts(session, event, patient_id, is_mock):
    """Select latest source event BEFORE checking final/cancelled status.

    Only already-screened prescriptions can be context. BEGIN IMMEDIATE in the
    caller makes simultaneous arrivals observe the preceding committed result.
    """
    header = snapshot(event).get("header", {})
    if not patient_id or header.get("patient_id") != patient_id:
        return [], ["Identitas pasien stabil belum tersedia/konsisten; DDI lintas resep belum dapat dinilai."], []
    care = header.get("care_setting", "UNKNOWN")
    if care not in {"RALAN", "RANAP"}:
        return [], ["Asal layanan belum diketahui; konteks DDI lintas resep belum dapat dipastikan."], []
    bounds = local_day_bounds(header.get("changed_at"))
    if bounds is None:
        return [], ["Waktu sumber resep saat ini tidak diketahui; DDI lintas resep hari ini belum dapat dinilai."], []
    day_start, day_end = bounds
    current = owner(session, event)
    statement = select(Prescription, MonitorEvent.no_resep).join(PrescriptionRevision).join(Screening).join(
        MonitorEvent, MonitorEvent.screening_id == Screening.id).where(
        or_(Prescription.patient_id == patient_id,
            func.json_extract(case((func.json_valid(MonitorEvent.snapshot_json), MonitorEvent.snapshot_json),
                else_="{}"), "$.header.patient_id") == patient_id),
        Prescription.is_mock.is_(is_mock),
        MonitorEvent.adapter_code == event.adapter_code, MonitorEvent.no_resep != event.no_resep,
        PrescriptionRevision.source_changed_at.is_not(None),
        PrescriptionRevision.source_changed_at >= day_start,
        PrescriptionRevision.source_changed_at < day_end)
    if current:
        statement = statement.where((Prescription.created_at < current.created_at) |
            ((Prescription.created_at == current.created_at) & (Prescription.id < current.id)))
    rows = session.execute(statement.distinct().order_by(Prescription.created_at.desc(), Prescription.id)
        .limit(MAX_CONTEXT + 1)).all()
    warnings = []
    if len(rows) > MAX_CONTEXT:
        warnings.append("Kandidat riwayat melebihi batas 200 resep; perlu rekonsiliasi, pemeriksaan belum lengkap.")
        rows = rows[:MAX_CONTEXT]
    if not rows:
        return [], warnings, []
    latest = select(MonitorEvent.no_resep, func.max(MonitorEvent.sequence).label("seq")).where(
        MonitorEvent.adapter_code == event.adapter_code,
        MonitorEvent.no_resep.in_([number for _, number in rows])).group_by(MonitorEvent.no_resep).subquery()
    events = session.scalars(select(MonitorEvent).join(latest,
        (latest.c.no_resep == MonitorEvent.no_resep) & (latest.c.seq == MonitorEvent.sequence))
        .where(MonitorEvent.adapter_code == event.adapter_code)).all()
    prescriptions = {number: row for row, number in rows}
    result = []
    for previous in events:
        payload = snapshot(previous)
        prior = payload.get("header", {})
        if not prior:
            warnings.append(f"Konteks resep {previous.no_resep} tidak dapat dibaca; perlu rekonsiliasi.")
            continue
        if prior.get("patient_id") != patient_id:
            warnings.append(f"Identitas pasien pada resep {previous.no_resep} berubah; resep tidak dipakai sebagai konteks. "
                "Tinjau koreksi identitas dan perubahan hasil.")
            continue
        if prior.get("care_setting") not in {"RALAN", "RANAP"}:
            warnings.append(f"Asal layanan resep {previous.no_resep} belum diketahui; konteks belum lengkap.")
            continue
        if prior.get("care_setting") != care:
            continue
        if not eligible(header, prior):
            if not timestamp(prior.get("changed_at")):
                warnings.append(f"Waktu sumber resep {previous.no_resep} tidak diketahui; konteks belum lengkap.")
            continue
        if previous.source_status not in FINAL_STATUSES:
            # Includes cancellation/withdrawn validation. Never fall back to old FINAL.
            if is_cancelled(previous):
                warnings.append(f"Resep {previous.no_resep} dibatalkan/validasinya ditarik; komposisi lama tidak dipakai. "
                    "Tinjau perubahan terapi dan rekonsiliasi sebelum menyimpulkan hasil.")
            continue
        if prior.get("item_basis") != "FINAL" or not prior.get("composition_complete"):
            warnings.append(f"Komposisi akhir resep {previous.no_resep} belum terverifikasi.")
            continue
        result.append(Context(previous, payload, prescriptions[previous.no_resep]))
    # Include rejected/cancelled revisions too: reverting to an empty context
    # must not reuse an old, possibly reviewed revision as the newest result.
    state = sorted((e.no_resep, e.id, e.fingerprint) for e in events)
    return sorted(result, key=lambda c: c.event.no_resep), warnings, state


def provenance(event, payload, revision_id="", revision_number=None):
    header = payload.get("header", {})
    return {"adapter": event.adapter_code, "no_resep": event.no_resep,
        "event_id": event.id, "source_sequence": event.sequence,
        "source_revision": payload.get("revision", ""), "source_fingerprint": event.fingerprint,
        "revision_id": revision_id, "revision_number": revision_number,
        "changed_at": header.get("changed_at"), "no_rawat": header.get("no_rawat", ""),
        "service_unit": header.get("service_unit", ""), "prescriber_name": header.get("prescriber_name", ""),
        "care_setting": header.get("care_setting", "UNKNOWN"), "source_status": event.source_status}


def decode_provenance(raw):
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, dict) and value.get("format") == "cross_rx_v1" else None
    except (ValueError, TypeError):
        return None


def storage_key(rule_key, other_source_number):
    return "CROSS:" + hashlib.sha256(f"{other_source_number}|{rule_key}".encode()).hexdigest()


def invalidate_dependents(session, changed, previous_event, now):
    """Durable local wake-up on a source revision, in the observation transaction.

    Never wake older owners for a new prescription, and never reread Khanza for
    a context-only change. The old result remains immutable and attributable.
    """
    if previous_event is None:
        return 0
    root = owner(session, previous_event)
    if root is None:
        return 0
    old_header = snapshot(previous_event).get("header", {})
    new_header = snapshot(changed).get("header", {})
    bounds = [value for value in (
        local_day_bounds(old_header.get("changed_at")),
        local_day_bounds(new_header.get("changed_at")),
    ) if value]
    if not bounds:
        return 0
    day_start = min(value[0] for value in bounds)
    day_end = max(value[1] for value in bounds)
    candidates = session.execute(select(MonitorInbox, Prescription).join(MonitorEvent,
        MonitorInbox.event_id == MonitorEvent.id).join(Screening, MonitorInbox.screening_id == Screening.id)
        .join(PrescriptionRevision, Screening.revision_id == PrescriptionRevision.id)
        .join(Prescription, PrescriptionRevision.prescription_id == Prescription.id).where(
        MonitorInbox.adapter_code == changed.adapter_code, MonitorInbox.no_resep != changed.no_resep,
        MonitorInbox.state.in_(("COMPLETED", "RECHECK", "CONTEXT_PENDING")),
        Prescription.patient_id.in_({old_header.get("patient_id", ""), new_header.get("patient_id", "")}),
        PrescriptionRevision.source_changed_at.is_not(None),
        PrescriptionRevision.source_changed_at >= day_start,
        PrescriptionRevision.source_changed_at < day_end,
        (Prescription.created_at > root.created_at) |
        ((Prescription.created_at == root.created_at) & (Prescription.id > root.id)))).all()
    count = 0
    for inbox, _ in candidates:
        source = session.get(MonitorEvent, inbox.event_id)
        header = snapshot(source).get("header", {})
        if any(header.get("patient_id") == h.get("patient_id") and
               header.get("care_setting") == h.get("care_setting") and eligible(header, h)
               for h in (old_header, new_header)):
            inbox.state, inbox.next_attempt_at = "CONTEXT_PENDING", now
            count += 1
    return count
