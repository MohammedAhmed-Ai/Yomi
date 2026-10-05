from fastapi import APIRouter, Depends
import sqlite3

from sqlalchemy.exc import IntegrityError
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Task, TaskTag
from app.schemas import CarryOverResult
from app.task_queries import active_tasks
from app.time_utils import local_date

router = APIRouter(prefix="/carry-over", tags=["carry-over"])

# SQLite caps the bound parameters a single statement may carry, so the set-based
# reads and writes below are applied in slices. One slice covers any realistic
# backlog, so the statement count stays flat as the backlog grows.
_SLICE = 400


def clone_values(original: Task, today, parent_task_id: int | None = None) -> dict:
    """Column values for a pending copy of `original`, planned for today and
    linked back to it.

    sort_order is carried over so the task keeps its place in the new day's order.
    recurrence_rule is deliberately not copied: this is the same unfinished work,
    not a new occurrence.
    """
    return {
        "title": original.title,
        "notes": original.notes,
        "points": original.points,
        "priority": original.priority,
        "sort_order": original.sort_order,
        "planned_date": today,
        "original_date": original.original_date,
        "parent_task_id": parent_task_id,
        "status": "pending",
        "carry_count": (original.carry_count or 0) + 1,
        "carried_from_id": original.id,
    }


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

    The whole backlog is handled with a fixed number of statements: everything is
    read up front, the copies are written in bulk, and the originals are flipped
    to "missed" in one set-based update.
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

            # Everything the run needs to decide is read here, once: the pending
            # subtasks travelling with each root, and which of those sources
            # already have a copy. Both are set lookups from here on.
            pending_subtasks_by_root = {
                original.id: [
                    subtask
                    for subtask in original.subtasks
                    if subtask.status == "pending"
                ]
                for original in overdue
            }
            already_copied = _copied_source_ids(
                db,
                {original.id for original in overdue}
                | {
                    subtask.id
                    for subtasks in pending_subtasks_by_root.values()
                    for subtask in subtasks
                },
            )

            # An original that already has a copy is left as a "missed" record
            # only; nothing new is planned for it.
            spent_ids = [original.id for original in overdue if original.id in already_copied]
            roots_to_carry = [
                (original, pending_subtasks_by_root[original.id])
                for original in overdue
                if original.id not in already_copied
            ]

            parent_rows = [
                (original, clone_values(original, today)) for original, _ in roots_to_carry
            ]
            parent_ids = _insert_clones(db, [row for _, row in parent_rows])

            subtask_rows = [
                (subtask, clone_values(subtask, today, parent_task_id=parent_ids[original.id]))
                for original, pending in roots_to_carry
                for subtask in pending
                if subtask.id not in already_copied
            ]
            subtask_ids = _insert_clones(db, [row for _, row in subtask_rows])

            carried = [(original, parent_ids[original.id]) for original, _ in parent_rows]
            carried += [(subtask, subtask_ids[subtask.id]) for subtask, _ in subtask_rows]
            _insert_tag_links(
                db,
                [
                    {"task_id": new_id, "tag_id": tag.id}
                    for source, new_id in carried
                    for tag in source.tags
                ],
            )

            _mark_missed(
                db,
                spent_ids
                + [original.id for original, _ in roots_to_carry]
                + [subtask.id for subtask, _ in subtask_rows],
            )

            db.commit()
            return CarryOverResult(
                date=today,
                tasks_carried=len(parent_rows),
                subtasks_carried=len(subtask_rows),
                total_carried=len(parent_rows) + len(subtask_rows),
            )
        except IntegrityError as exc:
            db.rollback()
            if attempt == 0 and _is_carried_from_conflict(db, exc):
                continue
            raise

    raise RuntimeError("Carry-over retry exhausted unexpectedly")


def _copied_source_ids(db: Session, source_ids: set[int]) -> set[int]:
    """The subset of `source_ids` that already has a copy.

    One statement per slice, instead of one existence query per task.
    """
    copied: set[int] = set()
    ordered = sorted(source_ids)
    for start in range(0, len(ordered), _SLICE):
        rows = db.execute(
            select(Task.carried_from_id).where(
                Task.carried_from_id.in_(ordered[start : start + _SLICE])
            )
        ).scalars()
        copied.update(source_id for source_id in rows if source_id is not None)
    return copied


def _insert_clones(db: Session, rows: list[dict]) -> dict[int, int]:
    """Write every clone in one statement. Returns carried_from_id -> new id.

    carried_from_id is unique among the rows (the partial unique index guarantees
    it in the table too), so the mapping back to the source task is unambiguous.
    """
    if not rows:
        return {}
    pairs = db.execute(
        insert(Task.__table__).returning(
            Task.__table__.c.id, Task.__table__.c.carried_from_id
        ),
        rows,
    ).all()
    return {carried_from_id: new_id for new_id, carried_from_id in pairs}


def _insert_tag_links(db: Session, links: list[dict]) -> None:
    if links:
        db.execute(insert(TaskTag.__table__), links)


def _mark_missed(db: Session, task_ids: list[int]) -> None:
    for start in range(0, len(task_ids), _SLICE):
        db.execute(
            update(Task.__table__)
            .where(Task.__table__.c.id.in_(task_ids[start : start + _SLICE]))
            .values(status="missed")
        )


def _is_carried_from_conflict(db: Session, error: IntegrityError) -> bool:
    original = error.orig
    return (
        db.get_bind().dialect.name == "sqlite"
        and isinstance(original, sqlite3.IntegrityError)
        and getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
        and "tasks.carried_from_id" in str(original)
    )