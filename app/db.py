from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

from app.models import Base

__all__ = ["Base", "engine", "SessionLocal", "get_db", "DATABASE_URL", "DB_PATH"]

# One database for the whole project, addressed absolutely. A relative
# "sqlite:///./yomi.db" would silently follow the working directory, so running
# Alembic from yomi/backend and the server from the repo root would end up with
# two separate files.
DB_PATH = Path(__file__).resolve().parent.parent / "yomi.db"

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()