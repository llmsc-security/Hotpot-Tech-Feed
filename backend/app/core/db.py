"""SQLAlchemy engine + session factory.

Synchronous SQLAlchemy 2.0. Async would force async-compatible adapters
everywhere; for batch ingest the sync model is fine and easier to reason about.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Sized for parallel ingest: each enrichment worker takes a session.
    pool_size=max(20, settings.ingest_workers + 8),
    max_overflow=64,
    pool_timeout=60,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Commits on a clean handler return; rolls back on
    exception. Without this, write routes that don't call db.commit() would
    silently drop their changes when the session closes.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts / Celery tasks. Commits on success, rolls back on exception."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
