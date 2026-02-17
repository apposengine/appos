"""Dashboard page — landing page with on_load data rule."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@page(
    route="/dashboard",
    title="Task Dashboard",
    interface_name="TaskDashboard",
    permissions=["dev_team", "managers", "taskm_admins"],
    on_load="rules.get_project_stats",
)
def dashboard_page():
    """
    Main dashboard page.
    Resolved URL: /taskm/dashboard
    On load, fires get_project_stats to populate metrics.
    """
    pass
