from __future__ import annotations

import pytest

from emss.domain.screening import (
    HashPrescriptionItem,
    IngredientOccurrence,
    build_ingredient_pairs,
    highest_risk,
    overall_status,
    prescription_hash,
)


def test_prescription_hash_is_order_independent_and_canonical() -> None:
    first = HashPrescriptionItem(
        "obat-1",
        " 1 ",
        "Dua kali sehari",
        "Oral",
        "Racikan A",
        ("Zat B", "Zat A"),
    )
    second = HashPrescriptionItem("OBAT-2", "2", "malam", "oral")

    assert prescription_hash((first, second)) == prescription_hash(
        (second, first)
    )
    assert prescription_hash((first,)) == prescription_hash(
        (
            HashPrescriptionItem(
                "obat-1",
                "1",
                "dua kali sehari",
                "oral",
                "racikan a",
                ("zat a", "zat b"),
            ),
        )
    )


@pytest.mark.parametrize(
    "changed",
    [
        HashPrescriptionItem("OBAT-1", "2", "1x1", "oral", "R1", ("zat a",)),
        HashPrescriptionItem("OBAT-1", "1", "2x1", "oral", "R1", ("zat a",)),
        HashPrescriptionItem("OBAT-1", "1", "1x1", "iv", "R1", ("zat a",)),
        HashPrescriptionItem("OBAT-1", "1", "1x1", "oral", "R2", ("zat a",)),
        HashPrescriptionItem("OBAT-1", "1", "1x1", "oral", "R1", ("zat b",)),
    ],
)
def test_prescription_hash_changes_for_clinical_fields(changed) -> None:
    baseline = HashPrescriptionItem(
        "OBAT-1", "1", "1x1", "oral", "R1", ("zat a",)
    )
    assert prescription_hash((baseline,)) != prescription_hash((changed,))


def test_pair_builder_skips_same_item_and_deduplicates_cross_items() -> None:
    pairs = build_ingredient_pairs(
        (
            IngredientOccurrence("racikan-1", "R1", "zat a", "R1"),
            IngredientOccurrence("racikan-1", "R1", "zat b", "R1"),
            IngredientOccurrence("normal-1", "N1", "zat c"),
            IngredientOccurrence("normal-2", "N2", "zat c"),
        )
    )

    assert [pair.pair_key for pair in pairs] == [
        "zat a || zat c",
        "zat b || zat c",
    ]


def test_risk_and_completeness_are_separate_dimensions() -> None:
    assert highest_risk(("INFO", "CRITICAL", "REVIEW")) == "CRITICAL"
    assert overall_status("CRITICAL", "UNMAPPED") == "UNMAPPED"
    assert overall_status("HIGH_RISK", "COMPLETE") == "HIGH_RISK"

    with pytest.raises(ValueError):
        highest_risk(("UNKNOWN",))
    with pytest.raises(ValueError):
        overall_status("SAFE", "UNKNOWN")
