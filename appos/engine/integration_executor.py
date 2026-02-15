"""
AppOS Integration Executor — Outbound HTTP call pipeline for @integration objects.

Pipeline (per call):
    1. Resolve Connected System → get base_url, auth, env overrides
    2. Build HTTP request from integration config (method, path, headers, body)
    3. Template substitution for dynamic values
    4. Execute via httpx.AsyncClient (connection pooled per connected system)
    5. Retry with exponential backoff on transient failures
    6. Circuit breaker per Connected System
    7. Map response using response_mapping
    8. Log execution (body only if log_payload=True)

Uses httpx for async HTTP — connection pooled, timeout-aware, retry-capable.
Does NOT use requests library — httpx is the standard for async Python HTTP.

Design refs:
    §5.5  Connected System — Connection details, auth, env overrides
    §5.11 Integration      — Outbound API call definition, retry, response mapping
    §8    Runtime Engine   — engine.dispatch() calls _execute_integration()
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from appos.engine.cache import RedisCache
from appos.engine.context import get_execution_context
from appos.engine.errors import AppOSDispatchError, AppOSError
from appos.engine.registry import ObjectRegistryManager, RegisteredObject

logger = logging.getLogger("appos.engine.integration_executor")


# ---------------------------------------------------------------------------
# Connected System Resolver
# ---------------------------------------------------------------------------

class ConnectedSystemResolver:
    """
    Resolves a Connected System reference to runtime connection details.

    Steps:
        1. Look up @connected_system in ObjectRegistryManager
        2. Call its handler() to get connection config dict
        3. Apply environment overrides (dev → staging → prod)
        4. Resolve credentials from admin-managed encrypted store (DB)
        5. Return merged config with base_url, auth headers, timeout, etc.

    Depends on:
        - ObjectRegistryManager for @connected_system lookups
        - Environment resolver (Task 2.4) for env-specific overrides
        - Credential store (Task 2.3) for encrypted secrets
    """

    def __init__(
        self,
        registry: ObjectRegistryManager,
        db_session_factory=None,
        environment: str = "default",
        credential_manager=None,
        environment_resolver=None,
    ):
        self._registry = registry
        self._db_session_factory = db_session_factory
        self._environment = environment
        self._credential_manager = credential_manager
        self._environment_resolver = environment_resolver

        # Cache resolved configs in memory (per process lifetime)
        self._resolved_cache: Dict[str, Dict[str, Any]] = {}

    def resolve(self, connected_system_name: str) -> Dict[str, Any]:
        """
        Resolve a Connected System name to its runtime config.

        Returns dict with:
            - base_url: str
            - timeout: int
            - auth_type: str (none/basic/api_key/oauth2/certificate)
            - auth_headers: Dict[str, str] — ready-to-use HTTP headers
            - extra_headers: Dict[str, str]
            - pool_config: Dict — connection pool settings

        Raises:
            AppOSDispatchError if connected system not found.
        """
        if connected_system_name in self._resolved_cache:
            return self._resolved_cache[connected_system_name]

        # Look up in registry — connected systems are global (not per-app)
        cs_ref = f"connected_systems.{connected_system_name}"
        cs_obj = self._registry.resolve(cs_ref)

        if cs_obj is None:
            # Try without prefix for backward compat
            for ref, obj in self._registry._objects.items():
                if obj.object_type == "connected_system" and obj.name == connected_system_name:
                    cs_obj = obj
                    break

        if cs_obj is None:
            raise AppOSDispatchError(
                f"Connected System not found: {connected_system_name}",
                object_ref=cs_ref,
            )

        # Call handler to get the config dict
        raw_config = cs_obj.handler() if callable(cs_obj.handler) else {}

        # Merge environment overrides
        config = self._apply_environment(raw_config)

        # Resolve auth headers from credentials
        auth_headers = self._resolve_auth(config, connected_system_name)

        resolved = {
            "name": connected_system_name,
            "base_url": config.get("base_url", ""),
            "timeout": config.get("timeout", 30),
            "auth_type": config.get("auth", {}).get("type", "none"),
            "auth_headers": auth_headers,
            "extra_headers": config.get("headers", {}),
            "pool_config": {
                "max_connections": config.get("pool_size", 10),
                "max_keepalive": config.get("max_overflow", 20),
            },
            "is_sensitive": config.get("is_sensitive", False),
        }

        self._resolved_cache[connected_system_name] = resolved
        return resolved

    def _apply_environment(self, raw_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment-specific overrides to connection config.

        Uses EnvironmentResolver when available (preferred), otherwise
        falls back to manual dict merge per Design §5.5.
        """
        if self._environment_resolver:
            try:
                return self._environment_resolver.resolve_config(raw_config)
            except Exception as e:
                logger.warning(f"EnvironmentResolver failed, falling back to manual merge: {e}")

        base = dict(raw_config.get("default", raw_config))
        env = self._environment

        overrides = raw_config.get("environment_overrides", {})
        if env in overrides:
            base.update(overrides[env])

        # Keep auth section from raw config
        base["auth"] = raw_config.get("auth", {})

        return base

    def _resolve_auth(
        self,
        config: Dict[str, Any],
        cs_name: str,
    ) -> Dict[str, str]:
        """
        Resolve auth config to ready-to-use HTTP headers.

        Per Design §5.5:
            - api_key: Authorization: Bearer {key}  (key from DB, not code)
            - basic:   Authorization: Basic {b64}
            - oauth2:  Authorization: Bearer {token} (token from token endpoint)
            - none:    {} (no auth headers)

        Credentials are stored encrypted in DB, managed via Admin Console.
        Full credential decryption depends on Task 2.3 (Credential encryption).
        For now, returns placeholder headers that the admin console will populate.
        """
        auth = config.get("auth", {})
        auth_type = auth.get("type", "none")

        if auth_type == "none":
            return {}

        if auth_type == "api_key":
            header_name = auth.get("header", "Authorization")
            prefix = auth.get("prefix", "Bearer")
            # Credential lookup from DB (encrypted)
            api_key = self._get_credential(cs_name, "api_key")
            if api_key:
                return {header_name: f"{prefix} {api_key}"}
            logger.warning(f"No API key found for connected system: {cs_name}")
            return {}

        if auth_type == "basic":
            username = self._get_credential(cs_name, "username")
            password = self._get_credential(cs_name, "password")
            if username and password:
                import base64
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                return {"Authorization": f"Basic {encoded}"}
            logger.warning(f"No basic auth credentials for connected system: {cs_name}")
            return {}

        if auth_type == "oauth2":
            # OAuth2 client credentials flow would go here
            # For now, log and return empty — depends on Task 2.3, 2.4
            logger.warning(
                f"OAuth2 auth for '{cs_name}' requires full credential store (Task 2.3). "
                f"Returning empty auth headers."
            )
            return {}

        return {}

    def _get_credential(self, cs_name: str, credential_key: str) -> Optional[str]:
        """
        Retrieve an encrypted credential from the platform DB.

        Uses CredentialManager when available (preferred) for Fernet-encrypted
        credential retrieval. Falls back to direct DB lookup.
        """
        # Preferred: Use CredentialManager for encrypted credential access
        if self._credential_manager:
            try:
                creds = self._credential_manager.get_credentials(cs_name)
                if creds and credential_key in creds:
                    return creds[credential_key]
            except Exception as e:
                logger.error(f"CredentialManager failed for '{cs_name}': {e}")
                return None

        # Fallback: Direct DB lookup
        if self._db_session_factory is None:
            return None

        try:
            session = self._db_session_factory()
            try:
                return None  # No raw DB path without CredentialManager
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to retrieve credential '{credential_key}' for '{cs_name}': {e}")
            return None

    def invalidate(self, connected_system_name: Optional[str] = None) -> None:
        """Invalidate cached resolved config(s)."""
        if connected_system_name:
            self._resolved_cache.pop(connected_system_name, None)
        else:
            self._resolved_cache.clear()


