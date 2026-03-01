"""Task creation page."""


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
