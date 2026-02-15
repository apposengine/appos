"""
AppOS Admin Console — Theme Editor Page

Route: /admin/themes
Purpose: Per-app theme editing (colors, fonts, border radius).
Design ref: AppOS_Design.md §13 (Admin Console → Theme Editor)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class ThemesState(rx.State):
    """State for the per-app theme editor page."""

    # Apps for theme selection
    apps: list[dict] = []
    selected_app: str = ""

    # Current theme (JSON from App.theme column)
    theme: dict = {}

    # Editable fields
    primary_color: str = "#3b82f6"
    accent_color: str = "#8b5cf6"
    background_color: str = "#ffffff"
    text_color: str = "#111827"
    font_family: str = "Inter, sans-serif"
    border_radius: str = "8"

    save_message: str = ""

    @rx.var
    def app_names(self) -> list[str]:
        """Computed var: list of app short names for the select dropdown."""
        return [app["short_name"] for app in self.apps]

    def load_apps(self) -> None:
        """Load apps list for theme selection."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import App

            session = runtime._db_session_factory()
            try:
                apps = session.query(App).filter(App.is_active == True).order_by(App.short_name).all()
                self.apps = [
                    {
                        "short_name": a.short_name,
                        "name": a.name,
                        "theme": a.theme or {},
                    }
                    for a in apps
                ]
            finally:
                session.close()
        except Exception:
            self.apps = []

    def select_app(self, app_name: str) -> None:
        """Select an app and load its theme."""
        self.selected_app = app_name
        self.save_message = ""

        # Find theme in loaded apps
        for app in self.apps:
            if app["short_name"] == app_name:
                theme = app.get("theme", {})
                self.theme = theme
                self.primary_color = theme.get("primary_color", "#3b82f6")
                self.accent_color = theme.get("accent_color", "#8b5cf6")
                self.background_color = theme.get("background_color", "#ffffff")
                self.text_color = theme.get("text_color", "#111827")
                self.font_family = theme.get("font_family", "Inter, sans-serif")
                self.border_radius = str(theme.get("border_radius", "8"))
                return

    def save_theme(self, form_data: dict) -> None:
        """Save theme for the selected app."""
        if not self.selected_app:
            self.save_message = "No app selected"
            return

        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                self.save_message = "Platform not initialized"
                return

            from appos.db.platform_models import App

            new_theme = {
                "primary_color": form_data.get("primary_color", self.primary_color),
                "accent_color": form_data.get("accent_color", self.accent_color),
                "background_color": form_data.get("background_color", self.background_color),
                "text_color": form_data.get("text_color", self.text_color),
                "font_family": form_data.get("font_family", self.font_family),
                "border_radius": form_data.get("border_radius", self.border_radius),
            }

            session = runtime._db_session_factory()
            try:
                app = session.query(App).filter_by(short_name=self.selected_app).first()
                if app:
                    app.theme = new_theme
                    session.commit()
                    self.save_message = f"Theme saved for {self.selected_app}"
                    self.theme = new_theme
                else:
                    self.save_message = f"App '{self.selected_app}' not found"
            finally:
                session.close()

            self.load_apps()
        except Exception as e:
            self.save_message = f"Error: {e}"


def themes_page() -> rx.Component:
    """Per-app theme editor page."""
    return admin_layout(
        rx.vstack(
            rx.heading("Theme Editor", size="6"),
            rx.text("Customise the look and feel per application.", color="gray"),
            rx.divider(),
            # App selector
            rx.hstack(
                rx.text("Application:", weight="bold", size="2"),
                rx.select(
                    ThemesState.app_names,
                    placeholder="Select an app…",
                    value=ThemesState.selected_app,
                    on_change=ThemesState.select_app,
                    size="2",
                ),
                spacing="3",
                align="center",
            ),
            rx.divider(),
            # Theme editor form (shown when app selected)
            rx.cond(
                ThemesState.selected_app,
                _theme_form(),
                rx.text("Select an application above to edit its theme.", color="gray"),
            ),
            # Save message
            rx.cond(
                ThemesState.save_message,
                rx.callout(
                    ThemesState.save_message,
                    icon="palette",
                    color_scheme="green",
                    size="1",
                ),
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=ThemesState.load_apps,
        ),
    )


def _theme_form() -> rx.Component:
    """Theme editing form with color pickers and text inputs."""
    return rx.form(
        rx.grid(
            rx.vstack(
                rx.text("Primary Color", size="2", weight="bold"),
                rx.input(
                    name="primary_color",
                    default_value=ThemesState.primary_color,
                    type="color",
                    size="2",
                ),
                spacing="1",
            ),
            rx.vstack(
                rx.text("Accent Color", size="2", weight="bold"),
                rx.input(
                    name="accent_color",
                    default_value=ThemesState.accent_color,
                    type="color",
                    size="2",
                ),
                spacing="1",
            ),
            rx.vstack(
                rx.text("Background Color", size="2", weight="bold"),
                rx.input(
                    name="background_color",
                    default_value=ThemesState.background_color,
                    type="color",
                    size="2",
                ),
                spacing="1",
            ),
            rx.vstack(
                rx.text("Text Color", size="2", weight="bold"),
                rx.input(
                    name="text_color",
                    default_value=ThemesState.text_color,
                    type="color",
                    size="2",
                ),
                spacing="1",
            ),
            rx.vstack(
                rx.text("Font Family", size="2", weight="bold"),
                rx.input(
                    name="font_family",
                    default_value=ThemesState.font_family,
                    size="2",
                ),
                spacing="1",
            ),
            rx.vstack(
                rx.text("Border Radius (px)", size="2", weight="bold"),
                rx.input(
                    name="border_radius",
                    default_value=ThemesState.border_radius,
                    type="number",
                    size="2",
                ),
                spacing="1",
            ),
            columns="3",
            spacing="4",
            width="100%",
        ),
        rx.hstack(
            rx.button("Save Theme", type="submit", size="2"),
            spacing="3",
            padding_top="4",
        ),
        on_submit=ThemesState.save_theme,
        width="100%",
    )
