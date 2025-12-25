"""
Graph Store Port Interface
Abstract interface for graph database operations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple


@dataclass
class GraphStoreConfig:
    """Graph store configuration"""
    database: str = "neo4j"

    # Connection settings
    uri: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Provider-specific settings
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphNode:
    """Graph node entity"""
    id: str
    labels: List[str]
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "labels": self.labels,
            "properties": self.properties
        }


@dataclass
class GraphRelation:
    """Graph relationship entity"""
    id: str
    type: str
    source_id: str
    target_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": self.properties
        }


@dataclass
class GraphPath:
    """Path in graph (sequence of nodes and relationships)"""
    nodes: List[GraphNode]
    relationships: List[GraphRelation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "relationships": [r.to_dict() for r in self.relationships]
        }


@dataclass
class GraphQueryResult:
    """Result of a graph query"""
    nodes: List[GraphNode] = field(default_factory=list)
    relationships: List[GraphRelation] = field(default_factory=list)
    paths: List[GraphPath] = field(default_factory=list)
    raw_result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class GraphStorePort(ABC):
    """
    Abstract interface for graph database operations.

    All graph store implementations must implement this interface.
    This allows swapping between different providers (Neo4j, ArangoDB, Neptune, etc.)
    without changing the application logic.
    """

    # ==================== Node Operations ====================

    @abstractmethod
    async def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any]
    ) -> GraphNode:
        """
        Create a new node.

        Args:
            labels: Node labels
            properties: Node properties

        Returns:
            Created node
        """
        pass

    @abstractmethod
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """
        Get node by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node if found
        """
        pass

    @abstractmethod
    async def update_node(
        self,
        node_id: str,
        properties: Dict[str, Any]
    ) -> Optional[GraphNode]:
        """
        Update node properties.

        Args:
            node_id: Node identifier
            properties: Properties to update

        Returns:
            Updated node
        """
        pass

    @abstractmethod
    async def delete_node(self, node_id: str, detach: bool = True) -> bool:
        """
        Delete a node.

        Args:
            node_id: Node identifier
            detach: Whether to delete relationships too

        Returns:
            True if deleted
        """
        pass

    @abstractmethod
    async def find_nodes(
        self,
        labels: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[GraphNode]:
        """
        Find nodes by labels and properties.

        Args:
            labels: Filter by labels
            properties: Filter by properties
            limit: Maximum results

        Returns:
            List of matching nodes
        """
        pass

    # ==================== Relationship Operations ====================

    @abstractmethod
    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> GraphRelation:
        """
        Create a relationship between nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            rel_type: Relationship type
            properties: Relationship properties

        Returns:
            Created relationship
        """
        pass

    @abstractmethod
    async def get_relationship(self, rel_id: str) -> Optional[GraphRelation]:
        """
        Get relationship by ID.

        Args:
            rel_id: Relationship identifier

        Returns:
            Relationship if found
        """
        pass

    @abstractmethod
    async def delete_relationship(self, rel_id: str) -> bool:
        """
        Delete a relationship.

        Args:
            rel_id: Relationship identifier

        Returns:
            True if deleted
        """
        pass

    @abstractmethod
    async def find_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        rel_type: Optional[str] = None,
        limit: int = 100
    ) -> List[GraphRelation]:
        """
        Find relationships by criteria.

        Args:
            source_id: Filter by source node
            target_id: Filter by target node
            rel_type: Filter by relationship type
            limit: Maximum results

        Returns:
            List of matching relationships
        """
        pass

    # ==================== Traversal Operations ====================

    @abstractmethod
    async def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",  # "outgoing", "incoming", "both"
        rel_types: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Tuple[GraphRelation, GraphNode]]:
        """
        Get neighboring nodes.

        Args:
            node_id: Source node ID
            direction: Relationship direction
            rel_types: Filter by relationship types
            limit: Maximum results

        Returns:
            List of (relationship, neighbor) tuples
        """
        pass

    @abstractmethod
    async def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        rel_types: Optional[List[str]] = None
    ) -> List[GraphPath]:
        """
        Find paths between nodes.

        Args:
            source_id: Start node ID
            target_id: End node ID
            max_depth: Maximum path length
            rel_types: Filter by relationship types

        Returns:
            List of paths
        """
        pass

    @abstractmethod
    async def find_shortest_path(
        self,
        source_id: str,
        target_id: str,
        rel_types: Optional[List[str]] = None
    ) -> Optional[GraphPath]:
        """
        Find shortest path between nodes.

        Args:
            source_id: Start node ID
            target_id: End node ID
            rel_types: Filter by relationship types

        Returns:
            Shortest path if exists
        """
        pass

    # ==================== Query Operations ====================

    @abstractmethod
    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> GraphQueryResult:
        """
        Execute a raw graph query (Cypher, AQL, etc.)

        Args:
            query: Query string
            parameters: Query parameters

        Returns:
            Query result
        """
        pass

    async def execute_read_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> GraphQueryResult:
        """
        Execute a read-only query (may use read replicas).

        Args:
            query: Query string
            parameters: Query parameters

        Returns:
            Query result
        """
        return await self.execute_query(query, parameters)

    # ==================== Schema Operations ====================

    @abstractmethod
    async def create_index(
        self,
        label: str,
        properties: List[str],
        unique: bool = False
    ) -> bool:
        """
        Create an index on node properties.

        Args:
            label: Node label
            properties: Properties to index
            unique: Whether index should enforce uniqueness

        Returns:
            True if created
        """
        pass

    @abstractmethod
    async def drop_index(self, label: str, properties: List[str]) -> bool:
        """
        Drop an index.

        Args:
            label: Node label
            properties: Indexed properties

        Returns:
            True if dropped
        """
        pass

    @abstractmethod
    async def list_indexes(self) -> List[Dict[str, Any]]:
        """
        List all indexes.

        Returns:
            List of index definitions
        """
        pass

    # ==================== Utility Operations ====================

    @abstractmethod
    async def count_nodes(
        self,
        labels: Optional[List[str]] = None
    ) -> int:
        """
        Count nodes.

        Args:
            labels: Filter by labels

        Returns:
            Node count
        """
        pass

    @abstractmethod
    async def count_relationships(
        self,
        rel_type: Optional[str] = None
    ) -> int:
        """
        Count relationships.

        Args:
            rel_type: Filter by type

        Returns:
            Relationship count
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the graph store is healthy.

        Returns:
            True if service is healthy
        """
        pass

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get graph statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "node_count": await self.count_nodes(),
            "relationship_count": await self.count_relationships()
        }
