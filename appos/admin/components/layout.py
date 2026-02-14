"""
AppOS Admin Console — Layout component (sidebar + header).
"""

import reflex as rx

from appos.admin.state import AdminState


def admin_layout(content: rx.Component) -> rx.Component:
    """Wrap content in the admin layout with sidebar and header."""
    return rx.hstack(
        _sidebar(),
        rx.box(
            _header(),
            rx.divider(),
            content,
            flex="1",
            overflow_y="auto",
            height="100vh",
        ),
        spacing="0",
        width="100%",
        height="100vh",
        on_mount=AdminState.check_auth,
    )


def _sidebar() -> rx.Component:
    """Admin console sidebar navigation."""
    return rx.box(
        rx.vstack(
            rx.heading("AppOS", size="4", padding="4"),
            rx.divider(),
            _nav_item("Dashboard", "/admin/dashboard", "layout-dashboard"),
            _nav_item("Users", "/admin/users", "users"),
            _nav_item("Groups", "/admin/groups", "shield"),
            _nav_item("Apps", "/admin/apps", "box"),
            _nav_item("Connections", "/admin/connections", "cable"),
            rx.divider(),
            _nav_item("Records", "/admin/records", "database"),
            _nav_item("Objects", "/admin/objects", "puzzle"),
            _nav_item("Processes", "/admin/processes", "git-branch"),
            rx.divider(),
            _nav_item("Logs", "/admin/logs", "file-text"),
            _nav_item("Metrics", "/admin/metrics", "bar-chart-3"),
            _nav_item("Workers", "/admin/workers", "cpu"),
            _nav_item("Sessions", "/admin/sessions", "monitor"),
            _nav_item("Themes", "/admin/themes", "palette"),
            _nav_item("Settings", "/admin/settings", "settings"),
            spacing="1",
            padding="3",
            width="100%",
        ),
        width="220px",
        min_width="220px",
        height="100vh",
        border_right="1px solid var(--gray-5)",
        background="var(--gray-2)",
    )


def _nav_item(label: str, href: str, icon: str) -> rx.Component:
    """Render a sidebar nav item."""
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=16),
            rx.text(label, size="2"),
            spacing="2",
            padding_x="3",
            padding_y="2",
            border_radius="6px",
            width="100%",
            _hover={"background": "var(--gray-4)"},
        ),
        href=href,
        width="100%",
        underline="none",
    )


def _header() -> rx.Component:
    """Admin console top header."""
    return rx.hstack(
        rx.spacer(),
        rx.text(AdminState.username, size="2", color="gray"),
        rx.button(
            "Logout",
            size="1",
            variant="ghost",
            on_click=AdminState.logout,
        ),
        padding="3",
        width="100%",
        align="center",
    )
