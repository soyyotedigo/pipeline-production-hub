"""add_notifications

Revision ID: a2b3c4d5e6f7
Revises: f7a8b9c0d1e2
Create Date: 2026-03-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Create enums ─────────────────────────────────────────────────────────
    notificationeventtype = sa.Enum(
        "task_assigned",
        "task_status_changed",
        "note_created",
        "note_reply",
        "version_submitted",
        "version_reviewed",
        "status_changed",
        "mention",
        name="notificationeventtype",
    )
    notificationeventtype.create(op.get_bind(), checkfirst=True)

    notificationentitytype = sa.Enum(
        "project",
        "shot",
        "asset",
        "pipeline_task",
        "note",
        "version",
        "playlist",
        name="notificationentitytype",
    )
    notificationentitytype.create(op.get_bind(), checkfirst=True)

    # ── Create notifications table ────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "task_assigned",
                "task_status_changed",
                "note_created",
                "note_reply",
                "version_submitted",
                "version_reviewed",
                "status_changed",
                "mention",
                name="notificationeventtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            postgresql.ENUM(
                "project",
                "shot",
                "asset",
                "pipeline_task",
                "note",
                "version",
                "playlist",
                name="notificationentitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_project_id", "notifications", ["project_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_project_id", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notificationeventtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationentitytype").drop(op.get_bind(), checkfirst=True)