# ---------------------------------------------------------------------------
# Circuit Breaker (per Connected System)
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Per-connected-system circuit breaker.

    States:
        CLOSED  → requests flow normally
        OPEN    → requests fail fast (no outbound call)
        HALF    → single probe request allowed; success → CLOSED, fail → OPEN

    Thresholds configurable per connected system via health_check config.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = self.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        if current == self.CLOSED:
            return True
        if current == self.HALF_OPEN:
            return True  # Allow single probe
        return False  # OPEN — fail fast

    def record_success(self) -> None:
        """Record a successful call — resets circuit."""
        self._failure_count = 0
        self._state = self.CLOSED

    def record_failure(self) -> None:
        """Record a failed call — may trip circuit."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = self.OPEN
            logger.warning(
                f"Circuit breaker OPEN for '{self.name}': "
                f"{self._failure_count} consecutive failures"
            )


# ---------------------------------------------------------------------------
# Integration Executor — Outbound pipeline
# ---------------------------------------------------------------------------

class IntegrationExecutor:
    """
    Executes outbound HTTP calls for @integration objects.

    Lifecycle (per call):
        1. Resolve Connected System → base URL, auth, timeout
        2. Build HTTP request from integration config + input params
        3. Check circuit breaker
        4. Execute via httpx with retry + exponential backoff
        5. Map response via response_mapping
        6. Log execution to integrations/ log folder

    Uses httpx.AsyncClient with connection pooling per Connected System.
    Connected System credentials come from admin-managed encrypted DB store.
    """

    # Safety cap — Connected Systems are developer-defined and few in number.
    # This prevents accidental growth (e.g., a bug generating dynamic CS names).
    MAX_CLIENTS: int = 50

    def __init__(
        self,
        registry: ObjectRegistryManager,
        cs_resolver: Optional[ConnectedSystemResolver] = None,
        db_session_factory=None,
        log_queue=None,
        environment: str = "default",
        credential_manager=None,
        environment_resolver=None,
    ):
        self._registry = registry
        self._cs_resolver = cs_resolver or ConnectedSystemResolver(
            registry=registry,
            db_session_factory=db_session_factory,
            environment=environment,
            credential_manager=credential_manager,
            environment_resolver=environment_resolver,
        )
        self._db_session_factory = db_session_factory
        self._log_queue = log_queue

        # httpx clients per Connected System (connection pooled)
        self._clients: Dict[str, Any] = {}

        # Circuit breakers per Connected System
        self._breakers: Dict[str, CircuitBreaker] = {}

    async def execute(
        self,
        integration_def: RegisteredObject,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute an outbound integration call.

        Args:
            integration_def: The registered @integration object.
            inputs: Key-value pairs for template substitution.

        Returns:
            Mapped response dict per response_mapping config.

        Raises:
            AppOSDispatchError on connected system not found or circuit open.
        """
        meta = integration_def.metadata
        cs_name = meta.get("connected_system")
        int_name = meta.get("name", integration_def.name)
        start_time = time.monotonic()

        if not cs_name:
            raise AppOSDispatchError(
                f"Integration '{int_name}' has no connected_system configured",
                object_ref=integration_def.object_ref,
            )

        # ── Step 1: Resolve Connected System ──
        cs_config = self._cs_resolver.resolve(cs_name)

        # ── Step 2: Get integration config ──
        int_config = integration_def.handler() if callable(integration_def.handler) else {}
        method = int_config.get("method", "GET").upper()
        path = int_config.get("path", "")
        headers = dict(int_config.get("headers", {}))
        body_template = int_config.get("body", {})
        response_mapping = int_config.get("response_mapping", {})
        error_handling = int_config.get("error_handling", {})
        retry_config = int_config.get("retry", {"count": 3, "delay": 1, "backoff": "exponential"})

        # ── Step 3: Template substitution ──
        url = f"{cs_config['base_url']}{self._substitute(path, inputs)}"
        headers = {k: self._substitute(v, inputs) for k, v in headers.items()}
        body = self._substitute_dict(body_template, inputs) if body_template else None

        # Merge auth headers from Connected System
        headers.update(cs_config.get("auth_headers", {}))
        headers.update(cs_config.get("extra_headers", {}))

        # ── Step 4: Circuit breaker check ──
        breaker = self._get_breaker(cs_name)
        if not breaker.allow_request():
            duration_ms = (time.monotonic() - start_time) * 1000
            self._log_integration(integration_def, method, url, 503, duration_ms, meta, error="Circuit open")
            raise AppOSDispatchError(
                f"Circuit breaker OPEN for '{cs_name}' — too many recent failures",
                object_ref=integration_def.object_ref,
            )

        # ── Step 5: Execute with retry ──
        timeout = cs_config.get("timeout", 30)
        max_retries = retry_config.get("count", 3)
        base_delay = retry_config.get("delay", 1)
        backoff_type = retry_config.get("backoff", "exponential")

        last_error: Optional[Exception] = None
        last_status: int = 0

        for attempt in range(max_retries + 1):
            try:
                status_code, response_body = await self._http_call(
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                    cs_name=cs_name,
                )
                last_status = status_code

                # ── Step 6: Handle errors by status code ──
                if 200 <= status_code < 300:
                    breaker.record_success()
                    duration_ms = (time.monotonic() - start_time) * 1000
                    self._log_integration(integration_def, method, url, status_code, duration_ms, meta)

                    # ── Step 7: Map response ──
                    return self._map_response(response_body, response_mapping)

                # Check error handling config for this status code
                action = self._resolve_error_action(status_code, error_handling)

                if action == "retry" and attempt < max_retries:
                    delay = self._calc_delay(attempt, base_delay, backoff_type)
                    logger.info(
                        f"Integration '{int_name}' got {status_code}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error
                breaker.record_failure()
                duration_ms = (time.monotonic() - start_time) * 1000
                self._log_integration(
                    integration_def, method, url, status_code, duration_ms, meta,
                    error=f"HTTP {status_code}"
                )
                raise AppOSDispatchError(
                    f"Integration '{int_name}' failed with HTTP {status_code}",
                    object_ref=integration_def.object_ref,
                    details={"status_code": status_code, "action": action},
                )

            except AppOSError:
                raise
            except Exception as e:
                last_error = e
                breaker.record_failure()

                if attempt < max_retries:
                    delay = self._calc_delay(attempt, base_delay, backoff_type)
                    logger.warning(
                        f"Integration '{int_name}' error: {e}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                    continue

        # All retries exhausted
        duration_ms = (time.monotonic() - start_time) * 1000
        self._log_integration(
            integration_def, "?", url, last_status, duration_ms, meta,
            error=str(last_error)
        )
        raise AppOSDispatchError(
            f"Integration '{int_name}' failed after {max_retries + 1} attempts: {last_error}",
            object_ref=integration_def.object_ref,
        )

    # -----------------------------------------------------------------------
    # HTTP Client (httpx)
    # -----------------------------------------------------------------------

    async def _http_call(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[Dict[str, Any]],
        timeout: int,
        cs_name: str,
    ) -> Tuple[int, Any]:
        """
        Execute the actual HTTP call via httpx.

        Connection pooled per Connected System for efficiency.
        """
        import httpx

        client = self._get_or_create_client(cs_name, timeout)

        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
            timeout=timeout,
        )

        # Parse response body
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        return response.status_code, response_body

    def _get_or_create_client(self, cs_name: str, timeout: int) -> Any:
        """
        Get or create an httpx.AsyncClient for a Connected System.

        Connection pooled — one client per Connected System, reused across calls.
        Client lifecycle managed by the IntegrationExecutor (closed on shutdown).
        A safety cap (MAX_CLIENTS) prevents accidental unbounded growth.
        """
        if cs_name not in self._clients:
            # Safety cap — Connected Systems are dev-defined and few.
            # If we hit this, something is generating dynamic CS names.
            if len(self._clients) >= self.MAX_CLIENTS:
                raise AppOSDispatchError(
                    f"httpx client pool at capacity ({self.MAX_CLIENTS}). "
                    f"Cannot create client for '{cs_name}'. "
                    f"Active clients: {sorted(self._clients.keys())}",
                    object_ref=f"connected_systems.{cs_name}",
                )

            import httpx

            # Pool limits from Connected System config
            cs_config = self._cs_resolver.resolve(cs_name)
            pool_config = cs_config.get("pool_config", {})

            limits = httpx.Limits(
                max_connections=pool_config.get("max_connections", 10),
                max_keepalive_connections=pool_config.get("max_keepalive", 5),
            )

            self._clients[cs_name] = httpx.AsyncClient(
                limits=limits,
                timeout=httpx.Timeout(timeout, connect=10.0),
                follow_redirects=True,
            )
            logger.info(
                f"Created httpx client for '{cs_name}' "
                f"(pool: {len(self._clients)}/{self.MAX_CLIENTS})"
            )

        return self._clients[cs_name]

    async def close_client(self, cs_name: str) -> bool:
        """
        Close and remove the httpx client for a specific Connected System.

        Useful when credentials are rotated via admin console — the next
        call to that CS will create a fresh client with new auth headers.

        Returns:
            True if a client was found and closed, False otherwise.
        """
        client = self._clients.pop(cs_name, None)
        if client is None:
            return False
        try:
            await client.aclose()
            logger.info(f"Closed httpx client for '{cs_name}'")
        except Exception as e:
            logger.warning(f"Error closing httpx client for '{cs_name}': {e}")
        # Also invalidate the CS resolver cache so next call re-resolves
        self._cs_resolver.invalidate(cs_name)
        return True

    async def close_all_clients(self) -> None:
        """Close all httpx clients. Called during runtime shutdown."""
        for name, client in self._clients.items():
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing httpx client for '{name}': {e}")
        count = len(self._clients)
        self._clients.clear()
        logger.info(f"Closed {count} httpx client(s)")

    def client_stats(self) -> Dict[str, Any]:
        """Return pool stats for health checks and admin dashboard."""
        return {
            "active_clients": len(self._clients),
            "max_clients": self.MAX_CLIENTS,
            "connected_systems": sorted(self._clients.keys()),
        }

    # -----------------------------------------------------------------------
    # Template Substitution
    # -----------------------------------------------------------------------

    def _substitute(self, template: str, values: Dict[str, Any]) -> str:
        """
        Replace {placeholder} tokens in a string with values from inputs.

        Per Design §5.11 — body and path templates use {key} syntax.
        Example: "/charges/{customer_id}" + {"customer_id": "cus_123"} → "/charges/cus_123"
        """
        if not isinstance(template, str):
            return str(template)

        def replacer(match):
            key = match.group(1)
            return str(values.get(key, match.group(0)))

        return re.sub(r"\{(\w+)\}", replacer, template)

    def _substitute_dict(self, template: Dict, values: Dict[str, Any]) -> Dict:
        """Recursively substitute {placeholders} in a dict template."""
        result = {}
        for k, v in template.items():
            if isinstance(v, str):
                result[k] = self._substitute(v, values)
            elif isinstance(v, dict):
                result[k] = self._substitute_dict(v, values)
            elif isinstance(v, list):
                result[k] = [
                    self._substitute(item, values) if isinstance(item, str) else item
                    for item in v
                ]
            else:
                result[k] = v
        return result

    # -----------------------------------------------------------------------
    # Error Handling
    # -----------------------------------------------------------------------

    def _resolve_error_action(
        self,
        status_code: int,
        error_handling: Dict[str, str],
    ) -> str:
        """
        Resolve the action for a given HTTP status code.

        Per Design §5.11 error_handling config:
            "402": "payment_failed"
            "429": "retry"
            "5xx": "retry"

        Supports exact codes ("402") and range patterns ("5xx", "4xx").
        """
        # Check exact match first
        code_str = str(status_code)
        if code_str in error_handling:
            return error_handling[code_str]

        # Check range patterns
        range_key = f"{code_str[0]}xx"
        if range_key in error_handling:
            return error_handling[range_key]

        # Default: retry for 5xx, fail for others
        if status_code >= 500:
            return "retry"
        return "fail"

    @staticmethod
    def _calc_delay(attempt: int, base_delay: float, backoff_type: str) -> float:
        """Calculate retry delay with backoff."""
        if backoff_type == "exponential":
            return base_delay * (2 ** attempt)
        elif backoff_type == "linear":
            return base_delay * (attempt + 1)
        return base_delay  # fixed

    # -----------------------------------------------------------------------
    # Circuit Breaker Management
    # -----------------------------------------------------------------------

    def _get_breaker(self, cs_name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a Connected System."""
        if cs_name not in self._breakers:
            self._breakers[cs_name] = CircuitBreaker(name=cs_name)
        return self._breakers[cs_name]

    # -----------------------------------------------------------------------
    # Response Mapping
    # -----------------------------------------------------------------------

    def _map_response(
        self,
        response_body: Any,
        mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Map HTTP response to structured output using response_mapping.

        Per Design §5.11:
            "charge_id": "$.id"        → response_body["id"]
            "status":    "$.status"    → response_body["status"]

        Supports nested access via dot notation: "$.data.customer.id"
        """
        if not mapping:
            return response_body if isinstance(response_body, dict) else {"result": response_body}

        result = {}
        for output_key, source_path in mapping.items():
            if source_path.startswith("$."):
                value = self._extract_path(response_body, source_path[2:])
                result[output_key] = value
            else:
                result[output_key] = source_path  # Literal value

        return result

    @staticmethod
    def _extract_path(data: Any, path: str) -> Any:
        """Extract a value from nested data using dot-notation path."""
        if not isinstance(data, dict):
            return None

        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def _log_integration(
        self,
        integration_def: RegisteredObject,
        method: str,
        url: str,
        status_code: int,
        duration_ms: float,
        meta: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """
        Log integration execution to integrations/execution/ log folder.

        Per Design §5.11 — logs method, target_url, status_code, duration.
        Body NOT logged by default; only if log_payload=True on decorator.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "log_type": "integration_execution",
            "object_type": "integrations",
            "object_ref": integration_def.object_ref,
            "connected_system": meta.get("connected_system", ""),
            "method": method,
            "target_url": url,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "app": integration_def.app_name,
            "integration_name": meta.get("name", integration_def.name),
        }

        if error:
            entry["error"] = error

        if self._log_queue:
            from appos.engine.logging import LogEntry
            log_entry = LogEntry(
                object_type=entry.get("object_type", "integrations"),
                category="execution",
                data=entry,
            )
            self._log_queue.push(log_entry)
