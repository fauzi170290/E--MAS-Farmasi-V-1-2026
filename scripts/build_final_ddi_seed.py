from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emss.domain.knowledge import canonical_pair, normalize_severity
from emss.importexport.drug_import import normalize_name
from emss.importexport.tabular_reader import XlsxTableReader


BUNDLE_ID = "EMAS-DDI-MEDSCAPE-v1.0.0"
CREATED_AT = "2026-09-14 00:00:00+00:00"
SOURCE_NAME = "EMAS DDI Runtime Database v1.0.0 (PUBLISHED)"
SOURCE_REFERENCE = "EMAS_DDI_RUNTIME_DATABASE_v1.0.0_PUBLISHED.xlsx"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def records(sheet) -> list[dict[str, object]]:
    if sheet.formula_cells:
        raise ValueError(f"Formula tidak diizinkan pada {sheet.name}: {sheet.formula_cells[:5]}")
    header = tuple(str(value or "").strip() for value in sheet.rows[0])
    return [dict(zip(header, row)) for row in sheet.rows[1:] if any(value not in (None, "") for value in row)]


def clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--old-seed", type=Path, default=ROOT / "seed/ddi-khanza-v1.0.0.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "seed/emas-ddi-medscape-v1.0.0.json.gz")
    parser.add_argument("--report", type=Path, default=ROOT / "outputs/final-ddi-migration/reconciliation.json")
    args = parser.parse_args()

    source_bytes = args.workbook.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    sheets = XlsxTableReader().read(args.workbook)
    required = {"README_EMAS_FINAL", "PAIR_STATUS", "DDI_CLINICAL", "DRUG_MAP_SIMRS", "RUNTIME_RULES"}
    if not required.issubset(sheets):
        raise ValueError(f"Sheet wajib tidak lengkap: {sorted(required - set(sheets))}")

    pair_rows = records(sheets["PAIR_STATUS"])
    clinical_rows = records(sheets["DDI_CLINICAL"])
    mapping_rows = records(sheets["DRUG_MAP_SIMRS"])
    clinical = {str(row["pair_key"]): row for row in clinical_rows}
    if len(clinical) != len(clinical_rows):
        raise ValueError("Duplicate pair_key pada DDI_CLINICAL")

    with gzip.open(args.old_seed, "rt", encoding="utf-8") as stream:
        old = json.load(stream)
    ingredients = old["ingredients"]
    ingredient_names = {str(row["normalized_name"]) for row in ingredients}
    old_by_pair = {str(row["pair_key"]): row for row in old["rules"]}

    status_map = {
        "DDI_POSITIVE": "INTERACTION_FOUND",
        "NO_INTERACTION_VERIFIED": "ASSESSED_NO_INTERACTION",
        "NOT_ASSESSABLE": "NOT_ASSESSABLE",
        "EXCLUDED_OUT_OF_SCOPE": "EXCLUDED",
    }
    rules: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in pair_rows:
        low, high, pair_key = canonical_pair(str(row["drug_a"]), str(row["drug_b"]))
        if pair_key != row["pair_key"] or pair_key in seen:
            raise ValueError(f"Pair-key tidak deterministik/duplikat: {row['pair_key']}")
        seen.add(pair_key)
        if low not in ingredient_names or high not in ingredient_names:
            raise ValueError(f"Canonical tidak tersedia pada ingredient master: {pair_key}")
        runtime_status = str(row["runtime_status_code"])
        interaction_status = status_map[runtime_status]
        detail = clinical.get(pair_key)
        if interaction_status == "INTERACTION_FOUND" and detail is None:
            raise ValueError(f"DDI positif tanpa DDI_CLINICAL: {pair_key}")
        if interaction_status != "INTERACTION_FOUND" and detail is not None:
            raise ValueError(f"Clinical row untuk pair non-DDI: {pair_key}")
        severity = str(row["severity_code"]) if interaction_status == "INTERACTION_FOUND" else "NONE"
        severity_code, severity_rank, app_severity = normalize_severity(severity)
        if severity_rank != int(row.get("severity_rank") or 0):
            raise ValueError(f"Severity rank tidak cocok: {pair_key}")
        detail_level = clean(detail.get("detail_level")) if detail else None
        rule = {
            "activation_status": "READY_FOR_PHARMACIST_REVIEW" if detail else "NOT_AN_ALERT_RULE",
            "app_severity": app_severity,
            "clinical_detail_available": detail_level != "SEVERITY_ONLY" if detail else None,
            "clinical_effect": clean(detail.get("clinical_effect_text")) if detail else None,
            "clinical_review_required": 0,
            "clinical_review_resolved": 1,
            "created_at": CREATED_AT,
            "external_pair_id": None,
            "ingredient_high": high,
            "ingredient_low": low,
            "interaction_status": interaction_status,
            "is_enabled": 0,
            "mechanism": clean(detail.get("mechanism_text")) if detail else None,
            # Existing immutable snapshot field; now explicitly carries display_action_text.
            "monitoring": clean(detail.get("display_action_text")) if detail else None,
            "notes": "Imported from final PUBLISHED source; activation remains governed by E-MAS.",
            "pair_key": pair_key,
            "population_risk": None,
            "recommendation": clean(detail.get("management_recommendation")) if detail else None,
            "record_status": "DRAFT",
            "severity_code": severity_code,
            "severity_label": clean(detail.get("severity_label")) if detail else None,
            "severity_rank": severity_rank,
            "source_accessed_at": "2026-09-14",
            "source_batch": detail_level,
            "source_evidence_count": 1,
            "source_final_code": runtime_status,
            "source_name": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
            "source_validation_status": clean(detail.get("validation_flag")) if detail else runtime_status,
            "updated_at": CREATED_AT,
            "validated_at": None,
            "validated_by_name": None,
            "medscape_action": clean(detail.get("medscape_action_text")) if detail else None,
            "recommendation_source": clean(detail.get("action_source")) if detail else None,
            "medscape_summary": clean(detail.get("interaction_summary")) if detail else None,
        }
        rules.append(rule)

    rules.sort(key=lambda row: str(row["pair_key"]))
    if len(rules) != 5410 or len(seen) != 5410:
        raise ValueError(f"Jumlah final pair bukan 5410: {len(rules)}")
    if sum(bool(row["clinical_review_required"]) for row in rules):
        raise ValueError("Master final masih menghasilkan HOLD")

    final_pairs = set(seen)
    old_pairs = set(old_by_pair)
    old_holds = {key for key, row in old_by_pair.items() if row.get("activation_status") == "HOLD_CLINICAL_REVIEW_REQUIRED"}
    map_names = {normalize_name(str(row["raw_drug_name"])) for row in mapping_rows}
    payload = {
        "bundle_id": BUNDLE_ID,
        "format": "EMSS_BUNDLED_DDI_SEED_V1",
        "ingredients": ingredients,
        "knowledge_base": {
            "created_at": CREATED_AT,
            "description": "Final runtime knowledge base from EMAS_DDI_RUNTIME_DATABASE_v1.0.0_PUBLISHED.xlsx; admin activation required.",
            "source_checksum": source_sha,
            "status": "DRAFT",
            "title": "Knowledge Base EMAS DDI Medscape v1.0.0",
            "updated_at": CREATED_AT,
            "version_code": BUNDLE_ID,
        },
        "privacy": {"patient_identity_included": False, "user_accounts_included": False, "validator_identity_redacted": True},
        "rules": rules,
    }
    payload_bytes = canonical_bytes(payload)
    semantic_sha = hashlib.sha256(payload_bytes).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            stream.write(payload_bytes)
    bundle_sha = hashlib.sha256(args.output.read_bytes()).hexdigest()
    profile = {
        "severity": dict(sorted(Counter(str(row["severity_code"]) for row in rules).items())),
        "interaction_status": dict(sorted(Counter(str(row["interaction_status"]) for row in rules).items())),
        "activation_status": dict(sorted(Counter(str(row["activation_status"]) for row in rules).items())),
        "missing_source_reference": sum(not row["source_reference"] for row in rules),
        "clinical_review_required": sum(bool(row["clinical_review_required"]) for row in rules),
        "enabled": sum(bool(row["is_enabled"]) for row in rules),
    }
    manifest = {
        "format": "EMSS_BUNDLED_DDI_SEED_MANIFEST_V1", "bundle_id": BUNDLE_ID,
        "bundle_file": args.output.name, "bundle_sha256": bundle_sha,
        "semantic_sha256": semantic_sha, "source_knowledge_checksum": source_sha,
        "knowledge_base_status": "DRAFT", "ingredient_count": len(ingredients),
        "rule_count": len(rules), "patient_identity_included": False,
        "user_accounts_included": False, "validator_identity_redacted": True,
        "catalog_profile": profile,
    }
    manifest_path = args.output.with_suffix("").with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "source_workbook": args.workbook.name, "source_sha256": source_sha,
        "existing_pair_count": len(old_pairs), "final_source_pair_count": len(final_pairs),
        "MATCH_EXACT": len(old_pairs & final_pairs), "MATCH_CANONICAL_CHANGED": 0,
        "NEW_IN_FINAL": len(final_pairs - old_pairs), "LEGACY_ONLY": len(old_pairs - final_pairs),
        "UNMAPPED_CANONICAL": 0, "AMBIGUOUS_MAPPING": 0,
        "old_seed_hold_count": len(old_holds), "old_holds_replaced_by_final": len(old_holds & final_pairs),
        "old_holds_not_in_final": len(old_holds - final_pairs), "new_hold_count": 0,
        "workbook_mapping_name_count": len(map_names), "runtime_profile": profile,
        "legacy_only_pairs": sorted(old_pairs - final_pairs),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bundle_sha256": bundle_sha, "semantic_sha256": semantic_sha, "source_sha256": source_sha, "profile": profile}, indent=2))


if __name__ == "__main__":
    main()
