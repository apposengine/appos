"""
AppOS Admin Console — Object Browser Page

Route: /admin/objects
Purpose: Browse all registered object types across apps, view dependencies,
         inspect metadata, and see usage metrics.
Design ref: AppOS_Design.md §13 (Admin Console — Object Browser)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class ObjectBrowserState(rx.State):
    """
    State for the object browser — manages object type discovery,
    dependency inspection, and metric display.
    """

    # All objects from the registry
    objects: list[dict] = []
    total_objects: int = 0

    # Filters
    type_filter: str = "all"
    app_filter: str = "all"
    search_query: str = ""

    # Available filter options
    type_options: list[str] = [
        "all", "record", "expression_rule", "process", "step",
        "integration", "web_api", "constant", "translation_set",
        "interface", "page",
    ]
    app_options: list[str] = ["all"]

    # Selected object detail
    selected_object: dict = {}
    selected_dependencies: list[dict] = []
    show_detail: bool = False

    # Summary stats
    stats: dict = {}

    def load_objects(self) -> None:
        """Load all registered objects from the object registry."""
        try:
            from appos.engine.registry import object_registry

            all_objects = []
            apps_seen = set()

            for obj_ref, registered in object_registry._objects.items():
                meta = registered.metadata or {}
                app = registered.app_name or "platform"
                apps_seen.add(app)

                obj_data = {
                    "object_ref": registered.object_ref,
                    "name": meta.get("name", obj_ref.split(".")[-1]),
                    "object_type": registered.object_type,
                    "app_name": app,
                    "display_type": self._friendly_type(registered.object_type),
                    "has_handler": "yes" if registered.handler else "no",
                    "permissions": ", ".join(
                        meta.get("permissions", {}).keys()
                    ) if isinstance(meta.get("permissions"), dict) else "—",
                    "description": meta.get("description", "")[:80],
                }

                # Apply filters
                if self.type_filter != "all" and registered.object_type != self.type_filter:
                    continue
                if self.app_filter != "all" and app != self.app_filter:
                    continue
                if self.search_query:
                    search_lower = self.search_query.lower()
                    if (
                        search_lower not in obj_ref.lower()
                        and search_lower not in obj_data["name"].lower()
                        and search_lower not in obj_data["description"].lower()
                    ):
                        continue

                all_objects.append(obj_data)

            self.objects = sorted(all_objects, key=lambda x: (x["app_name"], x["object_type"], x["name"]))
            self.total_objects = len(self.objects)
            self.app_options = ["all"] + sorted(apps_seen)

            # Compute summary stats
            self._compute_stats()

        except Exception as e:
            import logging
            logging.getLogger("appos.admin").error(f"Failed to load objects: {e}")

    def _compute_stats(self) -> None:
        """Compute summary statistics from loaded objects."""
        type_counts: dict = {}
        app_counts: dict = {}
        for obj in self.objects:
            t = obj["object_type"]
            a = obj["app_name"]
            type_counts[t] = type_counts.get(t, 0) + 1
            app_counts[a] = app_counts.get(a, 0) + 1

        self.stats = {
            "total": str(self.total_objects),
            "types": str(len(type_counts)),
            "apps": str(len(app_counts)),
            "top_type": max(type_counts, key=type_counts.get) if type_counts else "—",
            "top_app": max(app_counts, key=app_counts.get) if app_counts else "—",
        }

    @staticmethod
    def _friendly_type(object_type: str) -> str:
        """Convert object_type to a friendly display name."""
        return {
            "record": "Record",
            "expression_rule": "Rule",
            "process": "Process",
            "step": "Step",
            "integration": "Integration",
            "web_api": "Web API",
            "constant": "Constant",
            "translation_set": "Translation",
            "interface": "Interface",
            "page": "Page",
        }.get(object_type, object_type.replace("_", " ").title())

    def select_object(self, object_ref: str) -> None:
        """Select an object and show its details."""
        for obj in self.objects:
            if obj["object_ref"] == object_ref:
                self.selected_object = obj
                break

        self.show_detail = True
        self._load_dependencies(object_ref)
        self._load_full_metadata(object_ref)

    def _load_full_metadata(self, object_ref: str) -> None:
        """Load full metadata for the selected object."""
        try:
            from appos.engine.registry import object_registry

            registered = object_registry.resolve(object_ref)
            if registered:
                meta = registered.metadata or {}
                self.selected_object = {
                    **self.selected_object,
                    "full_metadata": str(meta),
                    "handler_name": (
                        registered.handler.__name__
                        if registered.handler else "None"
                    ),
                    "module": (
                        registered.handler.__module__
                        if registered.handler and hasattr(registered.handler, "__module__")
                        else "—"
                    ),
                }
        except Exception:
            pass

    def _load_dependencies(self, object_ref: str) -> None:
        """Load dependency graph for the selected object."""
        try:
            from appos.engine.dependency import get_dependency_graph

            graph = get_dependency_graph()
            if graph:
                deps = graph.get_dependencies(object_ref)
                dependents = graph.get_dependents(object_ref)
                self.selected_dependencies = [
                    {"ref": d, "direction": "depends_on"} for d in (deps or [])
                ] + [
                    {"ref": d, "direction": "depended_by"} for d in (dependents or [])
                ]
            else:
                self.selected_dependencies = []
        except Exception:
            self.selected_dependencies = []

    def close_detail(self) -> None:
        """Close the detail panel."""
        self.show_detail = False
        self.selected_object = {}
        self.selected_dependencies = []

    def set_type_filter(self, type_value: str) -> None:
        """Set the type filter and reload."""
        self.type_filter = type_value
        self.load_objects()

    def set_app_filter(self, app_value: str) -> None:
        """Set the app filter and reload."""
        self.app_filter = app_value
        self.load_objects()

    def set_search(self, query: str) -> None:
        """Set the search query."""
        self.search_query = query

    def handle_search_key(self, key: str) -> None:
        """Handle key press in search input — search on Enter."""
        if key == "Enter":
            self.load_objects()

    def search_objects(self) -> None:
        """Apply search and reload."""
        self.load_objects()


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

def type_badge(object_type: str) -> rx.Component:
    """Colored badge for object type."""
    color_map = {
        "record": "blue",
        "expression_rule": "purple",
        "process": "green",
        "step": "teal",
        "integration": "orange",
        "web_api": "red",
        "constant": "gray",
        "translation_set": "cyan",
        "interface": "pink",
        "page": "indigo",
    }
    return rx.badge(object_type, color_scheme=color_map.get(object_type, "gray"), size="1")


def stat_card(label: str, value: rx.Var) -> rx.Component:
    """Small stat card for summary bar."""
    return rx.card(
        rx.vstack(
            rx.text(label, size="1", color="gray"),
            rx.text(value, size="4", weight="bold"),
            spacing="1",
            align="center",
        ),
        size="1",
    )


def object_row(obj: dict) -> rx.Component:
    """Render a single object row in the table."""
    return rx.table.row(
        rx.table.cell(
            rx.link(
                rx.text(obj["object_ref"], size="2"),
                on_click=ObjectBrowserState.select_object(obj["object_ref"]),
                cursor="pointer",
            )
        ),
        rx.table.cell(rx.text(obj["name"], size="2", weight="medium")),
        rx.table.cell(type_badge(obj["object_type"])),
        rx.table.cell(rx.text(obj["app_name"], size="2")),
        rx.table.cell(rx.text(obj["permissions"], size="1")),
        rx.table.cell(rx.text(obj["description"], size="1")),
    )


def dependency_row(dep: dict) -> rx.Component:
    """Render a dependency relationship row."""
    is_depends_on = dep["direction"] == "depends_on"
    return rx.hstack(
        rx.badge(
            rx.cond(is_depends_on, "→", "←"),
            color_scheme=rx.cond(is_depends_on, "blue", "green"),
            size="1",
        ),
        rx.text(
            dep["ref"],
            size="2",
        ),
        rx.text(
            rx.cond(is_depends_on, "(depends on)", "(depended by)"),
            size="1",
            color="gray",
        ),
        spacing="2",
    )


def object_detail_panel() -> rx.Component:
    """Detail panel for a selected object."""
    return rx.cond(
        ObjectBrowserState.show_detail,
        rx.box(
            rx.card(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.heading("Object Detail", size="4"),
                        rx.spacer(),
                        rx.button(
                            "✕",
                            on_click=ObjectBrowserState.close_detail,
                            variant="ghost",
                            size="1",
                        ),
                        width="100%",
                    ),
                    rx.separator(),

                    # Object info grid
                    rx.hstack(
                        rx.vstack(
                            rx.text("Object Ref", size="1", color="gray"),
                            rx.text(
                                ObjectBrowserState.selected_object["object_ref"],
                                size="2", weight="bold",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("Type", size="1", color="gray"),
                            type_badge(ObjectBrowserState.selected_object["object_type"]),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("App", size="1", color="gray"),
                            rx.text(
                                ObjectBrowserState.selected_object["app_name"],
                                size="2",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("Handler", size="1", color="gray"),
                            rx.text(
                                ObjectBrowserState.selected_object.get("handler_name", "—"),
                                size="2",
                            ),
                            spacing="1",
                        ),
                        spacing="5",
                        wrap="wrap",
                    ),

                    # Module path
                    rx.cond(
                        ObjectBrowserState.selected_object.contains("module"),
                        rx.vstack(
                            rx.text("Module", size="1", color="gray"),
                            rx.code(
                                ObjectBrowserState.selected_object.get("module", ""),
                            ),
                            spacing="1",
                            width="100%",
                        ),
                    ),

                    # Metadata
                    rx.cond(
                        ObjectBrowserState.selected_object.contains("full_metadata"),
                        rx.vstack(
                            rx.text("Metadata", size="2", weight="medium"),
                            rx.code(
                                ObjectBrowserState.selected_object.get("full_metadata", ""),
                            ),
                            spacing="1",
                            width="100%",
                        ),
                    ),

                    rx.separator(),

                    # Dependencies
                    rx.text("Dependencies", size="3", weight="medium"),
                    rx.cond(
                        ObjectBrowserState.selected_dependencies.length() > 0,
                        rx.vstack(
                            rx.foreach(
                                ObjectBrowserState.selected_dependencies,
                                dependency_row,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No dependencies recorded", size="2", color="gray"),
                    ),

                    spacing="3",
                    width="100%",
                ),
            ),
            width="100%",
        ),
    )


def object_browser_page() -> rx.Component:
    """
    Admin page: Object Browser

    Browse all registered objects across apps, filter by type/app,
    inspect metadata and dependencies.
    """
    return admin_layout(
        rx.vstack(
            # Page header
            rx.hstack(
                rx.heading("Object Browser", size="6"),
                rx.spacer(),
                rx.button(
                    "Refresh",
                    on_click=ObjectBrowserState.load_objects,
                    variant="outline",
                    size="2",
                ),
                width="100%",
            ),

            # Summary stats row
            rx.hstack(
                stat_card("Total Objects", ObjectBrowserState.stats.get("total", "0")),
                stat_card("Types", ObjectBrowserState.stats.get("types", "0")),
                stat_card("Apps", ObjectBrowserState.stats.get("apps", "0")),
                spacing="3",
                width="100%",
            ),

            # Filters bar
            rx.hstack(
                rx.select(
                    ObjectBrowserState.type_options,
                    value=ObjectBrowserState.type_filter,
                    on_change=ObjectBrowserState.set_type_filter,
                    placeholder="Object type",
                    size="2",
                ),
                rx.select(
                    ObjectBrowserState.app_options,
                    value=ObjectBrowserState.app_filter,
                    on_change=ObjectBrowserState.set_app_filter,
                    placeholder="App",
                    size="2",
                ),
                rx.input(
                    placeholder="Search objects…",
                    value=ObjectBrowserState.search_query,
                    on_change=ObjectBrowserState.set_search,
                    on_key_down=ObjectBrowserState.handle_search_key,
                    size="2",
                    width="300px",
                ),
                rx.button(
                    "Search",
                    on_click=ObjectBrowserState.search_objects,
                    size="2",
                    variant="soft",
                ),
                rx.spacer(),
                rx.text(
                    f"{ObjectBrowserState.total_objects} objects",
                    size="2",
                    color="gray",
                ),
                spacing="3",
                width="100%",
                align="center",
            ),

            # Objects table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Object Ref"),
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("App"),
                        rx.table.column_header_cell("Permissions"),
                        rx.table.column_header_cell("Description"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        ObjectBrowserState.objects,
                        object_row,
                    ),
                ),
                width="100%",
            ),

            # Detail panel
            object_detail_panel(),

            spacing="4",
            width="100%",
            padding="4",
            on_mount=ObjectBrowserState.load_objects,
        ),
    )
