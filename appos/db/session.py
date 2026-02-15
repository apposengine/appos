"""
AppOS Database Session Management.

Provides scoped session creation and context managers for DB access.
Uses the global EngineRegistry for multi-engine support.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session, sessionmaker, scoped_session

from appos.db.base import Base, engine_registry


# Scoped session factory for the platform DB (appos_core)
_platform_session_factory: Optional[scoped_session] = None


def init_platform_db(db_url: str, schema: Optional[str] = None, **kwargs) -> None:
    """
    Initialize the platform database engine and create tables.

    Args:
        db_url: PostgreSQL connection URL for appos_core.
        schema: PostgreSQL schema name (e.g. 'appOS'). If set, tables are
                created inside this schema via search_path.
        **kwargs: Additional engine kwargs (pool_size, etc.).
    """
    global _platform_session_factory

    engine_registry.register("appos_core", db_url, **kwargs)
    engine = engine_registry.get("appos_core")

    # Apply schema if specified — use search_path so all table references resolve
    if schema:
        import sqlalchemy
        from sqlalchemy import text as sa_text

        with engine.connect() as conn:
            conn.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            conn.commit()

        @sqlalchemy.event.listens_for(engine, "connect")
        def set_search_path(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute(f'SET search_path TO "{schema}", public')
            cursor.close()

    # Create all platform tables
    Base.metadata.create_all(engine)

    # Set up scoped session factory
    factory = sessionmaker(bind=engine)
    _platform_session_factory = scoped_session(factory)


def get_platform_session() -> Session:
    """
    Get a session for the platform database (appos_core).
    Uses scoped_session for thread-safety.
    """
    if _platform_session_factory is None:
        raise RuntimeError(
            "Platform DB not initialized. Call init_platform_db() first."
        )
    return _platform_session_factory()


@contextmanager
def platform_session_scope() -> Generator[Session, None, None]:
    """
    Context manager for platform DB sessions with auto-commit/rollback.

    Usage:
        with platform_session_scope() as session:
            user = session.query(User).filter_by(username='admin').first()
    """
    session = get_platform_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def app_session_scope(connected_system_name: str) -> Generator[Session, None, None]:
    """
    Context manager for app database sessions (Connected System).

    Args:
        connected_system_name: The name of the Connected System engine.
    """
    session = engine_registry.get_session(connected_system_name)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_all_sessions() -> None:
    """Close all sessions and dispose all engines. Used during shutdown."""
    global _platform_session_factory
    if _platform_session_factory:
        _platform_session_factory.remove()
    engine_registry.dispose_all()
