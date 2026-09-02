from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from emss.domain.knowledge import canonical_pair
from emss.importexport.drug_import import normalize_code, normalize_name, normalize_text


RISK_PRIORITY = {
    "SAFE": 0,
    "INFO": 1,
    "REVIEW": 2,
    "HIGH_RISK": 3,
    "CRITICAL": 4,
}
COMPLETENESS_PRIORITY = {
    "COMPLETE": 0,
    "NOT_ASSESSED": 1,
    "UNMAPPED": 2,
    "INCOMPLETE": 3,
    "ERROR": 4,
}


@dataclass(frozen=True)
class HashPrescriptionItem:
    khanza_code: str
    quantity: str = ""
    directions: str = ""
    route: str = ""
    compound_group: str = ""
    active_ingredients: tuple[str, ...] = ()


@dataclass(frozen=True)
class IngredientOccurrence:
    source_item_key: str
    khanza_code: str
    ingredient_name: str
    compound_group: str = ""


@dataclass(frozen=True)
class IngredientPair:
    pair_key: str
    ingredient_low: str
    ingredient_high: str
    source_item_keys: tuple[str, str]
    khanza_codes: tuple[str, str]


def prescription_hash(items: Iterable[HashPrescriptionItem]) -> str:
    canonical_items = []
    for item in items:
        canonical_items.append(
            {
                "khanza_code": normalize_code(item.khanza_code),
                "quantity": normalize_text(item.quantity),
                "directions": normalize_name(item.directions),
                "route": normalize_name(item.route),
                "compound_group": normalize_name(item.compound_group),
                "active_ingredients": sorted(
                    {
                        normalize_name(name)
                        for name in item.active_ingredients
                        if normalize_name(name)
                    }
                ),
            }
        )
    canonical_items.sort(
        key=lambda value: json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    )
    payload = json.dumps(
        canonical_items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_ingredient_pairs(
    occurrences: Iterable[IngredientOccurrence],
) -> tuple[IngredientPair, ...]:
    rows = tuple(occurrences)
    unique: dict[str, IngredientPair] = {}
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1 :]:
            if left.source_item_key == right.source_item_key:
                continue
            if normalize_name(left.ingredient_name) == normalize_name(
                right.ingredient_name
            ):
                continue
            low, high, pair_key = canonical_pair(
                left.ingredient_name, right.ingredient_name
            )
            if normalize_name(left.ingredient_name) == low:
                source_keys = (left.source_item_key, right.source_item_key)
                codes = (left.khanza_code, right.khanza_code)
            else:
                source_keys = (right.source_item_key, left.source_item_key)
                codes = (right.khanza_code, left.khanza_code)
            unique.setdefault(
                pair_key,
                IngredientPair(
                    pair_key=pair_key,
                    ingredient_low=low,
                    ingredient_high=high,
                    source_item_keys=source_keys,
                    khanza_codes=codes,
                ),
            )
    return tuple(unique[key] for key in sorted(unique))


def highest_risk(statuses: Iterable[str]) -> str:
    result = "SAFE"
    for status in statuses:
        if status not in RISK_PRIORITY:
            raise ValueError(f"Status risiko tidak valid: {status}")
        if RISK_PRIORITY[status] > RISK_PRIORITY[result]:
            result = status
    return result


def overall_status(risk_status: str, completeness_status: str) -> str:
    if risk_status not in RISK_PRIORITY:
        raise ValueError(f"Status risiko tidak valid: {risk_status}")
    if completeness_status not in COMPLETENESS_PRIORITY:
        raise ValueError(
            f"Status kelengkapan tidak valid: {completeness_status}"
        )
    return (
        risk_status
        if completeness_status == "COMPLETE"
        else completeness_status
    )

