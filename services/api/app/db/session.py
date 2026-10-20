"""Database engine, session management and the declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import Settings, get_settings

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def build_engine(settings: Settings) -> Any:
    """Create the SQLAlchemy engine from settings."""
    return create_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Any:
    """Process-wide engine (created lazily so imports stay cheap in tests)."""
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
