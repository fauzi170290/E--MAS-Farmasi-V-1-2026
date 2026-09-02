from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.config.settings import AppEnvironment, AppSettings
from emss.database.catalog_models import DrugComponentMapping, DrugMaster
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.database.monitoring_models import MonitorEvent
from emss.database.screening_models import (
    Prescription,
    PrescriptionItem,
    PrescriptionRevision,
    Screening,
    ScreeningIssue,
    ScreeningPair,
)
from emss.domain.screening import (
    COMPLETENESS_PRIORITY,
    RISK_PRIORITY,
    HashPrescriptionItem,
    IngredientOccurrence,
    build_ingredient_pairs,
    highest_risk,
    overall_status,
    prescription_hash,
)
from emss.importexport.drug_import import normalize_code, normalize_text
from emss.services.medication_safety import (
    MedicationSafetyService,
    SafetyPrescriptionItem,
)
from emss.utils.time import utc_now
from emss.domain.knowledge import canonical_pair
from emss.domain.kfa import is_kfa_product_code
from emss.services import longitudinal


class ScreeningError(ValueError):
    pass


class ScreeningUnavailableError(ScreeningError):
    pass


@dataclass(frozen=True)
class PrescriptionItemInput:
    source_item_key: str
    khanza_code: str
    display_name: str
    quantity: str = ""
    directions: str = ""
    route: str = ""
    compound_group: str = ""


@dataclass(frozen=True)
class PrescriptionInput:
    no_resep: str
    items: tuple[PrescriptionItemInput, ...]
    patient_id: str = ""
    patient_name: str = ""
    service_unit: str = ""
    prescriber_name: str = ""
    source_changed_at: datetime | None = None
    source_event_id: str = ""
    source_status: str = ""
    source_verified: bool = True


@dataclass(frozen=True)
class ScreeningPairResult:
    pair_key: str
    ingredient_low: str
    ingredient_high: str
    classification: str
    app_severity: str | None
    severity_code: str | None
    clinical_effect: str
    recommendation: str
    monitoring: str
    provenance: dict | None = None


@dataclass(frozen=True)
class ScreeningIssueResult:
    issue_type: str
    message: str
    khanza_code: str = ""
    display_name: str = ""
    pair_key: str = ""
    app_severity: str = ""


@dataclass(frozen=True)
class ScreeningResult:
    screening_id: str
    revision_id: str
    revision_number: int
    prescription_hash: str
    knowledge_base_version: str
    risk_status: str
    completeness_status: str
    overall_status: str
    ingredient_count: int
    pair_count: int
    interaction_count: int
    assessed_no_interaction_count: int
    not_assessed_count: int
    unmapped_drug_count: int
    pairs: tuple[ScreeningPairResult, ...]
    issues: tuple[ScreeningIssueResult, ...]
    is_mock: bool
    reused: bool


@dataclass(frozen=True)
class _MappedItem:
    source: PrescriptionItemInput
    mapping_status: str
    ingredients: tuple[str, ...]


@dataclass(frozen=True)
class _AssessmentPair:
    pair_key: str
    rule_key: str
    ingredient_low: str
    ingredient_high: str
    khanza_codes: tuple[str, str]
    provenance: dict | None = None


