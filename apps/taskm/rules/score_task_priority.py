"""Scoring rule — calculate numeric priority score (0-100) for a task."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@expression_rule(
    inputs=["task_id", "priority", "is_overdue", "days_until_due", "has_assignee"],
    outputs=["score", "urgency_label"],
    depends_on=["constants.TASKM_OVERDUE_THRESHOLD_HOURS"],
    permissions=["dev_team", "managers", "taskm_admins"],
    cacheable=True,
    cache_ttl=120,
)
def score_task_priority(ctx):
    """
    Calculate a numeric priority score (0-100) for a task.
    Higher score = more urgent. Used for dashboard sorting.

    Scoring formula:
      base = priority_weight
      + overdue_bonus (if past due)
      + deadline_proximity_bonus
      - unassigned_penalty
    """
    priority = ctx.input("priority") or "medium"
    is_overdue = ctx.input("is_overdue") or False
    days_until_due = ctx.input("days_until_due")
    has_assignee = ctx.input("has_assignee") or False

    # Base weight by priority level
    weights = {"low": 10, "medium": 30, "high": 60, "critical": 85}
    score = weights.get(priority, 30)

    # Overdue bonus
    if is_overdue:
        score += 15

    # Deadline proximity (within 3 days)
    if days_until_due is not None and 0 < days_until_due <= 3:
        score += int(10 * (3 - days_until_due))

    # Unassigned penalty
    if not has_assignee:
        score -= 5

    score = max(0, min(100, score))

    # Urgency label
    if score >= 80:
        label = "critical"
    elif score >= 50:
        label = "high"
    elif score >= 25:
        label = "normal"
    else:
        label = "low"

    ctx.output("score", score)
    ctx.output("urgency_label", label)
    return ctx.outputs()
