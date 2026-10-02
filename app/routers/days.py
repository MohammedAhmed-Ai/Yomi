from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import List

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
    day = db.query(Day).filter(Day.date == target_date).first()
    if not day:
        day = Day(date=target_date)
        db.add(day)
        db.commit()
        db.refresh(day)

    # Fetch tasks for this date, ordered by sort_order then id
    # We exclude 'deleted' tasks from the daily view
    tasks = db.query(Task).filter(
        Task.planned_date == target_date,
        Task.status != "deleted"
    ).order_by(Task.sort_order, Task.id).all()

    # Map tasks to the day object for the DayOut schema
    # Note: Day model doesn't have a relationship defined in models.py yet, 
    # but we can attach them to the object for Pydantic's from_attributes.
    day.tasks = tasks
    
    return day
