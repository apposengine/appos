"""
AppOS Health Check — Connection health monitoring for Connected Systems.

Provides:
    - HealthCheckService: Periodic health checks for database + REST API systems
    - Health status tracking and reporting
    - CircuitBreaker integration for auto-recovery
    - Platform health endpoint data (/health, /ready)

Used by:
    - CircuitBreaker in integration_executor.py uses health check to auto-recover
    - Admin Console → Connected Systems page shows health status
    - Platform /health and /ready endpoints

Design refs: AppOS_Design.md §5.5 (health_check config), AppOS_Monitoring_Reference.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("appos.engine.health")


class HealthStatus(str, Enum):
    """Health status of a Connected System or subsystem."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "message": self.message,
            "checked_at": self.checked_at.isoformat(),
            "details": self.details,
        }


@dataclass
class HealthCheckConfig:
    """Configuration for a health check."""
    enabled: bool = True
    interval_seconds: int = 60
    timeout: int = 10
    endpoint: str = "/health"  # For REST API health checks
    unhealthy_threshold: int = 3  # Consecutive failures before marking unhealthy
    healthy_threshold: int = 1  # Consecutive successes before marking healthy

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthCheckConfig":
        if not data:
            return cls(enabled=False)
        return cls(
            enabled=data.get("enabled", True),
            interval_seconds=data.get("interval_seconds", 60),
            timeout=data.get("timeout", 10),
            endpoint=data.get("endpoint", "/health"),
            unhealthy_threshold=data.get("unhealthy_threshold", 3),
            healthy_threshold=data.get("healthy_threshold", 1),
        )


