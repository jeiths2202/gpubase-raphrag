"""Keyword search tool using Neo4j full-text search."""
from neo4j import AsyncGraphDatabase

from .base import Tool
from config import config


class KeywordSearchTool(Tool):
    """Exact keyword/text search in document content."""

    name = "keyword_search"
    description = """Search for exact keywords or text patterns in documents.
Use this tool when:
- User asks about specific error codes (e.g., -5212, E001)
- User mentions exact product names, function names, or identifiers
- Vector search didn't find relevant results for specific terms
- You need to find exact string matches

This is better than vector_search for finding specific codes or identifiers."""

    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "The exact keyword or text to search for (e.g., '-5212', 'DATASET_NOT_FOUND')",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["keyword"],
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

    async def execute(
        self,
        keyword: str,
        top_k: int = 5,
    ) -> dict:
        """Execute keyword search."""
        # Use CONTAINS for exact substring matching
        cypher = """
        MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
        WHERE c.content CONTAINS $keyword
        RETURN
            c.id AS chunk_id,
            c.content AS content,
            c.index AS chunk_index,
            c.page_number AS page_number,
            d.id AS doc_id,
            d.filename AS doc_title,
            d.type AS doc_type
        LIMIT $top_k
        """

        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                cypher,
                {"keyword": keyword, "top_k": top_k},
            )
            records = await result.data()

        return {
            "keyword": keyword,
            "results": [
                {
                    "chunk_id": r["chunk_id"],
                    "content": r["content"][:800] if r.get("content") else "",
                    "doc_id": r["doc_id"],
                    "doc_title": r["doc_title"],
                    "doc_type": r["doc_type"],
                    "page_number": r["page_number"],
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
