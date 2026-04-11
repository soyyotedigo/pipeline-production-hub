"""add_archived_at_to_core_entities

Revision ID: a1b2c3d4e5f6
Revises: d4f0a6c1b7a2
Create Date: 2026-03-12 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "d4f0a6c1b7a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_projects_archived_at"), "projects", ["archived_at"], unique=False)

    op.add_column("assets", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_assets_archived_at"), "assets", ["archived_at"], unique=False)

    op.add_column("shots", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_shots_archived_at"), "shots", ["archived_at"], unique=False)

    op.add_column("episodes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_episodes_archived_at"), "episodes", ["archived_at"], unique=False)

    op.add_column("sequences", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_sequences_archived_at"), "sequences", ["archived_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_sequences_archived_at"), table_name="sequences")
    op.drop_column("sequences", "archived_at")

    op.drop_index(op.f("ix_episodes_archived_at"), table_name="episodes")
    op.drop_column("episodes", "archived_at")

    op.drop_index(op.f("ix_shots_archived_at"), table_name="shots")
    op.drop_column("shots", "archived_at")

    op.drop_index(op.f("ix_assets_archived_at"), table_name="assets")
    op.drop_column("assets", "archived_at")

    op.drop_index(op.f("ix_projects_archived_at"), table_name="projects")
    op.drop_column("projects", "archived_at")
