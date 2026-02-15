"""
AppOS Logging System — Structured JSON file-based logging with async queue.

Implements:
- FileLogger: Per-object-type, per-category log files (daily rotation)
- AsyncLogQueue: In-memory queue with background flush (100ms / 50 entries)
- Log entry builders for each event type
- Retention-aware directory structure

Design refs: AppOS_Logging_Reference.md, AppOS_Design.md §14
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Dict, List, Optional

logger = logging.getLogger("appos.engine.logging")

# Valid object types and their permitted categories
OBJECT_TYPE_CATEGORIES = {
    "rules": ["execution", "performance", "security"],
    "processes": ["execution", "performance", "security"],
    "steps": ["execution", "performance"],
    "integrations": ["execution", "performance", "security"],
    "web_apis": ["execution", "performance", "security"],
    "records": ["execution", "performance", "security"],
    "interfaces": ["execution", "security"],
    "pages": ["execution", "security"],
    "constants": ["execution"],
    "documents": ["execution", "security"],
    "folders": ["execution", "security"],
    "translation_sets": ["execution"],
    "connected_systems": ["execution", "security"],
    "system": ["execution", "security"],
    "admin": ["execution", "security"],
}

# Retention defaults (days)
DEFAULT_RETENTION = {
    "execution": 90,
    "performance": 30,
    "security": 365,
}


class LogEntry:
    """A structured log entry destined for a specific file."""

    __slots__ = ("object_type", "category", "data")

    def __init__(self, object_type: str, category: str, data: Dict[str, Any]):
        self.object_type = object_type
        self.category = category
        self.data = data

    def to_json(self) -> str:
        return json.dumps(self.data, default=str, separators=(",", ":"))


class FileLogger:
    """
    Writes structured JSON log entries to per-object-type, per-category files.
    Files rotate daily: logs/{object_type}/{category}/{YYYY-MM-DD}.jsonl

    Thread-safe — uses a lock per file path.
    """

    def __init__(self, log_dir: str = "logs"):
        self._log_dir = Path(log_dir)
        self._file_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create the full directory tree for all object types and categories."""
        for obj_type, categories in OBJECT_TYPE_CATEGORIES.items():
            for cat in categories:
                (self._log_dir / obj_type / cat).mkdir(parents=True, exist_ok=True)

    def write(self, entry: LogEntry) -> None:
        """Write a single log entry to the appropriate file."""
        file_path = self._resolve_path(entry.object_type, entry.category)
        key = str(file_path)

        with self._file_locks[key]:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry.to_json())
                f.write("\n")

    def write_batch(self, entries: List[LogEntry]) -> None:
        """
        Write a batch of log entries, grouping by file path for efficiency.
        """
        grouped: Dict[str, List[LogEntry]] = defaultdict(list)
        for entry in entries:
            file_path = str(self._resolve_path(entry.object_type, entry.category))
            grouped[file_path].append(entry)

        for file_path, batch in grouped.items():
            with self._file_locks[file_path]:
                with open(file_path, "a", encoding="utf-8") as f:
                    for entry in batch:
                        f.write(entry.to_json())
                        f.write("\n")

    def _resolve_path(self, object_type: str, category: str) -> Path:
        """Resolve the log file path for today's date."""
        today = date.today().isoformat()
        return self._log_dir / object_type / category / f"{today}.jsonl"

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def query(
        self,
        object_type: str,
        category: str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Query log entries from JSONL files for a given object_type/category.

        Args:
            object_type: The object type folder (e.g. "rules", "integrations").
            category: The category folder (e.g. "execution", "security").
            start_date: Earliest date to include (defaults to 7 days ago).
            end_date: Latest date to include (defaults to today).
            filters: Optional dict of key/value pairs — only entries matching
                     ALL of them (exact equality on top-level data keys) are returned.
            limit: Max number of entries to return.

        Returns:
            List of parsed log-entry dicts, newest first.
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=7)

        log_base = self._log_dir / object_type / category
        if not log_base.exists():
            return []

        results: List[Dict[str, Any]] = []
        current = end_date
        while current >= start_date and len(results) < limit:
            file_path = log_base / f"{current.isoformat()}.jsonl"
            if file_path.exists():
                results.extend(
                    self._read_jsonl(file_path, filters, limit - len(results))
                )
            # Also check gzipped rotated file
            gz_path = file_path.with_suffix(".jsonl.gz")
            if gz_path.exists() and len(results) < limit:
                results.extend(
                    self._read_jsonl_gz(gz_path, filters, limit - len(results))
                )
            current -= timedelta(days=1)

        # Newest first — reverse because we iterated dates descending but
        # lines within a file are chronological
        results.reverse()
        return results[:limit]

    @staticmethod
    def _read_jsonl(
        path: Path,
        filters: Optional[Dict[str, Any]],
        remaining: int,
    ) -> List[Dict[str, Any]]:
        """Read up to *remaining* matching entries from a .jsonl file."""
        entries: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if filters and not all(data.get(k) == v for k, v in filters.items()):
                        continue
                    entries.append(data)
                    if len(entries) >= remaining:
                        break
        except OSError as exc:
            logger.warning("Could not read log file %s: %s", path, exc)
        return entries

    @staticmethod
    def _read_jsonl_gz(
        path: Path,
        filters: Optional[Dict[str, Any]],
        remaining: int,
    ) -> List[Dict[str, Any]]:
        """Read up to *remaining* matching entries from a gzipped .jsonl.gz file."""
        entries: List[Dict[str, Any]] = []
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if filters and not all(data.get(k) == v for k, v in filters.items()):
                        continue
                    entries.append(data)
                    if len(entries) >= remaining:
                        break
        except OSError as exc:
            logger.warning("Could not read gzipped log file %s: %s", path, exc)
        return entries


