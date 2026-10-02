from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from datetime import date

from app.db import get_db
from app.models import Day, Task
from app.schemas import DayOut

router = APIRouter(prefix="/days", tags=["days"])

@router.get("/{date_str}", response_model=DayOut)
def get_day(date_str: str, db: Session = Depends(get_db)):
    """
    Retrieve a day by date.
    If the day doesn't exist, it is automatically created.
    Returns the day and its associated tasks ordered by sort_order then id.
    """
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD."
        )

    # Get or create the Day
    day = db.get(Day, target_date)
    if not day:
        day = Day(date=target_date)
        db.add(day)
        db.commit()
        db.refresh(day)

    # Fetch tasks for this date, ordered by sort_order then id.
    # Soft-deleted tasks (and their subtasks) are excluded from the daily view.
    tasks = db.execute(
        select(Task)
        .options(selectinload(Task.subtasks))
        .where(Task.planned_date == target_date, Task.status != "deleted")
        .order_by(Task.sort_order, Task.id)
    ).scalars().all()

    # Tasks are returned flat (group them by parent_task_id on the client);
    # each task also carries its own nested "subtasks" tree.
    return DayOut(
        date=day.date,
        started_at=day.started_at,
        locked=bool(day.locked),
        reflection=day.reflection,
        mood=day.mood,
        tasks=list(tasks),
    )