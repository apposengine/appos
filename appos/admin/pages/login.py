"""
AppOS Admin Console — Login Page

Route: /admin/login
"""

import reflex as rx

from appos.admin.state import AdminState


def login_page() -> rx.Component:
    """Admin login page."""
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("AppOS Admin", size="6", text_align="center"),
                rx.text("Sign in to the admin console", color="gray", text_align="center"),
                rx.divider(),
                rx.form(
                    rx.vstack(
                        rx.text("Username", size="2", weight="bold"),
                        rx.input(
                            placeholder="admin",
                            name="username",
                            required=True,
                            size="3",
                        ),
                        rx.text("Password", size="2", weight="bold"),
                        rx.input(
                            placeholder="••••••••",
                            name="password",
                            type="password",
                            required=True,
                            size="3",
                        ),
                        rx.cond(
                            AdminState.login_error != "",
                            rx.callout(
                                AdminState.login_error,
                                icon="triangle_alert",
                                color_scheme="red",
                                size="1",
                            ),
                        ),
                        rx.button(
                            "Sign In",
                            type="submit",
                            size="3",
                            width="100%",
                            loading=AdminState.is_loading,
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    on_submit=AdminState.login,
                    width="100%",
                ),
                spacing="4",
                width="100%",
                padding="6",
            ),
            width="400px",
        ),
        min_height="100vh",
    )
