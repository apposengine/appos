"""Web API — POST /tasks with OAuth2 auth, triggers process."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@web_api(
    name="create_task",
    method="POST",
    path="/tasks",
    auth={"type": "oauth2", "connected_system": "notification_api"},
    version="v1",
    rate_limit={"requests": 50, "window": 60},
    permissions=["dev_team", "managers", "taskm_admins"],
    log_payload=True,
)
def create_task():
    """
    Create a new task via API and trigger the task lifecycle process.
    URL: POST /api/taskm/v1/tasks

    Demonstrates: POST with request body, handler pointing to a @process,
    async mode (client polls for completion), log_payload=True.
    """
    return {
        "handler": "processes.task_lifecycle",
        "request_mapping": {
            "title": "body.title",
            "description": "body.description",
            "project_id": "body.project_id",
            "priority": "body.priority",
            "assignee_id": "body.assignee_id",
        },
        "response_mapping": {
            "task_id": "$.task_id",
            "status": "$.status",
            "process_instance": "$.process_instance_id",
        },
        "async": False,
    }
