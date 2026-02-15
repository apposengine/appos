"""
AppOS Admin Console — Groups Management Page

Route: /admin/groups
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


def groups_page() -> rx.Component:
    """Group management page — list, create, edit, assign users/apps."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Groups", size="6"),
                rx.spacer(),
                rx.dialog.root(
                    rx.dialog.trigger(rx.button("Create Group", size="2")),
                    rx.dialog.content(
                        rx.dialog.title("Create New Group"),
                        rx.form(
                            rx.vstack(
                                _form_field("Name", "name"),
                                _form_field("Description", "description"),
                                rx.select(
                                    ["security", "team", "app"],
                                    placeholder="Group Type",
                                    name="type",
                                    default_value="security",
                                ),
                                rx.hstack(
                                    rx.dialog.close(rx.button("Cancel", variant="outline")),
                                    rx.button("Create", type="submit"),
                                    spacing="3",
                                    justify="end",
                                    width="100%",
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            on_submit=AdminState.create_group,
                            reset_on_submit=True,
                        ),
                    ),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Groups table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("Description"),
                        rx.table.column_header_cell("Active"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AdminState.groups,
                        _group_row,
                    ),
                ),
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=AdminState.load_groups,
        ),
    )


def _group_row(group: dict) -> rx.Component:
    """Render a single group row."""
    return rx.table.row(
        rx.table.cell(rx.text(group["name"], weight="bold")),
        rx.table.cell(rx.badge(group["type"])),
        rx.table.cell(group["description"]),
        rx.table.cell(
            rx.cond(
                group["is_active"],
                rx.badge("Active", color_scheme="green"),
                rx.badge("Disabled", color_scheme="red"),
            ),
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.cond(group["is_active"], "Disable", "Enable"),
                    size="1",
                    variant="outline",
                    color_scheme=rx.cond(group["is_active"], "red", "green"),
                    on_click=AdminState.toggle_group_active(group["id"]),
                ),
                rx.button("Members", size="1", variant="outline"),
                spacing="2",
            ),
        ),
    )


def _form_field(label: str, name: str) -> rx.Component:
    """Render a labeled form field."""
    return rx.vstack(
        rx.text(label, size="2", weight="bold"),
        rx.input(name=name, required=True, size="2"),
        spacing="1",
        width="100%",
    )
