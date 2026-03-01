"""Web API — GET /tasks/{task_id} with API key auth and rate limiting."""


@web_api(
    name="get_task",
    method="GET",
    path="/tasks/{task_id}",
    auth={"type": "api_key", "connected_system": "notification_api"},
    version="v1",
    rate_limit={"requests": 100, "window": 60},
    permissions=["dev_team", "managers", "taskm_admins"],
    log_payload=False,
)
def get_task():
    """
    Expose task retrieval as a REST API.
    URL: GET /api/taskm/v1/tasks/{task_id}

    Demonstrates: path param mapping, handler delegation to expression rule,
    response shaping, rate limiting, api_key auth via connected system.
    """
    return {
        "handler": "rules.validate_task",
        "request_mapping": {
            "task_id": "path.task_id",
        },
        "response_mapping": {
            "id": "$.task_id",
            "title": "$.title",
            "status": "$.status",
            "priority": "$.priority",
        },
    }
