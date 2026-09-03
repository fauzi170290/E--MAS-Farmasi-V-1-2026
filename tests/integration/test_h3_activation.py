from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from emss.database.catalog_models import ActiveIngredient, DrugComponentMapping, DrugMaster
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.database.models import AuditLog
from emss.services.h3_activation import H3ActivationError
from emss.services.knowledge import ManualDdiRule
from test_screening_engine import _admin, _prescription


def _prepare(container):
    admin = _admin(container)
    container.bundled_ddi.apply_if_eligible(admin.id)
    container.bundled_mapping.apply_if_eligible(admin.id)
    return admin


@pytest.mark.integration
def test_h3_activates_only_safe_positive_cohort_and_khanza_mappings(app_container):
    container = app_container
    admin = _prepare(container)

    preview = container.h3_activation.preview()
    assert preview.version_status == "DRAFT"
    assert (
        preview.eligible_pairs,
        preview.active_pairs,
        preview.held_pairs,
        preview.draft_pairs,
    ) == (379, 0, 175, 11)
    assert (preview.mapping_eligible, preview.mapping_blocked) == (414, 0)

    result = container.h3_activation.activate(
        admin.id, "Validasi KFT sintetis untuk pengujian H3"
    )

    assert result.version_status == "PUBLISHED"
    assert result.active_pairs == 379
    assert result.held_pairs == 175
    assert result.draft_pairs == 11
    assert result.mapping_eligible == 414
    assert not result.already_active
    with container.database.session() as session:
        version = session.get(KnowledgeBaseVersion, result.version_id)
        assert version.status == "PUBLISHED"
        assert session.execute(
            text(
                "SELECT COUNT(*) FROM ddi_rule WHERE "
                "knowledge_base_version_id=:version AND is_enabled=1 "
                "AND activation_status='ACTIVE' AND record_status='PUBLISHED'"
            ),
            {"version": result.version_id},
        ).scalar_one() == 379
        assert session.execute(
            text(
                "SELECT COUNT(*) FROM ddi_rule WHERE "
                "knowledge_base_version_id=:version AND "
                "activation_status='HOLD_CLINICAL_REVIEW_REQUIRED' AND is_enabled=0"
            ),
            {"version": result.version_id},
        ).scalar_one() == 175
        assert session.execute(
            text(
                "SELECT COUNT(*) FROM ddi_rule WHERE "
                "knowledge_base_version_id=:version AND "
                "activation_status='DRAFT' AND is_enabled=0"
            ),
            {"version": result.version_id},
        ).scalar_one() == 11
        assert session.execute(
            text("SELECT COUNT(*) FROM drug_master WHERE review_status='APPROVED'")
        ).scalar_one() == 414
        assert session.execute(
            text(
                "SELECT COUNT(*) FROM drug_component_mapping WHERE "
                "review_status='APPROVED' AND is_active=1"
            )
        ).scalar_one() == 444
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "H3_CONTROLLED_ACTIVATION")
        )
        assert audit is not None
        assert container.audit.verify_chain(session)

    # The H1 integrity check must accept the intentionally published bundle.
    assert container.bundled_ddi.apply_if_eligible(admin.id).status == "ALREADY_APPLIED"
    repeated = container.h3_activation.activate(
        admin.id, "Validasi ulang idempotensi H3"
    )
    assert repeated.already_active
    assert repeated.active_pairs == 379


@pytest.mark.integration
def test_h3_active_pair_is_used_by_real_khanza_code_screening(app_container):
    container = app_container
    admin = _prepare(container)
    activated = container.h3_activation.activate(
        admin.id, "Validasi KFT sintetis untuk skrining Khanza"
    )

    with container.database.session() as session:
        rules = session.scalars(
            select(DdiRule).where(
                DdiRule.knowledge_base_version_id == activated.version_id,
                DdiRule.is_enabled.is_(True),
            )
        ).all()
        codes = None
        chosen = None
        for rule in rules:
            found = []
            for ingredient_id in (rule.ingredient_low_id, rule.ingredient_high_id):
                drug = session.scalar(
                    select(DrugMaster)
                    .join(DrugComponentMapping)
                    .where(
                        DrugComponentMapping.ingredient_id == ingredient_id,
                        DrugComponentMapping.is_active.is_(True),
                        DrugComponentMapping.review_status == "APPROVED",
                        DrugMaster.review_status == "APPROVED",
                        DrugMaster.is_active.is_(True),
                    )
                    .order_by(DrugMaster.khanza_code)
                    .limit(1)
                )
                if drug is None:
                    break
                found.append(drug.khanza_code)
            if len(found) == 2 and found[0] != found[1]:
                codes = tuple(found)
                chosen = rule
                break
        assert codes is not None and chosen is not None

    screened = container.screening.screen(_prescription(codes), admin.id)

    assert screened.interaction_count >= 1
    selected = next(
        pair for pair in screened.pairs if pair.classification == "INTERACTION_FOUND"
    )
    assert selected.pair_key == chosen.pair_key
    assert selected.severity_code == chosen.severity_code


