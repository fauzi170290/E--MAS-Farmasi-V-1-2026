import pytest

from emss.domain.kfa import (
    KFA_CODE_SYSTEM,
    is_kfa_product_code,
    validate_kfa_bza_code,
    validate_kfa_product_code,
)


def test_kfa_code_contracts_follow_satusehat_prefixes():
    assert KFA_CODE_SYSTEM == "http://sys-ids.kemkes.go.id/kfa"
    assert validate_kfa_bza_code(" 91000101 ") == "91000101"
    assert validate_kfa_product_code("92000511") == ("92000511", "POV")
    assert validate_kfa_product_code("93002205") == ("93002205", "POA")
    assert validate_kfa_product_code("94002470") == ("94002470", "POAK")
    assert is_kfa_product_code("93002205")
    assert not is_kfa_product_code("91000101")


@pytest.mark.parametrize("value", ["91", "9100010A", "92000101", "091000101"])
def test_invalid_bza_codes_are_rejected(value):
    with pytest.raises(ValueError):
        validate_kfa_bza_code(value, required=True)


@pytest.mark.parametrize("value", ["93", "9300010A", "91000101", "95000101"])
def test_invalid_product_codes_are_rejected(value):
    with pytest.raises(ValueError):
        validate_kfa_product_code(value, required=True)