class AsyncLogQueue:
    """
    In-memory queue with a background flush thread.

    Entries are pushed non-blocking. A background thread flushes to FileLogger
    every flush_interval_ms OR when flush_batch_size entries accumulate,
    whichever comes first.

    Design: AppOS_Logging_Reference.md → Async Logging Pipeline
    """

    def __init__(
        self,
        file_logger: FileLogger,
        flush_interval_ms: int = 100,
        flush_batch_size: int = 50,
        max_queue_size: int = 10000,
    ):
        self._logger = file_logger
        self._flush_interval = flush_interval_ms / 1000.0  # convert to seconds
        self._flush_batch_size = flush_batch_size
        self._queue: Queue[LogEntry] = Queue(maxsize=max_queue_size)
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._dropped_count = 0

    def start(self) -> None:
        """Start the background flush thread."""
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="appos-log-flush",
            daemon=True,
        )
        self._flush_thread.start()
        logger.info("Async log queue started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the flush thread and drain remaining entries."""
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=timeout)
        # Final drain
        self._drain()
        logger.info(f"Async log queue stopped (dropped: {self._dropped_count})")

    def push(self, entry: LogEntry) -> bool:
        """
        Push a log entry to the queue. Non-blocking.

        Returns:
            True if queued, False if dropped (queue full).
        """
        try:
            self._queue.put_nowait(entry)
            return True
        except Full:
            self._dropped_count += 1
            return False

    def _flush_loop(self) -> None:
        """Background thread: flush on interval or batch size."""
        while self._running:
            batch = self._collect_batch()
            if batch:
                try:
                    self._logger.write_batch(batch)
                except Exception as e:
                    logger.error(f"Log flush error: {e}")
            else:
                time.sleep(self._flush_interval)

    def _collect_batch(self) -> List[LogEntry]:
        """Collect up to flush_batch_size entries from the queue."""
        batch: List[LogEntry] = []
        deadline = time.monotonic() + self._flush_interval

        while len(batch) < self._flush_batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                entry = self._queue.get(timeout=min(remaining, 0.01))
                batch.append(entry)
            except Empty:
                if batch:
                    break
                continue

        return batch

    def _drain(self) -> None:
        """Drain all remaining entries from the queue."""
        batch: List[LogEntry] = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        if batch:
            try:
                self._logger.write_batch(batch)
            except Exception as e:
                logger.error(f"Log drain error: {e}")

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        return self._dropped_count


# ---------------------------------------------------------------------------
# Log Entry Builders
# ---------------------------------------------------------------------------

