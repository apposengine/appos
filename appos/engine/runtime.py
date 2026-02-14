"""
AppOS Centralized Runtime Engine — Single source of truth for all runtime data.

Ties together:
- DependencyGraph (NetworkX)
- AsyncLogQueue (file-based logging)
- SecurityPolicy (permission checking)
- ObjectRegistryManager (object resolution)
- PermissionCache (Redis)
- Session store (Redis)

Provides:
- engine.dispatch() — unified dispatcher for any executable object
- engine.log_execution() / engine.log_dependency_access()
- engine.query_for_ai() — AI-readable runtime queries
- engine.startup() / engine.shutdown() — lifecycle management

Design refs: AppOS_Design.md §8
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from appos.engine.cache import (
    PermissionCache,
    RedisCache,
    create_object_cache,
    create_permission_cache,
    create_rate_limiter,
    create_session_store,
)
from appos.engine.context import (
    ExecutionContext,
    get_execution_context,
    require_execution_context,
    set_execution_context,
)
from appos.engine.dependency import DependencyGraph
from appos.engine.errors import AppOSDispatchError, AppOSError
from appos.engine.logging import (
    AsyncLogQueue,
    FileLogger,
    LogEntry,
    LogRetentionManager,
    init_logging,
    log,
    log_rule_execution,
    log_rule_performance,
    log_system_event,
    shutdown_logging,
)
from appos.engine.namespaces import (
    CrossAppNamespace,
    SecureAutoImportNamespace,
    build_app_namespaces,
)
from appos.engine.registry import ObjectRegistryManager, object_registry
from appos.engine.security import AuthService, SecurityPolicy

logger = logging.getLogger("appos.engine.runtime")

# Lazy import to avoid circular dependency at module level
_integration_executor = None


class CentralizedRuntime:
    """
    Single entry point for all runtime operations.

    Lifecycle:
        runtime = CentralizedRuntime(config)
        runtime.startup()   # init subsystems
        ...
        runtime.shutdown()  # flush & cleanup
    """

    def __init__(
        self,
        log_dir: str = "logs",
        dependency_dir: str = ".appos/runtime/dependencies",
        redis_url: str = "redis://localhost:6379",
        db_session_factory=None,
        flush_interval_ms: int = 100,
        flush_batch_size: int = 50,
    ):
        self._log_dir = log_dir
        self._dependency_dir = dependency_dir
        self._redis_url = redis_url
        self._db_session_factory = db_session_factory
        self._flush_interval_ms = flush_interval_ms
        self._flush_batch_size = flush_batch_size

        # Subsystems (initialized in startup())
        self.registry: ObjectRegistryManager = object_registry
        self.dependency_graph: Optional[DependencyGraph] = None
        self.security: Optional[SecurityPolicy] = None
        self.auth: Optional[AuthService] = None
        self.log_queue: Optional[AsyncLogQueue] = None
        self.permission_cache: Optional[PermissionCache] = None
        self.session_store: Optional[RedisCache] = None
        self.object_cache: Optional[RedisCache] = None
        self.rate_limiter: Optional[RedisCache] = None
        self.retention_manager: Optional[LogRetentionManager] = None
        self.integration_executor = None  # IntegrationExecutor — set in startup()

        self._started = False

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def startup(self) -> None:
        """Initialize all subsystems."""
        if self._started:
            logger.warning("Runtime already started")
            return

        logger.info("Starting AppOS Runtime Engine...")

        # 1. Dependency graph
        self.dependency_graph = DependencyGraph(
            persistence_dir=self._dependency_dir,
            db_session_factory=self._db_session_factory,
        )
        self.dependency_graph.load()

        # 2. Logging
        self.log_queue = init_logging(
            log_dir=self._log_dir,
            flush_interval_ms=self._flush_interval_ms,
            flush_batch_size=self._flush_batch_size,
        )

        # 3. Redis caches
        try:
            self.permission_cache = create_permission_cache(self._redis_url)
            self.session_store = create_session_store(self._redis_url)
            self.object_cache = create_object_cache(self._redis_url)
            self.rate_limiter = create_rate_limiter(self._redis_url)
        except Exception as e:
            logger.warning(f"Redis connection failed (running without cache): {e}")

        # 4. Security
        self.security = SecurityPolicy(
            permission_cache=self.permission_cache,
            db_session_factory=self._db_session_factory,
        )

        # 5. Auth service
        if self.session_store and self._db_session_factory:
            self.auth = AuthService(
                session_store=self.session_store,
                db_session_factory=self._db_session_factory,
            )

        # 6. Log retention
        self.retention_manager = LogRetentionManager(log_dir=self._log_dir)

        # 7. Integration executor (outbound HTTP via httpx)
        from appos.engine.integration_executor import IntegrationExecutor
        self.integration_executor = IntegrationExecutor(
            registry=self.registry,
            db_session_factory=self._db_session_factory,
            log_queue=self.log_queue,
        )

        self._started = True
        log(log_system_event("platform_started", details={"subsystems": self._subsystem_status()}))
        logger.info("AppOS Runtime Engine started successfully")

    def shutdown(self) -> None:
        """Flush all queues, persist state, close connections."""
        if not self._started:
            return

        logger.info("Shutting down AppOS Runtime Engine...")

        # 1. Persist dependency graph
        if self.dependency_graph:
            written = self.dependency_graph.persist_all()
            logger.info(f"Persisted {written} dependency files")

        # 2. Close httpx clients (integration executor)
        if self.integration_executor:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.integration_executor.close_all_clients())
                else:
                    loop.run_until_complete(self.integration_executor.close_all_clients())
            except RuntimeError:
                # No event loop — create one for cleanup
                asyncio.run(self.integration_executor.close_all_clients())

        # 3. Flush and stop logging
        log(log_system_event("platform_shutdown"))
        shutdown_logging()

        self._started = False
        logger.info("AppOS Runtime Engine shut down")

    # -----------------------------------------------------------------------
    # Dispatch — Unified object execution
    # -----------------------------------------------------------------------

    def dispatch(
        self,
        object_ref: str,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Unified dispatcher — resolves any object reference and executes it.

        Detects whether the ref points to an expression_rule, process, or integration
        and calls the appropriate executor.

        Args:
            object_ref: Fully-qualified object reference (e.g., "crm.rules.validate_customer").
            inputs: Dict of inputs to pass to the resolved object.
            **kwargs: Additional options (async_exec, timeout, etc.).

        Returns:
            Result depends on object type:
            - expression_rule: the rule's output dict
            - process: the ProcessInstance
            - integration: the integration response

        Security: Checks 'use' permission before dispatch.
        """
        resolved = self.registry.resolve(object_ref)

        if resolved is None:
            raise AppOSDispatchError(
                f"Object not found: {object_ref}",
                object_ref=object_ref,
            )

        # Security check
        if self.security:
            self.security.check_permission(object_ref, "use")

        # Log dispatch
        ctx = get_execution_context()
        start_time = time.monotonic()

        try:
            if resolved.object_type == "expression_rule":
                result = self._execute_rule(resolved, inputs or {})
            elif resolved.object_type == "process":
                result = self._start_process(resolved, inputs or {}, **kwargs)
            elif resolved.object_type == "integration":
                result = self._execute_integration(resolved, inputs or {})
            elif resolved.object_type == "web_api":
                # Web APIs are normally invoked via HTTP, but can also be
                # dispatched internally (e.g., from a process or rule).
                result = self._execute_web_api_handler(resolved, inputs or {})
            elif resolved.object_type == "constant":
                # Constants: resolve value. If object_ref type, dispatch to target.
                result = self._dispatch_constant(resolved, inputs or {}, **kwargs)
            else:
                raise AppOSDispatchError(
                    f"Cannot dispatch to object type '{resolved.object_type}'. "
                    f"Only expression_rule, process, integration, web_api, "
                    f"and constant are dispatchable. Ref: {object_ref}",
                    object_ref=object_ref,
                    object_type=resolved.object_type,
                )

            duration_ms = (time.monotonic() - start_time) * 1000

            # Log execution
            if ctx and self.log_queue:
                entry = log_rule_execution(
                    object_ref=object_ref,
                    execution_id=ctx.execution_id,
                    user_id=ctx.user_id,
                    app=resolved.app_name,
                    duration_ms=duration_ms,
                    success=True,
                )
                self.log_queue.push(entry)

                # Performance log
                perf_entry = log_rule_performance(
                    object_ref=object_ref,
                    execution_id=ctx.execution_id,
                    app=resolved.app_name,
                    duration_ms=duration_ms,
                )
                self.log_queue.push(perf_entry)

            return result

        except AppOSError:
            raise
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            if ctx and self.log_queue:
                entry = log_rule_execution(
                    object_ref=object_ref,
                    execution_id=ctx.execution_id,
                    user_id=ctx.user_id,
                    app=resolved.app_name,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(e),
                )
                self.log_queue.push(entry)
            raise

    def _execute_rule(self, resolved: Any, inputs: Dict[str, Any]) -> Any:
        """Execute an expression rule."""
        handler = resolved.handler
        if handler is None:
            raise AppOSDispatchError(
                f"Rule has no handler: {resolved.object_ref}",
                object_ref=resolved.object_ref,
            )

        from appos.engine.context import RuleContext

        ctx = get_execution_context()
        rule_ctx = RuleContext(inputs=inputs, execution_context=ctx)
        return handler(rule_ctx)

    def _start_process(self, resolved: Any, inputs: Dict[str, Any], **kwargs: Any) -> Any:
        """
        Start a process instance via ProcessExecutor.

        Delegates to Celery-based async execution by default.
        Falls back to synchronous execution if Celery is unavailable.
        """
        handler = resolved.handler
        if handler is None:
            raise AppOSDispatchError(
                f"Process has no handler: {resolved.object_ref}",
                object_ref=resolved.object_ref,
            )

        try:
            from appos.process.executor import get_process_executor
            executor = get_process_executor()
            async_mode = kwargs.pop("async_execution", True)
            user_id = kwargs.pop("user_id", 0)
            return executor.start_process(
                process_ref=resolved.object_ref,
                inputs=inputs,
                user_id=user_id,
                async_execution=async_mode,
            )
        except ImportError:
            # Fallback: direct handler call if executor not available
            return handler(inputs=inputs, **kwargs)

    def _execute_integration(self, resolved: Any, inputs: Dict[str, Any]) -> Any:
        """
        Execute an outbound integration call via IntegrationExecutor.

        Pipeline: Connected System resolution → httpx HTTP call → retry/backoff
        → circuit breaker → response mapping → logging.

        Falls back to direct handler call if IntegrationExecutor is not available.
        """
        if self.integration_executor:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Inside an async context — use await pattern
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            self.integration_executor.execute(resolved, inputs)
                        )
                        return future.result()
                else:
                    return loop.run_until_complete(
                        self.integration_executor.execute(resolved, inputs)
                    )
            except RuntimeError:
                return asyncio.run(
                    self.integration_executor.execute(resolved, inputs)
                )

        # Fallback: direct handler call (no Connected System resolution)
        handler = resolved.handler
        if handler is None:
            raise AppOSDispatchError(
                f"Integration has no handler: {resolved.object_ref}",
                object_ref=resolved.object_ref,
            )
        return handler(inputs=inputs)

    def _execute_web_api_handler(self, resolved: Any, inputs: Dict[str, Any]) -> Any:
        """
        Execute a @web_api's underlying handler when dispatched internally.

        Web APIs are normally invoked via HTTP (through reflex_bridge + api_executor).
        This method allows internal dispatch (e.g., from a process or rule)
        by resolving the web_api config and dispatching to its handler ref.
        """
        api_config = resolved.handler() if callable(resolved.handler) else {}
        handler_ref = api_config.get("handler")
        if not handler_ref:
            raise AppOSDispatchError(
                f"Web API has no handler: {resolved.object_ref}",
                object_ref=resolved.object_ref,
            )

        # Qualify with app name if needed
        app_name = resolved.app_name
        if app_name and "." in handler_ref and not handler_ref.startswith(f"{app_name}."):
            handler_ref = f"{app_name}.{handler_ref}"

        # Dispatch to the underlying handler (rule or process)
        return self.dispatch(handler_ref, inputs=inputs)

    def _dispatch_constant(
        self,
        resolved: Any,
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """
        Dispatch a @constant.

        - Primitive constants (int, float, str, bool): return the resolved value.
        - Object-ref constants: resolve the env-appropriate target ref string,
          then recursively dispatch to the target (rule, process, integration, etc.).

        Design ref: AppOS_Design.md §5.6 (Constant), §8 (Unified Dispatch)
        """
        from appos.decorators.constant import get_constant_manager

        manager = get_constant_manager()
        resolved_const = manager.resolve(resolved.object_ref)

        if resolved_const.is_object_ref and resolved_const.target_ref:
            # Object ref constant — dispatch to the resolved target
            logger.info(
                f"Constant dispatch: {resolved.object_ref} → {resolved_const.target_ref}"
            )
            return self.dispatch(resolved_const.target_ref, inputs=inputs, **kwargs)

        # Primitive constant — just return the value
        return resolved_const.value

    # -----------------------------------------------------------------------
    # Namespace builder — creates app execution scope
    # -----------------------------------------------------------------------

    def build_namespaces(self, app_name: str) -> Dict[str, SecureAutoImportNamespace]:
        """
        Build all auto-import namespaces for an app.
        Returns dict of {object_type: namespace} to inject into execution globals.
        """
        return build_app_namespaces(
            app_name=app_name,
            security_policy=self.security,
            log_queue=self.log_queue,
            dependency_graph=self.dependency_graph,
        )

    def build_cross_app_namespace(self, app_name: str) -> CrossAppNamespace:
        """Build a cross-app namespace for accessing another app's objects."""
        return CrossAppNamespace(
            app_name=app_name,
            security_policy=self.security,
            log_queue=self.log_queue,
            dependency_graph=self.dependency_graph,
        )

    # -----------------------------------------------------------------------
    # Log Cleanup (6.25)
    # -----------------------------------------------------------------------

    def cleanup_logs(self, config=None) -> Dict[str, int]:
        """
        Delete log files older than their retention period.

        Runs nightly via the cleanup_schedule cron or manually from admin.
        Reads retention settings from appos.yaml logging section.

        Returns dict of {category: files_deleted}.
        """
        import os
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        log_root = Path(self._log_dir)
        if not log_root.exists():
            return {}

        # Default retention (days)
        retention = {
            "execution": 90,
            "performance": 30,
            "security": 365,
        }
        if config:
            ret_cfg = getattr(config, "logging", None)
            if ret_cfg:
                r = getattr(ret_cfg, "retention", None)
                if r:
                    retention["execution"] = getattr(r, "execution_days", 90)
                    retention["performance"] = getattr(r, "performance_days", 30)
                    retention["security"] = getattr(r, "security_days", 365)

        now = datetime.now(timezone.utc)
        deleted: Dict[str, int] = {}

        for type_dir in log_root.iterdir():
            if not type_dir.is_dir():
                continue
            for cat_dir in type_dir.iterdir():
                if not cat_dir.is_dir():
                    continue
                category = cat_dir.name
                max_age_days = retention.get(category, 90)
                cutoff = now - timedelta(days=max_age_days)
                count = 0
                for jsonl_file in cat_dir.glob("*.jsonl"):
                    # Parse date from filename (e.g., 2026-02-07.jsonl)
                    try:
                        date_str = jsonl_file.stem
                        file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                        if file_date < cutoff:
                            jsonl_file.unlink()
                            count += 1
                    except (ValueError, OSError):
                        continue
                if count:
                    key = f"{type_dir.name}/{category}"
                    deleted[key] = count

        logger.info(f"Log cleanup: deleted {sum(deleted.values())} files")
        return deleted

    # -----------------------------------------------------------------------
    # ProcessInstance Partitioning (6.26)
    # -----------------------------------------------------------------------

    def create_monthly_partitions(
        self, months_ahead: int = 3, schema: str = "public"
    ) -> List[str]:
        """
        Create monthly partitions for process_instances and
        process_step_log tables.

        In production, these tables should be PARTITION BY RANGE (started_at).
        This method creates future monthly child tables.

        Args:
            months_ahead: How many months of future partitions to create.
            schema: Database schema name.

        Returns:
            List of partition names created.
        """
        if self._db_session_factory is None:
            logger.warning("No DB session factory — cannot create partitions")
            return []

        from datetime import date, timedelta

        from sqlalchemy import text

        created = []
        today = date.today()

        tables = ["process_instances", "process_step_log"]

        session = self._db_session_factory()
        try:
            for month_offset in range(months_ahead + 1):
                # Calculate month start/end
                year = today.year + (today.month + month_offset - 1) // 12
                month = (today.month + month_offset - 1) % 12 + 1
                start = date(year, month, 1)
                if month == 12:
                    end = date(year + 1, 1, 1)
                else:
                    end = date(year, month + 1, 1)

                suffix = start.strftime("%Y_%m")

                for table in tables:
                    partition_name = f"{table}_p{suffix}"
                    # Check if partition already exists
                    check_sql = text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = :schema AND table_name = :name"
                    )
                    exists = session.execute(
                        check_sql, {"schema": schema, "name": partition_name}
                    ).fetchone()

                    if exists:
                        continue

                    # Create partition
                    create_sql = text(
                        f'CREATE TABLE IF NOT EXISTS "{schema}"."{partition_name}" '
                        f"PARTITION OF \"{schema}\".\"{table}\" "
                        f"FOR VALUES FROM ('{start.isoformat()}') "
                        f"TO ('{end.isoformat()}')"
                    )
                    try:
                        session.execute(create_sql)
                        created.append(partition_name)
                        logger.info(f"Created partition: {partition_name}")
                    except Exception as e:
                        # Partition creation may fail if parent isn't partitioned
                        logger.debug(f"Partition skip ({partition_name}): {e}")

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Partition creation failed: {e}")
        finally:
            session.close()

        return created

    # -----------------------------------------------------------------------
    # Process Instance Archival (6.27)
    # -----------------------------------------------------------------------

    def archive_completed_instances(
        self,
        archive_after_days: int = 90,
        batch_size: int = 1000,
    ) -> int:
        """
        Move completed process instances older than archive_after_days
        to an archive partition or soft-delete them.

        For non-partitioned tables, sets a status='archived' field.
        For partitioned tables, data naturally ages into older partitions
        which can be detached.

        Args:
            archive_after_days: Days after completion before archiving.
            batch_size: Max rows to archive per batch.

        Returns:
            Number of instances archived.
        """
        if self._db_session_factory is None:
            logger.warning("No DB session factory — cannot archive")
            return 0

        from datetime import datetime, timedelta, timezone

        from sqlalchemy import text, update

        cutoff = datetime.now(timezone.utc) - timedelta(days=archive_after_days)

        session = self._db_session_factory()
        try:
            # Update completed instances older than cutoff
            from appos.db.platform_models import ProcessInstance

            result = session.execute(
                update(ProcessInstance)
                .where(ProcessInstance.status == "completed")
                .where(ProcessInstance.completed_at < cutoff)
                .where(ProcessInstance.status != "archived")
                .values(status="archived")
                .execution_options(synchronize_session=False)
            )
            archived = result.rowcount
            session.commit()
            logger.info(f"Archived {archived} completed process instances")
            return archived
        except Exception as e:
            session.rollback()
            logger.error(f"Archival failed: {e}")
            return 0
        finally:
            session.close()

    # -----------------------------------------------------------------------
    # AI Query interface
    # -----------------------------------------------------------------------

    def query_for_ai(self, question: str) -> Dict[str, Any]:
        """
        Structured endpoint for AI agents to query runtime state.

        Simple pattern matching to route to the right data source.
        Returns structured dicts that AI can parse.
        """
        q = question.lower()

        if "dependencies" in q or "depends on" in q:
            # Extract object ref from question
            object_ref = self._extract_object_ref(question)
            if object_ref and self.dependency_graph:
                return {
                    "type": "dependency_graph",
                    "data": {
                        "direct": self.dependency_graph.get_direct_dependencies(object_ref),
                        "tree": self.dependency_graph.get_full_tree(object_ref),
                    },
                }

        if "impact" in q or "change" in q:
            object_ref = self._extract_object_ref(question)
            if object_ref and self.dependency_graph:
                return {
                    "type": "impact_analysis",
                    "data": self.dependency_graph.impact_analysis(object_ref),
                }

        if "stats" in q or "status" in q:
            return {
                "type": "runtime_status",
                "data": self._subsystem_status(),
            }

        return {
            "type": "unknown",
            "message": "Could not understand query. Try: dependencies, impact analysis, or stats.",
        }

    @staticmethod
    def _extract_object_ref(text: str) -> Optional[str]:
        """Extract a dotted object reference from text."""
        import re

        match = re.search(r"[a-z_]+\.[a-z_]+\.[a-z_]+", text)
        return match.group(0) if match else None

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _subsystem_status(self) -> Dict[str, Any]:
        """Return status of all subsystems."""
        status: Dict[str, Any] = {
            "registry": {
                "objects": self.registry.count,
            },
            "dependency_graph": None,
            "log_queue": None,
            "permission_cache": self.permission_cache is not None,
            "session_store": self.session_store is not None,
            "object_cache": self.object_cache is not None,
        }

        if self.dependency_graph:
            status["dependency_graph"] = self.dependency_graph.stats()

        if self.log_queue:
            status["log_queue"] = {
                "pending": self.log_queue.pending_count,
                "dropped": self.log_queue.dropped_count,
            }

        return status


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: Optional[CentralizedRuntime] = None


def get_runtime() -> CentralizedRuntime:
    """
    Get the global CentralizedRuntime singleton.

    Raises RuntimeError if the runtime hasn't been created yet.
    Use init_runtime() to create and start.
    """
    global _runtime
    if _runtime is None:
        raise RuntimeError(
            "AppOS runtime not initialized. Call init_runtime() first."
        )
    return _runtime


def init_runtime(**kwargs: Any) -> CentralizedRuntime:
    """
    Create the global CentralizedRuntime singleton.

    Args:
        **kwargs: Passed to CentralizedRuntime.__init__().

    Returns:
        The initialized (but not yet started) runtime instance.
        Call runtime.startup() to start subsystems.
    """
    global _runtime
    _runtime = CentralizedRuntime(**kwargs)
    return _runtime
