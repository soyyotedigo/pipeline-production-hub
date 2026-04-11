"""add_time_logs

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-16 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "time_logs",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pipeline_task_id",
            postgresql.UUID(),
            sa.ForeignKey("pipeline_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 1440", name="ck_duration_range"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_time_logs_project_id", "time_logs", ["project_id"])
    op.create_index("ix_time_logs_pipeline_task_id", "time_logs", ["pipeline_task_id"])
    op.create_index("ix_time_logs_user_id", "time_logs", ["user_id"])
    op.create_index("ix_time_logs_date", "time_logs", ["date"])
    op.create_index("ix_time_logs_user_date", "time_logs", ["user_id", "date"])


def downgrade() -> None:
    op.drop_table("time_logs")
