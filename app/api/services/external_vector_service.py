"""
External Vector Service
Neo4j vector index for external document chunks.

Maintains complete isolation from internal documents (:Chunk nodes).
Uses separate :ExternalChunk nodes and dedicated vector index.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExternalChunkData:
    """Data for creating an external chunk node"""
    id: str
    user_id: str
    document_id: str
    connection_id: str
    content: str
    embedding: List[float]
    source: str
    source_name: str
    source_url: Optional[str] = None
    section_title: Optional[str] = None
    chunk_index: int = 0
    is_code: bool = False
    is_table: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ExternalSearchResult:
    """Result from external vector search"""
    chunk_id: str
    document_id: str
    user_id: str
    connection_id: str
    source: str
    content: str
    score: float
    source_name: str
    source_url: Optional[str]
    section_title: Optional[str]
    chunk_index: int
    metadata: Dict[str, Any]


class ExternalVectorService:
    """
    Neo4j vector service for external document chunks.

    ISOLATION ARCHITECTURE:
    - Internal docs use :Chunk nodes and chunk_embedding index
    - External docs use :ExternalChunk nodes and external_chunk_embedding index
    - Search is ALWAYS filtered by user_id (no cross-user access)
    """

    # Index configuration
    EXTERNAL_INDEX_NAME = "external_chunk_embedding"
    DIMENSION = 1024
    SIMILARITY_FUNCTION = "cosine"

    def __init__(self, graph=None):
        """
        Initialize with optional Neo4j graph connection.

        Args:
            graph: Neo4jGraph instance (will be injected)
        """
        self._graph = graph
        self._index_initialized = False

    def set_graph(self, graph):
        """Set the Neo4j graph connection (for dependency injection)"""
        self._graph = graph
        self._index_initialized = False

    @property
    def graph(self):
        """Get Neo4j graph, lazy-loading if needed"""
        if self._graph is None:
            from langchain_neo4j import Neo4jGraph
            from config import config
            self._graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )
        return self._graph

    async def init_vector_index(self) -> bool:
        """
        Create vector index for ExternalChunk nodes if not exists.

        Returns:
            True if successful
        """
        if self._index_initialized:
            return True

        try:
            self.graph.query(f"""
                CREATE VECTOR INDEX {self.EXTERNAL_INDEX_NAME} IF NOT EXISTS
                FOR (c:ExternalChunk) ON (c.embedding)
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {self.DIMENSION},
                        `vector.similarity_function`: '{self.SIMILARITY_FUNCTION}'
                    }}
                }}
            """)
            logger.info(f"External vector index '{self.EXTERNAL_INDEX_NAME}' created/verified")
            self._index_initialized = True
            return True
        except Exception as e:
            logger.error(f"External vector index creation error: {e}")
            return False

    async def add_chunk(self, chunk: ExternalChunkData) -> bool:
        """
        Add an external chunk node with embedding to Neo4j.

        Args:
            chunk: ExternalChunkData with all required fields

        Returns:
            True if successful
        """
        if not chunk.embedding:
            logger.warning(f"Cannot add chunk {chunk.id} without embedding")
            return False

        try:
            self.graph.query("""
                CREATE (c:ExternalChunk {
                    id: $chunk_id,
                    user_id: $user_id,
                    document_id: $document_id,
                    connection_id: $connection_id,
                    content: $content,
                    embedding: $embedding,
                    source: $source,
                    source_name: $source_name,
                    source_url: $source_url,
                    section_title: $section_title,
                    chunk_index: $chunk_index,
                    is_code: $is_code,
                    is_table: $is_table
                })
            """, {
                "chunk_id": chunk.id,
                "user_id": chunk.user_id,
                "document_id": chunk.document_id,
                "connection_id": chunk.connection_id,
                "content": chunk.content,
                "embedding": chunk.embedding,
                "source": chunk.source,
                "source_name": chunk.source_name,
                "source_url": chunk.source_url,
                "section_title": chunk.section_title,
                "chunk_index": chunk.chunk_index,
                "is_code": chunk.is_code,
                "is_table": chunk.is_table
            })
            return True
        except Exception as e:
            logger.error(f"Error adding external chunk {chunk.id}: {e}")
            return False

    async def add_chunks_batch(self, chunks: List[ExternalChunkData]) -> int:
        """
        Add multiple external chunks in batch.

        Args:
            chunks: List of ExternalChunkData

        Returns:
            Number of successfully added chunks
        """
        if not chunks:
            return 0

        # Filter chunks without embeddings
        valid_chunks = [c for c in chunks if c.embedding]
        if not valid_chunks:
            return 0

        try:
            # Use UNWIND for batch insert
            params = [{
                "chunk_id": c.id,
                "user_id": c.user_id,
                "document_id": c.document_id,
                "connection_id": c.connection_id,
                "content": c.content,
                "embedding": c.embedding,
                "source": c.source,
                "source_name": c.source_name,
                "source_url": c.source_url,
                "section_title": c.section_title,
                "chunk_index": c.chunk_index,
                "is_code": c.is_code,
                "is_table": c.is_table
            } for c in valid_chunks]

            self.graph.query("""
                UNWIND $chunks AS chunk
                CREATE (c:ExternalChunk {
                    id: chunk.chunk_id,
                    user_id: chunk.user_id,
                    document_id: chunk.document_id,
                    connection_id: chunk.connection_id,
                    content: chunk.content,
                    embedding: chunk.embedding,
                    source: chunk.source,
                    source_name: chunk.source_name,
                    source_url: chunk.source_url,
                    section_title: chunk.section_title,
                    chunk_index: chunk.chunk_index,
                    is_code: chunk.is_code,
                    is_table: chunk.is_table
                })
            """, {"chunks": params})

            logger.info(f"Added {len(valid_chunks)} external chunks to Neo4j")
            return len(valid_chunks)
        except Exception as e:
            logger.error(f"Error batch adding external chunks: {e}")
            return 0

    async def search(
        self,
        user_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.3,
        connection_ids: Optional[List[str]] = None
    ) -> List[ExternalSearchResult]:
        """
        Search for similar chunks in user's external resources.

        SECURITY: Always filtered by user_id for isolation.

        Args:
            user_id: User ID (required, enforces isolation)
            query_embedding: Query embedding vector
            top_k: Maximum results to return
            min_score: Minimum similarity score threshold
            connection_ids: Optional filter for specific connections

        Returns:
            List of ExternalSearchResult
        """
        if not user_id:
            logger.warning("search called without user_id - returning empty results")
            return []

        try:
            # Build connection filter
            connection_filter = ""
            params = {
                "k": top_k * 2,  # Get more to filter by user_id
                "embedding": query_embedding,
                "user_id": user_id,
                "min_score": min_score
            }

            if connection_ids:
                connection_filter = "AND node.connection_id IN $connection_ids"
                params["connection_ids"] = connection_ids

            results = self.graph.query(f"""
                CALL db.index.vector.queryNodes(
                    '{self.EXTERNAL_INDEX_NAME}',
                    $k,
                    $embedding
                )
                YIELD node, score
                WHERE node.user_id = $user_id
                  AND score >= $min_score
                  {connection_filter}
                RETURN
                    node.id AS chunk_id,
                    node.document_id AS document_id,
                    node.user_id AS user_id,
                    node.connection_id AS connection_id,
                    node.source AS source,
                    node.content AS content,
                    score,
                    node.source_name AS source_name,
                    node.source_url AS source_url,
                    node.section_title AS section_title,
                    node.chunk_index AS chunk_index,
                    node.is_code AS is_code,
                    node.is_table AS is_table
                ORDER BY score DESC
                LIMIT $top_k
            """, {**params, "top_k": top_k})

            return [
                ExternalSearchResult(
                    chunk_id=r["chunk_id"],
                    document_id=r["document_id"],
                    user_id=r["user_id"],
                    connection_id=r["connection_id"],
                    source=r["source"],
                    content=r["content"],
                    score=r["score"],
                    source_name=r["source_name"],
                    source_url=r["source_url"],
                    section_title=r["section_title"],
                    chunk_index=r["chunk_index"] or 0,
                    metadata={
                        "is_code": r["is_code"],
                        "is_table": r["is_table"]
                    }
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"External vector search error: {e}")
            return []

    async def remove_document_chunks(self, document_id: str) -> int:
        """
        Remove all chunks for a specific document.

        Args:
            document_id: Document ID to remove chunks for

        Returns:
            Number of chunks removed
        """
        try:
            result = self.graph.query("""
                MATCH (c:ExternalChunk {document_id: $document_id})
                WITH c, count(c) AS count
                DELETE c
                RETURN count
            """, {"document_id": document_id})

            count = result[0]["count"] if result else 0
            logger.info(f"Removed {count} external chunks for document {document_id}")
            return count
        except Exception as e:
            logger.error(f"Error removing document chunks: {e}")
            return 0

    async def remove_connection_chunks(self, connection_id: str) -> int:
        """
        Remove all chunks for a specific connection.

        Args:
            connection_id: Connection ID to remove chunks for

        Returns:
            Number of chunks removed
        """
        try:
            result = self.graph.query("""
                MATCH (c:ExternalChunk {connection_id: $connection_id})
                WITH c, count(c) AS count
                DELETE c
                RETURN count
            """, {"connection_id": connection_id})

            count = result[0]["count"] if result else 0
            logger.info(f"Removed {count} external chunks for connection {connection_id}")
            return count
        except Exception as e:
            logger.error(f"Error removing connection chunks: {e}")
            return 0

    async def remove_user_chunks(self, user_id: str) -> int:
        """
        Remove all chunks for a specific user.

        Args:
            user_id: User ID to remove all chunks for

        Returns:
            Number of chunks removed
        """
        try:
            result = self.graph.query("""
                MATCH (c:ExternalChunk {user_id: $user_id})
                WITH c, count(c) AS count
                DELETE c
                RETURN count
            """, {"user_id": user_id})

            count = result[0]["count"] if result else 0
            logger.info(f"Removed {count} external chunks for user {user_id}")
            return count
        except Exception as e:
            logger.error(f"Error removing user chunks: {e}")
            return 0

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics for a user's external chunks.

        Args:
            user_id: User ID

        Returns:
            Dictionary with chunk stats by connection
        """
        try:
            results = self.graph.query("""
                MATCH (c:ExternalChunk {user_id: $user_id})
                RETURN
                    c.connection_id AS connection_id,
                    count(c) AS chunk_count
            """, {"user_id": user_id})

            connections = {r["connection_id"]: r["chunk_count"] for r in results}
            total_chunks = sum(connections.values())

            return {
                "total_chunks": total_chunks,
                "connections": connections,
                "dimension": self.DIMENSION
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {"total_chunks": 0, "connections": {}, "dimension": self.DIMENSION}

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk data or None
        """
        try:
            results = self.graph.query("""
                MATCH (c:ExternalChunk {id: $chunk_id})
                RETURN
                    c.id AS id,
                    c.user_id AS user_id,
                    c.document_id AS document_id,
                    c.connection_id AS connection_id,
                    c.content AS content,
                    c.source AS source,
                    c.source_name AS source_name,
                    c.source_url AS source_url,
                    c.section_title AS section_title,
                    c.chunk_index AS chunk_index,
                    c.is_code AS is_code,
                    c.is_table AS is_table
            """, {"chunk_id": chunk_id})

            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting chunk {chunk_id}: {e}")
            return None

    async def verify_index_exists(self) -> bool:
        """
        Verify the external vector index exists.

        Returns:
            True if index exists
        """
        try:
            results = self.graph.query("""
                SHOW INDEXES
                WHERE name = $index_name
            """, {"index_name": self.EXTERNAL_INDEX_NAME})

            exists = len(results) > 0
            if exists:
                self._index_initialized = True
            return exists
        except Exception as e:
            logger.error(f"Error checking index: {e}")
            return False


# Singleton instance
_external_vector_service: Optional[ExternalVectorService] = None


def get_external_vector_service() -> ExternalVectorService:
    """Get or create external vector service singleton"""
    global _external_vector_service
    if _external_vector_service is None:
        _external_vector_service = ExternalVectorService()
    return _external_vector_service


async def initialize_external_vector_service(graph=None) -> ExternalVectorService:
    """
    Initialize the external vector service with graph connection.

    Args:
        graph: Optional Neo4jGraph instance

    Returns:
        Initialized ExternalVectorService
    """
    service = get_external_vector_service()
    if graph:
        service.set_graph(graph)
    await service.init_vector_index()
    return service
