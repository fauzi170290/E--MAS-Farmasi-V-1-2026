"""Controlled H3 activation for the verified bundled DDI and Khanza mapping."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections import Counter

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import (
    DrugComponentMapping,
    DrugMaster,
    ImportBatch,
)
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import (
    BundledDdiSeedApplication,
    DdiRule,
    KnowledgeBaseTransition,
    KnowledgeBaseVersion,
)
from emss.database.models import AppUser, AuditLog, UserRole
from emss.importexport.drug_import import normalize_name, normalize_text
from emss.services.bundled_ddi import (
    BUNDLE_ID as DDI_BUNDLE_ID,
    EXPECTED_BUNDLE_SHA256,
    EXPECTED_RULE_COUNT,
    verify_bundled_ddi_seed,
)
from emss.services.bundled_mapping import (
    BUNDLE_ID as MAPPING_BUNDLE_ID,
    _read_bundle,
)
from emss.services.knowledge import KnowledgeError
from emss.utils.time import utc_now


class H3ActivationError(KnowledgeError):
    pass


@dataclass(frozen=True)
class H3ActivationPreview:
    version_id: str
    version_status: str
    eligible_pairs: int
    active_pairs: int
    held_pairs: int
    draft_pairs: int
    mapping_eligible: int
    mapping_blocked: int


@dataclass(frozen=True)
class H3ActivationResult(H3ActivationPreview):
    activated_by: str
    already_active: bool


@dataclass(frozen=True)
class H5HoldValidationPreview:
    """Read-only contract proof for the cohort requested for H5 activation."""

    version_id: str
    version_status: str
    hold_pairs: int
    severity_counts: tuple[tuple[str, int], ...]
    source_references: int
    missing_source_reference_pairs: tuple[str, ...]
    activation_ready: bool
    cohort_sha256: str


@dataclass(frozen=True)
class H5HoldValidationResult(H5HoldValidationPreview):
    validated_by: str


@dataclass(frozen=True)
class H5HoldActivationResult:
    version_id: str
    active_pairs: int
    activated_hold_pairs: int
    missing_source_reference_pairs: tuple[str, ...]
    activated_by: str


class H3ActivationService:
    """Publish only the explicitly safe positive cohort.

    The operation is atomic and named-user audited. It never promotes HOLD,
    DRAFT, missing-reference, non-positive, or structurally changed records.
    """

    ROLES = frozenset({"SUPER_ADMIN", "KFT"})
    EXPECTED_ELIGIBLE_PAIRS = 379
    EXPECTED_HELD_PAIRS = 175
    EXPECTED_DRAFT_PAIRS = 11
    EXPECTED_MAPPING_COUNT = 414
    EXPECTED_HOLD_SEVERITY = {
        "MINOR": 30,
        "SIGNIFICANT": 120,
        "SERIOUS": 24,
        "CONTRAINDICATED": 1,
    }
    HOLD_SIGNATURE_FIELDS = (
        "pair_key",
        "interaction_status",
        "severity_code",
        "severity_rank",
        "source_name",
        "source_reference",
        "source_evidence_count",
        "clinical_review_required",
    )

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def preview(self) -> H3ActivationPreview:
        verify_bundled_ddi_seed()
        _manifest, _payload, mapping_rows = _read_bundle()
        with self.database.session() as session:
            version = self._bundled_version(session)
            eligible, active, held, draft = self._pair_counts(session, version.id)
            mapping_eligible, mapping_blocked, _drugs = self._mapping_candidates(
                session, mapping_rows
            )
            return H3ActivationPreview(
                version_id=version.id,
                version_status=version.status,
                eligible_pairs=eligible,
                active_pairs=active,
                held_pairs=held,
                draft_pairs=draft,
                mapping_eligible=mapping_eligible,
                mapping_blocked=mapping_blocked,
            )

    def preview_hold_cohort(self) -> H5HoldValidationPreview:
        """Verify HOLD pair evidence without changing activation state."""
        _manifest, payload = verify_bundled_ddi_seed()
        with self.database.session() as session:
            version = self._bundled_version(session)
            return self._validate_hold_cohort(session, version, payload)

    def validate_hold_cohort(
        self, actor_user_id: str, reason: str
    ) -> H5HoldValidationResult:
        """Record named KFT validation evidence; activation remains H5-C."""
        clean_reason = normalize_text(reason)
        if len(clean_reason) < 8:
            raise H3ActivationError(
                "Catatan validasi cohort HOLD minimal 8 karakter."
            )
        ddi_manifest, payload = verify_bundled_ddi_seed()
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            actor = self._authorize(session, actor_user_id)
            version = self._bundled_version(session)
            preview = self._validate_hold_cohort(session, version, payload)
            self.audit.append(
                session,
                AuditEvent(
                    category="KNOWLEDGE_BASE",
                    action="H5_HOLD_COHORT_VALIDATED",
                    outcome=("SUCCESS" if preview.activation_ready else "NEEDS_REVIEW"),
                    actor_user_id=actor.id,
                    entity_type="KNOWLEDGE_BASE_VERSION",
                    entity_id=version.id,
                    details={
                        "policy": "H5_HOLD_COHORT_V1",
                        "reason": clean_reason,
                        "ddi_bundle_id": DDI_BUNDLE_ID,
                        "ddi_bundle_sha256": ddi_manifest["bundle_sha256"],
                        "hold_pairs": preview.hold_pairs,
                        "severity_counts": dict(preview.severity_counts),
                        "source_references": preview.source_references,
                        "missing_source_reference_pairs": list(
                            preview.missing_source_reference_pairs
                        ),
                        "activation_ready": preview.activation_ready,
                        "cohort_sha256": preview.cohort_sha256,
                        "activation_performed": False,
                    },
                ),
            )
            session.commit()
            return H5HoldValidationResult(
                **preview.__dict__, validated_by=actor.display_name
            )

    def activate_hold_cohort(
        self, actor_user_id: str, reason: str
    ) -> H5HoldActivationResult:
        """Activate the named KFT-approved HOLD cohort after H5-B evidence capture.

        The explicit activation is intentionally separate from validation.  Any
        missing reference remains visible in the immutable audit record.
        """
        clean_reason = normalize_text(reason)
        if len(clean_reason) < 8:
            raise H3ActivationError(
                "Catatan keputusan aktivasi HOLD minimal 8 karakter."
            )
        ddi_manifest, payload = verify_bundled_ddi_seed()
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            actor = self._authorize(session, actor_user_id)
            version = self._bundled_version(session)
            if version.status != "PUBLISHED":
                raise H3ActivationError(
                    "Aktivasi HOLD hanya tersedia setelah katalog H3 berstatus PUBLISHED."
                )
            preview = self._validate_hold_cohort(session, version, payload)
            validation = session.scalar(
                select(AuditLog)
                .where(
                    AuditLog.action == "H5_HOLD_COHORT_VALIDATED",
                    AuditLog.entity_id == version.id,
                )
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                .limit(1)
            )
            if validation is None:
                raise H3ActivationError(
                    "Validasi H5-B bernama belum tercatat; aktivasi HOLD dihentikan."
                )
            try:
                validation_details = json.loads(validation.details_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise H3ActivationError(
                    "Bukti validasi H5-B tidak dapat dibaca; aktivasi HOLD dihentikan."
                ) from exc
            if validation_details.get("cohort_sha256") != preview.cohort_sha256:
                raise H3ActivationError(
                    "Bukti validasi H5-B tidak cocok dengan cohort saat ini; aktivasi HOLD dihentikan."
                )

            rules = session.scalars(
                select(DdiRule).where(
                    DdiRule.knowledge_base_version_id == version.id,
                    DdiRule.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED",
                )
            ).all()
            if len(rules) != self.EXPECTED_HELD_PAIRS:
                raise H3ActivationError(
                    "Jumlah pair HOLD berubah setelah validasi; aktivasi dihentikan."
                )
            now = utc_now()
            for rule in rules:
                rule.activation_status = "ACTIVE"
                rule.is_enabled = True
                rule.record_status = "PUBLISHED"
                rule.clinical_review_resolved = True
                rule.validated_by_name = actor.display_name
                rule.validated_at = now
                rule.updated_by = actor.id

            session.flush()
            active_pairs = session.scalar(
                select(func.count(DdiRule.id)).where(
                    DdiRule.knowledge_base_version_id == version.id,
                    DdiRule.activation_status == "ACTIVE",
                    DdiRule.is_enabled.is_(True),
                )
            ) or 0
            self.audit.append(
                session,
                AuditEvent(
                    category="KNOWLEDGE_BASE",
                    action="H5_HOLD_COHORT_ACTIVATED",
                    outcome="SUCCESS",
                    actor_user_id=actor.id,
                    entity_type="KNOWLEDGE_BASE_VERSION",
                    entity_id=version.id,
                    details={
                        "policy": "H5_HOLD_ACTIVATION_V1",
                        "reason": clean_reason,
                        "ddi_bundle_id": DDI_BUNDLE_ID,
                        "ddi_bundle_sha256": ddi_manifest["bundle_sha256"],
                        "cohort_sha256": preview.cohort_sha256,
                        "activated_hold_pairs": len(rules),
                        "active_pairs_after_activation": active_pairs,
                        "missing_source_reference_pairs": list(
                            preview.missing_source_reference_pairs
                        ),
                        "kft_review_acknowledged": bool(
                            preview.missing_source_reference_pairs
                        ),
                    },
                ),
            )
            session.commit()
            return H5HoldActivationResult(
                version_id=version.id,
                active_pairs=active_pairs,
                activated_hold_pairs=len(rules),
                missing_source_reference_pairs=preview.missing_source_reference_pairs,
                activated_by=actor.display_name,
            )

    def activate(self, actor_user_id: str, reason: str) -> H3ActivationResult:
        clean_reason = normalize_text(reason)
        if len(clean_reason) < 8:
            raise H3ActivationError(
                "Catatan validasi KFT minimal 8 karakter dan wajib menjelaskan dasar aktivasi."
            )
        ddi_manifest, _payload = verify_bundled_ddi_seed()
        mapping_manifest, _mapping_payload, mapping_rows = _read_bundle()
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            actor = self._authorize(session, actor_user_id)
            version = self._bundled_version(session)
            eligible, active, held, draft = self._pair_counts(session, version.id)
            mapping_eligible, mapping_blocked, candidates = self._mapping_candidates(
                session, mapping_rows
            )

            if version.status == "PUBLISHED":
                return H3ActivationResult(
                    version.id,
                    version.status,
                    eligible,
                    active,
                    held,
                    draft,
                    mapping_eligible,
                    mapping_blocked,
                    actor.display_name,
                    True,
                )
            if version.status != "DRAFT":
                raise H3ActivationError(
                    "Katalog bawaan tidak berada pada status DRAFT; aktivasi dihentikan."
                )
            other_active = session.scalar(
                select(KnowledgeBaseVersion.id).where(
                    KnowledgeBaseVersion.status == "PUBLISHED",
                    KnowledgeBaseVersion.id != version.id,
                )
            )
            if other_active:
                raise H3ActivationError(
                    "Sudah ada master PUBLISHED lain. Gabungkan melalui pengelolaan lanjutan; "
                    "katalog bawaan tidak menggantikannya otomatis."
                )
            if (
                eligible != self.EXPECTED_ELIGIBLE_PAIRS
                or held != self.EXPECTED_HELD_PAIRS
                or draft != self.EXPECTED_DRAFT_PAIRS
                or active != 0
            ):
                raise H3ActivationError(
                    "Cohort pair bawaan telah berubah dari kontrak H3; aktivasi dihentikan untuk review."
                )

            now = utc_now()
            rules = session.scalars(
                select(DdiRule).where(
                    DdiRule.knowledge_base_version_id == version.id
                )
            ).all()
            for rule in rules:
                rule.record_status = "PUBLISHED"
                if self._eligible_pair(rule):
                    rule.activation_status = "ACTIVE"
                    rule.is_enabled = True
                    rule.clinical_review_resolved = True
                    rule.validated_by_name = actor.display_name
                    rule.validated_at = now
                    rule.updated_by = actor.id
                else:
                    rule.is_enabled = False

            for drug in candidates:
                drug.review_status = "APPROVED"
                for component in drug.components:
                    component.review_status = "APPROVED"
                    component.is_active = True
                    component.reviewed_by = actor.id
                    component.reviewed_at = now

            mapping_batch = session.scalar(
                select(ImportBatch).where(
                    ImportBatch.import_type == "BUNDLED_MAPPING",
                    ImportBatch.source_version == MAPPING_BUNDLE_ID,
                )
            )
            if mapping_batch is None:
                raise H3ActivationError(
                    "Ledger pemetaan bawaan tidak ditemukan; aktivasi dihentikan."
                )
            if mapping_batch.source_sha256 is None:
                raise H3ActivationError("Provenance pemetaan bawaan tidak lengkap.")
            if mapping_blocked == 0:
                mapping_batch.status = "APPROVED"
                mapping_batch.completed_at = now

            old_status = version.status
            version.status = "PUBLISHED"
            version.reviewed_by = actor.id
            version.reviewed_at = now
            version.approved_by = actor.id
            version.approved_at = now
            version.published_by = actor.id
            version.published_at = now
            version.updated_at = now
            session.add(
                KnowledgeBaseTransition(
                    knowledge_base_version_id=version.id,
                    from_status=old_status,
                    to_status="PUBLISHED",
                    action="H3_CONTROLLED_ACTIVATION",
                    reason=clean_reason,
                    actor_user_id=actor.id,
                    occurred_at=now,
                )
            )
            details = {
                "policy": "H3_SAFE_POSITIVE_V1",
                "reason": clean_reason,
                "ddi_bundle_id": DDI_BUNDLE_ID,
                "ddi_bundle_sha256": ddi_manifest["bundle_sha256"],
                "mapping_bundle_id": MAPPING_BUNDLE_ID,
                "mapping_bundle_sha256": mapping_manifest["bundle_sha256"],
                "activated_pairs": eligible,
                "held_pairs": held,
                "draft_pairs": draft,
                "approved_mappings": mapping_eligible,
                "blocked_mappings": mapping_blocked,
            }
            self.audit.append(
                session,
                AuditEvent(
                    category="KNOWLEDGE_BASE",
                    action="H3_CONTROLLED_ACTIVATION",
                    outcome="SUCCESS",
                    actor_user_id=actor.id,
                    entity_type="KNOWLEDGE_BASE_VERSION",
                    entity_id=version.id,
                    details=details,
                ),
            )
            session.commit()
            return H3ActivationResult(
                version.id,
                "PUBLISHED",
                0,
                eligible,
                held,
                draft,
                mapping_eligible,
                mapping_blocked,
                actor.display_name,
                False,
            )

    @classmethod
    def _eligible_pair(cls, rule: DdiRule) -> bool:
        return bool(
            rule.interaction_status == "INTERACTION_FOUND"
            and rule.severity_code != "NONE"
            and rule.activation_status == "READY_FOR_PHARMACIST_REVIEW"
            and not rule.clinical_review_required
            and rule.source_reference
            and rule.source_reference.strip()
            and rule.source_evidence_count > 0
        )

    @classmethod
    def _pair_counts(cls, session, version_id: str) -> tuple[int, int, int, int]:
        rules = session.scalars(
            select(DdiRule).where(DdiRule.knowledge_base_version_id == version_id)
        ).all()
        if len(rules) != EXPECTED_RULE_COUNT:
            raise H3ActivationError("Jumlah pair bawaan tidak sesuai kontrak H3.")
        eligible = sum(cls._eligible_pair(rule) for rule in rules)
        active = sum(
            rule.is_enabled and rule.activation_status == "ACTIVE" for rule in rules
        )
        held = sum(
            rule.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED"
            for rule in rules
        )
        draft = sum(rule.activation_status == "DRAFT" for rule in rules)
        return eligible, active, held, draft

    @classmethod
    def _hold_signature(cls, rows) -> str:
        """Hash clinical identity fields only; published state is deliberately ignored."""
        normalized = []
        for row in rows:
            if isinstance(row, dict):
                value = {field: row.get(field) for field in cls.HOLD_SIGNATURE_FIELDS}
            else:
                value = {field: getattr(row, field) for field in cls.HOLD_SIGNATURE_FIELDS}
            value["clinical_review_required"] = bool(
                value["clinical_review_required"]
            )
            normalized.append(value)
        body = json.dumps(
            sorted(normalized, key=lambda value: value["pair_key"]),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(body).hexdigest()

    @classmethod
    def _validate_hold_cohort(
        cls, session, version: KnowledgeBaseVersion, payload: dict
    ) -> H5HoldValidationPreview:
        expected = [
            row for row in payload["rules"]
            if row.get("activation_status") == "HOLD_CLINICAL_REVIEW_REQUIRED"
        ]
        actual = session.scalars(
            select(DdiRule).where(
                DdiRule.knowledge_base_version_id == version.id,
                DdiRule.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED",
            )
        ).all()
        severity = Counter(row["severity_code"] for row in expected)
        expected_signature = cls._hold_signature(expected)
        actual_signature = cls._hold_signature(actual)
        missing_source_reference_pairs = tuple(
            sorted(
                str(row["pair_key"])
                for row in expected
                if not str(row.get("source_reference") or "").strip()
            )
        )
        source_references = len(expected) - len(missing_source_reference_pairs)
        structurally_valid = all(
            row.interaction_status == "INTERACTION_FOUND"
            and row.severity_code != "NONE"
            and row.clinical_review_required
            and not row.is_enabled
            and row.source_evidence_count > 0
            for row in actual
        )
        if (
            len(expected) != cls.EXPECTED_HELD_PAIRS
            or len(actual) != cls.EXPECTED_HELD_PAIRS
            or dict(severity) != cls.EXPECTED_HOLD_SEVERITY
            or not structurally_valid
            or actual_signature != expected_signature
        ):
            raise H3ActivationError(
                "Cohort HOLD tidak sesuai kontrak H5; validasi/aktivasi dihentikan untuk review KFT."
            )
        return H5HoldValidationPreview(
            version_id=version.id,
            version_status=version.status,
            hold_pairs=len(actual),
            severity_counts=tuple(sorted(severity.items())),
            source_references=source_references,
            missing_source_reference_pairs=missing_source_reference_pairs,
            activation_ready=not missing_source_reference_pairs,
            cohort_sha256=actual_signature,
        )

    @classmethod
    def _mapping_candidates(cls, session, mapping_rows):
        expected = {str(row["code"]): row for row in mapping_rows}
        if len(expected) != cls.EXPECTED_MAPPING_COUNT:
            raise H3ActivationError("Jumlah pemetaan bawaan tidak sesuai kontrak H3.")
        drugs = session.scalars(
            select(DrugMaster)
            .options(
                selectinload(DrugMaster.components).selectinload(
                    DrugComponentMapping.ingredient
                )
            )
            .where(DrugMaster.khanza_code.in_(expected))
        ).all()
        by_code = {drug.khanza_code: drug for drug in drugs}
        candidates = []
        for code, row in expected.items():
            drug = by_code.get(code)
            if drug is None or not drug.is_active:
                continue
            expected_components = tuple(
                (int(item["order"]), normalize_name(item["ingredient"]))
                for item in sorted(row["components"], key=lambda value: value["order"])
            )
            actual_components = tuple(
                (component.component_order, component.ingredient.normalized_name)
                for component in sorted(
                    drug.components, key=lambda value: value.component_order
                )
                if component.ingredient and component.ingredient.is_active
            )
            structurally_valid = bool(
                expected_components
                and actual_components == expected_components
                and drug.component_count == len(expected_components)
                and drug.source_mapping_status == "MAPPED"
                and drug.review_status in {"PENDING_REVIEW", "APPROVED"}
                and all(
                    component.source_mapping_status == "MAPPED"
                    and component.review_status in {"PENDING_REVIEW", "APPROVED"}
                    for component in drug.components
                )
            )
            if structurally_valid:
                candidates.append(drug)
        return len(candidates), len(expected) - len(candidates), candidates

    @staticmethod
    def _bundled_version(session) -> KnowledgeBaseVersion:
        ledger = session.scalar(
            select(BundledDdiSeedApplication).where(
                BundledDdiSeedApplication.bundle_id == DDI_BUNDLE_ID
            )
        )
        if (
            ledger is None
            or ledger.bundle_checksum_sha256 != EXPECTED_BUNDLE_SHA256
            or ledger.rule_count != EXPECTED_RULE_COUNT
        ):
            raise H3ActivationError("Ledger katalog DDI bawaan tidak valid.")
        version = session.get(KnowledgeBaseVersion, ledger.knowledge_base_version_id)
        if version is None or version.version_code != DDI_BUNDLE_ID:
            raise H3ActivationError("Versi katalog DDI bawaan tidak ditemukan.")
        return version

    @classmethod
    def _authorize(cls, session, actor_user_id: str) -> AppUser:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id, AppUser.is_active.is_(True))
        )
        if user is None:
            raise H3ActivationError("Pengguna aktif tidak ditemukan.")
        if user.normalized_username == "mode.farmasi":
            raise H3ActivationError("Gunakan akun Super Admin/KFT bernama.")
        roles = {link.role.code for link in user.roles}
        if not roles.intersection(cls.ROLES):
            raise H3ActivationError("Hanya Super Admin atau KFT yang dapat mengaktifkan H3.")
        return user
