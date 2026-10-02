from pydantic import BaseModel, Field, ConfigDict
from datetime import date, datetime
from typing import List, Optional

# --- Tags ---

class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("#888888", pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")

class TagCreate(TagBase):
    pass

class TagOut(TagBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- Tasks ---

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None
    points: int = Field(10, ge=0, le=1000)
    priority: int = Field(0, ge=0, le=3)
    planned_date: Optional[date] = None
    original_date: Optional[date] = None
    status: str = "pending"
    parent_task_id: Optional[int] = None
    recurrence_rule: Optional[str] = None
    sort_order: int = 0

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    notes: Optional[str] = None
    points: Optional[int] = Field(None, ge=0, le=1000)
    priority: Optional[int] = Field(None, ge=0, le=3)
    miss_reason: Optional[str] = None
    sort_order: Optional[int] = None

class TaskOut(TaskBase):
    id: int
    completed_at: Optional[datetime] = None
    completed_date: Optional[date] = None
    carry_count: int
    created_at: datetime
    deleted_at: Optional[datetime] = None
    tags: List[TagOut] = []
    
    model_config = ConfigDict(from_attributes=True)

# --- Days ---

class DayBase(BaseModel):
    pass

class DayOut(DayBase):
    date: date
    started_at: Optional[datetime] = None
    tasks: List[TaskOut] = []

    model_config = ConfigDict(from_attributes=True)
