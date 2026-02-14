"""
AppOS Admin Console — App Management Page

Route: /admin/apps
Purpose: Register, configure, and manage apps.
Design ref: AppOS_Design.md §5.4 (App), §13 (Admin Console)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


def apps_page() -> rx.Component:
    """App management page — list, register, configure, deactivate apps."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Apps", size="6"),
                rx.spacer(),
                rx.dialog.root(
                    rx.dialog.trigger(rx.button("Register App", size="2")),
                    rx.dialog.content(
                        rx.dialog.title("Register New App"),
                        rx.form(
                            rx.vstack(
                                _form_field("App Name", "name"),
                                _form_field("Short Name", "short_name",
                                            placeholder="e.g., crm"),
                                _form_field("Version", "version",
                                            placeholder="1.0.0"),
                                rx.text("Description", size="2", weight="bold"),
                                rx.text_area(
                                    name="description",
                                    placeholder="Brief description of the app",
                                    rows=3,
                                ),
                                rx.hstack(
                                    rx.dialog.close(
                                        rx.button("Cancel", variant="outline"),
                                    ),
                                    rx.button("Register", type="submit"),
                                    spacing="3",
                                    justify="end",
                                    width="100%",
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            on_submit=AdminState.create_app,
                        ),
                    ),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Apps table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Short Name"),
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Version"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Objects"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AdminState.apps,
                        _app_row,
                    ),
                ),
                width="100%",
            ),
            # No apps message
            rx.cond(
                AdminState.apps.length() == 0,
                rx.callout(
                    "No apps registered yet. Use 'Register App' or run "
                    "'appos new-app <name>' from the CLI.",
                    icon="info",
                ),
                rx.fragment(),
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=AdminState.load_apps,
        ),
    )


def _app_row(app: dict) -> rx.Component:
    """Render a single app row."""
    return rx.table.row(
        rx.table.cell(
            rx.code(app["short_name"], size="2"),
        ),
        rx.table.cell(rx.text(app["name"], weight="bold")),
        rx.table.cell(
            rx.badge(app["version"], variant="outline"),
        ),
        rx.table.cell(
            rx.cond(
                app["is_active"],
                rx.badge("Active", color_scheme="green"),
                rx.badge("Disabled", color_scheme="red"),
            ),
        ),
        rx.table.cell(
            rx.text("—", size="2", color="gray"),
        ),
        rx.table.cell(
            rx.hstack(
                rx.button("Configure", size="1", variant="outline"),
                rx.button("Objects", size="1", variant="outline"),
                spacing="2",
            ),
        ),
    )


def _form_field(
    label: str,
    name: str,
    type: str = "text",
    placeholder: str = "",
) -> rx.Component:
    """Render a labeled form field."""
    return rx.vstack(
        rx.text(label, size="2", weight="bold"),
        rx.input(
            name=name,
            type=type,
            required=True,
            size="2",
            placeholder=placeholder,
        ),
        spacing="1",
        width="100%",
    )
