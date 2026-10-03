from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from typing import List, Literal, Optional

# --- Tags ---

class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("#888888", pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")

class TagCreate(TagBase):
    model_config = ConfigDict(extra="forbid")

class TagOut(TagBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- Tasks ---

class TaskBase(BaseModel):
    """Editable task fields. Lifecycle fields (status/completed_*/deleted_at) are server-owned."""
    title: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None
    points: int = Field(10, ge=0, le=1000)
    priority: int = Field(0, ge=0, le=3)
    planned_date: Optional[date] = None
    original_date: Optional[date] = None
    parent_task_id: Optional[int] = None
    recurrence_rule: Optional[str] = None
    sort_order: int = 0

class TaskCreate(TaskBase):
    model_config = ConfigDict(extra="forbid")

class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    notes: Optional[str] = None
    points: Optional[int] = Field(None, ge=0, le=1000)
    priority: Optional[int] = Field(None, ge=0, le=3)
    miss_reason: Optional[Literal[
        "tired", "no_time", "forgot", "too_big", "emergency", "other"
    ]] = None
    sort_order: Optional[int] = None

class TaskOut(TaskBase):
    id: int
    status: str
    miss_reason: Optional[Literal[
        "tired", "no_time", "forgot", "too_big", "emergency", "other"
    ]] = None
    source_miss_reason: Optional[Literal[
        "tired", "no_time", "forgot", "too_big", "emergency", "other"
    ]] = None
    completed_at: Optional[datetime] = None
    completed_date: Optional[date] = None
    carry_count: int
    carried_from_id: Optional[int] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
    tags: List[TagOut] = []
    subtasks: List["TaskOut"] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("subtasks", mode="before")
    @classmethod
    def hide_deleted_subtasks(cls, value):
        """Soft-deleted children are invisible in the task tree."""
        if isinstance(value, list):
            return [t for t in value if getattr(t, "status", None) != "deleted"]
        return value

TaskOut.model_rebuild()

# --- Carry-over ---

class CarryOverResult(BaseModel):
    """What one carry-over run moved onto today."""
    date: date
    tasks_carried: int
    subtasks_carried: int
    total_carried: int

    model_config = ConfigDict(from_attributes=True)

# --- Days ---

class DayOut(BaseModel):
    date: date
    started_at: Optional[datetime] = None
    locked: bool = False
    reflection: Optional[str] = None
    mood: Optional[int] = None
    tasks: List[TaskOut] = []

    model_config = ConfigDict(from_attributes=True)

class DayUpdate(BaseModel):
    """A day stays editable when locked; the lock only freezes its tasks."""
    model_config = ConfigDict(extra="forbid")

    reflection: Optional[str] = Field(None, max_length=10000)
    mood: Optional[int] = Field(None, ge=1, le=5)
    locked: Optional[bool] = None

class DayScore(BaseModel):
    """
    Daily score. Yomi is all-or-nothing: `score` is the day's full point value
    only when every planned top-level task was completed *on that day*, otherwise 0.

    Subtasks are excluded from the totals because they decompose a parent task
    rather than adding work of their own, but they are reported separately.
    """
    date: date
    is_empty: bool
    is_complete: bool
    tasks_total: int
    tasks_done: int
    subtasks_total: int
    subtasks_done: int
    total_points: int
    earned_points: int
    score: int

    model_config = ConfigDict(from_attributes=True)

class StatsRangeDay(BaseModel):
    date: date
    tasks_total: int
    tasks_done: int
    total_points: int
    earned_points: int
    completion_pct: float
    score: int
    is_complete: bool
    is_empty: bool

class StatsRangeSummary(BaseModel):
    days_complete: int
    days_with_tasks: int
    total_score: int
    avg_completion_pct: float

class StatsRangeOut(BaseModel):
    days: List[StatsRangeDay]
    summary: StatsRangeSummary