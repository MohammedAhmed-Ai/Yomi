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


def load_source_miss_reasons(db: Session, tasks: list[Task]) -> list[Task]:
    """Populate carried copies' source reasons with one batched lookup."""
    source_ids = {task.carried_from_id for task in tasks if task.carried_from_id is not None}
    if not source_ids:
        return tasks

    reasons = dict(
        db.execute(
            select(Task.id, Task.miss_reason).where(Task.id.in_(source_ids))
        ).all()
    )
    for task in tasks:
        if task.carried_from_id is not None:
            task.source_miss_reason = reasons.get(task.carried_from_id)
    return tasks
