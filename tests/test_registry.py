"""Unit tests for appos.engine.registry — ObjectRegistryManager."""

import pytest

from appos.engine.registry import (
    OBJECT_TYPES,
    ObjectRegistryManager,
    RegisteredObject,
)
from appos.engine.errors import AppOSObjectNotFoundError


def _make_obj(
    ref: str = "crm.rules.calc",
    obj_type: str = "expression_rule",
    app: str = "crm",
    name: str = "calc",
) -> RegisteredObject:
    return RegisteredObject(
        object_ref=ref,
        object_type=obj_type,
        app_name=app,
        name=name,
        module_path=f"apps.{app}.rules.{name}",
        file_path=f"apps/{app}/rules/{name}.py",
        source_hash="abc123",
    )


class TestRegisteredObject:
    def test_category_mapping(self):
        obj = _make_obj(obj_type="expression_rule")
        assert obj.category == "rules"

        obj2 = _make_obj(obj_type="record", ref="crm.records.customer", name="customer")
        assert obj2.category == "records"

        obj3 = _make_obj(obj_type="process", ref="crm.processes.onboard", name="onboard")
        assert obj3.category == "processes"

    def test_default_values(self):
        obj = _make_obj()
        assert obj.metadata == {}
        assert obj.handler is None
        assert obj.is_active is True


class TestObjectRegistryManager:
    def setup_method(self):
        self.reg = ObjectRegistryManager()

    def test_register_and_resolve(self):
        obj = _make_obj()
        self.reg.register(obj)
        resolved = self.reg.resolve("crm.rules.calc")
        assert resolved is obj

    def test_resolve_missing(self):
        assert self.reg.resolve("nonexistent") is None

    def test_resolve_or_raise(self):
        with pytest.raises(AppOSObjectNotFoundError):
            self.reg.resolve_or_raise("nonexistent")

    def test_resolve_or_raise_success(self):
        obj = _make_obj()
        self.reg.register(obj)
        assert self.reg.resolve_or_raise("crm.rules.calc") is obj

    def test_invalid_type_raises(self):
        obj = _make_obj(obj_type="invalid_type")
        with pytest.raises(ValueError, match="Invalid object type"):
            self.reg.register(obj)

    def test_unregister(self):
        obj = _make_obj()
        self.reg.register(obj)
        self.reg.unregister("crm.rules.calc")
        assert self.reg.resolve("crm.rules.calc") is None
        assert self.reg.count == 0

    def test_unregister_nonexistent(self):
        self.reg.unregister("nonexistent")  # should not raise

    def test_get_by_type(self):
        self.reg.register(_make_obj("crm.rules.a", "expression_rule", "crm", "a"))
        self.reg.register(_make_obj("crm.rules.b", "expression_rule", "crm", "b"))
        self.reg.register(_make_obj("crm.records.c", "record", "crm", "c"))
        results = self.reg.get_by_type("expression_rule")
        assert len(results) == 2

    def test_get_by_type_with_app(self):
        self.reg.register(_make_obj("crm.rules.a", "expression_rule", "crm", "a"))
        self.reg.register(_make_obj("fin.rules.b", "expression_rule", "fin", "b"))
        results = self.reg.get_by_type("expression_rule", app_name="crm")
        assert len(results) == 1
        assert results[0].object_ref == "crm.rules.a"

    def test_get_by_app(self):
        self.reg.register(_make_obj("crm.rules.a", "expression_rule", "crm", "a"))
        self.reg.register(_make_obj("crm.records.b", "record", "crm", "b"))
        self.reg.register(_make_obj("fin.rules.c", "expression_rule", "fin", "c"))
        results = self.reg.get_by_app("crm")
        assert len(results) == 2

    def test_get_all_and_refs(self):
        self.reg.register(_make_obj("crm.rules.a", "expression_rule", "crm", "a"))
        self.reg.register(_make_obj("crm.rules.b", "expression_rule", "crm", "b"))
        assert len(self.reg.get_all()) == 2
        refs = self.reg.get_all_refs()
        assert "crm.rules.a" in refs
        assert "crm.rules.b" in refs

    def test_contains(self):
        self.reg.register(_make_obj())
        assert self.reg.contains("crm.rules.calc") is True
        assert self.reg.contains("nonexistent") is False

    def test_count(self):
        assert self.reg.count == 0
        self.reg.register(_make_obj("crm.rules.a", "expression_rule", "crm", "a"))
        assert self.reg.count == 1

    def test_clear(self):
        self.reg.register(_make_obj())
        self.reg.clear()
        assert self.reg.count == 0
        assert self.reg.resolve("crm.rules.calc") is None

    def test_scan_app_directory(self, project_root):
        # Create a Python file in rules/
        rules_dir = project_root / "apps" / "crm" / "rules"
        (rules_dir / "calculate_discount.py").write_text("# rule\n")
        (rules_dir / "_private.py").write_text("# skip\n")

        count = self.reg.scan_app_directory("crm", project_root / "apps" / "crm")
        assert count >= 1
        assert self.reg.contains("crm.rules.calculate_discount")
        # Private files (starting with _) should be skipped
        assert not self.reg.contains("crm.rules._private")


class TestObjectTypes:
    """Verify the full set of valid object types."""

    def test_all_types_present(self):
        expected = {
            "record", "expression_rule", "constant", "process", "step",
            "integration", "web_api", "interface", "page", "site",
            "document", "folder", "translation_set", "connected_system",
        }
        assert OBJECT_TYPES == expected
