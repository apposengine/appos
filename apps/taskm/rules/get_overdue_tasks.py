"""Query rule — fetch overdue tasks for a project."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@expression_rule(
    inputs=["project_id"],
    outputs=["overdue_tasks", "count"],
    permissions=["dev_team", "managers", "taskm_admins"],
)
def get_overdue_tasks(ctx):
    """
    Fetch overdue tasks for a project.
    Demonstrates: query logic as expression rule, list output, filtering.

    In a full deployment, this would use records.task.list(filters=...),
    but here we show the pattern with mock-friendly structure.
    """
    project_id = ctx.input("project_id")
    from datetime import datetime, timezone

    query_spec = {
        "record": "Task",
        "filters": {
            "project_id": project_id,
            "status__ne": "done",
            "due_date__lt": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
        },
        "sort": "-due_date",
        "limit": 50,
    }

    ctx.output("overdue_tasks", query_spec)
    ctx.output("count", 0)
    return ctx.outputs()
