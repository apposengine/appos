"""TaskList interface — DataTable with search, filter, pagination."""
from apps.taskm.interfaces.components import Button, DataTable


@interface(
    name="TaskList",
    record_name="Task",
    type="list",
    permissions=["dev_team", "managers", "taskm_admins"],
)
def task_list():
    """
    Auto-generated-style task list with search, filter, pagination.
    Demonstrates: DataTable component, row actions, navigation buttons.
    """
    return DataTable(
        record="Task",
        columns=["title", "status", "priority", "assignee_id", "due_date", "project_id"],
        searchable=True,
        filterable=True,
        page_size=25,
        actions=[
            Button("New Task", action="navigate", to="/taskm/tasks/new"),
        ],
        row_actions=[
            Button("Edit", action="navigate", to="/taskm/tasks/{id}/edit"),
            Button("Delete", action="delete", confirm=True),
        ],
    )