@pytest.mark.integration
def test_h5_hold_validation_records_named_evidence_without_activation(app_container):
    container = app_container
    admin = _prepare(container)
    container.h3_activation.activate(admin.id, "Validasi H3 sebelum verifikasi HOLD")

    preview = container.h3_activation.preview_hold_cohort()
    assert preview.hold_pairs == 175
    assert dict(preview.severity_counts) == {
        "CONTRAINDICATED": 1,
        "MINOR": 30,
        "SERIOUS": 24,
        "SIGNIFICANT": 120,
    }
    assert preview.source_references == 168
    assert len(preview.missing_source_reference_pairs) == 7
    assert not preview.activation_ready

    result = container.h3_activation.validate_hold_cohort(
        admin.id, "Validasi KFT cohort HOLD untuk aktivasi H5"
    )
    assert result.hold_pairs == 175
    assert result.validated_by
    assert not result.activation_ready
    with container.database.session() as session:
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE activation_status="
                 "'HOLD_CLINICAL_REVIEW_REQUIRED' AND is_enabled=1")
        ).scalar_one() == 0
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "H5_HOLD_COHORT_VALIDATED")
        )
        assert audit is not None
        assert audit.outcome == "NEEDS_REVIEW"
        assert container.audit.verify_chain(session)


@pytest.mark.integration
def test_h5_hold_validation_fails_closed_when_clinical_evidence_changes(app_container):
    container = app_container
    admin = _prepare(container)
    with container.database.session() as session:
        held = session.scalar(
            select(DdiRule).where(
                DdiRule.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED"
            )
        )
        held.source_reference = ""
        session.commit()
    with pytest.raises(H3ActivationError, match="kontrak H5"):
        container.h3_activation.preview_hold_cohort()


@pytest.mark.integration
def test_h5_activates_all_hold_pairs_after_named_validation(app_container):
    container = app_container
    admin = _prepare(container)
    container.h3_activation.activate(admin.id, "Validasi H3 sebelum aktivasi cohort HOLD")
    validation = container.h3_activation.validate_hold_cohort(
        admin.id, "Keputusan KFT untuk aktivasi semua cohort HOLD"
    )
    assert not validation.activation_ready

    result = container.h3_activation.activate_hold_cohort(
        admin.id, "Keputusan KFT untuk aktivasi semua cohort HOLD"
    )
    assert result.activated_hold_pairs == 175
    assert result.active_pairs == 554
    assert len(result.missing_source_reference_pairs) == 7
    with container.database.session() as session:
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE activation_status='ACTIVE' "
                 "AND is_enabled=1")
        ).scalar_one() == 554
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE activation_status="
                 "'HOLD_CLINICAL_REVIEW_REQUIRED'")
        ).scalar_one() == 0
        activation_audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "H5_HOLD_COHORT_ACTIVATED")
        )
        assert activation_audit is not None
        assert container.audit.verify_chain(session)


@pytest.mark.integration
def test_assessed_no_interaction_pairs_become_safe_reference_not_alert(app_container):
    container = app_container
    admin = _prepare(container)
    container.h3_activation.activate(admin.id, "Validasi H3 sebelum basis referensi aman")

    result = container.h3_activation.activate_no_interaction_reference_basis(
        admin.id, "Keputusan KFT mengaktifkan basis pemeriksaan aman"
    )
    assert result.activated_reference_pairs == 3646
    assert result.already_active_pairs == 0
    with container.database.session() as session:
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE interaction_status="
                 "'ASSESSED_NO_INTERACTION' AND severity_code='NONE' "
                 "AND activation_status='ACTIVE' AND is_enabled=1")
        ).scalar_one() == 3646
        assert session.execute(
            text("SELECT COUNT(*) FROM ddi_rule WHERE interaction_status="
                 "'ASSESSED_NO_INTERACTION' AND app_severity IS NOT NULL")
        ).scalar_one() == 0
        assert session.scalar(
            select(AuditLog).where(
                AuditLog.action == "DDI_NO_INTERACTION_REFERENCE_ACTIVATED"
            )
        ) is not None
        assert container.audit.verify_chain(session)


