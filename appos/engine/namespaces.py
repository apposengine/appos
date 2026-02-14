"""
AppOS SecureAutoImportNamespace — Zero-Import system.

Intercepts all attribute access on global namespaces (records, constants,
rules, processes, integrations, web_apis, translations).

On every access:
  1. Security check (BLOCKING — cache-first, DB fallback)
  2. Dependency tracking (NON-BLOCKING — pushed to log queue)
  3. Lazy-load and cache the resolved module

Design refs: AppOS_Design.md §4, AppOS_Permissions_Reference.md
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from appos.engine.errors import AppOSSecurityError

logger = logging.getLogger("appos.engine.namespaces")


# ---------------------------------------------------------------------------
# ProcessStartProxy — enables processes.X.start(inputs={...})
# ---------------------------------------------------------------------------

class ProcessStartProxy:
    """
    Wraps a resolved process to provide .start(inputs={}) method.

    Usage (inside expression rules / other processes):
        processes.onboard_customer.start(inputs={"customer_id": 123})

    This is what SecureAutoImportNamespace returns for object_type="processes".
    """

    def __init__(self, app_name: str, process_name: str, module: Any = None):
        self._app_name = app_name
        self._process_name = process_name
        self._module = module
        self._object_ref = f"{app_name}.processes.{process_name}"

    def start(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        async_execution: bool = True,
    ) -> Dict[str, Any]:
        """
        Start this process with the given inputs.

        Args:
            inputs: Process input data.
            user_id: User ID who triggered the start.
            async_execution: If True, dispatch via Celery.

        Returns:
            Instance dict from ProcessExecutor.start_process().
        """
        from appos.engine.runtime import get_runtime

        runtime = get_runtime()
        return runtime.dispatch(
            self._object_ref,
            inputs=inputs or {},
            user_id=user_id,
            async_execution=async_execution,
        )

    def __repr__(self) -> str:
        return f"<Process {self._object_ref}>"

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to underlying module for advanced use."""
        if name.startswith("_"):
            raise AttributeError(name)
        if self._module:
            return getattr(self._module, name)
        raise AttributeError(
            f"Process '{self._process_name}' has no attribute '{name}'"
        )


