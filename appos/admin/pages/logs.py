"""
AppOS Admin Console — Log Viewer Page

Route: /admin/logs
Purpose: Filter and view system logs (Tier 1 — .appos/logs/ JSONL files).
Design ref: AppOS_Design.md §14 (Logging & Metrics Strategy)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class LogsState(rx.State):
    """State for the log viewer page."""

    # Log entries (parsed from JSONL files)
    entries: list[dict] = []
    total_entries: int = 0

    # Filters
    object_type: str = "all"
    log_category: str = "all"
    date_filter: str = ""
    search_query: str = ""

    # Available filter values
    object_types: list[str] = [
        "all", "rules", "processes", "steps", "integrations",
        "web_apis", "records", "interfaces", "pages", "constants",
        "connected_systems", "documents", "translation_sets", "folders",
    ]
    log_categories: list[str] = ["all", "execution", "performance", "security"]

    # Pagination
    page: int = 1
    page_size: int = 50

    def load_logs(self) -> None:
        """Load log entries from the .appos/logs/ file tree."""
        import json
        from pathlib import Path

        try:
            log_root = Path(".appos/logs")
            if not log_root.exists():
                self.entries = []
                self.total_entries = 0
                return

            # Determine which directories to scan
            if self.object_type == "all":
                type_dirs = [d for d in log_root.iterdir() if d.is_dir()]
            else:
                target = log_root / self.object_type
                type_dirs = [target] if target.exists() else []

            all_entries: list[dict] = []
            for type_dir in type_dirs:
                if self.log_category == "all":
                    cat_dirs = [d for d in type_dir.iterdir() if d.is_dir()]
                else:
                    target_cat = type_dir / self.log_category
                    cat_dirs = [target_cat] if target_cat.exists() else []

                for cat_dir in cat_dirs:
                    # Find JSONL files (optionally filter by date)
                    for jsonl_file in sorted(cat_dir.glob("*.jsonl"), reverse=True):
                        if self.date_filter and self.date_filter not in jsonl_file.name:
                            continue
                        try:
                            with open(jsonl_file, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        entry = json.loads(line)
                                        entry["_type"] = type_dir.name
                                        entry["_category"] = cat_dir.name
                                        # Apply text search
                                        if self.search_query:
                                            if self.search_query.lower() not in line.lower():
                                                continue
                                        all_entries.append(entry)
                                    except json.JSONDecodeError:
                                        continue
                        except OSError:
                            continue

            # Sort by timestamp descending
            all_entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
            self.total_entries = len(all_entries)

            # Paginate
            start = (self.page - 1) * self.page_size
            end = start + self.page_size
            self.entries = [
                {
                    "ts": e.get("ts", "—"),
                    "exec_id": e.get("exec_id", "—"),
                    "app": e.get("app", "—"),
                    "obj": e.get("obj", "—"),
                    "user": e.get("user", "—"),
                    "status": e.get("status", e.get("result", "—")),
                    "dur_ms": str(e.get("dur_ms", "—")),
                    "type": e.get("_type", "—"),
                    "category": e.get("_category", "—"),
                }
                for e in all_entries[start:end]
            ]
        except Exception:
            self.entries = []
            self.total_entries = 0

    def set_object_type(self, value: str) -> None:
        self.object_type = value
        self.page = 1
        self.load_logs()

    def set_log_category(self, value: str) -> None:
        self.log_category = value
        self.page = 1
        self.load_logs()

    def set_search(self, value: str) -> None:
        self.search_query = value

    def apply_search(self) -> None:
        self.page = 1
        self.load_logs()

    def next_page(self) -> None:
        if self.page * self.page_size < self.total_entries:
            self.page += 1
            self.load_logs()

    def prev_page(self) -> None:
        if self.page > 1:
            self.page -= 1
            self.load_logs()


def logs_page() -> rx.Component:
    """Log viewer page — browse system logs with filters."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Logs", size="6"),
                rx.spacer(),
                rx.text(
                    f"{LogsState.total_entries} entries",
                    size="2",
                    color="gray",
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Filters
            rx.hstack(
                rx.vstack(
                    rx.text("Object Type", size="1", weight="bold"),
                    rx.select(
                        LogsState.object_types,
                        value=LogsState.object_type,
                        on_change=LogsState.set_object_type,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Category", size="1", weight="bold"),
                    rx.select(
                        LogsState.log_categories,
                        value=LogsState.log_category,
                        on_change=LogsState.set_log_category,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Search", size="1", weight="bold"),
                    rx.hstack(
                        rx.input(
                            placeholder="Search logs…",
                            value=LogsState.search_query,
                            on_change=LogsState.set_search,
                            size="2",
                        ),
                        rx.button("Go", size="2", on_click=LogsState.apply_search),
                        spacing="2",
                    ),
                    spacing="1",
                ),
                spacing="4",
                align="end",
            ),
            rx.divider(),
            # Log entries table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Timestamp"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("Category"),
                        rx.table.column_header_cell("App"),
                        rx.table.column_header_cell("Object"),
                        rx.table.column_header_cell("User"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Duration"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        LogsState.entries,
                        _log_row,
                    ),
                ),
                width="100%",
            ),
            # Pagination
            rx.hstack(
                rx.button(
                    "← Previous",
                    size="1",
                    variant="outline",
                    on_click=LogsState.prev_page,
                    disabled=LogsState.page <= 1,
                ),
                rx.text(f"Page {LogsState.page}", size="2"),
                rx.button(
                    "Next →",
                    size="1",
                    variant="outline",
                    on_click=LogsState.next_page,
                ),
                spacing="3",
                justify="center",
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=LogsState.load_logs,
        ),
    )


def _log_row(entry: dict) -> rx.Component:
    """Render a single log entry row."""
    return rx.table.row(
        rx.table.cell(rx.text(entry["ts"], size="1")),
        rx.table.cell(rx.badge(entry["type"], size="1")),
        rx.table.cell(rx.badge(entry["category"], color_scheme="purple", size="1")),
        rx.table.cell(rx.text(entry["app"], size="1")),
        rx.table.cell(rx.text(entry["obj"], size="1", weight="bold")),
        rx.table.cell(rx.text(entry["user"], size="1")),
        rx.table.cell(
            rx.cond(
                entry["status"] == "ok",
                rx.badge("ok", color_scheme="green", size="1"),
                rx.cond(
                    entry["status"] == "DENIED",
                    rx.badge("DENIED", color_scheme="red", size="1"),
                    rx.badge(entry["status"], color_scheme="gray", size="1"),
                ),
            ),
        ),
        rx.table.cell(rx.text(entry["dur_ms"], size="1", color="gray")),
    )
