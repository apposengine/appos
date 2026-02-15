"""
AppOS Platform Models — All SQLAlchemy models for the appos_core database.

Tables defined here (16 platform tables):
1.  users                   — User accounts (basic/system_admin/service_account)
2.  groups                  — Access control groups
3.  user_groups             — User ↔ Group junction
4.  apps                    — Application registry
5.  group_apps              — Group ↔ App junction
6.  object_permission       — Unified 6-permission model with wildcards
7.  connected_systems       — External connections (DB, API, FTP, SMTP, IMAP)
8.  connected_system_groups — ConnSys ↔ Group junction
9.  process_instances       — Process execution tracking (partitioned)
10. process_step_log        — Step execution history (partitioned)
11. dependency_changes      — Dependency graph history
12. object_registry         — Discovered object catalog
13. platform_config         — Runtime-editable settings
14. scheduled_tasks         — Celery Beat schedule
15. login_audit_log         — Login attempt audit trail
16. event_log               — Custom business event logging (Tier 2)

Matches AppOS_Database_Design.md v1.0 and AppOS_Design.md v2.1 §5.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from appos.db.base import AuditMixin, Base, SoftDeleteMixin


# ---------------------------------------------------------------------------
# 1. Users
# ---------------------------------------------------------------------------

class User(Base, AuditMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    user_type = Column(String(20), default="basic", nullable=False, index=True)
    preferred_language = Column(String(10), default="en", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    last_login = Column(DateTime(timezone=True), index=True)
    api_key_hash = Column(String(255), nullable=True)

    # Relationships
    groups = relationship(
        "Group",
        secondary="user_groups",
        back_populates="users",
        lazy="selectin",
        primaryjoin="User.id == UserGroup.user_id",
        secondaryjoin="Group.id == UserGroup.group_id",
    )

    __table_args__ = (
        CheckConstraint(
            "user_type IN ('basic', 'system_admin', 'service_account')",
            name="ck_users_user_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', type='{self.user_type}')>"


# ---------------------------------------------------------------------------
# 2. Groups
# ---------------------------------------------------------------------------

class Group(Base, AuditMixin):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    type = Column(String(20), default="security", nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    users = relationship(
        "User",
        secondary="user_groups",
        back_populates="groups",
        lazy="selectin",
        primaryjoin="Group.id == UserGroup.group_id",
        secondaryjoin="User.id == UserGroup.user_id",
    )
    apps = relationship("App", secondary="group_apps", back_populates="groups", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "type IN ('security', 'team', 'app', 'system')",
            name="ck_groups_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Group(id={self.id}, name='{self.name}', type='{self.type}')>"


# ---------------------------------------------------------------------------
# 3. User-Groups Junction
# ---------------------------------------------------------------------------

class UserGroup(Base):
    __tablename__ = "user_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group"),
        Index("idx_ug_user_id", "user_id"),
        Index("idx_ug_group_id", "group_id"),
    )


# ---------------------------------------------------------------------------
# 4. Apps
# ---------------------------------------------------------------------------

class App(Base, AuditMixin):
    __tablename__ = "apps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(20), default="1.0.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    environment = Column(String(20), default="dev", nullable=False, index=True)
    db_connected_system = Column(String(100), nullable=True)
    theme = Column(JSON, default=dict, nullable=False)
    security_defaults = Column(JSON, default=dict, nullable=False)
    config = Column(JSON, default=dict, nullable=False)

    # Relationships
    groups = relationship("Group", secondary="group_apps", back_populates="apps", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "environment IN ('dev', 'staging', 'prod')",
            name="ck_apps_environment",
        ),
    )

    def __repr__(self) -> str:
        return f"<App(id={self.id}, short_name='{self.short_name}')>"


# ---------------------------------------------------------------------------
# 5. Group-Apps Junction
# ---------------------------------------------------------------------------

class GroupApp(Base):
    __tablename__ = "group_apps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    app_id = Column(Integer, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "app_id", name="uq_group_app"),
        Index("idx_ga_group_id", "group_id"),
        Index("idx_ga_app_id", "app_id"),
    )


# ---------------------------------------------------------------------------
# 6. Object Permissions
# ---------------------------------------------------------------------------

class ObjectPermission(Base):
    __tablename__ = "object_permission"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(100), nullable=False, index=True)
    object_ref = Column(String(255), nullable=False, index=True)
    permission = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("group_name", "object_ref", "permission", name="uq_perm"),
        CheckConstraint(
            "permission IN ('view', 'use', 'create', 'update', 'delete', 'admin')",
            name="ck_perm_type",
        ),
        Index("idx_perm_group_obj", "group_name", "object_ref"),
    )

    def __repr__(self) -> str:
        return f"<ObjectPermission({self.group_name} → {self.object_ref}: {self.permission})>"


# ---------------------------------------------------------------------------
# 7. Connected Systems
# ---------------------------------------------------------------------------

class ConnectedSystem(Base, AuditMixin):
    __tablename__ = "connected_systems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    connection_details = Column(JSON, default=dict, nullable=False)
    auth_type = Column(String(20), default="none", nullable=False)
    credentials_encrypted = Column(LargeBinary, nullable=True)
    environment_overrides = Column(JSON, default=dict, nullable=False)
    health_check = Column(JSON, default=dict, nullable=False)
    is_sensitive = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "type IN ('database', 'rest_api', 'ftp', 'smtp', 'imap', 'custom')",
            name="ck_cs_type",
        ),
        CheckConstraint(
            "auth_type IN ('none', 'basic', 'oauth2', 'api_key', 'certificate')",
            name="ck_cs_auth_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<ConnectedSystem(name='{self.name}', type='{self.type}')>"


# ---------------------------------------------------------------------------
# 8. Connected System Groups Junction
# ---------------------------------------------------------------------------

class ConnectedSystemGroup(Base):
    __tablename__ = "connected_system_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connected_system_id = Column(
        Integer, ForeignKey("connected_systems.id", ondelete="CASCADE"), nullable=False
    )
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("connected_system_id", "group_id", name="uq_cs_group"),
        Index("idx_csg_cs_id", "connected_system_id"),
        Index("idx_csg_group_id", "group_id"),
    )


# ---------------------------------------------------------------------------
# 9. Process Instances (Partitioned in production; flat table for dev)
# ---------------------------------------------------------------------------

class ProcessInstance(Base):
    __tablename__ = "process_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String(50), unique=True, nullable=False, index=True)
    process_name = Column(String(100), nullable=False, index=True)
    app_name = Column(String(50), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    current_step = Column(String(100), nullable=True)
    inputs = Column(JSON, default=dict, nullable=False)
    variables = Column(JSON, default=dict, nullable=False)
    variable_visibility = Column(JSON, default=dict, nullable=False)
    outputs = Column(JSON, nullable=True)
    error_info = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    started_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_instance_id = Column(Integer, nullable=True, index=True)
    triggered_by = Column(String(255), nullable=True)

    # Audit fields (not using mixin to match exact schema)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','paused','completed','failed','cancelled','interrupted')",
            name="ck_pi_status",
        ),
        Index("idx_pi_app_status", "app_name", "status"),
    )

    def __repr__(self) -> str:
        return f"<ProcessInstance(instance_id='{self.instance_id}', status='{self.status}')>"


# ---------------------------------------------------------------------------
# 10. Process Step Log (Partitioned in production; flat table for dev)
# ---------------------------------------------------------------------------

class ProcessStepLog(Base):
    __tablename__ = "process_step_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_instance_id = Column(Integer, ForeignKey("process_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name = Column(String(100), nullable=False, index=True)
    rule_ref = Column(String(200), nullable=False)
    status = Column(String(30), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Numeric(12, 3), nullable=True)
    inputs = Column(JSON, nullable=True)
    outputs = Column(JSON, nullable=True)
    error_info = Column(JSON, nullable=True)
    attempt = Column(Integer, default=1, nullable=False)
    is_fire_and_forget = Column(Boolean, default=False, nullable=False)
    is_parallel = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','async_dispatched','interrupted')",
            name="ck_psl_status",
        ),
        Index("idx_psl_instance_step", "process_instance_id", "step_name", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<ProcessStepLog(step='{self.step_name}', status='{self.status}')>"


# ---------------------------------------------------------------------------
# 11. Dependency Changes
# ---------------------------------------------------------------------------

class DependencyChange(Base):
    __tablename__ = "dependency_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_ref = Column(String(255), nullable=False, index=True)
    change_type = Column(String(20), nullable=False, index=True)
    old_hash = Column(String(64), nullable=True)
    new_hash = Column(String(64), nullable=True)
    details = Column(JSON, nullable=True)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    changed_by = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('added', 'removed', 'modified')",
            name="ck_depchange_type",
        ),
    )


# ---------------------------------------------------------------------------
# 12. Object Registry
# ---------------------------------------------------------------------------

class ObjectRegistry(Base):
    __tablename__ = "object_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_ref = Column(String(255), unique=True, nullable=False)
    object_type = Column(String(30), nullable=False, index=True)
    app_name = Column(String(50), nullable=True, index=True)
    module_path = Column(String(500), nullable=False)
    file_path = Column(String(500), nullable=False)
    source_hash = Column(String(64), nullable=False)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    discovered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "object_type IN ("
            "'record','expression_rule','constant','process','step',"
            "'integration','web_api','interface','page','site',"
            "'document','folder','translation_set','connected_system'"
            ")",
            name="ck_or_type",
        ),
        Index("idx_or_type_app", "object_type", "app_name"),
    )


# ---------------------------------------------------------------------------
# 13. Platform Config
# ---------------------------------------------------------------------------

class PlatformConfigEntry(Base):
    __tablename__ = "platform_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    category = Column(String(50), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# 14. Scheduled Tasks
# ---------------------------------------------------------------------------

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200), unique=True, nullable=False)
    schedule = Column(String(100), nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)
    app_name = Column(String(50), nullable=False, index=True)
    process_name = Column(String(100), nullable=False)
    inputs = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# 15. Login Audit Log
# ---------------------------------------------------------------------------

class LoginAuditLog(Base):
    __tablename__ = "login_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    success = Column(Boolean, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max
    user_agent = Column(Text, nullable=True)
    failure_reason = Column(String(100), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


# ---------------------------------------------------------------------------
# 16. Event Log (per-app custom business event logging)
# ---------------------------------------------------------------------------

class EventLog(Base):
    """
    Custom business event logging table.

    Apps write events here via engine.log_event() for auditing,
    compliance, and business intelligence. Tier 2 (DB) logging.

    Design ref: AppOS_Design.md §14 (Tier 2: App Runtime Logs → Database)
    """
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_name = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    event_name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_username = Column(String(100), nullable=True)
    object_ref = Column(String(255), nullable=True, index=True)
    record_type = Column(String(100), nullable=True)
    record_id = Column(Integer, nullable=True)
    payload = Column(JSON, default=dict, nullable=False)
    severity = Column(String(20), default="info", nullable=False)
    correlation_id = Column(String(50), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="ck_eventlog_severity",
        ),
        Index("idx_el_app_type", "app_name", "event_type"),
        Index("idx_el_app_created", "app_name", "created_at"),
    )
