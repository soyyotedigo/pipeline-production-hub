"""add_notes

Revision ID: d5e6f7a8b9c0
Revises: b2c3d4e5f6a7
Create Date: 2026-03-13 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Add 'client' value to rolename enum ──────────────────────────────
    op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'client'")

    # ── Create noteentitytype enum ────────────────────────────────────────
    noteentitytype = sa.Enum(
        "project",
        "episode",
        "sequence",
        "shot",
        "asset",
        "pipeline_task",
        "version",
        name="noteentitytype",
    )
    noteentitytype.create(op.get_bind(), checkfirst=True)

    # ── Create notes table ────────────────────────────────────────────────
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            postgresql.ENUM(
                "project",
                "episode",
                "sequence",
                "shot",
                "asset",
                "pipeline_task",
                "version",
                name="noteentitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "parent_note_id",
            sa.Uuid(),
            sa.ForeignKey("notes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_client_visible", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(op.f("ix_notes_id"), "notes", ["id"])
    op.create_index("ix_notes_entity", "notes", ["entity_type", "entity_id"])
    op.create_index(op.f("ix_notes_project_id"), "notes", ["project_id"])
    op.create_index(op.f("ix_notes_author_id"), "notes", ["author_id"])
    op.create_index(op.f("ix_notes_parent_note_id"), "notes", ["parent_note_id"])
    op.create_index(op.f("ix_notes_archived_at"), "notes", ["archived_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("notes")
    sa.Enum(name="noteentitytype").drop(op.get_bind(), checkfirst=True)
