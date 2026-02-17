"""Task Manager  Records. Each record is defined in its own module."""

from .project import Project
from .task import Task
from .comment import Comment
from .document import Document
from .document_version import DocumentVersion
from .folder import Folder

# Resolve cross-file forward references (e.g. Project ↔ Task, Document ↔ Folder)
for _model in (Project, Task, Comment, Document, DocumentVersion, Folder):
    _model.model_rebuild()

__all__ = ["Project", "Task", "Comment", "Document", "DocumentVersion", "Folder"]
