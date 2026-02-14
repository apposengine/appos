"""
AppOS — Main Reflex application entry point.

Registers all admin routes and app routes.
Single-port, multi-app routing.
"""

import reflex as rx

from appos.admin.pages.dashboard import dashboard_page
from appos.admin.pages.groups import groups_page
from appos.admin.pages.login import login_page
from appos.admin.pages.users import users_page

# Create the Reflex app
app = rx.App()

# Admin console routes
app.add_page(login_page, route="/admin/login", title="AppOS Admin — Login")
app.add_page(dashboard_page, route="/admin/dashboard", title="AppOS Admin — Dashboard")
app.add_page(users_page, route="/admin/users", title="AppOS Admin — Users")
app.add_page(groups_page, route="/admin/groups", title="AppOS Admin — Groups")

# Redirect /admin → /admin/dashboard
app.add_page(lambda: rx.fragment(), route="/admin", on_load=rx.redirect("/admin/dashboard"))
