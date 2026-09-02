from dataclasses import replace
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QInputDialog
from test_screening_engine import _admin, _seed, _prescription
from emss.services.authentication import AuthenticatedUser
from emss.services.reference import DrugEdit
from emss.ui.reference import DrugEditor, PairEditor, ReferencePairsPanel
from emss.ui.application import APP_STYLESHEET, DrugCatalogTab


def named(c):
    admin = _admin(c)
    user = c.users.create_user(username="kft.ui", display_name="KFT Sintetis", password="Password UAT UI 67!",
        roles=("KFT",), actor_user_id=admin.id)
    return AuthenticatedUser(user.id, user.username, user.display_name, frozenset({"KFT"}), False)


@pytest.mark.ui
def test_new_drug_pair_activation_form_through_engine(qtbot, app_container, qapp):
    c, user = app_container, named(app_container)
    original_style = qapp.styleSheet()
    arrow = Path(__file__).resolve().parents[2] / "src/emss/assets/combo-chevron-down.svg"
    qapp.setStyleSheet(APP_STYLESHEET.replace("__COMBO_ARROW_PATH__", arrow.as_posix()))
    try:
        drug_ids = []
        for name in ("zat uat a", "zat uat b"):
            dialog = DrugEditor(c, user)
            qtbot.addWidget(dialog)
            dialog.show()
            dialog.name.setText("Obat sintetis " + name)
            dialog.ingredients.setText(name)
            dialog.reference.setText("Bukti komposisi sintetis UAT-67")
            qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
            assert dialog.result() == QDialog.DialogCode.Accepted
            drug_ids.append(dialog.saved_id)
        pair = PairEditor(c, user, drug_id=drug_ids[0])
        qtbot.addWidget(pair)
        pair.show()
        pair.right.select_drug(drug_ids[1])
        qtbot.mouseClick(pair.save_button, Qt.MouseButton.LeftButton)
        assert pair.result() != QDialog.DialogCode.Accepted
        assert "referensi" in pair.message.text().lower()
        pair.source.setText("Sumber sintetis untuk uji perangkat lunak")
        pair.reference.setText("UAT-67, tanpa rekomendasi klinis nyata")
        pair.effect.setText("Efek sintetis")
        pair.recommendation.setText("Rekomendasi uji; bukan untuk terapi pasien")
        qapp.processEvents()
        if directory := os.environ.get("EMAS_BATCH67_SHOTS"):
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            assert pair.grab().save(str(path / "pair-simpan-aktifkan.png"))
        qtbot.mouseClick(pair.save_button, Qt.MouseButton.LeftButton)
        assert pair.result() == QDialog.DialogCode.Accepted
        codes = tuple(c.reference.drug_detail(i)["code"] for i in drug_ids)
        result = c.screening.screen(_prescription(codes), user.id)
        assert result.interaction_count == 1 and result.completeness_status == "COMPLETE"
        panel = ReferencePairsPanel(c, user)
        qtbot.addWidget(panel)
        assert panel.table.rowCount() == 1
    finally:
        qapp.setStyleSheet(original_style)


@pytest.mark.ui
def test_readonly_roles_and_mapping_changed_while_pair_is_open(qtbot, app_container):
    c = app_container
    admin = _admin(c)
    base, codes = _seed(c, admin.id)
    user = AuthenticatedUser(admin.id, admin.username, admin.display_name, frozenset({"SUPER_ADMIN"}), False)
    denied = replace(user, roles=frozenset({"APOTEKER"}))
    panel = ReferencePairsPanel(c, denied)
    qtbot.addWidget(panel)
    assert not panel.new_button.isEnabled() and not panel.edit_button.isEnabled()
    anonymous = ReferencePairsPanel(c, replace(user, username="mode.farmasi"))
    qtbot.addWidget(anonymous)
    assert not anonymous.new_button.isEnabled()
    drugs = [c.catalog.list_drugs(code)[0].id for code in codes]
    dialog = PairEditor(c, user, drug_id=drugs[0])
    qtbot.addWidget(dialog)
    dialog.right.select_drug(drugs[1])
    dialog.source.setText("UAT")
    dialog.reference.setText("UAT-67")
    old = c.reference.drug_detail(drugs[0])
    c.reference.save_drug(DrugEdit(old["name"], ("zat c",), "UAT perubahan", old["code"], drugs[0], old["updated_at"]), admin.id)
    dialog.save(True)
    assert "Pemetaan obat berubah" in dialog.message.text()
    assert c.reference.active_version_id() == base


@pytest.mark.ui
def test_inactive_drug_remains_editable_for_reactivation(qtbot, app_container):
    c, user = app_container, named(app_container)
    identifier = c.reference.save_drug(DrugEdit("Obat UAT", ("zat uat",), "UAT komposisi"), user.id)
    old = c.reference.drug_detail(identifier)
    c.reference.set_drug_active(identifier, user.id, old["updated_at"])
    tab = DrugCatalogTab(c, user)
    qtbot.addWidget(tab)
    assert tab.table.rowCount() == 0
    tab.active_filter.setCurrentIndex(1)
    assert tab.table.rowCount() == 1
    dialog = DrugEditor(c, user, identifier)
    qtbot.addWidget(dialog)
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert c.reference.drug_detail(identifier)["is_active"]


@pytest.mark.ui
def test_bundled_draft_pairs_are_visible_but_not_editable(qtbot, app_container):
    c = app_container
    admin = _admin(c)
    c.bundled_ddi.apply_if_eligible(admin.id)
    user = AuthenticatedUser(admin.id, admin.username, admin.display_name,
        frozenset({"SUPER_ADMIN"}), False)

    panel = ReferencePairsPanel(c, user)
    qtbot.addWidget(panel)

    assert panel.table.rowCount() == 5432
    assert "Katalog bawaan terpulihkan" in panel.summary_label.text()
    assert not panel.edit_button.isEnabled()
    assert panel.table.item(0, 3).text() == "Draft bawaan"


@pytest.mark.ui
def test_h3_activation_button_requires_confirmation_and_refreshes_status(
    qtbot, app_container, monkeypatch
):
    c = app_container
    admin = _admin(c)
    c.bundled_ddi.apply_if_eligible(admin.id)
    c.bundled_mapping.apply_if_eligible(admin.id)
    user = AuthenticatedUser(
        admin.id,
        admin.username,
        admin.display_name,
        frozenset({"SUPER_ADMIN"}),
        False,
    )
    panel = ReferencePairsPanel(c, user)
    qtbot.addWidget(panel)
    assert panel.activate_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Validasi KFT sintetis melalui UI H3", True),
    )
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *_args, **_kwargs: messages.append(_args[2]),
    )

    qtbot.mouseClick(panel.activate_button, Qt.MouseButton.LeftButton)

    assert not panel.activate_button.isEnabled()
    assert panel.edit_button.isEnabled()
    assert "379 pair positif aktif" in panel.summary_label.text()
    assert messages and "379 pair positif aktif" in messages[0]
