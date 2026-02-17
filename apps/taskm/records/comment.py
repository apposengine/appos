"""Comment record — simple child record on a Task."""

from datetime import datetime

from pydantic import BaseModel, Field

import appos  # noqa: F401 — auto-injects decorators into builtins


@record
class Comment(BaseModel):
    """
    Comment on a Task.  Demonstrates a simple child record with belongs_to relationship.
    """

    task_id: int = Field(description="FK to Task")
    author_id: int = Field(description="User ID of comment author")
    body: str = Field(max_length=4000, description="Comment text (Markdown)")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    task: "Task" = belongs_to("Task", required=True)

    class Meta:
        table_name = "comments"
        audit = False
        soft_delete = False
        display_field = "body"
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["dev_team", "managers", "taskm_admins"],
            "update": ["dev_team", "managers", "taskm_admins"],
            "delete": ["managers", "taskm_admins"],
        }
