"""Task detail page — dynamic route with path parameter."""


@page(
    route="/tasks/detail",
    title="Task Detail",
    interface_name="TaskList",  # Would be a TaskDetail interface in full app
    permissions=["dev_team", "managers", "taskm_admins"],
)
def task_detail_page():
    """
    Single task detail view.
    Resolved URL: /taskm/tasks/detail?task_id=xxx
    Uses query param instead of path param (Reflex route constraint).
    """
    pass