def _base_entry(
    event: str,
    level: str,
    object_ref: str,
    execution_id: Optional[str] = None,
    user_id: Optional[Any] = None,
    app: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a base log entry with common fields."""
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "object_ref": object_ref,
    }
    if execution_id:
        entry["execution_id"] = execution_id
    if user_id is not None:
        entry["user_id"] = user_id
    if app:
        entry["app"] = app
    entry.update(extra)
    return entry


def log_rule_execution(
    object_ref: str,
    execution_id: str,
    user_id: Any,
    app: str,
    duration_ms: float,
    success: bool,
    process_instance_id: Optional[str] = None,
    step_name: Optional[str] = None,
    dependencies_accessed: Optional[List[str]] = None,
    cached: bool = False,
    error: Optional[str] = None,
) -> LogEntry:
    """Build a rule execution log entry."""
    data = _base_entry(
        event="rule_executed",
        level="INFO" if success else "ERROR",
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        duration_ms=duration_ms,
        success=success,
        cached=cached,
    )
    if process_instance_id:
        data["process_instance_id"] = process_instance_id
    if step_name:
        data["step_name"] = step_name
    if dependencies_accessed:
        data["dependencies_accessed"] = dependencies_accessed
    if error:
        data["error"] = error
    return LogEntry("rules", "execution", data)


def log_rule_performance(
    object_ref: str,
    execution_id: str,
    app: str,
    duration_ms: float,
    cached: bool = False,
) -> LogEntry:
    """Build a rule performance log entry."""
    data = _base_entry(
        event="rule_performance",
        level="INFO",
        object_ref=object_ref,
        execution_id=execution_id,
        app=app,
        duration_ms=duration_ms,
        cached=cached,
    )
    return LogEntry("rules", "performance", data)


def log_process_event(
    event: str,
    object_ref: str,
    execution_id: str,
    user_id: Any,
    app: str,
    process_instance_id: str,
    display_name: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    started_by: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> LogEntry:
    """Build a process event log entry (started/completed/failed)."""
    level = "ERROR" if "fail" in event else "INFO"
    data = _base_entry(
        event=event,
        level=level,
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        process_instance_id=process_instance_id,
    )
    if display_name:
        data["display_name"] = display_name
    if inputs:
        data["inputs"] = inputs
    if started_by:
        data["started_by"] = started_by
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    if error:
        data["error"] = error
    return LogEntry("processes", "execution", data)


def log_integration_call(
    object_ref: str,
    execution_id: str,
    user_id: Any,
    app: str,
    connected_system: str,
    method: str,
    url: str,
    status_code: int,
    duration_ms: float,
    success: bool,
    log_payload: bool = False,
    request_size_bytes: Optional[int] = None,
    response_size_bytes: Optional[int] = None,
    request_body: Optional[Any] = None,
    response_body: Optional[Any] = None,
) -> LogEntry:
    """Build an integration call log entry."""
    data = _base_entry(
        event="integration_called",
        level="INFO" if success else "ERROR",
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        connected_system=connected_system,
        method=method,
        url=url,
        status_code=status_code,
        duration_ms=duration_ms,
        success=success,
        log_payload=log_payload,
    )
    if request_size_bytes is not None:
        data["request_size_bytes"] = request_size_bytes
    if response_size_bytes is not None:
        data["response_size_bytes"] = response_size_bytes
    if log_payload:
        if request_body is not None:
            data["request_body"] = request_body
        if response_body is not None:
            data["response_body"] = response_body
    return LogEntry("integrations", "execution", data)


def log_record_operation(
    operation: str,
    object_ref: str,
    execution_id: str,
    user_id: Any,
    app: str,
    record_id: Optional[Any] = None,
    fields_changed: Optional[List[str]] = None,
    process_instance_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> LogEntry:
    """Build a record CRUD log entry."""
    data = _base_entry(
        event=f"record_{operation}",
        level="INFO",
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        operation=operation,
    )
    if record_id is not None:
        data["record_id"] = record_id
    if fields_changed:
        data["fields_changed"] = fields_changed
    if process_instance_id:
        data["process_instance_id"] = process_instance_id
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    return LogEntry("records", "execution", data)


def log_security_event(
    event: str,
    object_ref: str,
    object_type: str,
    permission_needed: str,
    user_id: Any,
    user_groups: List[str],
    app: str,
    execution_id: Optional[str] = None,
    source_object: Optional[str] = None,
    dependency_chain: Optional[List[str]] = None,
    level: str = "WARNING",
) -> LogEntry:
    """Build a security event log entry (deny/escalation)."""
    data = _base_entry(
        event=event,
        level=level,
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        object_type=object_type,
        permission_needed=permission_needed,
        user_groups=user_groups,
    )
    if source_object:
        data["source_object"] = source_object
    if dependency_chain:
        data["dependency_chain"] = dependency_chain
    return LogEntry(object_type if object_type in OBJECT_TYPE_CATEGORIES else "system", "security", data)


def log_web_api_request(
    object_ref: str,
    execution_id: str,
    user_id: Any,
    app: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_size_bytes: Optional[int] = None,
    response_size_bytes: Optional[int] = None,
) -> LogEntry:
    """Build a web API request log entry."""
    data = _base_entry(
        event="web_api_request",
        level="INFO" if status_code < 400 else "ERROR",
        object_ref=object_ref,
        execution_id=execution_id,
        user_id=user_id,
        app=app,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
    )
    if request_size_bytes is not None:
        data["request_size_bytes"] = request_size_bytes
    if response_size_bytes is not None:
        data["response_size_bytes"] = response_size_bytes
    return LogEntry("web_apis", "execution", data)


def log_system_event(
    event: str,
    level: str = "INFO",
    details: Optional[Dict[str, Any]] = None,
) -> LogEntry:
    """Build a system event log entry (startup, shutdown, config changes)."""
    data = _base_entry(
        event=event,
        level=level,
        object_ref="system",
    )
    if details:
        data["details"] = details
    return LogEntry("system", "execution", data)


# ---------------------------------------------------------------------------
# Log Cleanup / Retention
# ---------------------------------------------------------------------------

class LogRetentionManager:
    """
    Cleans up log files older than configured retention periods.
    Optionally compresses old files with gzip.

    Design: AppOS_Logging_Reference.md → Log Rotation & Cleanup
    """

    def __init__(
        self,
        log_dir: str = "logs",
        retention_days: Optional[Dict[str, int]] = None,
        compress_after_days: int = 7,
    ):
        self._log_dir = Path(log_dir)
        self._retention = retention_days or DEFAULT_RETENTION.copy()
        self._compress_after = compress_after_days

    def cleanup(self) -> Dict[str, int]:
        """
        Run retention cleanup across all log directories.

        Returns:
            Dict with counts: {"deleted": N, "compressed": M}
        """
        deleted = 0
        compressed = 0
        today = date.today()

        for obj_type, categories in OBJECT_TYPE_CATEGORIES.items():
            for cat in categories:
                cat_dir = self._log_dir / obj_type / cat
                if not cat_dir.exists():
                    continue

                retention = self._retention.get(cat, 90)

                for file_path in cat_dir.iterdir():
                    if not file_path.is_file():
                        continue

                    file_date = self._parse_file_date(file_path)
                    if file_date is None:
                        continue

                    age_days = (today - file_date).days

                    # Delete if beyond retention
                    if age_days > retention:
                        file_path.unlink()
                        deleted += 1
                        continue

                    # Compress if old enough and not already compressed
                    if (
                        age_days > self._compress_after
                        and file_path.suffix == ".jsonl"
                    ):
                        self._compress_file(file_path)
                        compressed += 1

        result = {"deleted": deleted, "compressed": compressed}
        logger.info(f"Log cleanup: {result}")
        return result

    def _parse_file_date(self, file_path: Path) -> Optional[date]:
        """Extract date from filename like 2026-02-12.jsonl or 2026-02-12.jsonl.gz."""
        name = file_path.name
        # Remove extensions
        date_str = name.split(".")[0]
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            return None

    def _compress_file(self, file_path: Path) -> None:
        """Gzip a log file and remove the original."""
        gz_path = file_path.with_suffix(file_path.suffix + ".gz")
        try:
            with open(file_path, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            file_path.unlink()
        except Exception as e:
            logger.error(f"Failed to compress {file_path}: {e}")
            # Clean up partial gz file
            if gz_path.exists():
                gz_path.unlink()


# ---------------------------------------------------------------------------
# Convenience: Global Log Queue Singleton
# ---------------------------------------------------------------------------

_global_queue: Optional[AsyncLogQueue] = None


def init_logging(
    log_dir: str = "logs",
    flush_interval_ms: int = 100,
    flush_batch_size: int = 50,
    max_queue_size: int = 10000,
) -> AsyncLogQueue:
    """Initialize the global async log queue."""
    global _global_queue
    file_logger = FileLogger(log_dir=log_dir)
    _global_queue = AsyncLogQueue(
        file_logger=file_logger,
        flush_interval_ms=flush_interval_ms,
        flush_batch_size=flush_batch_size,
        max_queue_size=max_queue_size,
    )
    _global_queue.start()
    return _global_queue


def get_log_queue() -> Optional[AsyncLogQueue]:
    """Get the global async log queue."""
    return _global_queue


def log(entry: LogEntry) -> bool:
    """Push a log entry to the global queue. Non-blocking."""
    if _global_queue is None:
        logger.warning("Log queue not initialized — entry dropped")
        return False
    return _global_queue.push(entry)


def shutdown_logging() -> None:
    """Flush and stop the global log queue."""
    global _global_queue
    if _global_queue:
        _global_queue.stop()
        _global_queue = None