@pytest.mark.integration
def test_h5_uses_published_local_snapshot_and_preserves_previously_active_hold(app_container):
    container = app_container
    admin = _prepare(container)
    activated = container.h3_activation.activate(
        admin.id, "Validasi H3 sebelum perubahan pair lokal"
    )
    with container.database.session() as session:
        active = session.scalar(select(DdiRule).where(
            DdiRule.knowledge_base_version_id == activated.version_id,
            DdiRule.activation_status == "ACTIVE",
        ))
        low = session.get(ActiveIngredient, active.ingredient_low_id).standard_name
        high = session.get(ActiveIngredient, active.ingredient_high_id).standard_name
        data = ManualDdiRule(
            version_id=activated.version_id, ingredient_a=low, ingredient_b=high,
            interaction_status=active.interaction_status,
            severity_code=active.severity_code, source_name=active.source_name,
            source_reference=active.source_reference, source_accessed_at=active.source_accessed_at,
            clinical_effect=active.clinical_effect or "", recommendation=active.recommendation or "",
            monitoring=active.monitoring or "", mechanism=active.mechanism or "",
            population_risk=active.population_risk or "", notes=active.notes or "",
        )
        active_rule_id = active.id
    container.reference.save_pair(
        data, admin.id, expected_version_id=activated.version_id,
        edit_rule_id=active_rule_id, active=True,
    )
    with container.database.session() as session:
        local = session.scalar(select(KnowledgeBaseVersion).where(
            KnowledgeBaseVersion.status == "PUBLISHED",
            KnowledgeBaseVersion.version_code.like("LOCAL-%"),
        ))
        held = session.scalar(select(DdiRule).where(
            DdiRule.knowledge_base_version_id == local.id,
            DdiRule.activation_status == "HOLD_CLINICAL_REVIEW_REQUIRED",
        ))
        held.activation_status, held.is_enabled = "ACTIVE", True
        held.clinical_review_resolved = True
        session.commit()

    preview = container.h3_activation.preview_hold_cohort()
    assert (preview.version_id, preview.hold_pairs, preview.already_active_pairs) == (
        local.id, 174, 1
    )
    container.h3_activation.validate_hold_cohort(
        admin.id, "Validasi KFT pada snapshot lokal terpublikasi"
    )
    result = container.h3_activation.activate_hold_cohort(
        admin.id, "Aktivasi HOLD tersisa pada snapshot lokal"
    )
    assert (result.activated_hold_pairs, result.already_active_pairs, result.active_pairs) == (174, 1, 554)


@pytest.mark.integration
def test_h3_denies_unprivileged_actor_and_changed_mapping(app_container):
    container = app_container
    admin = _prepare(container)
    pharmacist = container.users.create_user(
        username="apoteker.h3",
        display_name="Apoteker H3",
        password="Password apoteker H3 aman!",
        roles=("APOTEKER",),
        actor_user_id=admin.id,
    )
    with pytest.raises(H3ActivationError, match="Super Admin atau KFT"):
        container.h3_activation.activate(
            pharmacist.id, "Percobaan tanpa kewenangan H3"
        )

    with container.database.session() as session:
        drug = session.scalar(
            select(DrugMaster)
            .options(selectinload(DrugMaster.components))
            .order_by(DrugMaster.khanza_code)
        )
        changed_drug_id = drug.id
        drug.component_count += 1
        session.commit()
    preview = container.h3_activation.preview()
    assert preview.mapping_eligible == 413
    assert preview.mapping_blocked == 1
    result = container.h3_activation.activate(
        admin.id, "Validasi H3 dengan satu pemetaan diblokir"
    )
    assert result.mapping_eligible == 413
    assert result.mapping_blocked == 1
    with container.database.session() as session:
        changed = session.get(DrugMaster, changed_drug_id)
        assert changed.review_status == "PENDING_REVIEW"
