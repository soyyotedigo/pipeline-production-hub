"""add_pipeline_tasks

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── Enums ────────────────────────────────────────────────────────────
    pipelinesteptype = sa.Enum(
        "layout",
        "animation",
        "fx",
        "lighting",
        "compositing",
        "roto",
        "paint",
        "modeling",
        "rigging",
        "shading",
        "groom",
        "lookdev",
        name="pipelinesteptype",
    )
    pipelinesteptype.create(op.get_bind(), checkfirst=True)

    pipelinestepappliesto = sa.Enum(
        "shot",
        "asset",
        "both",
        name="pipelinestepappliesto",
    )
    pipelinestepappliesto.create(op.get_bind(), checkfirst=True)

    pipelinetaskstatus = sa.Enum(
        "blocked",
        "pending",
        "in_progress",
        "review",
        "revision",
        "approved",
        name="pipelinetaskstatus",
    )
    pipelinetaskstatus.create(op.get_bind(), checkfirst=True)

    # ── Add pipeline_task to statuslogentitytype enum ────────────────────
    op.execute("ALTER TYPE statuslogentitytype ADD VALUE IF NOT EXISTS 'pipeline_task'")

    # ── pipeline_templates ───────────────────────────────────────────────
    op.create_table(
        "pipeline_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_pipeline_templates_id"), "pipeline_templates", ["id"])
    op.create_index(
        op.f("ix_pipeline_templates_project_type"), "pipeline_templates", ["project_type"]
    )
    op.create_index(
        op.f("ix_pipeline_templates_archived_at"), "pipeline_templates", ["archived_at"]
    )

    # ── pipeline_template_steps ──────────────────────────────────────────
    op.create_table(
        "pipeline_template_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(255), nullable=False),
        sa.Column(
            "step_type",
            postgresql.ENUM(
                "layout",
                "animation",
                "fx",
                "lighting",
                "compositing",
                "roto",
                "paint",
                "modeling",
                "rigging",
                "shading",
                "groom",
                "lookdev",
                name="pipelinesteptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column(
            "applies_to",
            postgresql.ENUM(
                "shot", "asset", "both", name="pipelinestepappliesto", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_pipeline_template_steps_id"), "pipeline_template_steps", ["id"])
    op.create_index(
        op.f("ix_pipeline_template_steps_template_id"), "pipeline_template_steps", ["template_id"]
    )

    # ── pipeline_tasks ───────────────────────────────────────────────────
    op.create_table(
        "pipeline_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "shot_id",
            sa.Uuid(),
            sa.ForeignKey("shots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("step_name", sa.String(255), nullable=False),
        sa.Column(
            "step_type",
            postgresql.ENUM(
                "layout",
                "animation",
                "fx",
                "lighting",
                "compositing",
                "roto",
                "paint",
                "modeling",
                "rigging",
                "shading",
                "groom",
                "lookdev",
                name="pipelinesteptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "blocked",
                "pending",
                "in_progress",
                "review",
                "revision",
                "approved",
                name="pipelinetaskstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="blocked",
        ),
        sa.Column(
            "assigned_to",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(shot_id IS NOT NULL AND asset_id IS NULL) OR (shot_id IS NULL AND asset_id IS NOT NULL)",
            name="ck_pipeline_tasks_one_parent",
        ),
    )
    op.create_index(op.f("ix_pipeline_tasks_id"), "pipeline_tasks", ["id"])
    op.create_index(op.f("ix_pipeline_tasks_shot_id"), "pipeline_tasks", ["shot_id"])
    op.create_index(op.f("ix_pipeline_tasks_asset_id"), "pipeline_tasks", ["asset_id"])
    op.create_index(op.f("ix_pipeline_tasks_assigned_to"), "pipeline_tasks", ["assigned_to"])
    op.create_index(op.f("ix_pipeline_tasks_archived_at"), "pipeline_tasks", ["archived_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("pipeline_tasks")
    op.drop_table("pipeline_template_steps")
    op.drop_table("pipeline_templates")

    sa.Enum(name="pipelinetaskstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="pipelinestepappliesto").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="pipelinesteptype").drop(op.get_bind(), checkfirst=True)
