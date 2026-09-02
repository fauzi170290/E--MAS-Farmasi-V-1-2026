from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.intervention_models import (
    InterventionDetail,
    PharmacistIntervention,
)
from emss.database.models import AppUser, UserRole
from emss.database.queue_models import ProcessingQueue
from emss.database.screening_models import ScreeningIssue, ScreeningPair
from emss.utils.time import utc_now


class InterventionError(ValueError):
    pass


INTERVENTION_TYPES = (
    ("NO_INTERVENTION", "Tidak perlu intervensi"),
    ("CLINICAL_MONITORING", "Monitoring klinis"),
    ("LAB_MONITORING", "Monitoring laboratorium"),
    ("PATIENT_EDUCATION", "Edukasi pasien"),
    ("ADMINISTRATION_TIME", "Penyesuaian waktu pemberian"),
    ("DOSE_ADJUSTMENT", "Rekomendasi penyesuaian dosis"),
    ("DRUG_SUBSTITUTION", "Rekomendasi penggantian obat"),
    ("DRUG_DISCONTINUATION", "Rekomendasi penghentian obat"),
    ("INDICATION_CLARIFICATION", "Klarifikasi indikasi"),
    ("PRESCRIBER_CONFIRMATION", "Konfirmasi dokter"),
    ("SERVICE_DELAY", "Penundaan pelayanan"),
    ("OTHER", "Lainnya"),
)

DECISIONS = (
    ("CHANGE_MEDICATION", "Obat diganti"),
    ("STOP_MEDICATION", "Obat dihentikan"),
    ("ADJUST_DOSE", "Dosis disesuaikan"),
    ("ADJUST_SCHEDULE", "Waktu pemberian disesuaikan"),
    ("CONTINUE_WITH_MONITORING", "Terapi dilanjutkan dengan monitoring"),
    ("CONTINUE_UNCHANGED", "Terapi dilanjutkan tanpa perubahan"),
    ("NO_CHANGE_REQUIRED", "Tidak diperlukan perubahan"),
    ("PENDING", "Belum diputuskan"),
)

COMMUNICATION_RESULTS = (
    ("ACCEPTED_FULL", "Diterima seluruhnya"),
    ("ACCEPTED_PARTIAL", "Diterima sebagian"),
    ("NOT_ACCEPTED", "Tidak diterima"),
    ("DOCTOR_UNREACHABLE", "Dokter tidak dapat dihubungi"),
    ("PENDING", "Belum diputuskan"),
    ("NO_CHANGE_REQUIRED", "Tidak diperlukan perubahan"),
    ("CONTINUE_WITH_MONITORING", "Terapi dilanjutkan dengan monitoring"),
)

COMMUNICATION_METHODS = (
    ("PHONE", "Telepon"),
    ("WHATSAPP_CALL", "WhatsApp call"),
    ("DIRECT", "Komunikasi langsung"),
    ("OTHER", "Lainnya"),
)

CONTINUED_DECISIONS = {
    "CONTINUE_WITH_MONITORING",
    "CONTINUE_UNCHANGED",
}


@dataclass(frozen=True)
class InterventionRecord:
    id: str
    queue_item_id: str
    no_resep: str
    service_unit: str
    risk_status: str
    pharmacist_name: str
    status: str
    intervention_type: str
    decision: str
    communication_method: str
    communication_result: str
    contacted_party: str
    reason_if_continued: str
    notes: str
    created_at: str
    updated_at: str
    completed_at: str


