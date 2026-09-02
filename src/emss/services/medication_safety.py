from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import ActiveIngredient, DrugMaster
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole
from emss.database.safety_models import (
    HighAlertMedication,
    IngredientTherapyProfile,
    LasaPair,
    MedicationSafetyPolicy,
)
from emss.domain.screening import RISK_PRIORITY
from emss.importexport.drug_import import normalize_code, normalize_name, normalize_text
from emss.utils.time import utc_now


class MedicationSafetyError(ValueError):
    pass


class MedicationSafetyPermissionError(PermissionError):
    pass


@dataclass(frozen=True)
class SafetyPrescriptionItem:
    source_item_key: str
    khanza_code: str
    display_name: str
    route: str
    compound_group: str
    ingredients: tuple[str, ...]


@dataclass(frozen=True)
class SafetyFinding:
    issue_type: str
    app_severity: str
    message: str
    reference: str = ""
    khanza_code: str = ""
    display_name: str = ""


@dataclass(frozen=True)
class SafetyPolicyView:
    polypharmacy_threshold: int
    hyperpolypharmacy_threshold: int
    is_active: bool


@dataclass(frozen=True)
class TherapyProfileView:
    ingredient_name: str
    therapeutic_class: str
    therapeutic_subclass: str
    atc_code: str
    route_context: str
    source: str
    is_active: bool


@dataclass(frozen=True)
class HighAlertView:
    drug_code: str
    drug_name: str
    category: str
    unit_scope: str
    app_severity: str
    requires_double_check: bool
    recommendation: str
    is_active: bool


@dataclass(frozen=True)
class LasaPairView:
    drug_code_a: str
    drug_name_a: str
    drug_code_b: str
    drug_name_b: str
    lasa_type: str
    unit_scope: str
    app_severity: str
    requires_double_check: bool
    recommendation: str
    is_active: bool


