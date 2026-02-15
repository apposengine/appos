"""
AppOS Reflex Bridge — Wraps all AppOS apps into a single Reflex application.

Responsibilities:
    - Register admin console routes (/admin/*)
    - Register per-app page routes (/{app_short_name}/*)
    - Register @web_api routes (/api/{app}/{version}/{path}) via Reflex's internal FastAPI
    - Apply per-app theming
    - Auth guard on every page load

Single-port architecture: One Reflex instance, URL-based routing for all apps + APIs.
Web API routes use Reflex's app.api (which IS FastAPI/Starlette under the hood).
No separate server needed.

Design refs:
    §12  UI Layer — Single-port routing, per-app theming, component hierarchy
    §5.12 Web API — /api/{app}/{ver}/{path} URL pattern
    §5.14 Page    — @page decorator + route binding
    §5.15 Site    — @site decorator + navigation hierarchy
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from appos.engine.registry import ObjectRegistryManager, RegisteredObject

logger = logging.getLogger("appos.ui.reflex_bridge")


# ---------------------------------------------------------------------------
# Navigation Structure
# ---------------------------------------------------------------------------

class NavItem:
    """A navigation menu item for an app's site."""

    def __init__(
        self,
        label: str,
        route: str,
        icon: str = "",
        children: Optional[List["NavItem"]] = None,
    ):
        self.label = label
        self.route = route
        self.icon = icon
        self.children = children or []


