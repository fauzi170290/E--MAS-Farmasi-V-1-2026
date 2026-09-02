from dataclasses import replace
import pytest
from sqlalchemy import select, func
from test_screening_engine import _admin, _seed, _prescription
from emss.services.reference import DrugEdit
from emss.services.knowledge import ManualDdiRule, KnowledgeError
from emss.database.knowledge_models import DdiRule, KnowledgeBaseVersion
from emss.database.models import AuditLog
from emss.database.catalog_models import DrugMaster


def data(**kwargs):
    return ManualDdiRule(version_id="", ingredient_a="zat a", ingredient_b="zat b",
        interaction_status="INTERACTION_FOUND", severity_code="SERIOUS",
        source_name="Sumber sintetis", source_reference="UAT-REF-67", **kwargs)


def test_pair_activation_keeps_other_rules_drafts_and_history(app_container):
    c = app_container
    admin = _admin(c)
    base, codes = _seed(c, admin.id)
    original = c.screening.screen(_prescription(codes), admin.id)
    draft = c.knowledge.create_version("DRAFT-UNRELATED", "Draft", admin.id)
    draft_id = c.knowledge.save_manual_rule(replace(data(), version_id=draft), admin.id)
    old = c.knowledge.list_rules(base)[0]
    active = c.reference.save_pair(data(), admin.id, expected_version_id=base, edit_rule_id=old.id)
    current = c.reference.active_version_id()
    result = c.screening.screen(_prescription(codes), admin.id)
    assert result.knowledge_base_version != original.knowledge_base_version
    assert result.pairs[0].severity_code == "SERIOUS"
    assert original.pairs[0].severity_code == "CONTRAINDICATED"
    assert c.reference.pair_detail(old.id)["severity_code"] == "CONTRAINDICATED"
    assert c.reference.pair_detail(draft_id)["activation_status"] == "DRAFT"
    assert not c.reference.pair_detail(draft_id)["is_enabled"]
    with c.database.session() as s:
        assert c.audit.verify_chain(s)
        assert s.get(KnowledgeBaseVersion, draft).status == "DRAFT"
    extra = replace(data(), ingredient_b="zat c", severity_code="MINOR")
    c.reference.save_pair(extra, admin.id, expected_version_id=current)
    new = c.knowledge.list_rules(c.reference.active_version_id())
    assert len(new) == 2
    assert next(x for x in new if x.pair_key == "zat a || zat b").severity_code == "SERIOUS"


def test_kft_drug_mapping_pair_immediate_and_denied_other_roles(app_container):
    c = app_container
    admin = _admin(c)
    kft = c.users.create_user(username="kft.editor", display_name="KFT", password="Password KFT uji aman!",
        roles=("KFT",), actor_user_id=admin.id)
    pharmacist = c.users.create_user(username="apoteker.read", display_name="Apoteker",
        password="Password apoteker aman!", roles=("APOTEKER",), actor_user_id=admin.id)
    ids = [c.reference.save_drug(DrugEdit(name=f"Obat {name}", ingredients=(name,),
        reference="Bukti komposisi UAT"), kft.id) for name in ("zat a", "zat b")]
    drugs = [c.reference.drug_detail(x) for x in ids]
    assert all(d["code"].startswith("LOCAL:") for d in drugs)
    c.reference.save_pair(data(), kft.id, expected_version_id="")
    result = c.screening.screen(_prescription(tuple(d["code"] for d in drugs)), kft.id)
    assert result.pairs[0].classification == "INTERACTION_FOUND"
    assert result.completeness_status == "COMPLETE"
    with pytest.raises(KnowledgeError):
        c.reference.save_drug(DrugEdit(name="Obat ilegal", ingredients=("zat x",),
            reference="UAT"), pharmacist.id)
    with pytest.raises(KnowledgeError):
        c.reference.save_pair(data(), pharmacist.id, expected_version_id=c.reference.active_version_id())