class HealthCheckService:
    """
    Central health monitoring service for all Connected Systems and platform subsystems.

    Tracks:
        - Connected System connectivity (database ping, REST API health endpoint)
        - Redis connectivity
        - Celery worker availability
        - Overall platform health

    Usage:
        service = HealthCheckService()
        service.register_check("crm_database", check_fn, config)
        result = await service.check("crm_database")
        summary = await service.check_all()
    """

    def __init__(self):
        self._checks: Dict[str, _RegisteredCheck] = {}
        self._results: Dict[str, HealthCheckResult] = {}
        self._background_task: Optional[asyncio.Task] = None

    def register_check(
        self,
        name: str,
        check_fn: Callable,
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        """
        Register a health check function.

        Args:
            name: Unique check name (typically Connected System name).
            check_fn: Async or sync callable that returns True (healthy) or False.
                Signature: check_fn() -> bool
            config: Health check configuration.
        """
        self._checks[name] = _RegisteredCheck(
            name=name,
            check_fn=check_fn,
            config=config or HealthCheckConfig(),
            consecutive_failures=0,
            consecutive_successes=0,
        )
        self._results[name] = HealthCheckResult(
            name=name,
            status=HealthStatus.UNKNOWN,
        )
        logger.debug(f"Registered health check: {name}")

    def register_database_check(
        self,
        name: str,
        engine_name: str,
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        """
        Register a health check for a database Connected System.

        Uses SQLAlchemy engine.connect() → SELECT 1 to verify connectivity.
        """
        from appos.db.base import engine_registry

        def db_check() -> bool:
            try:
                engine = engine_registry.get(engine_name)
                with engine.connect() as conn:
                    from sqlalchemy import text
                    conn.execute(text("SELECT 1"))
                return True
            except Exception as e:
                logger.debug(f"DB health check failed for {engine_name}: {e}")
                return False

        self.register_check(name, db_check, config)

    def register_http_check(
        self,
        name: str,
        base_url: str,
        endpoint: str = "/health",
        timeout: int = 10,
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        """
        Register a health check for a REST API Connected System.

        Makes HTTP GET to base_url + endpoint, expects 2xx response.
        """
        async def http_check() -> bool:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=timeout) as client:
                    url = f"{base_url.rstrip('/')}{endpoint}"
                    resp = await client.get(url)
                    return 200 <= resp.status_code < 300
            except Exception as e:
                logger.debug(f"HTTP health check failed for {name}: {e}")
                return False

        self.register_check(name, http_check, config)

    def register_redis_check(
        self,
        name: str = "redis",
        redis_url: str = "redis://localhost:6379",
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        """Register a health check for Redis connectivity."""
        def redis_check() -> bool:
            try:
                import redis
                client = redis.from_url(redis_url, socket_timeout=5)
                return client.ping()
            except Exception as e:
                logger.debug(f"Redis health check failed: {e}")
                return False

        self.register_check(name, redis_check, config)

    async def check(self, name: str) -> HealthCheckResult:
        """
        Run a single health check by name.

        Updates internal state (consecutive failures/successes) and
        returns the result.
        """
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"No health check registered for '{name}'",
            )

        registered = self._checks[name]
        if not registered.config.enabled:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="Health check disabled",
            )

        start = time.monotonic()

        try:
            # Support both sync and async check functions
            check_fn = registered.check_fn
            if asyncio.iscoroutinefunction(check_fn):
                healthy = await asyncio.wait_for(
                    check_fn(),
                    timeout=registered.config.timeout,
                )
            else:
                healthy = check_fn()

            latency_ms = (time.monotonic() - start) * 1000

            if healthy:
                registered.consecutive_successes += 1
                registered.consecutive_failures = 0

                if registered.consecutive_successes >= registered.config.healthy_threshold:
                    status = HealthStatus.HEALTHY
                else:
                    status = HealthStatus.DEGRADED

                result = HealthCheckResult(
                    name=name,
                    status=status,
                    latency_ms=latency_ms,
                    message="OK",
                )
            else:
                registered.consecutive_failures += 1
                registered.consecutive_successes = 0

                if registered.consecutive_failures >= registered.config.unhealthy_threshold:
                    status = HealthStatus.UNHEALTHY
                else:
                    status = HealthStatus.DEGRADED

                result = HealthCheckResult(
                    name=name,
                    status=status,
                    latency_ms=latency_ms,
                    message=f"Check returned unhealthy (failures: {registered.consecutive_failures})",
                )

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - start) * 1000
            registered.consecutive_failures += 1
            registered.consecutive_successes = 0
            result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Timeout after {registered.config.timeout}s",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            registered.consecutive_failures += 1
            registered.consecutive_successes = 0
            result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=str(e),
            )

        self._results[name] = result
        return result

    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks concurrently."""
        tasks = [self.check(name) for name in self._checks]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return dict(self._results)

    def get_last_result(self, name: str) -> Optional[HealthCheckResult]:
        """Get the most recent health check result for a system."""
        return self._results.get(name)

    def get_all_results(self) -> Dict[str, HealthCheckResult]:
        """Get all last-known health check results."""
        return dict(self._results)

    def is_healthy(self, name: str) -> bool:
        """Quick check: is a system currently healthy?"""
        result = self._results.get(name)
        if result is None:
            return True  # Unknown = assume healthy (optimistic)
        return result.status == HealthStatus.HEALTHY

    def get_platform_health(self) -> Dict[str, Any]:
        """
        Get overall platform health summary (for /health endpoint).

        Returns:
            Dict with overall status + individual system statuses.
        """
        results = self.get_all_results()

        if not results:
            return {
                "status": "healthy",
                "checks": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        statuses = [r.status for r in results.values()]

        if all(s == HealthStatus.HEALTHY for s in statuses):
            overall = "healthy"
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = "unhealthy"
        else:
            overall = "degraded"

        return {
            "status": overall,
            "checks": {name: r.to_dict() for name, r in results.items()},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def start_background_monitoring(self, default_interval: int = 60) -> None:
        """Start periodic background health checks."""
        if self._background_task is not None:
            logger.warning("Background health monitoring already running")
            return

        async def _monitor():
            while True:
                try:
                    await self.check_all()
                except Exception as e:
                    logger.error(f"Health check monitoring error: {e}")
                await asyncio.sleep(default_interval)

        self._background_task = asyncio.create_task(_monitor())
        logger.info(f"Started background health monitoring (interval={default_interval}s)")

    async def stop_background_monitoring(self) -> None:
        """Stop periodic background health checks."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
            logger.info("Stopped background health monitoring")

    @property
    def registered_checks(self) -> List[str]:
        """List all registered check names."""
        return list(self._checks.keys())


@dataclass
class _RegisteredCheck:
    """Internal: tracked state for a registered health check."""
    name: str
    check_fn: Callable
    config: HealthCheckConfig
    consecutive_failures: int = 0
    consecutive_successes: int = 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_health_service: Optional[HealthCheckService] = None


def get_health_service() -> HealthCheckService:
    """Get or create the global HealthCheckService singleton."""
    global _health_service
    if _health_service is None:
        _health_service = HealthCheckService()
    return _health_service
