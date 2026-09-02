from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from emss.audit.service import AuditEvent, AuditService
from emss.config.settings import AppSettings
from emss.database.engine import DatabaseManager
from emss.database.models import AppUser, Role, UserRole
from emss.services.authentication import AuthenticatedUser
from emss.utils.time import utc_now


class WorkstationModeError(ValueError):
    pass


class WorkstationAccessService:
    USERNAME = "mode.farmasi"

    def __init__(
        self,
        database: DatabaseManager,
        audit: AuditService,
        settings: AppSettings,
    ) -> None:
        self.database = database
        self.audit = audit
        self.settings = settings
        with database.session() as session:
            self.settings.pharmacy_care_setting = session.execute(text(
                'SELECT care_setting FROM pharmacy_installation WHERE id=1')).scalar_one_or_none() or ''

    def enter_mode(self, *, care_setting: str = '') -> AuthenticatedUser:
        if not self.settings.allow_workstation_mode:
            raise WorkstationModeError(
                "Mode Farmasi belum diaktifkan oleh administrator IT"
            )
        with self.database.session() as session:
            selected = session.execute(text('SELECT care_setting FROM pharmacy_installation WHERE id=1')).scalar_one_or_none()
            if not selected and care_setting not in {'RALAN', 'RANAP'}:
                raise WorkstationModeError('Pilih Farmasi Rawat Jalan atau Farmasi Rawat Inap untuk instalasi ini.')
            if selected and care_setting and selected != care_setting:
                raise WorkstationModeError('Lokasi instalasi sudah ditetapkan dan tidak dapat diganti dari Mode Farmasi.')
            if not session.scalar(
                select(AppUser.id).where(
                    AppUser.normalized_username != self.USERNAME
                )
            ):
                raise WorkstationModeError(
                    "Administrator pertama harus dibuat sebelum Mode Farmasi"
                )
            user = session.scalar(
                select(AppUser)
                .options(
                    selectinload(AppUser.roles).selectinload(UserRole.role)
                )
                .where(AppUser.normalized_username == self.USERNAME)
            )
            if user is None:
                role = session.scalar(
                    select(Role).where(Role.code == "APOTEKER")
                )
                if role is None:
                    raise WorkstationModeError("Role APOTEKER tidak tersedia")
                now = utc_now()
                user = AppUser(
                    username=self.USERNAME,
                    normalized_username=self.USERNAME,
                    display_name=f"Mode {self.settings.workstation_label}",
                    password_hash="!WORKSTATION-MODE-NO-PASSWORD!",
                    is_active=False,
                    must_change_password=False,
                    password_changed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                session.flush()
                session.add(UserRole(user_id=user.id, role_id=role.id, assigned_at=now))
                session.flush()
            if not selected:
                session.execute(text('INSERT INTO pharmacy_installation(id,care_setting,selected_at) VALUES (1,:care,:at)'),
                    {'care':care_setting, 'at':utc_now()})
                selected = care_setting
                self.audit.append(session, AuditEvent(category='CONFIGURATION', action='PHARMACY_INSTALLATION_SELECTED',
                    outcome='SUCCESS', actor_user_id=user.id, details={'care_setting':selected, 'passwordless_first_setup':True}))
            self.audit.append(
                session,
                AuditEvent(
                    category="USER_ACTIVITY",
                    action="WORKSTATION_MODE_ENTERED",
                    outcome="SUCCESS",
                    actor_user_id=user.id,
                    entity_type="APP_USER",
                    entity_id=user.id,
                    details={
                        "workstation_label": self.settings.workstation_label
                    },
                ),
            )
            session.commit()
            self.settings.pharmacy_care_setting = selected
            return AuthenticatedUser(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                roles=frozenset({"APOTEKER"}),
                must_change_password=False,
            )
