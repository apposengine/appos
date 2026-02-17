"""TaskCreateForm interface — form for creating new tasks."""
import appos  # noqa: F401 — auto-injects decorators into builtins
from apps.taskm.interfaces.components import Field, Form


@interface(
    name="TaskCreateForm",
    record_name="Task",
    type="create",
    permissions=["dev_team", "managers", "taskm_admins"],
)
def task_create_form():
    """
    Form for creating new tasks.
    Demonstrates: Form component with various field types, choices, required.
    """
    return Form(
        record="Task",
        fields=[
            Field("title", label="Task Title", required=True),
            Field("description", field_type="textarea"),
            Field("project_id", label="Project", field_type="reference", required=True),
            Field("priority", field_type="select",
                  choices=["low", "medium", "high", "critical"]),
            Field("assignee_id", label="Assignee", field_type="reference"),
            Field("due_date", field_type="datetime"),
            Field("estimated_hours", field_type="number"),
            Field("tags", field_type="tags"),
        ],
        submit_label="Create Task",
    )
