"""
AppOS Admin Console — Worker Management Page

Route: /admin/workers
Purpose: View Celery workers, scale pool, queue depth, autoscale control.
Design ref: AppOS_Design.md §13 (Worker Management), WorkerManager class
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class WorkerManager:
    """
    Interface to Celery worker control for admin console.

    Reads worker state via celery.control.inspect() and manages pool
    size via celery.control.pool_grow/pool_shrink.
    """

    def __init__(self, celery_app=None):
        self.app = celery_app
        self._inspect = None

    def _get_inspect(self):
        if self.app is None:
            return None
        if self._inspect is None:
            self._inspect = self.app.control.inspect()
        return self._inspect

    def get_workers(self) -> dict:
        """Get all active workers and their stats."""
        inspect = self._get_inspect()
        if inspect is None:
            return {"active": {}, "reserved": {}, "stats": {}, "active_queues": {}}
        return {
            "active": inspect.active() or {},
            "reserved": inspect.reserved() or {},
            "stats": inspect.stats() or {},
            "active_queues": inspect.active_queues() or {},
        }

    def scale_worker(self, worker: str, delta: int) -> None:
        """Grow or shrink a specific worker's pool. delta=+1 or -1."""
        if self.app is None:
            return
        if delta > 0:
            self.app.control.pool_grow(delta, destination=[worker])
        elif delta < 0:
            self.app.control.pool_shrink(abs(delta), destination=[worker])

    def set_autoscale(self, max_concurrency: int, min_concurrency: int) -> None:
        """Update autoscale range for all workers."""
        if self.app is None:
            return
        self.app.control.autoscale(max=max_concurrency, min=min_concurrency)

    def get_queue_lengths(self, redis_url: str = "redis://localhost:6379") -> dict:
        """Get pending task count per queue from Redis."""
        try:
            import redis as redis_lib
            r = redis_lib.from_url(redis_url)
            queues = ["celery", "process_steps", "scheduled"]
            return {q: r.llen(q) for q in queues}
        except Exception:
            return {"celery": 0, "process_steps": 0, "scheduled": 0}


