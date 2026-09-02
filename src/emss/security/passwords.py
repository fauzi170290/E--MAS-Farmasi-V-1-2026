from __future__ import annotations

import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordPolicyError(ValueError):
    pass


class PasswordService:
    MIN_LENGTH = 6
    MAX_LENGTH = 128
    BLOCKLIST = frozenset(
        {
            "password",
            "123456",
            "qwerty",
            "admin1",
            "password123",
            "administrator",
            "admin123456789",
            "emssfarmasi",
            "khanza123456789",
            "123456789012345",
            "qwertyuiopasdfg",
        }
    )

    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        self._dummy_hash = self._hasher.hash(
            "dummy-authentication-value-never-used"
        )

    def validate(self, password: str, username: str | None = None) -> None:
        normalized = unicodedata.normalize("NFKC", password)
        length = len(normalized)
        if length < self.MIN_LENGTH:
            raise PasswordPolicyError(
                f"Password minimal {self.MIN_LENGTH} karakter"
            )
        if length > self.MAX_LENGTH:
            raise PasswordPolicyError(
                f"Password maksimal {self.MAX_LENGTH} karakter"
            )
        folded = normalized.casefold()
        if folded in self.BLOCKLIST:
            raise PasswordPolicyError("Password terlalu umum")
        if username and username.casefold() in folded:
            raise PasswordPolicyError("Password tidak boleh memuat username")

    def hash(self, password: str, username: str | None = None) -> str:
        self.validate(password, username)
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> None:
        try:
            self._hasher.verify(self._dummy_hash, password)
        except VerifyMismatchError:
            pass

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
