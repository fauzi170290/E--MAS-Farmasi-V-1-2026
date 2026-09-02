from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from emss.database.models import AppUser, AuditLog, UserRole
from emss.services.authentication import AccountLockedError, AuthenticationError
from emss.services.users import (
    DuplicateUsernameError,
    InvalidCurrentPasswordError,
    UserValidationError,
)
from emss.services.workstation import WorkstationModeError


ADMIN_PASSWORD = "Frasa aman untuk admin 2026!"


@pytest.mark.integration
def test_first_admin_and_successful_login_are_audited(app_container):
    created = app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )

    authenticated = app_container.authentication.authenticate(
        "ADMIN.LOCAL", ADMIN_PASSWORD
    )

    assert authenticated.id == created.id
    assert authenticated.roles == frozenset({"SUPER_ADMIN", "IT_ADMIN"})

    with app_container.database.session() as session:
        stored = session.get(AppUser, created.id)
        assert stored is not None
        assert stored.password_hash != ADMIN_PASSWORD
        assert stored.password_hash.startswith("$argon2id$")
        assert session.scalar(
            select(func.count()).select_from(UserRole)
        ) == 2
        actions = session.scalars(
            select(AuditLog.action).order_by(AuditLog.occurred_at)
        ).all()
        assert actions == ["USER_CREATED", "LOGIN"]
        outcomes = session.scalars(
            select(AuditLog.outcome).order_by(AuditLog.occurred_at)
        ).all()
        assert outcomes[-1] == "SUCCESS"
        assert app_container.audit.verify_chain(session)


@pytest.mark.integration
def test_unknown_user_and_bad_password_use_generic_error(app_container):
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )

    with pytest.raises(AuthenticationError, match="Username atau password salah"):
        app_container.authentication.authenticate("tidak.ada", "apa pun")
    with pytest.raises(AuthenticationError, match="Username atau password salah"):
        app_container.authentication.authenticate("admin.local", "salah")


@pytest.mark.integration
def test_account_locks_after_configured_failures(app_container):
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )

    for _ in range(app_container.settings.login_max_attempts):
        with pytest.raises(AuthenticationError):
            app_container.authentication.authenticate("admin.local", "salah")

    with pytest.raises(AccountLockedError):
        app_container.authentication.authenticate(
            "admin.local", ADMIN_PASSWORD
        )


@pytest.mark.integration
def test_first_admin_cannot_be_created_twice(app_container):
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )

    with pytest.raises(UserValidationError):
        app_container.users.create_first_admin(
            username="admin.dua",
            display_name="Administrator Dua",
            password="Frasa aman untuk admin dua!",
        )


@pytest.mark.integration
def test_duplicate_username_is_case_insensitive(app_container):
    first = app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )

    with pytest.raises(DuplicateUsernameError):
        app_container.users.create_user(
            username="ADMIN.LOCAL",
            display_name="Duplikat",
            password="Frasa aman berbeda 2026!",
            roles=("VIEWER",),
            actor_user_id=first.id,
        )


@pytest.mark.integration
def test_audit_does_not_store_password(app_container):
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )
    with pytest.raises(AuthenticationError):
        app_container.authentication.authenticate("admin.local", "salah")

    with app_container.database.session() as session:
        serialized = "\n".join(
            json.dumps(
                {
                    "action": row.action,
                    "details": row.details_json,
                }
            )
            for row in session.scalars(select(AuditLog)).all()
        )
    assert ADMIN_PASSWORD not in serialized
    assert '"salah"' not in serialized


@pytest.mark.integration
def test_user_can_change_password_and_action_is_audited(app_container):
    created = app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )
    new_password = "Frasa pengganti yang aman 2026!"

    with pytest.raises(
        InvalidCurrentPasswordError, match="tidak benar"
    ):
        app_container.users.change_password(
            user_id=created.id,
            current_password="password salah",
            new_password=new_password,
        )
    app_container.users.change_password(
        user_id=created.id,
        current_password=ADMIN_PASSWORD,
        new_password=new_password,
    )

    with pytest.raises(AuthenticationError):
        app_container.authentication.authenticate(
            "admin.local", ADMIN_PASSWORD
        )
    authenticated = app_container.authentication.authenticate(
        "admin.local", new_password
    )
    assert authenticated.id == created.id
    with app_container.database.session() as session:
        outcomes = session.execute(
            select(AuditLog.outcome).where(
                AuditLog.action == "PASSWORD_CHANGE"
            )
        ).scalars().all()
        serialized = "\n".join(
            row.details_json
            for row in session.scalars(select(AuditLog)).all()
        )
        assert outcomes == ["DENIED", "SUCCESS"]
        assert ADMIN_PASSWORD not in serialized
        assert new_password not in serialized


@pytest.mark.integration
def test_workstation_mode_requires_config_and_creates_one_locked_identity(
    app_container,
) -> None:
    with pytest.raises(WorkstationModeError, match="belum diaktifkan"):
        app_container.workstation_access.enter_mode()
    app_container.users.create_first_admin(
        username="admin.local",
        display_name="Administrator Lokal",
        password=ADMIN_PASSWORD,
    )
    app_container.settings.allow_workstation_mode = True

    first = app_container.workstation_access.enter_mode(care_setting="RALAN")
    second = app_container.workstation_access.enter_mode()
    assert app_container.settings.pharmacy_care_setting == "RALAN"
    with pytest.raises(WorkstationModeError, match="tidak dapat diganti"):
        app_container.workstation_access.enter_mode(care_setting="RANAP")

    assert first.id == second.id
    assert first.roles == frozenset({"APOTEKER"})
    assert first.username == "mode.farmasi"
    with pytest.raises(AuthenticationError, match="tidak aktif"):
        app_container.authentication.authenticate("mode.farmasi", "apa pun")
    with app_container.database.session() as session:
        system_user = session.get(AppUser, first.id)
        actions = session.scalars(select(AuditLog.action)).all()
        assert system_user is not None and not system_user.is_active
        assert actions.count("WORKSTATION_MODE_ENTERED") == 2
