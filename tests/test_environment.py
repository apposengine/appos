"""Unit tests for appos.engine.environment — EnvironmentResolver."""

import pytest
from unittest.mock import patch

from appos.engine.environment import (
    EnvironmentResolver,
    get_environment_resolver,
    resolve_env_config,
    resolve_env_value,
)


class TestEnvironmentResolver:
    """Test environment-specific configuration resolution."""

    def test_default_environment(self):
        resolver = EnvironmentResolver(environment="dev")
        assert resolver.environment == "dev"

    def test_resolve_default_plus_override(self):
        """Case 1: default + environment_overrides structure."""
        resolver = EnvironmentResolver(environment="prod")
        config = {
            "default": {
                "host": "dev-db.local",
                "port": 5432,
                "pool_size": 5,
            },
            "environment_overrides": {
                "prod": {
                    "host": "prod-db.cluster",
                    "pool_size": 20,
                },
            },
        }
        result = resolver.resolve(config)
        assert result["host"] == "prod-db.cluster"
        assert result["port"] == 5432  # inherited from default
        assert result["pool_size"] == 20  # overridden

    def test_resolve_no_override_uses_default(self):
        resolver = EnvironmentResolver(environment="staging")
        config = {
            "default": {"host": "dev-db.local", "port": 5432},
            "environment_overrides": {
                "prod": {"host": "prod-db.cluster"},
            },
        }
        result = resolver.resolve(config)
        assert result["host"] == "dev-db.local"  # staging not in overrides

    def test_resolve_simple_env_keys(self):
        """Case 2: top-level environment keys (Constant pattern)."""
        resolver = EnvironmentResolver(environment="prod")
        config = {"dev": 100, "prod": 500, "default": 200}
        result = resolver.resolve(config)
        assert result == 500

    def test_resolve_no_env_structure(self):
        """Case 3: no environment nesting — returned as-is."""
        resolver = EnvironmentResolver(environment="dev")
        config = {"host": "localhost", "port": 5432}
        result = resolver.resolve(config)
        assert result == {"host": "localhost", "port": 5432}

    def test_resolve_value_map(self):
        resolver = EnvironmentResolver(environment="prod")
        values = {"default": 10, "prod": 100}
        assert resolver.resolve_value(values) == 100

    def test_resolve_value_fallback_default(self):
        resolver = EnvironmentResolver(environment="staging")
        values = {"default": 10, "prod": 100}
        assert resolver.resolve_value(values) == 10

    def test_resolve_value_scalar(self):
        resolver = EnvironmentResolver(environment="dev")
        assert resolver.resolve_value(42) == 42

    def test_resolve_connected_system(self):
        resolver = EnvironmentResolver(environment="prod")
        config = {
            "default": {
                "host": "api.dev.local",
                "port": 443,
                "pool_size": 5,
                "max_overflow": 10,
            },
            "environment_overrides": {
                "prod": {"host": "api.prod.com", "pool_size": 20},
            },
            "auth": {"type": "api_key", "header": "X-Api-Key"},
            "health_check": {"endpoint": "/health"},
        }
        result = resolver.resolve_connected_system(config)
        assert result["connection_details"]["host"] == "api.prod.com"
        assert result["pool_config"]["pool_size"] == 20
        assert result["auth"]["type"] == "api_key"
        assert result["health_check"]["endpoint"] == "/health"

    def test_deep_merge(self):
        base = {"a": 1, "nested": {"x": 10, "y": 20}}
        override = {"a": 2, "nested": {"y": 99}}
        result = EnvironmentResolver._deep_merge(base, override)
        assert result["a"] == 2
        assert result["nested"]["x"] == 10
        assert result["nested"]["y"] == 99


class TestConvenienceFunctions:
    def test_get_environment_resolver(self):
        resolver = get_environment_resolver("prod")
        assert resolver.environment == "prod"

    def test_resolve_env_config(self):
        config = {"default": {"host": "x"}, "environment_overrides": {}}
        result = resolve_env_config(config, environment="dev")
        assert result["host"] == "x"

    def test_resolve_env_value(self):
        values = {"default": 5, "prod": 50}
        assert resolve_env_value(values, environment="prod") == 50
