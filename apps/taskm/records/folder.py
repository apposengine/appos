"""Folder record — runtime folder management (Design §5.17)."""

from typing import List, Optional

from pydantic import BaseModel, Field

import appos  # noqa: F401 — auto-injects decorators into builtins


@record
class Folder(BaseModel):
    """
    Folder configuration that drives physical directory creation.
    Demonstrates: document_types (MIME filter), max_size_mb, auto_cleanup.
    """

    name: str = Field(max_length=100)
    path: str = Field(max_length=500)
    purpose: str = Field(max_length=200)
    app_id: int = Field()
    document_types: List[str] = Field(
        default_factory=lambda: ["application/pdf", "image/*", "text/plain"],
    )
    max_size_mb: int = Field(default=500)
    auto_cleanup: Optional[dict] = Field(default=None)
    is_active: bool = Field(default=True)

    # Relationships
    documents: List["Document"] = has_many("Document")

    class Meta:
        permissions = {
            "view": ["dev_team", "managers", "taskm_admins"],
            "create": ["taskm_admins"],
            "update": ["taskm_admins"],
            "delete": ["taskm_admins"],
        }