class SecureAutoImportNamespace:
    """
    Intercepts attribute access on global namespaces.

    Usage:
        records = SecureAutoImportNamespace("crm", "records", security_policy, log_queue)
        customer = records.customer  # → security check, log, lazy-load apps.crm.records.customer
    """

    def __init__(
        self,
        app_name: str,
        object_type: str,
        security_policy: Any,
        log_queue: Any = None,
        dependency_graph: Any = None,
    ):
        self._app_name = app_name
        self._object_type = object_type
        self._security_policy = security_policy
        self._log_queue = log_queue
        self._dep_graph = dependency_graph
        self._cache: Dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        # Avoid infinite recursion on internal attrs
        if name.startswith("_"):
            raise AttributeError(name)

        object_ref = f"{self._app_name}.{self._object_type}.{name}"

        # 1. SECURITY CHECK — BLOCKING
        from appos.engine.context import get_execution_context

        ctx = get_execution_context()
        permission = self._default_permission_for_access()

        if ctx:
            allowed = self._security_policy.check_access(
                user_groups=ctx.user_groups,
                object_ref=object_ref,
                permission=permission,
                user_type=ctx.user_type,
            )
            if not allowed:
                self._push_security_log(object_ref, ctx, "DENIED", permission)
                raise AppOSSecurityError(
                    f"Access denied: {ctx.username} → {object_ref} ({permission})",
                    user_id=ctx.user_id,
                    user_groups=sorted(ctx.user_groups),
                    object_ref=object_ref,
                    required_permission=permission,
                    execution_id=ctx.execution_id,
                )

        # 2. DEPENDENCY TRACKING — NON-BLOCKING
        caller_info = self._get_caller_info()
        if ctx:
            self._push_dependency_log(object_ref, ctx, caller_info)

        # 3. LAZY LOAD + CACHE
        if name not in self._cache:
            module = self._resolve_module(name)
            self._cache[name] = module

        return self._cache[name]

    def _default_permission_for_access(self) -> str:
        """Determine default permission to check based on object type."""
        if self._object_type in ("rules", "constants", "translation_sets"):
            return "use"
        if self._object_type in ("processes",):
            return "use"
        if self._object_type in ("records",):
            return "view"
        if self._object_type in ("integrations", "web_apis"):
            return "use"
        return "view"

    def _resolve_module(self, name: str) -> Any:
        """
        Lazy-load the Python module or object handler.

        Resolution:  apps.{app_name}.{object_type}.{name}

        For processes, wraps the result in a ProcessStartProxy
        to enable ``processes.X.start(inputs={...})``.
        """
        module_path = f"apps.{self._app_name}.{self._object_type}.{name}"
        resolved_module = None
        try:
            resolved_module = importlib.import_module(module_path)
            logger.debug(f"Loaded module: {module_path}")
        except ImportError as e:
            # Try as a sub-attribute of a package
            try:
                parent_path = f"apps.{self._app_name}.{self._object_type}"
                parent = importlib.import_module(parent_path)
                resolved_module = getattr(parent, name)
            except (ImportError, AttributeError):
                raise AppOSSecurityError(
                    f"Object not found: {self._app_name}.{self._object_type}.{name}",
                    object_ref=f"{self._app_name}.{self._object_type}.{name}",
                ) from e

        # Wrap processes in ProcessStartProxy for .start() support
        if self._object_type == "processes":
            return ProcessStartProxy(
                app_name=self._app_name,
                process_name=name,
                module=resolved_module,
            )

        return resolved_module

    def _get_caller_info(self) -> Dict[str, Any]:
        """Extract caller information from the call stack."""
        try:
            frame = inspect.currentframe()
            # Walk up: _get_caller_info → __getattr__ → actual caller
            if frame and frame.f_back and frame.f_back.f_back:
                caller = frame.f_back.f_back
                return {
                    "file": caller.f_code.co_filename,
                    "function": caller.f_code.co_name,
                    "line": caller.f_lineno,
                }
        except Exception:
            pass
        return {}

    def _push_dependency_log(
        self, object_ref: str, ctx: Any, caller_info: Dict[str, Any]
    ) -> None:
        """Push dependency log entry to the async queue (non-blocking)."""
        if self._log_queue is None:
            return

        try:
            from appos.engine.logging import LogEntry, _base_entry

            data = _base_entry(
                event="dependency_accessed",
                level="DEBUG",
                object_ref=object_ref,
                execution_id=ctx.execution_id,
                user_id=ctx.user_id,
                app=self._app_name,
            )
            if caller_info:
                data["caller"] = caller_info

            entry = LogEntry(self._object_type, "execution", data)
            self._log_queue.push(entry)
        except Exception as e:
            logger.debug(f"Failed to log dependency: {e}")

        # Update dependency graph
        if self._dep_graph and caller_info:
            try:
                caller_ref = self._infer_object_ref(caller_info)
                if caller_ref:
                    self._dep_graph.add_dependency(caller_ref, object_ref)
            except Exception:
                pass

    def _push_security_log(
        self, object_ref: str, ctx: Any, status: str, permission: str
    ) -> None:
        """Push security event to the async queue (non-blocking)."""
        if self._log_queue is None:
            return

        try:
            from appos.engine.logging import log_security_event

            entry = log_security_event(
                event="security_denied" if status == "DENIED" else "security_allowed",
                object_ref=object_ref,
                object_type=self._object_type,
                permission_needed=permission,
                user_id=ctx.user_id,
                user_groups=sorted(ctx.user_groups),
                app=self._app_name,
                execution_id=ctx.execution_id,
            )
            self._log_queue.push(entry)
        except Exception as e:
            logger.debug(f"Failed to log security event: {e}")

    def _infer_object_ref(self, caller_info: Dict[str, Any]) -> Optional[str]:
        """Infer object_ref from caller file path."""
        try:
            file_path = caller_info.get("file", "")
            # Extract from path: .../apps/{app}/{object_type}/{name}.py
            path = Path(file_path)
            parts = path.parts
            if "apps" in parts:
                idx = parts.index("apps")
                if idx + 3 <= len(parts):
                    app = parts[idx + 1]
                    obj_type = parts[idx + 2]
                    name = path.stem
                    return f"{app}.{obj_type}.{name}"
        except Exception:
            pass
        return None

    def invalidate_cache(self, name: Optional[str] = None) -> None:
        """Invalidate cached module(s)."""
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()

    def __repr__(self) -> str:
        return f"<Namespace {self._app_name}.{self._object_type}>"


