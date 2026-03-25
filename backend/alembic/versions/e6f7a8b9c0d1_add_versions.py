"""add_versions

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Expand statuslogentitytype with 'version' ─────────────────────────
    op.execute("ALTER TYPE statuslogentitytype ADD VALUE IF NOT EXISTS 'version'")

    # ── Create versionstatus enum ─────────────────────────────────────────
    versionstatus = sa.Enum(
        "pending_review",
        "approved",
        "revision_requested",
        "final",
        name="versionstatus",
    )
    versionstatus.create(op.get_bind(), checkfirst=True)

    # ── Create versions table ─────────────────────────────────────────────
    op.create_table(
        "versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shot_id",
            sa.Uuid(),
            sa.ForeignKey("shots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "pipeline_task_id",
            sa.Uuid(),
            sa.ForeignKey("pipeline_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending_review",
                "approved",
                "revision_requested",
                "final",
                name="versionstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "submitted_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("media_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "shot_id IS NOT NULL OR asset_id IS NOT NULL",
            name="ck_version_entity",
        ),
    )

    op.create_index(op.f("ix_versions_id"), "versions", ["id"])
    op.create_index(op.f("ix_versions_project_id"), "versions", ["project_id"])
    op.create_index(op.f("ix_versions_shot_id"), "versions", ["shot_id"])
    op.create_index(op.f("ix_versions_asset_id"), "versions", ["asset_id"])
    op.create_index(op.f("ix_versions_pipeline_task_id"), "versions", ["pipeline_task_id"])
    op.create_index(op.f("ix_versions_submitted_by"), "versions", ["submitted_by"])
    op.create_index(op.f("ix_versions_status"), "versions", ["status"])
    op.create_index(op.f("ix_versions_archived_at"), "versions", ["archived_at"])

    # ── Add version_id to files ───────────────────────────────────────────
    op.add_column(
        "files",
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_files_version_id"), "files", ["version_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_files_version_id"), table_name="files")
    op.drop_column("files", "version_id")
    op.drop_table("versions")
    sa.Enum(name="versionstatus").drop(op.get_bind(), checkfirst=True)
