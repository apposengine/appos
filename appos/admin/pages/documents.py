"""
AppOS Admin Console — Documents & Folders Page

Route: /admin/documents
Purpose: View and manage @document and @folder objects, upload files, browse storage.
Design ref: AppOS_Design.md §13 (Admin Console → Documents)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class DocumentsState(rx.State):
    """State for the documents management page."""

    # Documents list
    documents: list[dict] = []
    total_documents: int = 0

    # Folders list
    folders: list[dict] = []
    total_folders: int = 0

    # Current view
    current_folder: str = ""
    view_mode: str = "list"  # "list" | "grid"

    # Filters
    search_query: str = ""
    filter_app: str = ""
    filter_mime: str = ""

    # Upload state
    uploading: bool = False
    upload_progress: int = 0

    # Feedback
    action_message: str = ""

    def load_documents(self) -> None:
        """Load documents from the document service."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            # Get document objects from registry
            doc_objects = runtime.registry.get_by_type("document")
            folder_objects = runtime.registry.get_by_type("folder")

            docs = []
            for obj in doc_objects:
                meta = obj.metadata or {}
                docs.append({
                    "object_ref": obj.object_ref,
                    "name": obj.name,
                    "app_name": obj.app_name or "platform",
                    "folder": meta.get("folder", "/"),
                    "mime_type": meta.get("mime_type", "unknown"),
                    "size": meta.get("size", 0),
                    "version": meta.get("version", 1),
                    "created_by": meta.get("created_by", ""),
                    "created_at": meta.get("created_at", ""),
                    "is_active": obj.is_active,
                })

            folders = []
            for obj in folder_objects:
                meta = obj.metadata or {}
                folders.append({
                    "object_ref": obj.object_ref,
                    "name": obj.name,
                    "app_name": obj.app_name or "platform",
                    "path": meta.get("path", f"/{obj.name}"),
                    "allowed_types": meta.get("allowed_types", []),
                    "max_size_mb": meta.get("max_size_mb", 10),
                    "is_active": obj.is_active,
                })

            # Apply filters
            if self.filter_app:
                docs = [d for d in docs if d["app_name"] == self.filter_app]
                folders = [f for f in folders if f["app_name"] == self.filter_app]
            if self.search_query:
                q = self.search_query.lower()
                docs = [d for d in docs if q in d["name"].lower()]
                folders = [f for f in folders if q in f["name"].lower()]
            if self.current_folder:
                docs = [d for d in docs if d["folder"] == self.current_folder]

            self.documents = docs
            self.total_documents = len(docs)
            self.folders = folders
            self.total_folders = len(folders)

        except Exception as e:
            self.action_message = f"Error loading documents: {e}"

    def navigate_folder(self, folder_path: str) -> None:
        """Navigate to a folder."""
        self.current_folder = folder_path
        self.load_documents()

    def set_search(self, value: str) -> None:
        """Update search query and reload."""
        self.search_query = value
        self.load_documents()

    def set_filter_app(self, value: str) -> None:
        """Filter by app."""
        self.filter_app = value
        self.load_documents()

    def toggle_view(self) -> None:
        """Toggle between list and grid view."""
        self.view_mode = "grid" if self.view_mode == "list" else "list"

    async def handle_upload(self, files: list[rx.UploadFile]) -> None:
        """Handle document file upload."""
        self.uploading = True
        self.upload_progress = 0

        try:
            for i, file in enumerate(files):
                upload_data = await file.read()
                file_name = file.filename

                # Store via document service
                try:
                    from appos.documents.service import DocumentService
                    service = DocumentService()
                    service.store(
                        name=file_name,
                        content=upload_data,
                        folder=self.current_folder or "/",
                        mime_type=file.content_type or "application/octet-stream",
                    )
                except ImportError:
                    pass

                self.upload_progress = int((i + 1) / len(files) * 100)

            self.action_message = f"Uploaded {len(files)} file(s) successfully"
            self.load_documents()
        except Exception as e:
            self.action_message = f"Upload failed: {e}"
        finally:
            self.uploading = False


