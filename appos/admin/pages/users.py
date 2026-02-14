"""
AppOS Admin Console — Users Management Page

Route: /admin/users
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


def users_page() -> rx.Component:
    """User management page — list, create, edit, deactivate users."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Users", size="6"),
                rx.spacer(),
                rx.dialog.root(
                    rx.dialog.trigger(rx.button("Create User", size="2")),
                    rx.dialog.content(
                        rx.dialog.title("Create New User"),
                        rx.form(
                            rx.vstack(
                                _form_field("Username", "username"),
                                _form_field("Email", "email", type="email"),
                                _form_field("Full Name", "full_name"),
                                _form_field("Password", "password", type="password"),
                                rx.select(
                                    ["basic", "system_admin", "service_account"],
                                    placeholder="User Type",
                                    name="user_type",
                                    default_value="basic",
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
                        ),
                    ),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Users table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Username"),
                        rx.table.column_header_cell("Email"),
                        rx.table.column_header_cell("Full Name"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("Active"),
                        rx.table.column_header_cell("Last Login"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AdminState.users,
                        _user_row,
                    ),
                ),
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=AdminState.load_users,
        ),
    )


def _user_row(user: dict) -> rx.Component:
    """Render a single user row."""
    return rx.table.row(
        rx.table.cell(rx.text(user["username"], weight="bold")),
        rx.table.cell(user["email"]),
        rx.table.cell(user["full_name"]),
        rx.table.cell(
            rx.badge(user["user_type"], color_scheme=_type_color(user["user_type"])),
        ),
        rx.table.cell(
            rx.cond(
                user["is_active"],
                rx.badge("Active", color_scheme="green"),
                rx.badge("Disabled", color_scheme="red"),
            ),
        ),
        rx.table.cell(rx.text(user["last_login"], size="1", color="gray")),
        rx.table.cell(
            rx.hstack(
                rx.button("Edit", size="1", variant="outline"),
                spacing="2",
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


def _type_color(user_type: str) -> str:
    """Get badge color for user type."""
    colors = {
        "system_admin": "red",
        "basic": "blue",
        "service_account": "orange",
    }
    return colors.get(user_type, "gray")
