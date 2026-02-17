"""Task Manager  Interfaces. Each interface is defined in its own module."""

from .task_list import task_list
from .task_dashboard import task_dashboard
from .task_create_form import task_create_form

__all__ = ["task_list", "task_dashboard", "task_create_form"]