def folder_breadcrumb() -> rx.Component:
    """Breadcrumb navigation for folder hierarchy."""
    return rx.hstack(
        rx.link("Root", on_click=DocumentsState.navigate_folder(""), cursor="pointer"),
        rx.cond(
            DocumentsState.current_folder != "",
            rx.hstack(
                rx.text(" / "),
                rx.text(DocumentsState.current_folder, font_weight="bold"),
            ),
            rx.fragment(),
        ),
        spacing="2",
    )


def documents_list() -> rx.Component:
    """Main documents page content."""
    return rx.box(
        rx.heading("Documents & Folders", size="6"),
        rx.text("Manage @document and @folder objects across all apps."),
        rx.hstack(
            rx.input(
                placeholder="Search documents...",
                on_change=DocumentsState.set_search,
                width="300px",
            ),
            rx.select(
                ["", "crm", "platform"],
                placeholder="Filter by app",
                on_change=DocumentsState.set_filter_app,
            ),
            rx.button(
                rx.cond(
                    DocumentsState.view_mode == "list",
                    "Grid View",
                    "List View",
                ),
                on_click=DocumentsState.toggle_view,
                variant="outline",
            ),
            spacing="4",
            margin_bottom="16px",
        ),
        folder_breadcrumb(),
        # Folders section
        rx.cond(
            DocumentsState.total_folders > 0,
            rx.box(
                rx.heading("Folders", size="4", margin_top="16px"),
                rx.hstack(
                    rx.foreach(
                        DocumentsState.folders,
                        lambda f: rx.card(
                            rx.text(f["name"], font_weight="bold"),
                            rx.text(f"App: {f['app_name']}", size="1", color="gray"),
                            on_click=DocumentsState.navigate_folder(f["path"]),
                            cursor="pointer",
                            width="200px",
                        ),
                    ),
                    wrap="wrap",
                    spacing="4",
                ),
            ),
            rx.fragment(),
        ),
        # Documents section
        rx.box(
            rx.heading("Documents", size="4", margin_top="16px"),
            rx.cond(
                DocumentsState.total_documents > 0,
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("App"),
                            rx.table.column_header_cell("MIME Type"),
                            rx.table.column_header_cell("Size"),
                            rx.table.column_header_cell("Version"),
                            rx.table.column_header_cell("Status"),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(
                            DocumentsState.documents,
                            lambda doc: rx.table.row(
                                rx.table.cell(doc["name"]),
                                rx.table.cell(doc["app_name"]),
                                rx.table.cell(doc["mime_type"]),
                                rx.table.cell(str(doc["size"])),
                                rx.table.cell(str(doc["version"])),
                                rx.table.cell(
                                    rx.cond(
                                        doc["is_active"],
                                        rx.badge("Active", color_scheme="green"),
                                        rx.badge("Archived", color_scheme="gray"),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
                rx.text("No documents in this folder.", color="gray"),
            ),
        ),
        # Upload section
        rx.box(
            rx.heading("Upload", size="4", margin_top="24px"),
            rx.upload(
                rx.text("Drag & drop files here or click to browse"),
                border="1px dashed",
                padding="32px",
                text_align="center",
            ),
            rx.button(
                "Upload",
                on_click=DocumentsState.handle_upload(rx.upload_files()),
                loading=DocumentsState.uploading,
                margin_top="8px",
            ),
            margin_top="16px",
        ),
        rx.cond(
            DocumentsState.action_message != "",
            rx.callout(DocumentsState.action_message, margin_top="8px"),
            rx.fragment(),
        ),
        on_mount=DocumentsState.load_documents,
    )


def documents_page() -> rx.Component:
    """Admin documents page."""
    return admin_layout(documents_list())
