"""Tasks list page."""


@page(
    route="/tasks",
    title="Tasks",
    interface_name="TaskList",
    permissions=["dev_team", "managers", "taskm_admins"],
)
def tasks_page():
    """
    Task listing page.
    Resolved URL: /taskm/tasks
    """
    pass