class SiteConfig:
    """Resolved site configuration for an app."""

    def __init__(
        self,
        name: str,
        app_name: str,
        navigation: List[NavItem],
        default_page: str = "/",
        auth_required: bool = True,
        theme: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.app_name = app_name
        self.navigation = navigation
        self.default_page = default_page
        self.auth_required = auth_required
        self.theme = theme or {}


# ---------------------------------------------------------------------------
# Route Definitions
# ---------------------------------------------------------------------------

class AppRoute:
    """A resolved route for a page within an app."""

    def __init__(
        self,
        route: str,
        title: str,
        app_name: str,
        page_ref: str,
        interface_ref: Optional[str] = None,
        requires_auth: bool = True,
        permissions: Optional[List[str]] = None,
    ):
        self.route = route
        self.title = title
        self.app_name = app_name
        self.page_ref = page_ref
        self.interface_ref = interface_ref
        self.requires_auth = requires_auth
        self.permissions = permissions or []


class APIRoute:
    """A resolved route for a @web_api endpoint."""

    def __init__(
        self,
        route: str,
        method: str,
        app_name: str,
        api_ref: str,
        api_def: RegisteredObject,
    ):
        self.route = route
        self.method = method
        self.app_name = app_name
        self.api_ref = api_ref
        self.api_def = api_def


# ---------------------------------------------------------------------------
# AppOS Reflex Application
# ---------------------------------------------------------------------------

class AppOSReflexApp:
    """
    Wraps all AppOS apps into a single Reflex application.

    Binds:
        /admin/*                → Built-in admin console pages
        /{app_short_name}/*     → Per-app pages (from @page decorators)
        /api/{app}/{ver}/{path} → Web API routes (from @web_api decorators)

    Usage (called from appos/appos.py during startup):
        bridge = AppOSReflexApp(registry=runtime.registry, runtime=runtime)
        bridge.register_all(app)   # app = Reflex rx.App instance
    """

    def __init__(
        self,
        registry: ObjectRegistryManager,
        runtime=None,   # CentralizedRuntime — for API executor
    ):
        self._registry = registry
        self._runtime = runtime
        self._app_routes: List[AppRoute] = []
        self._api_routes: List[APIRoute] = []

        self._site_configs: Dict[str, SiteConfig] = {}  # app_name → SiteConfig

    def register_all(self, reflex_app) -> None:
        """
        Register all routes on the Reflex app instance.

        Args:
            reflex_app: The rx.App instance (from Reflex).
        """
        self._build_site_configs()
        self._register_admin_routes(reflex_app)
        self._register_app_routes(reflex_app)
        self._register_api_routes(reflex_app)
        logger.info(
            f"Registered {len(self._app_routes)} page routes, "
            f"{len(self._api_routes)} API routes, "
            f"{len(self._site_configs)} site configs"
        )

    # -----------------------------------------------------------------------
    # Admin Routes
    # -----------------------------------------------------------------------

    def _register_admin_routes(self, reflex_app) -> None:
        """
        Register built-in admin console pages.

        Routes: /admin/login, /admin/dashboard, /admin/users, /admin/groups, etc.
        Defined in appos/admin/pages/ — already imported in appos.py.
        """
        # Admin routes are registered declaratively via @rx.page in admin page modules.
        # They don't need dynamic registration here.
        # This method exists for future admin route customization.
        logger.debug("Admin routes registered via @rx.page decorators in appos/admin/pages/")

    # -----------------------------------------------------------------------
    # App Page Routes
    # -----------------------------------------------------------------------

    def _register_app_routes(self, reflex_app) -> None:
        """
        Auto-register all @page objects from all active apps.

        Per Design §12:
            URL pattern: /{app_short_name}/{page_route}
            Example: /crm/customers, /finance/invoices

        Each page points to an @interface (which renders components).
        Auth guard runs on_load to validate session.
        """
        page_objects = self._registry.get_by_type("page")

        for page_def in page_objects:
            ref = page_def.object_ref
            meta = page_def.metadata
            app_name = page_def.app_name
            if not app_name:
                continue

            raw_route = meta.get("route", f"/{page_def.name}")
            if not raw_route.startswith("/"):
                raw_route = f"/{raw_route}"

            full_route = f"/{app_name}{raw_route}"
            title = meta.get("title", page_def.name.replace("_", " ").title())

            app_route = AppRoute(
                route=full_route,
                title=title,
                app_name=app_name,
                page_ref=ref,
                interface_ref=meta.get("interface"),
                requires_auth=meta.get("requires_auth", True),
                permissions=meta.get("permissions", []),
            )
            self._app_routes.append(app_route)

            # Register with Reflex
            # The actual rendering depends on InterfaceRenderer (Task 4.4)
            # For now, register a placeholder page component
            try:
                self._add_reflex_page(
                    reflex_app=reflex_app,
                    route=full_route,
                    title=title,
                    page_def=page_def,
                    app_name=app_name,
                )
            except Exception as e:
                logger.error(f"Failed to register page route {full_route}: {e}")

        logger.info(f"Registered {len(self._app_routes)} app page routes")

    def _add_reflex_page(
        self,
        reflex_app,
        route: str,
        title: str,
        page_def: RegisteredObject,
        app_name: str,
    ) -> None:
        """
        Add a single page to the Reflex app.

        Resolution order:
        1. If @page has an interface_name → use InterfaceRenderer
        2. If @page handler returns rx.Component → use directly
        3. If @page handler returns ComponentDef → render via InterfaceRenderer
        """
        import reflex as rx

        meta = page_def.metadata
        interface_ref = meta.get("interface")

        # Path 1: Page points to a named @interface → render via InterfaceRenderer
        if interface_ref:
            page_fn = self._build_interface_page(interface_ref, app_name)
            if page_fn:
                # Wrap with app layout (site navigation)
                wrapped = self._wrap_with_site_layout(page_fn, app_name)
                reflex_app.add_page(
                    wrapped,
                    route=route,
                    title=title,
                    on_load=self._get_auth_guard(page_def),
                )
                return

        # Path 2/3: Page has its own handler
        handler = page_def.handler
        if handler and callable(handler):
            # Wrap with site layout for consistent navigation
            wrapped = self._wrap_with_site_layout(handler, app_name)
            reflex_app.add_page(
                wrapped,
                route=route,
                title=title,
                on_load=self._get_auth_guard(page_def),
            )
        else:
            logger.warning(f"Page {page_def.object_ref} has no handler — skipping route {route}")

    def _build_interface_page(
        self, interface_name: str, app_name: str
    ) -> Optional[Any]:
        """
        Build a Reflex page component from a named @interface.

        Looks up the @interface in the registry, creates an InterfaceRenderer,
        and returns a page function.
        """
        from appos.decorators.interface import interface_extend_registry
        from appos.ui.renderer import InterfaceRenderer

        # Look up the interface in the registry
        interface_def = None

        # Try fully-qualified ref first
        fq_ref = f"{app_name}.interfaces.{interface_name}"
        interface_def = self._registry.resolve(fq_ref)

        # Try by name scan
        if interface_def is None:
            interfaces = self._registry.get_by_type("interface", app_name=app_name)
            for iface in interfaces:
                if iface.metadata.get("name") == interface_name or iface.name == interface_name:
                    interface_def = iface
                    break

        if interface_def is None:
            logger.error(f"Interface {interface_name} not found for app {app_name}")
            return None

        # Resolve theme
        theme = self.get_app_theme(app_name)

        def page_component() -> Any:
            renderer = InterfaceRenderer(
                interface_def=interface_def,
                theme=theme,
                app_name=app_name,
            )
            return renderer.to_reflex()

        return page_component

    def _get_auth_guard(self, page_def: RegisteredObject):
        """
        Build an on_load auth guard for a page.

        Validates session on every page load — redirects to /admin/login if invalid.
        Uses the Reflex on_load event pattern.
        """
        meta = page_def.metadata
        if meta.get("requires_auth", True) is False:
            return None

        # Return the auth check event handler from AdminState
        # This validates the session cookie on each page load
        try:
            from appos.admin.state import AdminState
            return AdminState.check_auth
        except ImportError:
            return None

    # -----------------------------------------------------------------------
    # Web API Routes (via Reflex's internal FastAPI)
    # -----------------------------------------------------------------------

    def _register_api_routes(self, reflex_app) -> None:
        """
        Register all @web_api objects as HTTP endpoints via Reflex's internal FastAPI.

        Per Design §12 and §5.12:
            URL pattern: /api/{app_short_name}/{version}/{path}
            Example: /api/crm/v1/customers/{customer_id}

        Reflex exposes app.api which IS a FastAPI APIRouter.
        We add routes to it directly — no separate server, single port.
        """
        web_api_objects = self._registry.get_by_type("web_api")

        for api_def in web_api_objects:
            ref = api_def.object_ref
            meta = api_def.metadata
            app_name = api_def.app_name
            if not app_name:
                logger.warning(f"Web API {ref} has no app_name — skipping")
                continue

            version = meta.get("version", "v1")
            path = meta.get("path", f"/{api_def.name}")
            if not path.startswith("/"):
                path = f"/{path}"

            full_route = f"/api/{app_name}/{version}{path}"
            method = meta.get("method", "GET").upper()

            api_route = APIRoute(
                route=full_route,
                method=method,
                app_name=app_name,
                api_ref=ref,
                api_def=api_def,
            )
            self._api_routes.append(api_route)

            # Create the FastAPI endpoint handler
            handler = self._create_api_handler(api_def)

            # Register on Reflex's internal FastAPI router
            try:
                api_router = self._get_api_router(reflex_app)
                if api_router is not None:
                    methods = [method]
                    api_router.add_api_route(
                        full_route,
                        handler,
                        methods=methods,
                        name=f"appos_{app_name}_{meta.get('name', api_def.name)}",
                    )
                    logger.debug(f"Registered API route: {method} {full_route}")
                else:
                    logger.warning(
                        f"Reflex API router not available — API route {method} {full_route} "
                        f"not registered. Ensure Reflex version supports app.api."
                    )
            except Exception as e:
                logger.error(f"Failed to register API route {method} {full_route}: {e}")

        logger.info(f"Registered {len(self._api_routes)} API routes")

    def _get_api_router(self, reflex_app):
        """
        Get the FastAPI router from Reflex's app.

        Reflex internally uses FastAPI + Starlette. The `app.api` attribute
        gives access to the FastAPI router for adding custom API routes.

        Returns None if the API router is not accessible (older Reflex versions).
        """
        # Reflex >= 0.6: app.api is a FastAPI APIRouter
        if hasattr(reflex_app, "api"):
            return reflex_app.api

        # Fallback: try to access the underlying FastAPI app
        if hasattr(reflex_app, "_app") and hasattr(reflex_app._app, "api"):
            return reflex_app._app.api

        # Try the Starlette app directly
        if hasattr(reflex_app, "app") and hasattr(reflex_app.app, "add_api_route"):
            return reflex_app.app

        return None

    def _create_api_handler(self, api_def: RegisteredObject):
        """
        Create a FastAPI-compatible async endpoint handler for a @web_api.

        The handler:
            1. Converts the Starlette Request to our APIRequest model
            2. Delegates to APIExecutor.execute() for the full pipeline
            3. Returns a Starlette JSONResponse

        This is the bridge between Reflex's FastAPI and our execution engine.
        """
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        from appos.engine.api_executor import APIExecutor, RateLimiter, starlette_to_api_request

        # Capture api_def in closure
        captured_def = api_def

        async def endpoint(request: Request) -> JSONResponse:
            """FastAPI endpoint handler — delegates to AppOS API executor."""
            # Convert Starlette request to our normalized model
            api_request = await starlette_to_api_request(request)

            # Create executor (uses runtime for auth, security, dispatch)
            executor = APIExecutor(
                runtime=self._runtime,
                rate_limiter=RateLimiter(
                    self._runtime.rate_limiter if self._runtime else None
                ),
            )

            # Execute the full inbound pipeline
            api_response = await executor.execute(captured_def, api_request)

            # Build response headers
            headers = dict(api_response.headers)
            headers.setdefault("X-AppOS-API", "1")

            return JSONResponse(
                content=api_response.body,
                status_code=api_response.status_code,
                headers=headers,
            )

        return endpoint

    # -----------------------------------------------------------------------
    # Theme Resolution
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Site Config & Navigation Builder (Task 4.8)
    # -----------------------------------------------------------------------

    def _build_site_configs(self) -> None:
        """
        Build site configurations for all apps.

        Reads @site objects from the registry and resolves navigation menus.
        If no @site is defined for an app, auto-generates a nav from @page definitions.
        """
        # Collect all site definitions
        site_objects = self._registry.get_by_type("site")

        for site_def in site_objects:
            app_name = site_def.app_name
            if not app_name:
                continue

            handler = site_def.handler
            if handler and callable(handler):
                try:
                    site_data = handler()
                    if isinstance(site_data, dict):
                        nav_items = []
                        for nav in site_data.get("navigation", []):
                            nav_items.append(NavItem(
                                label=nav.get("label", ""),
                                route=f"/{app_name}{nav.get('route', '')}",
                                icon=nav.get("icon", ""),
                            ))

                        self._site_configs[app_name] = SiteConfig(
                            name=site_data.get("name", site_def.metadata.get("name", app_name)),
                            app_name=app_name,
                            navigation=nav_items,
                            default_page=f"/{app_name}{site_data.get('default_page', '/')}",
                            auth_required=site_data.get("auth_required", True),
                            theme=self.get_app_theme(app_name),
                        )
                        logger.debug(f"Built site config for {app_name} with {len(nav_items)} nav items")
                except Exception as e:
                    logger.error(f"Failed to build site config for {app_name}: {e}")

        # Auto-generate site config for apps without @site
        app_names = set()
        page_objects = self._registry.get_by_type("page")
        for page_def in page_objects:
            if page_def.app_name:
                app_names.add(page_def.app_name)

        for app_name in app_names:
            if app_name in self._site_configs:
                continue

            # Auto-generate nav from @page definitions
            app_pages = self._registry.get_by_type("page", app_name=app_name)
            nav_items = []
            for page_def in app_pages:
                meta = page_def.metadata
                raw_route = meta.get("route", f"/{page_def.name}")
                if not raw_route.startswith("/"):
                    raw_route = f"/{raw_route}"
                full_route = f"/{app_name}{raw_route}"
                label = meta.get("title", page_def.name.replace("_", " ").title())
                nav_items.append(NavItem(label=label, route=full_route))

            if nav_items:
                self._site_configs[app_name] = SiteConfig(
                    name=app_name.title(),
                    app_name=app_name,
                    navigation=nav_items,
                    default_page=nav_items[0].route if nav_items else f"/{app_name}",
                    auth_required=True,
                    theme=self.get_app_theme(app_name),
                )
                logger.debug(f"Auto-generated site config for {app_name} with {len(nav_items)} pages")

    def _wrap_with_site_layout(
        self, page_fn: Any, app_name: str
    ) -> Any:
        """
        Wrap a page component function with the app's site layout (navigation sidebar).

        If no site config exists for the app, returns the page as-is.
        """
        import reflex as rx

        site_config = self._site_configs.get(app_name)
        if not site_config or not site_config.navigation:
            return page_fn

        theme = site_config.theme or {}
        primary_color = theme.get("primary_color", "#3B82F6")
        font_family = theme.get("font_family", "Inter")

        def wrapped_page() -> rx.Component:
            # Build navigation sidebar
            nav_links = []
            for nav_item in site_config.navigation:
                nav_links.append(
                    rx.link(
                        rx.hstack(
                            rx.icon(nav_item.icon, size=16) if nav_item.icon else rx.fragment(),
                            rx.text(nav_item.label, size="2"),
                            spacing="2",
                            align="center",
                            padding="8px 12px",
                            border_radius="6px",
                            _hover={"background": "var(--gray-a3)"},
                            width="100%",
                        ),
                        href=nav_item.route,
                        underline="none",
                        width="100%",
                    )
                )

            sidebar = rx.box(
                rx.vstack(
                    rx.heading(site_config.name, size="4", padding="12px"),
                    rx.divider(),
                    *nav_links,
                    spacing="1",
                    width="100%",
                    padding="8px",
                ),
                width="240px",
                min_height="100vh",
                border_right="1px solid var(--gray-a5)",
                background="var(--gray-a2)",
                position="fixed",
                left="0",
                top="0",
            )

            # Page content with offset for sidebar
            content = page_fn() if callable(page_fn) else page_fn
            main_content = rx.box(
                content,
                margin_left="240px",
                padding="24px",
                width="calc(100% - 240px)",
                min_height="100vh",
            )

            return rx.box(
                sidebar,
                main_content,
                style={"font_family": font_family},
                width="100%",
            )

        return wrapped_page

    def get_site_config(self, app_name: str) -> Optional[SiteConfig]:
        """Get the site configuration for an app."""
        return self._site_configs.get(app_name)

    def get_all_site_configs(self) -> Dict[str, SiteConfig]:
        """Get all site configurations."""
        return dict(self._site_configs)

    # -----------------------------------------------------------------------
    # Theme Resolution
    # -----------------------------------------------------------------------

    def get_app_theme(self, app_name: str) -> Dict[str, Any]:
        """
        Resolve the theme config for an app from its app.yaml.

        Per Design §12 — each app can define:
            primary_color, secondary_color, accent_color,
            font_family, border_radius

        Returns default theme if app has no custom theme.
        """
        default_theme = {
            "primary_color": "#3B82F6",
            "secondary_color": "#1E40AF",
            "accent_color": "#DBEAFE",
            "font_family": "Inter",
            "border_radius": "8px",
        }

        # Look up app config from registry or config engine
        # Full implementation depends on YAML config parsing + app.yaml loading
        try:
            from appos.engine.config import load_app_config
            app_config = load_app_config(app_name)
            if app_config and hasattr(app_config, "theme"):
                theme_config = app_config.theme
                if theme_config:
                    return {**default_theme, **theme_config}
        except Exception:
            pass

        return default_theme

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def get_registered_routes(self) -> Dict[str, List[Dict[str, str]]]:
        """Get all registered routes for admin console display."""
        return {
            "pages": [
                {"route": r.route, "title": r.title, "app": r.app_name}
                for r in self._app_routes
            ],
            "apis": [
                {"route": r.route, "method": r.method, "app": r.app_name}
                for r in self._api_routes
            ],
        }

    def get_api_routes_for_app(self, app_name: str) -> List[APIRoute]:
        """Get all API routes for a specific app."""
        return [r for r in self._api_routes if r.app_name == app_name]
