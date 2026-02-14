"""
AppOS Admin Console — Settings Page

Route: /admin/settings
Purpose: View and edit platform configuration (DB, YAML, cache TTL,
         session timeout, log retention).
Design ref: AppOS_Design.md §13 (Admin Console → Settings)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class SettingsState(rx.State):
    """State for the platform settings page."""

    # Config entries loaded from platform_config table
    settings: list[dict] = []

    # Editable form values (flattened for simplicity)
    edit_key: str = ""
    edit_value: str = ""
    save_error: str = ""
    save_success: str = ""

    # Category filter
    category_filter: str = "all"
    categories: list[str] = ["all", "database", "redis", "logging", "session", "security"]

    def load_settings(self) -> None:
        """Load platform settings from DB."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import PlatformConfigEntry

            session = runtime._db_session_factory()
            try:
                query = session.query(PlatformConfigEntry).order_by(
                    PlatformConfigEntry.category, PlatformConfigEntry.key
                )
                if self.category_filter and self.category_filter != "all":
                    query = query.filter(
                        PlatformConfigEntry.category == self.category_filter
                    )
                entries = query.all()
                self.settings = [
                    {
                        "id": e.id,
                        "key": e.key,
                        "value": str(e.value) if e.value is not None else "",
                        "category": e.category,
                        "updated_at": (
                            e.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                            if e.updated_at
                            else "—"
                        ),
                    }
                    for e in entries
                ]
            finally:
                session.close()
        except Exception:
            self.settings = []

    def set_category_filter(self, value: str) -> None:
        """Change category filter and reload."""
        self.category_filter = value
        self.load_settings()

    def start_edit(self, key: str, value: str) -> None:
        """Begin editing a setting."""
        self.edit_key = key
        self.edit_value = value
        self.save_error = ""
        self.save_success = ""

    def save_setting(self, form_data: dict) -> None:
        """Save an edited setting back to the DB."""
        import json
        self.save_error = ""
        self.save_success = ""

        key = form_data.get("key", "").strip()
        raw_value = form_data.get("value", "").strip()

        if not key:
            self.save_error = "Key is required"
            return

        try:
            # Try to parse as JSON, fall back to string
            try:
                parsed = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError):
                parsed = raw_value

            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                self.save_error = "Platform not initialized"
                return

            from appos.db.platform_models import PlatformConfigEntry
            from datetime import datetime, timezone

            session = runtime._db_session_factory()
            try:
                entry = session.query(PlatformConfigEntry).filter_by(key=key).first()
                if entry:
                    entry.value = parsed
                    entry.updated_at = datetime.now(timezone.utc)
                else:
                    category = form_data.get("category", "general")
                    entry = PlatformConfigEntry(
                        key=key, value=parsed, category=category
                    )
                    session.add(entry)
                session.commit()
                self.save_success = f"Saved: {key}"
            finally:
                session.close()

            self.load_settings()
        except Exception as e:
            self.save_error = str(e)

    def create_setting(self, form_data: dict) -> None:
        """Create a new platform config entry."""
        import json
        self.save_error = ""

        key = form_data.get("key", "").strip()
        raw_value = form_data.get("value", "").strip()
        category = form_data.get("category", "general").strip()

        if not key:
            self.save_error = "Key is required"
            return

        try:
            try:
                parsed = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError):
                parsed = raw_value

            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                self.save_error = "Platform not initialized"
                return

            from appos.db.platform_models import PlatformConfigEntry

            session = runtime._db_session_factory()
            try:
                existing = session.query(PlatformConfigEntry).filter_by(key=key).first()
                if existing:
                    self.save_error = f"Key '{key}' already exists"
                    return
                entry = PlatformConfigEntry(key=key, value=parsed, category=category)
                session.add(entry)
                session.commit()
            finally:
                session.close()

            self.load_settings()
        except Exception as e:
            self.save_error = str(e)


def settings_page() -> rx.Component:
    """Platform settings — view and edit config entries."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Settings", size="6"),
                rx.spacer(),
                rx.select(
                    SettingsState.categories,
                    value=SettingsState.category_filter,
                    on_change=SettingsState.set_category_filter,
                    size="2",
                ),
                rx.dialog.root(
                    rx.dialog.trigger(rx.button("Add Setting", size="2")),
                    rx.dialog.content(
                        rx.dialog.title("New Setting"),
                        rx.form(
                            rx.vstack(
                                _form_field("Key", "key"),
                                _form_field("Value", "value"),
                                rx.select(
                                    ["general", "database", "redis", "logging",
                                     "session", "security"],
                                    name="category",
                                    default_value="general",
                                ),
                                rx.cond(
                                    SettingsState.save_error,
                                    rx.callout(
                                        SettingsState.save_error,
                                        icon="alert_triangle",
                                        color_scheme="red",
                                        size="1",
                                    ),
                                ),
                                rx.hstack(
                                    rx.dialog.close(
                                        rx.button("Cancel", variant="outline")
                                    ),
                                    rx.button("Create", type="submit"),
                                    spacing="3",
                                    justify="end",
                                    width="100%",
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            on_submit=SettingsState.create_setting,
                        ),
                    ),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Success / error banners
            rx.cond(
                SettingsState.save_success,
                rx.callout(
                    SettingsState.save_success,
                    icon="check",
                    color_scheme="green",
                    size="1",
                ),
            ),
            # Settings table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Key"),
                        rx.table.column_header_cell("Value"),
                        rx.table.column_header_cell("Category"),
                        rx.table.column_header_cell("Updated"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        SettingsState.settings,
                        _setting_row,
                    ),
                ),
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=SettingsState.load_settings,
        ),
    )


def _setting_row(entry: dict) -> rx.Component:
    """Render a single settings row."""
    return rx.table.row(
        rx.table.cell(rx.text(entry["key"], weight="bold", size="2")),
        rx.table.cell(
            rx.code(entry["value"], size="1"),
        ),
        rx.table.cell(rx.badge(entry["category"], color_scheme="blue")),
        rx.table.cell(rx.text(entry["updated_at"], size="1", color="gray")),
        rx.table.cell(
            rx.button(
                "Edit",
                size="1",
                variant="outline",
                on_click=SettingsState.start_edit(entry["key"], entry["value"]),
            ),
        ),
    )


def _form_field(label: str, name: str, type: str = "text") -> rx.Component:
    """Render a labeled form field."""
    return rx.vstack(
        rx.text(label, size="2", weight="bold"),
        rx.input(name=name, type=type, required=True, size="2"),
        spacing="1",
        width="100%",
    )
