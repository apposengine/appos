"""
AppOS Error Hierarchy — Structured exceptions for AI-native debugging.

All errors include execution_id for end-to-end tracing.
When inside a process, also includes process_instance_id and step_name.
Stored in process_step_log.error_info JSON for failed steps.
Queryable via runtime.query_for_ai().

Hierarchy:
    AppOSError
    ├── AppOSSecurityError       — Access denied
    ├── AppOSDispatchError       — Object not found / cannot dispatch
    ├── AppOSValidationError     — Input validation failed
    ├── AppOSTimeoutError        — Execution exceeded timeout
    ├── AppOSIntegrationError    — External system call failed
    ├── AppOSRecordError         — Record operation failed
    ├── AppOSObjectNotFoundError — Object reference not found in registry
    ├── AppOSConfigError         — Configuration error
    └── AppOSSessionError        — Session/auth error
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AppOSError(Exception):
    """
    Base error for all AppOS engine failures.
    Structured for AI debugging — all context serializable to JSON.
    """

    def __init__(self, message: str, **context: Any):
        self.message = message
        self.execution_id: Optional[str] = context.get("execution_id")
        self.object_ref: Optional[str] = context.get("object_ref")
        self.object_type: Optional[str] = context.get("object_type")
        self.error_type: str = self.__class__.__name__
        self.context: Dict[str, Any] = context
        self.dependency_chain: List[str] = context.get("dependency_chain", [])
        self.process_instance_id: Optional[str] = context.get("process_instance_id")
        self.step_name: Optional[str] = context.get("step_name")
        self.timestamp: str = datetime.now(timezone.utc).isoformat()
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error to JSON-compatible dict for logging and DB storage."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "execution_id": self.execution_id,
            "object_ref": self.object_ref,
            "object_type": self.object_type,
            "process_instance_id": self.process_instance_id,
            "step_name": self.step_name,
            "dependency_chain": self.dependency_chain,
            "timestamp": self.timestamp,
            "context": {
                k: str(v) for k, v in self.context.items()
                if k not in (
                    "execution_id", "object_ref", "object_type",
                    "process_instance_id", "step_name", "dependency_chain",
                )
            },
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    def __repr__(self) -> str:
        parts = [f"{self.error_type}: {self.message}"]
        if self.object_ref:
            parts.append(f"object_ref={self.object_ref}")
        if self.execution_id:
            parts.append(f"execution_id={self.execution_id}")
        return " | ".join(parts)


class AppOSSecurityError(AppOSError):
    """
    Access denied. Logged to security/ log files.
    Includes user_id, user_groups, and the object_ref that was denied.
    """

    def __init__(self, message: str, **context: Any):
        self.user_id: Optional[str] = context.get("user_id")
        self.user_groups: Optional[list] = context.get("user_groups")
        self.required_permission: Optional[str] = context.get("required_permission")
        super().__init__(message, **context)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["user_id"] = self.user_id
        d["user_groups"] = self.user_groups
        d["required_permission"] = self.required_permission
        return d


class AppOSDispatchError(AppOSError):
    """Object not found or cannot be dispatched to the target type."""
    pass


class AppOSValidationError(AppOSError):
    """
    Input validation failed (Pydantic, MIME type, constraints).
    Includes field-level error details.
    """

    def __init__(self, message: str, **context: Any):
        self.validation_errors: Optional[list] = context.get("validation_errors")
        super().__init__(message, **context)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["validation_errors"] = self.validation_errors
        return d


class AppOSTimeoutError(AppOSError):
    """Execution exceeded timeout (process step, integration call)."""

    def __init__(self, message: str, **context: Any):
        self.timeout_seconds: Optional[int] = context.get("timeout_seconds")
        super().__init__(message, **context)


class AppOSIntegrationError(AppOSError):
    """External system call failed (REST API, FTP, SMTP, etc.)."""

    def __init__(self, message: str, **context: Any):
        self.connected_system: Optional[str] = context.get("connected_system")
        self.status_code: Optional[int] = context.get("status_code")
        self.response_body: Optional[str] = context.get("response_body")
        super().__init__(message, **context)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["connected_system"] = self.connected_system
        d["status_code"] = self.status_code
        return d


class AppOSRecordError(AppOSError):
    """Record operation failed (create, update, delete, query)."""

    def __init__(self, message: str, **context: Any):
        self.record_type: Optional[str] = context.get("record_type")
        self.record_id: Optional[int] = context.get("record_id")
        self.operation: Optional[str] = context.get("operation")
        super().__init__(message, **context)


class AppOSObjectNotFoundError(AppOSError):
    """Object reference not found in the registry."""
    pass


class AppOSConfigError(AppOSError):
    """Configuration error — invalid appos.yaml or app.yaml."""
    pass


class AppOSSessionError(AppOSError):
    """Session or authentication error."""
    pass
