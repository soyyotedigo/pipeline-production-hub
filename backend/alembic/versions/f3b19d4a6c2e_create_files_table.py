"""create_files_table

Revision ID: f3b19d4a6c2e
Revises: e4a8f8d2c6b1
Create Date: 2026-03-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b19d4a6c2e"
down_revision: str | Sequence[str] | None = "e4a8f8d2c6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("shot_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "((shot_id IS NOT NULL)::int + (asset_id IS NOT NULL)::int) = 1",
            name="ck_files_exactly_one_parent",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size_non_negative"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "original_name", "version", name="uq_files_asset_original_version"
        ),
        sa.UniqueConstraint(
            "shot_id", "original_name", "version", name="uq_files_shot_original_version"
        ),
    )
    op.create_index(op.f("ix_files_asset_id"), "files", ["asset_id"], unique=False)
    op.create_index(op.f("ix_files_checksum_sha256"), "files", ["checksum_sha256"], unique=False)
    op.create_index(op.f("ix_files_id"), "files", ["id"], unique=False)
    op.create_index(op.f("ix_files_original_name"), "files", ["original_name"], unique=False)
    op.create_index(op.f("ix_files_shot_id"), "files", ["shot_id"], unique=False)
    op.create_index(op.f("ix_files_uploaded_by"), "files", ["uploaded_by"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_files_uploaded_by"), table_name="files")
    op.drop_index(op.f("ix_files_shot_id"), table_name="files")
    op.drop_index(op.f("ix_files_original_name"), table_name="files")
    op.drop_index(op.f("ix_files_id"), table_name="files")
    op.drop_index(op.f("ix_files_checksum_sha256"), table_name="files")
    op.drop_index(op.f("ix_files_asset_id"), table_name="files")
    op.drop_table("files")
