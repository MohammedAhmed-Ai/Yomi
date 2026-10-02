from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.db import get_db
from app.models import Task
from app.schemas import CarryOverResult
from app.time_utils import local_date

router = APIRouter(prefix="/carry-over", tags=["carry-over"])


def clone_for(original: Task, today, parent_task_id: int | None = None) -> Task:
    """A pending copy of `original`, planned for today and linked back to it.

    sort_order is carried over so the task keeps its place in the new day's order.
    recurrence_rule is deliberately not copied: this is the same unfinished work,
    not a new occurrence.
    """
    clone = Task(
        title=original.title,
        notes=original.notes,
        points=original.points,
        priority=original.priority,
        sort_order=original.sort_order,
        planned_date=today,
        original_date=original.original_date,
        parent_task_id=parent_task_id,
        status="pending",
        carry_count=(original.carry_count or 0) + 1,
        carried_from_id=original.id,
    )
    clone.tags = list(original.tags)
    return clone


@router.post("/", response_model=CarryOverResult)
def carry_over(db: Session = Depends(get_db)):
    """Move every unfinished task from a past day onto today.

    The original stays on its own day as a read-only "missed" record, so the day it
    belonged to keeps counting it as not done. Its pending subtasks are carried the
    same way, under the new parent.

    This is a system action, so it deliberately ignores the day lock: a locked day
    is a statement about the past, not a reason to keep carrying work forward.

    Idempotent: originals become "missed" and the copies are planned for today, so
    a second run finds nothing left to do and creates no duplicates.
    """
    today = local_date()

    overdue = db.execute(
        select(Task)
        .options(selectinload(Task.subtasks))
        .where(
            Task.status == "pending",
            Task.planned_date < today,
            Task.parent_task_id.is_(None),
        )
        .order_by(Task.planned_date, Task.id)
    ).scalars().unique().all()

    tasks_carried = 0
    subtasks_carried = 0

    for original in overdue:
        # Only pending children travel; missed or deleted ones stay as they are.
        pending_subtasks = [s for s in original.subtasks if s.status == "pending"]

        carried_parent = clone_for(original, today)
        db.add(carried_parent)
        db.flush()  # assign the new parent's id to its subtask copies
        tasks_carried += 1

        for subtask in pending_subtasks:
            db.add(clone_for(subtask, today, parent_task_id=carried_parent.id))
            subtasks_carried += 1

        original.status = "missed"
        for subtask in pending_subtasks:
            subtask.status = "missed"

    db.commit()

    return CarryOverResult(
        date=today,
        tasks_carried=tasks_carried,
        subtasks_carried=subtasks_carried,
        total_carried=tasks_carried + subtasks_carried,
    )