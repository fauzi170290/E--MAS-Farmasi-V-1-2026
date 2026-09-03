import pytest

from emss.normalization import canonical_khanza_code


@pytest.mark.parametrize("source", ("000003795", "03795", "3795"))
def test_numeric_khanza_codes_share_five_digit_identity(source):
    assert canonical_khanza_code(source) == "03795"


def test_non_numeric_khanza_code_is_not_rewritten():
    assert canonical_khanza_code(" OBAT-001 ") == "OBAT-001"
