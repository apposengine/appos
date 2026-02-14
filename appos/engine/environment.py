"""
AppOS Environment Overrides Resolver — Resolves env-specific config for
Connected Systems, Constants, and other environment-aware objects.

Used by:
    - ConnectedSystemResolver._apply_environment()
    - @constant env-specific resolution
    - App-level environment awareness

Design refs: AppOS_Design.md §5.5 (Connected System env overrides), §16 (Configuration)
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional

from appos.engine.config import get_environment, get_platform_config

logger = logging.getLogger("appos.engine.environment")


class EnvironmentResolver:
    """
    Resolves environment-specific overrides for configuration dictionaries.

    Override precedence (highest → lowest):
        1. Environment-specific override (e.g., "prod")
        2. "default" key
        3. Raw values (no environment nesting)

    Usage:
        resolver = EnvironmentResolver()
        config = resolver.resolve(connected_system_config)
        # In 'prod' env: returns merged default + prod overrides
    """

    def __init__(self, environment: Optional[str] = None):
        """
        Args:
            environment: Override environment name. If None, reads from platform config.
        """
        self._environment = environment

    @property
    def environment(self) -> str:
        """Current resolved environment."""
        if self._environment:
            return self._environment
        try:
            return get_environment()
        except Exception:
            return "dev"

    def resolve(
        self,
        config: Dict[str, Any],
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a config dict, applying environment-specific overrides.

        If config has environment_overrides or top-level env keys like
        {"default": {...}, "prod": {...}}, merges the current/specified
        environment on top of the default.

        Args:
            config: Raw configuration dict from @connected_system or similar.
            environment: Explicit environment. If None, uses self.environment.

        Returns:
            Merged configuration dict with environment overrides applied.
        """
        env = environment or self.environment

        # Case 1: config has "default" + environment_overrides structure
        # (Connected System pattern from §5.5)
        if "default" in config and isinstance(config["default"], dict):
            result = copy.deepcopy(config["default"])

            # Apply environment_overrides if present
            env_overrides = config.get("environment_overrides", {})
            if env in env_overrides and isinstance(env_overrides[env], dict):
                result = self._deep_merge(result, env_overrides[env])
                logger.debug(f"Applied env override '{env}' to config")

            # Carry forward non-connection keys (auth, health_check, etc.)
            for key in config:
                if key not in ("default", "environment_overrides") and key not in result:
                    result[key] = copy.deepcopy(config[key])

            return result

        # Case 2: config has top-level environment keys (Constant pattern)
        # {"dev": "value1", "prod": "value2", "default": "fallback"}
        if env in config:
            return config[env] if not isinstance(config[env], dict) else copy.deepcopy(config[env])

        # Case 3: No environment structure — return as-is
        return copy.deepcopy(config)

    def resolve_value(
        self,
        values: Dict[str, Any],
        environment: Optional[str] = None,
    ) -> Any:
        """
        Resolve a simple value map like {"default": 100, "prod": 500}.

        Used for Constants with environment-specific values.

        Args:
            values: Dict with environment keys mapping to values.
            environment: Explicit environment override.

        Returns:
            The resolved value for the current environment.
        """
        env = environment or self.environment

        if isinstance(values, dict):
            if env in values:
                return values[env]
            if "default" in values:
                return values["default"]

        # Not a dict or no env keys — return as-is
        return values

    def resolve_connected_system(
        self,
        config: Dict[str, Any],
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full Connected System config resolution with all sections.

        Resolves:
            - Connection details (default + env overrides)
            - Auth config (preserved)
            - Health check config (preserved)
            - Pool config (extracted from connection details)

        Args:
            config: Raw Connected System config from handler().
            environment: Explicit environment override.

        Returns:
            Fully resolved dict with connection_details, auth, health_check, pool_config.
        """
        env = environment or self.environment
        result: Dict[str, Any] = {}

        # Resolve connection details
        connection_details = self.resolve(config, env)

        # Extract pool config from connection details
        pool_keys = {
            "pool_size", "max_overflow", "pool_timeout",
            "pool_recycle", "pool_pre_ping", "pool_reset_on_return",
        }
        pool_config = {}
        clean_details = {}

        for k, v in connection_details.items():
            if k in pool_keys:
                pool_config[k] = v
            else:
                clean_details[k] = v

        result["connection_details"] = clean_details
        result["pool_config"] = pool_config

        # Preserve auth section
        if "auth" in config:
            result["auth"] = copy.deepcopy(config["auth"])

        # Preserve health_check section
        if "health_check" in config:
            result["health_check"] = copy.deepcopy(config["health_check"])

        return result

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-merge override dict into base dict. Override values win.

        Only merges nested dicts — lists and scalars are replaced entirely.
        """
        result = copy.deepcopy(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = EnvironmentResolver._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_resolver: Optional[EnvironmentResolver] = None


def get_environment_resolver(environment: Optional[str] = None) -> EnvironmentResolver:
    """Get or create the global EnvironmentResolver singleton."""
    global _resolver
    if _resolver is None or environment is not None:
        _resolver = EnvironmentResolver(environment=environment)
    return _resolver


def resolve_env_config(config: Dict[str, Any], environment: Optional[str] = None) -> Dict[str, Any]:
    """Convenience: resolve a config dict for the current environment."""
    return get_environment_resolver().resolve(config, environment)


def resolve_env_value(values: Dict[str, Any], environment: Optional[str] = None) -> Any:
    """Convenience: resolve a simple value map for the current environment."""
    return get_environment_resolver().resolve_value(values, environment)
