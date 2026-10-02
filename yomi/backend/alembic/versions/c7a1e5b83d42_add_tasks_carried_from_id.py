"""add tasks.carried_from_id

Revision ID: c7a1e5b83d42
Revises: b2f4c1a97d10
Create Date: 2026-10-03 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1e5b83d42'
down_revision: Union[str, Sequence[str], None] = 'b2f4c1a97d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Link a carried-over task back to the copy it came from.

    SQLite cannot add a foreign key to an existing table with ALTER TABLE, so the
    batch mode recreates 'tasks' and copies every existing row across unchanged.
    """
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.add_column(sa.Column("carried_from_id", sa.Integer(), nullable=True))
        batch.create_index(op.f("ix_tasks_carried_from_id"), ["carried_from_id"], unique=False)
        batch.create_foreign_key(
            "fk_tasks_carried_from_id_tasks", "tasks", ["carried_from_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("fk_tasks_carried_from_id_tasks", type_="foreignkey")
        batch.drop_index(op.f("ix_tasks_carried_from_id"))
        batch.drop_column("carried_from_id")