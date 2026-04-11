"""add_playlists

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-03-14 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Enums ─────────────────────────────────────────────────────────────
    playliststatus = sa.Enum("draft", "in_progress", "completed", name="playliststatus")
    playliststatus.create(op.get_bind(), checkfirst=True)

    reviewstatus = sa.Enum("pending", "approved", "revision_requested", name="reviewstatus")
    reviewstatus.create(op.get_bind(), checkfirst=True)

    # ── playlists ─────────────────────────────────────────────────────────
    op.create_table(
        "playlists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "in_progress", "completed", name="playliststatus", create_type=False
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_playlists_id"), "playlists", ["id"])
    op.create_index(op.f("ix_playlists_project_id"), "playlists", ["project_id"])
    op.create_index(op.f("ix_playlists_created_by"), "playlists", ["created_by"])
    op.create_index(op.f("ix_playlists_date"), "playlists", ["date"])
    op.create_index(op.f("ix_playlists_archived_at"), "playlists", ["archived_at"])

    # ── playlist_items ────────────────────────────────────────────────────
    op.create_table(
        "playlist_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "playlist_id",
            sa.Uuid(),
            sa.ForeignKey("playlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column(
            "review_status",
            postgresql.ENUM(
                "pending", "approved", "revision_requested", name="reviewstatus", create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("playlist_id", "version_id", name="uq_playlist_version"),
    )
    op.create_index(op.f("ix_playlist_items_id"), "playlist_items", ["id"])
    op.create_index(op.f("ix_playlist_items_playlist_id"), "playlist_items", ["playlist_id"])
    op.create_index(op.f("ix_playlist_items_version_id"), "playlist_items", ["version_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("playlist_items")
    op.drop_table("playlists")
    sa.Enum(name="reviewstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="playliststatus").drop(op.get_bind(), checkfirst=True)
