"""Unit tests for appos.engine.errors — Error hierarchy & serialization."""

import json
import pytest

from appos.engine.errors import (
    AppOSError,
    AppOSConfigError,
    AppOSDispatchError,
    AppOSIntegrationError,
    AppOSObjectNotFoundError,
    AppOSRecordError,
    AppOSSecurityError,
    AppOSSessionError,
    AppOSTimeoutError,
    AppOSValidationError,
)


class TestAppOSError:
    """Base error class tests."""

    def test_basic_creation(self):
        err = AppOSError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"
        assert err.error_type == "AppOSError"
        assert err.execution_id is None
        assert err.object_ref is None

    def test_context_fields(self):
        err = AppOSError(
            "fail",
            execution_id="exec_abc",
            object_ref="crm.rules.calc",
            object_type="expression_rule",
            process_instance_id="pi_123",
            step_name="step1",
        )
        assert err.execution_id == "exec_abc"
        assert err.object_ref == "crm.rules.calc"
        assert err.object_type == "expression_rule"
        assert err.process_instance_id == "pi_123"
        assert err.step_name == "step1"

    def test_to_dict(self):
        err = AppOSError("fail", execution_id="exec_1", object_ref="crm.rules.x")
        d = err.to_dict()
        assert d["error_type"] == "AppOSError"
        assert d["message"] == "fail"
        assert d["execution_id"] == "exec_1"
        assert d["object_ref"] == "crm.rules.x"
        assert "timestamp" in d

    def test_to_json(self):
        err = AppOSError("fail")
        raw = err.to_json()
        parsed = json.loads(raw)
        assert parsed["error_type"] == "AppOSError"
        assert parsed["message"] == "fail"

    def test_repr(self):
        err = AppOSError("fail", object_ref="crm.rules.x", execution_id="exec_1")
        r = repr(err)
        assert "AppOSError" in r
        assert "crm.rules.x" in r
        assert "exec_1" in r

    def test_dependency_chain(self):
        err = AppOSError(
            "chain error",
            dependency_chain=["a.rules.x", "a.rules.y", "a.rules.z"],
        )
        assert err.dependency_chain == ["a.rules.x", "a.rules.y", "a.rules.z"]

    def test_extra_context_serialized(self):
        err = AppOSError("fail", custom_field="hello")
        d = err.to_dict()
        assert d["context"]["custom_field"] == "hello"


class TestAppOSSecurityError:
    def test_security_fields(self):
        err = AppOSSecurityError(
            "denied",
            user_id="42",
            user_groups=["crm_users"],
            required_permission="update",
            object_ref="crm.records.customer",
        )
        assert err.user_id == "42"
        assert err.user_groups == ["crm_users"]
        assert err.required_permission == "update"
        assert err.error_type == "AppOSSecurityError"

    def test_to_dict_includes_fields(self):
        err = AppOSSecurityError("denied", user_id="1", user_groups=["g"], required_permission="view")
        d = err.to_dict()
        assert d["user_id"] == "1"
        assert d["required_permission"] == "view"

    def test_is_subclass(self):
        err = AppOSSecurityError("denied")
        assert isinstance(err, AppOSError)


class TestAppOSValidationError:
    def test_validation_errors(self):
        err = AppOSValidationError(
            "bad input",
            validation_errors=[{"field": "email", "error": "invalid"}],
        )
        assert err.validation_errors == [{"field": "email", "error": "invalid"}]
        d = err.to_dict()
        assert "validation_errors" in d


class TestAppOSTimeoutError:
    def test_timeout_seconds(self):
        err = AppOSTimeoutError("too slow", timeout_seconds=30)
        assert err.timeout_seconds == 30


class TestAppOSIntegrationError:
    def test_integration_fields(self):
        err = AppOSIntegrationError(
            "API failed",
            connected_system="salesforce",
            status_code=500,
            response_body="Internal Server Error",
        )
        assert err.connected_system == "salesforce"
        assert err.status_code == 500
        d = err.to_dict()
        assert d["connected_system"] == "salesforce"
        assert d["status_code"] == 500


class TestAppOSRecordError:
    def test_record_fields(self):
        err = AppOSRecordError(
            "duplicate",
            record_type="customer",
            record_id=42,
            operation="create",
        )
        assert err.record_type == "customer"
        assert err.record_id == 42
        assert err.operation == "create"


class TestAppOSSimpleSubclasses:
    def test_dispatch_error(self):
        err = AppOSDispatchError("not found")
        assert isinstance(err, AppOSError)

    def test_object_not_found(self):
        err = AppOSObjectNotFoundError("missing")
        assert isinstance(err, AppOSError)

    def test_config_error(self):
        err = AppOSConfigError("bad config")
        assert isinstance(err, AppOSError)

    def test_session_error(self):
        err = AppOSSessionError("expired")
        assert isinstance(err, AppOSError)


class TestErrorRaiseCatch:
    """Ensure errors can be raised and caught via hierarchy."""

    def test_catch_base(self):
        with pytest.raises(AppOSError):
            raise AppOSSecurityError("denied")

    def test_catch_specific(self):
        with pytest.raises(AppOSSecurityError):
            raise AppOSSecurityError("denied")

    def test_does_not_match_sibling(self):
        with pytest.raises(AppOSSecurityError):
            raise AppOSSecurityError("denied")
        # This should NOT catch as ValidationError
        with pytest.raises(AppOSSecurityError):
            try:
                raise AppOSSecurityError("denied")
            except AppOSValidationError:
                pytest.fail("Should not have caught as ValidationError")
