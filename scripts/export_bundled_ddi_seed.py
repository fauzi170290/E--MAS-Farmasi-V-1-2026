from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path


FORMAT = "EMSS_BUNDLED_DDI_SEED_V1"
BUNDLE_ID = "DDI-KHANZA-v1.0.0"
INGREDIENT_FIELDS = (
    "standard_name",
    "normalized_name",
    "is_active",
    "created_at",
    "updated_at",
)
RULE_FIELDS = (
    "external_pair_id",
    "pair_key",
    "interaction_status",
    "severity_code",
    "severity_label",
    "severity_rank",
    "app_severity",
    "clinical_effect",
    "mechanism",
    "recommendation",
    "monitoring",
    "population_risk",
    "source_name",
    "source_reference",
    "source_accessed_at",
    "source_batch",
    "source_evidence_count",
    "source_validation_status",
    "source_final_code",
    "activation_status",
    "clinical_review_required",
    "clinical_review_resolved",
    "record_status",
    "is_enabled",
    "validated_at",
    "notes",
    "created_at",
    "updated_at",
)


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def export_seed(source_database: Path, output_directory: Path) -> dict[str, object]:
    source = source_database.resolve()
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:/{source.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        versions = connection.execute(
            "SELECT * FROM knowledge_base_version ORDER BY created_at"
        ).fetchall()
        if len(versions) != 1:
            raise ValueError("Database sumber wajib memiliki tepat satu knowledge base")
        version = dict(versions[0])
        if version["version_code"] != BUNDLE_ID:
            raise ValueError("Kode knowledge base sumber tidak sesuai bundle")

        ingredient_rows = connection.execute(
            "SELECT * FROM active_ingredient WHERE id IN ("
            "SELECT ingredient_low_id FROM ddi_rule UNION "
            "SELECT ingredient_high_id FROM ddi_rule) ORDER BY normalized_name"
        ).fetchall()
        ingredients_by_id = {row["id"]: row["normalized_name"] for row in ingredient_rows}
        ingredients = [
            {field: row[field] for field in INGREDIENT_FIELDS}
            for row in ingredient_rows
        ]

        rules = []
        for row in connection.execute("SELECT * FROM ddi_rule ORDER BY pair_key"):
            item = {field: row[field] for field in RULE_FIELDS}
            item["ingredient_low"] = ingredients_by_id[row["ingredient_low_id"]]
            item["ingredient_high"] = ingredients_by_id[row["ingredient_high_id"]]
            item["validated_by_name"] = (
                "MIGRATED_VALIDATION_REDACTED"
                if row["validated_by_name"]
                else None
            )
            rules.append(item)

        payload = {
            "format": FORMAT,
            "bundle_id": BUNDLE_ID,
            "privacy": {
                "contains_patient_identity": False,
                "contains_user_accounts": False,
                "validator_identity_redacted": True,
            },
            "knowledge_base": {
                "version_code": version["version_code"],
                "title": version["title"],
                "description": version["description"],
                "status": version["status"],
                "source_checksum": version["source_checksum"],
                "created_at": version["created_at"],
                "updated_at": version["updated_at"],
            },
            "ingredients": ingredients,
            "rules": rules,
        }
        semantic_bytes = _canonical(payload)
        semantic_sha256 = hashlib.sha256(semantic_bytes).hexdigest()
        bundle_path = output / "ddi-khanza-v1.0.0.json.gz"
        with bundle_path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                compressed.write(semantic_bytes)
        bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        manifest = {
            "format": "EMSS_BUNDLED_DDI_SEED_MANIFEST_V1",
            "bundle_id": BUNDLE_ID,
            "bundle_file": bundle_path.name,
            "bundle_sha256": bundle_sha256,
            "semantic_sha256": semantic_sha256,
            "source_database_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_knowledge_checksum": version["source_checksum"],
            "knowledge_base_status": version["status"],
            "ingredient_count": len(ingredients),
            "rule_count": len(rules),
            "patient_identity_included": False,
            "user_accounts_included": False,
            "validator_identity_redacted": True,
        }
        manifest_path = output / "ddi-khanza-v1.0.0.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_database", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(export_seed(args.source_database, args.output_directory), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
