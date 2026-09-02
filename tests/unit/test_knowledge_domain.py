from __future__ import annotations

import pytest

from emss.domain.knowledge import (
    canonical_pair,
    normalize_severity,
    validate_status_severity,
)


def test_canonical_pair_is_order_independent():
    assert canonical_pair(" Warfarin ", "DIAZEPAM") == (
        "diazepam",
        "warfarin",
        "diazepam || warfarin",
    )
    assert canonical_pair("diazepam", "warfarin") == canonical_pair(
        "warfarin", "diazepam"
    )


@pytest.mark.parametrize("left,right", [("", "a"), ("a", ""), ("a", "A")])
def test_canonical_pair_rejects_incomplete_or_same(left, right):
    with pytest.raises(ValueError):
        canonical_pair(left, right)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("NONE", ("NONE", 0, None)),
        ("minor", ("MINOR", 1, "INFO")),
        ("Significant", ("SIGNIFICANT", 2, "REVIEW")),
        ("SERIOUS", ("SERIOUS", 3, "HIGH_RISK")),
        ("contraindicated", ("CONTRAINDICATED", 4, "CRITICAL")),
    ],
)
def test_severity_mapping(code, expected):
    assert normalize_severity(code) == expected


def test_invalid_status_severity_combinations_are_rejected():
    with pytest.raises(ValueError):
        normalize_severity("unknown")
    with pytest.raises(ValueError):
        validate_status_severity("INTERACTION_FOUND", "NONE")
    with pytest.raises(ValueError):
        validate_status_severity("NOT_ASSESSABLE", "MINOR")
    with pytest.raises(ValueError):
        validate_status_severity("UNKNOWN", "NONE")
