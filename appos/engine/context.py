"""
AppOS Execution & Process Context — Thread-safe state management.

Four-State Model (Design §7):
1. DEFINITION STATE  — Object source code (files)
2. COMPILED STATE    — Parsed objects in registry (memory)
3. RUNTIME STATE     — ExecutionContext per request (contextvars)
4. PROCESS STATE     — ProcessContext per process instance (DB-backed)

Usage:
    from appos.engine.context import (
        current_execution_context,
        ExecutionContext,
        ProcessContext,
        set_execution_context,
        get_execution_context,
    )
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from appos.engine.errors import AppOSSecurityError

# ---------------------------------------------------------------------------
# Thread-safe context variable — one per request/task execution
# ---------------------------------------------------------------------------

current_execution_context: ContextVar[Optional["ExecutionContext"]] = ContextVar(
    "execution_context", default=None
)


@dataclass
class ExecutionContext:
    """
    Thread-safe per-request execution context. Set on login, used on every access.

    Populated by auth middleware and carried through the full request lifecycle.
    """

    user_id: int
    username: str
    user_type: str  # "basic" | "system_admin" | "service_account"
    user_groups: Set[str]
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    app_name: Optional[str] = None
    preferred_language: str = "en"
    timezone: str = "UTC"
    full_name: str = ""
    session_id: Optional[str] = None

    # Populated by auto-import layer
    dependencies_accessed: List[dict] = field(default_factory=list)

    # Process context (set when running inside a process)
    process_instance_id: Optional[str] = None
    step_name: Optional[str] = None

    @property
    def is_system_admin(self) -> bool:
        return self.user_type == "system_admin"

    @property
    def is_service_account(self) -> bool:
        return self.user_type == "service_account"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "user_type": self.user_type,
            "user_groups": sorted(self.user_groups),
            "execution_id": self.execution_id,
            "app_name": self.app_name,
            "preferred_language": self.preferred_language,
            "timezone": self.timezone,
            "process_instance_id": self.process_instance_id,
            "step_name": self.step_name,
        }


def set_execution_context(ctx: ExecutionContext) -> None:
    """Set the execution context for the current thread/task."""
    current_execution_context.set(ctx)


def get_execution_context() -> Optional[ExecutionContext]:
    """Get the current execution context. Returns None if not set."""
    return current_execution_context.get()


def require_execution_context() -> ExecutionContext:
    """Get execution context or raise error if not set."""
    ctx = get_execution_context()
    if ctx is None:
        raise AppOSSecurityError(
            "No execution context — user not authenticated",
            error_type="missing_context",
        )
    return ctx


def clear_execution_context() -> None:
    """Clear the execution context (e.g., on logout or request end)."""
    current_execution_context.set(None)


def get_preferred_language() -> str:
    """
    Get the current user's preferred language.

    Resolution chain (Design §5.18):
    1. User's preferred_language from ExecutionContext (populated from DB User record)
    2. Falls back to "en" (mandatory default)

    This is used by @translation_set .get() methods and the InterfaceRenderer
    for resolving translation_ref dicts.
    """
    ctx = get_execution_context()
    if ctx and ctx.preferred_language:
        return ctx.preferred_language
    return "en"


def resolve_translation(
    translations_data: Dict[str, Dict[str, str]],
    key: str,
    lang: Optional[str] = None,
    **format_params: Any,
) -> str:
    """
    Resolve a translation key with full fallback chain.

    Fallback chain (Design §5.18):
    1. User's preferred_language (or explicit `lang` param)
    2. "en" (mandatory default — every key MUST include "en")
    3. Key name as-is (if key completely missing from the set)

    Args:
        translations_data: Full translation dict {key: {lang: text}}
        key: Translation key to resolve
        lang: Override language (if None, uses ctx.user.preferred_language)
        **format_params: Named params for string formatting

    Returns:
        Resolved translated string.
    """
    # Get target language
    if lang is None:
        lang = get_preferred_language()

    # Get translations for key
    key_translations = translations_data.get(key)
    if not key_translations:
        # Key completely missing → return key name as-is
        return key

    # Resolve with fallback chain
    text = key_translations.get(lang)
    if text is None:
        # Fallback to English (mandatory default)
        text = key_translations.get("en")
    if text is None:
        # Last resort — return key name
        return key

    # Format with params
    if format_params:
        try:
            text = text.format(**format_params)
        except (KeyError, IndexError, ValueError):
            pass  # Return unformatted if params don't match

    return text


# ---------------------------------------------------------------------------
# Process Context — DB-backed, accessible across all steps
# ---------------------------------------------------------------------------

class ProcessContext:
    """
    Process-level state. Variables accessible across all steps.
    Persisted to ProcessInstance.variables in DB.

    Variable visibility:
    - logged=True (default): visible in logs, admin UI, AI queries, stored plaintext
    - logged=False:          hidden from logs/UI/AI, stored as SHA-256 hash
    - sensitive=True:        hidden from everything, stored encrypted (Fernet)
    """

    def __init__(
        self,
        instance_id: str,
        inputs: Dict[str, Any] = None,
        variables: Dict[str, Any] = None,
        visibility: Dict[str, str] = None,
    ):
        self.instance_id = instance_id
        self._inputs = inputs or {}
        self._variables = variables or {}
        self._visibility: Dict[str, str] = visibility or {}  # {var_name: "logged"|"hidden"|"sensitive"}
        self._dirty = False

    def var(
        self,
        name: str,
        value: Any = None,
        logged: bool = True,
        sensitive: bool = False,
    ) -> Any:
        """
        Get or set a process variable.

        Args:
            name: Variable name.
            value: If provided, sets the variable. If None, gets it.
            logged: If False, variable is hidden from logs/UI (stored hashed).
            sensitive: If True, variable is encrypted and never shown anywhere.

        Returns:
            The variable value (on get) or the set value (on set).
        """
        if value is not None:
            self._variables[name] = value
            if sensitive:
                self._visibility[name] = "sensitive"
            elif not logged:
                self._visibility[name] = "hidden"
            else:
                self._visibility[name] = "logged"
            self._dirty = True
            return value
        return self._variables.get(name)

    def input(self, name: str) -> Any:
        """Get a process input value."""
        return self._inputs.get(name)

    @property
    def inputs(self) -> Dict[str, Any]:
        """All process inputs (read-only)."""
        return dict(self._inputs)

    @property
    def variables(self) -> Dict[str, Any]:
        """All variables (internal use)."""
        return dict(self._variables)

    @property
    def visibility(self) -> Dict[str, str]:
        """Variable visibility flags."""
        return dict(self._visibility)

    def output(self, name: str, value: Any) -> None:
        """Set a named output value (shortcut for var with logged=True)."""
        self.var(name, value, logged=True)

    def outputs(self) -> Dict[str, Any]:
        """Get all logged variables (for returning from rules/steps)."""
        return {
            k: v for k, v in self._variables.items()
            if self._visibility.get(k, "logged") == "logged"
        }

    @property
    def is_dirty(self) -> bool:
        """Whether variables have been modified since last persist."""
        return self._dirty

    def mark_clean(self) -> None:
        """Mark as persisted."""
        self._dirty = False

    def get_persistable_variables(self) -> Dict[str, Any]:
        """
        Get variables in their storage form:
        - logged: plaintext
        - hidden: SHA-256 hash
        - sensitive: Fernet-encrypted via CredentialManager
        """
        result = {}
        for name, value in self._variables.items():
            vis = self._visibility.get(name, "logged")
            if vis == "logged":
                result[name] = value
            elif vis == "hidden":
                result[name] = f"sha256:{hashlib.sha256(json.dumps(value, default=str).encode()).hexdigest()}"
            elif vis == "sensitive":
                # Use CredentialManager for Fernet encryption
                try:
                    from appos.engine.credentials import CredentialManager
                    cm = CredentialManager()
                    encrypted = cm.encrypt({name: value})
                    result[name] = f"enc:{encrypted.decode('utf-8') if isinstance(encrypted, bytes) else encrypted}"
                except Exception:
                    # Fallback: store hashed if encryption unavailable
                    result[name] = f"sha256:{hashlib.sha256(json.dumps(value, default=str).encode()).hexdigest()}"
        return result

    @property
    def user(self) -> Optional[ExecutionContext]:
        """Get current user from execution context."""
        return get_execution_context()

    def __repr__(self) -> str:
        return (
            f"<ProcessContext(instance_id='{self.instance_id}', "
            f"vars={len(self._variables)}, inputs={len(self._inputs)})>"
        )


# ---------------------------------------------------------------------------
# Rule Execution Context (lightweight wrapper for expression rules)
# ---------------------------------------------------------------------------

class RuleContext:
    """
    Context passed to @expression_rule functions.
    Provides input(), output(), and access to execution context.
    """

    def __init__(self, inputs: Dict[str, Any] = None, process_ctx: Optional[ProcessContext] = None):
        self._inputs = inputs or {}
        self._outputs: Dict[str, Any] = {}
        self._process_ctx = process_ctx

    def input(self, name: str) -> Any:
        """Get an input value."""
        return self._inputs.get(name)

    def output(self, name: str, value: Any) -> None:
        """Set an output value."""
        self._outputs[name] = value

    def outputs(self) -> Dict[str, Any]:
        """Get all output values."""
        return dict(self._outputs)

    @property
    def var(self):
        """Access process variables (only available when running inside a process)."""
        if self._process_ctx:
            return self._process_ctx.var
        raise RuntimeError("ctx.var is only available inside a process step")

    @property
    def user(self) -> Optional[ExecutionContext]:
        """Get current user from execution context."""
        return get_execution_context()

    @property
    def execution_id(self) -> Optional[str]:
        ctx = get_execution_context()
        return ctx.execution_id if ctx else None

    def __repr__(self) -> str:
        return f"<RuleContext(inputs={list(self._inputs.keys())}, outputs={list(self._outputs.keys())})>"
