"""
AppOS — Reflex configuration.

Single-port, multi-app routing:
  /admin/*       → Admin Console
  /crm/*         → CRM app pages
  /finance/*     → Finance app pages
  /api/crm/*     → CRM Web APIs
  /api/finance/* → Finance Web APIs
"""

import reflex as rx

config = rx.Config(
    app_name="appos",
    # Frontend port for dev server
    frontend_port=3000,
    # API / backend port
    backend_port=8000,
    # Telemetry
    telemetry_enabled=False,
    # Disable unused default plugins
    disable_plugins=["reflex.plugins.sitemap.SitemapPlugin"],
)
