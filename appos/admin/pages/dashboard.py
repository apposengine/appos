"""
AppOS Admin Console — Dashboard Page

Route: /admin/dashboard
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


def dashboard_page() -> rx.Component:
    """Admin dashboard — platform overview."""
    return admin_layout(
        rx.vstack(
            rx.heading("Dashboard", size="6"),
            rx.text(f"Welcome, {AdminState.full_name}", color="gray"),
            rx.divider(),
            # Stats cards
            rx.grid(
                _stat_card("Users", "Total registered users", "users"),
                _stat_card("Groups", "Active groups", "shield"),
                _stat_card("Apps", "Registered applications", "layout"),
                _stat_card("Objects", "Total registered objects", "box"),
                columns="4",
                spacing="4",
                width="100%",
            ),
            rx.divider(),
            rx.heading("Quick Actions", size="4"),
            rx.hstack(
                rx.link(rx.button("Manage Users", variant="outline"), href="/admin/users"),
                rx.link(rx.button("Manage Groups", variant="outline"), href="/admin/groups"),
                rx.link(rx.button("View Logs", variant="outline"), href="/admin/logs"),
                spacing="3",
            ),
            spacing="5",
            width="100%",
            padding="6",
        ),
    )


def _stat_card(title: str, description: str, icon: str) -> rx.Component:
    """Render a stats card."""
    return rx.card(
        rx.vstack(
            rx.text(title, weight="bold", size="3"),
            rx.text(description, color="gray", size="2"),
            spacing="1",
        ),
    )
