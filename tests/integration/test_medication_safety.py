from __future__ import annotations

import pytest

from emss.database.catalog_models import ActiveIngredient, DrugComponentMapping, DrugMaster
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.domain.knowledge import canonical_pair
from emss.services.screening import PrescriptionInput, PrescriptionItemInput


def _admin(container):
    return container.users.create_first_admin(
        username="admin.safety",
        display_name="Admin Safety",
        password="Password safety yang aman!",
    )


def _seed_catalog(container, admin_id: str) -> tuple[str, dict[str, str]]:
    with container.database.session() as session:
        ingredients: dict[str, ActiveIngredient] = {}
        for index in range(1, 6):
            name = f"zat {index}"
            ingredient = ActiveIngredient(standard_name=name, normalized_name=name)
            session.add(ingredient); session.flush(); ingredients[name] = ingredient
        version = KnowledgeBaseVersion(
            version_code="KB-SAFETY-TEST", title="KB safety test",
            status="PUBLISHED", created_by=admin_id,
        )
        session.add(version); session.flush()
        low, high, pair_key = canonical_pair("zat 1", "zat 2")
        session.add(DdiRule(
            knowledge_base_version_id=version.id,
            ingredient_low_id=ingredients[low].id,
            ingredient_high_id=ingredients[high].id,
            pair_key=pair_key,
            interaction_status="ASSESSED_NO_INTERACTION",
            severity_code="NONE", severity_rank=0, app_severity=None,
            source_name="Uji", source_validation_status="CONFIRMED",
            activation_status="ACTIVE", clinical_review_required=False,
            clinical_review_resolved=True, record_status="PUBLISHED",
            is_enabled=True, created_by=admin_id, updated_by=admin_id,
        ))
        specs = {
            "D1-A": "zat 1", "D1-B": "zat 1", "D2": "zat 2",
            "D3": "zat 3", "D4": "zat 4", "D5": "zat 5",
        }
        ids: dict[str, str] = {}
        for code, ingredient_name in specs.items():
            drug = DrugMaster(
                khanza_code=code, display_name=f"Obat {code}",
                normalized_name=code.casefold(), source_version="TEST",
                source_mapping_status="MAPPED", review_status="APPROVED",
                mapping_method="TEST", component_count=1,
            )
            session.add(drug); session.flush(); ids[code] = drug.id
            session.add(DrugComponentMapping(
                drug_id=drug.id, ingredient_id=ingredients[ingredient_name].id,
                component_order=1, source_mapping_status="MAPPED",
                mapping_method="TEST", review_status="APPROVED", is_active=True,
                source_version="TEST",
            ))
        session.commit()
        return version.id, ids


def _rx(no_resep: str, *codes: str) -> PrescriptionInput:
    return PrescriptionInput(
        no_resep=no_resep, service_unit="DEPO RAWAT JALAN",
        items=tuple(PrescriptionItemInput(
            source_item_key=str(index), khanza_code=code,
            display_name=f"Obat {code}", route="oral",
        ) for index, code in enumerate(codes, start=1)),
    )


@pytest.mark.integration
def test_duplicate_active_ingredient_requires_review(app_container) -> None:
    admin = _admin(app_container)
    version_id, _ = _seed_catalog(app_container, admin.id)

    result = app_container.screening.screen(
        _rx("RX-DUPLICATE", "D1-A", "D1-B"), admin.id, version_id=version_id
    )

    duplicate = [row for row in result.issues if row.issue_type == "DUPLICATE_THERAPY"]
    assert result.risk_status == "REVIEW"
    assert result.completeness_status == "COMPLETE"
    assert duplicate and duplicate[0].app_severity == "REVIEW"
    assert "zat 1" in duplicate[0].message


@pytest.mark.integration
def test_high_alert_default_is_review_alert_and_not_a_ddi_pair(app_container) -> None:
    admin = _admin(app_container)
    version_id, _ = _seed_catalog(app_container, admin.id)
    app_container.medication_safety.upsert_high_alert(
        admin.id,
        "D1-A",
        "High-alert uji",
        "Lakukan double-check.",
    )

    result = app_container.screening.screen(
        _rx("RX-HIGH-ALERT-ONLY", "D1-A"), admin.id, version_id=version_id
    )

    finding = next(row for row in result.issues if row.issue_type == "HIGH_ALERT")
    assert result.risk_status == "REVIEW"
    assert result.pair_count == 0 and result.interaction_count == 0
    assert finding.app_severity == "REVIEW"


@pytest.mark.integration
def test_polypharmacy_uses_unique_ingredients_and_configurable_threshold(app_container) -> None:
    admin = _admin(app_container)
    version_id, _ = _seed_catalog(app_container, admin.id)
    policy = app_container.medication_safety.get_policy()
    assert (policy.polypharmacy_threshold, policy.hyperpolypharmacy_threshold) == (5, 10)

    result = app_container.screening.screen(
        _rx("RX-POLY", "D1-A", "D2", "D3", "D4", "D5"),
        admin.id, version_id=version_id,
    )

    findings = [row for row in result.issues if row.issue_type == "POLYPHARMACY"]
    assert result.ingredient_count == 5
    assert result.risk_status == "INFO"
    assert findings and "5 zat aktif unik" in findings[0].message
    app_container.queue.enqueue_screening(result.screening_id)
    assert app_container.dashboard.summary().polypharmacy == 1


@pytest.mark.integration
def test_validated_class_high_alert_and_lasa_change_forces_new_revision(app_container) -> None:
    admin = _admin(app_container)
    version_id, _ = _seed_catalog(app_container, admin.id)
    prescription = _rx("RX-SAFETY-MASTER", "D1-A", "D2")
    before = app_container.screening.screen(prescription, admin.id, version_id=version_id)
    assert before.risk_status == "SAFE" and before.completeness_status == "COMPLETE"

    safety = app_container.medication_safety
    safety.upsert_therapy_profile(admin.id, "zat 1", "Kelas Uji", source="KFT")
    safety.upsert_therapy_profile(admin.id, "zat 2", "Kelas Uji", source="KFT")
    safety.upsert_high_alert(
        admin.id, "D1-A", "Elektrolit konsentrat", "Lakukan verifikasi dosis.",
        unit_scope="DEPO RAWAT JALAN", app_severity="HIGH_RISK",
    )
    safety.upsert_lasa_pair(
        admin.id, "D1-A", "D2", "LOOK_ALIKE", "Pisahkan lokasi penyimpanan.",
        unit_scope="DEPO RAWAT JALAN",
    )
    after = app_container.screening.screen(prescription, admin.id, version_id=version_id)

    assert after.revision_number == 2 and not after.reused
    assert after.prescription_hash != before.prescription_hash
    assert after.risk_status == "HIGH_RISK"
    assert {row.issue_type for row in after.issues} >= {"DUPLICATE_THERAPY", "HIGH_ALERT", "LASA"}
    high_alert = next(row for row in after.issues if row.issue_type == "HIGH_ALERT")
    assert "double-check" in high_alert.message
    app_container.queue.enqueue_screening(after.screening_id)
    summary = app_container.dashboard.summary()
    assert (summary.duplicate_therapy, summary.high_alert, summary.lasa) == (1, 1, 1)
