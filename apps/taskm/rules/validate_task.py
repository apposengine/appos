"""Validation rule — validate task data before creation."""


@expression_rule(
    inputs=["title", "priority", "project_id"],
    outputs=["is_valid", "errors"],
    permissions=["dev_team", "managers", "taskm_admins"],
)
def validate_task(ctx):
    """
    Validate task data before creation.
    Demonstrates: validation pattern, error collection.
    """
    title = ctx.input("title") or ""
    priority = ctx.input("priority") or ""
    project_id = ctx.input("project_id")

    errors = []
    if not title.strip():
        errors.append("Title is required")
    if len(title) > 200:
        errors.append("Title must be 200 characters or fewer")
    if priority not in ("low", "medium", "high", "critical"):
        errors.append(f"Invalid priority: {priority}")
    if not project_id:
        errors.append("Project ID is required")

    ctx.output("is_valid", len(errors) == 0)
    ctx.output("errors", errors)
    return ctx.outputs()
