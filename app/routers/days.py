from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select
from datetime import date

from app.db import get_db
from app.models import Day, Task, utcnow
from app.schemas import DayOut, DayScore, DayUpdate
from app.scoring import score_day_tasks
from app.task_queries import active_tasks, active_task_conditions

router = APIRouter(prefix="/days", tags=["days"])


def parse_date(date_str: str) -> date:
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD."
        )


def get_or_create_day(db: Session, target_date: date) -> Day:
    day = db.get(Day, target_date)
    if not day:
        day = Day(date=target_date)
        db.add(day)
        db.commit()
        db.refresh(day)
    return day


def day_tasks(db: Session, target_date: date) -> list:
    """Tasks planned for the date, ordered by sort_order then id.
    Soft-deleted tasks (and their subtasks) are excluded from the daily view."""
    return list(
        db.execute(
            active_tasks(Task.planned_date == target_date)
            .options(selectinload(Task.subtasks))
            .order_by(Task.sort_order, Task.id)
        ).scalars().all()
    )


def day_response(db: Session, day: Day) -> DayOut:
    # Tasks are returned flat (group them by parent_task_id on the client);
    # each task also carries its own nested "subtasks" tree.
    return DayOut(
        date=day.date,
        started_at=day.started_at,
        locked=bool(day.locked),
        reflection=day.reflection,
        mood=day.mood,
        tasks=day_tasks(db, day.date),
    )


@router.get("/{date_str}", response_model=DayOut)
def get_day(date_str: str, db: Session = Depends(get_db)):
    """Retrieve a day by date, creating it if this is the first time it is visited."""
    target_date = parse_date(date_str)
    return day_response(db, get_or_create_day(db, target_date))


@router.post("/{date_str}/start", response_model=DayOut)
def start_day(date_str: str, db: Session = Depends(get_db)):
    """Mark the day as started. Idempotent: the first start time is kept."""
    target_date = parse_date(date_str)
    day = get_or_create_day(db, target_date)

    if not day.started_at:
        day.started_at = utcnow()
        db.commit()
        db.refresh(day)

    return day_response(db, day)


@router.patch("/{date_str}", response_model=DayOut)
def update_day(date_str: str, day_in: DayUpdate, db: Session = Depends(get_db)):
    """Save the day's reflection and mood, or lock/unlock it.

    Locking freezes the day's tasks (they can no longer be completed, edited or
    deleted) but the reflection itself stays writable.
    """
    target_date = parse_date(date_str)
    day = get_or_create_day(db, target_date)

    for field, value in day_in.model_dump(exclude_unset=True).items():
        setattr(day, field, value)

    db.commit()
    db.refresh(day)
    return day_response(db, day)


@router.get("/{date_str}/score", response_model=DayScore)
def get_day_score(date_str: str, db: Session = Depends(get_db)):
    """All-or-nothing daily score.

    A task only counts as done for the day it was planned on *and* completed on,
    so a task finished late is a miss for the day it belonged to. Scoring does
    not create a Day row.
    """
    target_date = parse_date(date_str)

    roots = db.execute(
        active_tasks(
            Task.planned_date == target_date,
            Task.parent_task_id.is_(None),
        )
    ).scalars().all()

    subtasks_total, subtasks_done = db.execute(
        select(
            func.count(Task.id),
            func.count(Task.id).filter(Task.completed_date == target_date),
        ).where(
            *active_task_conditions(
                Task.planned_date == target_date,
                Task.parent_task_id.isnot(None),
            )
        )
    ).one()

    score = score_day_tasks(target_date, roots)

    return DayScore(
        date=target_date,
        is_empty=score.is_empty,
        is_complete=score.is_complete,
        tasks_total=score.tasks_total,
        tasks_done=score.tasks_done,
        subtasks_total=subtasks_total,
        subtasks_done=subtasks_done,
        total_points=score.total_points,
        earned_points=score.earned_points,
        score=score.score,
    )