"""
AppOS Admin Console — Records Browser Page

Route: /admin/records
Purpose: Browse all @record types across apps, view data, inspect schemas.
Design ref: AppOS_Design.md §5.7 (Record), §9 (Record System), §13 (Admin Console)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class RecordsBrowserState(rx.State):
    """
    State for the records browser — manages record type selection,
    data loading, and schema introspection.
    """

    # Record types discovered from the registry
    record_types: list[dict] = []

    # Currently selected record
    selected_record: str = ""
    selected_record_fields: list[dict] = []
    record_data: list[dict] = []
    record_count: int = 0

    # Pagination
    page: int = 1
    page_size: int = 25

    # Filter
    search_query: str = ""

    def load_record_types(self) -> None:
        """Load all registered @record types from the object registry."""
        try:
            from appos.engine.registry import object_registry

            records = object_registry.get_by_type("record")
            self.record_types = [
                {
                    "object_ref": r.object_ref,
                    "name": r.metadata.get("name", r.object_ref.split(".")[-1]),
                    "app": r.app_name or "platform",
                    "table_name": r.metadata.get("table_name", ""),
                    "audit": str(r.metadata.get("audit", False)),
                    "soft_delete": str(r.metadata.get("soft_delete", True)),
                }
                for r in records
            ]
        except Exception as e:
            self.record_types = []

    def select_record(self, object_ref: str) -> None:
        """Select a record type to browse its data and schema."""
        self.selected_record = object_ref
        self.page = 1
        self._load_record_schema()
        self._load_record_data()

    def _load_record_schema(self) -> None:
        """Load the schema (field list) for the selected record."""
        try:
            from appos.engine.registry import object_registry

            registered = object_registry.resolve(self.selected_record)
            if registered is None or registered.handler is None:
                self.selected_record_fields = []
                return

            handler = registered.handler
            # For Pydantic models, extract fields from model_fields
            if hasattr(handler, "model_fields"):
                fields = []
                for fname, finfo in handler.model_fields.items():
                    field_type = str(finfo.annotation) if finfo.annotation else "unknown"
                    fields.append({
                        "name": fname,
                        "type": field_type,
                        "required": finfo.is_required(),
                        "default": str(finfo.default) if finfo.default is not None else "—",
                    })
                self.selected_record_fields = fields
            else:
                self.selected_record_fields = []
        except Exception:
            self.selected_record_fields = []

    def _load_record_data(self) -> None:
        """Load sample data for the selected record (if table exists)."""
        # Data loading requires a generated SQLAlchemy model + DB connection.
        # This will be fully functional once the model generator output is
        # importable. For now, show schema only.
        self.record_data = []
        self.record_count = 0

    def set_search(self, value: str) -> None:
        """Update search query."""
        self.search_query = value

    def next_page(self) -> None:
        """Go to next page."""
        self.page += 1
        self._load_record_data()

    def prev_page(self) -> None:
        """Go to previous page."""
        if self.page > 1:
            self.page -= 1
            self._load_record_data()


def records_browser_page() -> rx.Component:
    """Records browser — browse all @record types and their data."""
    return admin_layout(
        rx.vstack(
            rx.heading("Records Browser", size="6"),
            rx.text(
                "Browse registered @record types, inspect schemas, and view data.",
                size="2",
                color="gray",
            ),
            rx.divider(),
            rx.hstack(
                # Left panel: record type list
                rx.box(
                    _record_type_list(),
                    width="280px",
                    min_width="280px",
                    border_right="1px solid var(--gray-5)",
                    overflow_y="auto",
                    height="calc(100vh - 200px)",
                ),
                # Right panel: selected record details
                rx.box(
                    _record_detail_panel(),
                    flex="1",
                    overflow_y="auto",
                    padding_left="4",
                    height="calc(100vh - 200px)",
                ),
                width="100%",
                spacing="0",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=RecordsBrowserState.load_record_types,
        ),
    )


def _record_type_list() -> rx.Component:
    """Left panel — list of all record types."""
    return rx.vstack(
        rx.text("Record Types", size="3", weight="bold", padding="2"),
        rx.foreach(
            RecordsBrowserState.record_types,
            _record_type_item,
        ),
        rx.cond(
            RecordsBrowserState.record_types.length() == 0,
            rx.text(
                "No @record types registered.\nDefine records in apps/*/records/.",
                size="1",
                color="gray",
                padding="2",
            ),
            rx.fragment(),
        ),
        spacing="1",
        width="100%",
        padding="2",
    )


def _record_type_item(record: dict) -> rx.Component:
    """A single record type in the left sidebar."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("database", size=14),
                rx.text(record["name"], weight="bold", size="2"),
                spacing="2",
            ),
            rx.text(record["app"], size="1", color="gray"),
            spacing="0",
        ),
        padding="2",
        border_radius="6px",
        cursor="pointer",
        width="100%",
        _hover={"background": "var(--gray-4)"},
        on_click=RecordsBrowserState.select_record(record["object_ref"]),
    )


def _record_detail_panel() -> rx.Component:
    """Right panel — schema + data for selected record."""
    return rx.cond(
        RecordsBrowserState.selected_record != "",
        rx.vstack(
            # Header
            rx.hstack(
                rx.heading(RecordsBrowserState.selected_record, size="4"),
                rx.spacer(),
                rx.badge("Schema", variant="outline"),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Schema table
            rx.text("Fields", size="3", weight="bold"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Field"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("Required"),
                        rx.table.column_header_cell("Default"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        RecordsBrowserState.selected_record_fields,
                        _field_row,
                    ),
                ),
                width="100%",
            ),
            # Data preview placeholder
            rx.divider(),
            rx.text("Data Preview", size="3", weight="bold"),
            rx.cond(
                RecordsBrowserState.record_count > 0,
                rx.text(
                    f"Showing page {RecordsBrowserState.page}",
                    size="1",
                    color="gray",
                ),
                rx.callout(
                    "Data preview is available after running the model generator "
                    "and applying migrations. Use: appos generate && appos migrate",
                    icon="info",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        # No record selected
        rx.center(
            rx.vstack(
                rx.icon("database", size=48, color="gray"),
                rx.text(
                    "Select a record type to view its schema and data.",
                    size="2",
                    color="gray",
                ),
                align="center",
                spacing="3",
            ),
            height="400px",
        ),
    )


def _field_row(field: dict) -> rx.Component:
    """Render a field row in the schema table."""
    return rx.table.row(
        rx.table.cell(rx.code(field["name"], size="2")),
        rx.table.cell(rx.text(field["type"], size="2")),
        rx.table.cell(
            rx.cond(
                field["required"],
                rx.badge("Required", color_scheme="red", size="1"),
                rx.badge("Optional", color_scheme="gray", size="1"),
            ),
        ),
        rx.table.cell(rx.text(field["default"], size="1", color="gray")),
    )
