"""Unit tests for appos.decorators — @record event hooks, @interface_extend, constant manager."""

import pytest
from unittest.mock import MagicMock, patch

from appos.decorators.record import (
    RecordEvent,
    RecordEventManager,
    RecordHook,
)
from appos.decorators.interface import (
    InterfaceExtendRegistry,
    interface_extend_registry,
)
from appos.decorators.constant import (
    ConstantManager,
    ResolvedConstant,
    _looks_like_object_ref,
    _infer_constant_type,
)


class TestRecordEvent:
    """Test RecordEvent constants."""

    def test_event_names(self):
        assert RecordEvent.ON_CREATE == "on_create"
        assert RecordEvent.ON_UPDATE == "on_update"
        assert RecordEvent.ON_DELETE == "on_delete"
        assert RecordEvent.ON_VIEW == "on_view"
        assert RecordEvent.BEFORE_CREATE == "before_create"
        assert RecordEvent.BEFORE_UPDATE == "before_update"
        assert RecordEvent.BEFORE_DELETE == "before_delete"


class TestRecordHook:
    def test_creation(self):
        hook = RecordHook(
            record_ref="crm.records.customer",
            event="on_create",
            target_ref="crm.rules.validate_customer",
        )
        assert hook.record_ref == "crm.records.customer"
        assert hook.event == "on_create"
        assert hook.target_ref == "crm.rules.validate_customer"
        assert hook.priority == 0
        assert hook.condition is None
        assert hook.async_dispatch is False


class TestRecordEventManager:
    def setup_method(self):
        self.mgr = RecordEventManager()

    def test_register_hook(self):
        self.mgr.register_hook(
            "crm.records.customer",
            "on_create",
            "crm.rules.validate",
        )
        hooks = self.mgr.get_hooks_for_record("crm.records.customer")
        assert len(hooks) == 1

    def test_register_multiple_hooks(self):
        self.mgr.register_hook("rec", "on_create", "rule_a")
        self.mgr.register_hook("rec", "on_create", "rule_b")
        self.mgr.register_hook("rec", "on_update", "rule_c")
        hooks = self.mgr.get_hooks_for_record("rec")
        assert len(hooks) == 3

    def test_hook_count(self):
        self.mgr.register_hook("rec", "on_create", "rule_a")
        self.mgr.register_hook("rec", "on_update", "rule_b")
        assert self.mgr.hook_count == 2

    def test_get_all_hooks(self):
        self.mgr.register_hook("rec_a", "on_create", "rule_1")
        self.mgr.register_hook("rec_b", "on_delete", "rule_2")
        all_hooks = self.mgr.get_all_hooks()
        assert "rec_a" in all_hooks
        assert "rec_b" in all_hooks


class TestInterfaceExtendRegistry:
    def setup_method(self):
        self.reg = InterfaceExtendRegistry()

    def test_register_and_get(self):
        def my_extension(base):
            return base + " extended"

        self.reg.register("crm.interfaces.dashboard", my_extension)
        exts = self.reg.get_extensions("crm.interfaces.dashboard")
        assert len(exts) == 1

    def test_has_extensions(self):
        self.reg.register("x", lambda b: b)
        assert self.reg.has_extensions("x") is True
        assert self.reg.has_extensions("y") is False

    def test_apply_extensions(self):
        self.reg.register("x", lambda b: b + " modified")
        result = self.reg.apply_extensions("x", "base")
        assert result == "base modified"

    def test_apply_no_extensions(self):
        result = self.reg.apply_extensions("y", "base")
        assert result == "base"

    def test_clear(self):
        self.reg.register("x", lambda b: b)
        self.reg.clear()
        assert self.reg.count == 0

    def test_count(self):
        self.reg.register("a", lambda b: b)
        self.reg.register("b", lambda b: b)
        assert self.reg.count == 2


class TestConstantHelpers:
    """Test constant utility functions."""

    def test_looks_like_object_ref(self):
        assert _looks_like_object_ref("crm.rules.calculate_discount") is True
        assert _looks_like_object_ref("crm.constants.TAX_RATE") is True
        assert _looks_like_object_ref("plain_string") is False
        assert _looks_like_object_ref(42) is False
        assert _looks_like_object_ref("") is False

    def test_infer_constant_type_primitive(self):
        assert _infer_constant_type(42, None) == "int"
        assert _infer_constant_type(3.14, None) == "float"
        assert _infer_constant_type("hello", None) == "str"
        assert _infer_constant_type(True, None) == "bool"

    def test_infer_constant_type_object_ref(self):
        result = _infer_constant_type("crm.rules.some_rule", None)
        assert result == "object_ref"


class TestResolvedConstant:
    def test_creation(self):
        rc = ResolvedConstant(
            object_ref="crm.constants.TAX_RATE",
            name="TAX_RATE",
            value=0.08,
            value_type="float",
            is_object_ref=False,
            target_ref=None,
            app_name="crm",
            raw_value=0.08,
        )
        assert rc.object_ref == "crm.constants.TAX_RATE"
        assert rc.value == 0.08
        assert rc.is_object_ref is False


class TestConstantManager:
    """Test ConstantManager with mocked registry."""

    def setup_method(self):
        from appos.engine.registry import ObjectRegistryManager
        self.registry = ObjectRegistryManager()
        self.mgr = ConstantManager(registry=self.registry)

    def test_get_all_constants_empty(self):
        result = self.mgr.get_all_constants("crm")
        assert result == []

    def test_clear_cache(self):
        # Should not raise
        self.mgr.clear_cache()

    def test_enable_disable_cache(self):
        self.mgr.disable_cache()
        self.mgr.enable_cache()
        # Should not raise

    def test_to_summary(self):
        summary = self.mgr.to_summary("crm")
        assert isinstance(summary, dict)
