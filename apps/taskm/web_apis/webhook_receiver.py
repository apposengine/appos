"""Web API — POST /webhooks/events for inbound webhook receiver."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@web_api(
    name="webhook_receiver",
    method="POST",
    path="/webhooks/events",
    auth={"type": "api_key", "connected_system": "notification_api"},
    version="v1",
    permissions=["taskm_admins"],
    log_payload=True,
)
def webhook_receiver():
    """
    Receive inbound webhook events from external systems.
    URL: POST /api/taskm/v1/webhooks/events

    Demonstrates: webhook pattern, minimal auth, logging payload for debugging.
    """
    return {
        "handler": "rules.validate_task",
        "request_mapping": {
            "title": "body.event_type",
            "priority": "body.priority",
            "project_id": "body.project_id",
        },
        "response_mapping": {
            "received": "$.is_valid",
            "errors": "$.errors",
        },
    }
