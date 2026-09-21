"""Add AI Master ownership tables.

Revision ID: 0016_ai_master
Revises: 0015_dashboard_perf_indexes
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0016_ai_master"
down_revision = "0015_dashboard_perf_indexes"
branch_labels = None
depends_on = None

_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=3), "mysql")


def upgrade() -> None:
    op.create_table(
        "ai_master",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", _DATETIME, nullable=False),
        sa.Column("updated_at", _DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_ai_master_name"),
    )
    op.create_index("ix_ai_master_name", "ai_master", ["name"])
    op.create_table(
        "component_ai_master",
        sa.Column("component_id", sa.String(128), nullable=False),
        sa.Column("ai_master_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["ai_master_id"], ["ai_master.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("component_id"),
        sa.UniqueConstraint("component_id", name="uq_component_ai_master_component"),
    )
    op.create_index(
        "ix_component_ai_master_master", "component_ai_master", ["ai_master_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_component_ai_master_master", table_name="component_ai_master")
    op.drop_table("component_ai_master")
    op.drop_index("ix_ai_master_name", table_name="ai_master")
    op.drop_table("ai_master")
