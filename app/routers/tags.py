from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List

from app.db import get_db
from app.models import Tag
from app.schemas import TagCreate, TagOut

router = APIRouter(prefix="/tags", tags=["tags"])

@router.get("/", response_model=List[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return db.execute(select(Tag)).scalars().all()

@router.post("/", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(tag_in: TagCreate, db: Session = Depends(get_db)):
    # Check for duplicates
    existing_tag = db.execute(
        select(Tag).where(Tag.name == tag_in.name)
    ).scalar_one_or_none()
    
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="Tag with this name already exists"
        )

    db_tag = Tag(**tag_in.model_dump())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag
