"""Task lifecycle process — full multi-step orchestration showcasing all features."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@process(
    name="task_lifecycle",
    description="Full task lifecycle: validate → create → score → notify (parallel) → done",
    inputs=["title", "description", "project_id", "priority", "assignee_id"],
    display_name="Task: {title}",
    triggers=[
        event("records.task.on_create"),
    ],
    permissions=["dev_team", "managers", "taskm_admins"],
    timeout=300,
    on_error="fail",
)
def task_lifecycle(ctx):
    """
    Multi-step process demonstrating all process features.

    Process variables (ctx.var):
      - logged=True  (default) — visible in logs, admin UI, AI queries
      - logged=False            — hidden from logs/UI/AI, stored as SHA-256 hash
      - sensitive=True          — hidden from everything, stored encrypted (Fernet)
    """

    # --- Process-level variables ---
    ctx.var("title", ctx.input("title"), logged=True)
    ctx.var("description", ctx.input("description"), logged=True)
    ctx.var("project_id", ctx.input("project_id"), logged=True)
    ctx.var("priority", ctx.input("priority") or "medium", logged=True)
    ctx.var("assignee_id", ctx.input("assignee_id"), logged=True)
    ctx.var("task_id", None, logged=True)

    # Hidden variable — value hashed in DB, not in logs
    ctx.var("internal_trace_id", "trace_abc123", logged=False)

    # Sensitive variable — encrypted in DB, never shown anywhere
    ctx.var("api_token_snapshot", "tok_secret_xyz", sensitive=True)

    return [
        # Step 1: Validate task data
        step(
            "validate",
            rule="validate_task",
            input_mapping={
                "title": "ctx.var.title",
                "priority": "ctx.var.priority",
                "project_id": "ctx.var.project_id",
            },
            output_mapping={
                "is_valid": "ctx.var.is_valid",
                "errors": "ctx.var.validation_errors",
            },
            on_error="fail",
            timeout=30,
        ),

        # Step 2: Score the task priority (only if validation passed)
        step(
            "score",
            rule="score_task_priority",
            condition="ctx.var.is_valid",
            input_mapping={
                "task_id": "ctx.var.task_id",
                "priority": "ctx.var.priority",
                "is_overdue": "False",
                "days_until_due": "None",
                "has_assignee": "ctx.var.assignee_id",
            },
            output_mapping={
                "score": "ctx.var.priority_score",
                "urgency_label": "ctx.var.urgency",
            },
            retry_count=2,
            retry_delay=5,
            on_error="skip",
        ),

        # Step 3: Initialize project resources (if needed)
        step(
            "init_project",
            rule="initialize_project",
            condition="ctx.var.is_valid",
            input_mapping={
                "project_id": "ctx.var.project_id",
                "project_name": "ctx.var.title",
                "owner_id": "ctx.var.assignee_id",
            },
            output_mapping={
                "initialized": "ctx.var.project_init_result",
            },
            on_error="skip",
        ),

        # Step 4: Parallel execution — notify + update stats simultaneously
        parallel(
            step(
                "notify_assignee",
                rule="reassess_task_priority",
                input_mapping={
                    "task_id": "ctx.var.task_id",
                    "changes": "{'status': 'created'}",
                },
                output_mapping={
                    "new_score": "ctx.var.notification_score",
                    "notification_sent": "ctx.var.notified",
                },
                on_error="skip",
            ),
            step(
                "update_stats",
                rule="get_project_stats",
                input_mapping={
                    "project_id": "ctx.var.project_id",
                },
                output_mapping={
                    "total_tasks": "ctx.var.project_total",
                    "completion_pct": "ctx.var.project_progress",
                },
                on_error="skip",
            ),
        ),

        # Step 5: Fire-and-forget — send external notification (non-blocking)
        step(
            "external_notify",
            rule="reassess_task_priority",
            input_mapping={
                "task_id": "ctx.var.task_id",
                "changes": "{'notification': 'external'}",
            },
            fire_and_forget=True,
            on_error="skip",
        ),
    ]
