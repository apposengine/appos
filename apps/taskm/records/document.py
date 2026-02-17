"""Document record — file/artifact management with versioning (Design §5.16)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

import appos  # noqa: F401 — auto-injects decorators into builtins


@record
class Document(BaseModel):
    """
    Document metadata — physical files stored in runtime/documents/ folder.
    Demonstrates: versioning, MIME type, size, tags, soft_delete, owner.
    """

    name: str = Field(max_length=255)
    file_path: str = Field(max_length=500)
    folder_id: Optional[int] = Field(default=None)
    mime_type: str = Field(max_length=100)
    size_bytes: int = Field(ge=0)
    version: int = Field(default=1)
    tags: List[str] = Field(default_factory=list)
    owner_id: int = Field()
    is_archived: bool = Field(default=False)

    # Relationships
    folder: Optional["Folder"] = belongs_to("Folder")
    versions: List["DocumentVersion"] = has_many("DocumentVersion")

    class Meta:
        audit = True
        soft_delete = True
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["managers", "taskm_admins"],
            "update": ["managers", "taskm_admins"],
            "delete": ["taskm_admins"],
        }
