"""TaskManager site — collection of pages forming the navigable app."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@site(name="TaskManager")
def taskm_site():
    """
    Task Manager site definition.

    Demonstrates:
      - pages list referencing @page functions
      - Navigation menu with labels, routes, icons
      - auth_required (all pages require login)
      - default_page (redirect on login)
      - Theme reference from app.yaml
    """
    return {
        "pages": [
            "dashboard_page",
            "tasks_page",
            "task_create_page",
            "task_detail_page",
        ],
        "navigation": [
            {"label": "Dashboard", "route": "/dashboard", "icon": "layout-dashboard"},
            {"label": "Tasks", "route": "/tasks", "icon": "check-square"},
            {"label": "New Task", "route": "/tasks/new", "icon": "plus-circle"},
        ],
        "auth_required": True,
        "default_page": "/dashboard",
        "theme": "taskm_theme",
    }
