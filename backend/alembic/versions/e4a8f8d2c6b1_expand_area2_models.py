"""expand_area2_models

Revision ID: e4a8f8d2c6b1
Revises: c1e7a5f9b312
Create Date: 2026-03-02 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a8f8d2c6b1"
down_revision: str | Sequence[str] | None = "c1e7a5f9b312"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROJECT_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "in_progress",
    "review",
    "revision",
    "approved",
    "delivered",
    name="projectstatus",
)
SHOT_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "in_progress",
    "review",
    "revision",
    "approved",
    "delivered",
    name="shotstatus",
)
ASSET_STATUS_ENUM = postgresql.ENUM(
    "pending",
    "in_progress",
    "review",
    "revision",
    "approved",
    "delivered",
    name="assetstatus",
)
ASSET_TYPE_ENUM = postgresql.ENUM(
    "character",
    "prop",
    "environment",
    "fx",
    name="assettype",
)
STATUS_LOG_ENTITY_TYPE_ENUM = postgresql.ENUM(
    "project",
    "shot",
    "asset",
    name="statuslogentitytype",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    PROJECT_STATUS_ENUM.create(bind, checkfirst=True)
    SHOT_STATUS_ENUM.create(bind, checkfirst=True)
    ASSET_STATUS_ENUM.create(bind, checkfirst=True)
    ASSET_TYPE_ENUM.create(bind, checkfirst=True)
    STATUS_LOG_ENTITY_TYPE_ENUM.create(bind, checkfirst=True)

    op.add_column(
        "projects",
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "in_progress",
                "review",
                "revision",
                "approved",
                "delivered",
                name="projectstatus",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column("projects", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_projects_created_by"), "projects", ["created_by"], unique=False)
    op.create_foreign_key(
        "fk_projects_created_by_users",
        "projects",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "shots",
        "status",
        existing_type=sa.String(length=32),
        type_=postgresql.ENUM(
            "pending",
            "in_progress",
            "review",
            "revision",
            "approved",
            "delivered",
            name="shotstatus",
            create_type=False,
        ),
        existing_nullable=False,
        postgresql_using="status::text::shotstatus",
    )
    op.alter_column("shots", "status", server_default="pending")
    op.add_column("shots", sa.Column("frame_start", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("frame_end", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("assigned_to", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_shots_assigned_to"), "shots", ["assigned_to"], unique=False)
    op.create_foreign_key(
        "fk_shots_assigned_to_users",
        "shots",
        "users",
        ["assigned_to"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_shots_frame_range",
        "shots",
        "frame_start IS NULL OR frame_end IS NULL OR frame_end >= frame_start",
    )

    op.alter_column(
        "assets",
        "asset_type",
        existing_type=sa.String(length=64),
        type_=postgresql.ENUM(
            "character",
            "prop",
            "environment",
            "fx",
            name="assettype",
            create_type=False,
        ),
        existing_nullable=False,
        postgresql_using="asset_type::text::assettype",
    )
    op.alter_column(
        "assets",
        "status",
        existing_type=sa.String(length=32),
        type_=postgresql.ENUM(
            "pending",
            "in_progress",
            "review",
            "revision",
            "approved",
            "delivered",
            name="assetstatus",
            create_type=False,
        ),
        existing_nullable=False,
        postgresql_using="status::text::assetstatus",
    )
    op.alter_column("assets", "status", server_default="pending")
    op.add_column("assets", sa.Column("assigned_to", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_assets_assigned_to"), "assets", ["assigned_to"], unique=False)
    op.create_foreign_key(
        "fk_assets_assigned_to_users",
        "assets",
        "users",
        ["assigned_to"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "status_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "entity_type",
            postgresql.ENUM(
                "project",
                "shot",
                "asset",
                name="statuslogentitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_status_logs_changed_at"), "status_logs", ["changed_at"], unique=False)
    op.create_index(op.f("ix_status_logs_changed_by"), "status_logs", ["changed_by"], unique=False)
    op.create_index(op.f("ix_status_logs_entity_id"), "status_logs", ["entity_id"], unique=False)
    op.create_index(
        op.f("ix_status_logs_entity_type"), "status_logs", ["entity_type"], unique=False
    )
    op.create_index(op.f("ix_status_logs_id"), "status_logs", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_index(op.f("ix_status_logs_id"), table_name="status_logs")
    op.drop_index(op.f("ix_status_logs_entity_type"), table_name="status_logs")
    op.drop_index(op.f("ix_status_logs_entity_id"), table_name="status_logs")
    op.drop_index(op.f("ix_status_logs_changed_by"), table_name="status_logs")
    op.drop_index(op.f("ix_status_logs_changed_at"), table_name="status_logs")
    op.drop_table("status_logs")

    op.drop_constraint("fk_assets_assigned_to_users", "assets", type_="foreignkey")
    op.drop_index(op.f("ix_assets_assigned_to"), table_name="assets")
    op.drop_column("assets", "assigned_to")
    op.alter_column("assets", "status", server_default=None)
    op.alter_column(
        "assets",
        "status",
        existing_type=postgresql.ENUM(
            "pending",
            "in_progress",
            "review",
            "revision",
            "approved",
            "delivered",
            name="assetstatus",
            create_type=False,
        ),
        type_=sa.String(length=32),
        existing_nullable=False,
        postgresql_using="status::text",
    )
    op.alter_column(
        "assets",
        "asset_type",
        existing_type=postgresql.ENUM(
            "character",
            "prop",
            "environment",
            "fx",
            name="assettype",
            create_type=False,
        ),
        type_=sa.String(length=64),
        existing_nullable=False,
        postgresql_using="asset_type::text",
    )

    op.drop_constraint("ck_shots_frame_range", "shots", type_="check")
    op.drop_constraint("fk_shots_assigned_to_users", "shots", type_="foreignkey")
    op.drop_index(op.f("ix_shots_assigned_to"), table_name="shots")
    op.drop_column("shots", "assigned_to")
    op.drop_column("shots", "frame_end")
    op.drop_column("shots", "frame_start")
    op.alter_column("shots", "status", server_default=None)
    op.alter_column(
        "shots",
        "status",
        existing_type=postgresql.ENUM(
            "pending",
            "in_progress",
            "review",
            "revision",
            "approved",
            "delivered",
            name="shotstatus",
            create_type=False,
        ),
        type_=sa.String(length=32),
        existing_nullable=False,
        postgresql_using="status::text",
    )

    op.drop_constraint("fk_projects_created_by_users", "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_created_by"), table_name="projects")
    op.drop_column("projects", "created_by")
    op.drop_column("projects", "status")

    STATUS_LOG_ENTITY_TYPE_ENUM.drop(bind, checkfirst=True)
    ASSET_TYPE_ENUM.drop(bind, checkfirst=True)
    ASSET_STATUS_ENUM.drop(bind, checkfirst=True)
    SHOT_STATUS_ENUM.drop(bind, checkfirst=True)
    PROJECT_STATUS_ENUM.drop(bind, checkfirst=True)
