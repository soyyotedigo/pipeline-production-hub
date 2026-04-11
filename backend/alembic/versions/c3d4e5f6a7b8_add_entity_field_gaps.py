"""add_entity_field_gaps

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create new enum types
    priority_enum = postgresql.ENUM(
        "low", "normal", "high", "urgent", name="priority", create_type=False
    )
    priority_enum.create(op.get_bind(), checkfirst=True)

    difficulty_enum = postgresql.ENUM(
        "easy", "medium", "hard", "hero", name="difficulty", create_type=False
    )
    difficulty_enum.create(op.get_bind(), checkfirst=True)

    filetype_enum = postgresql.ENUM(
        "source_scene",
        "render",
        "plate",
        "reference",
        "delivery",
        "thumbnail",
        name="filetype",
        create_type=False,
    )
    filetype_enum.create(op.get_bind(), checkfirst=True)

    filestatus_enum = postgresql.ENUM(
        "wip",
        "published",
        "approved",
        "deprecated",
        name="filestatus",
        create_type=False,
    )
    filestatus_enum.create(op.get_bind(), checkfirst=True)

    episodestatus_enum = postgresql.ENUM(
        "active",
        "in_progress",
        "completed",
        "on_hold",
        "omitted",
        name="episodestatus",
        create_type=False,
    )
    episodestatus_enum.create(op.get_bind(), checkfirst=True)

    sequencestatus_enum = postgresql.ENUM(
        "active",
        "in_progress",
        "completed",
        "on_hold",
        "omitted",
        name="sequencestatus",
        create_type=False,
    )
    sequencestatus_enum.create(op.get_bind(), checkfirst=True)

    # 2. Expand existing enums with new values
    # AssetType expansions
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'vehicle'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'set_piece'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'matte_painting'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'texture'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'hdri'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'camera'")
    op.execute("ALTER TYPE assettype ADD VALUE IF NOT EXISTS 'assembly'")

    # PipelineStepType expansions
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'matchmove'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'prep'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'matte_painting'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'cfx'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'editorial'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'rendering'")
    op.execute("ALTER TYPE pipelinesteptype ADD VALUE IF NOT EXISTS 'texture'")

    # ShotStatus expansions
    op.execute("ALTER TYPE shotstatus ADD VALUE IF NOT EXISTS 'on_hold'")
    op.execute("ALTER TYPE shotstatus ADD VALUE IF NOT EXISTS 'omitted'")
    op.execute("ALTER TYPE shotstatus ADD VALUE IF NOT EXISTS 'final'")

    # AssetStatus expansions
    op.execute("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'on_hold'")
    op.execute("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'omitted'")
    op.execute("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'final'")

    # ProjectStatus expansions
    op.execute("ALTER TYPE projectstatus ADD VALUE IF NOT EXISTS 'on_hold'")
    op.execute("ALTER TYPE projectstatus ADD VALUE IF NOT EXISTS 'omitted'")
    op.execute("ALTER TYPE projectstatus ADD VALUE IF NOT EXISTS 'final'")
    op.execute("ALTER TYPE projectstatus ADD VALUE IF NOT EXISTS 'bidding'")

    # 3. ALTER TABLE — User profile fields
    op.add_column("users", sa.Column("first_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("department", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(30), nullable=True))

    # 4. ALTER TABLE — Project production fields
    op.add_column("projects", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("fps", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("resolution_width", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("resolution_height", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("thumbnail_url", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("color_space", sa.String(50), nullable=True))

    # 5. ALTER TABLE — Shot new fields
    op.add_column("shots", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("shots", sa.Column("thumbnail_url", sa.String(500), nullable=True))
    op.add_column(
        "shots",
        sa.Column(
            "priority",
            postgresql.ENUM("low", "normal", "high", "urgent", name="priority", create_type=False),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "shots",
        sa.Column(
            "difficulty",
            postgresql.ENUM("easy", "medium", "hard", "hero", name="difficulty", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("shots", sa.Column("handle_head", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("handle_tail", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("cut_in", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("cut_out", sa.Integer(), nullable=True))
    op.add_column("shots", sa.Column("bid_days", sa.Float(), nullable=True))
    op.add_column("shots", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # 6. ALTER TABLE — Asset new fields
    op.add_column("assets", sa.Column("code", sa.String(50), nullable=True))
    op.add_column("assets", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("thumbnail_url", sa.String(500), nullable=True))
    op.add_column(
        "assets",
        sa.Column(
            "priority",
            postgresql.ENUM("low", "normal", "high", "urgent", name="priority", create_type=False),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column("assets", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_asset_project_code", "assets", ["project_id", "code"])

    # 7. ALTER TABLE — Episode new fields
    op.add_column(
        "episodes",
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "in_progress",
                "completed",
                "on_hold",
                "omitted",
                name="episodestatus",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("episodes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("episodes", sa.Column("order", sa.Integer(), nullable=True))
    op.add_column("episodes", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # 8. ALTER TABLE — Sequence new fields
    op.add_column(
        "sequences",
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "in_progress",
                "completed",
                "on_hold",
                "omitted",
                name="sequencestatus",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("sequences", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("sequences", sa.Column("order", sa.Integer(), nullable=True))
    op.add_column("sequences", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # 9. ALTER TABLE — File pipeline context fields
    op.add_column(
        "files",
        sa.Column(
            "pipeline_task_id",
            sa.Uuid(),
            sa.ForeignKey("pipeline_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "file_type",
            postgresql.ENUM(
                "source_scene",
                "render",
                "plate",
                "reference",
                "delivery",
                "thumbnail",
                name="filetype",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "file_status",
            postgresql.ENUM(
                "wip", "published", "approved", "deprecated", name="filestatus", create_type=False
            ),
            nullable=False,
            server_default="wip",
        ),
    )
    op.add_column("files", sa.Column("comment", sa.Text(), nullable=True))
    op.create_index("ix_files_pipeline_task_id", "files", ["pipeline_task_id"])


def downgrade() -> None:
    # Files
    op.drop_index("ix_files_pipeline_task_id", table_name="files")
    op.drop_column("files", "comment")
    op.drop_column("files", "file_status")
    op.drop_column("files", "file_type")
    op.drop_column("files", "pipeline_task_id")

    # Sequences
    op.drop_column("sequences", "updated_at")
    op.drop_column("sequences", "order")
    op.drop_column("sequences", "description")
    op.drop_column("sequences", "status")

    # Episodes
    op.drop_column("episodes", "updated_at")
    op.drop_column("episodes", "order")
    op.drop_column("episodes", "description")
    op.drop_column("episodes", "status")

    # Assets
    op.drop_constraint("uq_asset_project_code", "assets", type_="unique")
    op.drop_column("assets", "updated_at")
    op.drop_column("assets", "priority")
    op.drop_column("assets", "thumbnail_url")
    op.drop_column("assets", "description")
    op.drop_column("assets", "code")

    # Shots
    op.drop_column("shots", "updated_at")
    op.drop_column("shots", "bid_days")
    op.drop_column("shots", "cut_out")
    op.drop_column("shots", "cut_in")
    op.drop_column("shots", "handle_tail")
    op.drop_column("shots", "handle_head")
    op.drop_column("shots", "difficulty")
    op.drop_column("shots", "priority")
    op.drop_column("shots", "thumbnail_url")
    op.drop_column("shots", "description")

    # Projects
    op.drop_column("projects", "color_space")
    op.drop_column("projects", "thumbnail_url")
    op.drop_column("projects", "resolution_height")
    op.drop_column("projects", "resolution_width")
    op.drop_column("projects", "fps")
    op.drop_column("projects", "end_date")
    op.drop_column("projects", "start_date")

    # Users
    op.drop_column("users", "phone")
    op.drop_column("users", "timezone")
    op.drop_column("users", "department")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

    # Drop new enum types
    sa.Enum(name="sequencestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="episodestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="filestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="filetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="difficulty").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="priority").drop(op.get_bind(), checkfirst=True)

    # Note: ALTER TYPE ... REMOVE VALUE is not supported in PostgreSQL
    # Enum value removals from existing types (assettype, pipelinesteptype,
    # shotstatus, assetstatus, projectstatus) cannot be done in downgrade.
