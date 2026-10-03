from fastapi import APIRouter, Depends
import sqlite3

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Task
from app.schemas import CarryOverResult
from app.task_queries import active_tasks
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

    for attempt in range(2):
        try:
            overdue = db.execute(
                active_tasks(
                    Task.status == "pending",
                    Task.planned_date < today,
                    Task.parent_task_id.is_(None),
                )
                .options(selectinload(Task.subtasks))
                .order_by(Task.planned_date, Task.id)
            ).scalars().unique().all()

            tasks_carried = 0
            subtasks_carried = 0

            for original in overdue:
                pending_subtasks = [
                    subtask
                    for subtask in original.subtasks
                    if subtask.status == "pending"
                ]
                if _has_copy(db, original.id):
                    original.status = "missed"
                    continue

                carried_parent = clone_for(original, today)
                db.add(carried_parent)
                db.flush()
                tasks_carried += 1

                for subtask in pending_subtasks:
                    if _has_copy(db, subtask.id):
                        continue
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
        except IntegrityError as exc:
            db.rollback()
            if attempt == 0 and _is_carried_from_conflict(db, exc):
                continue
            raise

    raise RuntimeError("Carry-over retry exhausted unexpectedly")


def _has_copy(db: Session, source_id: int) -> bool:
    return db.execute(
        select(Task.id).where(Task.carried_from_id == source_id)
    ).scalar_one_or_none() is not None


def _is_carried_from_conflict(db: Session, error: IntegrityError) -> bool:
    original = error.orig
    return (
        db.get_bind().dialect.name == "sqlite"
        and isinstance(original, sqlite3.IntegrityError)
        and getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
        and "tasks.carried_from_id" in str(original)
    )