class WorkersState(rx.State):
    """State for the worker management page."""

    # Worker list
    workers: list[dict] = []
    total_workers: int = 0
    total_pool_size: int = 0
    total_active: int = 0
    total_queued: int = 0

    # Queue lengths
    queues: list[dict] = []

    # Autoscale
    autoscale_min: str = "4"
    autoscale_max: str = "16"

    # Feedback
    action_message: str = ""

    def load_workers(self) -> None:
        """Load worker status from Celery."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                self.workers = []
                return

            # Try to get Celery app
            try:
                from appos.process.scheduler import celery_app
                manager = WorkerManager(celery_app)
            except (ImportError, AttributeError):
                manager = WorkerManager(None)

            info = manager.get_workers()

            active_tasks = info.get("active", {}) or {}
            reserved_tasks = info.get("reserved", {}) or {}
            stats_info = info.get("stats", {}) or {}

            workers_list = []
            total_pool = 0
            total_active = 0
            total_queued = 0

            for worker_name in stats_info:
                worker_stats = stats_info[worker_name]
                pool_info = worker_stats.get("pool", {})
                pool_size = pool_info.get("max-concurrency", 0)
                active_count = len(active_tasks.get(worker_name, []))
                queued_count = len(reserved_tasks.get(worker_name, []))

                workers_list.append({
                    "name": worker_name,
                    "status": "ok",
                    "pool_size": str(pool_size),
                    "active": str(active_count),
                    "queued": str(queued_count),
                })
                total_pool += pool_size
                total_active += active_count
                total_queued += queued_count

            self.workers = workers_list
            self.total_workers = len(workers_list)
            self.total_pool_size = total_pool
            self.total_active = total_active
            self.total_queued = total_queued

            # Queue lengths from Redis
            redis_url = getattr(runtime, "_redis_url", "redis://localhost:6379")
            q_lengths = manager.get_queue_lengths(redis_url)
            self.queues = [
                {"name": name, "length": str(length)}
                for name, length in q_lengths.items()
            ]

        except Exception:
            self.workers = []
            self.queues = []

    def scale_worker_up(self, worker_name: str) -> None:
        """Add 1 worker thread to a specific node."""
        self._scale(worker_name, +1)

    def scale_worker_down(self, worker_name: str) -> None:
        """Remove 1 worker thread from a specific node."""
        self._scale(worker_name, -1)

    def _scale(self, worker_name: str, delta: int) -> None:
        try:
            from appos.process.scheduler import celery_app
            manager = WorkerManager(celery_app)
            manager.scale_worker(worker_name, delta)
            direction = "up" if delta > 0 else "down"
            self.action_message = f"Scaled {worker_name} {direction} by {abs(delta)}"
            self.load_workers()
        except Exception as e:
            self.action_message = f"Error: {e}"

    def apply_autoscale(self, form_data: dict) -> None:
        """Apply autoscale settings to all workers."""
        try:
            min_val = int(form_data.get("autoscale_min", 4))
            max_val = int(form_data.get("autoscale_max", 16))
            from appos.process.scheduler import celery_app
            manager = WorkerManager(celery_app)
            manager.set_autoscale(max_concurrency=max_val, min_concurrency=min_val)
            self.action_message = f"Autoscale set: min={min_val}, max={max_val}"
        except Exception as e:
            self.action_message = f"Error: {e}"


def workers_page() -> rx.Component:
    """Worker management page — view and control Celery workers."""
    return admin_layout(
        rx.vstack(
            rx.heading("Workers", size="6"),
            rx.divider(),
            # Summary cards
            rx.grid(
                _stat_card("Workers", WorkersState.total_workers),
                _stat_card("Pool Size", WorkersState.total_pool_size),
                _stat_card("Active", WorkersState.total_active),
                _stat_card("Queued", WorkersState.total_queued),
                columns="4",
                spacing="4",
                width="100%",
            ),
            # Action message
            rx.cond(
                WorkersState.action_message,
                rx.callout(
                    WorkersState.action_message,
                    icon="info",
                    color_scheme="blue",
                    size="1",
                ),
            ),
            rx.divider(),
            # Workers table
            rx.heading("Worker Nodes", size="4"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Worker"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Pool"),
                        rx.table.column_header_cell("Active"),
                        rx.table.column_header_cell("Queued"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        WorkersState.workers,
                        _worker_row,
                    ),
                ),
                width="100%",
            ),
            rx.divider(),
            # Queue status
            rx.heading("Queue Status", size="4"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Queue"),
                        rx.table.column_header_cell("Pending Tasks"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        WorkersState.queues,
                        _queue_row,
                    ),
                ),
                width="100%",
            ),
            rx.divider(),
            # Autoscale controls
            rx.heading("Global Scaling", size="4"),
            rx.form(
                rx.hstack(
                    rx.vstack(
                        rx.text("Min Concurrency", size="2", weight="bold"),
                        rx.input(
                            name="autoscale_min",
                            default_value=WorkersState.autoscale_min,
                            type="number",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("Max Concurrency", size="2", weight="bold"),
                        rx.input(
                            name="autoscale_max",
                            default_value=WorkersState.autoscale_max,
                            type="number",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    rx.button("Apply Autoscale", type="submit", size="2"),
                    spacing="4",
                    align="end",
                ),
                on_submit=WorkersState.apply_autoscale,
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=WorkersState.load_workers,
        ),
    )


def _worker_row(worker: dict) -> rx.Component:
    """Render a single worker row."""
    return rx.table.row(
        rx.table.cell(rx.text(worker["name"], weight="bold", size="2")),
        rx.table.cell(rx.badge("OK", color_scheme="green", size="1")),
        rx.table.cell(rx.text(worker["pool_size"], size="2")),
        rx.table.cell(rx.text(worker["active"], size="2")),
        rx.table.cell(rx.text(worker["queued"], size="2")),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "+",
                    size="1",
                    variant="outline",
                    on_click=WorkersState.scale_worker_up(worker["name"]),
                ),
                rx.button(
                    "−",
                    size="1",
                    variant="outline",
                    on_click=WorkersState.scale_worker_down(worker["name"]),
                ),
                spacing="2",
            ),
        ),
    )


def _queue_row(queue: dict) -> rx.Component:
    """Render a queue status row."""
    return rx.table.row(
        rx.table.cell(rx.text(queue["name"], weight="bold", size="2")),
        rx.table.cell(rx.badge(queue["length"], color_scheme="blue", size="1")),
    )


def _stat_card(title: str, value) -> rx.Component:
    """Render a stat card."""
    return rx.card(
        rx.vstack(
            rx.text(title, size="2", color="gray"),
            rx.heading(value, size="5"),
            spacing="1",
            align="center",
        ),
    )
