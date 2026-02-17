"""Web API — GET /projects/{project_id}/stats with rate limiting."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@web_api(
    name="get_project_stats",
    method="GET",
    path="/projects/{project_id}/stats",
    auth={"type": "api_key", "connected_system": "notification_api"},
    version="v1",
    rate_limit={"requests": 200, "window": 60},
    permissions=["managers", "taskm_admins"],
)
def get_project_stats_api():
    """
    Public stats endpoint for a project.
    URL: GET /api/taskm/v1/projects/{project_id}/stats
    """
    return {
        "handler": "rules.get_project_stats",
        "request_mapping": {
            "project_id": "path.project_id",
        },
        "response_mapping": {
            "total_tasks": "$.total_tasks",
            "completed": "$.completed",
            "in_progress": "$.in_progress",
            "overdue": "$.overdue",
            "completion_pct": "$.completion_pct",
        },
    }
