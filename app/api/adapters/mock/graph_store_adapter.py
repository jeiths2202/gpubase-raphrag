"""
Mock Graph Store Adapter
Mock implementation for testing and development.
"""
from typing import Optional, List, Dict, Any, Tuple
import asyncio
import uuid

from ...ports.graph_store_port import (
    GraphStorePort,
    GraphStoreConfig,
    GraphNode,
    GraphRelation,
    GraphPath,
    GraphQueryResult
)


class MockGraphStoreAdapter(GraphStorePort):
    """
    Mock graph store adapter for testing and development.

    Uses in-memory storage with graph traversal.
    """

    def __init__(
        self,
        simulate_delay: bool = True,
        delay_ms: int = 10
    ):
        self.simulate_delay = simulate_delay
        self.delay_ms = delay_ms
        self._nodes: Dict[str, GraphNode] = {}
        self._relationships: Dict[str, GraphRelation] = {}
        self._outgoing: Dict[str, List[str]] = {}  # node_id -> [rel_id]
        self._incoming: Dict[str, List[str]] = {}  # node_id -> [rel_id]
        self._indexes: Dict[str, Dict[str, Any]] = {}

    # ==================== Node Operations ====================

    async def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any]
    ) -> GraphNode:
        """Create a new node"""
        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        node_id = str(uuid.uuid4())
        node = GraphNode(id=node_id, labels=labels, properties=properties)

        self._nodes[node_id] = node
        self._outgoing[node_id] = []
        self._incoming[node_id] = []

        return node

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by ID"""
        return self._nodes.get(node_id)

    async def update_node(
        self,
        node_id: str,
        properties: Dict[str, Any]
    ) -> Optional[GraphNode]:
        """Update node properties"""
        node = self._nodes.get(node_id)
        if not node:
            return None

        node.properties.update(properties)
        return node

    async def delete_node(self, node_id: str, detach: bool = True) -> bool:
        """Delete a node"""
        if node_id not in self._nodes:
            return False

        if detach:
            # Delete all relationships
            for rel_id in list(self._outgoing.get(node_id, [])):
                await self.delete_relationship(rel_id)
            for rel_id in list(self._incoming.get(node_id, [])):
                await self.delete_relationship(rel_id)

        del self._nodes[node_id]
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)

        return True

    async def find_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[GraphNode]:
        """Find nodes by labels and properties"""
        results = []

        for node in self._nodes.values():
            # Check labels
            if labels and not all(l in node.labels for l in labels):
                continue

            # Check properties
            if properties:
                match = True
                for key, value in properties.items():
                    if node.properties.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            results.append(node)

            if len(results) >= limit:
                break

        return results

    # ==================== Relationship Operations ====================

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> GraphRelation:
        """Create a relationship"""
        if source_id not in self._nodes or target_id not in self._nodes:
            raise ValueError("Source or target node does not exist")

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        rel_id = str(uuid.uuid4())
        rel = GraphRelation(
            id=rel_id,
            type=rel_type,
            source_id=source_id,
            target_id=target_id,
            properties=properties or {}
        )

        self._relationships[rel_id] = rel
        self._outgoing[source_id].append(rel_id)
        self._incoming[target_id].append(rel_id)

        return rel

    async def get_relationship(self, rel_id: str) -> Optional[GraphRelation]:
        """Get relationship by ID"""
        return self._relationships.get(rel_id)

    async def delete_relationship(self, rel_id: str) -> bool:
        """Delete a relationship"""
        rel = self._relationships.get(rel_id)
        if not rel:
            return False

        self._outgoing[rel.source_id].remove(rel_id)
        self._incoming[rel.target_id].remove(rel_id)
        del self._relationships[rel_id]

        return True

    async def find_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        rel_type: Optional[str] = None,
        limit: int = 100
    ) -> List[GraphRelation]:
        """Find relationships by criteria"""
        results = []

        for rel in self._relationships.values():
            if source_id and rel.source_id != source_id:
                continue
            if target_id and rel.target_id != target_id:
                continue
            if rel_type and rel.type != rel_type:
                continue

            results.append(rel)

            if len(results) >= limit:
                break

        return results

    # ==================== Traversal Operations ====================

    async def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        rel_types: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Tuple[GraphRelation, GraphNode]]:
        """Get neighboring nodes"""
        results = []

        rel_ids = []
        if direction in ("outgoing", "both"):
            rel_ids.extend(self._outgoing.get(node_id, []))
        if direction in ("incoming", "both"):
            rel_ids.extend(self._incoming.get(node_id, []))

        for rel_id in rel_ids:
            rel = self._relationships.get(rel_id)
            if not rel:
                continue

            if rel_types and rel.type not in rel_types:
                continue

            neighbor_id = rel.target_id if rel.source_id == node_id else rel.source_id
            neighbor = self._nodes.get(neighbor_id)

            if neighbor:
                results.append((rel, neighbor))

            if len(results) >= limit:
                break

        return results

    async def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        rel_types: Optional[List[str]] = None
    ) -> List[GraphPath]:
        """Find paths between nodes using BFS"""
        if source_id not in self._nodes or target_id not in self._nodes:
            return []

        paths = []
        queue: List[Tuple[List[str], List[str]]] = [([source_id], [])]  # (node_ids, rel_ids)
        visited = set()

        while queue and len(paths) < 10:  # Limit paths
            node_path, rel_path = queue.pop(0)
            current = node_path[-1]

            if len(node_path) > max_depth + 1:
                continue

            if current == target_id:
                # Build path
                nodes = [self._nodes[nid] for nid in node_path]
                relationships = [self._relationships[rid] for rid in rel_path]
                paths.append(GraphPath(nodes=nodes, relationships=relationships))
                continue

            visited.add(current)

            for rel_id in self._outgoing.get(current, []):
                rel = self._relationships[rel_id]
                if rel_types and rel.type not in rel_types:
                    continue

                if rel.target_id not in visited:
                    queue.append((node_path + [rel.target_id], rel_path + [rel_id]))

        return paths

    async def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        rel_types: Optional[List[str]] = None
    ) -> Optional[GraphPath]:
        """Find shortest path using BFS"""
        paths = await self.find_paths(source_id, target_id, max_depth=10, rel_types=rel_types)

        if not paths:
            return None

        return min(paths, key=lambda p: len(p.nodes))

    # ==================== Query Operations ====================

    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> GraphQueryResult:
        """Execute mock query (limited support)"""
        # Mock implementation - just return empty result
        return GraphQueryResult(
            nodes=[],
            relationships=[],
            metadata={"query": query, "params": parameters}
        )

    # ==================== Schema Operations ====================

    async def create_index(
        self,
        label: str,
        properties: List[str],
        unique: bool = False
    ) -> bool:
        """Create an index"""
        key = f"{label}:{','.join(properties)}"
        self._indexes[key] = {
            "label": label,
            "properties": properties,
            "unique": unique
        }
        return True

    async def drop_index(self, label: str, properties: List[str]) -> bool:
        """Drop an index"""
        key = f"{label}:{','.join(properties)}"
        if key in self._indexes:
            del self._indexes[key]
            return True
        return False

    async def list_indexes(self) -> List[Dict[str, Any]]:
        """List all indexes"""
        return list(self._indexes.values())

    # ==================== Utility Operations ====================

    async def count_nodes(
        self,
        labels: Optional[List[str]] = None
    ) -> int:
        """Count nodes"""
        if not labels:
            return len(self._nodes)

        return len([
            n for n in self._nodes.values()
            if all(l in n.labels for l in labels)
        ])

    async def count_relationships(
        self,
        rel_type: Optional[str] = None
    ) -> int:
        """Count relationships"""
        if not rel_type:
            return len(self._relationships)

        return len([
            r for r in self._relationships.values()
            if r.type == rel_type
        ])

    async def health_check(self) -> bool:
        """Always healthy"""
        return True

    # ==================== Test Helpers ====================

    def clear_all(self) -> None:
        """Clear all data"""
        self._nodes.clear()
        self._relationships.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._indexes.clear()
