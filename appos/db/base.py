"""
AppOS Database Base — SQLAlchemy declarative base, mixins, and engine registry.

Provides:
- Base: SQLAlchemy declarative base for all platform models
- AuditMixin: created_at, updated_at, created_by, updated_by
- SoftDeleteMixin: is_deleted, deleted_at, deleted_by
- EngineRegistry: Multi-engine registry for Connected Systems
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, Integer, Boolean, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all AppOS models."""
    pass


class AuditMixin:
    """Adds created_at, updated_at, created_by, updated_by columns."""
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)


class SoftDeleteMixin:
    """Adds is_deleted, deleted_at, deleted_by columns for soft delete support."""
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(Integer, nullable=True)


class EngineRegistry:
    """
    Multi-engine registry for managing SQLAlchemy engines across Connected Systems.

    Each Connected System of type="database" registers its own engine.
    The platform manages engine lifecycle centrally.

    Usage:
        registry = EngineRegistry()
        registry.register("appos_core", "postgresql://...")
        engine = registry.get("appos_core")
        session = registry.get_session("appos_core")
    """

    def __init__(self):
        self._engines: Dict[str, Any] = {}
        self._session_factories: Dict[str, sessionmaker] = {}

    def register(
        self,
        name: str,
        url: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        pool_pre_ping: bool = True,
        **kwargs: Any,
    ) -> None:
        """Register a new database engine."""
        engine = create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            **kwargs,
        )
        self._engines[name] = engine
        self._session_factories[name] = sessionmaker(bind=engine)

    def get(self, name: str) -> Any:
        """Get a registered engine by name."""
        if name not in self._engines:
            raise KeyError(f"Engine '{name}' not registered. Available: {list(self._engines.keys())}")
        return self._engines[name]

    def get_session(self, name: str = "appos_core") -> Session:
        """Get a new session for a registered engine."""
        if name not in self._session_factories:
            raise KeyError(f"Session factory '{name}' not found. Available: {list(self._session_factories.keys())}")
        return self._session_factories[name]()

    def dispose(self, name: Optional[str] = None) -> None:
        """Dispose one or all engines (close connection pools)."""
        if name:
            if name in self._engines:
                self._engines[name].dispose()
        else:
            for engine in self._engines.values():
                engine.dispose()

    def dispose_all(self) -> None:
        """Dispose all engines."""
        self.dispose()

    @property
    def registered_names(self) -> list:
        """List all registered engine names."""
        return list(self._engines.keys())

    def health_check(self, name: str) -> bool:
        """Check if an engine can connect."""
        try:
            from sqlalchemy import text
            engine = self.get(name)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


# Global engine registry singleton
engine_registry = EngineRegistry()
