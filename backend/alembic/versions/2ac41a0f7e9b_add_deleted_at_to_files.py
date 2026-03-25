"""add_deleted_at_to_files

Revision ID: 2ac41a0f7e9b
Revises: f3b19d4a6c2e
Create Date: 2026-03-04 20:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ac41a0f7e9b"
down_revision: str | Sequence[str] | None = "f3b19d4a6c2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("files", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("files", "deleted_at")
