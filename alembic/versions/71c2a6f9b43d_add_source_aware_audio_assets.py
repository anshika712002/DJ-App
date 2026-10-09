"""add source-aware audio assets and request track metadata

Revision ID: 71c2a6f9b43d
Revises: d66802f3171b
Create Date: 2026-10-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "71c2a6f9b43d"
down_revision: Union[str, Sequence[str], None] = "d66802f3171b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "song_requests",
        sa.Column("trackMetadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ownerId", sa.Integer(), nullable=False),
        sa.Column("sourceType", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist", sa.String(length=255), nullable=True),
        sa.Column("artwork", sa.String(length=2048), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("filePath", sa.String(length=512), nullable=False),
        sa.Column("license", sa.String(length=255), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("createdAt", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ownerId"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filePath"),
    )
    op.create_index(op.f("ix_audio_assets_id"), "audio_assets", ["id"], unique=False)
    op.create_index(
        op.f("ix_audio_assets_ownerId"), "audio_assets", ["ownerId"], unique=False
    )
    op.create_index(
        op.f("ix_audio_assets_sourceType"),
        "audio_assets",
        ["sourceType"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audio_assets_sourceType"), table_name="audio_assets")
    op.drop_index(op.f("ix_audio_assets_ownerId"), table_name="audio_assets")
    op.drop_index(op.f("ix_audio_assets_id"), table_name="audio_assets")
    op.drop_table("audio_assets")
    op.drop_column("song_requests", "trackMetadata")