class PharmacistInterventionService:
    AUTHORIZED_ROLES = {"APOTEKER", "SUPER_ADMIN", "CLINICAL_REVIEWER"}

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def save(
        self,
        *,
        queue_item_id: str,
        actor_user_id: str,
        intervention_type: str,
        decision: str,
        communication_method: str = "",
        communication_result: str = "",
        contacted_party: str = "",
        reason_if_continued: str = "",
        notes: str = "",
        complete: bool = False,
    ) -> InterventionRecord:
        intervention_type = intervention_type.strip().upper()
        decision = decision.strip().upper()
        communication_method = communication_method.strip().upper()
        communication_result = communication_result.strip().upper()
        contacted_party = contacted_party.strip()
        reason_if_continued = reason_if_continued.strip()
        notes = notes.strip()
        self._validate_codes(
            intervention_type,
            decision,
            communication_method,
            communication_result,
        )

        with self.database.session() as session:
            actor = session.scalar(
                select(AppUser)
                .options(
                    selectinload(AppUser.roles).selectinload(UserRole.role)
                )
                .where(AppUser.id == actor_user_id)
            )
            if actor is None or not actor.is_active:
                raise InterventionError("Identitas apoteker tidak ditemukan")
            role_codes = {link.role.code for link in actor.roles}
            if not role_codes.intersection(self.AUTHORIZED_ROLES):
                raise InterventionError(
                    "Akun ini tidak berwenang mencatat intervensi klinis"
                )
            if actor.normalized_username == "mode.farmasi":
                raise InterventionError(
                    "Mode Farmasi tidak dapat mencatat intervensi atas nama petugas"
                )

            queue = session.get(ProcessingQueue, queue_item_id)
            if queue is None:
                raise InterventionError("Resep pada antrean tidak ditemukan")
            self._validate_clinical_fields(
                queue.risk_status,
                decision,
                communication_method,
                communication_result,
                contacted_party,
                reason_if_continued,
                complete,
            )

            now = utc_now()
            row = session.scalar(
                select(PharmacistIntervention).where(
                    PharmacistIntervention.queue_item_id == queue_item_id
                )
            )
            created = row is None
            if row is None:
                row = PharmacistIntervention(
                    queue_item_id=queue.id,
                    screening_id=queue.screening_id,
                    pharmacist_user_id=actor.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            row.pharmacist_user_id = actor.id
            row.intervention_type = intervention_type
            row.decision = decision
            row.communication_method = communication_method or None
            row.communication_result = communication_result or None
            row.contacted_party = contacted_party or None
            row.reason_if_continued = reason_if_continued or None
            row.notes = notes or None
            row.status = "COMPLETED" if complete else "OPEN"
            row.completed_at = now if complete else None
            row.updated_at = now
            session.flush()

            for detail in list(row.details):
                session.delete(detail)
            session.flush()
            self._snapshot_findings(session, row, queue)

            queue.review_status = (
                "INTERVENTION_COMPLETED" if complete else "INTERVENTION_OPEN"
            )
            if complete:
                queue.reviewed_by = actor.id
                queue.reviewed_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_AUDIT",
                    action=(
                        "INTERVENTION_CREATED"
                        if created
                        else "INTERVENTION_UPDATED"
                    ),
                    outcome="SUCCESS",
                    actor_user_id=actor.id,
                    entity_type="pharmacist_intervention",
                    entity_id=row.id,
                    details={
                        "queue_item_id": queue.id,
                        "no_resep": queue.source_no_resep,
                        "risk_status": queue.risk_status,
                        "intervention_type": intervention_type,
                        "decision": decision,
                        "communication_result": communication_result or None,
                        "status": row.status,
                    },
                ),
            )
            session.commit()
            return self._record(row, queue, actor.display_name)

    def get_for_queue(self, queue_item_id: str) -> InterventionRecord | None:
        with self.database.session() as session:
            result = session.execute(
                select(PharmacistIntervention, ProcessingQueue, AppUser)
                .join(
                    ProcessingQueue,
                    ProcessingQueue.id == PharmacistIntervention.queue_item_id,
                )
                .join(
                    AppUser,
                    AppUser.id == PharmacistIntervention.pharmacist_user_id,
                )
                .where(PharmacistIntervention.queue_item_id == queue_item_id)
            ).one_or_none()
            if result is None:
                return None
            row, queue, actor = result
            return self._record(row, queue, actor.display_name)

    def list_records(
        self, *, status: str = "", search: str = "", limit: int = 500
    ) -> list[InterventionRecord]:
        statement = (
            select(PharmacistIntervention, ProcessingQueue, AppUser)
            .join(
                ProcessingQueue,
                ProcessingQueue.id == PharmacistIntervention.queue_item_id,
            )
            .join(
                AppUser,
                AppUser.id == PharmacistIntervention.pharmacist_user_id,
            )
        )
        if status:
            statement = statement.where(
                PharmacistIntervention.status == status.upper()
            )
        if search.strip():
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    ProcessingQueue.source_no_resep.ilike(pattern),
                    ProcessingQueue.service_unit.ilike(pattern),
                    AppUser.display_name.ilike(pattern),
                )
            )
        statement = statement.order_by(
            PharmacistIntervention.updated_at.desc()
        ).limit(max(1, min(limit, 2000)))
        with self.database.session() as session:
            return [
                self._record(row, queue, actor.display_name)
                for row, queue, actor in session.execute(statement).all()
            ]

    @staticmethod
    def _validate_codes(
        intervention_type: str,
        decision: str,
        communication_method: str,
        communication_result: str,
    ) -> None:
        if intervention_type not in dict(INTERVENTION_TYPES):
            raise InterventionError("Jenis intervensi tidak valid")
        if decision not in dict(DECISIONS):
            raise InterventionError("Keputusan intervensi tidak valid")
        if communication_method and communication_method not in dict(
            COMMUNICATION_METHODS
        ):
            raise InterventionError("Media komunikasi tidak valid")
        if communication_result and communication_result not in dict(
            COMMUNICATION_RESULTS
        ):
            raise InterventionError("Hasil komunikasi tidak valid")

    @staticmethod
    def _validate_clinical_fields(
        risk_status: str,
        decision: str,
        communication_method: str,
        communication_result: str,
        contacted_party: str,
        reason_if_continued: str,
        complete: bool,
    ) -> None:
        if not complete:
            return
        if decision == "PENDING":
            raise InterventionError(
                "Intervensi belum dapat diselesaikan karena keputusan masih tertunda"
            )
        if risk_status in {"HIGH_RISK", "CRITICAL"}:
            if not communication_method:
                raise InterventionError(
                    "Media komunikasi wajib untuk HIGH_RISK atau CRITICAL"
                )
            if not communication_result:
                raise InterventionError(
                    "Hasil komunikasi wajib untuk HIGH_RISK atau CRITICAL"
                )
            if not contacted_party:
                raise InterventionError(
                    "Nama dokter/pihak yang dihubungi wajib dicatat"
                )
        if decision in CONTINUED_DECISIONS and not reason_if_continued:
            raise InterventionError(
                "Alasan wajib dicatat bila terapi tetap dilanjutkan"
            )

    @staticmethod
    def _snapshot_findings(
        session, row: PharmacistIntervention, queue: ProcessingQueue
    ) -> None:
        if not queue.screening_id:
            return
        pairs = session.scalars(
            select(ScreeningPair).where(
                ScreeningPair.screening_id == queue.screening_id
            )
        ).all()
        issues = session.scalars(
            select(ScreeningIssue).where(
                ScreeningIssue.screening_id == queue.screening_id
            )
        ).all()
        for pair in pairs:
            session.add(
                InterventionDetail(
                    intervention_id=row.id,
                    finding_type="DDI_PAIR",
                    reference=pair.pair_key,
                    action=row.intervention_type,
                    outcome=row.decision,
                    notes=pair.recommendation or pair.clinical_effect,
                )
            )
        for issue in issues:
            session.add(
                InterventionDetail(
                    intervention_id=row.id,
                    finding_type=issue.issue_type,
                    reference=(
                        issue.pair_key
                        or issue.khanza_code
                        or issue.display_name
                    ),
                    action=row.intervention_type,
                    outcome=row.decision,
                    notes=issue.message,
                )
            )

    @staticmethod
    def _record(
        row: PharmacistIntervention,
        queue: ProcessingQueue,
        pharmacist_name: str,
    ) -> InterventionRecord:
        return InterventionRecord(
            id=row.id,
            queue_item_id=queue.id,
            no_resep=queue.source_no_resep,
            service_unit=queue.service_unit or "-",
            risk_status=queue.risk_status,
            pharmacist_name=pharmacist_name,
            status=row.status,
            intervention_type=row.intervention_type,
            decision=row.decision,
            communication_method=row.communication_method or "",
            communication_result=row.communication_result or "",
            contacted_party=row.contacted_party or "",
            reason_if_continued=row.reason_if_continued or "",
            notes=row.notes or "",
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
            completed_at=row.completed_at.isoformat() if row.completed_at else "",
        )
