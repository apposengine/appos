"""Record event hook — re-evaluate task priority on Task.on_update."""


@expression_rule(
    inputs=["task_id", "changes"],
    outputs=["new_score", "notification_sent"],
    depends_on=[
        "constants.DEFAULT_SCORING_RULE",
        "constants.ENABLE_NOTIFICATIONS",
    ],
    permissions=["dev_team", "managers", "taskm_admins"],
)
def reassess_task_priority(ctx):
    """
    Re-evaluate task priority when a task is updated.
    Triggered by Task.Meta.on_update = ["reassess_task_priority"].

    Demonstrates:
      - Using object reference constants for dynamic dispatch
      - Conditional logic based on which fields changed
      - Inter-rule calling pattern
    """
    task_id = ctx.input("task_id")
    changes = ctx.input("changes") or {}

    # Only re-score if relevant fields changed
    score_relevant = {"status", "priority", "due_date", "assignee_id"}
    changed_fields = set(changes.keys())

    if not changed_fields.intersection(score_relevant):
        ctx.output("new_score", None)
        ctx.output("notification_sent", False)
        return ctx.outputs()

    # Dynamic dispatch via constant → resolves to score_task_priority
    new_score = 50  # Placeholder — in real impl, calls engine.dispatch()

    ctx.output("new_score", new_score)
    ctx.output("notification_sent", False)
    return ctx.outputs()
