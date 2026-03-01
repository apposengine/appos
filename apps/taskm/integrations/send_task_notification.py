"""Outbound integration — send task notification via REST API."""


@integration(
    name="send_task_notification",
    connected_system="notification_api",
    permissions=["dev_team", "managers", "taskm_admins"],
    log_payload=True,
)
def send_task_notification():
    """
    Send a notification to the external notification micro-service.
    The service runs as a local FastAPI app (external_api_server.py).

    Demonstrates:
      - POST method with JSON body template
      - Header with idempotency key
      - Path templating
      - response_mapping (JSONPath-style)
      - error_handling per status code
      - Retry with exponential backoff
      - log_payload=True for debugging
    """
    return {
        "method": "POST",
        "path": "/api/v1/notifications",
        "headers": {
            "Content-Type": "application/json",
            "X-Idempotency-Key": "{idempotency_key}",
        },
        "body": {
            "event": "{event_type}",
            "task_id": "{task_id}",
            "task_title": "{task_title}",
            "project": "{project_name}",
            "assignee": "{assignee_name}",
            "message": "{message}",
            "severity": "{severity}",
        },
        "response_mapping": {
            "notification_id": "$.id",
            "status": "$.status",
            "delivered_at": "$.delivered_at",
        },
        "error_handling": {
            "400": "fail",
            "401": "fail",
            "429": "retry",
            "5xx": "retry",
        },
        "retry": {
            "count": 3,
            "delay": 2,
            "backoff": "exponential",
        },
    }
