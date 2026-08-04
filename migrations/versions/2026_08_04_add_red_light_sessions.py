"""add red_light_sessions table

Revision ID: c7f2a4e819b1
Revises: b1e4f9a2c83d
Create Date: 2026-08-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7f2a4e819b1"
down_revision: Union[str, Sequence[str], None] = "b1e4f9a2c83d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "red_light_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("health", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rlgl_namespace_user", "red_light_sessions", ["namespace", "user_id"]
    )
    op.create_index("idx_rlgl_status", "red_light_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("idx_rlgl_status", table_name="red_light_sessions")
    op.drop_index("idx_rlgl_namespace_user", table_name="red_light_sessions")
    op.drop_table("red_light_sessions")
