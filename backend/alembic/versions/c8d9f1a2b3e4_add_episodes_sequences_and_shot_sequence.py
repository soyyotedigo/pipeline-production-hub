"""add_episodes_sequences_and_shot_sequence

Revision ID: c8d9f1a2b3e4
Revises: 868c807dfacb
Create Date: 2026-03-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9f1a2b3e4"
down_revision: str | Sequence[str] | None = "868c807dfacb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEQUENCE_SCOPE_TYPE_ENUM = postgresql.ENUM(
    "sequence",
    "spot",
    "level",
    name="sequencescopetype",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    SEQUENCE_SCOPE_TYPE_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_episode_project_code"),
    )
    op.create_index(op.f("ix_episodes_id"), "episodes", ["id"], unique=False)
    op.create_index(op.f("ix_episodes_project_id"), "episodes", ["project_id"], unique=False)

    op.create_table(
        "sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "scope_type",
            postgresql.ENUM(
                "sequence", "spot", "level", name="sequencescopetype", create_type=False
            ),
            nullable=False,
            server_default="sequence",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_sequence_project_code"),
    )
    op.create_index(op.f("ix_sequences_episode_id"), "sequences", ["episode_id"], unique=False)
    op.create_index(op.f("ix_sequences_id"), "sequences", ["id"], unique=False)
    op.create_index(op.f("ix_sequences_project_id"), "sequences", ["project_id"], unique=False)

    op.add_column("shots", sa.Column("sequence_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_shots_sequence_id"), "shots", ["sequence_id"], unique=False)
    op.create_foreign_key(
        "fk_shots_sequence_id_sequences",
        "shots",
        "sequences",
        ["sequence_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_constraint("fk_shots_sequence_id_sequences", "shots", type_="foreignkey")
    op.drop_index(op.f("ix_shots_sequence_id"), table_name="shots")
    op.drop_column("shots", "sequence_id")

    op.drop_index(op.f("ix_sequences_project_id"), table_name="sequences")
    op.drop_index(op.f("ix_sequences_id"), table_name="sequences")
    op.drop_index(op.f("ix_sequences_episode_id"), table_name="sequences")
    op.drop_table("sequences")

    op.drop_index(op.f("ix_episodes_project_id"), table_name="episodes")
    op.drop_index(op.f("ix_episodes_id"), table_name="episodes")
    op.drop_table("episodes")

    SEQUENCE_SCOPE_TYPE_ENUM.drop(bind, checkfirst=True)
