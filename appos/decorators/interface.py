"""
AppOS Interface Decorator Extensions — @interface.extend override mechanism.

Allows developers to modify auto-generated interfaces without replacing them entirely.
The extend mechanism retrieves the generated interface's component tree, passes it to
the extension function, and re-registers the modified version.

Design refs:
    §9   Record System — "Overriding Generated Interfaces"
    §5.13 Interface — extend/modify generated interface

Usage:
    # Extend an auto-generated interface by name
    @interface_extend("CustomerList")
    def extend_customer_list(base):
        base.columns.append("credit_limit")
        base.actions.append(Button("Export", action="rule", rule="export_customers"))
        return base

    # Replace specific fields in a form
    @interface_extend("CustomerCreate")
    def extend_customer_create(base):
        # Add a custom field
        base.fields.append(Field("custom_field", field_type="text"))
        return base
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("appos.decorators.interface")


class InterfaceExtendRegistry:
    """
    Registry for @interface.extend overrides.

    When an interface is rendered, the renderer checks this registry for
    any extensions and applies them to the base component tree.

    Extensions are applied AFTER the base interface handler runs but
    BEFORE rendering to Reflex components.
    """

    def __init__(self):
        # interface_name → list of extension functions (applied in order)
        self._extensions: Dict[str, list] = {}

    def register(self, interface_name: str, extend_fn: Callable) -> None:
        """Register an extension function for an interface."""
        self._extensions.setdefault(interface_name, []).append(extend_fn)
        logger.debug(f"Registered extension for interface: {interface_name}")

    def get_extensions(self, interface_name: str) -> list:
        """Get all extensions for an interface (applied in registration order)."""
        return self._extensions.get(interface_name, [])

    def has_extensions(self, interface_name: str) -> bool:
        """Check if an interface has any extensions."""
        return interface_name in self._extensions

    def apply_extensions(self, interface_name: str, base_result: Any) -> Any:
        """
        Apply all registered extensions to an interface's base result.

        Each extension receives the (possibly modified) base result and
        must return the modified version.

        Args:
            interface_name: Name of the interface being extended
            base_result: The component tree from the base interface handler

        Returns:
            Modified component tree after all extensions applied
        """
        extensions = self.get_extensions(interface_name)
        if not extensions:
            return base_result

        result = base_result
        for extend_fn in extensions:
            try:
                modified = extend_fn(result)
                if modified is not None:
                    result = modified
                else:
                    logger.warning(
                        f"Extension for {interface_name} returned None — "
                        f"using previous result. Extension functions must return the modified component."
                    )
            except Exception as e:
                logger.error(
                    f"Extension failed for {interface_name}: {e}",
                    exc_info=True,
                )
                # Continue with unmodified result on error

        return result

    def clear(self) -> None:
        """Clear all registered extensions."""
        self._extensions.clear()

    @property
    def count(self) -> int:
        """Total number of registered extensions."""
        return sum(len(exts) for exts in self._extensions.values())


# Global singleton
interface_extend_registry = InterfaceExtendRegistry()


# ---------------------------------------------------------------------------
# @interface.extend decorator
# ---------------------------------------------------------------------------

def interface_extend(
    interface_name: str,
    *,
    priority: int = 0,
) -> Callable:
    """
    Decorator to extend/modify an existing (typically auto-generated) interface.

    The decorated function receives the base interface's component tree
    and must return the modified version.

    Args:
        interface_name: Name of the interface to extend (e.g., "CustomerList")
        priority: Extension priority (lower runs first). Default 0.

    Usage:
        @interface_extend("CustomerList")
        def extend_customer_list(base):
            # base is the DataTableDef returned by the @interface handler
            base.columns.append("credit_limit")
            base.actions.append(Button("Export", action="rule", rule="export_customers"))
            return base

        @interface_extend("CustomerCreate")
        def extend_customer_create(base):
            # base is the FormDef returned by the @interface handler
            from appos.ui.components import Field
            base.fields.insert(0, Field("vip_code", required=True))
            return base
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(base: Any) -> Any:
            return fn(base)

        # Store priority for future ordered application
        wrapper._extend_priority = priority
        wrapper._extend_target = interface_name

        # Register the extension
        interface_extend_registry.register(interface_name, wrapper)

        # Also register in the object registry for discovery
        try:
            from appos.engine.registry import RegisteredObject, object_registry

            module = getattr(fn, "__module__", "")
            app_name = _infer_app(module)

            reg = RegisteredObject(
                object_ref=f"{app_name}.interfaces.{fn.__name__}" if app_name else fn.__name__,
                object_type="interface",
                app_name=app_name,
                name=fn.__name__,
                module_path=module,
                file_path="",
                source_hash="",
                metadata={
                    "name": fn.__name__,
                    "extends": interface_name,
                    "priority": priority,
                    "type": "extension",
                },
                handler=wrapper,
            )
            object_registry.register(reg)
        except Exception as e:
            logger.debug(f"Could not register extension in object registry: {e}")

        return wrapper

    return decorator


def _infer_app(module_path: str) -> str:
    """Infer app name from module path: apps.crm.interfaces.X → crm."""
    parts = module_path.split(".")
    if "apps" in parts:
        idx = parts.index("apps")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


# ---------------------------------------------------------------------------
# Integration with InterfaceRenderer
#
# The renderer calls apply_extensions() after invoking the base handler.
# This is wired in renderer.py via:
#
#   from appos.decorators.interface import interface_extend_registry
#   result = handler()
#   result = interface_extend_registry.apply_extensions(interface_name, result)
# ---------------------------------------------------------------------------
