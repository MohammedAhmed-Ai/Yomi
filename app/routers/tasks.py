from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload
from datetime import date
from typing import List, Optional

from app.db import get_db
from app.models import Day, Task, utcnow
from app.schemas import TaskCreate, TaskUpdate, TaskOut
from app.task_queries import active_tasks, get_active_task, load_source_miss_reasons
from app.time_utils import local_date

router = APIRouter(prefix="/tasks", tags=["tasks"])


def assert_day_unlocked(db: Session, task: Task) -> None:
    """A locked day is frozen: its tasks can no longer be changed."""
    if not task.planned_date:
        return
    day = db.get(Day, task.planned_date)
    if day and day.locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Day {task.planned_date.isoformat()} is locked",
        )


def get_task_or_404(db: Session, task_id: int) -> Task:
    """Fetch a live task. Soft-deleted tasks are treated as gone."""
    task = get_active_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def get_writable_task(db: Session, task_id: int) -> Task:
    """Fetch a task that may be modified.

    A missed task is a historical record of what was not done: it stays on its own
    day and is read-only, so the work continues on the copy carried over instead.
    """
    task = get_task_or_404(db, task_id)
    if task.status == "missed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task {task_id} was missed and is read-only. "
                "Work on the copy that was carried over instead."
            ),
        )
    return task


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    # Subtask constraints: Limited to 1 level deep
    if task_in.parent_task_id:
        parent = get_active_task(db, task_in.parent_task_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent task not found")
        if parent.parent_task_id:
            raise HTTPException(
                status_code=400,
                detail="Subtasks are limited to 1 level deep"
            )

        # Inherit planned_date from parent if not provided
        if not task_in.planned_date:
            task_in.planned_date = parent.planned_date

    if task_in.planned_date:
        day = db.get(Day, task_in.planned_date)
        if day and day.locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Day {task_in.planned_date.isoformat()} is locked",
            )

    task_data = task_in.model_dump()
    # Lifecycle fields are server-owned
    task_data["status"] = "pending"
    # Specification: original_date = planned_date on creation
    task_data["original_date"] = task_data.get("planned_date")

    db_task = Task(**task_data)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = get_writable_task(db, task_id)
    assert_day_unlocked(db, db_task)

    # Completing an already-done task is a no-op: keep the original completion stamps
    if db_task.status != "done":
        now = utcnow()
        db_task.status = "done"
        db_task.completed_at = now
        db_task.completed_date = local_date(now)
        db.commit()
        db.refresh(db_task)

    return db_task


@router.post("/{task_id}/uncomplete", response_model=TaskOut)
def uncomplete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = get_writable_task(db, task_id)
    assert_day_unlocked(db, db_task)

    if db_task.status == "done":
        db_task.status = "pending"
        db_task.completed_at = None
        db_task.completed_date = None
        db.commit()
        db.refresh(db_task)

    return db_task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    db_task = get_task_or_404(db, task_id)

    if db_task.status == "missed" and set(payload) != {"miss_reason"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task {task_id} was missed and is read-only. "
                "Only its miss reason can be changed."
            ),
        )

    if db_task.status != "missed":
        assert_day_unlocked(db, db_task)

    try:
        task_in = TaskUpdate.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=payload) from exc

    update_data = task_in.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = get_writable_task(db, task_id)
    assert_day_unlocked(db, db_task)

    # Soft delete: status="deleted" and deleted_at set, cascaded to subtasks
    now = utcnow()
    for task in [db_task, *db_task.subtasks]:
        if not task.is_deleted:
            task.status = "deleted"
            task.deleted_at = now

    db.commit()
    return None


@router.get("/", response_model=List[TaskOut])
def list_tasks(
    planned_date: Optional[date] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = (
        active_tasks()
        .options(selectinload(Task.subtasks))
        .order_by(Task.sort_order, Task.id)
    )
    if planned_date:
        query = query.where(Task.planned_date == planned_date)
    if status:
        query = query.where(Task.status == status)

    result = db.execute(query).scalars().all()
    return load_source_miss_reasons(db, result)