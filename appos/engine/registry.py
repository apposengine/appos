"""
AppOS Object Registry — Register, discover, and retrieve objects by type+app+name.

The registry is the COMPILED STATE layer — rebuilt on startup by scanning app directories.
Stores object metadata in memory (fast lookup) and persists to object_registry DB table.

Object types: record, expression_rule, constant, process, step, integration,
              web_api, interface, page, site, document, folder,
              translation_set, connected_system
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("appos.engine.registry")

# Valid object types
OBJECT_TYPES = frozenset({
    "record", "expression_rule", "constant", "process", "step",
    "integration", "web_api", "interface", "page", "site",
    "document", "folder", "translation_set", "connected_system",
})


@dataclass
class RegisteredObject:
    """Metadata for a registered AppOS object."""

    object_ref: str          # e.g., "crm.rules.calculate_discount"
    object_type: str         # e.g., "expression_rule"
    app_name: Optional[str]  # e.g., "crm" — None for platform/global objects
    name: str                # e.g., "calculate_discount"
    module_path: str         # Python module path
    file_path: str           # Filesystem path
    source_hash: str         # SHA-256 of source file
    metadata: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable] = None  # The actual callable (for rules, etc.)
    is_active: bool = True

    @property
    def category(self) -> str:
        """Map object type to its namespace category."""
        type_to_category = {
            "expression_rule": "rules",
            "constant": "constants",
            "record": "records",
            "process": "processes",
            "step": "steps",
            "integration": "integrations",
            "web_api": "web_apis",
            "interface": "interfaces",
            "page": "pages",
            "site": "sites",
            "document": "documents",
            "folder": "folders",
            "translation_set": "translation_sets",
            "connected_system": "connected_systems",
        }
        return type_to_category.get(self.object_type, self.object_type)


class ObjectRegistryManager:
    """
    In-memory object registry with lookup by ref, type, and app.

    Usage:
        registry = ObjectRegistryManager()
        registry.register(obj)
        rule = registry.resolve("crm.rules.calculate_discount")
        all_rules = registry.get_by_type("expression_rule", app_name="crm")
    """

    def __init__(self):
        # Primary index: object_ref → RegisteredObject
        self._objects: Dict[str, RegisteredObject] = {}

        # Secondary indexes for fast lookup
        self._by_type: Dict[str, Dict[str, RegisteredObject]] = {}  # type → {ref: obj}
        self._by_app: Dict[str, Dict[str, RegisteredObject]] = {}   # app → {ref: obj}
        self._by_type_app: Dict[str, Dict[str, RegisteredObject]] = {}  # "type:app" → {ref: obj}

    def register(self, obj: RegisteredObject) -> None:
        """Register an object in the registry."""
        if obj.object_type not in OBJECT_TYPES:
            raise ValueError(f"Invalid object type: {obj.object_type}. Valid: {OBJECT_TYPES}")

        self._objects[obj.object_ref] = obj

        # Update secondary indexes
        self._by_type.setdefault(obj.object_type, {})[obj.object_ref] = obj

        if obj.app_name:
            self._by_app.setdefault(obj.app_name, {})[obj.object_ref] = obj
            key = f"{obj.object_type}:{obj.app_name}"
            self._by_type_app.setdefault(key, {})[obj.object_ref] = obj

        logger.debug(f"Registered: {obj.object_ref} ({obj.object_type})")

    def unregister(self, object_ref: str) -> None:
        """Remove an object from the registry."""
        obj = self._objects.pop(object_ref, None)
        if obj is None:
            return

        self._by_type.get(obj.object_type, {}).pop(object_ref, None)
        if obj.app_name:
            self._by_app.get(obj.app_name, {}).pop(object_ref, None)
            key = f"{obj.object_type}:{obj.app_name}"
            self._by_type_app.get(key, {}).pop(object_ref, None)

    def resolve(self, object_ref: str) -> Optional[RegisteredObject]:
        """
        Resolve an object reference string to its registered object.

        Args:
            object_ref: Fully-qualified reference (e.g., "crm.rules.calculate_discount")

        Returns:
            RegisteredObject or None if not found.
        """
        return self._objects.get(object_ref)

    def resolve_or_raise(self, object_ref: str) -> RegisteredObject:
        """Resolve or raise AppOSObjectNotFoundError."""
        from appos.engine.errors import AppOSObjectNotFoundError

        obj = self.resolve(object_ref)
        if obj is None:
            raise AppOSObjectNotFoundError(
                f"Object not found: {object_ref}",
                object_ref=object_ref,
            )
        return obj

    def get_by_type(
        self, object_type: str, app_name: Optional[str] = None
    ) -> List[RegisteredObject]:
        """Get all objects of a given type, optionally filtered by app."""
        if app_name:
            key = f"{object_type}:{app_name}"
            return list(self._by_type_app.get(key, {}).values())
        return list(self._by_type.get(object_type, {}).values())

    def get_by_app(self, app_name: str) -> List[RegisteredObject]:
        """Get all objects for a specific app."""
        return list(self._by_app.get(app_name, {}).values())

    def get_all(self) -> List[RegisteredObject]:
        """Get all registered objects."""
        return list(self._objects.values())

    def get_all_refs(self) -> Set[str]:
        """Get all registered object references."""
        return set(self._objects.keys())

    def contains(self, object_ref: str) -> bool:
        """Check if an object reference is registered."""
        return object_ref in self._objects

    @property
    def count(self) -> int:
        """Total number of registered objects."""
        return len(self._objects)

    def clear(self) -> None:
        """Clear all registrations."""
        self._objects.clear()
        self._by_type.clear()
        self._by_app.clear()
        self._by_type_app.clear()

    def scan_app_directory(self, app_name: str, app_path: Path) -> int:
        """
        Scan an app directory and register all discovered objects.

        Args:
            app_name: App short name (e.g., "crm").
            app_path: Path to the app directory (e.g., Path("apps/crm")).

        Returns:
            Number of objects discovered.
        """
        count = 0
        # Map directory names to object types
        dir_to_type = {
            "records": "record",
            "rules": "expression_rule",
            "constants": "constant",
            "processes": "process",
            "steps": "step",
            "integrations": "integration",
            "web_apis": "web_api",
            "interfaces": "interface",
            "pages": "page",
            "translation_sets": "translation_set",
        }

        for dir_name, obj_type in dir_to_type.items():
            type_dir = app_path / dir_name
            if not type_dir.is_dir():
                continue

            for py_file in type_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                obj_name = py_file.stem
                object_ref = f"{app_name}.{dir_name}.{obj_name}"
                module_path = f"apps.{app_name}.{dir_name}.{obj_name}"

                # Compute source hash
                source_hash = hashlib.sha256(py_file.read_bytes()).hexdigest()

                obj = RegisteredObject(
                    object_ref=object_ref,
                    object_type=obj_type,
                    app_name=app_name,
                    name=obj_name,
                    module_path=module_path,
                    file_path=str(py_file),
                    source_hash=source_hash,
                )
                self.register(obj)
                count += 1

        logger.info(f"Scanned app '{app_name}': {count} objects discovered")
        return count

    def to_summary(self) -> Dict[str, int]:
        """Get a summary of registered objects by type."""
        summary = {}
        for obj_type in OBJECT_TYPES:
            count = len(self._by_type.get(obj_type, {}))
            if count > 0:
                summary[obj_type] = count
        return summary


# Global registry singleton
object_registry = ObjectRegistryManager()
