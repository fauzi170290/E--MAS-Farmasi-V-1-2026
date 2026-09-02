from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import ActiveIngredient
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import (
    BundledDdiSeedApplication,
    DdiRule,
    KnowledgeBaseTransition,
    KnowledgeBaseVersion,
)
from emss.database.models import AppUser, Role, UserRole
from emss.domain.knowledge import canonical_pair, normalize_severity, validate_status_severity
from emss.domain.kfa import validate_kfa_bza_code
from emss.importexport.drug_import import normalize_name
from emss.utils.resources import bundled_resource
from emss.utils.time import utc_now


class BundledDdiSeedError(ValueError):
    pass


@dataclass(frozen=True)
class BundledDdiSeedResult:
    status: str
    bundle_id: str
    rule_count: int
    ingredient_count: int
    reused_ingredient_count: int = 0
    knowledge_base_version_id: str | None = None


FORMAT = "EMSS_BUNDLED_DDI_SEED_V1"
MANIFEST_FORMAT = "EMSS_BUNDLED_DDI_SEED_MANIFEST_V1"
BUNDLE_ID = "DDI-KHANZA-v1.0.0"
BUNDLE_FILENAME = "ddi-khanza-v1.0.0.json.gz"
MANIFEST_FILENAME = "ddi-khanza-v1.0.0.manifest.json"
EXPECTED_BUNDLE_SHA256 = "ef207bede48cc3a8d1972c28ce8b52a345602ec7de11451b0c327947fb0926cd"
EXPECTED_SEMANTIC_SHA256 = "dbd4539134135ceaa2f872faa7068b4445dd2eae8414d479db3f6c22a421d16e"
EXPECTED_SOURCE_KNOWLEDGE_SHA256 = "9f5283e7908fbfe679484344567b8b34e58b78ced80c8a3de9a38a805667420a"
EXPECTED_INGREDIENT_COUNT = 159
EXPECTED_RULE_COUNT = 5432
EXPECTED_CATALOG_PROFILE = {
    "severity": {
        "NONE": 4867,
        "MINOR": 102,
        "SIGNIFICANT": 404,
        "SERIOUS": 55,
        "CONTRAINDICATED": 4,
    },
    "interaction_status": {
        "ASSESSED_NO_INTERACTION": 3646,
        "NOT_ASSESSABLE": 975,
        "EXCLUDED": 246,
        "INTERACTION_FOUND": 565,
    },
    "activation_status": {
        "NOT_AN_ALERT_RULE": 4867,
        "READY_FOR_PHARMACIST_REVIEW": 379,
        "HOLD_CLINICAL_REVIEW_REQUIRED": 175,
        "DRAFT": 11,
    },
    "missing_source_reference": 18,
    "clinical_review_required": 175,
    "enabled": 0,
}
MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
ELIGIBLE_ACTOR_ROLES = frozenset({"SUPER_ADMIN", "IT_ADMIN", "KNOWLEDGE_ADMIN"})


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bounded(path: Path, maximum: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise BundledDdiSeedError(f"Artefak seed tidak valid: {path.name}")
    if path.stat().st_size > maximum:
        raise BundledDdiSeedError(f"Artefak seed terlalu besar: {path.name}")
    return path.read_bytes()


def verify_bundled_ddi_seed(root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    seed_root = root if root is not None else bundled_resource("seed")
    manifest_bytes = _read_bounded(seed_root / MANIFEST_FILENAME, 64 * 1024)
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundledDdiSeedError("Manifest seed DDI tidak valid") from exc
    expected_manifest = {
        "format": MANIFEST_FORMAT,
        "bundle_id": BUNDLE_ID,
        "bundle_file": BUNDLE_FILENAME,
        "bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "semantic_sha256": EXPECTED_SEMANTIC_SHA256,
        "source_knowledge_checksum": EXPECTED_SOURCE_KNOWLEDGE_SHA256,
        "knowledge_base_status": "DRAFT",
        "ingredient_count": EXPECTED_INGREDIENT_COUNT,
        "rule_count": EXPECTED_RULE_COUNT,
        "patient_identity_included": False,
        "user_accounts_included": False,
        "validator_identity_redacted": True,
        "catalog_profile": EXPECTED_CATALOG_PROFILE,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise BundledDdiSeedError(f"Kontrak manifest seed tidak sesuai: {key}")

    bundle_bytes = _read_bounded(seed_root / BUNDLE_FILENAME, MAX_COMPRESSED_BYTES)
    if _sha256(bundle_bytes) != EXPECTED_BUNDLE_SHA256:
        raise BundledDdiSeedError("Checksum bundle seed DDI tidak sesuai")
    try:
        with gzip.open(seed_root / BUNDLE_FILENAME, "rb") as compressed:
            payload_bytes = compressed.read(MAX_UNCOMPRESSED_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise BundledDdiSeedError("Bundle seed DDI tidak dapat dibaca") from exc
    if len(payload_bytes) > MAX_UNCOMPRESSED_BYTES:
        raise BundledDdiSeedError("Isi bundle seed DDI melebihi batas")
    if _sha256(payload_bytes) != EXPECTED_SEMANTIC_SHA256:
        raise BundledDdiSeedError("Checksum semantik seed DDI tidak sesuai")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundledDdiSeedError("Payload seed DDI tidak valid") from exc
    if _canonical(payload) != payload_bytes:
        raise BundledDdiSeedError("Payload seed DDI tidak kanonik")
    if payload.get("format") != FORMAT or payload.get("bundle_id") != BUNDLE_ID:
        raise BundledDdiSeedError("Identitas bundle seed DDI tidak sesuai")
    ingredients = payload.get("ingredients")
    rules = payload.get("rules")
    knowledge = payload.get("knowledge_base")
    if not isinstance(ingredients, list) or len(ingredients) != EXPECTED_INGREDIENT_COUNT:
        raise BundledDdiSeedError("Jumlah zat aktif bundle seed tidak sesuai")
    if not isinstance(rules, list) or len(rules) != EXPECTED_RULE_COUNT:
        raise BundledDdiSeedError("Jumlah DDI pair bundle seed tidak sesuai")
    if not isinstance(knowledge, dict):
        raise BundledDdiSeedError("Metadata knowledge base seed tidak tersedia")
    if knowledge.get("version_code") != BUNDLE_ID or knowledge.get("status") != "DRAFT":
        raise BundledDdiSeedError("Status knowledge base seed harus DRAFT")
    if knowledge.get("source_checksum") != EXPECTED_SOURCE_KNOWLEDGE_SHA256:
        raise BundledDdiSeedError("Checksum sumber knowledge base tidak sesuai")
    actual_profile = {
        "severity": dict(Counter(str(row.get("severity_code")) for row in rules)),
        "interaction_status": dict(Counter(str(row.get("interaction_status")) for row in rules)),
        "activation_status": dict(Counter(str(row.get("activation_status")) for row in rules)),
        "missing_source_reference": sum(not str(row.get("source_reference") or "").strip() for row in rules),
        "clinical_review_required": sum(bool(row.get("clinical_review_required")) for row in rules),
        "enabled": sum(bool(row.get("is_enabled")) for row in rules),
    }
    if actual_profile != EXPECTED_CATALOG_PROFILE:
        raise BundledDdiSeedError("Profil klinis bundle seed DDI tidak sesuai")
    return manifest, payload


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise BundledDdiSeedError("Timestamp seed DDI tidak valid")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BundledDdiSeedError("Timestamp seed DDI tidak valid") from exc


def _as_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise BundledDdiSeedError("Tanggal sumber seed DDI tidak valid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BundledDdiSeedError("Tanggal sumber seed DDI tidak valid") from exc


class BundledDdiSeedService:
    GENESIS_HASH = "0" * 64

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def apply_if_eligible(self, actor_user_id: str | None = None) -> BundledDdiSeedResult:
        manifest, payload = verify_bundled_ddi_seed()
        with self.database.session() as session:
            prior = session.scalar(
                select(BundledDdiSeedApplication).where(
                    BundledDdiSeedApplication.bundle_id == BUNDLE_ID
                )
            )
            if prior is not None:
                if (
                    prior.bundle_checksum_sha256 != EXPECTED_BUNDLE_SHA256
                    or prior.semantic_checksum_sha256 != EXPECTED_SEMANTIC_SHA256
                    or prior.rule_count != EXPECTED_RULE_COUNT
                    or prior.ingredient_count != EXPECTED_INGREDIENT_COUNT
                ):
                    raise BundledDdiSeedError("Ledger seed DDI tidak sesuai kontrak")
                version = session.get(KnowledgeBaseVersion, prior.knowledge_base_version_id)
                if version is None:
                    raise BundledDdiSeedError("Versi master pada ledger seed DDI tidak ditemukan")
                self._assert_bundle_version(session, payload, version)
                return BundledDdiSeedResult(
                    "ALREADY_APPLIED",
                    BUNDLE_ID,
                    prior.rule_count,
                    prior.ingredient_count,
                    prior.reused_ingredient_count,
                    prior.knowledge_base_version_id,
                )

            actor = self._actor(session, actor_user_id)
            if actor is None:
                return BundledDdiSeedResult(
                    "DEFERRED_NO_ADMIN",
                    BUNDLE_ID,
                    EXPECTED_RULE_COUNT,
                    EXPECTED_INGREDIENT_COUNT,
                )

            existing_bundle = session.scalar(select(KnowledgeBaseVersion).where(
                KnowledgeBaseVersion.version_code == BUNDLE_ID))
            if existing_bundle is not None:
                self._assert_bundle_version(session, payload, existing_bundle)
                self._record_recovered_ledger(session, manifest, existing_bundle, actor)
                session.commit()
                return BundledDdiSeedResult(
                    "RECOVERED_EXISTING_BUNDLE", BUNDLE_ID,
                    EXPECTED_RULE_COUNT, EXPECTED_INGREDIENT_COUNT,
                    EXPECTED_INGREDIENT_COUNT, existing_bundle.id)

            had_existing_master = bool(
                (session.scalar(select(func.count(KnowledgeBaseVersion.id))) or 0)
                or (session.scalar(select(func.count(DdiRule.id))) or 0)
            )
            result = self._apply(session, manifest, payload, actor)
            session.commit()
            if had_existing_master:
                return BundledDdiSeedResult(
                    "APPLIED_ALONGSIDE_EXISTING_MASTER", result.bundle_id,
                    result.rule_count, result.ingredient_count,
                    result.reused_ingredient_count, result.knowledge_base_version_id)
            return result

    @staticmethod
    def _assert_bundle_version(
        session, payload: dict[str, Any], version: KnowledgeBaseVersion, *, strict_content: bool = False
    ) -> None:
        """Verify catalog identity while preserving named KFT review changes.

        The immutable ledger proves which payload was originally applied. Rules
        remain reviewable by design, so an already-applied database is checked
        for the complete canonical pair/ingredient set without resetting
        severity, references, validation notes, or reviewer identity.
        """
        knowledge = payload["knowledge_base"]
        if (
            version.version_code != BUNDLE_ID
            or version.status not in {"DRAFT", "PUBLISHED", "RETIRED"}
            or version.source_checksum != EXPECTED_SOURCE_KNOWLEDGE_SHA256
            or version.title != str(knowledge["title"])
        ):
            raise BundledDdiSeedError("Metadata versi master DDI bawaan tidak sesuai")

        ingredients = session.scalars(select(ActiveIngredient)).all()
        by_id = {row.id: row for row in ingredients}
        by_name = {row.normalized_name: row for row in ingredients}
        expected_ingredients = {str(row["normalized_name"]): row for row in payload["ingredients"]}
        for name, expected in expected_ingredients.items():
            actual = by_name.get(name)
            if actual is None or actual.standard_name != str(expected["standard_name"]) or actual.is_active != bool(expected["is_active"]):
                raise BundledDdiSeedError("Zat aktif master DDI bawaan tidak lengkap/berubah")
            expected_kfa = validate_kfa_bza_code(expected.get("kfa_bza_code"))
            if expected_kfa and actual.kfa_bza_code != expected_kfa:
                raise BundledDdiSeedError("Kode BZA KFA master DDI bawaan tidak sesuai")

        expected_rules = {str(row["pair_key"]): row for row in payload["rules"]}
        actual_rules = session.scalars(select(DdiRule).where(
            DdiRule.knowledge_base_version_id == version.id)).all()
        if len(actual_rules) != EXPECTED_RULE_COUNT or len(expected_rules) != EXPECTED_RULE_COUNT:
            raise BundledDdiSeedError("Jumlah pair master DDI bawaan tidak sesuai")
        fields = (
            "external_pair_id", "interaction_status", "severity_code", "severity_label",
            "severity_rank", "app_severity", "clinical_effect", "mechanism",
            "recommendation", "monitoring", "population_risk", "source_name",
            "source_reference", "source_batch", "source_evidence_count",
            "source_validation_status", "source_final_code", "activation_status",
            "clinical_review_required", "clinical_review_resolved", "record_status",
            "is_enabled", "validated_by_name", "notes",
        )
        for actual in actual_rules:
            expected = expected_rules.pop(actual.pair_key, None)
            if expected is None:
                raise BundledDdiSeedError("Pair asing ditemukan pada master DDI bawaan")
            actual_names = {by_id[actual.ingredient_low_id].normalized_name,
                by_id[actual.ingredient_high_id].normalized_name}
            if actual_names != {str(expected["ingredient_low"]), str(expected["ingredient_high"])}:
                raise BundledDdiSeedError("Relasi zat aktif pair DDI bawaan berubah")
            if strict_content:
                for field in fields:
                    expected_value = expected.get(field)
                    if field in {"severity_rank", "source_evidence_count"}:
                        expected_value = int(expected_value)
                    elif field in {"clinical_review_required", "clinical_review_resolved", "is_enabled"}:
                        expected_value = bool(expected_value)
                    if getattr(actual, field) != expected_value:
                        raise BundledDdiSeedError(f"Konten pair master DDI bawaan berubah: {actual.pair_key}")
                if actual.source_accessed_at != _as_date(expected.get("source_accessed_at")):
                    raise BundledDdiSeedError("Tanggal referensi pair DDI bawaan berubah")
                expected_validated = _as_datetime(expected["validated_at"]) if expected.get("validated_at") else None
                if actual.validated_at != expected_validated:
                    raise BundledDdiSeedError("Timestamp validasi pair DDI bawaan berubah")
        if expected_rules:
            raise BundledDdiSeedError("Pair master DDI bawaan tidak lengkap")

    def _record_recovered_ledger(self, session, manifest, version, actor) -> None:
        applied_at = utc_now()
        previous = session.scalar(select(BundledDdiSeedApplication.entry_hash)
            .order_by(BundledDdiSeedApplication.applied_at.desc()).limit(1)) or self.GENESIS_HASH
        ledger_payload = {
            "bundle_id": BUNDLE_ID,
            "bundle_checksum_sha256": EXPECTED_BUNDLE_SHA256,
            "semantic_checksum_sha256": EXPECTED_SEMANTIC_SHA256,
            "source_knowledge_checksum_sha256": EXPECTED_SOURCE_KNOWLEDGE_SHA256,
            "knowledge_base_version_id": version.id,
            "ingredient_count": EXPECTED_INGREDIENT_COUNT,
            "rule_count": EXPECTED_RULE_COUNT,
            "reused_ingredient_count": EXPECTED_INGREDIENT_COUNT,
            "applied_by": actor.id,
            "applied_at": applied_at.isoformat(),
            "previous_hash": previous,
        }
        session.add(BundledDdiSeedApplication(
            bundle_id=BUNDLE_ID, bundle_checksum_sha256=EXPECTED_BUNDLE_SHA256,
            semantic_checksum_sha256=EXPECTED_SEMANTIC_SHA256,
            source_knowledge_checksum_sha256=EXPECTED_SOURCE_KNOWLEDGE_SHA256,
            knowledge_base_version_id=version.id,
            ingredient_count=EXPECTED_INGREDIENT_COUNT, rule_count=EXPECTED_RULE_COUNT,
            reused_ingredient_count=EXPECTED_INGREDIENT_COUNT, applied_by=actor.id,
            applied_at=applied_at, previous_hash=previous,
            entry_hash=_sha256(_canonical(ledger_payload))))
        self.audit.append(session, AuditEvent(
            category="KNOWLEDGE_BASE", action="BUNDLED_DDI_RECOVERED",
            outcome="SUCCESS", actor_user_id=actor.id,
            entity_type="KNOWLEDGE_BASE_VERSION", entity_id=version.id,
            details={"bundle_id": BUNDLE_ID, "bundle_checksum_sha256": manifest["bundle_sha256"],
                "rule_count": EXPECTED_RULE_COUNT, "ingredient_count": EXPECTED_INGREDIENT_COUNT,
                "preserved_existing_master": True}))

    @staticmethod
    def _actor(session, actor_user_id: str | None) -> AppUser | None:
        query = (
            select(AppUser)
            .join(UserRole, UserRole.user_id == AppUser.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(AppUser.is_active.is_(True), Role.code.in_(ELIGIBLE_ACTOR_ROLES))
            .order_by(AppUser.created_at, AppUser.id)
            .limit(1)
        )
        if actor_user_id is not None:
            query = query.where(AppUser.id == actor_user_id)
        return session.scalar(query)

    def _apply(
        self,
        session,
        manifest: dict[str, Any],
        payload: dict[str, Any],
        actor: AppUser,
    ) -> BundledDdiSeedResult:
        existing_ingredients = {
            row.normalized_name: row
            for row in session.scalars(select(ActiveIngredient)).all()
        }
        existing_kfa = {
            row.kfa_bza_code: row
            for row in existing_ingredients.values()
            if row.kfa_bza_code
        }
        ingredient_ids: dict[str, str] = {}
        reused = 0
        seen: set[str] = set()
        for item in payload["ingredients"]:
            standard_name = str(item["standard_name"]).strip()
            normalized_name = str(item["normalized_name"]).strip()
            try:
                kfa_bza_code = validate_kfa_bza_code(item.get("kfa_bza_code"))
            except ValueError as exc:
                raise BundledDdiSeedError("Kode BZA KFA bundle tidak valid") from exc
            if (
                not standard_name
                or normalize_name(standard_name) != normalized_name
                or normalized_name in seen
            ):
                raise BundledDdiSeedError("Zat aktif bundle seed tidak valid/duplikat")
            seen.add(normalized_name)
            by_name = existing_ingredients.get(normalized_name)
            by_kfa = existing_kfa.get(kfa_bza_code) if kfa_bza_code else None
            if by_name is not None and by_kfa is not None and by_name.id != by_kfa.id:
                raise BundledDdiSeedError("Nama zat aktif dan kode BZA KFA bundle bertentangan")
            ingredient = by_kfa or by_name
            if ingredient is None:
                ingredient = ActiveIngredient(
                    standard_name=standard_name,
                    normalized_name=normalized_name,
                    kfa_bza_code=kfa_bza_code or None,
                    kfa_validation_status="DECLARED" if kfa_bza_code else "NOT_SET",
                    is_active=bool(item["is_active"]),
                    created_at=_as_datetime(item["created_at"]),
                    updated_at=_as_datetime(item["updated_at"]),
                )
                session.add(ingredient)
                session.flush()
                existing_ingredients[normalized_name] = ingredient
                if kfa_bza_code:
                    existing_kfa[kfa_bza_code] = ingredient
            else:
                if ingredient.normalized_name != normalized_name:
                    raise BundledDdiSeedError("Kode BZA KFA bundle sudah terikat pada nama lain")
                if ingredient.kfa_bza_code and kfa_bza_code and ingredient.kfa_bza_code != kfa_bza_code:
                    raise BundledDdiSeedError("Zat aktif bundle memiliki kode BZA KFA berbeda")
                if kfa_bza_code and not ingredient.kfa_bza_code:
                    ingredient.kfa_bza_code = kfa_bza_code
                    ingredient.kfa_validation_status = "DECLARED"
                reused += 1
            ingredient_ids[normalized_name] = ingredient.id

        knowledge = payload["knowledge_base"]
        version = KnowledgeBaseVersion(
            version_code=BUNDLE_ID,
            title=str(knowledge["title"]),
            description=str(knowledge.get("description") or ""),
            status="DRAFT",
            source_checksum=EXPECTED_SOURCE_KNOWLEDGE_SHA256,
            created_by=actor.id,
            created_at=_as_datetime(knowledge["created_at"]),
            updated_at=_as_datetime(knowledge["updated_at"]),
        )
        session.add(version)
        session.flush()

        pair_keys: set[str] = set()
        for item in payload["rules"]:
            low_name = str(item["ingredient_low"])
            high_name = str(item["ingredient_high"])
            _low, _high, pair_key = canonical_pair(low_name, high_name)
            if pair_key != item["pair_key"]:
                raise BundledDdiSeedError("Canonical DDI pair bundle tidak valid")
            if pair_key in pair_keys:
                raise BundledDdiSeedError("Canonical DDI pair bundle duplikat")
            pair_keys.add(pair_key)
            interaction_status = str(item["interaction_status"])
            severity_code, severity_rank, app_severity = normalize_severity(
                item["severity_code"]
            )
            validate_status_severity(interaction_status, severity_code)
            if severity_rank != int(item["severity_rank"]) or app_severity != item["app_severity"]:
                raise BundledDdiSeedError("Mapping severity bundle seed tidak valid")
            if item["record_status"] != "DRAFT" or bool(item["is_enabled"]):
                raise BundledDdiSeedError("Seed DDI tidak boleh aktif otomatis")
            ingredient_low_id, ingredient_high_id = sorted(
                (ingredient_ids[low_name], ingredient_ids[high_name])
            )
            session.add(
                DdiRule(
                    knowledge_base_version_id=version.id,
                    external_pair_id=item.get("external_pair_id"),
                    ingredient_low_id=ingredient_low_id,
                    ingredient_high_id=ingredient_high_id,
                    pair_key=pair_key,
                    interaction_status=interaction_status,
                    severity_code=severity_code,
                    severity_label=item.get("severity_label"),
                    severity_rank=severity_rank,
                    app_severity=app_severity,
                    clinical_effect=item.get("clinical_effect"),
                    mechanism=item.get("mechanism"),
                    recommendation=item.get("recommendation"),
                    monitoring=item.get("monitoring"),
                    population_risk=item.get("population_risk"),
                    source_name=str(item["source_name"]),
                    source_reference=item.get("source_reference"),
                    source_accessed_at=_as_date(item.get("source_accessed_at")),
                    source_batch=item.get("source_batch"),
                    source_evidence_count=int(item["source_evidence_count"]),
                    source_validation_status=item.get("source_validation_status"),
                    source_final_code=item.get("source_final_code"),
                    activation_status=str(item["activation_status"]),
                    clinical_review_required=bool(item["clinical_review_required"]),
                    clinical_review_resolved=bool(item["clinical_review_resolved"]),
                    record_status="DRAFT",
                    is_enabled=False,
                    validated_by_name=item.get("validated_by_name"),
                    validated_at=(
                        _as_datetime(item["validated_at"])
                        if item.get("validated_at")
                        else None
                    ),
                    notes=item.get("notes"),
                    created_by=actor.id,
                    updated_by=actor.id,
                    created_at=_as_datetime(item["created_at"]),
                    updated_at=_as_datetime(item["updated_at"]),
                )
            )
        session.flush()
        inserted = session.scalar(
            select(func.count(DdiRule.id)).where(
                DdiRule.knowledge_base_version_id == version.id
            )
        )
        if inserted != EXPECTED_RULE_COUNT:
            raise BundledDdiSeedError("Jumlah DDI pair hasil seed tidak sesuai")

        applied_at = utc_now()
        session.add(
            KnowledgeBaseTransition(
                knowledge_base_version_id=version.id,
                from_status=None,
                to_status="DRAFT",
                action="BUNDLED_SEED",
                reason=(
                    "Seed master DDI tervalidasi checksum; tetap DRAFT dan "
                    "memerlukan workflow klinis aplikasi"
                ),
                actor_user_id=actor.id,
                occurred_at=applied_at,
            )
        )
        previous = session.scalar(
            select(BundledDdiSeedApplication.entry_hash)
            .order_by(BundledDdiSeedApplication.applied_at.desc())
            .limit(1)
        ) or self.GENESIS_HASH
        ledger_payload = {
            "bundle_id": BUNDLE_ID,
            "bundle_checksum_sha256": EXPECTED_BUNDLE_SHA256,
            "semantic_checksum_sha256": EXPECTED_SEMANTIC_SHA256,
            "source_knowledge_checksum_sha256": EXPECTED_SOURCE_KNOWLEDGE_SHA256,
            "knowledge_base_version_id": version.id,
            "ingredient_count": EXPECTED_INGREDIENT_COUNT,
            "rule_count": EXPECTED_RULE_COUNT,
            "reused_ingredient_count": reused,
            "applied_by": actor.id,
            "applied_at": applied_at.isoformat(),
            "previous_hash": previous,
        }
        entry_hash = _sha256(_canonical(ledger_payload))
        session.add(
            BundledDdiSeedApplication(
                bundle_id=BUNDLE_ID,
                bundle_checksum_sha256=EXPECTED_BUNDLE_SHA256,
                semantic_checksum_sha256=EXPECTED_SEMANTIC_SHA256,
                source_knowledge_checksum_sha256=EXPECTED_SOURCE_KNOWLEDGE_SHA256,
                knowledge_base_version_id=version.id,
                ingredient_count=EXPECTED_INGREDIENT_COUNT,
                rule_count=EXPECTED_RULE_COUNT,
                reused_ingredient_count=reused,
                applied_by=actor.id,
                applied_at=applied_at,
                previous_hash=previous,
                entry_hash=entry_hash,
            )
        )
        self.audit.append(
            session,
            AuditEvent(
                category="KNOWLEDGE_BASE",
                action="BUNDLED_DDI_SEED",
                outcome="SUCCESS",
                actor_user_id=actor.id,
                entity_type="KNOWLEDGE_BASE_VERSION",
                entity_id=version.id,
                details={
                    "bundle_id": BUNDLE_ID,
                    "bundle_checksum_sha256": manifest["bundle_sha256"],
                    "semantic_checksum_sha256": manifest["semantic_sha256"],
                    "source_knowledge_checksum_sha256": manifest[
                        "source_knowledge_checksum"
                    ],
                    "knowledge_base_status": "DRAFT",
                    "ingredient_count": EXPECTED_INGREDIENT_COUNT,
                    "rule_count": EXPECTED_RULE_COUNT,
                    "reused_ingredient_count": reused,
                    "patient_identity_included": False,
                    "user_accounts_included": False,
                },
            ),
        )
        return BundledDdiSeedResult(
            "APPLIED",
            BUNDLE_ID,
            EXPECTED_RULE_COUNT,
            EXPECTED_INGREDIENT_COUNT,
            reused,
            version.id,
        )
