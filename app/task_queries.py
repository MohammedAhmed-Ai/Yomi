from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Task


def active_tasks(*criteria: ColumnElement[bool]) -> Select[tuple[Task]]:
    """Build a task query that always excludes soft-deleted rows."""
    return select(Task).where(Task.status != "deleted", *criteria)


def active_task_conditions(
    *criteria: ColumnElement[bool],
) -> tuple[ColumnElement[bool], ...]:
    """Return reusable criteria for task queries and aggregate queries."""
    return (Task.status != "deleted", *criteria)


def get_active_task(db: Session, task_id: int) -> Task | None:
    return db.execute(active_tasks(Task.id == task_id)).scalar_one_or_none()


def is_active_task(task: Task) -> bool:
    return task.status != "deleted"
