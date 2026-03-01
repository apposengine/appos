"""Task record — core work item with rich field types and relationships."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


@record
class Task(BaseModel):
    """
    Individual work item belonging to a Project.

    Demonstrates:
      - Foreign key (project_id), choices, pattern validation
      - belongs_to (Project), has_many (Comment), has_one (future)
      - Event hooks: on_update triggers reassessment rule
      - Soft delete + audit log
    """

    title: str = Field(max_length=200, description="Task title")
    description: Optional[str] = Field(default=None, max_length=2000)
    project_id: int = Field(description="FK to Project")
    status: str = Field(
        default="todo",
        json_schema_extra={
            "choices": ["todo", "in_progress", "in_review", "done", "blocked"],
        },
    )
    priority: str = Field(
        default="medium",
        json_schema_extra={"choices": ["low", "medium", "high", "critical"]},
    )
    assignee_id: Optional[int] = Field(default=None, description="Assigned user ID")
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=999)
    actual_hours: float = Field(default=0.0, ge=0)
    due_date: Optional[datetime] = Field(default=None)
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

    # Relationships
    project: "Project" = belongs_to("Project", required=True)
    comments: List["Comment"] = has_many("Comment", cascade="all, delete-orphan")

    class Meta:
        table_name = "tasks"
        audit = True
        soft_delete = True
        display_field = "title"
        search_fields = ["title", "description", "tags"]
        connected_system = "taskm_database"
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["dev_team", "managers", "taskm_admins"],
            "update": ["dev_team", "managers", "taskm_admins"],
            "delete": ["managers", "taskm_admins"],
        }
        on_create = []
        on_update = ["reassess_task_priority"]
        on_delete = []
