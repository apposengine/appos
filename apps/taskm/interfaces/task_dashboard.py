"""TaskDashboard interface — custom composite layout with Cards + DataTable."""
from apps.taskm.interfaces.components import Card, DataTable, Layout, Metric, Row


@interface(
    name="TaskDashboard",
    permissions=["dev_team", "managers", "taskm_admins"],
)
def task_dashboard():
    """
    Custom dashboard combining metrics, cards, and a task table.
    Demonstrates: Layout, Row, Card, Metric, custom composition.

    In real deployment, Metric values would come from:
      rules.get_project_stats() via on_load.
    """
    return Layout([
        Row([
            Card("Project Overview", content=Metric("Total Tasks", 42, change="+3")),
            Card("Completion", content=Metric("Done", "67%", change="+5%")),
            Card("Overdue", content=Metric("Overdue", 5, change="-2")),
            Card("Active", content=Metric("In Progress", 15)),
        ]),
        Row([
            DataTable(
                record="Task",
                columns=["title", "status", "priority", "due_date"],
                searchable=True,
                page_size=10,
            ),
        ]),
    ])
