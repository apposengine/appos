"""
AppOS Document & Folder Models — Pydantic + SQLAlchemy definitions.

Document: File metadata with versioning.
DocumentVersion: Tracks each version of a document.
Folder: Dynamic folder configuration with MIME validation and retention.

Design refs:
    §5.16 Document — Per-app file management with versioning
    §5.17 Folder — Per-app dynamic folder management

Physical storage: apps/{app_short_name}/runtime/documents/{folder.path}/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("appos.documents.models")


# ---------------------------------------------------------------------------
# Document record (§5.16)
# ---------------------------------------------------------------------------

class Document(BaseModel):
    """
    Document metadata — stored in DB. Physical files in app's runtime/documents/ folder.

    Supports versioning: each upload creates a new DocumentVersion.
    The current version is tracked by the `version` field.
    Security inheritance: Documents in a Folder inherit Folder permissions.
    """

    id: Optional[int] = Field(default=None, description="Auto-generated primary key")
    name: str = Field(max_length=255, description="Document display name")
    file_path: str = Field(max_length=500, description="Relative path to physical file")
    folder_id: Optional[int] = Field(default=None, description="Parent folder ID")
    app_id: int = Field(description="Owning app ID")
    mime_type: str = Field(max_length=100, description="File MIME type (e.g., application/pdf)")
    size_bytes: int = Field(ge=0, description="File size in bytes")
    version: int = Field(default=1, description="Current version number (auto-incremented)")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    owner_id: int = Field(description="User ID who uploaded the document")
    is_archived: bool = Field(default=False, description="Soft-archive flag")

    # Timestamps
    created_at: Optional[datetime] = Field(default=None, description="Upload timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last modification")

    class Meta:
        table_name = "documents"
        audit = True
        soft_delete = True
        display_field = "name"
        search_fields = ["name", "tags", "mime_type"]
        permissions = {
            "view": ["*"],
            "use": ["*"],
            "create": [],   # Set per-app in app.yaml or per-folder
            "update": [],
            "delete": [],
        }

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }

    def current_file_path(self, app_short_name: str) -> str:
        """Return the full relative path: apps/{app}/runtime/documents/{file_path}."""
        return f"apps/{app_short_name}/runtime/documents/{self.file_path}"


# ---------------------------------------------------------------------------
# DocumentVersion record (§5.16)
# ---------------------------------------------------------------------------

class DocumentVersion(BaseModel):
    """
    Tracks document version history.

    Each time a document is updated (new file uploaded), a new version is created.
    The previous version is preserved for rollback.
    """

    id: Optional[int] = Field(default=None, description="Auto-generated primary key")
    document_id: int = Field(description="Parent document ID")
    version: int = Field(description="Version number (sequential)")
    file_path: str = Field(max_length=500, description="Path to this version's file")
    size_bytes: int = Field(ge=0, description="File size of this version")
    uploaded_by: int = Field(description="User ID who uploaded this version")
    uploaded_at: Optional[datetime] = Field(
        default=None,
        description="Upload timestamp for this version",
    )
    change_note: Optional[str] = Field(
        default=None, max_length=500, description="Change description"
    )

    class Meta:
        table_name = "document_versions"
        permissions = {
            "view": ["*"],
            "create": [],
            "delete": [],
        }


# ---------------------------------------------------------------------------
# Folder record (§5.17)
# ---------------------------------------------------------------------------

class Folder(BaseModel):
    """
    Folder configuration — DB record drives physical directory creation.

    Engine behavior:
    1. On app startup → reads Folder table → creates missing physical dirs
    2. On Document upload → validates MIME type against folder.document_types
    3. On Document upload → validates size against folder.max_size_mb
    4. Auto-cleanup runs on schedule per retention policy
    """

    id: Optional[int] = Field(default=None, description="Auto-generated primary key")
    name: str = Field(max_length=100, description="Folder display name")
    path: str = Field(max_length=500, description="Relative path under app's runtime/documents/")
    purpose: str = Field(max_length=200, description="What this folder is for (e.g., invoices)")
    app_id: int = Field(description="Owning app ID")
    document_types: List[str] = Field(
        default_factory=lambda: ["*/*"],
        description="Allowed MIME types (e.g., ['application/pdf', 'image/*'])",
    )
    max_size_mb: int = Field(default=1000, description="Maximum total folder size in MB")
    auto_cleanup: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Retention policy: {retention_days: int, archive_first: bool}",
    )
    is_active: bool = Field(default=True, description="Whether folder accepts new uploads")

    # Timestamps
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)

    class Meta:
        table_name = "folders"
        unique_together = [("app_id", "path")]
        permissions = {
            "view": ["*"],
            "use": ["*"],
            "create": [],
            "update": [],
            "delete": [],
        }

    def physical_path(self, app_short_name: str) -> str:
        """Return the full physical path: apps/{app}/runtime/documents/{path}/."""
        return f"apps/{app_short_name}/runtime/documents/{self.path}"

    def accepts_mime_type(self, mime_type: str) -> bool:
        """
        Check if a MIME type is allowed by this folder's document_types.

        Supports:
        - Exact match: "application/pdf"
        - Wildcard category: "image/*"
        - Universal: "*/*"
        """
        if "*/*" in self.document_types:
            return True

        for allowed in self.document_types:
            if allowed == mime_type:
                return True
            # Check wildcard: "image/*" matches "image/png"
            if allowed.endswith("/*"):
                category = allowed.split("/")[0]
                if mime_type.startswith(category + "/"):
                    return True

        return False

    def check_size_limit(self, current_total_bytes: int, new_file_bytes: int) -> bool:
        """Check if adding a new file would exceed the folder size limit."""
        limit_bytes = self.max_size_mb * 1024 * 1024
        return (current_total_bytes + new_file_bytes) <= limit_bytes
