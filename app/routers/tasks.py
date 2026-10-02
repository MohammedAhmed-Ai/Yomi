from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from datetime import date
import os
from zoneinfo import ZoneInfo
from typing import List, Optional

from app.db import get_db
from app.models import Task, utcnow
from app.schemas import TaskCreate, TaskUpdate, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_or_404(db: Session, task_id: int) -> Task:
    """Fetch a live task. Soft-deleted tasks are treated as gone."""
    task = db.get(Task, task_id)
    if not task or task.is_deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def local_date(now) -> date:
    """Today in the configured timezone (TIMEZONE, default Africa/Cairo)."""
    tz_name = os.getenv("TIMEZONE", "Africa/Cairo")
    try:
        return now.astimezone(ZoneInfo(tz_name)).date()
    except Exception:
        return now.date()


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    # Subtask constraints: Limited to 1 level deep
    if task_in.parent_task_id:
        parent = db.get(Task, task_in.parent_task_id)
        if not parent or parent.is_deleted:
            raise HTTPException(status_code=404, detail="Parent task not found")
        if parent.parent_task_id:
            raise HTTPException(
                status_code=400,
                detail="Subtasks are limited to 1 level deep"
            )

        # Inherit planned_date from parent if not provided
        if not task_in.planned_date:
            task_in.planned_date = parent.planned_date

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
    db_task = get_task_or_404(db, task_id)

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
    db_task = get_task_or_404(db, task_id)

    if db_task.status == "done":
        db_task.status = "pending"
        db_task.completed_at = None
        db_task.completed_date = None
        db.commit()
        db.refresh(db_task)

    return db_task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    db_task = get_task_or_404(db, task_id)

    update_data = task_in.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = get_task_or_404(db, task_id)

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
        select(Task)
        .options(selectinload(Task.subtasks))
        .where(Task.status != "deleted")
        .order_by(Task.sort_order, Task.id)
    )
    if planned_date:
        query = query.where(Task.planned_date == planned_date)
    if status:
        query = query.where(Task.status == status)

    result = db.execute(query).scalars().all()
    return result