import os
from dataclasses import dataclass
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "yomi.db"
DEFAULT_TIMEZONE = "Africa/Cairo"
DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    database_url: str
    timezone: str
    cors_origins: tuple[str, ...]


def get_settings() -> Settings:
    cors_origins = os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return Settings(
        database_url=os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH.as_posix()}",
        timezone=os.environ.get("TIMEZONE", DEFAULT_TIMEZONE),
        cors_origins=tuple(cors_origins.split(",")),
    )
