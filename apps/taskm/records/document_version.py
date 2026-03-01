"""DocumentVersion record — tracks document version history."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


@record
class DocumentVersion(BaseModel):
    """Tracks document version history."""

    document_id: int = Field()
    version: int = Field()
    file_path: str = Field(max_length=500)
    size_bytes: int = Field(ge=0)
    uploaded_by: int = Field()
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    change_note: Optional[str] = Field(default=None, max_length=500)

    class Meta:
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["managers", "taskm_admins"],
            "delete": ["taskm_admins"],
        }