class DdiScreeningService:
    ENGINE_VERSION = "2.1.0"
    MOCK_ENVIRONMENTS = frozenset(
        {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}
    )

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        settings: AppSettings,
        medication_safety: MedicationSafetyService,
    ) -> None:
        self.database = database
        self.audit = audit
        self.settings = settings
        self.medication_safety = medication_safety

    def screen(
        self,
        prescription: PrescriptionInput,
        actor_user_id: str,
        *,
        mock_mode: bool = False,
        version_id: str | None = None,
    ) -> ScreeningResult:
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            source_event = session.get(MonitorEvent, prescription.source_event_id) if prescription.source_event_id else None
            cancelled = longitudinal.is_cancelled(source_event)
            if cancelled:
                prescription = replace(prescription, items=(), source_verified=False)
            # The permission to evaluate DRAFT rules is separate from source identity.
            clean = self._validate_input(prescription, mock_mode, allow_empty=cancelled)
            version = self._select_version(session, mock_mode, version_id)
            mapped_items, issues = self._map_items(
                session, clean.items, mock_mode
            )
            if not clean.source_verified:
                issues.append(ScreeningIssueResult(issue_type='DATA_INCOMPLETE',
                    message=('Resep dibatalkan/validasi ditarik. Hasil lama tetap tersimpan; tinjau perubahan terapi.'
                        if cancelled else 'Komposisi akhir sumber belum terverifikasi; hasil bukan konfirmasi tanpa interaksi.')))
            cross_pairs, cross_issues, context_fingerprint = self._cross_pairs(
                session, source_event, clean, mapped_items, mock_mode)
            issues.extend(cross_issues)
            duplicate_issues, duplicate_fingerprint = ([], "") if source_event else self._longitudinal_duplicates(
                session, clean, mapped_items)
            issues.extend(duplicate_issues)
            base_hash = prescription_hash(
                HashPrescriptionItem(
                    khanza_code=item.source.khanza_code,
                    quantity=item.source.quantity,
                    directions=item.source.directions,
                    route=item.source.route,
                    compound_group=item.source.compound_group,
                    active_ingredients=item.ingredients,
                )
                for item in mapped_items
            )
            safety_fingerprint = self.medication_safety.configuration_fingerprint(
                session
            )
            hash_value = hashlib.sha256(
                f"{base_hash}|{safety_fingerprint}|{duplicate_fingerprint}|{context_fingerprint}|{self.ENGINE_VERSION}".encode("utf-8")
            ).hexdigest()
            if clean.source_event_id or not clean.source_verified:
                hash_value = hashlib.sha256(f'{hash_value}|{clean.source_event_id}|{clean.source_verified}'.encode()).hexdigest()

            prescription_row = session.scalar(
                select(Prescription).where(
                    Prescription.source_no_resep == clean.no_resep
                )
            )
            if source_event:
                # Prefer recorded source identity, including pre-0.34.1 local
                # labels. Full source number + adapter may not share a ledger.
                scoped_row = session.scalar(
                    select(Prescription)
                    .join(PrescriptionRevision, PrescriptionRevision.prescription_id == Prescription.id)
                    .join(Screening, Screening.revision_id == PrescriptionRevision.id)
                    .join(MonitorEvent, MonitorEvent.screening_id == Screening.id)
                    .where(MonitorEvent.adapter_code == source_event.adapter_code,
                        MonitorEvent.no_resep == source_event.no_resep)
                    .order_by(PrescriptionRevision.revision_number.desc()).limit(1)
                )
                if scoped_row is not None:
                    prescription_row = scoped_row
                elif prescription_row is not None:
                    other_adapter = session.scalar(select(MonitorEvent.adapter_code)
                        .join(Screening, MonitorEvent.screening_id == Screening.id)
                        .join(PrescriptionRevision, Screening.revision_id == PrescriptionRevision.id)
                        .where(PrescriptionRevision.prescription_id == prescription_row.id,
                            MonitorEvent.adapter_code != source_event.adapter_code).limit(1))
                    if other_adapter:
                        prescription_row = None
            stored_number = clean.no_resep
            if prescription_row is None and session.scalar(select(Prescription.id).where(
                    Prescription.source_no_resep == stored_number)):
                stored_number = "SRC:" + hashlib.sha256(f"{source_event.adapter_code}|{source_event.no_resep}".encode()).hexdigest()
            if prescription_row is None:
                prescription_row = Prescription(
                    source_no_resep=stored_number,
                    patient_id=clean.patient_id or None,
                    patient_name=clean.patient_name or None,
                    service_unit=clean.service_unit or None,
                    prescriber_name=clean.prescriber_name or None,
                    is_mock=mock_mode,
                )
                session.add(prescription_row)
                session.flush()
            elif prescription_row.is_mock != mock_mode:
                raise ScreeningError(
                    "Nomor resep sudah digunakan pada mode yang berbeda"
                )

            existing = session.scalar(
                select(PrescriptionRevision)
                .options(
                    selectinload(PrescriptionRevision.screening).selectinload(
                        Screening.pairs
                    ),
                    selectinload(PrescriptionRevision.screening).selectinload(
                        Screening.issues
                    ),
                )
                .where(
                    PrescriptionRevision.prescription_id == prescription_row.id,
                    PrescriptionRevision.prescription_hash == hash_value,
                    PrescriptionRevision.knowledge_base_version_id == version.id,
                    PrescriptionRevision.is_mock.is_(mock_mode),
                )
            )
            if existing is not None and existing.screening is not None:
                if source_event is not None:
                    source_event.screening_id = existing.screening.id
                result = self._to_result(
                    existing, existing.screening, version.version_code, True
                )
                self.audit.append(
                    session,
                    AuditEvent(
                        category="CLINICAL_SCREENING",
                        action="DDI_SCREENING_REUSED",
                        outcome="SUCCESS",
                        actor_user_id=actor_user_id,
                        entity_type="screening",
                        entity_id=existing.screening.id,
                        details={
                            "no_resep": clean.no_resep,
                            "prescription_hash": hash_value,
                            "knowledge_base_version": version.version_code,
                            "revision_number": existing.revision_number,
                            "is_mock": mock_mode,
                        },
                    ),
                )
                session.commit()
                return result

            revision_number = (
                session.scalar(
                    select(func.max(PrescriptionRevision.revision_number)).where(
                        PrescriptionRevision.prescription_id
                        == prescription_row.id
                    )
                )
                or 0
            ) + 1
            prescription_row.patient_id = clean.patient_id or None
            prescription_row.patient_name = clean.patient_name or None
            prescription_row.service_unit = clean.service_unit or None
            prescription_row.prescriber_name = clean.prescriber_name or None
            prescription_row.updated_at = utc_now()

            revision = PrescriptionRevision(
                prescription_id=prescription_row.id,
                revision_number=revision_number,
                prescription_hash=hash_value,
                knowledge_base_version_id=version.id,
                is_mock=mock_mode,
                source_changed_at=clean.source_changed_at,
            )
            session.add(revision)
            session.flush()
            for item in mapped_items:
                session.add(
                    PrescriptionItem(
                        revision_id=revision.id,
                        source_item_key=item.source.source_item_key,
                        khanza_code=item.source.khanza_code,
                        display_name=item.source.display_name,
                        quantity=item.source.quantity or None,
                        directions=item.source.directions or None,
                        route=item.source.route or None,
                        compound_group=item.source.compound_group or None,
                        mapping_status=item.mapping_status,
                        active_ingredients_json=json.dumps(
                            item.ingredients, ensure_ascii=False
                        ),
                    )
                )

            screening = self._execute(
                session, revision, version, mapped_items, issues, mock_mode, cross_pairs
            )
            if source_event is not None:
                source_event.screening_id = screening.id
            self.audit.append(
                session,
                AuditEvent(
                    category="CLINICAL_SCREENING",
                    action="DDI_SCREENING_COMPLETED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="screening",
                    entity_id=screening.id,
                    details={
                        "no_resep": clean.no_resep,
                        "prescription_hash": hash_value,
                        "knowledge_base_version": version.version_code,
                        "revision_number": revision_number,
                        "risk_status": screening.risk_status,
                        "completeness_status": screening.completeness_status,
                        "is_mock": mock_mode,
                    },
                ),
            )
            session.commit()
            return self._to_result(
                revision, screening, version.version_code, False
            )

    def _cross_pairs(self, session, event, clean, mapped_items, mock_mode):
        if event is None or not clean.source_verified or clean.source_status not in longitudinal.FINAL_STATUSES:
            return (), [], ""
        candidates, warnings, source_state = longitudinal.contexts(session, event, clean.patient_id, mock_mode)
        issues = [ScreeningIssueResult(issue_type="DATA_INCOMPLETE", message=text) for text in warnings]
        pairs, fingerprint_rows = [], []
        current_source = longitudinal.provenance(event, longitudinal.snapshot(event))
        for candidate in candidates:
            previous, payload = candidate.event, candidate.payload
            try:
                source_items = tuple(PrescriptionItemInput(**row) for row in
                    payload.get("regular_items", []) + payload.get("compounded_items", []))
                prior_input = self._validate_input(PrescriptionInput(previous.no_resep, source_items), False)
            except (TypeError, ValueError):
                issues.append(ScreeningIssueResult(issue_type="DATA_INCOMPLETE",
                    message=f"Item resep {previous.no_resep} tidak lengkap; perlu rekonsiliasi."))
                continue
            prior_items, prior_issues = self._map_items(session, prior_input.items, mock_mode)
            for issue in prior_issues:
                issues.append(ScreeningIssueResult(issue_type=issue.issue_type, khanza_code=issue.khanza_code,
                    display_name=issue.display_name, message=f"Resep {previous.no_resep}: {issue.message}"))
            prior_screening = session.get(Screening, previous.screening_id) if previous.screening_id else None
            prior_revision = session.get(PrescriptionRevision, prior_screening.revision_id) if prior_screening else None
            prior_source = longitudinal.provenance(previous, payload,
                prior_revision.id if prior_revision else "", prior_revision.revision_number if prior_revision else None)
            # Source fingerprint + current mappings; no recursive screening hashes.
            fingerprint_rows.append({"event": previous.id, "source": previous.fingerprint,
                "mapping": [asdict(item) for item in prior_items]})
            grouped, duplicate_ingredients = {}, set()
            for left in mapped_items:
                for right in prior_items:
                    for a in left.ingredients:
                        for b in right.ingredients:
                            if a == b:
                                duplicate_ingredients.add(a)
                                continue
                            low, high, key = canonical_pair(a, b)
                            metadata = grouped.setdefault(key, {"format": "cross_rx_v1",
                                "policy": longitudinal.POLICY, "use_status": "UNKNOWN_RECONCILIATION_REQUIRED",
                                "current": dict(current_source), "previous": prior_source,
                                "occurrences": []})
                            metadata["occurrences"].append({"current": asdict(left.source),
                                "current_ingredient": a, "previous": asdict(right.source), "previous_ingredient": b})
            if grouped or duplicate_ingredients:
                issues.append(ScreeningIssueResult(issue_type="CROSS_RX_CONTEXT", app_severity="REVIEW",
                    message=f"Konteks lintas resep {event.no_resep} vs {previous.no_resep}. "
                    "Riwayat merupakan kandidat potensi interaksi, bukan bukti obat masih digunakan. "
                    "Konfirmasi penggunaan aktual dan rekonsiliasi dengan pasien/dokter."))
            if duplicate_ingredients:
                issues.append(ScreeningIssueResult(issue_type="DUPLICATE_THERAPY", app_severity="REVIEW",
                    pair_key=" + ".join(sorted(duplicate_ingredients)),
                    message=f"Kandungan sama pada resep {event.no_resep} dan {previous.no_resep}: "
                    f"{', '.join(sorted(duplicate_ingredients))}. Pastikan obat masih digunakan dan pemberian ulang diperlukan."))
            for key, metadata in sorted(grouped.items()):
                low, high = key.split(" || ", 1)
                occurrence = metadata["occurrences"][0]
                pairs.append(_AssessmentPair(longitudinal.storage_key(key, previous.no_resep), key,
                    low, high, (occurrence["current"]["khanza_code"], occurrence["previous"]["khanza_code"]), metadata))
        fingerprint = json.dumps({"policy": longitudinal.POLICY, "contexts": fingerprint_rows,
            "source_state": source_state, "warnings": warnings}, sort_keys=True, ensure_ascii=False)
        return tuple(pairs), issues, fingerprint

    def _longitudinal_duplicates(
        self,
        session: Session,
        prescription: PrescriptionInput,
        mapped_items: tuple[_MappedItem, ...],
    ) -> tuple[list[ScreeningIssueResult], str]:
        """Compare a final prescription with recent final history already in E-MAS.

        This deliberately performs no extra Khanza query. It is a reconciliation
        signal, not a claim that duplicate therapy is clinically erroneous.
        """
        if (
            not prescription.patient_id
            or not prescription.source_verified
            or prescription.source_status not in {'DIPROSES_FARMASI', 'DISERAHKAN'}
        ):
            return [], ''
        current_ingredients = {
            ingredient for item in mapped_items for ingredient in item.ingredients
        }
        if not current_ingredients:
            return [], ''
        upper = prescription.source_changed_at or utc_now()
        day_bounds = longitudinal.local_day_bounds(upper)
        if day_bounds is None:
            return [], ''
        lower, day_end = day_bounds
        source_event = session.get(MonitorEvent, prescription.source_event_id) if prescription.source_event_id else None
        rows = session.execute(
            select(
                MonitorEvent.no_resep,
                Prescription.service_unit,
                PrescriptionRevision.id,
                PrescriptionRevision.source_changed_at,
                PrescriptionItem.active_ingredients_json,
            )
            .join(PrescriptionRevision, PrescriptionRevision.prescription_id == Prescription.id)
            .join(PrescriptionItem, PrescriptionItem.revision_id == PrescriptionRevision.id)
            .join(Screening, Screening.revision_id == PrescriptionRevision.id)
            .join(MonitorEvent, MonitorEvent.screening_id == Screening.id)
            .where(
                Prescription.patient_id == prescription.patient_id,
                Prescription.source_no_resep != prescription.no_resep,
                MonitorEvent.no_resep != (source_event.no_resep if source_event else prescription.no_resep),
                MonitorEvent.adapter_code == source_event.adapter_code if source_event else True,
                MonitorEvent.source_status.in_({'DIPROSES_FARMASI', 'DISERAHKAN'}),
                PrescriptionRevision.source_changed_at.is_not(None),
                PrescriptionRevision.source_changed_at >= lower,
                PrescriptionRevision.source_changed_at < day_end,
                PrescriptionRevision.source_changed_at <= upper,
            )
            .order_by(
                PrescriptionRevision.source_changed_at.desc(),
                PrescriptionRevision.revision_number.desc(),
            )
            .limit(500)
        ).all()
        latest_revision: dict[str, str] = {}
        matches: dict[str, set[str]] = {}
        units: dict[str, str] = {}
        for no_resep, service_unit, revision_id, _changed_at, raw_ingredients in rows:
            selected = latest_revision.setdefault(no_resep, revision_id)
            if selected != revision_id:
                continue
            try:
                ingredients = set(json.loads(raw_ingredients or '[]'))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            overlap = current_ingredients.intersection(ingredients)
            if overlap:
                matches.setdefault(no_resep, set()).update(overlap)
                units[no_resep] = service_unit or '-'
        issues = []
        fingerprint_rows = []
        for no_resep in sorted(matches):
            ingredients = sorted(matches[no_resep])
            fingerprint_rows.append(f"{no_resep}:{','.join(ingredients)}")
            issues.append(ScreeningIssueResult(
                issue_type='DUPLICATE_THERAPY',
                pair_key=' + '.join(ingredients),
                app_severity='REVIEW',
                message=(
                    "Obat dengan kandungan yang sama tercatat pada resep sebelumnya. "
                    "Pastikan apakah obat tersebut masih digunakan dan apakah pemberian ulang diperlukan.\n"
                    f"Obat/kandungan: {', '.join(ingredients)} · Resep sebelumnya: {no_resep} · Poli: {units[no_resep]}"
                ),
            ))
        return issues, '|'.join(fingerprint_rows)

    def _execute(
        self,
        session: Session,
        revision: PrescriptionRevision,
        version: KnowledgeBaseVersion,
        mapped_items: tuple[_MappedItem, ...],
        issue_rows: list[ScreeningIssueResult],
        mock_mode: bool,
        cross_pairs: tuple[_AssessmentPair, ...] = (),
    ) -> Screening:
        started_at = utc_now()
        occurrences = [
            IngredientOccurrence(
                source_item_key=item.source.source_item_key,
                khanza_code=item.source.khanza_code,
                ingredient_name=ingredient,
                compound_group=item.source.compound_group,
            )
            for item in mapped_items
            for ingredient in item.ingredients
        ]
        ingredient_pairs = tuple(_AssessmentPair(pair.pair_key, pair.pair_key, pair.ingredient_low,
            pair.ingredient_high, pair.khanza_codes) for pair in build_ingredient_pairs(occurrences)) + cross_pairs
        for pair in cross_pairs:
            pair.provenance["current"].update(revision_id=revision.id, revision_number=revision.revision_number)
        safety_findings = self.medication_safety.evaluate(
            session,
            tuple(
                SafetyPrescriptionItem(
                    source_item_key=item.source.source_item_key,
                    khanza_code=item.source.khanza_code,
                    display_name=item.source.display_name,
                    route=item.source.route,
                    compound_group=item.source.compound_group,
                    ingredients=item.ingredients,
                )
                for item in mapped_items
            ),
            revision.prescription.service_unit or "",
        )
        for finding in safety_findings:
            issue_rows.append(
                ScreeningIssueResult(
                    issue_type=finding.issue_type,
                    pair_key=finding.reference,
                    khanza_code=finding.khanza_code,
                    display_name=finding.display_name,
                    message=finding.message,
                    app_severity=finding.app_severity,
                )
            )
        pair_keys = [pair.rule_key for pair in ingredient_pairs]
        rules = (
            session.scalars(
                select(DdiRule).where(
                    DdiRule.knowledge_base_version_id == version.id,
                    DdiRule.pair_key.in_(pair_keys),
                )
            ).all()
            if pair_keys
            else []
        )
        rules_by_key = {rule.pair_key: rule for rule in rules}

        pair_payloads: list[tuple[object, DdiRule | None, str]] = []
        risk_values: list[str] = [
            finding.app_severity for finding in safety_findings
        ] + [issue.app_severity for issue in issue_rows if issue.app_severity]
        assessed_count = interaction_count = not_assessed_count = 0
        for pair in ingredient_pairs:
            rule = rules_by_key.get(pair.rule_key)
            classification = self._classification(rule, mock_mode)
            if classification == "INTERACTION_FOUND":
                interaction_count += 1
                risk_values.append(rule.app_severity or "REVIEW")  # type: ignore[union-attr]
            elif classification == "ASSESSED_NO_INTERACTION":
                assessed_count += 1
            else:
                not_assessed_count += 1
                issue_rows.append(
                    ScreeningIssueResult(
                        issue_type="PAIR_NOT_ASSESSED",
                        pair_key=pair.rule_key,
                        message=(
                            "Pasangan belum memiliki penilaian eksplisit yang "
                            "dapat digunakan; hasil bukan berarti aman."
                        ),
                    )
                )
            pair_payloads.append((pair, rule, classification))

        completeness = "COMPLETE"
        issue_types = {issue.issue_type for issue in issue_rows}
        for candidate, issue_type in (
            ("NOT_ASSESSED", "PAIR_NOT_ASSESSED"),
            ("UNMAPPED", "DRUG_UNMAPPED"),
            ("INCOMPLETE", "DATA_INCOMPLETE"),
            ("ERROR", "ENGINE_ERROR"),
        ):
            if (
                issue_type in issue_types
                and COMPLETENESS_PRIORITY[candidate]
                > COMPLETENESS_PRIORITY[completeness]
            ):
                completeness = candidate
        risk = highest_risk(risk_values)
        screening = Screening(
            revision_id=revision.id,
            knowledge_base_version_id=version.id,
            risk_status=risk,
            completeness_status=completeness,
            overall_status=overall_status(risk, completeness),
            highest_severity_rank=RISK_PRIORITY[risk],
            ingredient_count=len({item.ingredient_name for item in occurrences}),
            pair_count=len(ingredient_pairs),
            interaction_count=interaction_count,
            assessed_no_interaction_count=assessed_count,
            not_assessed_count=not_assessed_count,
            unmapped_drug_count=sum(
                issue.issue_type == "DRUG_UNMAPPED" for issue in issue_rows
            ),
            is_mock=mock_mode,
            engine_version=self.ENGINE_VERSION,
            started_at=started_at,
            completed_at=utc_now(),
        )
        session.add(screening)
        session.flush()
        for pair, rule, classification in pair_payloads:
            session.add(
                ScreeningPair(
                    screening_id=screening.id,
                    pair_key=pair.pair_key,
                    ingredient_low=pair.ingredient_low,
                    ingredient_high=pair.ingredient_high,
                    khanza_codes_json=json.dumps(pair.provenance or pair.khanza_codes, ensure_ascii=False),
                    classification=classification,
                    ddi_rule_id=rule.id if rule else None,
                    severity_code=rule.severity_code if rule else None,
                    severity_rank=rule.severity_rank if rule else 0,
                    app_severity=rule.app_severity if rule else None,
                    clinical_effect=rule.clinical_effect if rule else None,
                    recommendation=rule.recommendation if rule else None,
                    monitoring=rule.monitoring if rule else None,
                    source_validation_status=(
                        rule.source_validation_status if rule else None
                    ),
                )
            )
        for issue in issue_rows:
            session.add(
                ScreeningIssue(
                    screening_id=screening.id,
                    issue_type=issue.issue_type,
                    khanza_code=issue.khanza_code or None,
                    display_name=issue.display_name or None,
                    pair_key=issue.pair_key or None,
                    app_severity=issue.app_severity or None,
                    message=issue.message,
                )
            )
        session.flush()
        session.refresh(screening, attribute_names=["pairs", "issues"])
        return screening

    @staticmethod
    def _classification(rule: DdiRule | None, mock_mode: bool) -> str:
        if rule is None:
            return "PAIR_NOT_ASSESSED"
        if rule.activation_status == "INACTIVE":
            return "PAIR_NOT_ASSESSED"
        usable = mock_mode or (
            rule.is_enabled
            and rule.record_status == "PUBLISHED"
            and rule.activation_status == "ACTIVE"
        )
        if not usable:
            return "PAIR_NOT_ASSESSED"
        if rule.interaction_status == "INTERACTION_FOUND":
            return "INTERACTION_FOUND"
        if (
            rule.interaction_status == "ASSESSED_NO_INTERACTION"
            and rule.source_validation_status
            != "NO_INTERACTION_QUICK_CLOSURE"
        ):
            return "ASSESSED_NO_INTERACTION"
        return "PAIR_NOT_ASSESSED"

    def _map_items(
        self,
        session: Session,
        items: tuple[PrescriptionItemInput, ...],
        mock_mode: bool,
    ) -> tuple[tuple[_MappedItem, ...], list[ScreeningIssueResult]]:
        codes = {item.khanza_code for item in items}
        kfa_codes = {code for code in codes if is_kfa_product_code(code)}
        drugs = session.scalars(
            select(DrugMaster)
            .options(
                selectinload(DrugMaster.components).selectinload(
                    DrugComponentMapping.ingredient
                )
            )
            .where(
                or_(
                    DrugMaster.khanza_code.in_(codes),
                    DrugMaster.kfa_product_code.in_(kfa_codes) if kfa_codes else False,
                ),
                DrugMaster.is_active.is_(True),
            )
        ).all()
        by_code = {drug.khanza_code: drug for drug in drugs}
        kfa_matches: dict[str, list[DrugMaster]] = {}
        for drug in drugs:
            if drug.kfa_product_code:
                kfa_matches.setdefault(drug.kfa_product_code, []).append(drug)
        ambiguous_kfa: set[str] = set()
        for kfa_code, matches in kfa_matches.items():
            signatures = {
                tuple(sorted(mapping.ingredient_id for mapping in drug.components
                    if mock_mode or (mapping.is_active and mapping.review_status == "APPROVED")))
                for drug in matches
            }
            if len(signatures) == 1:
                by_code[kfa_code] = sorted(matches, key=lambda row: row.khanza_code)[0]
            else:
                ambiguous_kfa.add(kfa_code)
        result: list[_MappedItem] = []
        issues: list[ScreeningIssueResult] = []
        for item in items:
            if item.khanza_code in ambiguous_kfa:
                result.append(_MappedItem(item, "DATA_INCOMPLETE", ()))
                issues.append(ScreeningIssueResult(
                    issue_type="DATA_INCOMPLETE", khanza_code=item.khanza_code,
                    display_name=item.display_name,
                    message="Kode produk KFA memiliki pemetaan kandungan yang bertentangan; tinjau Master Obat.",
                ))
                continue
            drug = by_code.get(item.khanza_code)
            if drug is None:
                result.append(_MappedItem(item, "UNMAPPED", ()))
                issues.append(
                    ScreeningIssueResult(
                        issue_type="DRUG_UNMAPPED",
                        khanza_code=item.khanza_code,
                        display_name=item.display_name,
                        message="Kode obat belum dipetakan ke zat aktif.",
                    )
                )
                continue
            components = [
                mapping
                for mapping in sorted(
                    drug.components, key=lambda value: value.component_order
                )
                if mock_mode
                or (
                    mapping.is_active
                    and mapping.review_status == "APPROVED"
                    and drug.review_status == "APPROVED"
                )
            ]
            ingredient_names = tuple(
                mapping.ingredient.standard_name
                for mapping in components
                if mapping.ingredient and mapping.ingredient.is_active
            )
            if not ingredient_names:
                issue_type = (
                    "DRUG_UNMAPPED"
                    if drug.source_mapping_status == "UNMAPPED"
                    or (not mock_mode and drug.review_status != "APPROVED")
                    else "DATA_INCOMPLETE"
                )
                result.append(_MappedItem(item, issue_type, ()))
                issues.append(
                    ScreeningIssueResult(
                        issue_type=issue_type,
                        khanza_code=item.khanza_code,
                        display_name=item.display_name,
                        message=(
                            "Mapping zat aktif belum tersedia/disetujui."
                            if issue_type == "DRUG_UNMAPPED"
                            else "Komponen zat aktif tidak lengkap atau belum aktif."
                        ),
                    )
                )
                continue
            incomplete = (
                drug.source_mapping_status != "MAPPED"
                or len(ingredient_names) < drug.component_count
            )
            result.append(
                _MappedItem(
                    item,
                    "DATA_INCOMPLETE" if incomplete else "MAPPED",
                    ingredient_names,
                )
            )
            if incomplete:
                issues.append(
                    ScreeningIssueResult(
                        issue_type="DATA_INCOMPLETE",
                        khanza_code=item.khanza_code,
                        display_name=item.display_name,
                        message=(
                            "Mapping obat hanya sebagian; pasangan yang "
                            "terbentuk tidak mewakili seluruh komponen."
                        ),
                    )
                )
        return tuple(result), issues

    def _select_version(
        self, session: Session, mock_mode: bool, version_id: str | None
    ) -> KnowledgeBaseVersion:
        if mock_mode and self.settings.environment not in self.MOCK_ENVIRONMENTS:
            raise ScreeningUnavailableError(
                "Mode MOCK hanya diizinkan pada environment development/test"
            )
        statement = select(KnowledgeBaseVersion)
        if version_id:
            statement = statement.where(KnowledgeBaseVersion.id == version_id)
        elif mock_mode:
            statement = statement.where(
                KnowledgeBaseVersion.status.in_(("DRAFT", "PUBLISHED"))
            ).order_by(KnowledgeBaseVersion.created_at.desc())
        else:
            statement = statement.where(
                KnowledgeBaseVersion.status == "PUBLISHED"
            ).order_by(KnowledgeBaseVersion.published_at.desc())
        version = session.scalar(statement.limit(1))
        if version is None:
            raise ScreeningUnavailableError(
                "Knowledge base yang sesuai belum tersedia"
            )
        if mock_mode:
            if version.status not in {"DRAFT", "PUBLISHED"}:
                raise ScreeningUnavailableError(
                    "Mode MOCK hanya dapat memakai knowledge base DRAFT/PUBLISHED"
                )
        elif version.status != "PUBLISHED":
            raise ScreeningUnavailableError(
                "Skrining klinis hanya dapat memakai knowledge base PUBLISHED"
            )
        return version

    @staticmethod
    def _validate_input(
        value: PrescriptionInput, mock_mode: bool, *, allow_empty: bool = False
    ) -> PrescriptionInput:
        no_resep = normalize_text(value.no_resep)
        if not no_resep:
            raise ScreeningError("Nomor resep wajib diisi")
        if mock_mode and not no_resep.startswith("MOCK-"):
            no_resep = f"MOCK-{no_resep}"
        if not value.items and not allow_empty:
            raise ScreeningError("Resep minimal memiliki satu item")
        seen: set[str] = set()
        clean_items: list[PrescriptionItemInput] = []
        for index, item in enumerate(value.items, start=1):
            key = normalize_text(item.source_item_key) or str(index)
            if key in seen:
                raise ScreeningError(f"source_item_key duplikat: {key}")
            seen.add(key)
            code = normalize_code(item.khanza_code)
            if not code:
                raise ScreeningError(f"Kode obat item {key} wajib diisi")
            clean_items.append(
                PrescriptionItemInput(
                    source_item_key=key,
                    khanza_code=code,
                    display_name=normalize_text(item.display_name) or code,
                    quantity=normalize_text(item.quantity),
                    directions=normalize_text(item.directions),
                    route=normalize_text(item.route),
                    compound_group=normalize_text(item.compound_group),
                )
            )
        return PrescriptionInput(
            no_resep=no_resep,
            items=tuple(clean_items),
            patient_id=normalize_text(value.patient_id),
            patient_name=normalize_text(value.patient_name),
            service_unit=normalize_text(value.service_unit),
            prescriber_name=normalize_text(value.prescriber_name),
            source_changed_at=value.source_changed_at,
            source_event_id=value.source_event_id,
            source_status=value.source_status,
            source_verified=value.source_verified,
        )

    @staticmethod
    def _to_result(
        revision: PrescriptionRevision,
        screening: Screening,
        version_code: str,
        reused: bool,
    ) -> ScreeningResult:
        return ScreeningResult(
            screening_id=screening.id,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            prescription_hash=revision.prescription_hash,
            knowledge_base_version=version_code,
            risk_status=screening.risk_status,
            completeness_status=screening.completeness_status,
            overall_status=screening.overall_status,
            ingredient_count=screening.ingredient_count,
            pair_count=screening.pair_count,
            interaction_count=screening.interaction_count,
            assessed_no_interaction_count=(
                screening.assessed_no_interaction_count
            ),
            not_assessed_count=screening.not_assessed_count,
            unmapped_drug_count=screening.unmapped_drug_count,
            pairs=tuple(
                ScreeningPairResult(
                    pair_key=f"{row.ingredient_low} || {row.ingredient_high}",
                    ingredient_low=row.ingredient_low,
                    ingredient_high=row.ingredient_high,
                    classification=row.classification,
                    app_severity=row.app_severity,
                    severity_code=row.severity_code,
                    clinical_effect=row.clinical_effect or "",
                    recommendation=row.recommendation or "",
                    monitoring=row.monitoring or "",
                    provenance=longitudinal.decode_provenance(row.khanza_codes_json),
                )
                for row in sorted(screening.pairs, key=lambda value: value.pair_key)
            ),
            issues=tuple(
                ScreeningIssueResult(
                    issue_type=row.issue_type,
                    message=row.message,
                    khanza_code=row.khanza_code or "",
                    display_name=row.display_name or "",
                    pair_key=row.pair_key or "",
                    app_severity=row.app_severity or "",
                )
                for row in sorted(
                    screening.issues,
                    key=lambda value: (
                        value.issue_type,
                        value.khanza_code or "",
                        value.pair_key or "",
                    ),
                )
            ),
            is_mock=screening.is_mock,
            reused=reused,
        )
