from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import case, func, select

from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.intervention_models import PharmacistIntervention
from emss.database.queue_models import ProcessingQueue
from emss.database.models import Role, UserRole
from emss.database.screening_models import ScreeningIssue, ScreeningPair
from emss.utils.time import utc_now


MONTH_NAMES = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


@dataclass(frozen=True)
class PeriodBounds:
    code: str
    label: str
    start: datetime | None
    end: datetime | None
    previous_start: datetime | None
    previous_end: datetime | None


@dataclass(frozen=True)
class DashboardSummary:
    period_code: str
    period_label: str
    prescriptions_screened: int
    previous_prescriptions: int
    prescription_change_percent: float | None
    critical: int
    critical_rate: float
    high_risk: int
    high_risk_total: int
    high_risk_rate: float
    review: int
    incomplete: int
    completeness_rate: float
    interventions_total: int
    interventions_open: int
    interventions_completed: int
    high_risk_interventions_completed: int
    intervention_coverage_rate: float
    accepted: int
    communicated: int
    acceptance_rate: float
    average_completion_minutes: float
    duplicate_therapy: int
    polypharmacy: int
    high_alert: int
    lasa: int
    contraindicated_pairs: int = 0
    serious_pairs: int = 0
    significant_pairs: int = 0
    minor_pairs: int = 0
    assessed_no_interaction_pairs: int = 0
    not_assessed_pairs: int = 0
    unique_ddi_pairs: int = 0
    cross_prescription_findings: int = 0


@dataclass(frozen=True)
class UnitRiskSummary:
    service_unit: str
    prescriptions: int
    critical: int
    high_risk: int
    risk_rate: float
    interventions: int


@dataclass(frozen=True)
class MonthlyTrend:
    month_number: int
    month_label: str
    prescriptions: int
    critical: int
    critical_rate: float
    high_risk: int
    high_risk_rate: float
    interventions_completed: int
    accepted: int
    communicated: int
    acceptance_rate: float


