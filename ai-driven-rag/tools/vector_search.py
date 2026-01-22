"""Vector search tool using Neo4j vector index."""
import httpx
from neo4j import AsyncGraphDatabase

from .base import Tool
from config import config


class VectorSearchTool(Tool):
    """Semantic search using Neo4j vector index."""

    name = "vector_search"
    description = """Search documents and web pages by semantic similarity.
Use this tool when:
- User asks about a topic and you need to find relevant information
- User asks general questions about concepts or procedures
- You need background information to answer a question

Supports searching:
- source="document": Only uploaded documents (PDF, DOCX, etc.)
- source="web": Only web pages
- source="all": Both documents and web pages (default)

Returns a list of relevant chunks with similarity scores."""

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
            "source": {
                "type": "string",
                "description": "Source to search: 'document', 'web', or 'all' (default: 'all')",
                "enum": ["document", "web", "all"],
                "default": "all",
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

    async def _search_documents(self, embedding: list[float], top_k: int) -> list[dict]:
        """Search document chunks."""
        cypher = """
        CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
        YIELD node AS chunk, score
        MATCH (d:Document)-[:CONTAINS]->(chunk)
        WHERE score >= 0.3
        RETURN
            chunk.id AS chunk_id,
            chunk.content AS content,
            chunk.index AS chunk_index,
            chunk.page_number AS page_number,
            d.id AS doc_id,
            d.filename AS title,
            'document' AS source_type,
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
                },
            )
            return await result.data()

    async def _search_web(self, embedding: list[float], top_k: int) -> list[dict]:
        """Search web page chunks."""
        cypher = """
        CALL db.index.vector.queryNodes('external_chunk_embedding', $top_k, $embedding)
        YIELD node AS chunk, score
        WHERE score >= 0.3
        RETURN
            chunk.id AS chunk_id,
            chunk.content AS content,
            0 AS chunk_index,
            0 AS page_number,
            chunk.document_id AS doc_id,
            chunk.source_name AS title,
            'web' AS source_type,
            score
        ORDER BY score DESC
        """
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                cypher,
                {
                    "top_k": top_k,
                    "embedding": embedding,
                },
            )
            return await result.data()

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        source: str = "all",
    ) -> dict:
        """Execute vector search."""
        embedding = await self._get_embedding(query)

        results = []

        if source in ("document", "all"):
            doc_results = await self._search_documents(embedding, top_k)
            results.extend(doc_results)

        if source in ("web", "all"):
            web_results = await self._search_web(embedding, top_k)
            results.extend(web_results)

        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

        return {
            "query": query,
            "source_filter": source,
            "results": [
                {
                    "chunk_id": r["chunk_id"],
                    "content": r["content"][:500] + "..." if len(r.get("content", "")) > 500 else r.get("content", ""),
                    "doc_id": r["doc_id"],
                    "title": r["title"],
                    "source_type": r["source_type"],
                    "page_number": r["page_number"],
                    "score": round(r["score"], 4),
                }
                for r in results
            ],
            "total": len(results),
        }

    async def close(self):
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
