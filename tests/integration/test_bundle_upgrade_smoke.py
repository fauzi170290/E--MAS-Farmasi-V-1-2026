from __future__ import annotations

import pytest

from emss.release.bundle_smoke import run_bundle_smoke


@pytest.mark.integration
def test_bundled_reference_clean_install_and_upgrade_preserve_local_data():
    result = run_bundle_smoke()

    assert result["state"] == "READY"
    assert result["schema_revision"] == "0029_kfa_identity"
    assert result["counts"] == {
        "ddi_rule": 5432,
        "drug_master": 414,
        "drug_component_mapping": 444,
    }
    assert result["enabled_ddi"] == 0
    assert result["non_pending_mappings"] == 0
    assert result["h3_active_ddi"] == 379
    assert result["h3_approved_mappings"] == 414
    assert result["h3_held_ddi"] == 175
    assert result["h3_draft_ddi"] == 11
    assert result["ledger_recovered"] is True
    assert result["local_master_preserved"] is True
    assert result["clinical_review_preserved"] is True
    assert result["mapping_correction_preserved"] is True
    assert result["user_files_preserved"] is True
    assert result["operational_data_accessed"] is False
