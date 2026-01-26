"""Document read tool for retrieving full document content."""
from neo4j import AsyncGraphDatabase

from .base import Tool
from config import config


class DocumentReadTool(Tool):
    """Read full document content from Neo4j."""

    name = "document_read"
    description = """Read the full content of a document.
Use this tool when:
- You found a relevant document via vector_search and need more details
- User asks for the complete content of a specific document
- You need to read a specific section or chunk of a document

Returns the full document content with all chunks assembled."""

    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "The document ID to read",
            },
            "chunk_id": {
                "type": "string",
                "description": "Optional: specific chunk ID to read instead of full document",
            },
            "include_metadata": {
                "type": "boolean",
                "description": "Whether to include document metadata",
                "default": True,
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
        chunk_id: str | None = None,
        include_metadata: bool = True,
    ) -> dict:
        """Read document or chunk content."""
        driver = await self._get_driver()

        if chunk_id:
            # Read specific chunk
            cypher = """
            MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk {id: $chunk_id})
            RETURN
                c.id AS chunk_id,
                c.content AS content,
                c.index AS chunk_index,
                c.page_number AS page_number,
                d.id AS doc_id,
                d.filename AS doc_title,
                d.type AS doc_type,
                d.indexed_at AS indexed_at
            """
            async with driver.session() as session:
                result = await session.run(
                    cypher,
                    {"doc_id": doc_id, "chunk_id": chunk_id},
                )
                record = await result.single()

            if not record:
                return {"error": f"Chunk '{chunk_id}' not found in document '{doc_id}'"}

            return {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "content": record["content"],
                "metadata": {
                    "doc_title": record["doc_title"],
                    "doc_type": record["doc_type"],
                    "chunk_index": record["chunk_index"],
                    "page_number": record["page_number"],
                    "indexed_at": str(record["indexed_at"]) if record["indexed_at"] else None,
                } if include_metadata else None,
            }

        # Read full document with all chunks
        cypher = """
        MATCH (d:Document {id: $doc_id})
        OPTIONAL MATCH (d)-[:CONTAINS]->(c:Chunk)
        WITH d, c
        ORDER BY c.index
        RETURN
            d.id AS doc_id,
            d.filename AS doc_title,
            d.type AS doc_type,
            d.chunk_count AS chunk_count,
            d.indexed_at AS indexed_at,
            collect({
                id: c.id,
                content: c.content,
                index: c.index,
                page_number: c.page_number
            }) AS chunks
        """

        async with driver.session() as session:
            result = await session.run(cypher, {"doc_id": doc_id})
            record = await result.single()

        if not record:
            return {"error": f"Document '{doc_id}' not found"}

        # Assemble full content from chunks
        chunks = [c for c in record["chunks"] if c.get("content")]
        chunks.sort(key=lambda x: x.get("index", 0) or 0)
        full_content = "\n\n".join(c["content"] for c in chunks if c.get("content"))

        response = {
            "doc_id": doc_id,
            "content": full_content if full_content else "(No content available)",
            "chunk_count": len(chunks),
        }

        if include_metadata:
            response["metadata"] = {
                "title": record["doc_title"],
                "type": record["doc_type"],
                "indexed_at": str(record["indexed_at"]) if record["indexed_at"] else None,
            }

        return response

    async def close(self):
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
