"""Aggregation rule — compute project-level task statistics."""


@expression_rule(
    inputs=["project_id"],
    outputs=["total_tasks", "completed", "in_progress", "overdue", "completion_pct"],
    permissions=["dev_team", "managers", "taskm_admins"],
    cacheable=True,
    cache_ttl=60,
)
def get_project_stats(ctx):
    """
    Compute project-level task statistics.
    Demonstrates: multiple outputs, cacheable aggregation.
    """
    project_id = ctx.input("project_id")

    # In real impl: records.task.list(filters={"project_id": project_id})
    total = 12
    completed = 5
    in_progress = 4
    overdue = 2

    ctx.output("total_tasks", total)
    ctx.output("completed", completed)
    ctx.output("in_progress", in_progress)
    ctx.output("overdue", overdue)
    ctx.output("completion_pct", round(completed / total * 100, 1) if total > 0 else 0.0)
    return ctx.outputs()
