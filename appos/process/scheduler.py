"""
AppOS Process Scheduler — event triggers and Celery Beat integration.

Responsibilities:
1. Event-based triggers: listen for record events / custom events →
   auto-start processes that declared matching triggers
2. Cron-based triggers: register schedule() triggers with Celery Beat
3. Manual trigger API: start_by_event() / start_by_schedule()

Design ref: AppOS_Design.md §11 (Process Engine — Starting a Process)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("appos.process.scheduler")


# ---------------------------------------------------------------------------
# Event trigger registry
# ---------------------------------------------------------------------------

class EventTriggerRegistry:
    """
    Maps event names → list of (process_ref, filter_fn) that should start
    when that event fires.

    Example:
        @process(triggers=[event("customer.created"), event("order.submitted")])
        def onboard_customer(): ...

    The registry is populated at startup by scanning all registered processes.
    """

    def __init__(self) -> None:
        self._triggers: Dict[str, List[Tuple[str, Optional[Callable]]]] = {}

    def register(
        self,
        event_name: str,
        process_ref: str,
        filter_fn: Optional[Callable] = None,
    ) -> None:
        """Register a process to be triggered by an event."""
        if event_name not in self._triggers:
            self._triggers[event_name] = []

        # Deduplicate
        existing = {ref for ref, _ in self._triggers[event_name]}
        if process_ref not in existing:
            self._triggers[event_name].append((process_ref, filter_fn))
            logger.debug(f"Registered event trigger: {event_name} → {process_ref}")

    def unregister(self, event_name: str, process_ref: str) -> None:
        """Remove a specific process trigger for an event."""
        if event_name in self._triggers:
            self._triggers[event_name] = [
                (ref, fn) for ref, fn in self._triggers[event_name]
                if ref != process_ref
            ]

    def get_triggers(self, event_name: str) -> List[Tuple[str, Optional[Callable]]]:
        """Get all process refs registered for a given event."""
        return self._triggers.get(event_name, [])

    def get_all_events(self) -> List[str]:
        """Get names of all registered events."""
        return list(self._triggers.keys())

    def clear(self) -> None:
        """Clear all triggers."""
        self._triggers.clear()

    @property
    def count(self) -> int:
        return sum(len(v) for v in self._triggers.values())


# Singleton
_event_registry = EventTriggerRegistry()


def get_event_registry() -> EventTriggerRegistry:
    """Get the global event trigger registry."""
    return _event_registry


# ---------------------------------------------------------------------------
# Schedule trigger registry (Celery Beat)
# ---------------------------------------------------------------------------

class ScheduleTriggerRegistry:
    """
    Maps cron expressions → process refs for Celery Beat scheduling.

    Example:
        @process(triggers=[schedule("0 2 * * *")])  # 2am daily
        def nightly_cleanup(): ...

    Populates Celery Beat schedule at startup.
    """

    def __init__(self) -> None:
        self._schedules: List[Dict[str, Any]] = []

    def register(
        self,
        process_ref: str,
        cron_expression: str,
        timezone_str: str = "UTC",
        enabled: bool = True,
    ) -> None:
        """Register a cron-based process trigger."""
        self._schedules.append({
            "process_ref": process_ref,
            "cron": cron_expression,
            "timezone": timezone_str,
            "enabled": enabled,
        })
        logger.debug(
            f"Registered schedule trigger: {cron_expression} ({timezone_str}) → {process_ref}"
        )

    def unregister(self, process_ref: str) -> None:
        """Remove all schedule triggers for a process."""
        self._schedules = [
            s for s in self._schedules if s["process_ref"] != process_ref
        ]

    def get_schedules(self) -> List[Dict[str, Any]]:
        """Get all registered schedules."""
        return list(self._schedules)

    def get_enabled_schedules(self) -> List[Dict[str, Any]]:
        """Get only enabled schedules."""
        return [s for s in self._schedules if s.get("enabled", True)]

    def clear(self) -> None:
        self._schedules.clear()

    @property
    def count(self) -> int:
        return len(self._schedules)


# Singleton
_schedule_registry = ScheduleTriggerRegistry()


def get_schedule_registry() -> ScheduleTriggerRegistry:
    """Get the global schedule trigger registry."""
    return _schedule_registry


# ---------------------------------------------------------------------------
# ProcessScheduler — coordinates triggers + Celery Beat
# ---------------------------------------------------------------------------

class ProcessScheduler:
    """
    Top-level orchestrator that:
    1. Scans the object registry for @process with triggers
    2. Populates event + schedule registries
    3. Configures Celery Beat with cron schedules
    4. Provides fire_event() to trigger process starts
    """

    def __init__(self) -> None:
        self.event_registry = get_event_registry()
        self.schedule_registry = get_schedule_registry()
        self._initialized = False

    def initialize(self) -> None:
        """
        Scan all registered processes and populate trigger registries.
        Called during runtime startup.
        """
        if self._initialized:
            return

        from appos.engine.registry import object_registry

        process_count = 0
        event_count = 0
        schedule_count = 0

        for obj_ref, registered in object_registry._objects.items():
            if registered.object_type != "process":
                continue

            process_count += 1
            meta = registered.metadata or {}
            triggers = meta.get("triggers", [])

            for trigger in triggers:
                if not isinstance(trigger, dict):
                    continue

                trigger_type = trigger.get("type")

                if trigger_type == "event":
                    event_name = trigger.get("event", "")
                    if event_name:
                        self.event_registry.register(event_name, obj_ref)
                        event_count += 1

                elif trigger_type == "schedule":
                    cron_expr = trigger.get("cron", "")
                    tz = trigger.get("timezone", "UTC")
                    if cron_expr:
                        self.schedule_registry.register(
                            process_ref=obj_ref,
                            cron_expression=cron_expr,
                            timezone_str=tz,
                        )
                        schedule_count += 1

        self._initialized = True
        logger.info(
            f"ProcessScheduler initialized: {process_count} processes, "
            f"{event_count} event triggers, {schedule_count} schedule triggers"
        )

    def fire_event(
        self,
        event_name: str,
        event_data: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        async_execution: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fire a named event — starts all processes registered for it.

        Args:
            event_name: The event name (e.g., "customer.created").
            event_data: Data to pass as inputs to triggered processes.
            user_id: ID of user who triggered the event (0 for system).
            async_execution: If True, dispatch via Celery.

        Returns:
            List of started instance dicts.
        """
        triggers = self.event_registry.get_triggers(event_name)
        if not triggers:
            logger.debug(f"No triggers registered for event: {event_name}")
            return []

        from appos.process.executor import get_process_executor
        executor = get_process_executor()

        started = []
        for process_ref, filter_fn in triggers:
            # Apply optional filter function
            if filter_fn and not filter_fn(event_data):
                logger.debug(
                    f"Filter blocked trigger: {event_name} → {process_ref}"
                )
                continue

            try:
                instance = executor.start_process(
                    process_ref=process_ref,
                    inputs=event_data or {},
                    user_id=user_id,
                    async_execution=async_execution,
                )
                started.append(instance)
                logger.info(
                    f"Event '{event_name}' triggered process: {process_ref} "
                    f"→ {instance.get('instance_id', 'unknown')}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to start process {process_ref} from event "
                    f"'{event_name}': {e}"
                )

        return started

    def configure_celery_beat(self) -> Dict[str, Any]:
        """
        Generate Celery Beat schedule config from registered schedule triggers.

        Returns:
            Dict suitable for celery_app.conf.beat_schedule.
        """
        beat_schedule: Dict[str, Any] = {}

        for sched in self.schedule_registry.get_enabled_schedules():
            process_ref = sched["process_ref"]
            cron_expr = sched["cron"]
            tz = sched.get("timezone", "UTC")

            # Parse cron expression: "minute hour day_of_month month_of_year day_of_week"
            parts = cron_expr.strip().split()
            if len(parts) < 5:
                logger.warning(
                    f"Invalid cron expression for {process_ref}: {cron_expr}"
                )
                continue

            from celery.schedules import crontab

            schedule_name = f"process-{process_ref.replace('.', '-')}"
            beat_schedule[schedule_name] = {
                "task": "appos.process.scheduler.scheduled_process_task",
                "schedule": crontab(
                    minute=parts[0],
                    hour=parts[1],
                    day_of_month=parts[2],
                    month_of_year=parts[3],
                    day_of_week=parts[4],
                ),
                "args": (process_ref,),
                "options": {"queue": "scheduled"},
            }

            logger.debug(
                f"Celery Beat schedule: {schedule_name} = {cron_expr} ({tz})"
            )

        return beat_schedule

    def apply_celery_beat_config(self) -> int:
        """
        Apply schedule triggers to the Celery app's Beat config.

        Returns:
            Number of schedules configured.
        """
        beat_schedule = self.configure_celery_beat()
        if not beat_schedule:
            return 0

        from appos.process.executor import get_celery_app
        celery_app = get_celery_app()
        celery_app.conf.beat_schedule = beat_schedule
        logger.info(f"Applied {len(beat_schedule)} Celery Beat schedules")
        return len(beat_schedule)


