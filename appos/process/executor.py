"""
AppOS Process Executor — Celery-based process step execution engine.

Executes @process definitions by:
1. Creating a ProcessInstance record in DB
2. Iterating through steps (sequentially or parallel via Celery group)
3. Executing each step's expression rule via engine.dispatch()
4. Logging step results to process_step_log table
5. Managing process state (running → completed/failed)

Celery Tasks:
    - execute_process_step: runs a single step, triggers next
    - start_process_async: creates instance + kicks off first step

Design refs: AppOS_Design.md §11 (Process Engine), §5.9 (Process)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from celery import Celery, group as celery_group

logger = logging.getLogger("appos.process.executor")


# ---------------------------------------------------------------------------
# Celery app (configured at startup from platform config)
# ---------------------------------------------------------------------------

_celery_app: Optional[Celery] = None


def get_celery_app() -> Celery:
    """Get or create the Celery app singleton."""
    global _celery_app
    if _celery_app is None:
        _celery_app = _create_celery_app()
    return _celery_app


def _create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    try:
        from appos.engine.config import load_platform_config
        config = load_platform_config()
        broker = config.celery.broker
        backend = config.celery.result_backend
    except Exception:
        broker = "redis://localhost:6379/0"
        backend = "redis://localhost:6379/1"

    app = Celery("appos", broker=broker, backend=backend)

    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_default_queue="process_steps",
        task_routes={
            "appos.process.executor.execute_process_step_task": {"queue": "process_steps"},
            "appos.process.executor.start_process_task": {"queue": "process_steps"},
        },
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )

    return app


def init_celery(broker: Optional[str] = None, backend: Optional[str] = None) -> Celery:
    """
    Initialize the Celery app with custom config (called from runtime.startup).

    Args:
        broker: Redis broker URL. Defaults to config.
        backend: Redis result backend URL. Defaults to config.

    Returns:
        Configured Celery app.
    """
    global _celery_app
    app = get_celery_app()
    if broker:
        app.conf.broker_url = broker
    if backend:
        app.conf.result_backend = backend
    _celery_app = app
    return app


# ---------------------------------------------------------------------------
# Process definition parser — extracts step list from @process handler
# ---------------------------------------------------------------------------

def parse_process_definition(handler: Any) -> Dict[str, Any]:
    """
    Call the @process handler to get its step definitions.

    A @process function returns a list of step() dicts and parallel() groups.
    Example:
        @process
        def onboard_customer():
            return [
                step("validate", rule="validate_customer"),
                step("setup", rule="setup_account"),
                parallel(
                    step("email", rule="send_welcome", fire_and_forget=True),
                    step("notify", rule="notify_sales", fire_and_forget=True),
                ),
            ]

    Returns:
        {"steps": [...], "metadata": {...}}
    """
    try:
        result = handler()
    except TypeError:
        # Handler might need inputs — try with empty dict
        try:
            result = handler(inputs={})
        except Exception:
            result = []

    if isinstance(result, list):
        return {"steps": result}
    if isinstance(result, dict) and "steps" in result:
        return result
    return {"steps": result if isinstance(result, list) else []}


# ---------------------------------------------------------------------------
# ProcessExecutor — orchestrates full process lifecycle
# ---------------------------------------------------------------------------

class ProcessExecutor:
    """
    Orchestrates process execution: instance creation, step dispatch,
    state management, and completion handling.

    Usage:
        executor = ProcessExecutor(db_session_factory)
        instance = executor.start_process(
            process_ref="crm.processes.onboard_customer",
            inputs={"customer_id": 123},
            user_id=1,
        )
    """

    def __init__(self, db_session_factory=None):
        self._session_factory = db_session_factory

    def start_process(
        self,
        process_ref: str,
        inputs: Dict[str, Any],
        user_id: int = 0,
        async_execution: bool = True,
    ) -> Dict[str, Any]:
        """
        Start a new process instance.

        Args:
            process_ref: Fully-qualified process ref (e.g., "crm.processes.onboard_customer")
            inputs: Initial inputs to the process.
            user_id: ID of the user who started the process.
            async_execution: If True, dispatch steps via Celery. If False, execute synchronously.

        Returns:
            Dict with instance info: {instance_id, status, process_name, ...}
        """
        from appos.engine.registry import object_registry

        # Resolve the process
        registered = object_registry.resolve_or_raise(process_ref)
        if registered.object_type != "process":
            from appos.engine.errors import AppOSDispatchError
            raise AppOSDispatchError(
                f"Expected process, got '{registered.object_type}': {process_ref}",
                object_ref=process_ref,
                object_type=registered.object_type,
            )

        # Parse the process definition (list of steps)
        process_def = parse_process_definition(registered.handler)
        steps = process_def.get("steps", [])
        metadata = registered.metadata or {}

        # Generate instance ID
        instance_id = f"proc_{uuid.uuid4().hex[:12]}"

        # Create ProcessInstance in DB
        instance_data = self._create_instance(
            instance_id=instance_id,
            process_name=metadata.get("name", process_ref.split(".")[-1]),
            app_name=registered.app_name or "",
            display_name=metadata.get("display_name", ""),
            inputs=inputs,
            user_id=user_id,
            triggered_by=process_ref,
        )

        logger.info(
            f"Started process: {process_ref} → instance {instance_id} "
            f"({len(steps)} steps, async={async_execution})"
        )

        if async_execution:
            # Dispatch first step via Celery
            self._dispatch_step_async(instance_id, process_ref, steps, 0)
        else:
            # Execute all steps synchronously
            self._execute_steps_sync(instance_id, process_ref, steps, inputs)

        return instance_data

    def _create_instance(
        self,
        instance_id: str,
        process_name: str,
        app_name: str,
        display_name: str,
        inputs: Dict[str, Any],
        user_id: int,
        triggered_by: str,
    ) -> Dict[str, Any]:
        """Create a ProcessInstance record in the database."""
        if self._session_factory is None:
            # No DB — return in-memory representation
            return {
                "instance_id": instance_id,
                "process_name": process_name,
                "app_name": app_name,
                "status": "running",
                "inputs": inputs,
            }

        from appos.db.platform_models import ProcessInstance

        session = self._session_factory()
        try:
            instance = ProcessInstance(
                instance_id=instance_id,
                process_name=process_name,
                app_name=app_name,
                display_name=display_name,
                status="running",
                inputs=inputs,
                variables={},
                variable_visibility={},
                started_by=user_id,
                triggered_by=triggered_by,
            )
            session.add(instance)
            session.commit()

            return {
                "instance_id": instance_id,
                "id": instance.id,
                "process_name": process_name,
                "app_name": app_name,
                "status": "running",
                "started_at": instance.started_at.isoformat() if instance.started_at else None,
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create process instance: {e}")
            raise
        finally:
            session.close()

    def _dispatch_step_async(
        self,
        instance_id: str,
        process_ref: str,
        steps: List[Dict[str, Any]],
        step_index: int,
    ) -> None:
        """Dispatch a step for async execution via Celery."""
        if step_index >= len(steps):
            self._complete_process(instance_id)
            return

        step_def = steps[step_index]

        if step_def.get("type") == "parallel":
            # Parallel group — dispatch all sub-steps concurrently
            tasks = []
            for sub_step in step_def.get("steps", []):
                tasks.append(
                    execute_process_step_task.s(
                        instance_id=instance_id,
                        process_ref=process_ref,
                        step_def=sub_step,
                        step_index=step_index,
                        total_steps=len(steps),
                        is_parallel=True,
                    )
                )
            if tasks:
                job = celery_group(tasks)
                result = job.apply_async()
                # After parallel completes, trigger next step
                # Note: In production, use chord() for callback after group
                logger.info(
                    f"Dispatched parallel group ({len(tasks)} tasks) "
                    f"for instance {instance_id}"
                )
        else:
            # Sequential step
            execute_process_step_task.delay(
                instance_id=instance_id,
                process_ref=process_ref,
                step_def=step_def,
                step_index=step_index,
                total_steps=len(steps),
                is_parallel=False,
            )

    def _execute_steps_sync(
        self,
        instance_id: str,
        process_ref: str,
        steps: List[Dict[str, Any]],
        inputs: Dict[str, Any],
    ) -> None:
        """Execute all steps synchronously (for non-Celery mode)."""
        from appos.engine.context import ProcessContext

        ctx = ProcessContext(
            instance_id=instance_id,
            inputs=inputs,
        )

        for i, step_def in enumerate(steps):
            if step_def.get("type") == "parallel":
                # Execute parallel steps sequentially in sync mode
                for sub_step in step_def.get("steps", []):
                    self._execute_single_step(instance_id, process_ref, sub_step, ctx, is_parallel=True)
            else:
                self._execute_single_step(instance_id, process_ref, step_def, ctx, is_parallel=False)

        # All steps done — complete the process
        self._complete_process(instance_id, outputs=ctx.outputs())

    def _execute_single_step(
        self,
        instance_id: str,
        process_ref: str,
        step_def: Dict[str, Any],
        ctx: Any,
        is_parallel: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a single step: resolve rule → dispatch → log result.

        Returns:
            Step result dict or None on failure.
        """
        step_name = step_def.get("name", "unnamed")
        rule_ref = step_def.get("rule", "")
        input_mapping = step_def.get("input_mapping", {})
        output_mapping = step_def.get("output_mapping", {})
        retry_count = step_def.get("retry_count", 0)
        retry_delay = step_def.get("retry_delay", 5)
        condition = step_def.get("condition")
        fire_and_forget = step_def.get("fire_and_forget", False)

        # Update current step in instance
        self._update_instance_step(instance_id, step_name)

        # Check condition (if any)
        if condition:
            try:
                # Evaluate condition against process variables
                cond_result = eval(condition, {"ctx": ctx})  # noqa: S307 - controlled eval
                if not cond_result:
                    self._log_step(
                        instance_id, step_name, rule_ref,
                        status="skipped", is_parallel=is_parallel,
                    )
                    logger.info(f"Step '{step_name}' skipped (condition not met)")
                    return None
            except Exception:
                pass  # If condition eval fails, proceed with the step

        # Resolve inputs from process context
        step_inputs = {}
        if input_mapping:
            for rule_param, ctx_var in input_mapping.items():
                step_inputs[rule_param] = ctx.var(ctx_var) if hasattr(ctx, 'var') else ctx._variables.get(ctx_var)
        else:
            # Default: pass all inputs
            step_inputs = ctx.inputs if hasattr(ctx, 'inputs') else {}

        # Execute with retry
        start_time = time.monotonic()
        last_error = None

        for attempt in range(retry_count + 1):
            try:
                # Qualify rule ref with app name if needed
                app_name = process_ref.split(".")[0] if "." in process_ref else ""
                full_rule_ref = rule_ref
                if app_name and "." not in rule_ref:
                    full_rule_ref = f"{app_name}.rules.{rule_ref}"
                elif app_name and rule_ref.count(".") == 0:
                    full_rule_ref = f"{app_name}.rules.{rule_ref}"

                # Dispatch to the rule via engine
                from appos.engine.runtime import get_runtime
                runtime = get_runtime()
                result = runtime.dispatch(full_rule_ref, inputs=step_inputs)

                duration_ms = (time.monotonic() - start_time) * 1000

                # Map outputs back to process context
                if output_mapping and isinstance(result, dict):
                    for rule_output, ctx_var in output_mapping.items():
                        if rule_output in result:
                            ctx.var(ctx_var, result[rule_output])

                # Persist context to DB
                self._persist_context(instance_id, ctx)

                # Log step completion
                self._log_step(
                    instance_id, step_name, full_rule_ref,
                    status="completed",
                    duration_ms=duration_ms,
                    inputs=step_inputs if step_def.get("log_inputs", False) else None,
                    outputs=result if step_def.get("log_outputs", False) else None,
                    attempt=attempt + 1,
                    is_fire_and_forget=fire_and_forget,
                    is_parallel=is_parallel,
                )

                logger.info(
                    f"Step '{step_name}' completed in {duration_ms:.1f}ms "
                    f"(attempt {attempt + 1})"
                )
                return result

            except Exception as e:
                last_error = e
                duration_ms = (time.monotonic() - start_time) * 1000

                if attempt < retry_count:
                    logger.warning(
                        f"Step '{step_name}' failed (attempt {attempt + 1}/{retry_count + 1}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    continue

                # Final attempt failed
                self._log_step(
                    instance_id, step_name, full_rule_ref,
                    status="failed",
                    duration_ms=duration_ms,
                    error_info={"error": str(e), "type": type(e).__name__},
                    attempt=attempt + 1,
                    is_fire_and_forget=fire_and_forget,
                    is_parallel=is_parallel,
                )

                on_error = step_def.get("on_error", "fail")
                if on_error == "fail":
                    self._fail_process(instance_id, str(e))
                    raise
                elif on_error == "skip":
                    logger.warning(f"Step '{step_name}' failed but on_error=skip: {e}")
                    return None
                elif on_error == "continue":
                    logger.warning(f"Step '{step_name}' failed but on_error=continue: {e}")
                    return None

        return None

    # -------------------------------------------------------------------
    # DB operations
    # -------------------------------------------------------------------

    def _update_instance_step(self, instance_id: str, step_name: str) -> None:
        """Update current_step on the ProcessInstance."""
        if not self._session_factory:
            return
        from appos.db.platform_models import ProcessInstance
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if instance:
                instance.current_step = step_name
                instance.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update instance step: {e}")
        finally:
            session.close()

    def _persist_context(self, instance_id: str, ctx: Any) -> None:
        """Persist process context variables to DB."""
        if not self._session_factory or not getattr(ctx, 'is_dirty', False):
            return
        from appos.db.platform_models import ProcessInstance
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if instance:
                instance.variables = ctx.get_persistable_variables()
                instance.variable_visibility = ctx.visibility
                instance.updated_at = datetime.now(timezone.utc)
                session.commit()
                ctx.mark_clean()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist process context: {e}")
        finally:
            session.close()

    def _log_step(
        self,
        instance_id: str,
        step_name: str,
        rule_ref: str,
        status: str,
        duration_ms: float = 0,
        inputs: Optional[Dict] = None,
        outputs: Optional[Dict] = None,
        error_info: Optional[Dict] = None,
        attempt: int = 1,
        is_fire_and_forget: bool = False,
        is_parallel: bool = False,
    ) -> None:
        """Log a step execution to the process_step_log table."""
        if not self._session_factory:
            return
        from appos.db.platform_models import ProcessStepLog, ProcessInstance
        session = self._session_factory()
        try:
            # Get the integer PK from the instance
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if not instance:
                return

            log_entry = ProcessStepLog(
                process_instance_id=instance.id,
                step_name=step_name,
                rule_ref=rule_ref,
                status=status,
                duration_ms=duration_ms,
                inputs=inputs,
                outputs=outputs,
                error_info=error_info,
                attempt=attempt,
                is_fire_and_forget=is_fire_and_forget,
                is_parallel=is_parallel,
            )
            if status in ("completed", "failed", "skipped"):
                log_entry.completed_at = datetime.now(timezone.utc)

            session.add(log_entry)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log process step: {e}")
        finally:
            session.close()

    def _complete_process(
        self, instance_id: str, outputs: Optional[Dict] = None
    ) -> None:
        """Mark a process instance as completed."""
        if not self._session_factory:
            return
        from appos.db.platform_models import ProcessInstance
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if instance:
                instance.status = "completed"
                instance.completed_at = datetime.now(timezone.utc)
                instance.updated_at = datetime.now(timezone.utc)
                if outputs:
                    instance.outputs = outputs
                session.commit()
                logger.info(f"Process {instance_id} completed")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to complete process: {e}")
        finally:
            session.close()

    def _fail_process(self, instance_id: str, error: str) -> None:
        """Mark a process instance as failed."""
        if not self._session_factory:
            return
        from appos.db.platform_models import ProcessInstance
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if instance:
                instance.status = "failed"
                instance.completed_at = datetime.now(timezone.utc)
                instance.updated_at = datetime.now(timezone.utc)
                instance.error_info = {"error": error}
                session.commit()
                logger.info(f"Process {instance_id} failed: {error}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to mark process as failed: {e}")
        finally:
            session.close()

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get process instance details."""
        if not self._session_factory:
            return None
        from appos.db.platform_models import ProcessInstance
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if not instance:
                return None
            return {
                "instance_id": instance.instance_id,
                "process_name": instance.process_name,
                "app_name": instance.app_name,
                "display_name": instance.display_name,
                "status": instance.status,
                "current_step": instance.current_step,
                "inputs": instance.inputs,
                "variables": instance.variables,
                "outputs": instance.outputs,
                "error_info": instance.error_info,
                "started_at": instance.started_at.isoformat() if instance.started_at else None,
                "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            }
        finally:
            session.close()

    def get_step_history(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get step execution history for a process instance."""
        if not self._session_factory:
            return []
        from appos.db.platform_models import ProcessInstance, ProcessStepLog
        session = self._session_factory()
        try:
            instance = (
                session.query(ProcessInstance)
                .filter(ProcessInstance.instance_id == instance_id)
                .first()
            )
            if not instance:
                return []

            steps = (
                session.query(ProcessStepLog)
                .filter(ProcessStepLog.process_instance_id == instance.id)
                .order_by(ProcessStepLog.started_at)
                .all()
            )
            return [
                {
                    "step_name": s.step_name,
                    "rule_ref": s.rule_ref,
                    "status": s.status,
                    "duration_ms": float(s.duration_ms) if s.duration_ms else None,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "attempt": s.attempt,
                    "is_parallel": s.is_parallel,
                    "is_fire_and_forget": s.is_fire_and_forget,
                    "error_info": s.error_info,
                }
                for s in steps
            ]
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

celery_app = get_celery_app()


@celery_app.task(bind=True, name="appos.process.executor.execute_process_step_task")
def execute_process_step_task(
    self,
    instance_id: str,
    process_ref: str,
    step_def: Dict[str, Any],
    step_index: int,
    total_steps: int,
    is_parallel: bool = False,
) -> Dict[str, Any]:
    """
    Celery task: execute a single process step.

    Called by ProcessExecutor._dispatch_step_async().
    After completion, triggers the next step (unless parallel).
    """
    from appos.engine.context import ProcessContext

    executor = get_process_executor()

    # Load current process variables from DB
    instance_data = executor.get_instance(instance_id)
    if instance_data is None:
        logger.error(f"Process instance not found: {instance_id}")
        return {"status": "error", "message": "Instance not found"}

    ctx = ProcessContext(
        instance_id=instance_id,
        inputs=instance_data.get("inputs", {}),
        variables=instance_data.get("variables", {}),
    )

    try:
        result = executor._execute_single_step(
            instance_id=instance_id,
            process_ref=process_ref,
            step_def=step_def,
            ctx=ctx,
            is_parallel=is_parallel,
        )

        # Trigger next step (if sequential, not parallel)
        if not is_parallel and step_index + 1 < total_steps:
            # Re-parse the process to get next step
            from appos.engine.registry import object_registry
            registered = object_registry.resolve(process_ref)
            if registered and registered.handler:
                process_def = parse_process_definition(registered.handler)
                steps = process_def.get("steps", [])
                executor._dispatch_step_async(
                    instance_id, process_ref, steps, step_index + 1
                )
        elif not is_parallel and step_index + 1 >= total_steps:
            # Last step — complete the process
            executor._complete_process(instance_id, outputs=ctx.outputs())

        return {"status": "completed", "step": step_def.get("name")}

    except Exception as e:
        logger.error(f"Step execution failed: {e}")
        return {"status": "failed", "step": step_def.get("name"), "error": str(e)}


@celery_app.task(name="appos.process.executor.start_process_task")
def start_process_task(
    process_ref: str,
    inputs: Dict[str, Any],
    user_id: int = 0,
) -> Dict[str, Any]:
    """
    Celery task: start a process asynchronously.

    Can be used from Web APIs with async=True mode.
    """
    executor = get_process_executor()
    return executor.start_process(
        process_ref=process_ref,
        inputs=inputs,
        user_id=user_id,
        async_execution=True,
    )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_process_executor: Optional[ProcessExecutor] = None


def get_process_executor() -> ProcessExecutor:
    """Get or create the global ProcessExecutor singleton."""
    global _process_executor
    if _process_executor is None:
        # Try to get DB session factory from runtime
        db_session_factory = None
        try:
            from appos.engine.runtime import get_runtime
            runtime = get_runtime()
            db_session_factory = runtime._db_session_factory
        except Exception:
            pass
        _process_executor = ProcessExecutor(db_session_factory=db_session_factory)
    return _process_executor


def init_process_executor(db_session_factory=None) -> ProcessExecutor:
    """Initialize the process executor with a specific DB session factory."""
    global _process_executor
    _process_executor = ProcessExecutor(db_session_factory=db_session_factory)
    return _process_executor
