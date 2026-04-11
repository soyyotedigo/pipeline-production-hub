"""merge heads

Revision ID: baa1b24e0ffb
Revises: a2b3c4d5e6f7, b2c3d4e5f6a1, b9c0d1e2f3a4, c3d4e5f6a1b2
Create Date: 2026-03-21 15:30:51.464144

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "baa1b24e0ffb"
down_revision: str | Sequence[str] | None = (
    "a2b3c4d5e6f7",
    "b2c3d4e5f6a1",
    "b9c0d1e2f3a4",
    "c3d4e5f6a1b2",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
