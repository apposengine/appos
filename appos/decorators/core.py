"""
AppOS Decorators — @expression_rule, @step, @process, @integration,
@web_api, @record, @constant, @page, @interface, @site, @translation_set,
@connected_system.

These decorators:
1. Register the function/class in the ObjectRegistryManager
2. Attach metadata for the engine (permissions, inputs/outputs, etc.)
3. Do NOT intercept execution — that's the engine's job

Design refs: AppOS_Design.md §5 Core Object Types
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from appos.engine.registry import RegisteredObject, object_registry

logger = logging.getLogger("appos.decorators")


# ---------------------------------------------------------------------------
# Helper to attach metadata + register
# ---------------------------------------------------------------------------

def _register_decorator(
    func_or_class: Any,
    object_type: str,
    metadata: Dict[str, Any],
) -> Any:
    """Attach metadata to a decorated function/class and register it."""
    # Attach metadata
    func_or_class._appos_type = object_type
    func_or_class._appos_meta = metadata

    # Determine object_ref and app_name from module path or metadata
    name = metadata.get("name") or getattr(func_or_class, "__name__", str(func_or_class))
    module = getattr(func_or_class, "__module__", "")
    app_name = _infer_app(module)
    object_ref = f"{app_name}.{_type_to_folder(object_type)}.{name}" if app_name else name

    # Register
    reg = RegisteredObject(
        object_ref=object_ref,
        object_type=object_type,
        app_name=app_name,
        handler=func_or_class,
        metadata=metadata,
    )
    object_registry.register(reg)

    logger.debug(f"Registered {object_type}: {object_ref}")
    return func_or_class


def _infer_app(module_path: str) -> str:
    """Infer app name from module path: apps.crm.rules.X → crm."""
    parts = module_path.split(".")
    if "apps" in parts:
        idx = parts.index("apps")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _type_to_folder(object_type: str) -> str:
    """Map object_type to folder name."""
    mapping = {
        "expression_rule": "rules",
        "record": "records",
        "constant": "constants",
        "process": "processes",
        "step": "steps",
        "integration": "integrations",
        "web_api": "web_apis",
        "interface": "interfaces",
        "page": "pages",
        "site": "sites",
        "translation_set": "translation_sets",
        "connected_system": "connected_systems",
    }
    return mapping.get(object_type, object_type)


# ---------------------------------------------------------------------------
# @expression_rule
# ---------------------------------------------------------------------------

def expression_rule(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    inputs: Optional[List[str]] = None,
    outputs: Optional[List[str]] = None,
    depends_on: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    cacheable: bool = False,
    cache_ttl: int = 300,
) -> Any:
    """
    Decorator for expression rules — the universal logic unit.

    Can be used bare (@expression_rule) or with args (@expression_rule(inputs=[...])).
    """
    metadata = {
        "name": name,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "depends_on": depends_on or [],
        "permissions": permissions or [],
        "cacheable": cacheable,
        "cache_ttl": cache_ttl,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "expression_rule", metadata)

    if func is not None:
        # Bare decorator: @expression_rule
        return decorator(func)
    # Decorator with args: @expression_rule(inputs=[...])
    return decorator


# ---------------------------------------------------------------------------
# @constant
# ---------------------------------------------------------------------------

def constant(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    validate: Optional[Callable] = None,
    permissions: Optional[List[str]] = None,
) -> Any:
    """
    Decorator for constants — static values, object refs, env overrides.

    Returns the value based on current environment.
    """
    metadata = {
        "name": name,
        "validate": validate,
        "permissions": permissions or [],
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            value = fn(*args, **kwargs)

            # If the function returns a dict with environment keys, resolve
            if isinstance(value, dict) and "default" in value:
                from appos.engine.config import get_environment
                env = get_environment()
                resolved = value.get(env, value.get("default"))
            else:
                resolved = value

            # Validate if validator provided
            if metadata.get("validate"):
                if not metadata["validate"](resolved):
                    from appos.engine.errors import AppOSValidationError
                    raise AppOSValidationError(
                        f"Constant '{metadata['name']}' failed validation: {resolved}",
                        object_ref=f"{_infer_app(fn.__module__)}.constants.{metadata['name']}",
                    )

            return resolved

        return _register_decorator(wrapper, "constant", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @record
# ---------------------------------------------------------------------------

def record(cls: Optional[type] = None, **kwargs: Any) -> Any:
    """
    Decorator for records — Pydantic data models.
    Attaches Meta configuration and registers with the engine.
    """
    def decorator(klass: type) -> type:
        meta = getattr(klass, "Meta", None)
        metadata = {
            "name": kwargs.get("name", klass.__name__),
            "table_name": getattr(meta, "table_name", _to_snake(klass.__name__) + "s"),
            "audit": getattr(meta, "audit", False),
            "soft_delete": getattr(meta, "soft_delete", False),
            "display_field": getattr(meta, "display_field", None),
            "search_fields": getattr(meta, "search_fields", []),
            "permissions": getattr(meta, "permissions", {}),
            "connected_system": getattr(meta, "connected_system", None),
            "on_create": getattr(meta, "on_create", []),
            "on_update": getattr(meta, "on_update", []),
            "on_delete": getattr(meta, "on_delete", []),
            "row_security_rule": getattr(meta, "row_security_rule", None),
        }
        return _register_decorator(klass, "record", metadata)

    if cls is not None:
        return decorator(cls)
    return decorator


def _to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


# ---------------------------------------------------------------------------
# @process
# ---------------------------------------------------------------------------

def process(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
    inputs: Optional[List[str]] = None,
    display_name: str = "",
    triggers: Optional[List[Any]] = None,
    permissions: Optional[List[str]] = None,
    timeout: Optional[int] = None,
    on_error: str = "fail",
) -> Any:
    """Decorator for processes — multi-step orchestrators."""
    metadata = {
        "name": name,
        "description": description,
        "inputs": inputs or [],
        "display_name": display_name,
        "triggers": triggers or [],
        "permissions": permissions or [],
        "timeout": timeout,
        "on_error": on_error,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "process", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# step() — not a decorator, a builder used inside processes
# ---------------------------------------------------------------------------

def step(
    name: str,
    rule: str,
    input_mapping: Optional[Dict[str, str]] = None,
    output_mapping: Optional[Dict[str, str]] = None,
    retry_count: int = 0,
    retry_delay: int = 5,
    timeout: Optional[int] = None,
    on_error: str = "fail",
    on_success: Optional[str] = None,
    condition: Optional[str] = None,
    fire_and_forget: bool = False,
) -> Dict[str, Any]:
    """
    Build a step definition for use inside a @process function.
    Returns a dict — not registered independently.
    """
    return {
        "type": "step",
        "name": name,
        "rule": rule,
        "input_mapping": input_mapping or {},
        "output_mapping": output_mapping or {},
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "timeout": timeout,
        "on_error": on_error,
        "on_success": on_success,
        "condition": condition,
        "fire_and_forget": fire_and_forget,
    }


def parallel(*steps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap steps in a parallel group (Celery group).
    Returns a dict — the engine interprets this as concurrent execution.
    """
    return {
        "type": "parallel",
        "steps": list(steps),
    }


