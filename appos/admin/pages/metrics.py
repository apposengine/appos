"""
AppOS Admin Console — Metrics Dashboard Page

Route: /admin/metrics
Purpose: Performance dashboards per object, app, time range.
         Reads from .appos/logs/{type}/performance/ JSONL files.
Design ref: AppOS_Design.md §13 (Metrics Dashboard), §14 (Metrics Collection)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class MetricsState(rx.State):
    """State for the metrics dashboard page."""

    # Aggregated metrics
    objects: list[dict] = []
    total_calls_24h: int = 0
    avg_duration_ms: float = 0.0
    error_rate: float = 0.0

    # Filters
    app_filter: str = ""
    type_filter: str = "all"
    time_range: str = "24h"

    type_options: list[str] = [
        "all", "rules", "processes", "steps", "integrations",
        "web_apis", "records", "interfaces", "connected_systems",
    ]
    time_options: list[str] = ["1h", "6h", "24h", "7d", "30d"]

    # Selected object detail
    selected_object: str = ""
    detail: dict = {}
    recent_executions: list[dict] = []

    def load_metrics(self) -> None:
        """Load and aggregate performance metrics from JSONL log files."""
        import json
        from collections import defaultdict
        from datetime import datetime, timedelta, timezone
        from pathlib import Path

        try:
            log_root = Path(".appos/logs")
            if not log_root.exists():
                self.objects = []
                return

            # Determine time cutoff
            now = datetime.now(timezone.utc)
            cutoffs = {
                "1h": timedelta(hours=1),
                "6h": timedelta(hours=6),
                "24h": timedelta(hours=24),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
            }
            cutoff = now - cutoffs.get(self.time_range, timedelta(hours=24))

            # Aggregate per object
            obj_stats: dict[str, dict] = defaultdict(lambda: {
                "calls": 0, "total_ms": 0.0, "errors": 0,
                "min_ms": float("inf"), "max_ms": 0.0, "durations": [],
            })

            # Determine type directories
            if self.type_filter == "all":
                type_dirs = [d for d in log_root.iterdir() if d.is_dir()]
            else:
                target = log_root / self.type_filter
                type_dirs = [target] if target.exists() else []

            for type_dir in type_dirs:
                perf_dir = type_dir / "performance"
                exec_dir = type_dir / "execution"

                # Read performance logs
                if perf_dir.exists():
                    for jsonl_file in perf_dir.glob("*.jsonl"):
                        try:
                            with open(jsonl_file, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        entry = json.loads(line)
                                        ts = entry.get("ts", "")
                                        try:
                                            entry_time = datetime.fromisoformat(
                                                ts.replace("Z", "+00:00")
                                            )
                                            if entry_time < cutoff:
                                                continue
                                        except (ValueError, AttributeError):
                                            continue

                                        if self.app_filter and entry.get("app") != self.app_filter:
                                            continue

                                        obj_ref = entry.get("obj", "unknown")
                                        dur = float(entry.get("dur_ms", 0))
                                        stats = obj_stats[obj_ref]
                                        stats["calls"] += 1
                                        stats["total_ms"] += dur
                                        stats["durations"].append(dur)
                                        stats["min_ms"] = min(stats["min_ms"], dur)
                                        stats["max_ms"] = max(stats["max_ms"], dur)
                                    except (json.JSONDecodeError, KeyError):
                                        continue
                        except OSError:
                            continue

                # Read execution logs for error counts
                if exec_dir.exists():
                    for jsonl_file in exec_dir.glob("*.jsonl"):
                        try:
                            with open(jsonl_file, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        entry = json.loads(line)
                                        ts = entry.get("ts", "")
                                        try:
                                            entry_time = datetime.fromisoformat(
                                                ts.replace("Z", "+00:00")
                                            )
                                            if entry_time < cutoff:
                                                continue
                                        except (ValueError, AttributeError):
                                            continue

                                        if self.app_filter and entry.get("app") != self.app_filter:
                                            continue

                                        obj_ref = entry.get("obj", "unknown")
                                        status = entry.get("status", "ok")
                                        if status not in ("ok", "completed"):
                                            obj_stats[obj_ref]["errors"] += 1
                                    except (json.JSONDecodeError, KeyError):
                                        continue
                        except OSError:
                            continue

            # Build sorted object list
            result = []
            total_calls = 0
            total_ms = 0.0
            total_errors = 0
            for obj_ref, stats in sorted(obj_stats.items(), key=lambda x: x[1]["calls"], reverse=True):
                calls = stats["calls"]
                avg_ms = stats["total_ms"] / calls if calls > 0 else 0
                durations = sorted(stats["durations"])
                p95_idx = int(len(durations) * 0.95) if durations else 0
                p95 = durations[p95_idx] if p95_idx < len(durations) else 0
                error_pct = (stats["errors"] / calls * 100) if calls > 0 else 0

                result.append({
                    "obj": obj_ref,
                    "calls": str(calls),
                    "avg_ms": f"{avg_ms:.1f}",
                    "p95_ms": f"{p95:.1f}",
                    "min_ms": f"{stats['min_ms']:.1f}" if stats["min_ms"] != float("inf") else "—",
                    "max_ms": f"{stats['max_ms']:.1f}",
                    "error_pct": f"{error_pct:.1f}%",
                })
                total_calls += calls
                total_ms += stats["total_ms"]
                total_errors += stats["errors"]

            self.objects = result
            self.total_calls_24h = total_calls
            self.avg_duration_ms = total_ms / total_calls if total_calls > 0 else 0
            self.error_rate = (total_errors / total_calls * 100) if total_calls > 0 else 0

        except Exception:
            self.objects = []

    def set_type_filter(self, value: str) -> None:
        self.type_filter = value
        self.load_metrics()

    def set_time_range(self, value: str) -> None:
        self.time_range = value
        self.load_metrics()

    def set_app_filter(self, value: str) -> None:
        self.app_filter = value
        self.load_metrics()

    def select_object(self, obj_ref: str) -> None:
        """Select an object to view detailed metrics."""
        self.selected_object = obj_ref
        # Find in objects list
        for o in self.objects:
            if o["obj"] == obj_ref:
                self.detail = o
                break


def metrics_page() -> rx.Component:
    """Metrics dashboard page — performance overview per object."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Metrics", size="6"),
                rx.spacer(),
                rx.text(
                    f"{MetricsState.total_calls_24h} total calls",
                    size="2",
                    color="gray",
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Summary cards
            rx.grid(
                _stat_card("Total Calls", MetricsState.total_calls_24h),
                _stat_card(
                    "Avg Duration",
                    rx.text(f"{MetricsState.avg_duration_ms:.1f} ms"),
                ),
                _stat_card(
                    "Error Rate",
                    rx.text(f"{MetricsState.error_rate:.1f}%"),
                ),
                columns="3",
                spacing="4",
                width="100%",
            ),
            # Filters
            rx.hstack(
                rx.vstack(
                    rx.text("Object Type", size="1", weight="bold"),
                    rx.select(
                        MetricsState.type_options,
                        value=MetricsState.type_filter,
                        on_change=MetricsState.set_type_filter,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Time Range", size="1", weight="bold"),
                    rx.select(
                        MetricsState.time_options,
                        value=MetricsState.time_range,
                        on_change=MetricsState.set_time_range,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("App", size="1", weight="bold"),
                    rx.input(
                        placeholder="Filter by app…",
                        value=MetricsState.app_filter,
                        on_change=MetricsState.set_app_filter,
                        size="2",
                    ),
                    spacing="1",
                ),
                spacing="4",
                align="end",
            ),
            rx.divider(),
            # Objects table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Object"),
                        rx.table.column_header_cell("Calls"),
                        rx.table.column_header_cell("Avg (ms)"),
                        rx.table.column_header_cell("P95 (ms)"),
                        rx.table.column_header_cell("Min (ms)"),
                        rx.table.column_header_cell("Max (ms)"),
                        rx.table.column_header_cell("Errors"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        MetricsState.objects,
                        _metric_row,
                    ),
                ),
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=MetricsState.load_metrics,
        ),
    )


def _metric_row(obj: dict) -> rx.Component:
    """Render a single object metrics row."""
    return rx.table.row(
        rx.table.cell(
            rx.text(obj["obj"], weight="bold", size="2"),
        ),
        rx.table.cell(rx.text(obj["calls"], size="2")),
        rx.table.cell(rx.text(obj["avg_ms"], size="2")),
        rx.table.cell(rx.text(obj["p95_ms"], size="2")),
        rx.table.cell(rx.text(obj["min_ms"], size="2", color="gray")),
        rx.table.cell(rx.text(obj["max_ms"], size="2", color="gray")),
        rx.table.cell(
            rx.badge(obj["error_pct"], color_scheme="red", size="1"),
        ),
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
