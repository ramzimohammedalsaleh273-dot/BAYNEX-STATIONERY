"""Database engine and session factory."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from baynex_stationery.config import APP_DIR, DATABASE_URL
from baynex_stationery.db.base import Base

APP_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database() -> None:
    # Import models so SQLAlchemy registers all mapped tables.
    from baynex_stationery.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
