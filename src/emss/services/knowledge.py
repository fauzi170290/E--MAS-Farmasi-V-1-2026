from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session, selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.database.catalog_models import ActiveIngredient
from emss.database.engine import DatabaseManager
from emss.database.knowledge_models import (
    DdiRule,
    KnowledgeBaseTransition,
    KnowledgeBaseVersion,
)
from emss.database.models import AppUser, UserRole
from emss.domain.knowledge import (
    INTERACTION_STATUSES,
    KNOWLEDGE_STATUSES,
    canonical_pair,
    normalize_severity,
    validate_status_severity,
)
from emss.importexport.drug_import import normalize_name, normalize_text
from emss.utils.time import utc_now


class KnowledgeError(ValueError):
    pass


class KnowledgePermissionError(KnowledgeError):
    pass


class KnowledgeStateError(KnowledgeError):
    pass


@dataclass(frozen=True)
class ManualDdiRule:
    version_id: str
    ingredient_a: str
    ingredient_b: str
    interaction_status: str
    severity_code: str
    severity_label: str = ""
    clinical_effect: str = ""
    mechanism: str = ""
    recommendation: str = ""
    monitoring: str = ""
    population_risk: str = ""
    source_name: str = ""
    source_reference: str = ""
    source_accessed_at: date | None = None
    validated_by: str = ""
    validated_at: datetime | None = None
    clinical_review_resolved: bool = False
    notes: str = ""


@dataclass(frozen=True)
class KnowledgeVersionItem:
    id: str
    version_code: str
    title: str
    status: str
    rule_count: int
    unresolved_holds: int
    created_at: str


@dataclass(frozen=True)
class DdiRuleItem:
    id: str
    pair_key: str
    interaction_status: str
    severity_code: str
    app_severity: str | None
    clinical_effect: str
    recommendation: str
    activation_status: str
    record_status: str
    clinical_review_required: bool
    clinical_review_resolved: bool
    is_enabled: bool


@dataclass(frozen=True)
class DdiRuleDetail:
    id: str
    pair_key: str
    interaction_status: str
    severity_code: str
    severity_label: str
    app_severity: str
    clinical_effect: str
    mechanism: str
    recommendation: str
    monitoring: str
    population_risk: str
    source_name: str
    source_reference: str
    source_accessed_at: str
    source_evidence_count: int
    source_validation_status: str
    source_final_code: str
    clinical_review_required: bool
    clinical_review_resolved: bool
    validated_by_name: str
    validated_at: str
    notes: str


@dataclass(frozen=True)
class KnowledgeSummary:
    total_rules: int
    interactions: int
    assessed_no_interaction: int
    not_assessable: int
    excluded: int
    required_holds: int
    unresolved_holds: int
    enabled_rules: int