class CrossAppNamespace:
    """
    Root-level namespace for cross-app access.

    Usage:
        finance = CrossAppNamespace("finance", security_policy, log_queue, dep_graph)
        tax = finance.rules.calculate_tax(amount=100)

    This enables:
        finance.rules.X      → SecureAutoImportNamespace("finance", "rules", ...)
        finance.constants.X   → SecureAutoImportNamespace("finance", "constants", ...)
    """

    OBJECT_TYPES = {
        "records", "constants", "rules", "processes", "steps",
        "integrations", "web_apis", "interfaces", "pages",
        "translation_sets", "documents", "folders",
    }

    def __init__(
        self,
        app_name: str,
        security_policy: Any,
        log_queue: Any = None,
        dependency_graph: Any = None,
    ):
        self._app_name = app_name
        self._security_policy = security_policy
        self._log_queue = log_queue
        self._dep_graph = dependency_graph
        self._namespaces: Dict[str, SecureAutoImportNamespace] = {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        if name in self.OBJECT_TYPES:
            if name not in self._namespaces:
                self._namespaces[name] = SecureAutoImportNamespace(
                    app_name=self._app_name,
                    object_type=name,
                    security_policy=self._security_policy,
                    log_queue=self._log_queue,
                    dependency_graph=self._dep_graph,
                )
            return self._namespaces[name]

        raise AttributeError(
            f"'{self._app_name}' has no object type '{name}'. "
            f"Valid types: {', '.join(sorted(self.OBJECT_TYPES))}"
        )

    def __repr__(self) -> str:
        return f"<AppNamespace {self._app_name}>"


# ---------------------------------------------------------------------------
# TranslationSetProxy — enables translations.crm_labels.get("key") syntax
# ---------------------------------------------------------------------------

class TranslationSetProxy:
    """
    Wraps a registered @translation_set to provide .get() and .ref() methods.

    Usage:
        translations = TranslationsNamespace("crm", security_policy)
        msg = translations.crm_labels.get("welcome_message", name="Alice")
        label = translations.crm_labels.ref("customer_name")  # lazy ref for interfaces

    Design ref: §5.18 Translation Set — language resolution, fallback chain
    """

    def __init__(self, set_name: str, handler: Any):
        self._set_name = set_name
        self._handler = handler
        self._data_cache: Optional[Dict[str, Any]] = None

    def _load_data(self) -> Dict[str, Any]:
        """Lazy-load translation data by calling the handler."""
        if self._data_cache is None:
            # If the handler itself has a .get() method (already wrapped by decorator),
            # we still need the raw data for our own fallback chain
            if hasattr(self._handler, '__wrapped__') or callable(self._handler):
                try:
                    raw = self._handler()
                    if isinstance(raw, dict):
                        self._data_cache = raw
                    else:
                        self._data_cache = {}
                except Exception:
                    self._data_cache = {}
            else:
                self._data_cache = {}
        return self._data_cache

    def get(self, key: str, lang: Optional[str] = None, **params: Any) -> str:
        """
        Get a translated string with fallback chain.

        Resolution: preferred_language → "en" → key name

        Args:
            key: Translation key
            lang: Override language (None = auto-detect from user context)
            **params: Format parameters for string interpolation

        Returns:
            Resolved translated string.
        """
        # If the decorator already attached a .get(), delegate to it
        if hasattr(self._handler, 'get') and callable(self._handler.get):
            return self._handler.get(key, lang=lang, **params)

        # Otherwise use our own resolution
        from appos.engine.context import resolve_translation
        data = self._load_data()
        return resolve_translation(data, key, lang=lang, **params)

    def ref(self, key: str) -> Dict[str, Any]:
        """
        Create a lazy translation reference for use in Interfaces.

        The InterfaceRenderer resolves these at render time based on
        the current user's preferred_language.

        Returns:
            Dict with _type="translation_ref" for the renderer.
        """
        # If the decorator already attached a .ref(), delegate
        if hasattr(self._handler, 'ref') and callable(self._handler.ref):
            return self._handler.ref(key)

        return {
            "_type": "translation_ref",
            "set": self._set_name,
            "key": key,
        }

    def keys(self) -> List[str]:
        """List all available translation keys."""
        data = self._load_data()
        return list(data.keys())

    def languages(self, key: Optional[str] = None) -> Set[str]:
        """List available languages (for a specific key, or all keys)."""
        data = self._load_data()
        langs: Set[str] = set()
        if key:
            key_data = data.get(key, {})
            langs.update(key_data.keys())
        else:
            for key_data in data.values():
                if isinstance(key_data, dict):
                    langs.update(key_data.keys())
        return langs

    def __repr__(self) -> str:
        return f"<TranslationSet '{self._set_name}'>"


class TranslationsNamespace:
    """
    Dedicated namespace for translations.{set_name}.get("key") access.

    Unlike SecureAutoImportNamespace (which returns raw modules),
    this wraps each translation set in a TranslationSetProxy that provides
    .get(key) and .ref(key) methods with language resolution.

    Usage (inside rules, processes, interfaces):
        translations.crm_labels.get("welcome_message", name=ctx.user.full_name)
        Field("name", label=translations.crm_labels.ref("customer_name"))

    Design ref: §5.18 Translation Set
    """

    def __init__(
        self,
        app_name: str,
        security_policy: Any,
        log_queue: Any = None,
        dependency_graph: Any = None,
    ):
        self._app_name = app_name
        self._security_policy = security_policy
        self._log_queue = log_queue
        self._dep_graph = dependency_graph
        self._inner = SecureAutoImportNamespace(
            app_name=app_name,
            object_type="translation_sets",
            security_policy=security_policy,
            log_queue=log_queue,
            dependency_graph=dependency_graph,
        )
        self._proxies: Dict[str, TranslationSetProxy] = {}

    def __getattr__(self, name: str) -> TranslationSetProxy:
        if name.startswith("_"):
            raise AttributeError(name)

        if name not in self._proxies:
            # Resolve through secure namespace (security check + lazy load)
            handler = self._inner.__getattr__(name)
            self._proxies[name] = TranslationSetProxy(name, handler)

        return self._proxies[name]

    def invalidate_cache(self, name: Optional[str] = None) -> None:
        """Invalidate cached translation sets."""
        if name:
            self._proxies.pop(name, None)
            self._inner.invalidate_cache(name)
        else:
            self._proxies.clear()
            self._inner.invalidate_cache()

    def __repr__(self) -> str:
        return f"<TranslationsNamespace {self._app_name}>"


def build_app_namespaces(
    app_name: str,
    security_policy: Any,
    log_queue: Any = None,
    dependency_graph: Any = None,
) -> Dict[str, Any]:
    """
    Build all standard namespaces for an app.

    Returns dict: {"records": ns, "constants": ns, "rules": ns, "translations": ns, ...}
    These are injected into the app's execution globals.

    Note: "translations" is a TranslationsNamespace (not SecureAutoImportNamespace)
    to provide .get()/.ref() methods. "translation_sets" is also available as raw access.
    """
    object_types = [
        "records", "constants", "rules", "processes", "steps",
        "integrations", "web_apis", "interfaces", "pages",
        "translation_sets",
    ]

    namespaces: Dict[str, Any] = {}
    for obj_type in object_types:
        namespaces[obj_type] = SecureAutoImportNamespace(
            app_name=app_name,
            object_type=obj_type,
            security_policy=security_policy,
            log_queue=log_queue,
            dependency_graph=dependency_graph,
        )

    # Add dedicated translations namespace with .get()/.ref() proxy
    namespaces["translations"] = TranslationsNamespace(
        app_name=app_name,
        security_policy=security_policy,
        log_queue=log_queue,
        dependency_graph=dependency_graph,
    )

    return namespaces