# ---------------------------------------------------------------------------
# Trigger builders for @process
# ---------------------------------------------------------------------------

def event(event_name: str) -> Dict[str, str]:
    """Build an event trigger for a process."""
    return {"type": "event", "event": event_name}


def schedule(cron_expression: str, timezone: str = "UTC") -> Dict[str, str]:
    """Build a schedule trigger for a process."""
    return {"type": "schedule", "cron": cron_expression, "timezone": timezone}


# ---------------------------------------------------------------------------
# @integration
# ---------------------------------------------------------------------------

def integration(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    connected_system: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    log_payload: bool = False,
) -> Any:
    """Decorator for integrations — outbound API calls."""
    metadata = {
        "name": name,
        "connected_system": connected_system,
        "permissions": permissions or [],
        "log_payload": log_payload,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "integration", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @web_api
# ---------------------------------------------------------------------------

def web_api(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    method: str = "GET",
    path: str = "",
    auth: Optional[Dict[str, Any]] = None,
    version: str = "v1",
    rate_limit: Optional[Dict[str, int]] = None,
    permissions: Optional[List[str]] = None,
    log_payload: bool = False,
) -> Any:
    """Decorator for web APIs — expose functions as REST endpoints."""
    metadata = {
        "name": name,
        "method": method,
        "path": path,
        "auth": auth or {},
        "version": version,
        "rate_limit": rate_limit,
        "permissions": permissions or [],
        "log_payload": log_payload,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "web_api", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @interface
# ---------------------------------------------------------------------------

def interface(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    record_name: Optional[str] = None,
    type: str = "custom",
    permissions: Optional[List[str]] = None,
) -> Any:
    """Decorator for interfaces — UI component definitions."""
    metadata = {
        "name": name,
        "record": record_name,
        "type": type,
        "permissions": permissions or [],
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "interface", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @page
# ---------------------------------------------------------------------------

def page(
    func: Optional[Callable] = None,
    *,
    route: str = "",
    title: str = "",
    interface_name: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    on_load: Optional[str] = None,
) -> Any:
    """Decorator for pages — routable Reflex pages."""
    metadata = {
        "route": route,
        "title": title,
        "interface": interface_name,
        "permissions": permissions or [],
        "on_load": on_load,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "page", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @site
# ---------------------------------------------------------------------------

def site(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
) -> Any:
    """Decorator for sites — collection of pages."""
    metadata = {"name": name}

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "site", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# @translation_set
# ---------------------------------------------------------------------------

def translation_set(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    app: Optional[str] = None,
) -> Any:
    """Decorator for translation sets — i18n labels."""
    metadata = {"name": name, "app": app}

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        # Add translation helper methods
        wrapper.get = _make_translation_getter(fn, metadata)
        wrapper.ref = _make_translation_ref(metadata)

        return _register_decorator(wrapper, "translation_set", metadata)

    if func is not None:
        return decorator(func)
    return decorator


def _make_translation_getter(fn: Callable, metadata: Dict[str, Any]) -> Callable:
    """Build a .get(key, lang=None, **params) method for translation sets."""
    _data_cache: Dict[str, Any] = {}

    def get(key: str, lang: Optional[str] = None, **params: Any) -> str:
        if not _data_cache:
            _data_cache.update(fn())

        translations = _data_cache.get(key, {})
        if not translations:
            return key  # Fallback: return key name

        # Resolve language
        if lang is None:
            from appos.engine.context import get_execution_context
            ctx = get_execution_context()
            lang = ctx.preferred_language if ctx else "en"

        text = translations.get(lang, translations.get("en", key))

        # Format with params
        if params:
            try:
                text = text.format(**params)
            except (KeyError, IndexError):
                pass

        return text

    return get


def _make_translation_ref(metadata: Dict[str, Any]) -> Callable:
    """Build a .ref(key) method that returns a lazy translation reference."""
    def ref(key: str) -> Dict[str, Any]:
        return {"_type": "translation_ref", "set": metadata["name"], "key": key}
    return ref


# ---------------------------------------------------------------------------
# @connected_system
# ---------------------------------------------------------------------------

def connected_system(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    type: str = "database",
    description: str = "",
) -> Any:
    """Decorator for connected systems — external connections."""
    metadata = {
        "name": name,
        "type": type,
        "description": description,
    }

    def decorator(fn: Callable) -> Callable:
        metadata["name"] = metadata["name"] or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return _register_decorator(wrapper, "connected_system", metadata)

    if func is not None:
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# Record relationship helpers
# ---------------------------------------------------------------------------

def has_many(
    target: str,
    back_ref: Optional[str] = None,
    cascade: str = "save-update, merge",
) -> Dict[str, Any]:
    """Declare a has-many relationship on a record."""
    return {
        "_relationship": "has_many",
        "target": target,
        "back_ref": back_ref,
        "cascade": cascade,
    }


def belongs_to(
    target: str,
    required: bool = False,
) -> Dict[str, Any]:
    """Declare a belongs-to relationship on a record."""
    return {
        "_relationship": "belongs_to",
        "target": target,
        "required": required,
    }


def has_one(
    target: str,
    back_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Declare a has-one relationship on a record."""
    return {
        "_relationship": "has_one",
        "target": target,
        "back_ref": back_ref,
    }
