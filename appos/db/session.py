"""
AppOS Database Session Management.

Provides the single entry point for platform DB initialisation plus
context managers for DB access.  Uses the global EngineRegistry for
multi-engine support.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.orm import Session, sessionmaker, scoped_session

from appos.db.base import Base, engine_registry


# Scoped session factory for the platform DB (appos_core).
# Populated by init_platform_db() — used by get_platform_session().
_platform_session_factory: Optional[scoped_session] = None


def init_platform_db(
    db_url: str,
    schema: str = "appOS",
    create_tables: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    pool_pre_ping: bool = True,
) -> sessionmaker:
    """
    Single entry point for platform database initialisation.

    All callers (appos.py runtime boot, ``appos init`` CLI, tests) must go
    through this function — no more duplicate engine-creation blocks.

    What it does
    ────────────
    1. Registers a named engine "appos_core" in EngineRegistry.
    2. Creates the PostgreSQL schema if it does not exist (idempotent).
    3. Registers a ``connect`` event listener so *every* new connection
       automatically runs ``SET search_path TO "<schema>", public``.
       This ensures all un-qualified table references (users, groups …)
       resolve to the correct schema regardless of the DB default.
    4. Optionally calls ``Base.metadata.create_all()`` — for dev / ``appos init``
       only.  Production deployments use the SQL migration scripts instead.
    5. Stores a thread-safe ``scoped_session`` factory as the module-level
       singleton (used by ``get_platform_session()``).

    Args:
        db_url:        PostgreSQL connection URL (postgresql://user:pass@host/db).
        schema:        Target schema name.  Defaults to "appOS" (matches the
                       ``database.db_schema`` field in appos.yaml).
        create_tables: When True, run Base.metadata.create_all() after schema
                       creation.  Use ONLY for ``appos init`` bootstrapping.
                       Production: leave False and rely on migration scripts.
        pool_size:     SQLAlchemy engine pool_size.
        max_overflow:  SQLAlchemy engine max_overflow.
        pool_timeout:  SQLAlchemy engine pool_timeout (seconds).
        pool_recycle:  SQLAlchemy engine pool_recycle (seconds).
        pool_pre_ping: SQLAlchemy engine pool_pre_ping.

    Returns:
        A plain ``sessionmaker`` bound to the initialised engine.
        Callers that manage their own session lifecycle (e.g. runtime.py)
        should use this return value.  Callers that want a thread-safe
        scoped session should use ``get_platform_session()`` instead.
    """
    global _platform_session_factory

    import sqlalchemy
    from sqlalchemy import text as sa_text

    # 1. Register engine in the global EngineRegistry
    engine_registry.register(
        "appos_core", db_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
    )
    engine = engine_registry.get("appos_core")

    # 2. Ensure schema exists (idempotent — safe to call at runtime too)
    with engine.connect() as conn:
        conn.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()

    # 3. Register search_path on every new connection
    @sqlalchemy.event.listens_for(engine, "connect")
    def set_search_path(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.close()

    # 4. Optionally create tables (dev/init path only)
    if create_tables:
        Base.metadata.create_all(engine)

    # 5. Build session factories
    factory = sessionmaker(bind=engine)
    _platform_session_factory = scoped_session(factory)

    return factory


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
