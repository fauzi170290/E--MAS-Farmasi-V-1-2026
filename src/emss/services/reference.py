"""Named-user reference editing; immutable rule snapshots, no schema changes."""
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent
from emss.database.catalog_models import ActiveIngredient, DrugMaster, DrugComponentMapping
from emss.database.knowledge_models import BundledDdiSeedApplication, DdiRule, KnowledgeBaseVersion
from emss.database.models import AppUser
from emss.domain.knowledge import canonical_pair, normalize_severity, validate_status_severity
from emss.domain.kfa import validate_kfa_bza_code, validate_kfa_product_code
from emss.importexport.drug_import import normalize_name, normalize_text
from emss.services.knowledge import KnowledgeBaseService, KnowledgeError
from emss.utils.time import utc_now


@dataclass(frozen=True)
class DrugEdit:
    name: str
    ingredients: tuple[str, ...]
    reference: str
    code: str = ""
    drug_id: str = ""
    expected_updated_at: str = ""
    kfa_product_code: str = ""
    ingredient_kfa_codes: tuple[str, ...] = ()
    source_system: str = ""


class ReferenceService:
    ROLES = frozenset({"SUPER_ADMIN", "KFT"})

    def __init__(self, database, audit):
        self.database, self.audit = database, audit

    def _authorize(self, session, actor):
        KnowledgeBaseService._require_roles(session, actor, self.ROLES)
        user = session.get(AppUser, actor)
        if user.normalized_username == "mode.farmasi":
            raise KnowledgeError("Gunakan akun petugas bernama untuk mengubah master.")
        return user

    @staticmethod
    def _lock(session):
        # SQLite: serialize writers before reading the edit token or active version.
        session.execute(text("BEGIN IMMEDIATE"))

    @staticmethod
    def _active(session):
        return session.scalar(select(KnowledgeBaseVersion)
            .where(KnowledgeBaseVersion.status == "PUBLISHED")
            .order_by(KnowledgeBaseVersion.published_at.desc(),
                      KnowledgeBaseVersion.created_at.desc()).limit(1))

    def active_version_id(self):
        with self.database.session() as session:
            version = self._active(session)
            return version.id if version else ""

    def display_version(self):
        """Return the active master, or the verified bundled draft for catalog browsing."""
        with self.database.session() as session:
            version = self._active(session)
            if version is None:
                version = session.scalar(
                    select(KnowledgeBaseVersion)
                    .join(BundledDdiSeedApplication,
                        BundledDdiSeedApplication.knowledge_base_version_id == KnowledgeBaseVersion.id)
                    .where(KnowledgeBaseVersion.status == "DRAFT")
                    .order_by(BundledDdiSeedApplication.applied_at.desc())
                    .limit(1)
                )
            return ({"id": version.id, "status": version.status,
                "title": version.title, "version_code": version.version_code}
                if version else None)

    def drug_detail(self, drug_id):
        with self.database.session() as session:
            row = session.scalar(select(DrugMaster)
                .options(selectinload(DrugMaster.components).selectinload(DrugComponentMapping.ingredient))
                .where(DrugMaster.id == drug_id))
            if row is None:
                raise KnowledgeError("Obat tidak ditemukan.")
            components = sorted(row.components, key=lambda item: item.component_order)
            usable = tuple(c for c in components
                if row.is_active and row.review_status == "APPROVED" and c.is_active
                and c.review_status == "APPROVED" and c.ingredient.is_active)
            return {"id": row.id, "code": row.khanza_code, "name": row.display_name,
                "ingredients": tuple(c.ingredient.standard_name for c in components),
                "ingredient_kfa_codes": tuple(c.ingredient.kfa_bza_code or "" for c in components),
                "usable_ingredients": tuple(c.ingredient.standard_name for c in usable),
                "usable_ingredient_records": tuple({"name": c.ingredient.standard_name,
                    "kfa_bza_code": c.ingredient.kfa_bza_code or ""} for c in usable),
                "kfa_product_code": row.kfa_product_code or "",
                "kfa_product_type": row.kfa_product_type or "",
                "kfa_validation_status": row.kfa_validation_status,
                "source_system": row.source_system,
                "reference": row.mapping_note or "", "is_active": row.is_active,
                "updated_at": row.updated_at.isoformat()}

    def save_drug(self, data: DrugEdit, actor):
        name, reference = normalize_text(data.name), normalize_text(data.reference)
        names = tuple(dict.fromkeys(normalize_name(x) for x in data.ingredients if normalize_name(x)))
        if not name or not names or not reference:
            raise KnowledgeError("Nama, kandungan yang terverifikasi dan referensi pemetaan wajib diisi.")
        if len(name) > 200 or any(len(x) > 200 for x in names) or len(data.code) > 50:
            raise KnowledgeError("Nama/kandungan/kode terlalu panjang.")
        kfa_product_code, kfa_product_type = validate_kfa_product_code(data.kfa_product_code)
        supplied_bza_codes = tuple(validate_kfa_bza_code(value) for value in data.ingredient_kfa_codes)
        if supplied_bza_codes and len(supplied_bza_codes) != len(names):
            raise KnowledgeError("Jumlah kode BZA KFA harus sama dengan jumlah kandungan; gunakan posisi kosong bila belum ada kode.")
        bza_codes = supplied_bza_codes or tuple("" for _name in names)
        if len(set(code for code in bza_codes if code)) != len([code for code in bza_codes if code]):
            raise KnowledgeError("Satu kode BZA KFA tidak boleh dipakai dua kali pada obat yang sama.")
        source_system = normalize_text(data.source_system).upper()
        if source_system and (len(source_system) > 40 or not source_system.replace("_", "").isalnum()):
            raise KnowledgeError("Identitas sistem sumber tidak valid.")
        with self.database.session() as session:
            self._lock(session)
            self._authorize(session, actor)
            now = utc_now()
            row = session.get(DrugMaster, data.drug_id) if data.drug_id else None
            if data.drug_id and (row is None or row.updated_at.isoformat() != data.expected_updated_at):
                raise KnowledgeError("Obat telah berubah. Muat ulang sebelum menyimpan.")
            before = None
            if row:
                before = {"name": row.display_name, "reference": row.mapping_note,
                    "source_system": row.source_system, "kfa_product_code": row.kfa_product_code,
                    "ingredients": [c.ingredient.standard_name for c in row.components],
                    "ingredient_kfa_codes": [c.ingredient.kfa_bza_code for c in row.components],
                    "is_active": row.is_active, "review_status": row.review_status,
                    "components": [{"id": c.id, "ingredient_id": c.ingredient_id,
                        "review_status": c.review_status, "is_active": c.is_active,
                        "mapping_method": c.mapping_method, "source_version": c.source_version}
                        for c in row.components]}
                if data.code and data.code != row.khanza_code:
                    raise KnowledgeError("Kode sumber tidak dapat diganti melalui edit pemetaan.")
                for component in list(row.components):
                    session.delete(component)
                session.flush()
            else:
                code = normalize_text(data.code) or "LOCAL:" + str(uuid4())
                if normalize_text(data.code).upper().startswith("LOCAL:"):
                    raise KnowledgeError("Identitas LOCAL dibuat sistem; kosongkan kode untuk obat lokal.")
                if session.scalar(select(DrugMaster.id).where(DrugMaster.khanza_code == code)):
                    raise KnowledgeError("Kode obat sudah ada. Pilih Edit Obat.")
                row = DrugMaster(khanza_code=code, source_version="LOCAL_MANUAL",
                    source_system=source_system or ("LOCAL" if code.startswith("LOCAL:") else "KHANZA"),
                    display_name=name, normalized_name=normalize_name(name),
                    source_mapping_status="MAPPED", review_status="APPROVED",
                    mapping_method="MANUAL_REFERENCE", component_count=len(names))
                session.add(row)
                session.flush()
            row.display_name, row.normalized_name = name, normalize_name(name)
            if source_system:
                row.source_system = source_system
            row.kfa_product_code = kfa_product_code or None
            row.kfa_product_type = kfa_product_type or None
            row.kfa_validation_status = "DECLARED" if kfa_product_code else "NOT_SET"
            row.mapping_note, row.mapping_method = reference, "MANUAL_REFERENCE"
            row.component_count, row.is_active = len(names), True
            row.source_mapping_status, row.review_status = "MAPPED", "APPROVED"
            row.updated_at = now
            for order, (ingredient_name, kfa_bza_code) in enumerate(zip(names, bza_codes), 1):
                by_name = session.scalar(select(ActiveIngredient).where(
                    ActiveIngredient.normalized_name == ingredient_name))
                by_kfa = (session.scalar(select(ActiveIngredient).where(
                    ActiveIngredient.kfa_bza_code == kfa_bza_code)) if kfa_bza_code else None)
                if by_name is not None and by_kfa is not None and by_name.id != by_kfa.id:
                    raise KnowledgeError("Nama kandungan dan kode BZA KFA menunjuk master yang berbeda.")
                ingredient = by_kfa or by_name
                if ingredient is None:
                    ingredient = ActiveIngredient(standard_name=ingredient_name,
                        normalized_name=ingredient_name, kfa_bza_code=kfa_bza_code or None,
                        kfa_validation_status="DECLARED" if kfa_bza_code else "NOT_SET")
                    session.add(ingredient)
                    session.flush()
                elif not ingredient.is_active:
                    raise KnowledgeError("Kandungan nonaktif harus ditelaah sebelum dipakai.")
                elif ingredient.normalized_name != ingredient_name:
                    raise KnowledgeError("Kode BZA KFA sudah terikat pada nama kandungan lain.")
                elif ingredient.kfa_bza_code and kfa_bza_code and ingredient.kfa_bza_code != kfa_bza_code:
                    raise KnowledgeError("Kandungan sudah memiliki kode BZA KFA yang berbeda.")
                elif kfa_bza_code and not ingredient.kfa_bza_code:
                    ingredient.kfa_bza_code = kfa_bza_code
                    ingredient.kfa_validation_status = "DECLARED"
                session.add(DrugComponentMapping(drug_id=row.id, ingredient_id=ingredient.id,
                    component_order=order, source_mapping_status="MAPPED",
                    mapping_method="MANUAL_REFERENCE", review_status="APPROVED", is_active=True,
                    source_version="LOCAL_MANUAL", reviewed_by=actor, reviewed_at=now))
            session.flush()
            self.audit.append(session, AuditEvent(category="REFERENCE", action="DRUG_SAVED_ACTIVE",
                outcome="SUCCESS", actor_user_id=actor, entity_type="drug_master", entity_id=row.id,
                details={"before": before, "after": {"name": name, "code": row.khanza_code,
                    "source_system": row.source_system, "kfa_product_code": row.kfa_product_code,
                    "ingredients": names, "ingredient_kfa_codes": bza_codes,
                    "reference": reference}}))
            session.commit()
            return row.id

    def set_drug_active(self, drug_id, actor, expected_updated_at, active=False):
        with self.database.session() as session:
            self._lock(session)
            self._authorize(session, actor)
            row = session.get(DrugMaster, drug_id)
            if row is None or row.updated_at.isoformat() != expected_updated_at:
                raise KnowledgeError("Obat telah berubah. Muat ulang.")
            if active:
                raise KnowledgeError("Gunakan Simpan & Aktifkan untuk menvalidasi pemetaan.")
            row.is_active, row.updated_at = False, utc_now()
            self.audit.append(session, AuditEvent(category="REFERENCE", action="DRUG_DEACTIVATED",
                outcome="SUCCESS", actor_user_id=actor, entity_type="drug_master", entity_id=row.id))
            session.commit()

    def pair_detail(self, rule_id):
        with self.database.session() as session:
            row = session.get(DdiRule, rule_id)
            if row is None:
                raise KnowledgeError("Pair tidak ditemukan.")
            return {column.name: getattr(row, column.name) for column in DdiRule.__table__.columns}

    def save_pair(self, data, actor, *, expected_version_id, edit_rule_id="",
                  active=True, selected_drug_ids=()):
        low, high, key = canonical_pair(data.ingredient_a, data.ingredient_b)
        severity, rank, app_severity = normalize_severity(data.severity_code)
        validate_status_severity(data.interaction_status, severity)
        if not normalize_text(data.source_name) or not normalize_text(data.source_reference):
            raise KnowledgeError("Sumber dan referensi yang dapat ditelusuri wajib diisi.")
        with self.database.session() as session:
            self._lock(session)
            user = self._authorize(session, actor)
            base = self._active(session)
            if (base.id if base else "") != expected_version_id:
                raise KnowledgeError("Master aktif telah berubah. Muat ulang sebelum menyimpan.")
            ingredients = {x.normalized_name: x for x in session.scalars(select(ActiveIngredient)
                .where(ActiveIngredient.normalized_name.in_((low, high)),
                       ActiveIngredient.is_active.is_(True))).all()}
            if len(ingredients) != 2:
                raise KnowledgeError("Kedua kandungan harus tersedia dan aktif di Master Obat.")
            if selected_drug_ids:
                if len(selected_drug_ids) != 2:
                    raise KnowledgeError("Pilih kedua obat dari master.")
                for drug_id, name in zip(selected_drug_ids, (normalize_name(data.ingredient_a), normalize_name(data.ingredient_b))):
                    drug = session.get(DrugMaster, drug_id)
                    if not drug or not drug.is_active or drug.review_status != "APPROVED" or not any(
                        c.is_active and c.review_status == "APPROVED" and c.ingredient.is_active
                        and c.ingredient.normalized_name == name for c in drug.components):
                        raise KnowledgeError("Pemetaan obat berubah/belum disetujui. Periksa Master Obat dan pilih ulang kandungan.")
            existing = session.scalar(select(DdiRule).where(
                DdiRule.knowledge_base_version_id == base.id, DdiRule.pair_key == key)) if base else None
            if existing and existing.id != edit_rule_id:
                raise KnowledgeError("Pasangan sudah ada. Pilih Edit Pasangan.")
            if edit_rule_id and (not existing or existing.id != edit_rule_id):
                raise KnowledgeError("Pair berubah atau tidak lagi aktif. Muat ulang.")
            now = utc_now()
            new_version = KnowledgeBaseVersion(version_code="LOCAL-" + uuid4().hex,
                title="Master aktif — perubahan per pasangan", status="PUBLISHED",
                based_on_version_id=base.id if base else None, created_by=actor,
                published_by=actor, published_at=now,
                description="Aktivasi langsung per entri; bukan persetujuan bulk draft.")
            session.add(new_version)
            session.flush()
            if base:
                # Copy every unrelated rule as-is. Draft/inactive flags are not promoted.
                columns = list(DdiRule.__table__.columns)
                copies = []
                for old in session.scalars(select(DdiRule).where(
                        DdiRule.knowledge_base_version_id == base.id, DdiRule.pair_key != key)):
                    values = {col.name: getattr(old, col.name) for col in columns}
                    values.update(id=str(uuid4()), knowledge_base_version_id=new_version.id)
                    copies.append(values)
                if copies:
                    session.execute(insert(DdiRule.__table__), copies)
                base.status, base.retired_at, base.retired_by = "RETIRED", now, actor
            rule = DdiRule(knowledge_base_version_id=new_version.id,
                ingredient_low_id=ingredients[low].id, ingredient_high_id=ingredients[high].id,
                pair_key=key, interaction_status=data.interaction_status, severity_code=severity,
                severity_rank=rank, app_severity=app_severity, source_name=normalize_text(data.source_name),
                source_reference=normalize_text(data.source_reference),
                source_accessed_at=data.source_accessed_at, source_validation_status="NAMED_USER_REVIEW",
                activation_status="ACTIVE" if active else "INACTIVE",
                record_status="PUBLISHED", is_enabled=active,
                clinical_review_required=False, clinical_review_resolved=True,
                created_by=actor, updated_by=actor, validated_by_name=user.display_name,
                validated_at=now, clinical_effect=data.clinical_effect,
                recommendation=data.recommendation, monitoring=data.monitoring,
                mechanism=data.mechanism, population_risk=data.population_risk, notes=data.notes)
            session.add(rule)
            session.flush()
            self.audit.append(session, AuditEvent(category="REFERENCE",
                action="PAIR_ACTIVATED" if active else "PAIR_DEACTIVATED",
                outcome="SUCCESS", actor_user_id=actor, entity_type="ddi_rule", entity_id=rule.id,
                details={"pair_key": key, "previous_rule_id": existing.id if existing else None,
                    "previous_version": base.id if base else None, "version": new_version.id,
                    "source": rule.source_name, "reference": rule.source_reference,
                    "severity": severity, "interaction_status": data.interaction_status,
                    "selected_drug_ids": selected_drug_ids}))
            session.commit()
            return rule.id
