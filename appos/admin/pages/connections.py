"""
AppOS Admin Console — Connected Systems Management Page

Route: /admin/connections
Purpose: Manage Connected Systems (DB, API, FTP, SMTP), credentials,
         environment overrides, and health checks.
Design ref: AppOS_Design.md §5.5 (Connected System), §13 (Admin Console)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class ConnectionsState(rx.State):
    """
    State for the Connected Systems management page.

    Manages:
    - Connected Systems list (from DB + registry)
    - Credential display (masked) and editing
    - Health check status
    - Environment override preview
    """

    # Connected systems list
    connections: list[dict] = []

    # Selected connection details
    selected_connection: str = ""
    connection_detail: dict = {}
    health_status: str = "unknown"
    health_last_check: str = ""

    # Create form state
    create_error: str = ""

    def load_connections(self) -> None:
        """Load all Connected Systems from the database."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import ConnectedSystem

            session = runtime._db_session_factory()
            try:
                systems = (
                    session.query(ConnectedSystem)
                    .order_by(ConnectedSystem.name)
                    .all()
                )
                self.connections = [
                    {
                        "id": str(cs.id),
                        "name": cs.name,
                        "type": cs.type,
                        "base_url": cs.base_url or "—",
                        "is_active": cs.is_active,
                        "auth_type": cs.auth_type or "none",
                    }
                    for cs in systems
                ]
            finally:
                session.close()
        except Exception as e:
            self.connections = []

    def select_connection(self, name: str) -> None:
        """Select a connection to view details."""
        self.selected_connection = name
        self._load_connection_detail()

    def _load_connection_detail(self) -> None:
        """Load full detail for the selected connection."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import ConnectedSystem

            session = runtime._db_session_factory()
            try:
                cs = (
                    session.query(ConnectedSystem)
                    .filter(ConnectedSystem.name == self.selected_connection)
                    .first()
                )
                if cs is None:
                    self.connection_detail = {}
                    return

                self.connection_detail = {
                    "name": cs.name,
                    "type": cs.type,
                    "base_url": cs.base_url or "",
                    "auth_type": cs.auth_type or "none",
                    "timeout_seconds": str(cs.timeout_seconds or 30),
                    "max_retries": str(cs.max_retries or 3),
                    "is_active": cs.is_active,
                    "description": cs.description or "",
                    "has_credentials": bool(cs.encrypted_credentials),
                }
            finally:
                session.close()

            # Check health
            self._check_health()

        except Exception:
            self.connection_detail = {}

    def _check_health(self) -> None:
        """Run a health check for the selected connection."""
        try:
            from appos.engine.health import get_health_service

            service = get_health_service()
            result = service.check(self.selected_connection)
            if result:
                self.health_status = result.status.value
                self.health_last_check = (
                    result.checked_at.strftime("%H:%M:%S")
                    if result.checked_at
                    else "—"
                )
            else:
                self.health_status = "unknown"
                self.health_last_check = "—"
        except Exception:
            self.health_status = "unknown"
            self.health_last_check = "—"

    def create_connection(self, form_data: dict) -> None:
        """Create a new Connected System from form data."""
        self.create_error = ""

        name = form_data.get("name", "").strip()
        cs_type = form_data.get("type", "rest_api")
        base_url = form_data.get("base_url", "").strip()
        auth_type = form_data.get("auth_type", "none")

        if not name:
            self.create_error = "Name is required"
            return

        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                self.create_error = "Platform not initialized"
                return

            from appos.db.platform_models import ConnectedSystem

            session = runtime._db_session_factory()
            try:
                # Check for duplicate
                existing = (
                    session.query(ConnectedSystem)
                    .filter(ConnectedSystem.name == name)
                    .first()
                )
                if existing:
                    self.create_error = f"Connected System '{name}' already exists"
                    return

                cs = ConnectedSystem(
                    name=name,
                    type=cs_type,
                    base_url=base_url or None,
                    auth_type=auth_type,
                    is_active=True,
                )
                session.add(cs)
                session.commit()
            finally:
                session.close()

            # Reload list
            self.load_connections()

        except Exception as e:
            self.create_error = str(e)

    def toggle_active(self) -> None:
        """Toggle the active status of the selected connection."""
        if not self.selected_connection:
            return

        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import ConnectedSystem

            session = runtime._db_session_factory()
            try:
                cs = (
                    session.query(ConnectedSystem)
                    .filter(ConnectedSystem.name == self.selected_connection)
                    .first()
                )
                if cs:
                    cs.is_active = not cs.is_active
                    session.commit()
            finally:
                session.close()

            self.load_connections()
            self._load_connection_detail()
        except Exception:
            pass


def connections_page() -> rx.Component:
    """Connected Systems management page."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Connected Systems", size="6"),
                rx.spacer(),
                rx.dialog.root(
                    rx.dialog.trigger(rx.button("New Connection", size="2")),
                    rx.dialog.content(
                        rx.dialog.title("New Connected System"),
                        rx.form(
                            rx.vstack(
                                _form_field("Name", "name", placeholder="e.g., stripe_api"),
                                rx.vstack(
                                    rx.text("Type", size="2", weight="bold"),
                                    rx.select(
                                        ["rest_api", "database", "ftp", "smtp",
                                         "soap", "graphql", "custom"],
                                        name="type",
                                        default_value="rest_api",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                _form_field("Base URL", "base_url",
                                            placeholder="https://api.example.com"),
                                rx.vstack(
                                    rx.text("Auth Type", size="2", weight="bold"),
                                    rx.select(
                                        ["none", "basic", "api_key", "oauth2",
                                         "certificate"],
                                        name="auth_type",
                                        default_value="none",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.cond(
                                    ConnectionsState.create_error != "",
                                    rx.callout(
                                        ConnectionsState.create_error,
                                        icon="alert-circle",
                                        color_scheme="red",
                                    ),
                                    rx.fragment(),
                                ),
                                rx.hstack(
                                    rx.dialog.close(
                                        rx.button("Cancel", variant="outline"),
                                    ),
                                    rx.button("Create", type="submit"),
                                    spacing="3",
                                    justify="end",
                                    width="100%",
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            on_submit=ConnectionsState.create_connection,
                        ),
                    ),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            rx.hstack(
                # Left: connections list
                rx.box(
                    _connections_list(),
                    width="300px",
                    min_width="300px",
                    border_right="1px solid var(--gray-5)",
                    overflow_y="auto",
                    height="calc(100vh - 200px)",
                ),
                # Right: connection detail
                rx.box(
                    _connection_detail(),
                    flex="1",
                    overflow_y="auto",
                    padding_left="4",
                    height="calc(100vh - 200px)",
                ),
                width="100%",
                spacing="0",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=ConnectionsState.load_connections,
        ),
    )


def _connections_list() -> rx.Component:
    """Left panel — list of all Connected Systems."""
    return rx.vstack(
        rx.text("Systems", size="3", weight="bold", padding="2"),
        rx.foreach(
            ConnectionsState.connections,
            _connection_item,
        ),
        rx.cond(
            ConnectionsState.connections.length() == 0,
            rx.text(
                "No Connected Systems yet.\n"
                "Create one or define @connected_system in code.",
                size="1",
                color="gray",
                padding="2",
            ),
            rx.fragment(),
        ),
        spacing="1",
        width="100%",
        padding="2",
    )


def _connection_item(conn: dict) -> rx.Component:
    """A single connection in the left sidebar."""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.icon("cable", size=14),
                    rx.text(conn["name"], weight="bold", size="2"),
                    spacing="2",
                ),
                rx.hstack(
                    rx.badge(conn["type"], size="1", variant="outline"),
                    rx.cond(
                        conn["is_active"],
                        rx.box(
                            width="8px", height="8px",
                            border_radius="50%",
                            background="var(--green-9)",
                        ),
                        rx.box(
                            width="8px", height="8px",
                            border_radius="50%",
                            background="var(--red-9)",
                        ),
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="0",
            ),
            width="100%",
        ),
        padding="2",
        border_radius="6px",
        cursor="pointer",
        width="100%",
        _hover={"background": "var(--gray-4)"},
        on_click=ConnectionsState.select_connection(conn["name"]),
    )


def _connection_detail() -> rx.Component:
    """Right panel — detailed view of selected connection."""
    return rx.cond(
        ConnectionsState.selected_connection != "",
        rx.vstack(
            # Header
            rx.hstack(
                rx.heading(ConnectionsState.selected_connection, size="4"),
                rx.spacer(),
                _health_badge(),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Connection details card
            rx.card(
                rx.vstack(
                    rx.text("Connection Details", weight="bold", size="3"),
                    _detail_row("Type", ConnectionsState.connection_detail["type"]),
                    _detail_row("Base URL",
                                ConnectionsState.connection_detail["base_url"]),
                    _detail_row("Auth Type",
                                ConnectionsState.connection_detail["auth_type"]),
                    _detail_row("Timeout",
                                ConnectionsState.connection_detail["timeout_seconds"]
                                + "s"),
                    _detail_row("Max Retries",
                                ConnectionsState.connection_detail["max_retries"]),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
            # Credentials card
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.text("Credentials", weight="bold", size="3"),
                        rx.spacer(),
                        rx.button("Edit", size="1", variant="outline"),
                        rx.button("Rotate", size="1", variant="outline",
                                  color_scheme="orange"),
                        width="100%",
                        align="center",
                    ),
                    rx.cond(
                        ConnectionsState.connection_detail["has_credentials"],
                        rx.hstack(
                            rx.icon("lock", size=14, color="green"),
                            rx.text("Credentials configured (encrypted)",
                                    size="2", color="green"),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.icon("unlock", size=14, color="orange"),
                            rx.text("No credentials configured", size="2",
                                    color="orange"),
                            spacing="2",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
            # Actions
            rx.hstack(
                rx.button(
                    rx.cond(
                        ConnectionsState.connection_detail["is_active"],
                        "Deactivate",
                        "Activate",
                    ),
                    size="2",
                    variant="outline",
                    color_scheme=rx.cond(
                        ConnectionsState.connection_detail["is_active"],
                        "red",
                        "green",
                    ),
                    on_click=ConnectionsState.toggle_active,
                ),
                rx.button("Test Connection", size="2", variant="outline"),
                spacing="3",
            ),
            spacing="4",
            width="100%",
        ),
        # No connection selected
        rx.center(
            rx.vstack(
                rx.icon("cable", size=48, color="gray"),
                rx.text(
                    "Select a Connected System to view details.",
                    size="2",
                    color="gray",
                ),
                align="center",
                spacing="3",
            ),
            height="400px",
        ),
    )


def _health_badge() -> rx.Component:
    """Health status badge."""
    return rx.hstack(
        rx.cond(
            ConnectionsState.health_status == "healthy",
            rx.badge("Healthy", color_scheme="green"),
            rx.cond(
                ConnectionsState.health_status == "degraded",
                rx.badge("Degraded", color_scheme="yellow"),
                rx.cond(
                    ConnectionsState.health_status == "unhealthy",
                    rx.badge("Unhealthy", color_scheme="red"),
                    rx.badge("Unknown", color_scheme="gray"),
                ),
            ),
        ),
        rx.text(
            ConnectionsState.health_last_check,
            size="1",
            color="gray",
        ),
        spacing="2",
        align="center",
    )


def _detail_row(label: str, value: rx.Var) -> rx.Component:
    """A label-value row in the detail card."""
    return rx.hstack(
        rx.text(label, size="2", color="gray", min_width="100px"),
        rx.text(value, size="2"),
        spacing="3",
        width="100%",
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
