from __future__ import annotations

import logging

import pytest

from emss.logging.setup import RedactingFilter


@pytest.mark.security
@pytest.mark.parametrize(
    "message,secret",
    [
        ("password=RahasiaSekali", "RahasiaSekali"),
        ("token: abcdef123456", "abcdef123456"),
        ("mysql+pymysql://user:SangatRahasia@db/sik", "SangatRahasia"),
    ],
)
def test_sensitive_values_are_redacted(message: str, secret: str):
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    assert RedactingFilter().filter(record)
    assert secret not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()

