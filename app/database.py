"""Konfiguracja SQLAlchemy (SQLite)."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

os.makedirs(settings.data_dir, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables as a simple bootstrap instead of full migrations."""
    from . import models  # noqa: F401  - register models

    Base.metadata.create_all(bind=engine)
    _light_migrations()


def _light_migrations() -> None:
    """Add missing columns to existing SQLite tables."""
    insp = inspect(engine)
    if "listing_images" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("listing_images")}
        if "is_floorplan" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE listing_images ADD COLUMN is_floorplan BOOLEAN DEFAULT 0"
                ))