# ---------------------------------------------------------------------------
# Celery task for scheduled process execution
# ---------------------------------------------------------------------------

def _get_celery_app():
    from appos.process.executor import get_celery_app
    return get_celery_app()


# Lazy-bind the task (avoids circular import at module level)
_scheduled_task = None


def get_scheduled_task():
    """Get or create the scheduled process Celery task."""
    global _scheduled_task
    if _scheduled_task is None:
        celery_app = _get_celery_app()

        @celery_app.task(name="appos.process.scheduler.scheduled_process_task")
        def scheduled_process_task(process_ref: str) -> Dict[str, Any]:
            """
            Celery Beat task: start a process on schedule.

            Called by Celery Beat according to the cron schedule
            configured via ProcessScheduler.apply_celery_beat_config().
            """
            from appos.process.executor import get_process_executor
            executor = get_process_executor()

            try:
                instance = executor.start_process(
                    process_ref=process_ref,
                    inputs={"triggered_by": "schedule", "timestamp": datetime.now(timezone.utc).isoformat()},
                    user_id=0,  # system user for scheduled tasks
                    async_execution=True,
                )
                logger.info(f"Scheduled process started: {process_ref}")
                return instance
            except Exception as e:
                logger.error(f"Scheduled process failed to start: {process_ref}: {e}")
                return {"error": str(e)}

        _scheduled_task = scheduled_process_task
    return _scheduled_task


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[ProcessScheduler] = None


def get_scheduler() -> ProcessScheduler:
    """Get or create the global ProcessScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ProcessScheduler()
    return _scheduler


def init_scheduler() -> ProcessScheduler:
    """Initialize the scheduler: scan processes, apply Beat config."""
    scheduler = get_scheduler()
    scheduler.initialize()
    scheduler.apply_celery_beat_config()
    # Ensure the scheduled task is registered
    get_scheduled_task()
    return scheduler
