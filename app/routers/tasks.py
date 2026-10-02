from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from datetime import datetime, date
from typing import List, Optional

from app.db import get_db
from app.models import Task, Tag, TaskTag
from app.schemas import TaskCreate, TaskUpdate, TaskOut, TagCreate, TagOut

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    # Subtask constraints: Limited to 1 level deep
    if task_in.parent_task_id:
        parent = db.get(Task, task_in.parent_task_id)
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

    # Specification: original_date = planned_date on creation
    task_data = task_in.model_dump()
    if task_data.get("planned_date"):
        task_data["original_date"] = task_data["planned_date"]

    db_task = Task(**task_data)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db_task.status = "done"
    db_task.completed_at = datetime.utcnow()
    db_task.completed_date = date.today()
    
    db.commit()
    db.refresh(db_task)
    return db_task

@router.post("/{task_id}/uncomplete", response_model=TaskOut)
def uncomplete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db_task.status = "pending"
    db_task.completed_at = None
    db_task.completed_date = None
    
    db.commit()
    db.refresh(db_task)
    return db_task

@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = task_in.model_dump(exclude_unset=True)
    
    # Special logic for completion
    if update_data.get("status") == "done" and db_task.status != "done":
        update_data["completed_at"] = datetime.utcnow()
        update_data["completed_date"] = date.today()
    elif update_data.get("status") == "pending" and db_task.status == "done":
        update_data["completed_at"] = None
        update_data["completed_date"] = None

    for key, value in update_data.items():
        setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Soft delete: status="deleted" and deleted_at set
    db_task.status = "deleted"
    db_task.deleted_at = datetime.utcnow()
    
    db.commit()
    return None
    
    db.commit()
    return None

@router.get("/", response_model=List[TaskOut])
def list_tasks(
    planned_date: Optional[date] = None, 
    status: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    query = select(Task).where(Task.status != "deleted")
    if planned_date:
        query = query.where(Task.planned_date == planned_date)
    if status:
        query = query.where(Task.status == status)
    
    result = db.execute(query).scalars().all()
    return result
