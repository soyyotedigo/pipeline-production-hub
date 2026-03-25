"""add_deliveries

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-03-16 10:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    deliverystatus = postgresql.ENUM(
        "preparing",
        "sent",
        "acknowledged",
        "accepted",
        "rejected",
        name="deliverystatus",
    )
    deliverystatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("recipient", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="deliverystatus", create_type=False),
            nullable=False,
            server_default="preparing",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deliveries_project_id", "deliveries", ["project_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])
    op.create_index("ix_deliveries_delivery_date", "deliveries", ["delivery_date"])
    op.create_index("ix_deliveries_created_by", "deliveries", ["created_by"])

    op.create_table(
        "delivery_items",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column(
            "delivery_id",
            postgresql.UUID(),
            sa.ForeignKey("deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(),
            sa.ForeignKey("versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shot_id",
            postgresql.UUID(),
            sa.ForeignKey("shots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", "version_id", name="uq_delivery_version"),
    )
    op.create_index("ix_delivery_items_delivery_id", "delivery_items", ["delivery_id"])
    op.create_index("ix_delivery_items_version_id", "delivery_items", ["version_id"])
    op.create_index("ix_delivery_items_shot_id", "delivery_items", ["shot_id"])


def downgrade() -> None:
    op.drop_table("delivery_items")
    op.drop_table("deliveries")
    op.execute("DROP TYPE IF EXISTS deliverystatus")
