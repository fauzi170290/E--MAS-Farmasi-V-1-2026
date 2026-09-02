"""Fondasi Sprint 1: role, user, audit, dan log teknis."""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa

revision = "0001_sprint1"
down_revision = None
branch_labels = None
depends_on = None


ROLES = [
    ("SUPER_ADMIN", "Super Administrator", "Akses administratif tertinggi"),
    ("IT_ADMIN", "Administrator IT", "Konfigurasi teknis, akun, dan backup"),
    ("KNOWLEDGE_ADMIN", "Knowledge Administrator", "Kelola draft knowledge"),
    ("CLINICAL_REVIEWER", "Clinical Reviewer", "Review aturan klinis"),
    ("APOTEKER", "Apoteker", "Skrining dan intervensi farmasi"),
    ("KEPALA_INSTALASI", "Kepala Instalasi", "Supervisi instalasi farmasi"),
    ("KFT", "Komite Farmasi dan Terapi", "Persetujuan kebijakan klinis"),
    ("PMKP", "PMKP", "Pemantauan mutu dan keselamatan pasien"),
    ("DIREKTUR", "Direktur", "Akses dashboard eksekutif"),
    ("VIEWER", "Viewer", "Akses baca terbatas"),
]


def upgrade() -> None:
    migration_time = datetime.now(UTC)
    op.create_table(
        "role",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_role"),
        sa.UniqueConstraint("code", name="uq_role_code"),
    )
    role_table = sa.table(
        "role",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        role_table,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "is_system": True,
                "created_at": migration_time,
            }
            for code, name, description in ROLES
        ],
    )

    op.create_table(
        "app_user",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("normalized_username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column(
            "failed_login_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.UniqueConstraint(
            "normalized_username", name="uq_app_user_username"
        ),
    )
    op.create_index("ix_app_user_active", "app_user", ["is_active"])

    op.create_table(
        "user_role",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["app_user.id"],
            name="fk_user_role_assigned_by_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name="fk_user_role_role_id_role",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_user_role_user_id_app_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_role"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("workstation", sa.String(length=120), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name="fk_audit_log_actor_user_id_app_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.UniqueConstraint("entry_hash", name="uq_audit_log_entry_hash"),
    )
    op.create_index(
        "ix_audit_occurred_action",
        "audit_log",
        ["occurred_at", "action"],
    )
    op.create_index("ix_audit_actor", "audit_log", ["actor_user_id"])

    op.create_table(
        "technical_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("event_code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.Text(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_technical_log"),
    )
    op.create_index(
        "ix_technical_occurred_level",
        "technical_log",
        ["occurred_at", "level"],
    )


def downgrade() -> None:
    op.drop_index("ix_technical_occurred_level", table_name="technical_log")
    op.drop_table("technical_log")
    op.drop_index("ix_audit_actor", table_name="audit_log")
    op.drop_index("ix_audit_occurred_action", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("user_role")
    op.drop_index("ix_app_user_active", table_name="app_user")
    op.drop_table("app_user")
    op.drop_table("role")
