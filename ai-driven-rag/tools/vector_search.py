"""Vector search tool using Neo4j vector index."""
import httpx
from neo4j import AsyncGraphDatabase

from .base import Tool
from config import config


class VectorSearchTool(Tool):
    """Semantic search using Neo4j vector index."""

    name = "vector_search"
    description = """Search documents by semantic similarity.
Use this tool when:
- User asks about a topic and you need to find relevant documents
- User mentions keywords, error codes, or concepts
- You need background information to answer a question

Returns a list of relevant document chunks with similarity scores."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Can be a question, keyword, or concept.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
            "doc_type": {
                "type": "string",
                "description": "Optional document type filter (e.g., 'pdf', 'docx', 'manual')",
            },
        },
        "required": ["query"],
    }

    def __init__(self):
        self._driver = None

    async def _get_driver(self):
        if not self._driver:
            self._driver = AsyncGraphDatabase.driver(
                config.neo4j_uri,
                auth=(config.neo4j_user, config.neo4j_password),
            )
        return self._driver

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector for text."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{config.embedding_api_url}/embeddings",
                json={
                    "input": text,
                    "model": config.embedding_model,
                    "input_type": "query",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> dict:
        """Execute vector search."""
        # Get query embedding
        embedding = await self._get_embedding(query)

        # Build Cypher query - matches actual Neo4j schema
        # Document -[:CONTAINS]-> Chunk
        type_filter = ""
        if doc_type:
            type_filter = "AND d.type = $doc_type"

        cypher = f"""
        CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
        YIELD node AS chunk, score
        MATCH (d:Document)-[:CONTAINS]->(chunk)
        WHERE score >= 0.3 {type_filter}
        RETURN
            chunk.id AS chunk_id,
            chunk.content AS content,
            chunk.index AS chunk_index,
            chunk.page_number AS page_number,
            d.id AS doc_id,
            d.filename AS doc_title,
            d.type AS doc_type,
            score
        ORDER BY score DESC
        """

        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                cypher,
                {
                    "index_name": config.vector_index_name,
                    "top_k": top_k,
                    "embedding": embedding,
                    "doc_type": doc_type,
                },
            )
            records = await result.data()

        return {
            "query": query,
            "results": [
                {
                    "chunk_id": r["chunk_id"],
                    "content": r["content"][:500] + "..." if len(r.get("content", "")) > 500 else r.get("content", ""),
                    "doc_id": r["doc_id"],
                    "doc_title": r["doc_title"],
                    "doc_type": r["doc_type"],
                    "page_number": r["page_number"],
                    "score": round(r["score"], 4),
                }
                for r in records
            ],
            "total": len(records),
        }

    async def close(self):
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