class KnowledgeBaseService:
    WRITER_ROLES = frozenset({"SUPER_ADMIN", "KNOWLEDGE_ADMIN"})
    REVIEWER_ROLES = frozenset({"SUPER_ADMIN", "CLINICAL_REVIEWER"})
    APPROVER_ROLES = frozenset({"SUPER_ADMIN", "KFT"})

    def __init__(self, database: DatabaseManager, audit: AuditService) -> None:
        self.database = database
        self.audit = audit

    def create_version(
        self,
        version_code: str,
        title: str,
        actor_user_id: str,
        *,
        description: str = "",
        based_on_version_id: str | None = None,
        source_checksum: str | None = None,
    ) -> str:
        code = normalize_text(version_code)
        clean_title = normalize_text(title)
        if not code or not clean_title:
            raise KnowledgeError("Kode versi dan judul wajib diisi")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.WRITER_ROLES)
            if session.scalar(
                select(KnowledgeBaseVersion.id).where(
                    KnowledgeBaseVersion.version_code == code
                )
            ):
                raise KnowledgeError(f"Versi knowledge base sudah ada: {code}")
            if based_on_version_id and session.get(
                KnowledgeBaseVersion, based_on_version_id
            ) is None:
                raise KnowledgeError("Versi sumber tidak ditemukan")
            version = KnowledgeBaseVersion(
                version_code=code,
                title=clean_title,
                description=normalize_text(description) or None,
                status="DRAFT",
                based_on_version_id=based_on_version_id,
                source_checksum=source_checksum,
                created_by=actor_user_id,
            )
            session.add(version)
            session.flush()
            self._record_transition(
                session, version, None, "DRAFT", "CREATE", actor_user_id, None
            )
            self._audit(
                session, "KNOWLEDGE_VERSION_CREATED", actor_user_id, version
            )
            session.commit()
            return version.id

    def duplicate_version(
        self,
        source_version_id: str,
        new_version_code: str,
        title: str,
        actor_user_id: str,
    ) -> str:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.WRITER_ROLES)
            source = session.scalar(
                select(KnowledgeBaseVersion)
                .options(selectinload(KnowledgeBaseVersion.rules))
                .where(KnowledgeBaseVersion.id == source_version_id)
            )
            if source is None:
                raise KnowledgeError("Versi sumber tidak ditemukan")
            code = normalize_text(new_version_code)
            if not code or session.scalar(
                select(KnowledgeBaseVersion.id).where(
                    KnowledgeBaseVersion.version_code == code
                )
            ):
                raise KnowledgeError("Kode versi baru kosong atau sudah digunakan")
            target = KnowledgeBaseVersion(
                version_code=code,
                title=normalize_text(title) or f"Salinan {source.title}",
                description=f"Diduplikasi dari {source.version_code}",
                status="DRAFT",
                based_on_version_id=source.id,
                created_by=actor_user_id,
            )
            session.add(target)
            session.flush()
            for rule in source.rules:
                session.add(
                    DdiRule(
                        knowledge_base_version_id=target.id,
                        external_pair_id=rule.external_pair_id,
                        ingredient_low_id=rule.ingredient_low_id,
                        ingredient_high_id=rule.ingredient_high_id,
                        pair_key=rule.pair_key,
                        interaction_status=rule.interaction_status,
                        severity_code=rule.severity_code,
                        severity_label=rule.severity_label,
                        severity_rank=rule.severity_rank,
                        app_severity=rule.app_severity,
                        clinical_effect=rule.clinical_effect,
                        mechanism=rule.mechanism,
                        recommendation=rule.recommendation,
                        monitoring=rule.monitoring,
                        population_risk=rule.population_risk,
                        source_name=rule.source_name,
                        source_reference=rule.source_reference,
                        source_accessed_at=rule.source_accessed_at,
                        source_batch=rule.source_batch,
                        source_evidence_count=rule.source_evidence_count,
                        source_validation_status=rule.source_validation_status,
                        source_final_code=rule.source_final_code,
                        activation_status="DRAFT",
                        clinical_review_required=rule.clinical_review_required,
                        clinical_review_resolved=(
                            False if rule.clinical_review_required else True
                        ),
                        record_status="DRAFT",
                        is_enabled=False,
                        validated_by_name=rule.validated_by_name,
                        validated_at=rule.validated_at,
                        notes=rule.notes,
                        created_by=actor_user_id,
                        updated_by=actor_user_id,
                    )
                )
            self._record_transition(
                session, target, None, "DRAFT", "DUPLICATE", actor_user_id, None
            )
            self._audit(
                session,
                "KNOWLEDGE_VERSION_DUPLICATED",
                actor_user_id,
                target,
                {"source_version_id": source.id, "rules": len(source.rules)},
            )
            session.commit()
            return target.id

    def save_manual_rule(
        self, data: ManualDdiRule, actor_user_id: str
    ) -> str:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.WRITER_ROLES)
            version = session.get(KnowledgeBaseVersion, data.version_id)
            if version is None:
                raise KnowledgeError("Versi knowledge base tidak ditemukan")
            if version.status != "DRAFT":
                raise KnowledgeStateError("Rule hanya dapat diubah pada versi DRAFT")
            low_name, high_name, pair_key = canonical_pair(
                data.ingredient_a, data.ingredient_b
            )
            ingredients = {
                row.normalized_name: row
                for row in session.scalars(
                    select(ActiveIngredient).where(
                        ActiveIngredient.normalized_name.in_((low_name, high_name))
                    )
                )
            }
            missing = [name for name in (low_name, high_name) if name not in ingredients]
            if missing:
                raise KnowledgeError(
                    "Zat aktif belum ada di master obat: " + ", ".join(missing)
                )
            interaction_status = normalize_text(data.interaction_status).upper()
            if interaction_status not in INTERACTION_STATUSES:
                raise KnowledgeError("Status interaksi tidak valid")
            try:
                severity_code, severity_rank, app_severity = normalize_severity(
                    data.severity_code
                )
                validate_status_severity(interaction_status, severity_code)
            except ValueError as exc:
                raise KnowledgeError(str(exc)) from exc
            source_name = normalize_text(data.source_name)
            if not source_name:
                raise KnowledgeError("Sumber wajib diisi")
            low_id, high_id = sorted(
                (ingredients[low_name].id, ingredients[high_name].id)
            )
            rule = session.scalar(
                select(DdiRule).where(
                    DdiRule.knowledge_base_version_id == version.id,
                    DdiRule.ingredient_low_id == low_id,
                    DdiRule.ingredient_high_id == high_id,
                )
            )
            action = "DDI_RULE_UPDATED" if rule else "DDI_RULE_CREATED"
            if rule is None:
                rule = DdiRule(
                    knowledge_base_version_id=version.id,
                    ingredient_low_id=low_id,
                    ingredient_high_id=high_id,
                    pair_key=pair_key,
                    created_by=actor_user_id,
                    updated_by=actor_user_id,
                    interaction_status=interaction_status,
                    severity_code=severity_code,
                    severity_rank=severity_rank,
                    source_name=source_name,
                )
                session.add(rule)
            rule.interaction_status = interaction_status
            rule.severity_code = severity_code
            rule.severity_label = normalize_text(data.severity_label) or None
            rule.severity_rank = severity_rank
            rule.app_severity = app_severity
            rule.clinical_effect = normalize_text(data.clinical_effect) or None
            rule.mechanism = normalize_text(data.mechanism) or None
            rule.recommendation = normalize_text(data.recommendation) or None
            rule.monitoring = normalize_text(data.monitoring) or None
            rule.population_risk = normalize_text(data.population_risk) or None
            rule.source_name = source_name
            rule.source_reference = normalize_text(data.source_reference) or None
            rule.source_accessed_at = data.source_accessed_at
            rule.activation_status = "DRAFT"
            rule.clinical_review_required = (
                interaction_status == "INTERACTION_FOUND"
                and severity_code in {"SIGNIFICANT", "SERIOUS", "CONTRAINDICATED"}
            )
            rule.clinical_review_resolved = bool(data.clinical_review_resolved)
            rule.record_status = "DRAFT"
            rule.is_enabled = False
            rule.validated_by_name = normalize_text(data.validated_by) or None
            rule.validated_at = data.validated_at
            rule.notes = normalize_text(data.notes) or None
            rule.updated_by = actor_user_id
            session.flush()
            self._audit(
                session,
                action,
                actor_user_id,
                version,
                {"rule_id": rule.id, "pair_key": pair_key},
            )
            session.commit()
            return rule.id

    def review_version(
        self, version_id: str, actor_user_id: str, reason: str = ""
    ) -> None:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.REVIEWER_ROLES)
            version = self._version_for_transition(session, version_id, "DRAFT")
            unresolved = self._unresolved_count(session, version.id)
            if unresolved:
                raise KnowledgeStateError(
                    f"{unresolved} rule HOLD masih memerlukan review klinis"
                )
            self._transition(
                session, version, "REVIEWED", "REVIEW", actor_user_id, reason
            )
            version.reviewed_by = actor_user_id
            version.reviewed_at = utc_now()
            session.commit()

    def resolve_rule_review(
        self, rule_id: str, actor_user_id: str, reason: str
    ) -> None:
        clean_reason = normalize_text(reason)
        if not clean_reason:
            raise KnowledgeError("Catatan review klinis wajib diisi")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.REVIEWER_ROLES)
            user = session.get(AppUser, actor_user_id)
            rule = session.get(DdiRule, rule_id)
            if rule is None:
                raise KnowledgeError("Rule DDI tidak ditemukan")
            version = session.get(
                KnowledgeBaseVersion, rule.knowledge_base_version_id
            )
            if version is None or version.status != "DRAFT":
                raise KnowledgeStateError(
                    "Review rule hanya dapat dilakukan pada versi DRAFT"
                )
            if not rule.clinical_review_required:
                raise KnowledgeStateError("Rule ini tidak memerlukan HOLD klinis")
            rule.clinical_review_resolved = True
            rule.validated_by_name = user.display_name if user else None
            rule.validated_at = utc_now()
            rule.updated_by = actor_user_id
            rule.notes = (
                f"{rule.notes}\nClinical review: {clean_reason}"
                if rule.notes
                else f"Clinical review: {clean_reason}"
            )
            self._audit(
                session,
                "DDI_RULE_CLINICAL_REVIEW_RESOLVED",
                actor_user_id,
                version,
                {"rule_id": rule.id, "pair_key": rule.pair_key},
            )
            session.commit()

    def approve_version(
        self, version_id: str, actor_user_id: str, reason: str = ""
    ) -> None:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.APPROVER_ROLES)
            version = self._version_for_transition(session, version_id, "REVIEWED")
            self._transition(
                session, version, "APPROVED", "APPROVE", actor_user_id, reason
            )
            version.approved_by = actor_user_id
            version.approved_at = utc_now()
            session.commit()

    def publish_version(
        self, version_id: str, actor_user_id: str, reason: str = ""
    ) -> None:
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.APPROVER_ROLES)
            version = self._version_for_transition(session, version_id, "APPROVED")
            for current in session.scalars(
                select(KnowledgeBaseVersion).where(
                    KnowledgeBaseVersion.status == "PUBLISHED",
                    KnowledgeBaseVersion.id != version.id,
                )
            ):
                self._transition(
                    session,
                    current,
                    "RETIRED",
                    "SUPERSEDE",
                    actor_user_id,
                    f"Digantikan oleh {version.version_code}",
                )
                current.retired_by = actor_user_id
                current.retired_at = utc_now()
            self._transition(
                session, version, "PUBLISHED", "PUBLISH", actor_user_id, reason
            )
            version.published_by = actor_user_id
            version.published_at = utc_now()
            session.commit()

    def retire_version(
        self, version_id: str, actor_user_id: str, reason: str
    ) -> None:
        if not normalize_text(reason):
            raise KnowledgeError("Alasan retirement wajib diisi")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.APPROVER_ROLES)
            version = self._version_for_transition(session, version_id, "PUBLISHED")
            self._transition(
                session, version, "RETIRED", "RETIRE", actor_user_id, reason
            )
            version.retired_by = actor_user_id
            version.retired_at = utc_now()
            session.commit()

    def rollback_to(
        self, target_version_id: str, actor_user_id: str, reason: str
    ) -> None:
        if not normalize_text(reason):
            raise KnowledgeError("Alasan rollback wajib diisi")
        with self.database.session() as session:
            self._require_roles(session, actor_user_id, self.APPROVER_ROLES)
            target = session.get(KnowledgeBaseVersion, target_version_id)
            if target is None or target.status not in {"APPROVED", "RETIRED"}:
                raise KnowledgeStateError(
                    "Rollback hanya dapat menuju versi APPROVED atau RETIRED"
                )
            if self._unresolved_count(session, target.id):
                raise KnowledgeStateError("Versi target masih memiliki HOLD klinis")
            for current in session.scalars(
                select(KnowledgeBaseVersion).where(
                    KnowledgeBaseVersion.status == "PUBLISHED"
                )
            ):
                self._transition(
                    session,
                    current,
                    "RETIRED",
                    "ROLLBACK_REPLACED",
                    actor_user_id,
                    reason,
                )
                current.retired_by = actor_user_id
                current.retired_at = utc_now()
            self._transition(
                session, target, "PUBLISHED", "ROLLBACK", actor_user_id, reason
            )
            target.published_by = actor_user_id
            target.published_at = utc_now()
            session.commit()

    def list_versions(self) -> list[KnowledgeVersionItem]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    KnowledgeBaseVersion,
                    func.count(DdiRule.id),
                    func.sum(
                        DdiRule.clinical_review_required.cast(type_=Integer)
                        * (1 - DdiRule.clinical_review_resolved.cast(type_=Integer))
                    ),
                )
                .outerjoin(
                    DdiRule,
                    DdiRule.knowledge_base_version_id == KnowledgeBaseVersion.id,
                )
                .group_by(KnowledgeBaseVersion.id)
                .order_by(KnowledgeBaseVersion.created_at.desc())
            ).all()
            return [
                KnowledgeVersionItem(
                    id=version.id,
                    version_code=version.version_code,
                    title=version.title,
                    status=version.status,
                    rule_count=int(rule_count or 0),
                    unresolved_holds=int(unresolved or 0),
                    created_at=version.created_at.isoformat(timespec="seconds"),
                )
                for version, rule_count, unresolved in rows
            ]

    def summary(self, version_id: str) -> KnowledgeSummary:
        with self.database.session() as session:
            counts = {
                status: int(
                    session.scalar(
                        select(func.count())
                        .select_from(DdiRule)
                        .where(
                            DdiRule.knowledge_base_version_id == version_id,
                            DdiRule.interaction_status == status,
                        )
                    )
                    or 0
                )
                for status in INTERACTION_STATUSES
            }
            required_holds = int(
                session.scalar(
                    select(func.count())
                    .select_from(DdiRule)
                    .where(
                        DdiRule.knowledge_base_version_id == version_id,
                        DdiRule.clinical_review_required.is_(True),
                    )
                )
                or 0
            )
            return KnowledgeSummary(
                total_rules=sum(counts.values()),
                interactions=counts["INTERACTION_FOUND"],
                assessed_no_interaction=counts["ASSESSED_NO_INTERACTION"],
                not_assessable=counts["NOT_ASSESSABLE"],
                excluded=counts["EXCLUDED"],
                required_holds=required_holds,
                unresolved_holds=self._unresolved_count(session, version_id),
                enabled_rules=int(
                    session.scalar(
                        select(func.count())
                        .select_from(DdiRule)
                        .where(
                            DdiRule.knowledge_base_version_id == version_id,
                            DdiRule.is_enabled.is_(True),
                        )
                    )
                    or 0
                ),
            )

    def list_rules(
        self,
        version_id: str,
        search: str = "",
        limit: int = 1000,
        filter_code: str = "ALL",
    ) -> list[DdiRuleItem]:
        with self.database.session() as session:
            selected_filter = normalize_text(filter_code).upper() or "ALL"
            allowed_filters = {
                "ALL",
                "UNRESOLVED_HOLD",
                "RESOLVED_HOLD",
                "CRITICAL",
                "HIGH_RISK",
                "INTERACTION_FOUND",
            }
            if selected_filter not in allowed_filters:
                raise KnowledgeError("Filter rule DDI tidak valid")
            statement = (
                select(DdiRule)
                .where(DdiRule.knowledge_base_version_id == version_id)
                .order_by(DdiRule.severity_rank.desc(), DdiRule.pair_key)
                .limit(max(1, min(limit, 10000)))
            )
            if selected_filter == "UNRESOLVED_HOLD":
                statement = statement.where(
                    DdiRule.clinical_review_required.is_(True),
                    DdiRule.clinical_review_resolved.is_(False),
                )
            elif selected_filter == "RESOLVED_HOLD":
                statement = statement.where(
                    DdiRule.clinical_review_required.is_(True),
                    DdiRule.clinical_review_resolved.is_(True),
                )
            elif selected_filter in {"CRITICAL", "HIGH_RISK"}:
                statement = statement.where(
                    DdiRule.app_severity == selected_filter
                )
            elif selected_filter == "INTERACTION_FOUND":
                statement = statement.where(
                    DdiRule.interaction_status == "INTERACTION_FOUND"
                )
            query = normalize_text(search)
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(
                        DdiRule.pair_key.ilike(pattern),
                        DdiRule.clinical_effect.ilike(pattern),
                        DdiRule.source_name.ilike(pattern),
                    )
                )
            rows = session.scalars(statement).all()
            return [
                DdiRuleItem(
                    id=row.id,
                    pair_key=row.pair_key,
                    interaction_status=row.interaction_status,
                    severity_code=row.severity_code,
                    app_severity=row.app_severity,
                    clinical_effect=row.clinical_effect or "",
                    recommendation=row.recommendation or "",
                    activation_status=row.activation_status,
                    record_status=row.record_status,
                    clinical_review_required=row.clinical_review_required,
                    clinical_review_resolved=row.clinical_review_resolved,
                    is_enabled=row.is_enabled,
                )
                for row in rows
            ]

    def get_rule_detail(self, rule_id: str) -> DdiRuleDetail:
        with self.database.session() as session:
            row = session.get(DdiRule, rule_id)
            if row is None:
                raise KnowledgeError("Rule DDI tidak ditemukan")
            return DdiRuleDetail(
                id=row.id,
                pair_key=row.pair_key,
                interaction_status=row.interaction_status,
                severity_code=row.severity_code,
                severity_label=row.severity_label or "",
                app_severity=row.app_severity or "",
                clinical_effect=row.clinical_effect or "",
                mechanism=row.mechanism or "",
                recommendation=row.recommendation or "",
                monitoring=row.monitoring or "",
                population_risk=row.population_risk or "",
                source_name=row.source_name,
                source_reference=row.source_reference or "",
                source_accessed_at=(
                    row.source_accessed_at.isoformat()
                    if row.source_accessed_at
                    else ""
                ),
                source_evidence_count=row.source_evidence_count,
                source_validation_status=row.source_validation_status or "",
                source_final_code=row.source_final_code or "",
                clinical_review_required=row.clinical_review_required,
                clinical_review_resolved=row.clinical_review_resolved,
                validated_by_name=row.validated_by_name or "",
                validated_at=(
                    row.validated_at.isoformat(timespec="seconds")
                    if row.validated_at
                    else ""
                ),
                notes=row.notes or "",
            )

    def _transition(
        self,
        session: Session,
        version: KnowledgeBaseVersion,
        new_status: str,
        action: str,
        actor_user_id: str,
        reason: str,
    ) -> None:
        old_status = version.status
        version.status = new_status
        version.updated_at = utc_now()
        rule_status = new_status
        for rule in session.scalars(
            select(DdiRule).where(
                DdiRule.knowledge_base_version_id == version.id
            )
        ):
            rule.record_status = rule_status
            rule.is_enabled = (
                new_status == "PUBLISHED"
                and rule.interaction_status == "INTERACTION_FOUND"
                and rule.severity_code != "NONE"
                and not (
                    rule.clinical_review_required
                    and not rule.clinical_review_resolved
                )
            )
            rule.updated_by = actor_user_id
        self._record_transition(
            session,
            version,
            old_status,
            new_status,
            action,
            actor_user_id,
            normalize_text(reason) or None,
        )
        self._audit(
            session,
            f"KNOWLEDGE_VERSION_{action}",
            actor_user_id,
            version,
            {"from": old_status, "to": new_status, "reason": reason},
        )

    @staticmethod
    def _record_transition(
        session: Session,
        version: KnowledgeBaseVersion,
        old_status: str | None,
        new_status: str,
        action: str,
        actor_user_id: str,
        reason: str | None,
    ) -> None:
        session.add(
            KnowledgeBaseTransition(
                knowledge_base_version_id=version.id,
                from_status=old_status,
                to_status=new_status,
                action=action,
                reason=reason,
                actor_user_id=actor_user_id,
            )
        )

    def _audit(
        self,
        session: Session,
        action: str,
        actor_user_id: str,
        version: KnowledgeBaseVersion,
        details: dict[str, object] | None = None,
    ) -> None:
        self.audit.append(
            session,
            AuditEvent(
                category="CLINICAL_AUDIT",
                action=action,
                outcome="SUCCESS",
                actor_user_id=actor_user_id,
                entity_type="KNOWLEDGE_BASE_VERSION",
                entity_id=version.id,
                details={"version_code": version.version_code, **(details or {})},
            ),
        )

    @staticmethod
    def _version_for_transition(
        session: Session, version_id: str, expected_status: str
    ) -> KnowledgeBaseVersion:
        version = session.get(KnowledgeBaseVersion, version_id)
        if version is None:
            raise KnowledgeError("Versi knowledge base tidak ditemukan")
        if version.status != expected_status:
            raise KnowledgeStateError(
                f"Status versi harus {expected_status}, saat ini {version.status}"
            )
        return version

    @staticmethod
    def _unresolved_count(session: Session, version_id: str) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(DdiRule)
                .where(
                    DdiRule.knowledge_base_version_id == version_id,
                    DdiRule.clinical_review_required.is_(True),
                    DdiRule.clinical_review_resolved.is_(False),
                )
            )
            or 0
        )

    @staticmethod
    def _require_roles(
        session: Session, actor_user_id: str, allowed_roles: frozenset[str]
    ) -> None:
        user = session.scalar(
            select(AppUser)
            .options(selectinload(AppUser.roles).selectinload(UserRole.role))
            .where(AppUser.id == actor_user_id, AppUser.is_active.is_(True))
        )
        if user is None:
            raise KnowledgePermissionError("Pengguna aktif tidak ditemukan")
        roles = {link.role.code for link in user.roles}
        if not roles.intersection(allowed_roles):
            raise KnowledgePermissionError(
                "Role tidak berwenang melakukan operasi knowledge base"
            )
