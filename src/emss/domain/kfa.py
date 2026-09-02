"""SATUSEHAT KFA identifiers used by the local medication master.

The application remains usable offline.  These helpers validate identifiers
already supplied by a SIMRS or a named reference editor; they do not call the
SATUSEHAT API and never contain facility credentials.
"""

from __future__ import annotations

from typing import Any


KFA_CODE_SYSTEM = "http://sys-ids.kemkes.go.id/kfa"
KFA_BZA_PREFIX = "91"
KFA_PRODUCT_TYPES = {"92": "POV", "93": "POA", "94": "POAK"}


def normalize_kfa_code(value: Any) -> str:
    return str(value or "").strip()


def validate_kfa_bza_code(value: Any, *, required: bool = False) -> str:
    code = normalize_kfa_code(value)
    if not code and not required:
        return ""
    if len(code) != 8 or not code.isdigit() or not code.startswith(KFA_BZA_PREFIX):
        raise ValueError("Kode BZA KFA harus 8 digit dan berawalan 91.")
    return code


def validate_kfa_product_code(value: Any, *, required: bool = False) -> tuple[str, str]:
    code = normalize_kfa_code(value)
    if not code and not required:
        return "", ""
    product_type = KFA_PRODUCT_TYPES.get(code[:2]) if len(code) == 8 and code.isdigit() else None
    if product_type is None:
        raise ValueError("Kode produk KFA harus 8 digit dan berawalan 92, 93, atau 94.")
    return code, product_type


def is_kfa_product_code(value: Any) -> bool:
    try:
        code, _kind = validate_kfa_product_code(value, required=True)
    except ValueError:
        return False
    return bool(code)