def test_conflicts_references_and_failed_audit_are_atomic(app_container, monkeypatch):
    c = app_container
    admin = _admin(c)
    base, _ = _seed(c, admin.id)
    old = c.knowledge.list_rules(base)[0]
    for bad in (replace(data(), source_reference=""), replace(data(), ingredient_b="zat a")):
        with pytest.raises(ValueError):
            c.reference.save_pair(bad, admin.id, expected_version_id=base, edit_rule_id=old.id)
    with pytest.raises(KnowledgeError, match="sudah ada"):
        c.reference.save_pair(data(), admin.id, expected_version_id=base)
    with pytest.raises(KnowledgeError, match="berubah"):
        c.reference.save_pair(data(), admin.id, expected_version_id="wrong", edit_rule_id=old.id)
    with c.database.session() as s:
        versions = s.scalar(select(func.count()).select_from(KnowledgeBaseVersion))
    def fail(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(c.audit, "append", fail)
        with pytest.raises(RuntimeError):
            c.reference.save_pair(data(), admin.id, expected_version_id=base, edit_rule_id=old.id)
    assert c.reference.active_version_id() == base
    with c.database.session() as s:
        assert s.scalar(select(func.count()).select_from(KnowledgeBaseVersion)) == versions


def test_edit_mapping_conflict_and_deactivation(app_container):
    c = app_container
    admin = _admin(c)
    base, codes = _seed(c, admin.id)
    drug_id = c.catalog.list_drugs(codes[0])[0].id
    old = c.reference.drug_detail(drug_id)
    edit = DrugEdit(name=old["name"], code=old["code"], ingredients=("zat c",), reference="Updated UAT",
        drug_id=drug_id, expected_updated_at=old["updated_at"])
    c.reference.save_drug(edit, admin.id)
    with pytest.raises(KnowledgeError, match="berubah"):
        c.reference.save_drug(edit, admin.id)
    assert c.reference.drug_detail(drug_id)["ingredients"] == ("zat c",)
    rule = c.knowledge.list_rules(base)[0]
    c.reference.save_pair(data(), admin.id, expected_version_id=base, edit_rule_id=rule.id, active=False)
    assert not c.knowledge.list_rules(c.reference.active_version_id())[0].is_enabled
    assert c.screening.screen(_prescription(codes), admin.id).interaction_count == 0


def test_inactive_rule_does_not_count_as_positive_in_dashboard(app_container):
    c = app_container
    admin = _admin(c)
    base, codes = _seed(c, admin.id)
    rule = c.knowledge.list_rules(base)[0]
    c.reference.save_pair(data(), admin.id, expected_version_id=base, edit_rule_id=rule.id, active=False)
    result = c.screening.screen(_prescription(codes), admin.id)
    c.queue.enqueue_screening(result.screening_id)
    assert result.not_assessed_count == 1
    summary = c.dashboard.summary("ALL")
    assert summary.serious_pairs == 0 and summary.unique_ddi_pairs == 0
    assert summary.not_assessed_pairs == 1


@pytest.mark.parametrize("role", ["APOTEKER", "CLINICAL_REVIEWER", "KNOWLEDGE_ADMIN", "IT_ADMIN"])
def test_only_explicit_manager_roles_can_activate(app_container, role):
    c = app_container
    admin = _admin(c)
    actor = c.users.create_user(username="not.manager", display_name="Petugas", password="UAT Permission 67!",
        roles=(role,), actor_user_id=admin.id)
    with pytest.raises(KnowledgeError):
        c.reference.save_drug(DrugEdit("Obat UAT", ("zat uat",), "UAT"), actor.id)


def test_anonymous_identity_cannot_write_even_with_role_and_audit_failure_rolls_back_drug(app_container, monkeypatch):
    from emss.database.models import AppUser
    c = app_container
    admin = _admin(c)
    with c.database.session() as s:
        row = s.get(AppUser, admin.id)
        original = row.normalized_username
        row.normalized_username = "mode.farmasi"
        s.commit()
    with pytest.raises(KnowledgeError, match="bernama"):
        c.reference.save_drug(DrugEdit("Obat UAT", ("zat uat",), "UAT"), admin.id)
    with c.database.session() as s:
        s.get(AppUser, admin.id).normalized_username = original
        s.commit()
    def fail(*args, **kwargs):
        raise RuntimeError("audit failure")
    monkeypatch.setattr(c.audit, "append", fail)
    with pytest.raises(RuntimeError):
        c.reference.save_drug(DrugEdit("Obat UAT", ("zat uat",), "UAT"), admin.id)
    assert c.catalog.list_drugs() == []


def test_two_editors_same_version_only_one_commits(app_container):
    from concurrent.futures import ThreadPoolExecutor
    c = app_container
    admin = _admin(c)
    base, _ = _seed(c, admin.id)
    old = c.knowledge.list_rules(base)[0]
    def save(code):
        try:
            c.reference.save_pair(replace(data(), severity_code=code), admin.id,
                expected_version_id=base, edit_rule_id=old.id)
            return "OK"
        except KnowledgeError:
            return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, ("SERIOUS", "MINOR")))
    assert sorted(outcomes) == ["CONFLICT", "OK"]
    with pytest.raises(KnowledgeError, match="sudah ada"):
        c.reference.save_pair(replace(data(), ingredient_a="zat b", ingredient_b="zat a"), admin.id,
            expected_version_id=c.reference.active_version_id())


def test_kfa_product_codes_portably_resolve_to_bza_and_screen(app_container):
    c = app_container
    admin = _admin(c)
    first = c.reference.save_drug(DrugEdit(
        name="Obat KFA A", code="SIMRS-A", ingredients=("zat a",),
        reference="KFA UAT", kfa_product_code="93000001",
        ingredient_kfa_codes=("91000001",), source_system="SIMRS_UAT"), admin.id)
    second = c.reference.save_drug(DrugEdit(
        name="Obat KFA B", code="SIMRS-B", ingredients=("zat b",),
        reference="KFA UAT", kfa_product_code="92000002",
        ingredient_kfa_codes=("91000002",), source_system="SIMRS_UAT"), admin.id)
    c.reference.save_pair(data(), admin.id, expected_version_id="")

    result = c.screening.screen(_prescription(("93000001", "92000002")), admin.id)

    assert result.interaction_count == 1
    assert result.pairs[0].pair_key == "zat a || zat b"
    detail = c.reference.drug_detail(first)
    assert detail["kfa_product_code"] == "93000001"
    assert detail["kfa_product_type"] == "POA"
    assert detail["ingredient_kfa_codes"] == ("91000001",)
    assert detail["source_system"] == "SIMRS_UAT"
    assert c.reference.drug_detail(second)["kfa_product_type"] == "POV"


def test_kfa_identity_conflicts_fail_closed(app_container):
    c = app_container
    admin = _admin(c)
    c.reference.save_drug(DrugEdit(
        name="Obat KFA A", code="SIMRS-A", ingredients=("zat a",),
        reference="KFA UAT", kfa_product_code="93000001",
        ingredient_kfa_codes=("91000001",)), admin.id)
    with pytest.raises(KnowledgeError, match="terikat pada nama kandungan lain"):
        c.reference.save_drug(DrugEdit(
            name="Obat KFA Konflik", code="SIMRS-X", ingredients=("zat x",),
            reference="KFA UAT", kfa_product_code="93000002",
            ingredient_kfa_codes=("91000001",)), admin.id)
