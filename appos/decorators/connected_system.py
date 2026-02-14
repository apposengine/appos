"""
AppOS Connected System — Full connection pool configuration, engine registration,
and environment-aware resolution for @connected_system objects.

Provides:
    - ConnectedSystemManager: Central manager for all Connected System lifecycles
    - Pool configuration: pool_size, max_overflow, pool_timeout, pool_recycle,
      pool_pre_ping, pool_reset_on_return
    - Engine registration into EngineRegistry for database-type systems
    - Environment-aware resolution (dev/staging/prod)

Dependencies:
    - EngineRegistry (appos.db.base)
    - EnvironmentResolver (appos.engine.environment)
    - ConnectedSystem DB model (appos.db.platform_models)
    - IntegrationExecutor reads pool_config from here

Design refs: AppOS_Design.md §5.5 (Connected System), §2 (Architecture)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from appos.db.base import engine_registry
from appos.engine.environment import EnvironmentResolver, get_environment_resolver

logger = logging.getLogger("appos.decorators.connected_system")


# ---------------------------------------------------------------------------
# Pool configuration defaults (matching appos.yaml database section)
# ---------------------------------------------------------------------------

@dataclass
class PoolConfig:
    """SQLAlchemy-compatible connection pool configuration."""
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 1800
    pool_pre_ping: bool = True
    pool_reset_on_return: str = "rollback"  # "rollback" | "commit" | None

    def to_engine_kwargs(self) -> Dict[str, Any]:
        """Convert to SQLAlchemy create_engine kwargs."""
        kwargs: Dict[str, Any] = {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": self.pool_pre_ping,
        }
        if self.pool_reset_on_return:
            kwargs["pool_reset_on_return"] = self.pool_reset_on_return
        return kwargs

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PoolConfig":
        """Build from a dict (e.g., from connected_system config)."""
        pool_keys = {
            "pool_size", "max_overflow", "pool_timeout",
            "pool_recycle", "pool_pre_ping", "pool_reset_on_return",
        }
        filtered = {k: v for k, v in data.items() if k in pool_keys}
        return cls(**filtered)

    @classmethod
    def from_platform_config(cls) -> "PoolConfig":
        """Load defaults from platform_config DB or appos.yaml."""
        try:
            from appos.engine.config import get_platform_config
            cfg = get_platform_config()
            return cls(
                pool_size=cfg.database.pool_size,
                max_overflow=cfg.database.max_overflow,
                pool_timeout=cfg.database.pool_timeout,
                pool_recycle=cfg.database.pool_recycle,
                pool_pre_ping=cfg.database.pool_pre_ping,
            )
        except Exception:
            return cls()


# ---------------------------------------------------------------------------
# Resolved Connected System data structure
# ---------------------------------------------------------------------------

@dataclass
class ResolvedConnectedSystem:
    """Fully resolved Connected System config, ready for use."""
    name: str
    type: str  # "database" | "rest_api" | "ftp" | "smtp" | "imap" | "custom"
    description: str = ""
    is_active: bool = True

    # Resolved connection details (after env overrides)
    connection_details: Dict[str, Any] = field(default_factory=dict)
    pool_config: PoolConfig = field(default_factory=PoolConfig)
    auth: Dict[str, Any] = field(default_factory=dict)
    health_check: Dict[str, Any] = field(default_factory=dict)

    # For rest_api type
    @property
    def base_url(self) -> str:
        return self.connection_details.get("base_url", "")

    @property
    def timeout(self) -> int:
        return self.connection_details.get("timeout", 30)

    # For database type
    @property
    def db_url(self) -> str:
        """Build SQLAlchemy connection URL from connection_details."""
        d = self.connection_details
        driver = d.get("driver", "postgresql")
        host = d.get("host", "localhost")
        port = d.get("port", 5432)
        database = d.get("database", "")
        # Credentials resolved separately via CredentialManager
        return f"{driver}://{host}:{port}/{database}"


# ---------------------------------------------------------------------------
# Connected System Manager
# ---------------------------------------------------------------------------

class ConnectedSystemManager:
    """
    Central manager for Connected System lifecycle:
        1. Register from @connected_system decorator or DB records
        2. Resolve with environment overrides
        3. Register database engines in EngineRegistry
        4. Provide resolved configs to IntegrationExecutor

    Usage:
        manager = ConnectedSystemManager()
        manager.register_from_decorator("crm_database", config_fn)
        resolved = manager.get("crm_database")
    """

    def __init__(
        self,
        env_resolver: Optional[EnvironmentResolver] = None,
        db_session_factory=None,
    ):
        self._env_resolver = env_resolver or get_environment_resolver()
        self._db_session_factory = db_session_factory
        self._systems: Dict[str, ResolvedConnectedSystem] = {}
        self._raw_configs: Dict[str, Dict[str, Any]] = {}

    def register_from_decorator(
        self,
        name: str,
        config_fn: Any,
        cs_type: str = "database",
        description: str = "",
    ) -> ResolvedConnectedSystem:
        """
        Register a Connected System from a @connected_system decorated function.

        Calls the handler to get raw config, resolves environment, extracts pool config,
        and registers the database engine if applicable.

        Args:
            name: Unique system name (e.g., "crm_database").
            config_fn: The decorated function that returns config dict.
            cs_type: System type ("database", "rest_api", etc.).
            description: Human-readable description.

        Returns:
            ResolvedConnectedSystem instance.
        """
        raw_config = config_fn() if callable(config_fn) else config_fn
        self._raw_configs[name] = raw_config

        # Resolve using EnvironmentResolver
        resolved_config = self._env_resolver.resolve_connected_system(raw_config)

        # Build pool config
        pool_data = resolved_config.get("pool_config", {})
        defaults = PoolConfig.from_platform_config()
        pool_config = PoolConfig(
            pool_size=pool_data.get("pool_size", defaults.pool_size),
            max_overflow=pool_data.get("max_overflow", defaults.max_overflow),
            pool_timeout=pool_data.get("pool_timeout", defaults.pool_timeout),
            pool_recycle=pool_data.get("pool_recycle", defaults.pool_recycle),
            pool_pre_ping=pool_data.get("pool_pre_ping", defaults.pool_pre_ping),
            pool_reset_on_return=pool_data.get("pool_reset_on_return", defaults.pool_reset_on_return),
        )

        resolved = ResolvedConnectedSystem(
            name=name,
            type=cs_type,
            description=description,
            connection_details=resolved_config.get("connection_details", {}),
            pool_config=pool_config,
            auth=resolved_config.get("auth", {}),
            health_check=resolved_config.get("health_check", {}),
        )

        self._systems[name] = resolved
        logger.info(f"Registered Connected System: {name} (type={cs_type})")

        return resolved

    def register_from_db(self, db_record: Any) -> ResolvedConnectedSystem:
        """
        Register a Connected System from its DB model row.

        Args:
            db_record: ConnectedSystem SQLAlchemy model instance.

        Returns:
            ResolvedConnectedSystem instance.
        """
        raw_config = {
            "default": db_record.connection_details or {},
            "environment_overrides": db_record.environment_overrides or {},
            "auth": {"type": db_record.auth_type},
            "health_check": db_record.health_check or {},
        }
        self._raw_configs[db_record.name] = raw_config

        resolved_config = self._env_resolver.resolve_connected_system(raw_config)
        pool_data = resolved_config.get("pool_config", {})

        resolved = ResolvedConnectedSystem(
            name=db_record.name,
            type=db_record.type,
            description=db_record.description or "",
            is_active=db_record.is_active,
            connection_details=resolved_config.get("connection_details", {}),
            pool_config=PoolConfig.from_dict(pool_data) if pool_data else PoolConfig.from_platform_config(),
            auth=resolved_config.get("auth", {}),
            health_check=resolved_config.get("health_check", {}),
        )

        self._systems[db_record.name] = resolved
        logger.info(f"Registered Connected System from DB: {db_record.name}")

        return resolved

    def register_engine(self, name: str, username: str = "", password: str = "") -> None:
        """
        Register a database-type Connected System's engine in the EngineRegistry.

        Must call after register_from_decorator / register_from_db.
        Credentials are passed separately (from CredentialManager).
        """
        resolved = self._systems.get(name)
        if not resolved:
            raise KeyError(f"Connected System '{name}' not registered. Call register_from_* first.")

        if resolved.type != "database":
            logger.debug(f"Skipping engine registration for non-database CS: {name}")
            return

        d = resolved.connection_details
        driver = d.get("driver", "postgresql")
        host = d.get("host", "localhost")
        port = d.get("port", 5432)
        database = d.get("database", "")

        # Build URL with credentials
        if username and password:
            url = f"{driver}://{username}:{password}@{host}:{port}/{database}"
        elif username:
            url = f"{driver}://{username}@{host}:{port}/{database}"
        else:
            url = f"{driver}://{host}:{port}/{database}"

        engine_registry.register(
            name=name,
            url=url,
            **resolved.pool_config.to_engine_kwargs(),
        )
        logger.info(f"Registered SQLAlchemy engine: {name}")

    def get(self, name: str) -> ResolvedConnectedSystem:
        """Get a resolved Connected System by name."""
        if name not in self._systems:
            raise KeyError(
                f"Connected System '{name}' not found. "
                f"Available: {list(self._systems.keys())}"
            )
        return self._systems[name]

    def get_all(self) -> Dict[str, ResolvedConnectedSystem]:
        """Get all registered Connected Systems."""
        return dict(self._systems)

    def load_all_from_db(self) -> int:
        """
        Load all active Connected Systems from the database.

        Returns:
            Number of systems loaded.
        """
        if not self._db_session_factory:
            logger.warning("No DB session factory — cannot load Connected Systems from DB")
            return 0

        from appos.db.platform_models import ConnectedSystem as CSModel

        count = 0
        try:
            session = self._db_session_factory()
            try:
                records = session.query(CSModel).filter(CSModel.is_active == True).all()
                for record in records:
                    self.register_from_db(record)
                    count += 1
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to load Connected Systems from DB: {e}")

        logger.info(f"Loaded {count} Connected Systems from database")
        return count

    def refresh(self, name: str) -> ResolvedConnectedSystem:
        """Re-resolve a Connected System (e.g., after environment change)."""
        if name in self._raw_configs:
            raw = self._raw_configs[name]
            resolved_config = self._env_resolver.resolve_connected_system(raw)
            existing = self._systems.get(name)
            if existing:
                existing.connection_details = resolved_config.get("connection_details", {})
                pool_data = resolved_config.get("pool_config", {})
                if pool_data:
                    existing.pool_config = PoolConfig.from_dict(pool_data)
                return existing
        raise KeyError(f"Cannot refresh '{name}' — no raw config stored")

    @property
    def names(self) -> List[str]:
        """List all registered system names."""
        return list(self._systems.keys())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[ConnectedSystemManager] = None


def get_connected_system_manager(
    db_session_factory=None,
    environment: Optional[str] = None,
) -> ConnectedSystemManager:
    """Get or create the global ConnectedSystemManager singleton."""
    global _manager
    if _manager is None:
        env_resolver = get_environment_resolver(environment)
        _manager = ConnectedSystemManager(
            env_resolver=env_resolver,
            db_session_factory=db_session_factory,
        )
    return _manager
