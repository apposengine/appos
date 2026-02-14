"""Unit tests for appos.engine.dependency — DependencyGraph."""

import json
import pytest
from pathlib import Path

from appos.engine.dependency import DependencyGraph


@pytest.fixture
def graph(tmp_path):
    """Create a DependencyGraph with temp persistence dir."""
    return DependencyGraph(persistence_dir=str(tmp_path / "deps"))


class TestDependencyGraphCore:
    """Core graph operations: add, remove, query."""

    def test_add_dependency(self, graph):
        graph.add_dependency("crm.rules.a", "crm.constants.TAX", access="read")
        assert graph.has_dependency("crm.rules.a", "crm.constants.TAX")
        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_add_dependency_updates_existing(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y", access="read")
        graph.add_dependency("a.rules.x", "a.constants.Y", access="execute")
        assert graph.edge_count == 1  # Still one edge, updated

    def test_remove_dependency(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y")
        assert graph.remove_dependency("a.rules.x", "a.constants.Y") is True
        assert not graph.has_dependency("a.rules.x", "a.constants.Y")

    def test_remove_nonexistent(self, graph):
        assert graph.remove_dependency("a", "b") is False

    def test_remove_node(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y")
        graph.add_dependency("a.rules.z", "a.constants.Y")
        assert graph.remove_node("a.constants.Y") is True
        assert graph.node_count == 2  # x and z remain
        assert graph.edge_count == 0

    def test_remove_nonexistent_node(self, graph):
        assert graph.remove_node("nonexistent") is False


class TestDependencyGraphQueries:
    """Query operations."""

    @pytest.fixture(autouse=True)
    def _setup_graph(self, graph):
        self.g = graph
        # Build: a -> b -> c
        #        a -> d
        self.g.add_dependency("a.rules.a", "a.rules.b", "execute")
        self.g.add_dependency("a.rules.b", "a.rules.c", "read")
        self.g.add_dependency("a.rules.a", "a.constants.d", "read")

    def test_direct_dependencies(self):
        deps = self.g.get_direct_dependencies("a.rules.a")
        refs = {d["ref"] for d in deps}
        assert refs == {"a.rules.b", "a.constants.d"}

    def test_direct_dependents(self):
        deps = self.g.get_direct_dependents("a.rules.b")
        refs = {d["ref"] for d in deps}
        assert refs == {"a.rules.a"}

    def test_transitive_dependencies(self):
        trans = self.g.get_transitive_dependencies("a.rules.a")
        assert "a.rules.b" in trans
        assert "a.rules.c" in trans
        assert "a.constants.d" in trans

    def test_transitive_dependents(self):
        trans = self.g.get_transitive_dependents("a.rules.c")
        assert "a.rules.b" in trans
        assert "a.rules.a" in trans

    def test_transitive_nonexistent(self):
        assert self.g.get_transitive_dependencies("nonexistent") == set()
        assert self.g.get_transitive_dependents("nonexistent") == set()

    def test_direct_deps_nonexistent(self):
        assert self.g.get_direct_dependencies("nonexistent") == []
        assert self.g.get_direct_dependents("nonexistent") == []

    def test_full_tree(self):
        tree = self.g.get_full_tree("a.rules.a")
        assert "a.rules.a" in tree

    def test_detect_cycles_none(self):
        cycles = self.g.detect_cycles()
        assert cycles == []

    def test_detect_cycles_present(self, graph):
        graph.add_dependency("x.rules.a", "x.rules.b")
        graph.add_dependency("x.rules.b", "x.rules.a")
        cycles = graph.detect_cycles()
        assert len(cycles) > 0


class TestImpactAnalysis:
    """Test impact_analysis() method."""

    def test_impact_analysis(self, graph):
        graph.add_dependency("crm.processes.onboard", "crm.rules.calc")
        graph.add_dependency("crm.web_apis.get_pricing", "crm.rules.calc")
        graph.add_dependency("crm.interfaces.dashboard", "crm.rules.calc")

        result = graph.impact_analysis("crm.rules.calc")
        assert result["object_ref"] == "crm.rules.calc"
        assert result["total_impact"] == 3
        assert "crm.processes.onboard" in result["transitive_dependents"]
        assert len(result["breakdown"]["processes"]) == 1
        assert len(result["breakdown"]["web_apis"]) == 1
        assert len(result["breakdown"]["interfaces"]) == 1
        assert "recommendation" in result

    def test_impact_analysis_no_dependents(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y")
        result = graph.impact_analysis("a.rules.x")
        assert result["total_impact"] == 0


class TestDependencyPersistence:
    """Test JSON persistence."""

    def test_persist_and_load(self, tmp_path):
        g1 = DependencyGraph(persistence_dir=str(tmp_path / "deps"))
        g1.add_dependency("a.rules.x", "a.constants.Y")
        written = g1.persist_all()
        assert written >= 1

        # Verify JSON file exists
        files = list((tmp_path / "deps").glob("*.json"))
        assert len(files) >= 1

        # Load into fresh graph
        g2 = DependencyGraph(persistence_dir=str(tmp_path / "deps"))
        loaded = g2.load()
        assert loaded >= 1
        assert g2.has_dependency("a.rules.x", "a.constants.Y")

    def test_persist_single(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y")
        written = graph.persist("a.rules.x")
        assert written == 1

    def test_stats(self, graph):
        graph.add_dependency("a.rules.x", "a.constants.Y")
        s = graph.stats()
        assert s["nodes"] == 2
        assert s["edges"] == 1
