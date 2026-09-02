from __future__ import annotations

import pytest

from emss.security.passwords import PasswordPolicyError, PasswordService


def test_password_hash_uses_argon2id_and_verifies():
    service = PasswordService()
    raw = "Frasa aman farmasi 2026!"

    password_hash = service.hash(raw, "apoteker")

    assert password_hash.startswith("$argon2id$")
    assert raw not in password_hash
    assert service.verify(password_hash, raw)
    assert not service.verify(password_hash, "salah total")


@pytest.mark.parametrize(
    "password",
    ["lima5", "password", "123456"],
)
def test_password_policy_rejects_weak_passwords(password: str):
    service = PasswordService()

    with pytest.raises(PasswordPolicyError):
        service.hash(password)


def test_password_policy_rejects_username_in_password():
    service = PasswordService()

    with pytest.raises(PasswordPolicyError):
        service.hash("Rahasia-apoteker-2026", "apoteker")


def test_password_policy_accepts_six_non_common_characters():
    service = PasswordService()

    password_hash = service.hash("Aman#6", "admin")

    assert service.verify(password_hash, "Aman#6")
