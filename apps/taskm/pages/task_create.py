"""Task creation page."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@page(
    route="/tasks/new",
    title="New Task",
    interface_name="TaskCreateForm",
    permissions=["dev_team", "managers", "taskm_admins"],
)
def task_create_page():
    """
    Task creation form page.
    Resolved URL: /taskm/tasks/new
    """
    pass
