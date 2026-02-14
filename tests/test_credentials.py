"""Unit tests for appos.engine.credentials — CredentialManager."""

import os
import pytest
from unittest.mock import MagicMock, patch

from appos.engine.credentials import CredentialManager


class TestCredentialManager:
    """Test encryption/decryption without real DB."""

    def setup_method(self):
        # Use a test secret key
        self.secret_key = "test-secret-key-for-unit-tests-only"
        self.mock_session = MagicMock()
        self.factory = MagicMock(return_value=self.mock_session)
        self.factory.__enter__ = MagicMock(return_value=self.mock_session)
        self.factory.__exit__ = MagicMock(return_value=False)
        self.mgr = CredentialManager(
            db_session_factory=self.factory,
            secret_key=self.secret_key,
        )

    def test_encrypt_decrypt_roundtrip(self):
        """Credentials should round-trip through encrypt/decrypt."""
        creds = {"username": "admin", "password": "secret123"}
        encrypted = self.mgr.encrypt(creds)
        assert isinstance(encrypted, bytes)
        decrypted = self.mgr.decrypt(encrypted)
        assert decrypted == creds

    def test_encrypt_produces_bytes(self):
        encrypted = self.mgr.encrypt({"key": "value"})
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

    def test_decrypt_wrong_key_fails(self):
        """Decrypting with wrong key should fail."""
        creds = {"username": "admin"}
        encrypted = self.mgr.encrypt(creds)

        other_mgr = CredentialManager(
            db_session_factory=self.factory,
            secret_key="completely-different-secret-key!!!",
        )
        with pytest.raises(Exception):
            other_mgr.decrypt(encrypted)

    def test_get_auth_headers_basic(self):
        """Test basic auth header generation."""
        auth_config = {
            "type": "basic",
            "username": "user",
            "password": "pass",
        }
        headers = self.mgr.get_auth_headers("test_system", auth_config)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_get_auth_headers_api_key(self):
        """Test API key header generation."""
        auth_config = {
            "type": "api_key",
            "header": "X-Api-Key",
            "key": "my-secret-key",
        }
        headers = self.mgr.get_auth_headers("test_system", auth_config)
        assert headers["X-Api-Key"] == "my-secret-key"

    def test_get_auth_headers_bearer(self):
        """Test OAuth2 bearer token header."""
        auth_config = {
            "type": "oauth2",
            "access_token": "tok_123",
        }
        headers = self.mgr.get_auth_headers("test_system", auth_config)
        assert headers["Authorization"] == "Bearer tok_123"
