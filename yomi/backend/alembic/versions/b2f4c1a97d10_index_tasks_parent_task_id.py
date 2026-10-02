"""index tasks.parent_task_id

Revision ID: b2f4c1a97d10
Revises: 85c9edec8cb8
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f4c1a97d10'
down_revision: Union[str, Sequence[str], None] = '85c9edec8cb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Subtask lookups and soft-delete cascades hit parent_task_id on every request."""
    op.create_index(op.f('ix_tasks_parent_task_id'), 'tasks', ['parent_task_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tasks_parent_task_id'), table_name='tasks')