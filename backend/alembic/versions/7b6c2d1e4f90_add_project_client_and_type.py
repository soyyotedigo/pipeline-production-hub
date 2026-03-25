"""add_project_client_and_type

Revision ID: 7b6c2d1e4f90
Revises: 2ac41a0f7e9b
Create Date: 2026-03-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b6c2d1e4f90"
down_revision: str | Sequence[str] | None = "2ac41a0f7e9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROJECT_TYPE_ENUM = postgresql.ENUM(
    "film",
    "series",
    "commercial",
    "game",
    "other",
    name="projecttype",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    PROJECT_TYPE_ENUM.create(bind, checkfirst=True)

    op.add_column("projects", sa.Column("client", sa.String(length=255), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "project_type",
            postgresql.ENUM(
                "film",
                "series",
                "commercial",
                "game",
                "other",
                name="projecttype",
                create_type=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_column("projects", "project_type")
    op.drop_column("projects", "client")

    PROJECT_TYPE_ENUM.drop(bind, checkfirst=True)
