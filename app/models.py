from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date

Base = declarative_base()


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    notes = Column(Text)
    points = Column(Integer, default=10)
    priority = Column(Integer, default=0)  # 0-3
    planned_date = Column(Date)
    original_date = Column(Date)
    status = Column(String, default="pending")  # "pending"|"done"|"deleted"
    completed_at = Column(DateTime, nullable=True)
    completed_date = Column(Date, nullable=True)
    carry_count = Column(Integer, default=0)
    miss_reason = Column(String, nullable=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    recurrence_rule = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)


class Day(Base):
    __tablename__ = "days"

    date = Column(Date, primary_key=True)
    started_at = Column(DateTime, nullable=True)
    locked = Column(Boolean, default=False)
    reflection = Column(Text, nullable=True)
    mood = Column(Integer, nullable=True)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String)


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)