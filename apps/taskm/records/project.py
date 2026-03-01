"""Project record — top-level grouping with audit, soft_delete, on_create hook."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


@record
class Project(BaseModel):
    """
    Project groups related tasks.

    Demonstrates:
      - Field constraints: max_length, choices, ge/le, default_factory
      - Meta: audit, soft_delete, display_field, search_fields
      - Meta: connected_system, row_security_rule (future)
      - Meta: permissions (per-group CRUD), on_create hook
      - Relationship: has_many → Task
    """

    name: str = Field(max_length=120, description="Project name")
    code: str = Field(
        max_length=10,
        description="Short code (e.g. 'DEMO')",
        json_schema_extra={"auto_generate": False},
    )
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(
        default="planning",
        json_schema_extra={"choices": ["planning", "active", "on_hold", "completed", "archived"]},
    )
    owner_id: int = Field(description="User ID of the project owner")
    budget: float = Field(default=0.0, ge=0, description="Budget in USD")
    start_date: Optional[datetime] = Field(default=None)
    end_date: Optional[datetime] = Field(default=None)
    is_public: bool = Field(default=False, description="Visible to all groups")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    tasks: List["Task"] = has_many("Task", back_ref="project")

    class Meta:
        table_name = "projects"
        audit = True
        soft_delete = True
        display_field = "name"
        search_fields = ["name", "code", "description"]
        connected_system = "taskm_database"
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["managers", "taskm_admins"],
            "update": ["managers", "taskm_admins"],
            "delete": ["taskm_admins"],
        }
        row_security_rule = None
        on_create = ["initialize_project"]
        on_update = []
        on_delete = []
