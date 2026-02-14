"""
AppOS Constant Manager — Manages constants with environment resolution,
type detection (primitive vs object_ref), and dynamic dispatch support.

When a constant's type is "object_ref", its resolved value is another
object_ref string (e.g., "crm.rules.validate_customer_v2"). Calling
engine.dispatch(constant_ref) will:
  1. Resolve the constant to its env-appropriate value (the target ref)
  2. Dispatch to the target (rule, process, integration, etc.)

This enables runtime-swappable logic without code deployment — just change
the constant's value in the admin console.

Design refs: AppOS_Design.md §5.6 (Constant), §8 (Unified Dispatch)
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from appos.engine.registry import ObjectRegistryManager, RegisteredObject, object_registry

logger = logging.getLogger("appos.decorators.constant")


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------

# Recognized object_ref prefixes — if a string constant value contains
# a dot-separated namespace matching one of these folder segments, it's
# treated as an object_ref.
_OBJECT_REF_FOLDERS = frozenset({
    "rules", "processes", "integrations", "web_apis",
    "constants", "records", "steps", "interfaces",
    "pages", "sites", "translation_sets", "connected_systems",
})


def _looks_like_object_ref(value: Any) -> bool:
    """
    Heuristic: a string value that looks like an AppOS object reference.

    Object refs follow the pattern "app.folder.name" where folder is one
    of the recognized AppOS type folders (rules, processes, etc.).
    """
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) < 3:
        return False
    return parts[1] in _OBJECT_REF_FOLDERS


def _infer_constant_type(value: Any, return_annotation: Any = None) -> str:
    """
    Infer the constant's type from its resolved value or return annotation.

    Returns one of: "string", "int", "float", "bool", "object_ref", "dict", "list"
    """
    # Check return annotation first (explicit type hint takes priority)
    if return_annotation is not None and return_annotation is not inspect.Parameter.empty:
        annotation_str = getattr(return_annotation, "__name__", str(return_annotation)).lower()
        if annotation_str in ("str", "string"):
            # Even if annotated as str, check if it looks like an object_ref
            if isinstance(value, str) and _looks_like_object_ref(value):
                return "object_ref"
            return "string"
        if annotation_str in ("int", "integer"):
            return "int"
        if annotation_str in ("float",):
            return "float"
        if annotation_str in ("bool",):
            return "bool"

    # Infer from resolved value
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "object_ref" if _looks_like_object_ref(value) else "string"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return "string"


# ---------------------------------------------------------------------------
# Resolved constant data
# ---------------------------------------------------------------------------

@dataclass
class ResolvedConstant:
    """A constant after environment resolution."""

    object_ref: str        # e.g., "crm.constants.TAX_RATE"
    name: str              # e.g., "TAX_RATE"
    value: Any             # Resolved value for current environment
    value_type: str        # "string" | "int" | "float" | "bool" | "object_ref"
    is_object_ref: bool    # True if value_type == "object_ref"
    target_ref: Optional[str] = None  # If object_ref, the target object_ref string
    app_name: Optional[str] = None
    raw_value: Any = None  # The raw (unresolved) value from the decorator

    def __repr__(self) -> str:
        if self.is_object_ref:
            return f"<Constant {self.name}={self.target_ref} (object_ref)>"
        return f"<Constant {self.name}={self.value!r} ({self.value_type})>"


# ---------------------------------------------------------------------------
# ConstantManager
# ---------------------------------------------------------------------------

class ConstantManager:
    """
    Manages all registered @constant objects with resolution, type detection,
    and dynamic dispatch support.

    Resolution pipeline:
        1. Look up constant by object_ref in the ObjectRegistryManager
        2. Call the constant's handler (the decorated function)
        3. Handler returns raw value (possibly a dict with env keys)
        4. The wrapper in core.py resolves environment → final value
        5. ConstantManager detects type (primitive vs object_ref)
        6. For object_ref constants, dispatch() resolves to the target

    Usage:
        manager = get_constant_manager()
        resolved = manager.resolve("crm.constants.TAX_RATE")
        # ResolvedConstant(name="TAX_RATE", value=0.18, value_type="float")

        resolved = manager.resolve("crm.constants.DEFAULT_VALIDATION_RULE")
        # ResolvedConstant(name="DEFAULT_VALIDATION_RULE",
        #                  value="crm.rules.validate_customer_v2",
        #                  is_object_ref=True, target_ref="crm.rules.validate_customer_v2")
    """

    def __init__(self, registry: Optional[ObjectRegistryManager] = None):
        self._registry = registry or object_registry
        # Cache of resolved constants (cleared on environment change or refresh)
        self._cache: Dict[str, ResolvedConstant] = {}
        self._cache_enabled: bool = True

    # -------------------------------------------------------------------
    # Resolution
    # -------------------------------------------------------------------

    def resolve(self, object_ref: str, bypass_cache: bool = False) -> ResolvedConstant:
        """
        Resolve a constant object_ref to its environment-appropriate value.

        Args:
            object_ref: Fully-qualified constant ref (e.g., "crm.constants.TAX_RATE")
            bypass_cache: If True, always re-evaluate the constant handler.

        Returns:
            ResolvedConstant with value, type, and object_ref flag.

        Raises:
            AppOSObjectNotFoundError: If the object_ref doesn't exist.
            AppOSDispatchError: If the object_ref isn't a constant.
        """
        # Check cache
        if self._cache_enabled and not bypass_cache and object_ref in self._cache:
            return self._cache[object_ref]

        registered = self._registry.resolve_or_raise(object_ref)

        if registered.object_type != "constant":
            from appos.engine.errors import AppOSDispatchError
            raise AppOSDispatchError(
                f"Expected constant, got '{registered.object_type}': {object_ref}",
                object_ref=object_ref,
                object_type=registered.object_type,
            )

        # Call the handler — the wrapper in core.py handles env resolution
        handler = registered.handler
        if handler is None:
            from appos.engine.errors import AppOSDispatchError
            raise AppOSDispatchError(
                f"Constant has no handler: {object_ref}",
                object_ref=object_ref,
            )

        # Get the raw value (before env resolution) for introspection
        # The handler is already wrapped by core.py to resolve environment
        value = handler()

        # Detect type
        # Check if the decorator metadata explicitly set type
        meta = registered.metadata or {}
        explicit_type = meta.get("type")

        if explicit_type == "object_ref" or (explicit_type is None and _looks_like_object_ref(value)):
            value_type = "object_ref"
        elif explicit_type:
            value_type = explicit_type
        else:
            # Check return annotation of the original function
            original = getattr(handler, "__wrapped__", handler)
            return_ann = inspect.signature(original).return_annotation
            value_type = _infer_constant_type(value, return_ann)

        is_obj_ref = value_type == "object_ref"
        target_ref = value if is_obj_ref and isinstance(value, str) else None

        result = ResolvedConstant(
            object_ref=object_ref,
            name=registered.metadata.get("name", registered.object_ref.split(".")[-1]),
            value=value,
            value_type=value_type,
            is_object_ref=is_obj_ref,
            target_ref=target_ref,
            app_name=registered.app_name,
            raw_value=value,
        )

        # Cache
        if self._cache_enabled:
            self._cache[object_ref] = result

        logger.debug(f"Resolved constant: {result}")
        return result

    def resolve_value(self, object_ref: str) -> Any:
        """
        Shortcut: resolve and return just the value.

        For object_ref constants, returns the target ref string.
        For primitives, returns the value directly.
        """
        return self.resolve(object_ref).value

    def resolve_target(self, object_ref: str) -> Optional[str]:
        """
        For object_ref constants, return the target object_ref string.
        Returns None for primitive constants.
        """
        resolved = self.resolve(object_ref)
        return resolved.target_ref if resolved.is_object_ref else None

    # -------------------------------------------------------------------
    # Dispatch (for object_ref constants)
    # -------------------------------------------------------------------

    def dispatch_constant(
        self,
        object_ref: str,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Resolve an object_ref constant and dispatch to its target.

        This is a convenience method — equivalent to:
            target = constant_manager.resolve_target(constant_ref)
            result = engine.dispatch(target, inputs)

        The runtime.dispatch() method calls this when it encounters a
        constant object_type.

        Args:
            object_ref: The constant's object_ref (e.g., "crm.constants.DEFAULT_VALIDATION_RULE")
            inputs: Inputs to pass to the resolved target.
            **kwargs: Additional dispatch options.

        Returns:
            The result from dispatching to the target object.

        Raises:
            AppOSDispatchError: If the constant is not an object_ref type,
                                or the target doesn't exist.
        """
        resolved = self.resolve(object_ref)

        if not resolved.is_object_ref or not resolved.target_ref:
            from appos.engine.errors import AppOSDispatchError
            raise AppOSDispatchError(
                f"Constant '{object_ref}' is not an object_ref type "
                f"(type={resolved.value_type}, value={resolved.value!r}). "
                f"Only object_ref constants can be dispatched.",
                object_ref=object_ref,
            )

        target_ref = resolved.target_ref
        logger.info(f"Dispatching object_ref constant: {object_ref} → {target_ref}")

        # Dispatch to the target via the global runtime
        # Import here to avoid circular dependency
        from appos.engine.runtime import get_runtime
        runtime = get_runtime()
        return runtime.dispatch(target_ref, inputs=inputs, **kwargs)

    # -------------------------------------------------------------------
    # Bulk operations
    # -------------------------------------------------------------------

    def get_all_constants(self, app_name: Optional[str] = None) -> List[ResolvedConstant]:
        """
        Resolve and return all registered constants for an app (or all apps).

        Args:
            app_name: Optional app filter. If None, returns all constants.

        Returns:
            List of ResolvedConstant, one per registered constant.
        """
        registered_list = self._registry.get_by_type("constant", app_name=app_name)
        results = []
        for reg in registered_list:
            try:
                resolved = self.resolve(reg.object_ref)
                results.append(resolved)
            except Exception as e:
                logger.warning(f"Failed to resolve constant {reg.object_ref}: {e}")
        return results

    def get_object_ref_constants(self, app_name: Optional[str] = None) -> List[ResolvedConstant]:
        """Get only constants whose type is object_ref."""
        return [c for c in self.get_all_constants(app_name) if c.is_object_ref]

    def get_primitive_constants(self, app_name: Optional[str] = None) -> List[ResolvedConstant]:
        """Get only primitive (non-object_ref) constants."""
        return [c for c in self.get_all_constants(app_name) if not c.is_object_ref]

    # -------------------------------------------------------------------
    # Cache management
    # -------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Clear the resolved constant cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared constant cache ({count} entries)")

    def invalidate(self, object_ref: str) -> None:
        """Invalidate a single cached constant."""
        self._cache.pop(object_ref, None)

    def enable_cache(self) -> None:
        """Enable caching of resolved constants."""
        self._cache_enabled = True

    def disable_cache(self) -> None:
        """Disable caching (useful for testing or dynamic updates)."""
        self._cache_enabled = False
        self._cache.clear()

    # -------------------------------------------------------------------
    # Introspection
    # -------------------------------------------------------------------

    def to_summary(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Return a summary of all constants for AI context / admin console.

        Returns:
            Dict with total count, type breakdown, and constant list.
        """
        all_consts = self.get_all_constants(app_name)
        type_counts: Dict[str, int] = {}
        constant_list = []

        for c in all_consts:
            type_counts[c.value_type] = type_counts.get(c.value_type, 0) + 1
            constant_list.append({
                "object_ref": c.object_ref,
                "name": c.name,
                "value_type": c.value_type,
                "is_object_ref": c.is_object_ref,
                "value": c.target_ref if c.is_object_ref else c.value,
                "app": c.app_name,
            })

        return {
            "total": len(all_consts),
            "by_type": type_counts,
            "constants": constant_list,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_constant_manager: Optional[ConstantManager] = None


def get_constant_manager() -> ConstantManager:
    """Get or create the global ConstantManager singleton."""
    global _constant_manager
    if _constant_manager is None:
        _constant_manager = ConstantManager()
    return _constant_manager
