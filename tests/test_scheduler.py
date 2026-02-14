"""Unit tests for appos.process.scheduler — EventTriggerRegistry, ScheduleTriggerRegistry."""

import pytest

from appos.process.scheduler import (
    EventTriggerRegistry,
    ScheduleTriggerRegistry,
    get_event_registry,
)


class TestEventTriggerRegistry:
    def setup_method(self):
        self.reg = EventTriggerRegistry()

    def test_register_trigger(self):
        self.reg.register("customer.created", "crm.processes.onboard")
        triggers = self.reg.get_triggers("customer.created")
        assert len(triggers) == 1
        assert triggers[0][0] == "crm.processes.onboard"

    def test_register_with_filter(self):
        filter_fn = lambda event_data: event_data.get("type") == "premium"
        self.reg.register("customer.created", "crm.processes.premium_onboard", filter_fn)
        triggers = self.reg.get_triggers("customer.created")
        assert triggers[0][1] is not None

    def test_deduplication(self):
        self.reg.register("evt", "proc_a")
        self.reg.register("evt", "proc_a")  # duplicate
        assert len(self.reg.get_triggers("evt")) == 1

    def test_multiple_triggers_per_event(self):
        self.reg.register("evt", "proc_a")
        self.reg.register("evt", "proc_b")
        assert len(self.reg.get_triggers("evt")) == 2

    def test_unregister(self):
        self.reg.register("evt", "proc_a")
        self.reg.register("evt", "proc_b")
        self.reg.unregister("evt", "proc_a")
        triggers = self.reg.get_triggers("evt")
        assert len(triggers) == 1
        assert triggers[0][0] == "proc_b"

    def test_get_triggers_empty(self):
        assert self.reg.get_triggers("nonexistent") == []

    def test_get_all_events(self):
        self.reg.register("evt_a", "proc_1")
        self.reg.register("evt_b", "proc_2")
        events = self.reg.get_all_events()
        assert set(events) == {"evt_a", "evt_b"}

    def test_clear(self):
        self.reg.register("evt", "proc")
        self.reg.clear()
        assert self.reg.count == 0

    def test_count(self):
        self.reg.register("evt_a", "proc_1")
        self.reg.register("evt_a", "proc_2")
        self.reg.register("evt_b", "proc_3")
        assert self.reg.count == 3


class TestScheduleTriggerRegistry:
    def setup_method(self):
        self.reg = ScheduleTriggerRegistry()

    def test_register_schedule(self):
        self.reg.register("crm.processes.cleanup", "0 2 * * *")
        schedules = self.reg.get_schedules()
        assert len(schedules) == 1
        assert schedules[0]["process_ref"] == "crm.processes.cleanup"
        assert schedules[0]["cron"] == "0 2 * * *"

    def test_register_with_timezone(self):
        self.reg.register("proc", "0 0 * * *", timezone_str="US/Eastern")
        schedules = self.reg.get_schedules()
        assert schedules[0]["timezone"] == "US/Eastern"

    def test_register_disabled(self):
        self.reg.register("proc", "0 0 * * *", enabled=False)
        assert len(self.reg.get_enabled_schedules()) == 0
        assert len(self.reg.get_schedules()) == 1

    def test_unregister(self):
        self.reg.register("proc_a", "0 0 * * *")
        self.reg.register("proc_b", "0 1 * * *")
        self.reg.unregister("proc_a")
        assert self.reg.count == 1

    def test_clear(self):
        self.reg.register("proc", "0 0 * * *")
        self.reg.clear()
        assert self.reg.count == 0


class TestSingletons:
    def test_event_registry_singleton(self):
        reg1 = get_event_registry()
        reg2 = get_event_registry()
        assert reg1 is reg2
