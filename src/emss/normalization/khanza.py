"""Stable identities for numeric Khanza medicine codes.

The source system has historically exposed the same item with varying leading
zeroes.  Keep the stored source code intact, but compare numeric codes through
this five-digit identity.
"""
from __future__ import annotations

import unicodedata
from typing import Any


def canonical_khanza_code(value: Any) -> str:
    """Return the five-digit Khanza identity, or a normalized nonnumeric code."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    code = " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().split())
    if code.isdigit():
        return code[-5:].zfill(5)
    return code


def same_khanza_code(left: Any, right: Any) -> bool:
    return canonical_khanza_code(left) == canonical_khanza_code(right)
