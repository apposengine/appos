"""
AppOS Dependency Graph — NetworkX-based runtime dependency tracking.

Implements:
- DependencyGraph: In-memory DiGraph with JSON persistence
- Automatic dependency tracking (called by SecureAutoImportNamespace)
- Impact analysis (direct + transitive dependents)
- JSON persistence to .appos/runtime/dependencies/
- DB historical tracking via dependency_changes table

Design refs: AppOS_Design.md §10
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]

logger = logging.getLogger("appos.engine.dependency")


class DependencyGraph:
    """
    In-memory dependency graph backed by NetworkX DiGraph.

    Edges: caller → target (caller depends-on target).
    Nodes: object_ref strings (e.g., "crm.rules.calculate_discount").
    Metadata on edges: access type (read/execute/write), first_seen, last_seen.

    Persistence:
    - JSON files: .appos/runtime/dependencies/{object_ref}.json
    - DB: dependency_changes table (historical audit)
    """

    def __init__(
        self,
        persistence_dir: str = ".appos/runtime/dependencies",
        db_session_factory=None,
    ):
        if nx is None:
            raise ImportError("networkx is required for DependencyGraph. Install: pip install networkx")

        self._graph = nx.DiGraph()
        self._persistence_dir = Path(persistence_dir)
        self._persistence_dir.mkdir(parents=True, exist_ok=True)
        self._db_session_factory = db_session_factory
        self._dirty: Set[str] = set()  # Nodes needing JSON refresh

    # -----------------------------------------------------------------------
    # Core graph operations
    # -----------------------------------------------------------------------

    def add_dependency(
        self,
        caller_ref: str,
        target_ref: str,
        access: str = "read",
    ) -> None:
        """
        Record that caller depends on target.

        Args:
            caller_ref: Object that accesses the target (e.g., "crm.rules.calc").
            target_ref: Object being accessed (e.g., "crm.constants.TAX_RATE").
            access: Access type — read | execute | write.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Add nodes if new
        if not self._graph.has_node(caller_ref):
            self._graph.add_node(caller_ref, first_seen=now)
        if not self._graph.has_node(target_ref):
            self._graph.add_node(target_ref, first_seen=now)

        # Add or update edge
        if self._graph.has_edge(caller_ref, target_ref):
            self._graph[caller_ref][target_ref]["last_seen"] = now
            self._graph[caller_ref][target_ref]["access"] = access
        else:
            self._graph.add_edge(
                caller_ref,
                target_ref,
                access=access,
                first_seen=now,
                last_seen=now,
            )

        self._dirty.add(caller_ref)
        self._dirty.add(target_ref)

    def remove_dependency(self, caller_ref: str, target_ref: str) -> bool:
        """Remove a specific dependency edge."""
        if self._graph.has_edge(caller_ref, target_ref):
            self._graph.remove_edge(caller_ref, target_ref)
            self._dirty.add(caller_ref)
            self._dirty.add(target_ref)
            return True
        return False

    def remove_node(self, object_ref: str) -> bool:
        """Remove a node and all its edges."""
        if self._graph.has_node(object_ref):
            # Track affected neighbors for dirty marking
            neighbors = set(self._graph.predecessors(object_ref)) | set(
                self._graph.successors(object_ref)
            )
            self._graph.remove_node(object_ref)
            self._dirty.update(neighbors)
            # Remove JSON file
            json_path = self._persistence_dir / f"{object_ref}.json"
            if json_path.exists():
                json_path.unlink()
            return True
        return False

    # -----------------------------------------------------------------------
    # Query operations
    # -----------------------------------------------------------------------

    def get_direct_dependencies(self, object_ref: str) -> List[Dict[str, str]]:
        """Get objects that object_ref directly depends on."""
        if not self._graph.has_node(object_ref):
            return []

        deps = []
        for target in self._graph.successors(object_ref):
            edge = self._graph[object_ref][target]
            deps.append({
                "ref": target,
                "type": self._infer_type(target),
                "access": edge.get("access", "read"),
            })
        return deps

    def get_direct_dependents(self, object_ref: str) -> List[Dict[str, str]]:
        """Get objects that depend on object_ref."""
        if not self._graph.has_node(object_ref):
            return []

        deps = []
        for caller in self._graph.predecessors(object_ref):
            edge = self._graph[caller][object_ref]
            deps.append({
                "ref": caller,
                "type": self._infer_type(caller),
                "access": edge.get("access", "read"),
            })
        return deps

    def get_transitive_dependencies(self, object_ref: str) -> Set[str]:
        """Get all objects object_ref transitively depends on (DFS)."""
        if not self._graph.has_node(object_ref):
            return set()
        return set(nx.descendants(self._graph, object_ref))

    def get_transitive_dependents(self, object_ref: str) -> Set[str]:
        """Get all objects that transitively depend on object_ref."""
        if not self._graph.has_node(object_ref):
            return set()
        return set(nx.ancestors(self._graph, object_ref))

    def get_full_tree(self, object_ref: str) -> Dict[str, Any]:
        """
        Build a full recursive dependency tree for an object.
        Used for JSON persistence: "full_dependency_tree" field.
        """
        visited: Set[str] = set()

        def _build(ref: str) -> Dict[str, Any]:
            if ref in visited:
                return {"_circular": True}
            visited.add(ref)
            children = {}
            if self._graph.has_node(ref):
                for target in self._graph.successors(ref):
                    children[target] = _build(target)
            return children

        return {object_ref: _build(object_ref)}

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies."""
        try:
            return list(nx.simple_cycles(self._graph))
        except Exception:
            return []

    def has_dependency(self, caller_ref: str, target_ref: str) -> bool:
        """Check if there is a direct dependency."""
        return self._graph.has_edge(caller_ref, target_ref)

    # -----------------------------------------------------------------------
    # Impact Analysis
    # -----------------------------------------------------------------------

    def impact_analysis(self, object_ref: str) -> Dict[str, Any]:
        """
        Analyze the impact of changing an object.

        Returns:
            Dict with direct_dependents, transitive_dependents, total_impact,
            and recommendation text.
        """
        direct = self.get_direct_dependents(object_ref)
        transitive = self.get_transitive_dependents(object_ref)

        # Categorize by type
        processes = [r for r in transitive if ".processes." in r]
        web_apis = [r for r in transitive if ".web_apis." in r]
        interfaces = [r for r in transitive if ".interfaces." in r]
        rules = [r for r in transitive if ".rules." in r]

        total = len(transitive)
        parts = []
        if processes:
            parts.append(f"{len(processes)} process(es)")
        if web_apis:
            parts.append(f"{len(web_apis)} API endpoint(s)")
        if interfaces:
            parts.append(f"{len(interfaces)} interface(s)")
        if rules:
            parts.append(f"{len(rules)} rule(s)")

        recommendation = (
            f"Changing {object_ref} affects {total} object(s)"
            + (f" across {', '.join(parts)}" if parts else "")
            + "."
        )

        return {
            "object_ref": object_ref,
            "direct_dependents": [d["ref"] for d in direct],
            "transitive_dependents": sorted(transitive),
            "total_impact": total,
            "breakdown": {
                "processes": processes,
                "web_apis": web_apis,
                "interfaces": interfaces,
                "rules": rules,
            },
            "recommendation": recommendation,
        }

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def persist(self, object_ref: Optional[str] = None) -> int:
        """
        Write dependency data to JSON files.

        Args:
            object_ref: If given, persist only this object. Otherwise, persist all dirty nodes.

        Returns:
            Number of files written.
        """
        refs = {object_ref} if object_ref else self._dirty.copy()
        written = 0

        for ref in refs:
            if not self._graph.has_node(ref):
                continue

            data = {
                "object": ref,
                "type": self._infer_type(ref),
                "app": self._infer_app(ref),
                "direct_dependencies": self.get_direct_dependencies(ref),
                "full_dependency_tree": self.get_full_tree(ref),
                "dependents": self.get_direct_dependents(ref),
                "last_modified": datetime.now(timezone.utc).isoformat(),
            }

            file_path = self._persistence_dir / f"{ref}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

            written += 1

        self._dirty -= refs
        return written

    def persist_all(self) -> int:
        """Persist all nodes in the graph."""
        written = 0
        for node in self._graph.nodes:
            self._dirty.add(node)
        return self.persist()

    def load(self) -> int:
        """
        Load dependency data from JSON files into the graph.

        Returns:
            Number of files loaded.
        """
        loaded = 0
        for json_file in self._persistence_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                obj_ref = data["object"]
                if not self._graph.has_node(obj_ref):
                    self._graph.add_node(obj_ref)

                for dep in data.get("direct_dependencies", []):
                    target = dep["ref"]
                    if not self._graph.has_node(target):
                        self._graph.add_node(target)
                    if not self._graph.has_edge(obj_ref, target):
                        self._graph.add_edge(
                            obj_ref,
                            target,
                            access=dep.get("access", "read"),
                        )

                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load {json_file}: {e}")

        logger.info(f"Loaded {loaded} dependency files ({self._graph.number_of_nodes()} nodes, {self._graph.number_of_edges()} edges)")
        return loaded

    # -----------------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics about the dependency graph."""
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "cycles": len(self.detect_cycles()),
            "dirty_nodes": len(self._dirty),
        }

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    @staticmethod
    def _infer_type(object_ref: str) -> str:
        """Infer object type from ref: crm.rules.X → expression_rule."""
        parts = object_ref.split(".")
        if len(parts) >= 2:
            type_map = {
                "rules": "expression_rule",
                "records": "record",
                "constants": "constant",
                "processes": "process",
                "steps": "step",
                "integrations": "integration",
                "web_apis": "web_api",
                "interfaces": "interface",
                "pages": "page",
                "translation_sets": "translation_set",
                "documents": "document",
                "folders": "folder",
                "connected_systems": "connected_system",
            }
            return type_map.get(parts[1] if len(parts) > 2 else parts[0], "unknown")
        return "unknown"

    @staticmethod
    def _infer_app(object_ref: str) -> str:
        """Infer app name from ref: crm.rules.X → crm."""
        parts = object_ref.split(".")
        return parts[0] if parts else "unknown"
