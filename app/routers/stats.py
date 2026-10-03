import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.db import get_db
from app.models import Task
from app.schemas import StatsRangeDay, StatsRangeOut, StatsRangeSummary
from app.scoring import score_day_tasks

router = APIRouter(prefix="/stats", tags=["stats"])


def parse_range_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD.",
        )
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD.",
        )


@router.get("/range", response_model=StatsRangeOut)
def get_stats_range(
    start: str = Query(...),
    end: str = Query(...),
    db: Session = Depends(get_db),
):
    start_date = parse_range_date(start)
    end_date = parse_range_date(end)

    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be on or before end date.",
        )

    range_length = (end_date - start_date).days + 1
    if range_length > 366:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 366 days.",
        )

    tasks_by_date: dict[date, list[Task]] = {}
    tasks = db.execute(
        select(Task)
        .options(lazyload(Task.subtasks), lazyload(Task.tags))
        .where(
            Task.planned_date >= start_date,
            Task.planned_date <= end_date,
            Task.status != "deleted",
            Task.parent_task_id.is_(None),
        )
    ).scalars().all()
    for task in tasks:
        tasks_by_date.setdefault(task.planned_date, []).append(task)

    days = []
    for offset in range(range_length):
        target_date = start_date + timedelta(days=offset)
        score = score_day_tasks(target_date, tasks_by_date.get(target_date, []))
        days.append(
            StatsRangeDay(
                date=target_date,
                tasks_total=score.tasks_total,
                tasks_done=score.tasks_done,
                total_points=score.total_points,
                earned_points=score.earned_points,
                completion_pct=score.completion_pct,
                score=score.score,
                is_complete=score.is_complete,
                is_empty=score.is_empty,
            )
        )

    days_with_tasks = [day for day in days if not day.is_empty]
    summary = StatsRangeSummary(
        days_complete=sum(day.is_complete for day in days),
        days_with_tasks=len(days_with_tasks),
        total_score=sum(day.score for day in days),
        avg_completion_pct=(
            sum(day.completion_pct for day in days_with_tasks) / len(days_with_tasks)
            if days_with_tasks
            else 0.0
        ),
    )
    return StatsRangeOut(days=days, summary=summary)
