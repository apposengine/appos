"""
AppOS Document Service — Upload, versioning, folder management, cleanup.

Handles:
- File upload with MIME validation and size checks
- Document versioning (auto-increment, version history)
- Physical folder creation on app startup
- Auto-cleanup per folder retention policy
- Download/delete with audit logging

Design refs:
    §5.16 Document — versioning behavior, security inheritance
    §5.17 Folder — engine behavior (startup, upload validation, cleanup)

Physical storage:
    apps/{app_short_name}/runtime/documents/{folder.path}/{filename}

Platform config:
    appos.yaml → documents.max_upload_size_mb (global limit)
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from appos.documents.models import Document, DocumentVersion, Folder
from appos.engine.errors import AppOSValidationError

logger = logging.getLogger("appos.documents.service")


class DocumentService:
    """
    Platform-level document management service.

    Instantiated per-app (each app has its own document root).
    Used by the engine for upload handling and by the Reflex FileUpload component.
    """

    def __init__(
        self,
        app_short_name: str,
        project_root: Optional[str] = None,
        max_upload_size_mb: int = 50,
    ):
        self._app = app_short_name
        self._project_root = Path(project_root) if project_root else self._find_project_root()
        self._max_upload_size_mb = max_upload_size_mb
        self._documents_root = self._project_root / "apps" / app_short_name / "runtime" / "documents"

    @staticmethod
    def _find_project_root() -> Path:
        """Find project root by looking for appos.yaml."""
        current = Path.cwd()
        for parent in [current, *current.parents]:
            if (parent / "appos.yaml").exists():
                return parent
        return current

    # -------------------------------------------------------------------
    # Folder Management (§5.17)
    # -------------------------------------------------------------------

    def ensure_folder_exists(self, folder: Folder) -> Path:
        """
        Create physical directory for a Folder record if it doesn't exist.

        Called on app startup for all active folders, and on-demand when
        a new Folder is created.

        Returns the physical path.
        """
        physical = self._documents_root / folder.path
        physical.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured folder exists: {physical}")
        return physical

    def ensure_all_folders(self, folders: List[Folder]) -> List[Path]:
        """Create physical directories for all active folders (startup)."""
        paths = []
        for folder in folders:
            if folder.is_active:
                paths.append(self.ensure_folder_exists(folder))
        return paths

    def validate_upload(
        self,
        folder: Folder,
        file_name: str,
        file_size: int,
        mime_type: Optional[str] = None,
        current_folder_size: int = 0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a file upload against folder constraints and platform limits.

        Returns (is_valid, error_message_or_None).
        """
        # 1. Check folder is active
        if not folder.is_active:
            return False, f"Folder '{folder.name}' is not accepting uploads"

        # 2. Detect MIME type if not provided
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(file_name)
            mime_type = mime_type or "application/octet-stream"

        # 3. Check MIME type against folder's allowed types
        if not folder.accepts_mime_type(mime_type):
            return False, (
                f"File type '{mime_type}' not allowed in folder '{folder.name}'. "
                f"Allowed: {folder.document_types}"
            )

        # 4. Check platform-level size limit
        max_bytes = self._max_upload_size_mb * 1024 * 1024
        if file_size > max_bytes:
            return False, (
                f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds "
                f"platform limit ({self._max_upload_size_mb} MB)"
            )

        # 5. Check folder size limit
        if not folder.check_size_limit(current_folder_size, file_size):
            return False, (
                f"Upload would exceed folder '{folder.name}' size limit "
                f"({folder.max_size_mb} MB)"
            )

        return True, None

    # -------------------------------------------------------------------
    # Document Upload (§5.16)
    # -------------------------------------------------------------------

    def upload_document(
        self,
        folder: Folder,
        file_name: str,
        file_data: BinaryIO,
        file_size: int,
        owner_id: int,
        mime_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        current_folder_size: int = 0,
    ) -> Tuple[Document, DocumentVersion]:
        """
        Upload a new document to a folder.

        1. Validate against folder constraints
        2. Write physical file to disk
        3. Create Document metadata
        4. Create initial DocumentVersion
        5. Return both records (caller persists to DB)

        Raises AppOSValidationError on validation failure.
        """
        # Detect MIME
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(file_name)
            mime_type = mime_type or "application/octet-stream"

        # Validate
        valid, error = self.validate_upload(
            folder, file_name, file_size, mime_type, current_folder_size
        )
        if not valid:
            raise AppOSValidationError(
                error or "Upload validation failed",
                object_ref=f"{self._app}.documents.upload",
            )

        # Generate unique file path to avoid collisions
        now = datetime.now(timezone.utc)
        safe_name = self._safe_filename(file_name)
        timestamp_prefix = now.strftime("%Y%m%d_%H%M%S")
        unique_name = f"{timestamp_prefix}_{safe_name}"
        relative_path = f"{folder.path}/{unique_name}"

        # Write physical file
        physical_path = self._documents_root / folder.path / unique_name
        physical_path.parent.mkdir(parents=True, exist_ok=True)

        bytes_written = 0
        file_hash = hashlib.sha256()
        with open(physical_path, "wb") as f:
            while True:
                chunk = file_data.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                file_hash.update(chunk)
                bytes_written += len(chunk)

        logger.info(
            f"Uploaded: {relative_path} ({bytes_written} bytes, "
            f"sha256={file_hash.hexdigest()[:12]})"
        )

        # Create Document metadata
        doc = Document(
            name=file_name,
            file_path=relative_path,
            folder_id=folder.id,
            app_id=folder.app_id,
            mime_type=mime_type,
            size_bytes=bytes_written,
            version=1,
            tags=tags or [],
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )

        # Create initial version
        version = DocumentVersion(
            document_id=None,  # Set after DB insert assigns doc.id
            version=1,
            file_path=relative_path,
            size_bytes=bytes_written,
            uploaded_by=owner_id,
            uploaded_at=now,
            change_note="Initial upload",
        )

        return doc, version

    def upload_new_version(
        self,
        document: Document,
        folder: Folder,
        file_name: str,
        file_data: BinaryIO,
        file_size: int,
        uploaded_by: int,
        change_note: Optional[str] = None,
        current_folder_size: int = 0,
    ) -> Tuple[Document, DocumentVersion]:
        """
        Upload a new version of an existing document.

        1. Validate against folder constraints
        2. Write new physical file (keeps old version file intact)
        3. Increment version number on Document
        4. Create new DocumentVersion record
        5. Return updated Document + new version record
        """
        mime_type = document.mime_type

        # Validate
        valid, error = self.validate_upload(
            folder, file_name, file_size, mime_type, current_folder_size
        )
        if not valid:
            raise AppOSValidationError(
                error or "Upload validation failed",
                object_ref=f"{self._app}.documents.upload_version",
            )

        now = datetime.now(timezone.utc)
        new_version_num = document.version + 1
        safe_name = self._safe_filename(file_name)
        unique_name = f"v{new_version_num}_{now.strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        relative_path = f"{folder.path}/{unique_name}"

        # Write physical file
        physical_path = self._documents_root / folder.path / unique_name
        physical_path.parent.mkdir(parents=True, exist_ok=True)

        bytes_written = 0
        with open(physical_path, "wb") as f:
            while True:
                chunk = file_data.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)

        logger.info(
            f"New version v{new_version_num} for doc '{document.name}': "
            f"{relative_path} ({bytes_written} bytes)"
        )

        # Update Document metadata
        document.version = new_version_num
        document.file_path = relative_path
        document.size_bytes = bytes_written
        document.updated_at = now

        # Create version record
        version = DocumentVersion(
            document_id=document.id,
            version=new_version_num,
            file_path=relative_path,
            size_bytes=bytes_written,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            change_note=change_note or f"Version {new_version_num}",
        )

        return document, version

    # -------------------------------------------------------------------
    # Document Download / Delete
    # -------------------------------------------------------------------

    def get_physical_path(self, document: Document) -> Path:
        """Get the full physical path for a document's current version."""
        return self._documents_root / document.file_path

    def get_version_physical_path(self, version: DocumentVersion) -> Path:
        """Get the full physical path for a specific document version."""
        return self._documents_root / version.file_path

    def delete_document(
        self,
        document: Document,
        versions: Optional[List[DocumentVersion]] = None,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a document — soft or hard.

        Soft delete: Sets is_archived=True, keeps physical files.
        Hard delete: Removes physical files for all versions.
        """
        if hard_delete:
            # Delete all version files
            paths_to_delete = []
            if versions:
                for v in versions:
                    p = self._documents_root / v.file_path
                    paths_to_delete.append(p)
            else:
                # At minimum delete current file
                paths_to_delete.append(self._documents_root / document.file_path)

            for p in paths_to_delete:
                try:
                    if p.exists():
                        p.unlink()
                        logger.info(f"Deleted file: {p}")
                except OSError as e:
                    logger.error(f"Failed to delete {p}: {e}")

        # Mark as archived (caller persists to DB)
        document.is_archived = True
        document.updated_at = datetime.now(timezone.utc)
        return True

    # -------------------------------------------------------------------
    # Folder Cleanup (§5.17 auto_cleanup)
    # -------------------------------------------------------------------

    def cleanup_folder(
        self,
        folder: Folder,
        documents: List[Document],
        archive_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Run auto-cleanup on a folder based on its retention policy.

        Policy: folder.auto_cleanup = {
            "retention_days": 90,
            "archive_first": True
        }

        Returns summary: {"archived": N, "deleted": N, "errors": N}
        """
        if not folder.auto_cleanup:
            return {"archived": 0, "deleted": 0, "errors": 0}

        retention_days = folder.auto_cleanup.get("retention_days", 90)
        archive_first = folder.auto_cleanup.get("archive_first", True)
        now = datetime.now(timezone.utc)

        archived = 0
        deleted = 0
        errors = 0

        for doc in documents:
            if doc.is_archived:
                continue

            # Check age
            doc_date = doc.updated_at or doc.created_at
            if doc_date is None:
                continue

            # Ensure timezone-aware comparison
            if doc_date.tzinfo is None:
                doc_date = doc_date.replace(tzinfo=timezone.utc)

            age_days = (now - doc_date).days
            if age_days < retention_days:
                continue

            try:
                if archive_first and archive_callback:
                    archive_callback(doc)
                    archived += 1

                doc.is_archived = True
                doc.updated_at = now
                deleted += 1
                logger.info(
                    f"Cleanup: archived doc '{doc.name}' (age={age_days}d, "
                    f"retention={retention_days}d)"
                )
            except Exception as e:
                logger.error(f"Cleanup error for doc '{doc.name}': {e}")
                errors += 1

        return {"archived": archived, "deleted": deleted, "errors": errors}

    def get_folder_total_size(self, documents: List[Document]) -> int:
        """Calculate total size of all non-archived documents in a folder."""
        return sum(d.size_bytes for d in documents if not d.is_archived)

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """
        Sanitize a filename for safe filesystem storage.

        Removes path separators, null bytes, and leading dots.
        Preserves extension.
        """
        # Remove path components
        name = os.path.basename(filename)
        # Remove null bytes and control chars
        name = "".join(c for c in name if c.isprintable() and c not in '<>:"/\\|?*')
        # Remove leading dots (hidden files)
        name = name.lstrip(".")
        # Fallback
        if not name:
            name = "unnamed_document"
        # Limit length
        if len(name) > 200:
            base, ext = os.path.splitext(name)
            name = base[:200 - len(ext)] + ext
        return name

    @staticmethod
    def detect_mime_type(filename: str) -> str:
        """Detect MIME type from filename."""
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"

    def __repr__(self) -> str:
        return f"<DocumentService app='{self._app}' root='{self._documents_root}'>"
