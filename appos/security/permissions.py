"""
AppOS UI Permissions — Inherited UI security from app.yaml.

Implements the three-tier inherited security model for UI objects:

Tier 1 (App Defaults):
    security.defaults.ui.groups in app.yaml defines default groups for
    @interface, @page, and @translation_set objects.

Tier 2 (Explicit Override):
    permissions=[...] on the decorator overrides the app default.

Tier 3 (Always Explicit):
    Records, Processes, Web APIs, Integrations, Connected Systems
    MUST have explicit permissions — appos check errors if missing.

Resolution order:
    1. Explicit permissions=[...] on the decorator → use those
    2. No explicit → inherit from app.yaml security.defaults.ui.groups
    3. No app.yaml defaults → empty (open)

Design refs:
    §6  Security Model — Three-tier inherited security
    §5.13 Interface — "Security: Interface permissions inherit from security.defaults.ui"
    §5.14 Page — "Security: Page permissions inherit from security.defaults.ui"
    AppOS_Permissions_Reference.md
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("appos.security.permissions")


class UISecurityResolver:
    """
    Resolves effective permissions for UI objects using three-tier inheritance.

    UI objects (interfaces, pages, translation_sets) inherit their security
    from the app's security.defaults.ui configuration unless explicitly overridden.
    """

    def __init__(self):
        # Cache: app_name → {ui_groups: [...], logic_groups: [...]}
        self._app_defaults: Dict[str, Dict[str, List[str]]] = {}

    def load_app_defaults(self, app_name: str, security_config: Optional[Any] = None) -> None:
        """
        Load security defaults for an app from its app.yaml config.

        Args:
            app_name: App short name
            security_config: AppSecurity model from app.yaml (or dict)
        """
        ui_groups: List[str] = []
        logic_groups: List[str] = []

        if security_config is None:
            # Try loading from config module
            try:
                from appos.engine.config import load_app_config
                app_config = load_app_config(app_name)
                if app_config:
                    security_config = app_config.security
            except Exception:
                pass

        if security_config:
            if hasattr(security_config, "defaults"):
                defaults = security_config.defaults
                if hasattr(defaults, "ui") and hasattr(defaults.ui, "groups"):
                    ui_groups = list(defaults.ui.groups)
                if hasattr(defaults, "logic") and hasattr(defaults.logic, "groups"):
                    logic_groups = list(defaults.logic.groups)
            elif isinstance(security_config, dict):
                defaults = security_config.get("defaults", {})
                ui_groups = defaults.get("ui", {}).get("groups", [])
                logic_groups = defaults.get("logic", {}).get("groups", [])

        self._app_defaults[app_name] = {
            "ui_groups": ui_groups,
            "logic_groups": logic_groups,
        }

        logger.debug(
            f"Loaded security defaults for {app_name}: "
            f"ui={ui_groups}, logic={logic_groups}"
        )

    def resolve_ui_permissions(
        self,
        app_name: str,
        explicit_permissions: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Resolve effective permissions for a UI object (interface/page/translation_set).

        Args:
            app_name: App short name
            explicit_permissions: Permissions declared on the decorator (if any)

        Returns:
            Effective permission groups list
        """
        # Explicit override takes priority
        if explicit_permissions:
            return explicit_permissions

        # Inherit from app.yaml defaults
        defaults = self._app_defaults.get(app_name, {})
        return defaults.get("ui_groups", [])

    def resolve_logic_permissions(
        self,
        app_name: str,
        explicit_permissions: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Resolve effective permissions for a logic object (expression_rule/constant).

        Args:
            app_name: App short name
            explicit_permissions: Permissions declared on the decorator (if any)

        Returns:
            Effective permission groups list
        """
        if explicit_permissions:
            return explicit_permissions

        defaults = self._app_defaults.get(app_name, {})
        return defaults.get("logic_groups", [])

    def get_app_defaults(self, app_name: str) -> Dict[str, List[str]]:
        """Get the raw security defaults for an app."""
        return self._app_defaults.get(app_name, {"ui_groups": [], "logic_groups": []})

    def check_ui_access(
        self,
        app_name: str,
        user_groups: Set[str],
        explicit_permissions: Optional[List[str]] = None,
    ) -> bool:
        """
        Check if a user has access to a UI object.

        Args:
            app_name: App short name
            user_groups: Set of group names the user belongs to
            explicit_permissions: Permissions on the decorator

        Returns:
            True if user has access
        """
        effective = self.resolve_ui_permissions(app_name, explicit_permissions)

        # No permissions defined → open access (all groups)
        if not effective:
            return True

        # Wildcard
        if "*" in effective:
            return True

        # Check intersection
        return bool(user_groups & set(effective))

    def validate_explicit_required(
        self,
        object_type: str,
        object_ref: str,
        permissions: Optional[Any],
    ) -> Optional[str]:
        """
        Validate that 'always explicit' objects have permissions defined.

        Returns an error message if validation fails, None if OK.

        Always-explicit types: record, process, web_api, integration, connected_system
        """
        always_explicit = {"record", "process", "web_api", "integration", "connected_system"}

        if object_type not in always_explicit:
            return None

        if not permissions:
            return (
                f"{object_type} '{object_ref}' requires explicit permissions "
                f"(security.defaults do not apply to {object_type} objects). "
                f"Add permissions=[...] to the decorator or Meta.permissions={{...}}"
            )

        return None

    def clear(self) -> None:
        """Clear cached defaults."""
        self._app_defaults.clear()


# Global singleton
ui_security_resolver = UISecurityResolver()
