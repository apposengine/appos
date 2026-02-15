"""
AppOS Admin Console — Translation Sets Page

Route: /admin/translations
Purpose: View and manage @translation_set objects across apps.
Design ref: AppOS_Design.md §13 (Admin Console → Translation Sets)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class TranslationsState(rx.State):
    """State for the translation sets management page."""

    # Translation sets data
    translation_sets: list[dict] = []
    total_sets: int = 0
    selected_set: dict = {}
    selected_locale: str = ""

    # Filters
    search_query: str = ""
    filter_app: str = ""
    filter_locale: str = ""

    # Feedback
    action_message: str = ""

    def load_translation_sets(self) -> None:
        """Load all @translation_set objects from the registry."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            ts_objects = runtime.registry.get_by_type("translation_set")
            sets = []
            for obj in ts_objects:
                meta = obj.metadata or {}
                handler = obj.handler
                # Call handler to get the actual translations
                translations = handler() if callable(handler) else {}

                locales = list(translations.keys()) if isinstance(translations, dict) else []
                total_keys = sum(
                    len(v) for v in translations.values() if isinstance(v, dict)
                )

                sets.append({
                    "object_ref": obj.object_ref,
                    "name": obj.name,
                    "app_name": obj.app_name or "platform",
                    "locales": locales,
                    "total_keys": total_keys,
                    "is_active": obj.is_active,
                    "module_path": obj.module_path,
                })

            # Apply filters
            if self.filter_app:
                sets = [s for s in sets if s["app_name"] == self.filter_app]
            if self.search_query:
                q = self.search_query.lower()
                sets = [s for s in sets if q in s["name"].lower() or q in s["app_name"].lower()]

            self.translation_sets = sets
            self.total_sets = len(sets)

        except Exception as e:
            self.action_message = f"Error loading translation sets: {e}"

    def select_set(self, object_ref: str) -> None:
        """Select a translation set to view details."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            obj = runtime.registry.resolve(object_ref)
            if obj is None:
                self.action_message = f"Translation set not found: {object_ref}"
                return

            handler = obj.handler
            translations = handler() if callable(handler) else {}

            self.selected_set = {
                "object_ref": obj.object_ref,
                "name": obj.name,
                "app_name": obj.app_name or "platform",
                "translations": translations,
            }
        except Exception as e:
            self.action_message = f"Error: {e}"

    def set_search(self, value: str) -> None:
        """Update search query and reload."""
        self.search_query = value
        self.load_translation_sets()

    def set_filter_app(self, value: str) -> None:
        """Filter by app name."""
        self.filter_app = value
        self.load_translation_sets()


def translations_list() -> rx.Component:
    """Table listing all translation sets."""
    return rx.box(
        rx.heading("Translation Sets", size="6"),
        rx.text(f"Manage @translation_set objects across all apps."),
        rx.hstack(
            rx.input(
                placeholder="Search...",
                on_change=TranslationsState.set_search,
                width="300px",
            ),
            rx.select(
                ["", "crm", "platform"],
                placeholder="Filter by app",
                on_change=TranslationsState.set_filter_app,
            ),
            spacing="4",
            margin_bottom="16px",
        ),
        rx.cond(
            TranslationsState.total_sets > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("App"),
                        rx.table.column_header_cell("Locales"),
                        rx.table.column_header_cell("Keys"),
                        rx.table.column_header_cell("Status"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        TranslationsState.translation_sets,
                        lambda ts: rx.table.row(
                            rx.table.cell(
                                rx.link(
                                    ts["name"],
                                    on_click=TranslationsState.select_set(ts["object_ref"]),
                                    cursor="pointer",
                                ),
                            ),
                            rx.table.cell(ts["app_name"]),
                            rx.table.cell(rx.text(ts["locales"].to(str))),
                            rx.table.cell(str(ts["total_keys"])),
                            rx.table.cell(
                                rx.cond(
                                    ts["is_active"],
                                    rx.badge("Active", color_scheme="green"),
                                    rx.badge("Inactive", color_scheme="red"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            rx.text("No translation sets found.", color="gray"),
        ),
        on_mount=TranslationsState.load_translation_sets,
    )


def translations_page() -> rx.Component:
    """Admin translations page."""
    return admin_layout(translations_list())
