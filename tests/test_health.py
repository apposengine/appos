"""Unit tests for appos.engine.health — HealthCheckService."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from appos.engine.health import (
    HealthCheckConfig,
    HealthCheckResult,
    HealthCheckService,
    HealthStatus,
    get_health_service,
)


class TestHealthStatus:
    def test_values(self):
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"
        assert HealthStatus.UNKNOWN == "unknown"


class TestHealthCheckConfig:
    def test_defaults(self):
        config = HealthCheckConfig()
        assert config.enabled is True
        assert config.interval_seconds > 0
        assert config.timeout > 0

    def test_from_dict(self):
        data = {"enabled": False, "interval_seconds": 120, "timeout": 10}
        config = HealthCheckConfig.from_dict(data)
        assert config.enabled is False
        assert config.interval_seconds == 120


class TestHealthCheckResult:
    def test_to_dict(self):
        result = HealthCheckResult(
            name="db",
            status=HealthStatus.HEALTHY,
            latency_ms=5.2,
            message="OK",
        )
        d = result.to_dict()
        assert d["name"] == "db"
        assert d["status"] == "healthy"
        assert d["latency_ms"] == 5.2
        assert d["message"] == "OK"


class TestHealthCheckService:
    def setup_method(self):
        self.svc = HealthCheckService()

    def test_register_check(self):
        async def my_check():
            return True
        self.svc.register_check("test", my_check)
        assert "test" in self.svc.registered_checks

    def test_registered_checks_empty(self):
        assert len(self.svc.registered_checks) == 0

    def test_get_last_result_none(self):
        assert self.svc.get_last_result("nonexistent") is None

    def test_get_all_results_empty(self):
        assert self.svc.get_all_results() == {}

    def test_is_healthy_unknown(self):
        assert self.svc.is_healthy("missing") is False

    @pytest.mark.asyncio
    async def test_check_executes(self):
        """Test that check() executes the check function."""
        async def my_check():
            return True

        self.svc.register_check("test", my_check)
        result = await self.svc.check("test")
        assert isinstance(result, HealthCheckResult)
        assert result.name == "test"
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_failure(self):
        """Test that a failing check returns UNHEALTHY."""
        async def bad_check():
            raise Exception("connection refused")

        self.svc.register_check("bad", bad_check)
        result = await self.svc.check("bad")
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_all(self):
        async def ok_check():
            return True

        self.svc.register_check("a", ok_check)
        self.svc.register_check("b", ok_check)
        results = await self.svc.check_all()
        assert len(results) == 2

    def test_get_platform_health(self):
        """Platform health aggregation without running checks."""
        result = self.svc.get_platform_health()
        assert "status" in result
        assert "checks" in result

    def test_singleton(self):
        svc1 = get_health_service()
        svc2 = get_health_service()
        assert svc1 is svc2
