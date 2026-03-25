"""add_tags

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tagentitytype = postgresql.ENUM(
        "project",
        "episode",
        "sequence",
        "shot",
        "asset",
        "pipeline_task",
        "version",
        name="tagentitytype",
    )
    tagentitytype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_tag_project_name"),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"])
    op.create_index("ix_tags_name", "tags", ["name"])

    op.create_table(
        "entity_tags",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column(
            "tag_id",
            postgresql.UUID(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_type", postgresql.ENUM(name="tagentitytype", create_type=False), nullable=False
        ),
        sa.Column("entity_id", postgresql.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tag_id", "entity_type", "entity_id", name="uq_entity_tag"),
    )
    op.create_index("ix_entity_tags_tag_id", "entity_tags", ["tag_id"])
    op.create_index("ix_entity_tags_entity", "entity_tags", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("entity_tags")
    op.drop_table("tags")
    op.execute("DROP TYPE IF EXISTS tagentitytype")