class MedicationSafetyService:
    WRITER_ROLES = frozenset(
        {"SUPER_ADMIN", "KNOWLEDGE_ADMIN", "CLINICAL_REVIEWER", "KFT"}
    )
    SEVERITIES = frozenset({"INFO", "REVIEW", "HIGH_RISK"})
    LASA_TYPES = frozenset(
        {
            "LOOK_ALIKE",
            "SOUND_ALIKE",
            "PACKAGING_SIMILAR",
            "STRENGTH_SIMILAR",
            "GENERIC_NAME_SIMILAR",
            "BRAND_NAME_SIMILAR",
        }
    )

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def get_policy(self) -> SafetyPolicyView:
        with self.database.session() as session:
            row = self._policy(session)
            return SafetyPolicyView(
                row.polypharmacy_threshold,
                row.hyperpolypharmacy_threshold,
                row.is_active,
            )

    def update_policy(
        self,
        actor_user_id: str,
        polypharmacy_threshold: int,
        hyperpolypharmacy_threshold: int,
        is_active: bool = True,
    ) -> SafetyPolicyView:
        if not 2 <= polypharmacy_threshold < hyperpolypharmacy_threshold <= 50:
            raise MedicationSafetyError(
                "Ambang harus 2-49 dan ambang hiperpolifarmasi harus lebih besar"
            )
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            row = self._policy(session)
            row.polypharmacy_threshold = polypharmacy_threshold
            row.hyperpolypharmacy_threshold = hyperpolypharmacy_threshold
            row.is_active = is_active
            row.validated_by = actor_user_id
            row.validated_at = utc_now()
            row.updated_at = utc_now()
            self._audit(session, "SAFETY_POLICY_UPDATED", actor_user_id, "POLICY", "1")
            session.commit()
        return self.get_policy()

    def list_therapy_profiles(self) -> tuple[TherapyProfileView, ...]:
        with self.database.session() as session:
            rows = session.execute(
                select(IngredientTherapyProfile, ActiveIngredient)
                .join(ActiveIngredient, ActiveIngredient.id == IngredientTherapyProfile.ingredient_id)
                .order_by(ActiveIngredient.standard_name)
            ).all()
            return tuple(
                TherapyProfileView(
                    ingredient.standard_name,
                    profile.therapeutic_class,
                    profile.therapeutic_subclass or "",
                    profile.atc_code or "",
                    profile.route_context or "",
                    profile.source or "",
                    profile.is_active,
                )
                for profile, ingredient in rows
            )

    def upsert_therapy_profile(
        self,
        actor_user_id: str,
        ingredient_name: str,
        therapeutic_class: str,
        *,
        therapeutic_subclass: str = "",
        atc_code: str = "",
        route_context: str = "",
        source: str = "",
        is_active: bool = True,
    ) -> None:
        ingredient_key = normalize_name(ingredient_name)
        class_name = normalize_text(therapeutic_class)
        if not ingredient_key or not class_name:
            raise MedicationSafetyError("Zat aktif dan kelas terapi wajib diisi")
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            ingredient = session.scalar(select(ActiveIngredient).where(ActiveIngredient.normalized_name == ingredient_key))
            if ingredient is None:
                raise MedicationSafetyError("Zat aktif tidak ditemukan pada master obat")
            row = session.scalar(select(IngredientTherapyProfile).where(IngredientTherapyProfile.ingredient_id == ingredient.id))
            if row is None:
                row = IngredientTherapyProfile(ingredient_id=ingredient.id, therapeutic_class=class_name)
                session.add(row)
            row.therapeutic_class = class_name
            row.therapeutic_subclass = normalize_text(therapeutic_subclass) or None
            row.atc_code = normalize_text(atc_code).upper() or None
            row.route_context = normalize_name(route_context) or None
            row.source = normalize_text(source) or None
            row.is_active = is_active
            row.validated_by = actor_user_id
            row.validated_at = utc_now()
            row.updated_at = utc_now()
            session.flush()
            self._audit(session, "THERAPY_PROFILE_UPSERTED", actor_user_id, "INGREDIENT_THERAPY_PROFILE", row.id)
            session.commit()

    def list_high_alerts(self) -> tuple[HighAlertView, ...]:
        with self.database.session() as session:
            rows = session.execute(
                select(HighAlertMedication, DrugMaster)
                .join(DrugMaster, DrugMaster.id == HighAlertMedication.drug_id)
                .order_by(DrugMaster.display_name, HighAlertMedication.unit_scope)
            ).all()
            return tuple(
                HighAlertView(
                    drug.khanza_code, drug.display_name, row.category,
                    row.unit_scope, row.app_severity, row.requires_double_check,
                    row.recommendation, row.is_active,
                )
                for row, drug in rows
            )

    def upsert_high_alert(
        self,
        actor_user_id: str,
        drug_code: str,
        category: str,
        recommendation: str,
        *,
        unit_scope: str = "*",
        app_severity: str = "REVIEW",
        requires_double_check: bool = True,
        source: str = "",
        is_active: bool = True,
    ) -> None:
        severity = self._severity(app_severity)
        code = normalize_code(drug_code)
        category = normalize_text(category)
        recommendation = normalize_text(recommendation)
        unit = normalize_text(unit_scope) or "*"
        if not code or not category or not recommendation:
            raise MedicationSafetyError("Kode obat, kategori, dan rekomendasi wajib diisi")
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            drug = session.scalar(select(DrugMaster).where(DrugMaster.khanza_code == code, DrugMaster.is_active.is_(True)))
            if drug is None:
                raise MedicationSafetyError("Kode obat tidak ditemukan pada master")
            row = session.scalar(select(HighAlertMedication).where(HighAlertMedication.drug_id == drug.id, HighAlertMedication.unit_scope == unit))
            if row is None:
                row = HighAlertMedication(drug_id=drug.id, category=category, unit_scope=unit, recommendation=recommendation, approved_at=utc_now())
                session.add(row)
            row.category = category
            row.app_severity = severity
            row.requires_double_check = requires_double_check
            row.recommendation = recommendation
            row.source = normalize_text(source) or None
            row.is_active = is_active
            row.validated_by = actor_user_id
            row.approved_at = utc_now()
            row.updated_at = utc_now()
            session.flush()
            self._audit(session, "HIGH_ALERT_UPSERTED", actor_user_id, "HIGH_ALERT_MEDICATION", row.id)
            session.commit()

    def list_lasa_pairs(self) -> tuple[LasaPairView, ...]:
        low = aliased(DrugMaster)
        high = aliased(DrugMaster)
        with self.database.session() as session:
            rows = session.execute(
                select(LasaPair, low, high)
                .join(low, low.id == LasaPair.drug_low_id)
                .join(high, high.id == LasaPair.drug_high_id)
                .order_by(low.display_name, high.display_name, LasaPair.lasa_type)
            ).all()
            return tuple(
                LasaPairView(
                    a.khanza_code, a.display_name, b.khanza_code, b.display_name,
                    row.lasa_type, row.unit_scope, row.app_severity,
                    row.requires_double_check, row.recommendation, row.is_active,
                )
                for row, a, b in rows
            )

    def upsert_lasa_pair(
        self,
        actor_user_id: str,
        drug_code_a: str,
        drug_code_b: str,
        lasa_type: str,
        recommendation: str,
        *,
        unit_scope: str = "*",
        app_severity: str = "REVIEW",
        requires_double_check: bool = True,
        source: str = "",
        is_active: bool = True,
    ) -> None:
        severity = self._severity(app_severity)
        code_a, code_b = normalize_code(drug_code_a), normalize_code(drug_code_b)
        kind = normalize_text(lasa_type).upper().replace(" ", "_")
        recommendation = normalize_text(recommendation)
        unit = normalize_text(unit_scope) or "*"
        if not code_a or not code_b or code_a == code_b:
            raise MedicationSafetyError("Dua kode obat LASA yang berbeda wajib diisi")
        if kind not in self.LASA_TYPES:
            raise MedicationSafetyError("Jenis LASA tidak valid")
        if not recommendation:
            raise MedicationSafetyError("Rekomendasi LASA wajib diisi")
        with self.database.session() as session:
            self._require_writer(session, actor_user_id)
            drugs = session.scalars(select(DrugMaster).where(DrugMaster.khanza_code.in_((code_a, code_b)), DrugMaster.is_active.is_(True))).all()
            by_code = {row.khanza_code: row for row in drugs}
            if len(by_code) != 2:
                raise MedicationSafetyError("Salah satu kode obat LASA tidak ditemukan")
            first, second = sorted((by_code[code_a], by_code[code_b]), key=lambda row: row.id)
            row = session.scalar(select(LasaPair).where(LasaPair.drug_low_id == first.id, LasaPair.drug_high_id == second.id, LasaPair.lasa_type == kind, LasaPair.unit_scope == unit))
            if row is None:
                row = LasaPair(drug_low_id=first.id, drug_high_id=second.id, lasa_type=kind, unit_scope=unit, recommendation=recommendation, approved_at=utc_now())
                session.add(row)
            row.app_severity = severity
            row.requires_double_check = requires_double_check
            row.recommendation = recommendation
            row.source = normalize_text(source) or None
            row.is_active = is_active
            row.validated_by = actor_user_id
            row.approved_at = utc_now()
            row.updated_at = utc_now()
            session.flush()
            self._audit(session, "LASA_PAIR_UPSERTED", actor_user_id, "LASA_PAIR", row.id)
            session.commit()

    def configuration_fingerprint(self, session: Session) -> str:
        policy = self._policy(session)
        payload: dict[str, object] = {
            "policy": [policy.polypharmacy_threshold, policy.hyperpolypharmacy_threshold, policy.is_active],
            "therapy": [list(row) for row in session.execute(select(IngredientTherapyProfile.ingredient_id, IngredientTherapyProfile.therapeutic_class, IngredientTherapyProfile.therapeutic_subclass, IngredientTherapyProfile.atc_code, IngredientTherapyProfile.route_context, IngredientTherapyProfile.is_active).order_by(IngredientTherapyProfile.id)).all()],
            "high_alert": [list(row) for row in session.execute(select(HighAlertMedication.drug_id, HighAlertMedication.category, HighAlertMedication.unit_scope, HighAlertMedication.app_severity, HighAlertMedication.requires_double_check, HighAlertMedication.recommendation, HighAlertMedication.is_active).order_by(HighAlertMedication.id)).all()],
            "lasa": [list(row) for row in session.execute(select(LasaPair.drug_low_id, LasaPair.drug_high_id, LasaPair.lasa_type, LasaPair.unit_scope, LasaPair.app_severity, LasaPair.requires_double_check, LasaPair.recommendation, LasaPair.is_active).order_by(LasaPair.id)).all()],
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def evaluate(self, session: Session, items: tuple[SafetyPrescriptionItem, ...], service_unit: str = "") -> tuple[SafetyFinding, ...]:
        findings: list[SafetyFinding] = []
        occurrences: dict[str, list[SafetyPrescriptionItem]] = {}
        display_by_ingredient: dict[str, str] = {}
        for item in items:
            for name in item.ingredients:
                key = normalize_name(name)
                if key:
                    occurrences.setdefault(key, []).append(item)
                    display_by_ingredient.setdefault(key, name)

        for key, rows in sorted(occurrences.items()):
            distinct = {row.source_item_key: row for row in rows}
            if len(distinct) < 2:
                continue
            same_compound = len({row.compound_group for row in distinct.values() if row.compound_group}) == 1 and all(row.compound_group for row in distinct.values())
            context = " dalam racikan yang sama (kemungkinan disengaja)" if same_compound else " pada lebih dari satu item resep"
            findings.append(SafetyFinding("DUPLICATE_THERAPY", "REVIEW", f"Zat aktif {display_by_ingredient[key]} muncul{context}; periksa dosis, rute, dan tujuan terapi.", reference=display_by_ingredient[key]))

        ingredient_keys = set(occurrences)
        profile_rows = session.execute(
            select(ActiveIngredient.normalized_name, IngredientTherapyProfile)
            .join(IngredientTherapyProfile, IngredientTherapyProfile.ingredient_id == ActiveIngredient.id)
            .where(ActiveIngredient.normalized_name.in_(ingredient_keys), IngredientTherapyProfile.is_active.is_(True))
        ).all() if ingredient_keys else []
        profiles = {name: profile for name, profile in profile_rows}
        class_seen: set[tuple[str, str, str]] = set()
        occurrence_rows = [(key, item) for key, rows in occurrences.items() for item in rows if key in profiles]
        for (left_key, left), (right_key, right) in combinations(occurrence_rows, 2):
            if left.source_item_key == right.source_item_key or left_key == right_key:
                continue
            left_profile, right_profile = profiles[left_key], profiles[right_key]
            if normalize_name(left_profile.therapeutic_class) != normalize_name(right_profile.therapeutic_class):
                continue
            if left_profile.route_context and normalize_name(left.route) != normalize_name(left_profile.route_context):
                continue
            if right_profile.route_context and normalize_name(right.route) != normalize_name(right_profile.route_context):
                continue
            item_keys = sorted((left.source_item_key, right.source_item_key))
            identity = (normalize_name(left_profile.therapeutic_class), item_keys[0], item_keys[1])
            if identity in class_seen:
                continue
            class_seen.add(identity)
            findings.append(SafetyFinding("DUPLICATE_THERAPY", "REVIEW", f"{left.display_name} dan {right.display_name} berada pada kelas terapi {left_profile.therapeutic_class}; nilai apakah kombinasi disengaja.", reference=left_profile.therapeutic_class))

        policy = self._policy(session)
        unique_count = len(ingredient_keys)
        if policy.is_active and unique_count >= policy.polypharmacy_threshold:
            hyper = unique_count >= policy.hyperpolypharmacy_threshold
            findings.append(SafetyFinding("POLYPHARMACY", "REVIEW" if hyper else "INFO", f"Terdapat {unique_count} zat aktif unik: {'hiperpolifarmasi' if hyper else 'polifarmasi'} menurut ambang lokal {policy.polypharmacy_threshold}/{policy.hyperpolypharmacy_threshold}.", reference=str(unique_count)))

        codes = {normalize_code(item.khanza_code) for item in items}
        drug_rows = session.scalars(select(DrugMaster).where(DrugMaster.khanza_code.in_(codes))).all() if codes else []
        drugs_by_id = {row.id: row for row in drug_rows}
        drugs_by_code = {row.khanza_code: row for row in drug_rows}
        unit_key = normalize_name(service_unit)
        high_rows = session.scalars(select(HighAlertMedication).where(HighAlertMedication.drug_id.in_(drugs_by_id), HighAlertMedication.is_active.is_(True))).all() if drugs_by_id else []
        for rule in high_rows:
            if not self._unit_matches(rule.unit_scope, unit_key):
                continue
            drug = drugs_by_id[rule.drug_id]
            check = " Wajib double-check." if rule.requires_double_check else ""
            findings.append(SafetyFinding("HIGH_ALERT", rule.app_severity, f"High-alert kategori {rule.category}.{check} {rule.recommendation}", reference=rule.category, khanza_code=drug.khanza_code, display_name=drug.display_name))

        lasa_rows = session.scalars(select(LasaPair).where(LasaPair.drug_low_id.in_(drugs_by_id), LasaPair.drug_high_id.in_(drugs_by_id), LasaPair.is_active.is_(True))).all() if len(drugs_by_id) >= 2 else []
        for rule in lasa_rows:
            if not self._unit_matches(rule.unit_scope, unit_key):
                continue
            first, second = drugs_by_id[rule.drug_low_id], drugs_by_id[rule.drug_high_id]
            check = " Wajib double-check obat yang dipilih." if rule.requires_double_check else ""
            findings.append(SafetyFinding("LASA", rule.app_severity, f"Pasangan LASA {rule.lasa_type}: {first.display_name} / {second.display_name}.{check} {rule.recommendation}", reference=f"{first.khanza_code} || {second.khanza_code}"))
        return tuple(findings)

    @staticmethod
    def highest_finding_risk(findings: tuple[SafetyFinding, ...]) -> str:
        return max((row.app_severity for row in findings), key=lambda value: RISK_PRIORITY[value], default="SAFE")

    @staticmethod
    def _unit_matches(scope: str, normalized_unit: str) -> bool:
        return scope == "*" or normalize_name(scope) == normalized_unit

    @staticmethod
    def _severity(value: str) -> str:
        clean = normalize_text(value).upper()
        if clean not in MedicationSafetyService.SEVERITIES:
            raise MedicationSafetyError("Severity harus INFO, REVIEW, atau HIGH_RISK")
        return clean

    @staticmethod
    def _policy(session: Session) -> MedicationSafetyPolicy:
        row = session.get(MedicationSafetyPolicy, 1)
        if row is None:
            row = MedicationSafetyPolicy(id=1)
            session.add(row)
            session.flush()
        return row

    def _require_writer(self, session: Session, actor_user_id: str) -> None:
        user = session.scalar(select(AppUser).options(selectinload(AppUser.roles).selectinload(UserRole.role)).where(AppUser.id == actor_user_id, AppUser.is_active.is_(True)))
        if user is None:
            raise MedicationSafetyPermissionError("Pengguna aktif tidak ditemukan")
        if not {link.role.code for link in user.roles}.intersection(self.WRITER_ROLES):
            raise MedicationSafetyPermissionError("Role tidak berwenang mengubah master keselamatan obat")

    def _audit(self, session: Session, action: str, actor_user_id: str, entity_type: str, entity_id: str) -> None:
        self.audit.append(session, AuditEvent(category="CLINICAL_KNOWLEDGE", action=action, outcome="SUCCESS", actor_user_id=actor_user_id, entity_type=entity_type, entity_id=entity_id))
