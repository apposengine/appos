"""
AppOS CRUD Service Generator — Auto-generates Record CRUD services with
audit logging, soft delete, event hooks, and security checks.

Provides:
    - RecordService: Base class for all generated CRUD services
    - ServiceGenerator: Generates per-record service files
    - Audit log integration (field-level change tracking)

Generated service methods:
    - create(data) → instance
    - get(id) → instance
    - get_by(field, value) → instance
    - update(id, data) → instance
    - delete(id) → bool
    - list(filters, page, page_size) → list
    - search(query, fields) → list
    - count(filters) → int

Design refs: AppOS_Design.md §9 (Generated CRUD Service), §5.7 (Record)
"""

from __future__ import annotations

import logging

from appos.utilities.utils import to_snake
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from appos.db.base import Base

logger = logging.getLogger("appos.generators.service_generator")


# ---------------------------------------------------------------------------
# Base Record Service
# ---------------------------------------------------------------------------

class RecordService:
    """
    Base CRUD service for auto-generated Record models.

    Subclasses set `model` and `pydantic_model` class vars.
    All operations respect soft-delete, audit logging, and event hooks.

    Usage:
        class CustomerService(RecordService):
            model = CustomerModel
            pydantic_model = Customer
            app_name = "crm"
            audit_enabled = True
            soft_delete_enabled = True
    """

    model: Type[Base] = None           # SQLAlchemy model class
    pydantic_model: type = None        # Original Pydantic @record class
    app_name: str = ""
    audit_enabled: bool = False
    soft_delete_enabled: bool = False

    # Event hooks — override in subclass or set via Meta.on_create etc.
    on_create_hooks: List[str] = []
    on_update_hooks: List[str] = []
    on_delete_hooks: List[str] = []

    def __init__(self, session_factory=None):
        """
        Args:
            session_factory: Callable that returns a SQLAlchemy Session.
        """
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        if self._session_factory is None:
            raise RuntimeError(
                f"No session factory for {self.__class__.__name__}. "
                "Pass session_factory or configure Connected System."
            )
        return self._session_factory()

    # -------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------

    def create(
        self,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> Any:
        """
        Create a new record.

        Args:
            data: Field values for the new record.
            user_id: ID of the user creating the record (for audit).
            session: Optional existing session (for transaction grouping).

        Returns:
            The created model instance.
        """
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            # Set audit fields
            if user_id:
                data["created_by"] = user_id
                data["updated_by"] = user_id

            instance = self.model(**data)
            session.add(instance)
            session.flush()  # Get ID before commit

            # Audit log
            if self.audit_enabled:
                self._log_create(session, instance, user_id)

            if own_session:
                session.commit()

            # Fire event hooks
            self._fire_hooks(self.on_create_hooks, instance, data)

            logger.debug(f"Created {self.model.__name__} id={instance.id}")
            return instance

        except Exception:
            if own_session:
                session.rollback()
            raise
        finally:
            if own_session:
                session.close()

    # -------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------

    def get(self, record_id: int, session: Optional[Session] = None) -> Optional[Any]:
        """Get a record by ID. Respects soft-delete."""
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            query = session.query(self.model).filter(self.model.id == record_id)

            if self.soft_delete_enabled and hasattr(self.model, "is_deleted"):
                query = query.filter(self.model.is_deleted == False)

            return query.first()
        finally:
            if own_session:
                session.close()

    def get_by(
        self,
        field: str,
        value: Any,
        session: Optional[Session] = None,
    ) -> Optional[Any]:
        """Get a record by a specific field value."""
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            column = getattr(self.model, field, None)
            if column is None:
                raise ValueError(f"Field '{field}' not found on {self.model.__name__}")

            query = session.query(self.model).filter(column == value)

            if self.soft_delete_enabled and hasattr(self.model, "is_deleted"):
                query = query.filter(self.model.is_deleted == False)

            return query.first()
        finally:
            if own_session:
                session.close()

    # -------------------------------------------------------------------
    # UPDATE
    # -------------------------------------------------------------------

    def update(
        self,
        record_id: int,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> Optional[Any]:
        """
        Update a record by ID.

        Only updates fields present in `data` (partial update).
        Tracks field-level changes for audit log.
        """
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            instance = self.get(record_id, session=session)
            if not instance:
                return None

            # Track changes for audit
            changes: Dict[str, Tuple[Any, Any]] = {}

            for field_name, new_value in data.items():
                if hasattr(instance, field_name):
                    old_value = getattr(instance, field_name)
                    if old_value != new_value:
                        changes[field_name] = (old_value, new_value)
                        setattr(instance, field_name, new_value)

            # Update audit fields
            if user_id and hasattr(instance, "updated_by"):
                instance.updated_by = user_id
            if hasattr(instance, "updated_at"):
                instance.updated_at = datetime.now(timezone.utc)

            # Audit log
            if self.audit_enabled and changes:
                self._log_update(session, instance, changes, user_id)

            if own_session:
                session.commit()

            # Fire event hooks
            if changes:
                self._fire_hooks(self.on_update_hooks, instance, {"changes": changes})

            logger.debug(f"Updated {self.model.__name__} id={record_id}: {list(changes.keys())}")
            return instance

        except Exception:
            if own_session:
                session.rollback()
            raise
        finally:
            if own_session:
                session.close()

    # -------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------

    def delete(
        self,
        record_id: int,
        user_id: Optional[int] = None,
        hard: bool = False,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Delete a record. Uses soft-delete by default if enabled.

        Args:
            record_id: Record ID.
            user_id: ID of the user performing the delete.
            hard: If True, permanently delete even if soft-delete is enabled.
            session: Optional existing session.

        Returns:
            True if record was deleted/deactivated.
        """
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            instance = session.query(self.model).filter(self.model.id == record_id).first()
            if not instance:
                return False

            if self.soft_delete_enabled and not hard and hasattr(instance, "is_deleted"):
                # Soft delete
                instance.is_deleted = True
                instance.deleted_at = datetime.now(timezone.utc)
                if user_id and hasattr(instance, "deleted_by"):
                    instance.deleted_by = user_id
            else:
                # Hard delete
                session.delete(instance)

            # Audit log
            if self.audit_enabled:
                self._log_delete(session, instance, user_id)

            if own_session:
                session.commit()

            # Fire event hooks
            self._fire_hooks(self.on_delete_hooks, instance, {})

            logger.debug(f"Deleted {self.model.__name__} id={record_id} (soft={self.soft_delete_enabled and not hard})")
            return True

        except Exception:
            if own_session:
                session.rollback()
            raise
        finally:
            if own_session:
                session.close()

    # -------------------------------------------------------------------
    # LIST & SEARCH
    # -------------------------------------------------------------------

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 25,
        order_by: Optional[str] = None,
        descending: bool = False,
        session: Optional[Session] = None,
    ) -> List[Any]:
        """
        List records with optional filtering and pagination.

        Args:
            filters: Dict of {field: value} for exact match filtering.
            page: Page number (1-indexed).
            page_size: Records per page.
            order_by: Field name to sort by.
            descending: Sort descending if True.

        Returns:
            List of model instances.
        """
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            query = session.query(self.model)

            # Soft delete filter
            if self.soft_delete_enabled and hasattr(self.model, "is_deleted"):
                query = query.filter(self.model.is_deleted == False)

            # Apply filters
            if filters:
                for field_name, value in filters.items():
                    column = getattr(self.model, field_name, None)
                    if column is not None:
                        query = query.filter(column == value)

            # Ordering
            if order_by:
                col = getattr(self.model, order_by, None)
                if col is not None:
                    query = query.order_by(col.desc() if descending else col.asc())
            elif hasattr(self.model, "created_at"):
                query = query.order_by(self.model.created_at.desc())

            # Pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

            return query.all()

        finally:
            if own_session:
                session.close()

    def search(
        self,
        query_text: str,
        search_fields: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 25,
        session: Optional[Session] = None,
    ) -> List[Any]:
        """
        Full-text search across specified fields using ILIKE.

        Args:
            query_text: Search query string.
            search_fields: Fields to search in. Uses Meta.search_fields if not specified.
            page: Page number.
            page_size: Records per page.

        Returns:
            List of matching model instances.
        """
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            query = session.query(self.model)

            if self.soft_delete_enabled and hasattr(self.model, "is_deleted"):
                query = query.filter(self.model.is_deleted == False)

            # Build OR conditions for search
            if search_fields and query_text:
                conditions = []
                for field_name in search_fields:
                    column = getattr(self.model, field_name, None)
                    if column is not None:
                        conditions.append(column.ilike(f"%{query_text}%"))
                if conditions:
                    query = query.filter(or_(*conditions))

            offset = (page - 1) * page_size
            return query.offset(offset).limit(page_size).all()

        finally:
            if own_session:
                session.close()

    def count(
        self,
        filters: Optional[Dict[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> int:
        """Count records matching filters."""
        own_session = session is None
        if own_session:
            session = self._get_session()

        try:
            query = session.query(func.count(self.model.id))

            if self.soft_delete_enabled and hasattr(self.model, "is_deleted"):
                query = query.filter(self.model.is_deleted == False)

            if filters:
                for field_name, value in filters.items():
                    column = getattr(self.model, field_name, None)
                    if column is not None:
                        query = query.filter(column == value)

            return query.scalar() or 0

        finally:
            if own_session:
                session.close()

    # -------------------------------------------------------------------
    # Audit Logging
    # -------------------------------------------------------------------

    def _log_create(self, session: Session, instance: Any, user_id: Optional[int]) -> None:
        """Log a CREATE operation to the audit table (one row per field)."""
        if not self._get_audit_model():
            return

        AuditModel = self._get_audit_model()
        execution_id = self._get_execution_id()

        for col in self.model.__table__.columns:
            if col.name in ("id", "created_at", "updated_at", "created_by", "updated_by"):
                continue
            value = getattr(instance, col.name, None)
            if value is not None:
                audit_entry = AuditModel(
                    record_id=instance.id,
                    field_name=col.name,
                    old_value=None,
                    new_value=str(value),
                    operation="create",
                    changed_by=user_id or 0,
                    execution_id=execution_id,
                )
                session.add(audit_entry)

    def _log_update(
        self,
        session: Session,
        instance: Any,
        changes: Dict[str, Tuple[Any, Any]],
        user_id: Optional[int],
    ) -> None:
        """Log an UPDATE operation (one row per changed field)."""
        if not self._get_audit_model():
            return

        AuditModel = self._get_audit_model()
        execution_id = self._get_execution_id()

        for field_name, (old_val, new_val) in changes.items():
            audit_entry = AuditModel(
                record_id=instance.id,
                field_name=field_name,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                operation="update",
                changed_by=user_id or 0,
                execution_id=execution_id,
            )
            session.add(audit_entry)

    def _log_delete(self, session: Session, instance: Any, user_id: Optional[int]) -> None:
        """Log a DELETE operation (single row with full record JSON)."""
        if not self._get_audit_model():
            return

        import json
        AuditModel = self._get_audit_model()
        execution_id = self._get_execution_id()

        # Serialize full record
        record_data = {}
        for col in self.model.__table__.columns:
            val = getattr(instance, col.name, None)
            record_data[col.name] = str(val) if val is not None else None

        audit_entry = AuditModel(
            record_id=instance.id,
            field_name="_record",
            old_value=json.dumps(record_data),
            new_value=None,
            operation="delete",
            changed_by=user_id or 0,
            execution_id=execution_id,
        )
        session.add(audit_entry)

    def _get_audit_model(self) -> Optional[type]:
        """Get the audit log model class (lazy import from generated code)."""
        # This will be overridden by generated service subclasses
        return getattr(self, "_audit_model", None)

    @staticmethod
    def _get_execution_id() -> Optional[str]:
        """Get the current execution ID from context."""
        try:
            from appos.engine.context import get_execution_context
            ctx = get_execution_context()
            return ctx.execution_id if ctx else None
        except Exception:
            return None

    # -------------------------------------------------------------------
    # Event Hooks
    # -------------------------------------------------------------------

    def _fire_hooks(self, hooks: List[str], instance: Any, data: Dict[str, Any]) -> None:
        """
        Fire event hooks (on_create, on_update, on_delete).

        Each hook is an object_ref (rule or process) dispatched via engine.dispatch().
        """
        if not hooks:
            return

        try:
            from appos.engine.runtime import get_runtime
            runtime = get_runtime()
            for hook_ref in hooks:
                logger.debug(f"Firing hook: {hook_ref} for {self.model.__name__} id={instance.id}")
                runtime.dispatch(hook_ref, inputs={"record_id": instance.id, **data})
        except Exception as e:
            logger.warning(f"Hook dispatch failed: {e}")


# ---------------------------------------------------------------------------
# Service Generator — generates per-record service Python files
# ---------------------------------------------------------------------------

def generate_service_code(
    class_name: str,
    app_name: str,
    table_name: str,
    audit: bool = False,
    soft_delete: bool = False,
    search_fields: Optional[List[str]] = None,
    on_create: Optional[List[str]] = None,
    on_update: Optional[List[str]] = None,
    on_delete: Optional[List[str]] = None,
) -> str:
    """
    Generate a RecordService subclass for a @record.

    Returns Python source code string.
    """
    model_name = f"{class_name}Model"
    service_name = f"{class_name}Service"
    model_import = f"from appos.generators.generated.models.{to_snake(class_name)} import {model_name}"

    search_fields_str = repr(search_fields or [])
    on_create_str = repr(on_create or [])
    on_update_str = repr(on_update or [])
    on_delete_str = repr(on_delete or [])

    audit_model_block = ""
    if audit:
        audit_model_block = f"""
    def _get_audit_model(self):
        # Lazy import to avoid circular deps
        try:
            from appos.generators.generated.models.{app_name}_{table_name}_audit_log import {class_name}AuditLogModel
            return {class_name}AuditLogModel
        except ImportError:
            return None
"""

    code = f'''"""
Auto-generated CRUD service for @record {class_name}.
App: {app_name}
Table: {table_name}

DO NOT EDIT — regenerate with `appos generate`.
"""

from typing import Any, Dict, List, Optional

{model_import}
from appos.generators.service_generator import RecordService


class {service_name}(RecordService):
    """CRUD service for {class_name} records."""

    model = {model_name}
    app_name = "{app_name}"
    audit_enabled = {audit}
    soft_delete_enabled = {soft_delete}

    # Event hooks from Meta
    on_create_hooks = {on_create_str}
    on_update_hooks = {on_update_str}
    on_delete_hooks = {on_delete_str}

    # Search fields from Meta
    _search_fields = {search_fields_str}

    def search(self, query_text: str, search_fields=None, **kwargs):
        return super().search(
            query_text,
            search_fields=search_fields or self._search_fields,
            **kwargs,
        )
{audit_model_block}
'''
    return code


def generate_and_write_service(
    record_class: type,
    app_name: str,
    output_dir: Optional[str] = None,
) -> str:
    """
    Generate and write a CRUD service file for a @record.

    Args:
        record_class: The @record Pydantic class.
        app_name: App short name.
        output_dir: Base output dir. Defaults to .appos/generated/.

    Returns:
        Path to the generated file.
    """
    from appos.generators.model_generator import parse_record

    if output_dir is None:
        from appos.engine.config import get_project_root
        output_dir = str(get_project_root() / ".appos" / "generated")

    parsed = parse_record(record_class, app_name)

    code = generate_service_code(
        class_name=parsed.class_name,
        app_name=parsed.app_name,
        table_name=parsed.table_name,
        audit=parsed.audit,
        soft_delete=parsed.soft_delete,
        search_fields=parsed.search_fields,
        on_create=parsed.on_create,
        on_update=parsed.on_update,
        on_delete=parsed.on_delete,
    )

    file_path = os.path.join(output_dir, "services", f"{to_snake(parsed.class_name)}_service.py")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    logger.info(f"Generated service: {file_path}")
    return file_path
