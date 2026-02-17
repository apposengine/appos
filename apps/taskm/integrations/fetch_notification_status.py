"""Outbound integration — fetch notification status via GET."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@integration(
    name="fetch_notification_status",
    connected_system="notification_api",
    permissions=["managers", "taskm_admins"],
    log_payload=False,
)
def fetch_notification_status():
    """
    Check the status of a previously sent notification.
    Demonstrates: GET method, path parameter templating, response mapping.
    """
    return {
        "method": "GET",
        "path": "/api/v1/notifications/{notification_id}",
        "headers": {},
        "body": {},
        "response_mapping": {
            "notification_id": "$.id",
            "status": "$.status",
            "delivered_at": "$.delivered_at",
            "event": "$.event",
        },
        "error_handling": {
            "404": "fail",
            "5xx": "retry",
        },
        "retry": {
            "count": 2,
            "delay": 1,
            "backoff": "linear",
        },
    }
