from dataclasses import dataclass
from datetime import date
from collections.abc import Sequence

from app.models import Task
from app.task_queries import is_active_task


@dataclass(frozen=True)
class DayTaskScore:
    tasks_total: int
    tasks_done: int
    total_points: int
    earned_points: int
    completion_pct: float
    score: int
    is_complete: bool
    is_empty: bool


def score_day_tasks(target_date: date, roots: Sequence[Task]) -> DayTaskScore:
    roots = [task for task in roots if is_active_task(task)]
    done = [
        task for task in roots
        if task.status == "done" and task.completed_date == target_date
    ]
    tasks_total = len(roots)
    tasks_done = len(done)
    total_points = sum(task.points or 0 for task in roots)
    earned_points = sum(task.points or 0 for task in done)
    is_complete = bool(roots) and tasks_done == tasks_total

    return DayTaskScore(
        tasks_total=tasks_total,
        tasks_done=tasks_done,
        total_points=total_points,
        earned_points=earned_points,
        completion_pct=(tasks_done / tasks_total * 100) if tasks_total else 0.0,
        score=total_points if is_complete else 0,
        is_complete=is_complete,
        is_empty=not roots,
    )
