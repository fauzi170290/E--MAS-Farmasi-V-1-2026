from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from emss.services.bundled_ddi import (
    EXPECTED_BUNDLE_SHA256,
    EXPECTED_INGREDIENT_COUNT,
    EXPECTED_RULE_COUNT,
    BundledDdiSeedError,
    verify_bundled_ddi_seed,
)


ROOT = Path(__file__).resolve().parents[2]


def test_bundled_ddi_contract_contains_only_clinical_master_content():
    manifest, payload = verify_bundled_ddi_seed(ROOT / "seed")

    assert manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256
    assert manifest["ingredient_count"] == EXPECTED_INGREDIENT_COUNT
    assert manifest["rule_count"] == EXPECTED_RULE_COUNT
    assert manifest["patient_identity_included"] is False
    assert manifest["user_accounts_included"] is False
    assert manifest["catalog_profile"]["severity"] == {
        "NONE": 4867, "MINOR": 102, "SIGNIFICANT": 404,
        "SERIOUS": 55, "CONTRAINDICATED": 4,
    }
    assert manifest["catalog_profile"]["missing_source_reference"] == 18
    assert payload["knowledge_base"]["status"] == "DRAFT"
    assert len(payload["ingredients"]) == 159
    assert len(payload["rules"]) == 5432
    assert not ({"username", "password_hash", "patient_id"} & payload.keys())


def test_bundled_ddi_contract_rejects_manifest_and_bundle_tampering(tmp_path):
    target = tmp_path / "seed"
    shutil.copytree(ROOT / "seed", target)
    manifest_path = target / "ddi-khanza-v1.0.0.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rule_count"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundledDdiSeedError, match="rule_count"):
        verify_bundled_ddi_seed(target)

    shutil.rmtree(target)
    shutil.copytree(ROOT / "seed", target)
    bundle_path = target / "ddi-khanza-v1.0.0.json.gz"
    data = bytearray(bundle_path.read_bytes())
    data[-1] ^= 1
    bundle_path.write_bytes(data)
    with pytest.raises(BundledDdiSeedError, match="Checksum bundle"):
        verify_bundled_ddi_seed(target)


def test_bundled_ddi_contract_rejects_missing_and_invalid_manifest(tmp_path):
    with pytest.raises(BundledDdiSeedError, match="Artefak seed"):
        verify_bundled_ddi_seed(tmp_path)
    (tmp_path / "ddi-khanza-v1.0.0.manifest.json").write_text(
        "{", encoding="utf-8"
    )
    with pytest.raises(BundledDdiSeedError, match="Manifest"):
        verify_bundled_ddi_seed(tmp_path)
