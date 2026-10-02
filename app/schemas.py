from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from typing import List, Optional

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
    miss_reason: Optional[str] = None
    sort_order: Optional[int] = None

class TaskOut(TaskBase):
    id: int
    status: str
    completed_at: Optional[datetime] = None
    completed_date: Optional[date] = None
    carry_count: int
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
    mood: Optional[int] = Field(None, ge=1, le=10)
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