class DashboardService:
    VALID_PERIODS = {"DAY", "MONTH", "QUARTER", "YEAR", "ALL"}

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def period_bounds(
        self, period_code: str = "ALL", anchor: date | None = None
    ) -> PeriodBounds:
        code = period_code.upper()
        if code not in self.VALID_PERIODS:
            raise ValueError("Periode dashboard tidak valid")
        # DAY follows the workstation's operational calendar day.  Timestamps
        # are still stored as UTC; no clinical/source date is invented.
        anchor = anchor or datetime.now().astimezone().date()
        if code == "ALL":
            return PeriodBounds("ALL", "Seluruh data", None, None, None, None)
        if code == "DAY":
            start = datetime(anchor.year, anchor.month, anchor.day)
            end = start + timedelta(days=1)
            previous_start = start - timedelta(days=1)
            return PeriodBounds(
                code,
                f"{anchor.day:02d}/{anchor.month:02d}/{anchor.year}",
                start,
                end,
                previous_start,
                start,
            )
        if code == "MONTH":
            start = datetime(anchor.year, anchor.month, 1)
            end = self._month_start(anchor.year, anchor.month + 1)
            previous_start = self._month_start(anchor.year, anchor.month - 1)
            return PeriodBounds(
                code,
                f"{MONTH_NAMES[anchor.month - 1]} {anchor.year}",
                start,
                end,
                previous_start,
                start,
            )
        if code == "QUARTER":
            quarter = (anchor.month - 1) // 3 + 1
            first_month = (quarter - 1) * 3 + 1
            start = datetime(anchor.year, first_month, 1)
            end = self._month_start(anchor.year, first_month + 3)
            previous_start = self._month_start(anchor.year, first_month - 3)
            return PeriodBounds(
                code,
                f"Triwulan {self._roman(quarter)} {anchor.year}",
                start,
                end,
                previous_start,
                start,
            )
        start = datetime(anchor.year, 1, 1)
        end = datetime(anchor.year + 1, 1, 1)
        return PeriodBounds(
            code,
            f"Tahun {anchor.year}",
            start,
            end,
            datetime(anchor.year - 1, 1, 1),
            start,
        )

    def summary(
        self, period_code: str = "ALL", anchor: date | None = None
    ) -> DashboardSummary:
        bounds = self.period_bounds(period_code, anchor)
        with self.database.session() as session:
            effective_ids = self._effective_queue_ids(session, bounds.start, bounds.end)
            queue_statement = select(
                func.count(ProcessingQueue.id),
                func.sum(case((ProcessingQueue.risk_status == "CRITICAL", 1), else_=0)),
                func.sum(case((ProcessingQueue.risk_status == "HIGH_RISK", 1), else_=0)),
                func.sum(case((ProcessingQueue.risk_status == "REVIEW", 1), else_=0)),
                func.sum(
                    case(
                        (ProcessingQueue.completeness_status != "COMPLETE", 1),
                        else_=0,
                    )
                ),
            )
            queue_statement = queue_statement.where(ProcessingQueue.id.in_(effective_ids))
            prescriptions, critical, high_risk, review, incomplete = (
                session.execute(queue_statement).one()
            )
            prescriptions = int(prescriptions or 0)
            critical = int(critical or 0)
            high_risk = int(high_risk or 0)
            review = int(review or 0)
            incomplete = int(incomplete or 0)

            previous_ids = self._effective_queue_ids(
                session, bounds.previous_start, bounds.previous_end
            ) if bounds.previous_start is not None else ()
            previous_statement = select(func.count(ProcessingQueue.id)).where(
                ProcessingQueue.id.in_(previous_ids)
            )
            previous = (
                int(session.scalar(previous_statement) or 0)
                if bounds.previous_start is not None
                else 0
            )

            intervention_statement = select(PharmacistIntervention)
            intervention_statement = self._apply_period(
                intervention_statement,
                PharmacistIntervention.created_at,
                bounds.start,
                bounds.end,
            )
            interventions = session.scalars(intervention_statement).all()
            completed = [row for row in interventions if row.status == "COMPLETED"]
            accepted = sum(
                row.communication_result in {"ACCEPTED_FULL", "ACCEPTED_PARTIAL"}
                for row in completed
            )
            communicated = sum(bool(row.communication_result) for row in completed)
            durations = [
                (row.completed_at - row.created_at).total_seconds() / 60
                for row in completed
                if row.completed_at is not None
            ]

            coverage_statement = (
                select(func.count(PharmacistIntervention.id))
                .join(
                    ProcessingQueue,
                    ProcessingQueue.id == PharmacistIntervention.queue_item_id,
                )
                .where(
                    PharmacistIntervention.status == "COMPLETED",
                    ProcessingQueue.risk_status.in_(("HIGH_RISK", "CRITICAL")),
                    ProcessingQueue.id.in_(effective_ids),
                )
            )
            coverage_statement = self._apply_period(
                coverage_statement,
                ProcessingQueue.detected_at,
                bounds.start,
                bounds.end,
            )
            high_risk_completed = int(session.scalar(coverage_statement) or 0)

            safety_statement = (
                select(
                    func.count(func.distinct(case((ScreeningIssue.issue_type == "DUPLICATE_THERAPY", ProcessingQueue.id), else_=None))),
                    func.count(func.distinct(case((ScreeningIssue.issue_type == "POLYPHARMACY", ProcessingQueue.id), else_=None))),
                    func.count(func.distinct(case((ScreeningIssue.issue_type == "HIGH_ALERT", ProcessingQueue.id), else_=None))),
                    func.count(func.distinct(case((ScreeningIssue.issue_type == "LASA", ProcessingQueue.id), else_=None))),
                )
                .select_from(ProcessingQueue)
                .join(ScreeningIssue, ScreeningIssue.screening_id == ProcessingQueue.screening_id)
                .where(ProcessingQueue.id.in_(effective_ids))
            )
            duplicate_therapy, polypharmacy, high_alert_count, lasa = (
                int(value or 0) for value in session.execute(safety_statement).one()
            )
            pair_statement = (
                select(
                    func.sum(case(((ScreeningPair.severity_code == 'CONTRAINDICATED') & (ScreeningPair.classification == 'INTERACTION_FOUND'), 1), else_=0)),
                    func.sum(case(((ScreeningPair.severity_code == 'SERIOUS') & (ScreeningPair.classification == 'INTERACTION_FOUND'), 1), else_=0)),
                    func.sum(case(((ScreeningPair.severity_code == 'SIGNIFICANT') & (ScreeningPair.classification == 'INTERACTION_FOUND'), 1), else_=0)),
                    func.sum(case(((ScreeningPair.severity_code == 'MINOR') & (ScreeningPair.classification == 'INTERACTION_FOUND'), 1), else_=0)),
                    func.sum(case((ScreeningPair.classification == 'ASSESSED_NO_INTERACTION', 1), else_=0)),
                    func.sum(case((ScreeningPair.classification.in_(('PAIR_NOT_ASSESSED', 'NOT_ASSESSED', 'NOT_ASSESSABLE')), 1), else_=0)),
                    func.count(func.distinct(case((ScreeningPair.classification == 'INTERACTION_FOUND',
                        ScreeningPair.ingredient_low + ' || ' + ScreeningPair.ingredient_high), else_=None))),
                    func.sum(case(((ScreeningPair.classification == 'INTERACTION_FOUND') &
                        ScreeningPair.khanza_codes_json.like('%cross_rx_v1%'), 1), else_=0)),
                )
                .select_from(ProcessingQueue)
                .join(ScreeningPair, ScreeningPair.screening_id == ProcessingQueue.screening_id)
                .where(ProcessingQueue.id.in_(effective_ids))
            )
            pair_counts = tuple(int(value or 0) for value in session.execute(pair_statement).one())

        high_risk_total = critical + high_risk
        return DashboardSummary(
            period_code=bounds.code,
            period_label=bounds.label,
            prescriptions_screened=prescriptions,
            previous_prescriptions=previous,
            prescription_change_percent=self._change_percent(prescriptions, previous),
            critical=critical,
            critical_rate=self._percent(critical, prescriptions),
            high_risk=high_risk,
            high_risk_total=high_risk_total,
            high_risk_rate=self._percent(high_risk_total, prescriptions),
            review=review,
            incomplete=incomplete,
            completeness_rate=self._percent(prescriptions - incomplete, prescriptions),
            interventions_total=len(interventions),
            interventions_open=len(interventions) - len(completed),
            interventions_completed=len(completed),
            high_risk_interventions_completed=high_risk_completed,
            intervention_coverage_rate=self._percent(
                high_risk_completed, high_risk_total
            ),
            accepted=accepted,
            communicated=communicated,
            acceptance_rate=self._percent(accepted, communicated),
            average_completion_minutes=(
                sum(durations) / len(durations) if durations else 0
            ),
            duplicate_therapy=duplicate_therapy,
            polypharmacy=polypharmacy,
            high_alert=high_alert_count,
            lasa=lasa,
            contraindicated_pairs=pair_counts[0],
            serious_pairs=pair_counts[1],
            significant_pairs=pair_counts[2],
            minor_pairs=pair_counts[3],
            assessed_no_interaction_pairs=pair_counts[4],
            not_assessed_pairs=pair_counts[5],
            unique_ddi_pairs=pair_counts[6],
            cross_prescription_findings=pair_counts[7],
        )

    def by_unit(
        self, period_code: str = "ALL", anchor: date | None = None
    ) -> list[UnitRiskSummary]:
        bounds = self.period_bounds(period_code, anchor)
        with self.database.session() as session:
            effective_ids = self._effective_queue_ids(session, bounds.start, bounds.end)
        statement = (
            select(
                ProcessingQueue.service_unit,
                func.count(ProcessingQueue.id),
                func.sum(
                    case((ProcessingQueue.risk_status == "CRITICAL", 1), else_=0)
                ),
                func.sum(
                    case((ProcessingQueue.risk_status == "HIGH_RISK", 1), else_=0)
                ),
                func.count(PharmacistIntervention.id),
            )
            .outerjoin(
                PharmacistIntervention,
                PharmacistIntervention.queue_item_id == ProcessingQueue.id,
            )
            .where(ProcessingQueue.id.in_(effective_ids))
            .group_by(ProcessingQueue.service_unit)
            .order_by(func.count(ProcessingQueue.id).desc())
        )
        with self.database.session() as session:
            rows = session.execute(statement).all()
        return [
            UnitRiskSummary(
                service_unit=unit or "Tidak diketahui",
                prescriptions=int(total or 0),
                critical=int(critical or 0),
                high_risk=int(high_risk or 0),
                risk_rate=self._percent(
                    int(critical or 0) + int(high_risk or 0), int(total or 0)
                ),
                interventions=int(interventions or 0),
            )
            for unit, total, critical, high_risk, interventions in rows
        ]

    def monthly_trend(self, year: int) -> list[MonthlyTrend]:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        with self.database.session() as session:
            effective_ids = self._effective_queue_ids(session, start, end)
            queue_rows = session.execute(
                select(
                    func.strftime("%m", ProcessingQueue.detected_at),
                    func.count(ProcessingQueue.id),
                    func.sum(
                        case(
                            (ProcessingQueue.risk_status == "CRITICAL", 1),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (ProcessingQueue.risk_status == "HIGH_RISK", 1),
                            else_=0,
                        )
                    ),
                )
                .where(
                    ProcessingQueue.id.in_(effective_ids),
                )
                .group_by(func.strftime("%m", ProcessingQueue.detected_at))
            ).all()
            interventions = session.scalars(
                select(PharmacistIntervention).where(
                    PharmacistIntervention.created_at >= start,
                    PharmacistIntervention.created_at < end,
                )
            ).all()
        queue_by_month = {
            int(month): (int(total or 0), int(critical or 0), int(high_risk or 0))
            for month, total, critical, high_risk in queue_rows
        }
        intervention_by_month: dict[int, list[PharmacistIntervention]] = {}
        for row in interventions:
            intervention_by_month.setdefault(row.created_at.month, []).append(row)
        result: list[MonthlyTrend] = []
        for month in range(1, 13):
            total, critical, high_risk = queue_by_month.get(month, (0, 0, 0))
            month_interventions = intervention_by_month.get(month, [])
            completed = [
                row for row in month_interventions if row.status == "COMPLETED"
            ]
            accepted = sum(
                row.communication_result in {"ACCEPTED_FULL", "ACCEPTED_PARTIAL"}
                for row in completed
            )
            communicated = sum(bool(row.communication_result) for row in completed)
            result.append(
                MonthlyTrend(
                    month_number=month,
                    month_label=MONTH_NAMES[month - 1],
                    prescriptions=total,
                    critical=critical,
                    critical_rate=self._percent(critical, total),
                    high_risk=high_risk,
                    high_risk_rate=self._percent(high_risk, total),
                    interventions_completed=len(completed),
                    accepted=accepted,
                    communicated=communicated,
                    acceptance_rate=self._percent(accepted, communicated),
                )
            )
        return result

    def available_years(self) -> tuple[int, ...]:
        current = utc_now().year
        with self.database.session() as session:
            values = session.scalars(
                select(func.strftime("%Y", ProcessingQueue.detected_at)).distinct()
            ).all()
        years = {int(value) for value in values if value and str(value).isdigit()}
        years.add(current)
        return tuple(sorted(years, reverse=True))

    def export_aggregate_csv(
        self,
        path: Path,
        actor_user_id: str,
        period_code: str = "ALL",
        anchor: date | None = None,
    ) -> Path:
        with self.database.session() as session:
            authorized = session.scalar(
                select(func.count()).select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == actor_user_id, Role.code == 'SUPER_ADMIN')
            )
            if not authorized:
                raise ValueError('Ekspor dashboard pDDI hanya tersedia untuk SUPER_ADMIN')
        path = Path(path)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = self.summary(period_code, anchor)
        unit_rows = self.by_unit(period_code, anchor)
        trend_year = (anchor or utc_now().date()).year
        trend = self.monthly_trend(trend_year)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["DASHBOARD KAJIAN POTENSI INTERAKSI OBAT (pDDI) - E-MAS FARMASI"])
            writer.writerow(["Periode", summary.period_label])
            writer.writerow(["Dibuat pada", utc_now().isoformat()])
            writer.writerow(["Basis metrik", "Resep = hasil skrining efektif terbaru per resep pada periode; pasangan = temuan pada hasil efektif tersebut. Temuan lintas resep dimiliki satu resep pemicu sehingga tidak dihitung ganda."])
            writer.writerow([])
            writer.writerow(["Indikator", "Jumlah", "Persentase"])
            for label, value, percentage in (
                ("Resep diskrining", summary.prescriptions_screened, ""),
                ("CRITICAL", summary.critical, summary.critical_rate),
                ("Risiko tinggi", summary.high_risk_total, summary.high_risk_rate),
                (
                    "Intervensi selesai",
                    summary.interventions_completed,
                    summary.intervention_coverage_rate,
                ),
                ("Rekomendasi diterima", summary.accepted, summary.acceptance_rate),
                (
                    "Data skrining lengkap",
                    summary.prescriptions_screened - summary.incomplete,
                    summary.completeness_rate,
                ),
                ("Duplicate therapy", summary.duplicate_therapy, self._percent(summary.duplicate_therapy, summary.prescriptions_screened)),
                ("Polifarmasi", summary.polypharmacy, self._percent(summary.polypharmacy, summary.prescriptions_screened)),
                ("High-alert", summary.high_alert, self._percent(summary.high_alert, summary.prescriptions_screened)),
                ("LASA", summary.lasa, self._percent(summary.lasa, summary.prescriptions_screened)),
                ("Pasangan kontraindikasi", summary.contraindicated_pairs, self._percent(summary.contraindicated_pairs, summary.prescriptions_screened)),
                ("Pasangan mayor/serius", summary.serious_pairs, self._percent(summary.serious_pairs, summary.prescriptions_screened)),
                ("Pasangan signifikan", summary.significant_pairs, self._percent(summary.significant_pairs, summary.prescriptions_screened)),
                ("Pasangan minor", summary.minor_pairs, self._percent(summary.minor_pairs, summary.prescriptions_screened)),
                ("Pasangan dinilai tanpa pDDI", summary.assessed_no_interaction_pairs, self._percent(summary.assessed_no_interaction_pairs, summary.prescriptions_screened)),
                ("Pasangan belum dinilai", summary.not_assessed_pairs, self._percent(summary.not_assessed_pairs, summary.prescriptions_screened)),
                ("Pasangan pDDI unik", summary.unique_ddi_pairs, ""),
                ("Temuan pDDI lintas resep", summary.cross_prescription_findings, self._percent(summary.cross_prescription_findings, summary.prescriptions_screened)),
            ):
                writer.writerow(
                    [label, value, f"{percentage:.1f}%" if percentage != "" else ""]
                )
            writer.writerow([])
            writer.writerow(["CATATAN", "pDDI adalah potensi interaksi berbasis pasangan obat pada basis aktif; bukan bukti kesalahan dokter atau apoteker dan memerlukan konteks klinis serta penilaian manfaat-risiko."])
            writer.writerow([])
            writer.writerow(
                [
                    "Unit/Depo",
                    "Resep",
                    "CRITICAL",
                    "HIGH_RISK",
                    "Risiko tinggi (%)",
                    "Intervensi",
                ]
            )
            for row in unit_rows:
                writer.writerow(
                    [
                        row.service_unit,
                        row.prescriptions,
                        row.critical,
                        row.high_risk,
                        f"{row.risk_rate:.1f}%",
                        row.interventions,
                    ]
                )
            writer.writerow([])
            writer.writerow([f"TREN BULANAN {trend_year}"])
            writer.writerow(
                [
                    "Bulan",
                    "Resep",
                    "CRITICAL",
                    "CRITICAL (%)",
                    "HIGH_RISK",
                    "HIGH_RISK (%)",
                    "Intervensi selesai",
                    "Acceptance rate (%)",
                ]
            )
            for row in trend:
                writer.writerow(
                    [
                        row.month_label,
                        row.prescriptions,
                        row.critical,
                        f"{row.critical_rate:.1f}",
                        row.high_risk,
                        f"{row.high_risk_rate:.1f}",
                        row.interventions_completed,
                        f"{row.acceptance_rate:.1f}",
                    ]
                )
        temporary.replace(path)
        with self.database.session() as session:
            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="AGGREGATE_REPORT_EXPORTED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="aggregate_report",
                    entity_id=path.name,
                    details={
                        "format": "CSV",
                        "period": summary.period_label,
                        "contains_patient_identity": False,
                    },
                ),
            )
            session.commit()
        return path

    @staticmethod
    def _apply_period(statement, column, start, end):
        if start is not None:
            statement = statement.where(column >= start)
        if end is not None:
            statement = statement.where(column < end)
        return statement

    @staticmethod
    def _effective_queue_ids(session, start, end) -> tuple[str, ...]:
        ranked = select(
            ProcessingQueue.id.label('id'),
            ProcessingQueue.detected_at.label('detected_at'),
            func.row_number().over(
                partition_by=func.coalesce(
                    ProcessingQueue.prescription_id,
                    ProcessingQueue.source_no_resep,
                ),
                order_by=(
                    ProcessingQueue.revision_number.desc(),
                    ProcessingQueue.detected_at.desc(),
                ),
            ).label('position'),
        ).where(
            ProcessingQueue.processing_status == 'COMPLETED',
        ).subquery()
        statement = select(ranked.c.id).where(ranked.c.position == 1)
        if start is not None:
            statement = statement.where(ranked.c.detected_at >= start)
        if end is not None:
            statement = statement.where(ranked.c.detected_at < end)
        return tuple(session.scalars(statement).all())

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float:
        return numerator / denominator * 100 if denominator else 0.0

    @staticmethod
    def _change_percent(current: int, previous: int) -> float | None:
        if previous == 0:
            return None
        return (current - previous) / previous * 100

    @staticmethod
    def _month_start(year: int, month: int) -> datetime:
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        return datetime(year, month, 1)

    @staticmethod
    def _roman(value: int) -> str:
        return ("I", "II", "III", "IV")[value - 1]
