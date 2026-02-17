"""Task Manager  Pages. Each page is defined in its own module."""

from .dashboard import dashboard_page
from .tasks import tasks_page
from .task_create import task_create_page
from .task_detail import task_detail_page

__all__ = ["dashboard_page", "tasks_page", "task_create_page", "task_detail_page"]
