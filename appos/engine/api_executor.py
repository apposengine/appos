"""
AppOS API Executor — Inbound HTTP request pipeline for @web_api endpoints.

Pipeline (per-request):
    1. Extract auth (API key header / session cookie / OAuth token)
    2. Rate limit check (Redis DB 5)
    3. CSRF validation (state-changing methods)
    4. Create ExecutionContext from authenticated user
    5. Resolve handler → expression_rule or process via engine.dispatch()
    6. Response mapping + serialization

Relies on Reflex's internal FastAPI (app.api.add_api_route) for HTTP routing.
Does NOT start its own server — single-port architecture per Design §12.

Design refs:
    §5.12 Web API         — Decorator, URL resolution, auth, async mode
    §6    Security Model  — Session auth, service account flow, CSRF
    §8    Runtime Engine  — engine.dispatch() for handler execution
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from appos.engine.cache import RedisCache
from appos.engine.context import ExecutionContext, set_execution_context
from appos.engine.errors import (
    AppOSDispatchError,
    AppOSError,
    AppOSSecurityError,
    AppOSSessionError,
    AppOSValidationError,
)
from appos.engine.logging import log, log_rule_execution, log_system_event
from appos.engine.registry import ObjectRegistryManager, RegisteredObject

logger = logging.getLogger("appos.engine.api_executor")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class APIRequest(BaseModel):
    """Normalized inbound API request (extracted from Starlette Request)."""

    method: str
    path: str
    path_params: Dict[str, str] = {}
    query_params: Dict[str, str] = {}
    headers: Dict[str, str] = {}
    body: Optional[Dict[str, Any]] = None
    client_ip: Optional[str] = None
    session_id: Optional[str] = None
    api_key: Optional[str] = None


class APIResponse(BaseModel):
    """Normalized outbound API response."""

    status_code: int = 200
    body: Any = None
    headers: Dict[str, str] = {}


class AsyncAPIResponse(BaseModel):
    """Response for async Web API calls — returns poll URL."""

    instance_id: str
    status: str = "pending"
    poll_url: str


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Sliding-window rate limiter backed by Redis DB 5.

    Key format: appos:rate:{app}:{api_name}:{client_identifier}
    Uses INCR + EXPIRE per window.
    """

    def __init__(self, rate_limit_cache: Optional[RedisCache] = None):
        self._cache = rate_limit_cache

    def check(
        self,
        app_name: str,
        api_name: str,
        client_id: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """
        Check if request is within rate limit.

        Returns:
            True if allowed, False if rate limit exceeded.
        """
        if self._cache is None or not self._cache.is_available:
            # No Redis → allow (degrade gracefully)
            return True

        key = f"{app_name}:{api_name}:{client_id}"
        count = self._cache.incr(key, ttl=window_seconds)

        if count < 0:
            # Redis failure → allow
            return True

        return count <= max_requests

    def get_remaining(
        self,
        app_name: str,
        api_name: str,
        client_id: str,
        max_requests: int,
    ) -> int:
        """Get remaining requests in current window."""
        if self._cache is None or not self._cache.is_available:
            return max_requests

        key = f"{app_name}:{api_name}:{client_id}"
        current = self._cache.get(key)
        if current is None:
            return max_requests
        return max(0, max_requests - int(current))


# ---------------------------------------------------------------------------
# API Executor — Inbound pipeline
# ---------------------------------------------------------------------------

class APIExecutor:
    """
    Processes inbound HTTP requests for @web_api endpoints.

    Lifecycle (per request):
        1. Authenticate → resolve user + groups
        2. Rate limit → reject if exceeded
        3. CSRF check → validate on POST/PUT/DELETE
        4. Set ExecutionContext → inject into contextvars
        5. Resolve handler → find @expression_rule or @process
        6. Map request inputs → call engine.dispatch()
        7. Map response → serialize and return

    Connected to Reflex via app.api.add_api_route() — see reflex_bridge.py.
    """

    def __init__(
        self,
        runtime,   # CentralizedRuntime — avoid circular import
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self._runtime = runtime
        self._rate_limiter = rate_limiter or RateLimiter(runtime.rate_limiter)

    async def execute(
        self,
        api_def: RegisteredObject,
        request: APIRequest,
    ) -> APIResponse:
        """
        Full inbound API pipeline.

        Args:
            api_def: The registered @web_api object (contains metadata).
            request: Normalized request data.

        Returns:
            APIResponse with status code, body, and headers.
        """
        meta = api_def.metadata
        app_name = api_def.app_name or ""
        api_name = meta.get("name", api_def.name)
        start_time = time.monotonic()

        try:
            # ── Step 1: Authenticate ──
            ctx = await self._authenticate(request, meta, app_name)
            set_execution_context(ctx)

            # ── Step 2: Rate limit ──
            rate_config = meta.get("rate_limit")
            if rate_config:
                client_id = request.client_ip or ctx.username
                allowed = self._rate_limiter.check(
                    app_name=app_name,
                    api_name=api_name,
                    client_id=client_id,
                    max_requests=rate_config.get("requests", 100),
                    window_seconds=rate_config.get("window", 60),
                )
                if not allowed:
                    return APIResponse(
                        status_code=429,
                        body={"error": "Rate limit exceeded", "retry_after": rate_config.get("window", 60)},
                        headers={"Retry-After": str(rate_config.get("window", 60))},
                    )

            # ── Step 3: CSRF validation (state-changing methods) ──
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                if ctx.session_id and not ctx.is_service_account:
                    csrf_token = request.headers.get("x-csrf-token", "")
                    if self._runtime.auth and not self._runtime.auth.validate_csrf(
                        ctx.session_id, csrf_token
                    ):
                        return APIResponse(
                            status_code=403,
                            body={"error": "Invalid CSRF token"},
                        )

            # ── Step 4: Permission check ──
            if self._runtime.security:
                self._runtime.security.check_permission(api_def.object_ref, "use")

            # ── Step 5: Resolve handler ──
            api_config = api_def.handler() if callable(api_def.handler) else {}
            handler_ref = api_config.get("handler")
            if not handler_ref:
                raise AppOSDispatchError(
                    f"Web API '{api_name}' has no handler configured",
                    object_ref=api_def.object_ref,
                )

            # Qualify handler ref with app name if not already qualified
            if handler_ref and "." in handler_ref and not handler_ref.startswith(f"{app_name}."):
                handler_ref = f"{app_name}.{handler_ref}"

            # ── Step 6: Map request inputs ──
            inputs = self._map_request_inputs(
                request=request,
                mapping=api_config.get("request_mapping", {}),
            )

            # ── Step 7: Check async mode ──
            is_async = api_config.get("async", False)

            if is_async:
                return await self._execute_async(
                    handler_ref=handler_ref,
                    inputs=inputs,
                    app_name=app_name,
                    api_name=api_name,
                    meta=meta,
                )

            # ── Step 8: Dispatch synchronously ──
            result = self._runtime.dispatch(handler_ref, inputs=inputs)

            # ── Step 9: Map response ──
            response_body = self._map_response(
                result=result,
                mapping=api_config.get("response_mapping", {}),
            )

            duration_ms = (time.monotonic() - start_time) * 1000
            self._log_api_execution(api_def, request, 200, duration_ms, meta)

            return APIResponse(status_code=200, body=response_body)

        except AppOSSecurityError as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            self._log_api_execution(api_def, request, 403, duration_ms, meta, error=str(e))
            return APIResponse(status_code=403, body={"error": "Access denied"})

        except AppOSSessionError:
            return APIResponse(status_code=401, body={"error": "Authentication required"})

        except AppOSValidationError as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            self._log_api_execution(api_def, request, 422, duration_ms, meta, error=str(e))
            return APIResponse(status_code=422, body={"error": str(e)})

        except AppOSDispatchError as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            self._log_api_execution(api_def, request, 500, duration_ms, meta, error=str(e))
            return APIResponse(status_code=500, body={"error": "Internal dispatch error"})

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.exception(f"Unhandled error in API {api_name}: {e}")
            self._log_api_execution(api_def, request, 500, duration_ms, meta, error=str(e))
            return APIResponse(status_code=500, body={"error": "Internal server error"})

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    async def _authenticate(
        self,
        request: APIRequest,
        meta: Dict[str, Any],
        app_name: str,
    ) -> ExecutionContext:
        """
        Authenticate the request using the method specified in the @web_api auth config.

        Auth types (from Design §5.12):
            - api_key:  Authorization header → AuthService.authenticate_api_key()
            - oauth2:   Bearer token → Connected System validates token
            - session:  Cookie-based → AuthService.validate_session()
            - none:     Public endpoint → uses "public_api" service account

        Service account auth resolves to a user with user_type="service_account"
        whose group membership applies normal permission checks.
        """
        auth_config = meta.get("auth", {})
        auth_type = auth_config.get("type", "api_key")

        # Auth not required — use public_api service account
        if meta.get("auth_required") is False or auth_type == "none":
            return self._get_public_context()

        auth_service = self._runtime.auth
        if auth_service is None:
            raise AppOSSessionError("Auth service not initialized")

        # API Key authentication (via Connected System reference)
        if auth_type == "api_key":
            api_key = (
                request.api_key
                or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
                or request.headers.get("x-api-key", "")
            )
            if not api_key:
                raise AppOSSessionError("API key required")

            ctx = auth_service.authenticate_api_key(api_key)
            if ctx is None:
                raise AppOSSecurityError("Invalid API key")
            return ctx

        # Session-based authentication (cookie)
        if auth_type == "session":
            session_id = request.session_id
            if not session_id:
                raise AppOSSessionError("Session required")

            ctx = auth_service.validate_session(session_id)
            if ctx is None:
                raise AppOSSessionError("Invalid or expired session")
            return ctx

        # OAuth2 — validate token via the connected_system referenced in auth config
        if auth_type == "oauth2":
            token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not token:
                raise AppOSSessionError("OAuth2 bearer token required")

            # Resolve the connected system for token validation
            cs_ref = auth_config.get("connected_system")
            if cs_ref:
                ctx = await self._validate_oauth_token(token, cs_ref)
                if ctx is None:
                    raise AppOSSecurityError("Invalid OAuth2 token")
                return ctx

            raise AppOSSecurityError("OAuth2 connected_system not configured")

        raise AppOSSecurityError(f"Unknown auth type: {auth_type}")

    async def _validate_oauth_token(
        self,
        token: str,
        connected_system_ref: str,
    ) -> Optional[ExecutionContext]:
        """
        Validate an OAuth2 token using the referenced Connected System.

        The Connected System defines the token validation endpoint.
        On success, resolves to a service account user → ExecutionContext.
        """
        # Import here to avoid circular import at module level
        from appos.engine.integration_executor import IntegrationExecutor

        # Resolve connected system from registry
        cs_ref = f"connected_systems.{connected_system_ref}"
        cs_obj = self._runtime.registry.resolve(cs_ref)
        if cs_obj is None:
            logger.error(f"Connected system not found for OAuth validation: {connected_system_ref}")
            return None

        # The connected system should define a token introspection endpoint
        # For now, delegate to the integration executor to call the validation endpoint
        # Full implementation depends on Connected System runtime details (Task 2.2-2.5)
        logger.warning(
            f"OAuth2 token validation via connected system '{connected_system_ref}' "
            f"requires Connected System runtime (Phase 2). Falling back to API key check."
        )

        # Fallback: try to match the token as an API key
        if self._runtime.auth:
            return self._runtime.auth.authenticate_api_key(token)
        return None

    def _get_public_context(self) -> ExecutionContext:
        """
        Create an ExecutionContext for unauthenticated (public) API requests.

        Per Design §6 — unauthenticated requests run as the "public_api"
        service account user who belongs to the "public_access" group.
        The engine ALWAYS has a user/group context.
        """
        return ExecutionContext(
            user_id=0,
            username="public_api",
            user_type="service_account",
            user_groups={"public_access"},
            preferred_language="en",
            timezone="UTC",
            full_name="Public API",
        )

    # -----------------------------------------------------------------------
    # Request / Response Mapping
    # -----------------------------------------------------------------------

    def _map_request_inputs(
        self,
        request: APIRequest,
        mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Map HTTP request data to handler inputs using the request_mapping config.

        Mapping syntax (from Design §5.12):
            "customer_id": "path.customer_id"   → from URL path param
            "page":        "query.page"          → from query string
            "order":       "body.order"          → from request body
            "auth_header": "header.authorization" → from request header

        If no mapping provided, passes body as-is for POST/PUT/PATCH,
        or query_params for GET/DELETE.
        """
        if not mapping:
            if request.method in ("POST", "PUT", "PATCH") and request.body:
                return dict(request.body)
            return dict(request.query_params)

        inputs: Dict[str, Any] = {}
        for input_name, source in mapping.items():
            parts = source.split(".", 1)
            source_type = parts[0]
            source_key = parts[1] if len(parts) > 1 else ""

            if source_type == "path":
                inputs[input_name] = request.path_params.get(source_key)
            elif source_type == "query":
                inputs[input_name] = request.query_params.get(source_key)
            elif source_type == "body":
                if request.body and source_key:
                    inputs[input_name] = request.body.get(source_key)
                elif request.body:
                    inputs[input_name] = request.body
            elif source_type == "header":
                inputs[input_name] = request.headers.get(source_key.lower())
            else:
                inputs[input_name] = source  # Literal value

        return inputs

    def _map_response(
        self,
        result: Any,
        mapping: Dict[str, str],
    ) -> Any:
        """
        Map handler output to API response body using response_mapping config.

        Mapping syntax (from Design §5.12):
            "id":   "$.customer_id"     → extract from result dict
            "name": "$.customer_name"

        If no mapping, returns the raw result.
        """
        if not mapping or not isinstance(result, dict):
            return result

        response: Dict[str, Any] = {}
        for output_key, source_path in mapping.items():
            if source_path.startswith("$."):
                field_name = source_path[2:]
                response[output_key] = result.get(field_name)
            else:
                response[output_key] = source_path  # Literal

        return response

    # -----------------------------------------------------------------------
    # Async Mode
    # -----------------------------------------------------------------------

    async def _execute_async(
        self,
        handler_ref: str,
        inputs: Dict[str, Any],
        app_name: str,
        api_name: str,
        meta: Dict[str, Any],
    ) -> APIResponse:
        """
        Execute in async mode — dispatch to process and return poll URL.

        Per Design §5.12: When async=True, returns:
            {"instance_id": "proc_xxx", "status": "pending",
             "poll_url": "/api/{app}/{version}/processes/{instance_id}/status"}
        """
        instance_id = f"proc_{uuid.uuid4().hex[:12]}"
        version = meta.get("version", "v1")

        # Queue the process for async execution
        # Full implementation relies on Celery integration (Task 3.10)
        try:
            self._runtime.dispatch(handler_ref, inputs=inputs, async_exec=True)
        except Exception as e:
            logger.error(f"Failed to queue async handler {handler_ref}: {e}")
            return APIResponse(status_code=500, body={"error": "Failed to queue task"})

        poll_url = f"/api/{app_name}/{version}/processes/{instance_id}/status"

        return APIResponse(
            status_code=202,
            body=AsyncAPIResponse(
                instance_id=instance_id,
                status="pending",
                poll_url=poll_url,
            ).model_dump(),
        )

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def _log_api_execution(
        self,
        api_def: RegisteredObject,
        request: APIRequest,
        status_code: int,
        duration_ms: float,
        meta: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """
        Log API execution to web_apis/execution/ log folder.

        Per Design §5.12 — logs method, path, status_code, handler, duration.
        Body NOT logged by default; only if log_payload=True on decorator.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "log_type": "web_api_execution",
            "object_type": "web_apis",
            "object_ref": api_def.object_ref,
            "method": request.method,
            "path": request.path,
            "status_code": status_code,
            "handler": meta.get("handler", ""),
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client_ip,
            "app": api_def.app_name,
            "api_name": meta.get("name", api_def.name),
        }

        if error:
            entry["error"] = error

        # Payload logging opt-in (Design §5.12)
        if meta.get("log_payload", False):
            entry["request_body"] = request.body
            # Response body added by caller if needed

        if self._runtime.log_queue:
            from appos.engine.logging import LogEntry
            log_entry = LogEntry(
                object_type=entry.get("object_type", "web_apis"),
                category="execution",
                data=entry,
            )
            self._runtime.log_queue.push(log_entry)


# ---------------------------------------------------------------------------
# Starlette/FastAPI request adapter
# ---------------------------------------------------------------------------

async def starlette_to_api_request(request) -> APIRequest:
    """
    Convert a Starlette/FastAPI Request object to our normalized APIRequest.

    Used by reflex_bridge.py when wiring routes to Reflex's internal FastAPI.
    """
    # Extract body for POST/PUT/PATCH
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = None

    # Extract session cookie
    session_id = request.cookies.get("appos_session")

    # Extract API key from multiple possible locations
    api_key = (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        or None
    )

    return APIRequest(
        method=request.method,
        path=request.url.path,
        path_params=dict(request.path_params) if hasattr(request, "path_params") else {},
        query_params=dict(request.query_params),
        headers={k: v for k, v in request.headers.items()},
        body=body,
        client_ip=request.client.host if request.client else None,
        session_id=session_id,
        api_key=api_key,
    )
