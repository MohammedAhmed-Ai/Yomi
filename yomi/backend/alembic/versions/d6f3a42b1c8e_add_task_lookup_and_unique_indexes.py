"""add task lookup and uniqueness indexes

Revision ID: d6f3a42b1c8e
Revises: c7a1e5b83d42
Create Date: 2026-10-03 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6f3a42b1c8e"
down_revision: Union[str, Sequence[str], None] = "c7a1e5b83d42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create requested indexes only when their names are not already present."""
    bind = op.get_bind()
    existing = {index["name"] for index in sa.inspect(bind).get_indexes("tasks")}
    indexes = (
        ("ix_tasks_planned_date_status", ["planned_date", "status"], False, None),
        ("ix_tasks_completed_date", ["completed_date"], False, None),
        ("ix_tasks_carried_from_id", ["carried_from_id"], False, None),
        (
            "uq_tasks_carried_from_id_not_null",
            ["carried_from_id"],
            True,
            sa.text("carried_from_id IS NOT NULL"),
        ),
    )
    for name, columns, unique, where in indexes:
        if name not in existing:
            op.create_index(
                name,
                "tasks",
                columns,
                unique=unique,
                sqlite_where=where,
            )


def downgrade() -> None:
    """Remove indexes introduced here, preserving the carried_from lookup index."""
    bind = op.get_bind()
    existing = {index["name"] for index in sa.inspect(bind).get_indexes("tasks")}
    for name in (
        "uq_tasks_carried_from_id_not_null",
        "ix_tasks_completed_date",
        "ix_tasks_planned_date_status",
    ):
        if name in existing:
            op.drop_index(name, table_name="tasks")
