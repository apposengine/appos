"""
AppOS Record Decorator — Extended record functionality with event hooks,
Meta configuration parsing, and record lifecycle management.

Provides:
    - RecordEventManager: Central registry for record event hooks
    - Event types: on_create, on_update, on_delete, on_view
    - Hook dispatching via engine.dispatch()
    - Record Meta configuration helpers

The @record decorator in core.py handles registration.
This module provides the event hook execution layer.

Design refs: AppOS_Design.md §5.7 (Record Meta), §9 (Auto-Generation pipeline)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("appos.decorators.record")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class RecordEvent:
    """Enumeration of record lifecycle events."""
    ON_CREATE = "on_create"
    ON_UPDATE = "on_update"
    ON_DELETE = "on_delete"
    ON_VIEW = "on_view"
    BEFORE_CREATE = "before_create"
    BEFORE_UPDATE = "before_update"
    BEFORE_DELETE = "before_delete"

    ALL = {
        ON_CREATE, ON_UPDATE, ON_DELETE, ON_VIEW,
        BEFORE_CREATE, BEFORE_UPDATE, BEFORE_DELETE,
    }


@dataclass
class RecordHook:
    """A registered event hook for a record."""
    record_ref: str          # "crm.records.customer"
    event: str               # "on_create", "on_update", etc.
    target_ref: str          # Object ref to dispatch: "crm.rules.validate_customer" or "crm.processes.onboard"
    priority: int = 0        # Lower = runs first
    condition: Optional[str] = None  # Optional condition expression
    async_dispatch: bool = False     # If True, dispatch via Celery (fire-and-forget)

    def __repr__(self) -> str:
        return f"<RecordHook({self.record_ref}.{self.event} → {self.target_ref})>"


# ---------------------------------------------------------------------------
# Record Event Manager
# ---------------------------------------------------------------------------

class RecordEventManager:
    """
    Central registry and dispatcher for record event hooks.

    Hooks are registered from @record Meta configuration:
        - Meta.on_create = ["onboard_customer"]     → fires on CREATE
        - Meta.on_update = ["log_customer_change"]   → fires on UPDATE
        - Meta.on_delete = []                        → no DELETE hooks

    Usage:
        manager = RecordEventManager()
        manager.register_hooks("crm.records.customer", {
            "on_create": ["crm.processes.onboard_customer"],
            "on_update": ["crm.rules.log_customer_change"],
        })

        # When a record is created:
        await manager.fire("crm.records.customer", "on_create", {
            "record_id": 42,
            "data": {"name": "Acme Corp", ...}
        })
    """

    def __init__(self):
        self._hooks: Dict[str, Dict[str, List[RecordHook]]] = {}
        # _hooks[record_ref][event] = [RecordHook, ...]

    def register_hooks(
        self,
        record_ref: str,
        hook_config: Dict[str, List[str]],
        app_name: str = "",
    ) -> int:
        """
        Register event hooks from a record's Meta configuration.

        Args:
            record_ref: Fully qualified record reference (e.g., "crm.records.customer").
            hook_config: Dict of {event: [target_refs]}, e.g.,
                {"on_create": ["onboard_customer"], "on_update": ["log_change"]}
            app_name: App name for qualifying short target refs.

        Returns:
            Number of hooks registered.
        """
        if record_ref not in self._hooks:
            self._hooks[record_ref] = {}

        count = 0
        for event, targets in hook_config.items():
            if event not in RecordEvent.ALL:
                logger.warning(f"Unknown event '{event}' for {record_ref} — skipping")
                continue

            if event not in self._hooks[record_ref]:
                self._hooks[record_ref][event] = []

            for target in targets:
                # Qualify with app name if not fully qualified
                qualified = target
                if app_name and "." not in target:
                    # Short name: "onboard_customer" → check if it's a process or rule
                    # Convention: if starts with verb, likely a rule; otherwise check both
                    qualified = f"{app_name}.rules.{target}"

                hook = RecordHook(
                    record_ref=record_ref,
                    event=event,
                    target_ref=qualified,
                )
                self._hooks[record_ref][event].append(hook)
                count += 1
                logger.debug(f"Registered hook: {record_ref}.{event} → {qualified}")

        return count

    def register_hook(
        self,
        record_ref: str,
        event: str,
        target_ref: str,
        priority: int = 0,
        condition: Optional[str] = None,
        async_dispatch: bool = False,
    ) -> None:
        """Register a single event hook programmatically."""
        if record_ref not in self._hooks:
            self._hooks[record_ref] = {}
        if event not in self._hooks[record_ref]:
            self._hooks[record_ref][event] = []

        hook = RecordHook(
            record_ref=record_ref,
            event=event,
            target_ref=target_ref,
            priority=priority,
            condition=condition,
            async_dispatch=async_dispatch,
        )
        self._hooks[record_ref][event].append(hook)
        # Sort by priority
        self._hooks[record_ref][event].sort(key=lambda h: h.priority)

    def fire(
        self,
        record_ref: str,
        event: str,
        payload: Dict[str, Any],
        runtime=None,
    ) -> List[Dict[str, Any]]:
        """
        Fire all hooks for a record event synchronously.

        Args:
            record_ref: Record reference (e.g., "crm.records.customer").
            event: Event name ("on_create", "on_update", "on_delete").
            payload: Event payload — typically includes:
                - record_id: int
                - data: Dict (for create/update)
                - changes: Dict (for update, field-level diffs)
                - user_id: int
            runtime: CentralizedRuntime instance for dispatch.

        Returns:
            List of results from each dispatched hook.
        """
        hooks = self._get_hooks(record_ref, event)
        if not hooks:
            return []

        results: List[Dict[str, Any]] = []

        for hook in hooks:
            try:
                if runtime:
                    result = runtime.dispatch(hook.target_ref, inputs=payload)
                    results.append({
                        "hook": hook.target_ref,
                        "status": "success",
                        "result": result,
                    })
                else:
                    logger.debug(
                        f"No runtime — skipping hook dispatch: "
                        f"{hook.target_ref} for {record_ref}.{event}"
                    )
                    results.append({
                        "hook": hook.target_ref,
                        "status": "skipped",
                        "reason": "no_runtime",
                    })
            except Exception as e:
                logger.error(f"Hook failed: {hook.target_ref} for {record_ref}.{event}: {e}")
                results.append({
                    "hook": hook.target_ref,
                    "status": "error",
                    "error": str(e),
                })

        return results

    async def fire_async(
        self,
        record_ref: str,
        event: str,
        payload: Dict[str, Any],
        runtime=None,
    ) -> List[Dict[str, Any]]:
        """
        Fire hooks asynchronously. Hooks with async_dispatch=True
        are dispatched via Celery (fire-and-forget).
        """
        hooks = self._get_hooks(record_ref, event)
        if not hooks:
            return []

        results: List[Dict[str, Any]] = []

        for hook in hooks:
            try:
                if hook.async_dispatch:
                    # TODO: Dispatch via Celery when Task 3.10 is implemented
                    logger.debug(f"Async dispatch (Celery): {hook.target_ref}")
                    results.append({
                        "hook": hook.target_ref,
                        "status": "async_dispatched",
                    })
                elif runtime:
                    result = runtime.dispatch(hook.target_ref, inputs=payload)
                    results.append({
                        "hook": hook.target_ref,
                        "status": "success",
                        "result": result,
                    })
                else:
                    results.append({
                        "hook": hook.target_ref,
                        "status": "skipped",
                        "reason": "no_runtime",
                    })
            except Exception as e:
                logger.error(f"Async hook failed: {hook.target_ref}: {e}")
                results.append({
                    "hook": hook.target_ref,
                    "status": "error",
                    "error": str(e),
                })

        return results

    def _get_hooks(self, record_ref: str, event: str) -> List[RecordHook]:
        """Get all hooks for a record + event combination."""
        record_hooks = self._hooks.get(record_ref, {})
        return record_hooks.get(event, [])

    def get_hooks_for_record(self, record_ref: str) -> Dict[str, List[RecordHook]]:
        """Get all hooks for a record (all events)."""
        return dict(self._hooks.get(record_ref, {}))

    def get_all_hooks(self) -> Dict[str, Dict[str, List[RecordHook]]]:
        """Get the complete hook registry."""
        return dict(self._hooks)

    @property
    def hook_count(self) -> int:
        """Total number of registered hooks."""
        return sum(
            len(hooks)
            for events in self._hooks.values()
            for hooks in events.values()
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_event_manager: Optional[RecordEventManager] = None


def get_record_event_manager() -> RecordEventManager:
    """Get or create the global RecordEventManager singleton."""
    global _event_manager
    if _event_manager is None:
        _event_manager = RecordEventManager()
    return _event_manager


def register_record_hooks_from_registry() -> int:
    """
    Scan the object registry for all @record objects and register
    their Meta event hooks with the RecordEventManager.

    Call this during startup after all records have been scanned.

    Returns:
        Total hooks registered.
    """
    from appos.engine.registry import object_registry

    manager = get_record_event_manager()
    total = 0

    for obj_ref, reg_obj in object_registry._objects.items():
        if reg_obj.object_type != "record":
            continue

        meta = reg_obj.metadata or {}
        hook_config = {}

        for event_key in ("on_create", "on_update", "on_delete"):
            targets = meta.get(event_key, [])
            if targets:
                hook_config[event_key] = targets

        if hook_config:
            count = manager.register_hooks(
                record_ref=obj_ref,
                hook_config=hook_config,
                app_name=reg_obj.app_name or "",
            )
            total += count

    logger.info(f"Registered {total} record event hooks from registry")
    return total
