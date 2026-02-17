"""Scheduled process — daily scan for overdue tasks."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@process(
    name="daily_overdue_check",
    description="Check all projects for overdue tasks and send digest",
    inputs=[],
    display_name="Daily Overdue Check",
    triggers=[
        schedule("0 8 * * *", timezone="UTC"),
    ],
    permissions=["taskm_admins"],
    timeout=600,
)
def daily_overdue_check(ctx):
    """
    Scheduled process: scans all projects for overdue tasks.
    Demonstrates: schedule trigger, simple sequential flow.
    """
    return [
        step(
            "scan_overdue",
            rule="get_overdue_tasks",
            input_mapping={"project_id": "None"},
            output_mapping={
                "overdue_tasks": "ctx.var.overdue_list",
                "count": "ctx.var.overdue_count",
            },
        ),
        step(
            "compute_stats",
            rule="get_project_stats",
            input_mapping={"project_id": "None"},
            output_mapping={
                "total_tasks": "ctx.var.total",
                "overdue": "ctx.var.overdue_total",
            },
            on_error="skip",
        ),
    ]
