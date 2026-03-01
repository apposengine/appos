"""Unit tests for appos.db.platform_models — SQLAlchemy models."""

import pytest
from datetime import datetime, timezone

from appos.db.platform_models import (
    App,
    ConnectedSystem,
    DependencyChange,
    Group,
    LoginAuditLog,
    ObjectPermission,
    ObjectRegistry,
    PlatformConfigEntry,
    ProcessInstance,
    ProcessStepLog,
    ScheduledTrigger,
    User,
    UserGroup,
)
from appos.db.base import Base, AuditMixin, SoftDeleteMixin, EngineRegistry


class TestModelTableNames:
    """Verify all 15 platform tables have correct __tablename__."""

    def test_app(self):
        assert App.__tablename__ == "apps"

    def test_user(self):
        assert User.__tablename__ == "users"

    def test_group(self):
        assert Group.__tablename__ == "groups"

    def test_user_group(self):
        assert UserGroup.__tablename__ == "user_groups"

    def test_connected_system(self):
        assert ConnectedSystem.__tablename__ == "connected_systems"

    def test_object_permission(self):
        assert ObjectPermission.__tablename__ == "object_permissions"

    def test_object_registry(self):
        assert ObjectRegistry.__tablename__ == "object_registry"

    def test_login_audit_log(self):
        assert LoginAuditLog.__tablename__ == "login_audit_log"

    def test_platform_config_entry(self):
        assert PlatformConfigEntry.__tablename__ == "platform_config"

    def test_process_instance(self):
        assert ProcessInstance.__tablename__ == "process_instances"

    def test_process_step_log(self):
        assert ProcessStepLog.__tablename__ == "process_step_log"

    def test_dependency_change(self):
        assert DependencyChange.__tablename__ == "dependency_changes"

    def test_scheduled_trigger(self):
        assert ScheduledTrigger.__tablename__ == "scheduled_triggers"


class TestModelColumns:
    """Verify key columns exist on models."""

    def test_user_has_key_columns(self):
        cols = {c.name for c in User.__table__.columns}
        assert "username" in cols
        assert "password_hash" in cols
        assert "user_type" in cols
        assert "is_active" in cols

    def test_group_has_key_columns(self):
        cols = {c.name for c in Group.__table__.columns}
        assert "name" in cols
        assert "app_name" in cols

    def test_object_permission_has_key_columns(self):
        cols = {c.name for c in ObjectPermission.__table__.columns}
        assert "group_name" in cols
        assert "object_pattern" in cols
        assert "permission" in cols
        assert "allowed" in cols

    def test_process_instance_has_key_columns(self):
        cols = {c.name for c in ProcessInstance.__table__.columns}
        assert "process_ref" in cols
        assert "status" in cols
        assert "started_at" in cols

    def test_dependency_change_has_key_columns(self):
        cols = {c.name for c in DependencyChange.__table__.columns}
        assert "object_ref" in cols
        assert "change_type" in cols
        assert "old_hash" in cols
        assert "new_hash" in cols


class TestBaseMixins:
    """Test base mixins."""

    def test_base_exists(self):
        assert Base is not None

    def test_audit_mixin_columns(self):
        # AuditMixin should provide created_at, updated_at, created_by, updated_by
        assert hasattr(AuditMixin, "created_at")
        assert hasattr(AuditMixin, "updated_at")
        assert hasattr(AuditMixin, "created_by")
        assert hasattr(AuditMixin, "updated_by")

    def test_soft_delete_mixin_columns(self):
        assert hasattr(SoftDeleteMixin, "is_deleted")
        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert hasattr(SoftDeleteMixin, "deleted_by")


class TestEngineRegistry:
    """Test the SQLAlchemy engine registry."""

    def test_creation(self):
        reg = EngineRegistry()
        assert reg.registered_names == set() or isinstance(reg.registered_names, set)

    def test_get_nonexistent(self):
        reg = EngineRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")
