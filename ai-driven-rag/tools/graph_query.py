"""Graph query tool using Neo4j relationships."""
from neo4j import AsyncGraphDatabase

from .base import Tool
from config import config


class GraphQueryTool(Tool):
    """Query document relationships and structure in Neo4j."""

    name = "graph_query"
    description = """Query document relationships and structure.
Use this tool when:
- User asks about relationships between documents or concepts
- User wants to find related documents to a known document
- User asks about document hierarchy or structure
- You need to explore connections between entities

Returns document relationships and connected information."""

    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Document ID to find relationships for",
            },
            "relationship_type": {
                "type": "string",
                "description": "Type of relationship to query",
                "enum": ["CONTAINS", "MENTIONS", "HAS_CONCEPT", "ALL"],
                "default": "ALL",
            },
            "depth": {
                "type": "integer",
                "description": "How many relationship hops to traverse (1-3)",
                "default": 1,
                "minimum": 1,
                "maximum": 3,
            },
        },
        "required": ["doc_id"],
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
        doc_id: str,
        relationship_type: str = "ALL",
        depth: int = 1,
    ) -> dict:
        """Execute graph query."""
        # Build relationship pattern
        if relationship_type == "ALL":
            rel_pattern = f"[r*1..{depth}]"
        else:
            rel_pattern = f"[r:{relationship_type}*1..{depth}]"

        cypher = f"""
        MATCH (d:Document {{id: $doc_id}})
        OPTIONAL MATCH (d)-{rel_pattern}-(related)
        WHERE related:Document OR related:Chunk OR related:Entity OR related:Concept
        WITH d, related
        RETURN
            d.id AS source_id,
            d.filename AS source_title,
            d.type AS source_type,
            collect(DISTINCT {{
                id: related.id,
                title: COALESCE(related.filename, related.content, related.name),
                type: labels(related)[0]
            }})[0..20] AS related_nodes
        """

        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(cypher, {"doc_id": doc_id})
            record = await result.single()

        if not record:
            return {
                "doc_id": doc_id,
                "error": "Document not found",
                "related_nodes": [],
            }

        return {
            "doc_id": doc_id,
            "source": {
                "id": record["source_id"],
                "title": record["source_title"],
                "type": record["source_type"],
            },
            "related_nodes": [
                node for node in record["related_nodes"]
                if node.get("id")
            ],
            "relationship_type": relationship_type,
            "depth": depth,
        }

    async def close(self):
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
