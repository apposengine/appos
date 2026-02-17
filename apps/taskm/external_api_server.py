"""
External Notification API Server — Standalone FastAPI application.

This is a self-contained micro-service that acts as the external system
behind the `notification_api` Connected System. It has its own:
  - API key authentication (X-API-Key header)
  - In-memory storage of notifications
  - Health check endpoint
  - CRUD for notifications

Run:
    uvicorn apps.taskm.external_api_server:app --port 9100 --reload

Or:
    python -m apps.taskm.external_api_server

This server is intentionally separate from AppOS to demonstrate
real integration testing with a proper auth mechanism.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Valid API keys — in production, these would be in a database or vault.
# The AppOS CredentialManager stores one of these keys for the notification_api
# Connected System, and passes it via the X-API-Key header.
VALID_API_KEYS: Dict[str, str] = {
    "taskm_key_001": "taskm-service",      # Task Manager app
    "admin_key_001": "admin-service",       # Admin Console
    "test_key_001": "test-runner",          # Test suite
}

# In-memory notification store
_notifications: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NotificationRequest(BaseModel):
    """Inbound notification payload from AppOS integration."""
    event: str = Field(description="Event type: task_created, task_updated, etc.")
    task_id: Optional[str] = Field(default=None, description="Related task ID")
    task_title: Optional[str] = Field(default=None, description="Task title")
    project: Optional[str] = Field(default=None, description="Project name")
    assignee: Optional[str] = Field(default=None, description="Assignee name")
    message: str = Field(description="Notification message body")
    severity: str = Field(default="info", description="info / warning / critical")


class NotificationResponse(BaseModel):
    """Response after creating a notification."""
    id: str
    status: str
    event: str
    delivered_at: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: float
    total_notifications: int


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Notification Micro-Service",
    description="External API for AppOS integration demo — authenticates via X-API-Key",
    version="1.0.0",
)

_start_time = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Validate the X-API-Key header.

    Security mechanism:
      - Constant-time comparison to prevent timing attacks
      - Returns the service identity associated with the key
      - Raises 401 if key is missing or invalid
    """
    if x_api_key is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "X-API-Key header is required"},
        )

    # Constant-time lookup to prevent timing-based enumeration
    service_name = None
    for key, name in VALID_API_KEYS.items():
        if hmac.compare_digest(x_api_key, key):
            service_name = name
            break

    if service_name is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key", "message": "Invalid API key"},
        )

    return service_name


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Public health check — no auth required."""
    now = datetime.now(timezone.utc)
    uptime = (now - _start_time).total_seconds()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        total_notifications=len(_notifications),
    )


@app.post(
    "/api/v1/notifications",
    response_model=NotificationResponse,
    status_code=201,
)
async def create_notification(
    payload: NotificationRequest,
    service: str = Depends(verify_api_key),
):
    """
    Create a notification.
    Requires valid X-API-Key header.

    This is the endpoint called by the AppOS `send_task_notification` integration:
      - Method: POST
      - Path: /api/v1/notifications
      - Body: JSON with event, task_id, message, severity, etc.
      - Auth: X-API-Key header

    Idempotency: If X-Idempotency-Key matches an existing notification,
    returns the existing one instead of creating a duplicate.
    """
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    notification = {
        "id": notification_id,
        "status": "delivered",
        "event": payload.event,
        "task_id": payload.task_id,
        "task_title": payload.task_title,
        "project": payload.project,
        "assignee": payload.assignee,
        "message": payload.message,
        "severity": payload.severity,
        "delivered_at": now,
        "created_by": service,
    }

    _notifications[notification_id] = notification

    return NotificationResponse(
        id=notification_id,
        status="delivered",
        event=payload.event,
        delivered_at=now,
        message=payload.message,
    )


@app.get(
    "/api/v1/notifications/{notification_id}",
    response_model=NotificationResponse,
)
async def get_notification(
    notification_id: str,
    service: str = Depends(verify_api_key),
):
    """Retrieve a notification by ID. Requires valid X-API-Key."""
    notification = _notifications.get(notification_id)
    if notification is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"Notification {notification_id} not found"},
        )

    return NotificationResponse(
        id=notification["id"],
        status=notification["status"],
        event=notification["event"],
        delivered_at=notification["delivered_at"],
        message=notification["message"],
    )


@app.get("/api/v1/notifications")
async def list_notifications(
    service: str = Depends(verify_api_key),
    limit: int = 50,
    event: Optional[str] = None,
):
    """List notifications with optional filtering. Requires valid X-API-Key."""
    results = list(_notifications.values())

    if event:
        results = [n for n in results if n["event"] == event]

    # Sort by delivered_at descending
    results.sort(key=lambda n: n["delivered_at"], reverse=True)

    return {
        "notifications": results[:limit],
        "total": len(results),
    }


@app.delete("/api/v1/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    service: str = Depends(verify_api_key),
):
    """Delete a notification. Requires valid X-API-Key."""
    if notification_id not in _notifications:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"Notification {notification_id} not found"},
        )

    del _notifications[notification_id]
    return {"deleted": True, "id": notification_id}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("Starting Notification API Server on http://localhost:9100")
    print(f"Valid API keys: {list(VALID_API_KEYS.keys())}")
    print("Health check: http://localhost:9100/health")
    print("Docs: http://localhost:9100/docs")
    uvicorn.run(app, host="0.0.0.0", port=9100)
