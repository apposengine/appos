"""
AppOS Document & Folder Management.

Platform-level records for file management with versioning.
Physical storage: apps/{app}/runtime/documents/{folder_path}/

Design refs:
    §5.16 Document (L1390)
    §5.17 Folder (L1467)
"""

from appos.documents.models import Document, DocumentVersion, Folder
from appos.documents.service import DocumentService

__all__ = [
    "Document",
    "DocumentVersion",
    "Folder",
    "DocumentService",
]
