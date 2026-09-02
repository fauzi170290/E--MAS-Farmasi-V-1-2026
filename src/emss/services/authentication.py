from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.config.settings import AppSettings
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, UserRole
from emss.security.passwords import PasswordService
from emss.services.users import normalize_username
from emss.utils.time import utc_now


class AuthenticationError(ValueError):
    pass


class AccountLockedError(AuthenticationError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    display_name: str
    roles: frozenset[str]
    must_change_password: bool


class AuthenticationService:
    def __init__(
        self,
        database: DatabaseManager,
        passwords: PasswordService,
        audit: AuditService,
        settings: AppSettings,
    ) -> None:
        self.database = database
        self.passwords = passwords
        self.audit = audit
        self.settings = settings

    def authenticate(self, username: str, password: str) -> AuthenticatedUser:
        normalized = normalize_username(username)
        now = utc_now()

        with self.database.session() as session:
            user = session.scalar(
                select(AppUser)
                .options(
                    selectinload(AppUser.roles).selectinload(UserRole.role)
                )
                .where(AppUser.normalized_username == normalized)
            )

            if user is None:
                self.passwords.verify_dummy(password)
                self.audit.append(
                    session,
                    AuditEvent(
                        category="USER_ACTIVITY",
                        action="LOGIN",
                        outcome="FAILED",
                        details={"reason": "INVALID_CREDENTIALS"},
                    ),
                )
                session.commit()
                raise AuthenticationError("Username atau password salah")

            if not user.is_active:
                self.audit.append(
                    session,
                    AuditEvent(
                        category="USER_ACTIVITY",
                        action="LOGIN",
                        outcome="DENIED",
                        actor_user_id=user.id,
                        details={"reason": "ACCOUNT_DISABLED"},
                    ),
                )
                session.commit()
                raise AuthenticationError("Akun tidak aktif")

            if user.locked_until is not None:
                locked_until = user.locked_until
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=now.tzinfo)
                if locked_until > now:
                    self.audit.append(
                        session,
                        AuditEvent(
                            category="USER_ACTIVITY",
                            action="LOGIN",
                            outcome="DENIED",
                            actor_user_id=user.id,
                            details={"reason": "ACCOUNT_LOCKED"},
                        ),
                    )
                    session.commit()
                    raise AccountLockedError(
                        "Akun terkunci sementara. Hubungi IT atau coba kembali nanti."
                    )

            if not self.passwords.verify(user.password_hash, password):
                user.failed_login_count += 1
                reason = "INVALID_CREDENTIALS"
                if user.failed_login_count >= self.settings.login_max_attempts:
                    user.locked_until = now + timedelta(
                        minutes=self.settings.login_lock_minutes
                    )
                    reason = "LOCKED_AFTER_FAILURES"
                self.audit.append(
                    session,
                    AuditEvent(
                        category="USER_ACTIVITY",
                        action="LOGIN",
                        outcome="FAILED",
                        actor_user_id=user.id,
                        details={"reason": reason},
                    ),
                )
                session.commit()
                raise AuthenticationError("Username atau password salah")

            if self.passwords.needs_rehash(user.password_hash):
                user.password_hash = self.passwords.hash(
                    password, user.username
                )
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login_at = now
            user.updated_at = now
            role_codes = frozenset(link.role.code for link in user.roles)
            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="LOGIN",
                    outcome="SUCCESS",
                    actor_user_id=user.id,
                    details={"roles": sorted(role_codes)},
                ),
            )
            session.commit()
            return AuthenticatedUser(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                roles=role_codes,
                must_change_password=user.must_change_password,
            )

