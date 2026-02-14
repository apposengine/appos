"""
AppOS Credential Manager — Encrypted credential storage and retrieval
for Connected System secrets using Fernet symmetric encryption.

Provides:
    - CredentialManager: Encrypt/decrypt credential blobs for connected_systems
    - Key derivation from platform secret (appos.yaml or env var)
    - Integration with ConnectedSystem.credentials_encrypted column (BYTEA)

Security model:
    - Credentials encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256)
    - Encryption key derived from APPOS_SECRET_KEY env var or appos.yaml
    - Admin Console manages credentials — NOT stored in code
    - Decrypted only at runtime, in-memory, for the duration of the call

Design refs: AppOS_Design.md §5.5, §9 (Encryption), AppOS_Database_Design.md §2.7
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("appos.engine.credentials")

# Default secret key source (override via APPOS_SECRET_KEY env var)
_DEFAULT_SECRET_KEY = "appos-dev-key-change-in-production"


class CredentialManager:
    """
    Encrypts and decrypts credential JSON blobs for Connected Systems.

    Credentials are stored as Fernet-encrypted BYTEA in the connected_systems
    table (credentials_encrypted column). This manager handles the full lifecycle:

    1. Admin Console → set_credentials(cs_name, {"username": "...", "password": "..."})
       → encrypt → store in DB
    2. IntegrationExecutor → get_credentials(cs_name)
       → read from DB → decrypt → return dict

    Usage:
        manager = CredentialManager(db_session_factory=get_session)
        manager.set_credentials("stripe_api", {"api_key": "sk_live_..."})
        creds = manager.get_credentials("stripe_api")
        # → {"api_key": "sk_live_..."}
    """

    def __init__(
        self,
        db_session_factory=None,
        secret_key: Optional[str] = None,
    ):
        self._db_session_factory = db_session_factory
        self._fernet = self._build_fernet(secret_key)

    @staticmethod
    def _build_fernet(secret_key: Optional[str] = None) -> Fernet:
        """
        Build a Fernet instance from a secret key.

        Uses APPOS_SECRET_KEY env var if available, otherwise falls back to
        the provided secret_key or the default dev key.
        """
        key_source = (
            os.environ.get("APPOS_SECRET_KEY")
            or secret_key
            or _DEFAULT_SECRET_KEY
        )

        # Derive a 32-byte key from the source using SHA-256,
        # then base64-encode for Fernet (which requires URL-safe b64 key)
        derived = hashlib.sha256(key_source.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(derived)

        return Fernet(fernet_key)

    # -----------------------------------------------------------------------
    # Encrypt / Decrypt
    # -----------------------------------------------------------------------

    def encrypt(self, credentials: Dict[str, Any]) -> bytes:
        """
        Encrypt a credentials dict to bytes (for DB storage).

        Args:
            credentials: Plain credentials dict, e.g.,
                {"username": "admin", "password": "secret", "api_key": "..."}

        Returns:
            Encrypted bytes (Fernet token).
        """
        payload = json.dumps(credentials, sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(payload)

    def decrypt(self, encrypted: bytes) -> Dict[str, Any]:
        """
        Decrypt bytes back to a credentials dict.

        Args:
            encrypted: Fernet-encrypted bytes from DB.

        Returns:
            Decrypted credentials dict.

        Raises:
            AppOSSecurityError: If decryption fails (wrong key, corrupted data).
        """
        try:
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            from appos.engine.errors import AppOSSecurityError
            raise AppOSSecurityError(
                "Failed to decrypt credentials — encryption key may have changed",
                object_ref="platform.credentials",
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            from appos.engine.errors import AppOSSecurityError
            raise AppOSSecurityError(
                f"Corrupted credential data: {e}",
                object_ref="platform.credentials",
            )

    # -----------------------------------------------------------------------
    # DB operations
    # -----------------------------------------------------------------------

    def set_credentials(
        self,
        connected_system_name: str,
        credentials: Dict[str, Any],
    ) -> None:
        """
        Encrypt and store credentials for a Connected System.

        Args:
            connected_system_name: The CS name (e.g., "stripe_api").
            credentials: Plain credentials dict.

        Raises:
            KeyError: If Connected System not found.
        """
        if not self._db_session_factory:
            raise RuntimeError("No DB session factory — cannot store credentials")

        from appos.db.platform_models import ConnectedSystem

        encrypted = self.encrypt(credentials)

        session = self._db_session_factory()
        try:
            cs = (
                session.query(ConnectedSystem)
                .filter(ConnectedSystem.name == connected_system_name)
                .first()
            )
            if not cs:
                raise KeyError(f"Connected System '{connected_system_name}' not found in DB")

            cs.credentials_encrypted = encrypted
            session.commit()
            logger.info(f"Stored encrypted credentials for: {connected_system_name}")
        except KeyError:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store credentials for {connected_system_name}: {e}")
            raise
        finally:
            session.close()

    def get_credentials(
        self,
        connected_system_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and decrypt credentials for a Connected System.

        Args:
            connected_system_name: The CS name (e.g., "stripe_api").

        Returns:
            Decrypted credentials dict, or None if no credentials stored.

        Raises:
            AppOSSecurityError: If decryption fails.
        """
        if not self._db_session_factory:
            logger.warning("No DB session factory — cannot retrieve credentials")
            return None

        from appos.db.platform_models import ConnectedSystem

        session = self._db_session_factory()
        try:
            cs = (
                session.query(ConnectedSystem)
                .filter(ConnectedSystem.name == connected_system_name)
                .first()
            )
            if not cs:
                logger.warning(f"Connected System '{connected_system_name}' not found")
                return None

            if not cs.credentials_encrypted:
                return None

            return self.decrypt(cs.credentials_encrypted)
        except Exception as e:
            logger.error(f"Failed to retrieve credentials for {connected_system_name}: {e}")
            raise
        finally:
            session.close()

    def delete_credentials(self, connected_system_name: str) -> None:
        """Remove stored credentials for a Connected System."""
        if not self._db_session_factory:
            raise RuntimeError("No DB session factory")

        from appos.db.platform_models import ConnectedSystem

        session = self._db_session_factory()
        try:
            cs = (
                session.query(ConnectedSystem)
                .filter(ConnectedSystem.name == connected_system_name)
                .first()
            )
            if cs:
                cs.credentials_encrypted = None
                session.commit()
                logger.info(f"Deleted credentials for: {connected_system_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete credentials: {e}")
            raise
        finally:
            session.close()

    def has_credentials(self, connected_system_name: str) -> bool:
        """Check if a Connected System has stored credentials (without decrypting)."""
        if not self._db_session_factory:
            return False

        from appos.db.platform_models import ConnectedSystem

        session = self._db_session_factory()
        try:
            cs = (
                session.query(ConnectedSystem)
                .filter(ConnectedSystem.name == connected_system_name)
                .first()
            )
            return cs is not None and cs.credentials_encrypted is not None
        finally:
            session.close()

    def rotate_key(self, new_secret_key: str) -> int:
        """
        Re-encrypt all credentials with a new key.

        Steps:
            1. Decrypt all credentials with current key
            2. Create new Fernet with new key
            3. Re-encrypt all credentials
            4. Store back in DB

        Args:
            new_secret_key: The new secret key to use.

        Returns:
            Number of credentials rotated.
        """
        if not self._db_session_factory:
            raise RuntimeError("No DB session factory")

        from appos.db.platform_models import ConnectedSystem

        new_fernet = self._build_fernet(new_secret_key)

        session = self._db_session_factory()
        try:
            systems = (
                session.query(ConnectedSystem)
                .filter(ConnectedSystem.credentials_encrypted.isnot(None))
                .all()
            )

            count = 0
            for cs in systems:
                # Decrypt with old key
                old_creds = self.decrypt(cs.credentials_encrypted)
                # Encrypt with new key
                payload = json.dumps(old_creds, sort_keys=True).encode("utf-8")
                cs.credentials_encrypted = new_fernet.encrypt(payload)
                count += 1

            session.commit()

            # Switch to new fernet
            self._fernet = new_fernet
            logger.info(f"Rotated encryption key for {count} Connected Systems")

            return count
        except Exception as e:
            session.rollback()
            logger.error(f"Key rotation failed: {e}")
            raise
        finally:
            session.close()

    def get_auth_headers(
        self,
        connected_system_name: str,
        auth_config: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        Build HTTP auth headers from stored credentials + auth config.

        Supports: basic, api_key, oauth2 (client_credentials).

        Args:
            connected_system_name: CS name for credential lookup.
            auth_config: Auth section from Connected System config.

        Returns:
            Dict of HTTP headers to add to outbound requests.
        """
        auth_type = auth_config.get("type", "none")
        if auth_type == "none":
            return {}

        creds = self.get_credentials(connected_system_name)
        if not creds:
            logger.warning(f"No credentials for {connected_system_name} (auth_type={auth_type})")
            return {}

        if auth_type == "basic":
            import base64 as b64
            username = creds.get("username", "")
            password = creds.get("password", "")
            token = b64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {token}"}

        elif auth_type == "api_key":
            header = auth_config.get("header", "Authorization")
            prefix = auth_config.get("prefix", "Bearer")
            key = creds.get("api_key", "")
            return {header: f"{prefix} {key}" if prefix else key}

        elif auth_type == "oauth2":
            # For OAuth2 client_credentials flow, return token if cached
            # Full OAuth2 token refresh requires a separate flow
            token = creds.get("access_token", "")
            if token:
                return {"Authorization": f"Bearer {token}"}
            logger.warning(f"No access_token in credentials for {connected_system_name}")
            return {}

        elif auth_type == "certificate":
            # Certificate auth is handled at the transport layer, not headers
            return {}

        logger.warning(f"Unknown auth_type '{auth_type}' for {connected_system_name}")
        return {}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_credential_manager: Optional[CredentialManager] = None


def get_credential_manager(
    db_session_factory=None,
    secret_key: Optional[str] = None,
) -> CredentialManager:
    """Get or create the global CredentialManager singleton."""
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = CredentialManager(
            db_session_factory=db_session_factory,
            secret_key=secret_key,
        )
    return _credential_manager
