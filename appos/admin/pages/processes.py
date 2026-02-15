"""
AppOS Admin Console — Process Monitor Page

Route: /admin/processes
Purpose: Monitor running/completed process instances, view step history,
         inspect variables, and manage process execution.
Design ref: AppOS_Design.md §11 (Process Engine — Process History)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class ProcessMonitorState(rx.State):
    """
    State for the process monitor page — manages instance listing,
    step history inspection, and process management.
    """

    # Process instances list
    instances: list[dict] = []
    total_instances: int = 0

    # Filters
    status_filter: str = "all"
    app_filter: str = ""
    search_query: str = ""

    # Pagination
    page: int = 1
    page_size: int = 25

    # Selected instance detail
    selected_instance: dict = {}
    step_history: list[dict] = []
    show_detail: bool = False

    # Available status values for filter
    status_options: list[str] = [
        "all", "running", "completed", "failed",
        "paused", "cancelled", "waiting", "timed_out",
    ]

    def load_instances(self) -> None:
        """Load process instances from the database."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import ProcessInstance
            from sqlalchemy import desc

            session = runtime._db_session_factory()
            try:
                query = session.query(ProcessInstance)

                # Apply filters
                if self.status_filter and self.status_filter != "all":
                    query = query.filter(
                        ProcessInstance.status == self.status_filter
                    )
                if self.app_filter:
                    query = query.filter(
                        ProcessInstance.app_name == self.app_filter
                    )
                if self.search_query:
                    search = f"%{self.search_query}%"
                    query = query.filter(
                        ProcessInstance.process_name.ilike(search)
                        | ProcessInstance.instance_id.ilike(search)
                        | ProcessInstance.display_name.ilike(search)
                    )

                self.total_instances = query.count()

                # Paginate
                offset = (self.page - 1) * self.page_size
                instances = (
                    query.order_by(desc(ProcessInstance.started_at))
                    .offset(offset)
                    .limit(self.page_size)
                    .all()
                )

                self.instances = [
                    {
                        "id": i.id,
                        "instance_id": i.instance_id,
                        "process_name": i.process_name,
                        "display_name": i.display_name or i.process_name,
                        "app_name": i.app_name or "—",
                        "status": i.status,
                        "current_step": i.current_step or "—",
                        "started_by": str(i.started_by) if i.started_by else "system",
                        "triggered_by": i.triggered_by or "—",
                        "started_at": (
                            i.started_at.strftime("%Y-%m-%d %H:%M:%S")
                            if i.started_at else "—"
                        ),
                        "completed_at": (
                            i.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                            if i.completed_at else "—"
                        ),
                        "duration": self._calc_duration(i),
                    }
                    for i in instances
                ]
            finally:
                session.close()
        except Exception as e:
            import logging
            logging.getLogger("appos.admin").error(f"Failed to load instances: {e}")

    @staticmethod
    def _calc_duration(instance) -> str:
        """Calculate human-readable duration."""
        if instance.started_at and instance.completed_at:
            delta = instance.completed_at - instance.started_at
            secs = delta.total_seconds()
            if secs < 1:
                return f"{secs * 1000:.0f}ms"
            if secs < 60:
                return f"{secs:.1f}s"
            if secs < 3600:
                return f"{secs / 60:.1f}m"
            return f"{secs / 3600:.1f}h"
        if instance.status == "running":
            return "running…"
        return "—"

    def select_instance(self, instance_id: str) -> None:
        """Select an instance and load its step history."""
        # Find in current list
        for inst in self.instances:
            if inst["instance_id"] == instance_id:
                self.selected_instance = inst
                break

        self.show_detail = True
        self._load_step_history(instance_id)
        self._load_instance_detail(instance_id)

    def _load_instance_detail(self, instance_id: str) -> None:
        """Load full instance detail including variables."""
        try:
            from appos.process.executor import get_process_executor

            executor = get_process_executor()
            detail = executor.get_instance(instance_id)
            if detail:
                self.selected_instance = {
                    **self.selected_instance,
                    "inputs": str(detail.get("inputs", {})),
                    "variables": str(detail.get("variables", {})),
                    "outputs": str(detail.get("outputs", {})),
                    "error_info": str(detail.get("error_info", "")),
                }
        except Exception:
            pass

    def _load_step_history(self, instance_id: str) -> None:
        """Load step execution history for the selected instance."""
        try:
            from appos.process.executor import get_process_executor

            executor = get_process_executor()
            history = executor.get_step_history(instance_id)
            self.step_history = [
                {
                    **step,
                    "duration_display": (
                        f"{step['duration_ms']:.0f}ms"
                        if step.get("duration_ms") else "—"
                    ),
                    "status_icon": {
                        "completed": "✓",
                        "failed": "✗",
                        "skipped": "⊘",
                        "running": "⟳",
                    }.get(step.get("status", ""), "?"),
                    "parallel_badge": "∥" if step.get("is_parallel") else "",
                }
                for step in history
            ]
        except Exception:
            self.step_history = []

    def close_detail(self) -> None:
        """Close the detail panel."""
        self.show_detail = False
        self.selected_instance = {}
        self.step_history = []

    def set_status_filter(self, status: str) -> None:
        """Set the status filter and reload."""
        self.status_filter = status
        self.page = 1
        self.load_instances()

    def set_search(self, query: str) -> None:
        """Set the search query."""
        self.search_query = query

    def handle_search_key(self, key: str) -> None:
        """Handle key press in search input — search on Enter."""
        if key == "Enter":
            self.page = 1
            self.load_instances()

    def search_instances(self) -> None:
        """Apply search and reload."""
        self.page = 1
        self.load_instances()

    def next_page(self) -> None:
        """Go to next page."""
        max_page = max(1, (self.total_instances + self.page_size - 1) // self.page_size)
        if self.page < max_page:
            self.page += 1
            self.load_instances()

    def prev_page(self) -> None:
        """Go to previous page."""
        if self.page > 1:
            self.page -= 1
            self.load_instances()


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

def status_badge(status: str) -> rx.Component:
    """Colored status badge."""
    color_map = {
        "running": "blue",
        "completed": "green",
        "failed": "red",
        "paused": "yellow",
        "cancelled": "gray",
        "waiting": "orange",
        "timed_out": "red",
    }
    return rx.badge(status, color_scheme=color_map.get(status, "gray"), size="1")


def instance_row(instance: dict) -> rx.Component:
    """Render a single process instance row."""
    return rx.table.row(
        rx.table.cell(
            rx.link(
                rx.text(instance["instance_id"], size="2"),
                on_click=ProcessMonitorState.select_instance(instance["instance_id"]),
                cursor="pointer",
            )
        ),
        rx.table.cell(rx.text(instance["process_name"], size="2", weight="medium")),
        rx.table.cell(rx.text(instance["app_name"], size="2")),
        rx.table.cell(status_badge(instance["status"])),
        rx.table.cell(rx.text(instance["current_step"], size="2")),
        rx.table.cell(rx.text(instance["started_at"], size="1")),
        rx.table.cell(rx.text(instance["duration"], size="2")),
        rx.table.cell(rx.text(instance["triggered_by"], size="1")),
    )


def step_history_row(step: dict) -> rx.Component:
    """Render a single step history row."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(step["status_icon"], size="2"),
                rx.text(step.get("parallel_badge", ""), size="2", color="blue"),
                spacing="1",
            )
        ),
        rx.table.cell(rx.text(step["step_name"], size="2", weight="medium")),
        rx.table.cell(rx.text(step.get("rule_ref", ""), size="1")),
        rx.table.cell(status_badge(step["status"])),
        rx.table.cell(rx.text(step["duration_display"], size="2")),
        rx.table.cell(rx.text(str(step.get("attempt", 1)), size="2")),
        rx.table.cell(
            rx.text(step.get("started_at", "—"), size="1")
        ),
    )


def instance_detail_panel() -> rx.Component:
    """Detail panel for a selected process instance."""
    return rx.cond(
        ProcessMonitorState.show_detail,
        rx.box(
            rx.card(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.heading(
                            "Process Detail",
                            size="4",
                        ),
                        rx.spacer(),
                        rx.button(
                            "✕",
                            on_click=ProcessMonitorState.close_detail,
                            variant="ghost",
                            size="1",
                        ),
                        width="100%",
                    ),
                    rx.separator(),

                    # Instance info
                    rx.hstack(
                        rx.vstack(
                            rx.text("Instance ID", size="1", color="gray"),
                            rx.text(
                                ProcessMonitorState.selected_instance["instance_id"],
                                size="2", weight="bold",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("Status", size="1", color="gray"),
                            status_badge(
                                ProcessMonitorState.selected_instance["status"]
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("Process", size="1", color="gray"),
                            rx.text(
                                ProcessMonitorState.selected_instance["process_name"],
                                size="2",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("Duration", size="1", color="gray"),
                            rx.text(
                                ProcessMonitorState.selected_instance["duration"],
                                size="2",
                            ),
                            spacing="1",
                        ),
                        spacing="5",
                        wrap="wrap",
                    ),

                    # Variables section
                    rx.cond(
                        ProcessMonitorState.selected_instance.contains("variables"),
                        rx.vstack(
                            rx.text("Variables", size="2", weight="medium"),
                            rx.code(
                                ProcessMonitorState.selected_instance["variables"],
                            ),
                            spacing="1",
                            width="100%",
                        ),
                    ),

                    # Error info
                    rx.cond(
                        ProcessMonitorState.selected_instance.contains("error_info"),
                        rx.vstack(
                            rx.text("Error", size="2", weight="medium", color="red"),
                            rx.code(
                                ProcessMonitorState.selected_instance["error_info"],
                            ),
                            spacing="1",
                            width="100%",
                        ),
                    ),

                    rx.separator(),

                    # Step History table
                    rx.text("Step History", size="3", weight="medium"),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell(""),
                                rx.table.column_header_cell("Step"),
                                rx.table.column_header_cell("Rule"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Duration"),
                                rx.table.column_header_cell("Attempt"),
                                rx.table.column_header_cell("Started"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                ProcessMonitorState.step_history,
                                step_history_row,
                            ),
                        ),
                        width="100%",
                    ),

                    spacing="3",
                    width="100%",
                ),
            ),
            width="100%",
        ),
    )


def processes_page() -> rx.Component:
    """
    Admin page: Process Monitor

    Displays running/completed process instances with filtering,
    step-by-step execution history, and variable inspection.
    """
    return admin_layout(
        rx.vstack(
            # Page header
            rx.hstack(
                rx.heading("Process Monitor", size="6"),
                rx.spacer(),
                rx.button(
                    "Refresh",
                    on_click=ProcessMonitorState.load_instances,
                    variant="outline",
                    size="2",
                ),
                width="100%",
            ),

            # Filters bar
            rx.hstack(
                # Status filter
                rx.select(
                    ProcessMonitorState.status_options,
                    value=ProcessMonitorState.status_filter,
                    on_change=ProcessMonitorState.set_status_filter,
                    placeholder="Status filter",
                    size="2",
                ),
                # Search
                rx.input(
                    placeholder="Search process name or ID…",
                    value=ProcessMonitorState.search_query,
                    on_change=ProcessMonitorState.set_search,
                    on_key_down=ProcessMonitorState.handle_search_key,
                    size="2",
                    width="300px",
                ),
                rx.button(
                    "Search",
                    on_click=ProcessMonitorState.search_instances,
                    size="2",
                    variant="soft",
                ),
                rx.spacer(),
                rx.text(
                    f"Total: {ProcessMonitorState.total_instances}",
                    size="2",
                    color="gray",
                ),
                spacing="3",
                width="100%",
                align="center",
            ),

            # Instances table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Instance ID"),
                        rx.table.column_header_cell("Process"),
                        rx.table.column_header_cell("App"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Current Step"),
                        rx.table.column_header_cell("Started"),
                        rx.table.column_header_cell("Duration"),
                        rx.table.column_header_cell("Trigger"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        ProcessMonitorState.instances,
                        instance_row,
                    ),
                ),
                width="100%",
            ),

            # Pagination
            rx.hstack(
                rx.button(
                    "← Prev",
                    on_click=ProcessMonitorState.prev_page,
                    variant="outline",
                    size="1",
                    disabled=ProcessMonitorState.page <= 1,
                ),
                rx.text(
                    f"Page {ProcessMonitorState.page}",
                    size="2",
                ),
                rx.button(
                    "Next →",
                    on_click=ProcessMonitorState.next_page,
                    variant="outline",
                    size="1",
                ),
                spacing="3",
                justify="center",
                width="100%",
            ),

            # Detail panel (shows when an instance is selected)
            instance_detail_panel(),

            spacing="4",
            width="100%",
            padding="4",
            on_mount=ProcessMonitorState.load_instances,
        ),
    )
