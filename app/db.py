from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from app.models import Base

__all__ = ["Base", "engine", "SessionLocal", "get_db", "DATABASE_URL"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./yomi.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()