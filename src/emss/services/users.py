from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from emss.audit.service import AuditEvent, AuditService
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, Role, UserRole
from emss.domain.roles import SystemRole
from emss.security.passwords import PasswordService
from emss.utils.time import utc_now


class DuplicateUsernameError(ValueError):
    pass


class UnknownRoleError(ValueError):
    pass


class UserValidationError(ValueError):
    pass


class InvalidCurrentPasswordError(UserValidationError):
    pass


def normalize_username(username: str) -> str:
    return username.strip().casefold()


class UserService:
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,80}$")

    def __init__(
        self,
        database: DatabaseManager,
        passwords: PasswordService,
        audit: AuditService,
    ) -> None:
        self.database = database
        self.passwords = passwords
        self.audit = audit

    def count_users(self) -> int:
        with self.database.session() as session:
            return session.scalar(select(func.count()).select_from(AppUser)) or 0

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password: str,
        roles: Iterable[SystemRole | str],
        actor_user_id: str | None = None,
        must_change_password: bool = False,
    ) -> AppUser:
        username = username.strip()
        display_name = display_name.strip()
        normalized = normalize_username(username)
        if not self.USERNAME_PATTERN.fullmatch(username):
            raise UserValidationError(
                "Username 3-80 karakter dan hanya boleh berisi "
                "huruf, angka, titik, garis bawah, atau tanda hubung"
            )
        if not display_name:
            raise UserValidationError("Nama tampilan wajib diisi")

        requested_roles = {
            role.value if isinstance(role, SystemRole) else str(role)
            for role in roles
        }
        if not requested_roles:
            raise UserValidationError("Minimal satu role wajib dipilih")

        password_hash = self.passwords.hash(password, username)
        now = utc_now()
        with self.database.session() as session:
            existing = session.scalar(
                select(AppUser).where(
                    AppUser.normalized_username == normalized
                )
            )
            if existing:
                raise DuplicateUsernameError("Username sudah digunakan")

            role_rows = session.scalars(
                select(Role).where(Role.code.in_(requested_roles))
            ).all()
            found_roles = {row.code for row in role_rows}
            missing = requested_roles - found_roles
            if missing:
                raise UnknownRoleError(
                    f"Role tidak ditemukan: {', '.join(sorted(missing))}"
                )

            user = AppUser(
                username=username,
                normalized_username=normalized,
                display_name=display_name,
                password_hash=password_hash,
                must_change_password=must_change_password,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            for role_row in role_rows:
                session.add(
                    UserRole(
                        user_id=user.id,
                        role_id=role_row.id,
                        assigned_by=actor_user_id,
                        assigned_at=now,
                    )
                )

            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="USER_CREATED",
                    outcome="SUCCESS",
                    actor_user_id=actor_user_id,
                    entity_type="APP_USER",
                    entity_id=user.id,
                    details={"username": username, "roles": sorted(found_roles)},
                ),
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateUsernameError("Username sudah digunakan") from exc
            session.refresh(user)
            return user

    def create_first_admin(
        self, *, username: str, display_name: str, password: str
    ) -> AppUser:
        if self.count_users() != 0:
            raise UserValidationError(
                "Administrator pertama hanya dapat dibuat saat belum ada pengguna"
            )
        return self.create_user(
            username=username,
            display_name=display_name,
            password=password,
            roles=(SystemRole.SUPER_ADMIN, SystemRole.IT_ADMIN),
        )

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        with self.database.session() as session:
            user = session.get(AppUser, user_id)
            if user is None or not user.is_active:
                raise UserValidationError("Pengguna aktif tidak ditemukan")
            if not self.passwords.verify(
                user.password_hash, current_password
            ):
                self.audit.append(
                    session,
                    AuditEvent(
                        category="USER_ACTIVITY",
                        action="PASSWORD_CHANGE",
                        outcome="DENIED",
                        actor_user_id=user.id,
                        entity_type="APP_USER",
                        entity_id=user.id,
                        details={"reason": "CURRENT_PASSWORD_INVALID"},
                    ),
                )
                session.commit()
                raise InvalidCurrentPasswordError(
                    "Password saat ini tidak benar"
                )
            if self.passwords.verify(user.password_hash, new_password):
                raise UserValidationError(
                    "Password baru harus berbeda dari password saat ini"
                )

            now = utc_now()
            user.password_hash = self.passwords.hash(
                new_password, user.username
            )
            user.must_change_password = False
            user.failed_login_count = 0
            user.locked_until = None
            user.password_changed_at = now
            user.updated_at = now
            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="PASSWORD_CHANGE",
                    outcome="SUCCESS",
                    actor_user_id=user.id,
                    entity_type="APP_USER",
                    entity_id=user.id,
                ),
            )
            session.commit()
