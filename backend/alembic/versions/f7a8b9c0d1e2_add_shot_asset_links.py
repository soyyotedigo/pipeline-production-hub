"""add_shot_asset_links

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-13 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Create linktype enum ──────────────────────────────────────────────
    linktype = sa.Enum("uses", "references", "instance_of", name="linktype")
    linktype.create(op.get_bind(), checkfirst=True)

    # ── Create shot_asset_links table ─────────────────────────────────────
    op.create_table(
        "shot_asset_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "shot_id",
            sa.Uuid(),
            sa.ForeignKey("shots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "link_type",
            postgresql.ENUM(
                "uses", "references", "instance_of", name="linktype", create_type=False
            ),
            nullable=False,
            server_default="uses",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("shot_id", "asset_id", name="uq_shot_asset_link"),
    )

    op.create_index(op.f("ix_shot_asset_links_id"), "shot_asset_links", ["id"])
    op.create_index(op.f("ix_shot_asset_links_shot_id"), "shot_asset_links", ["shot_id"])
    op.create_index(op.f("ix_shot_asset_links_asset_id"), "shot_asset_links", ["asset_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("shot_asset_links")
    sa.Enum(name="linktype").drop(op.get_bind(), checkfirst=True)
