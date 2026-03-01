"""REST API Connected System — Notification Service with API Key auth."""


@connected_system(
    name="notification_api",
    type="rest_api",
    description="External notification micro-service (webhook-style)",
)
def notification_api():
    """
    REST API connection to a notification service.
    Demonstrates: base_url, api_key auth (header-based), environment overrides,
    timeout, and is_sensitive flag.

    In the demo, this points to a local FastAPI server we provide
    (apps/taskm/external_api_server.py) so the integration can be tested
    end-to-end without any third-party dependency.
    """
    return {
        "default": {
            "base_url": "http://localhost:9100",
            "timeout": 15,
            "is_sensitive": False,
        },
        "auth": {
            "type": "api_key",
            "header": "X-API-Key",
            "prefix": "",
        },
        "environment_overrides": {
            "staging": {"base_url": "https://notify-staging.internal"},
            "prod": {"base_url": "https://notify.internal", "timeout": 10},
        },
        "health_check": {
            "enabled": True,
            "interval_seconds": 120,
        },
    }
