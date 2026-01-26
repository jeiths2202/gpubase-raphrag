"""
Web Source Indexer Service
Integrates web content with Neo4j storage and embedding pipeline
"""
import asyncio
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
import sys
import os

# Add src directory to path for importing existing modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from langchain_neo4j import Neo4jGraph
    from config import config
    from embeddings import NeMoEmbeddingService
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class WebSourceIndexer:
    """
    Service for indexing web source content into Neo4j with embeddings.
    Integrates with the existing RAG pipeline.
    """

    def __init__(self):
        self._graph = None
        self._embedding_service = None
        self._initialized = False

    def _ensure_initialized(self):
        """Initialize Neo4j and embedding connections"""
        if self._initialized:
            return

        if not NEO4J_AVAILABLE:
            print("[WebSourceIndexer] Neo4j dependencies not available")
            return

        try:
            self._graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )
            self._embedding_service = NeMoEmbeddingService()
            self._initialized = True
            print("[WebSourceIndexer] Initialized successfully")
        except Exception as e:
            print(f"[WebSourceIndexer] Initialization failed: {e}")

    async def index_web_source(
        self,
        web_source_id: str,
        url: str,
        title: str,
        content: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Index a web source and its chunks into Neo4j with embeddings.

        Args:
            web_source_id: Unique ID for the web source
            url: Source URL
            title: Page title
            content: Full extracted content
            chunks: List of content chunks with id, content, index
            metadata: Additional metadata

        Returns:
            True if indexing was successful
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_index_web_source,
            web_source_id, url, title, content, chunks, metadata
        )

    def _sync_index_web_source(
        self,
        web_source_id: str,
        url: str,
        title: str,
        content: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Synchronous indexing implementation"""
        self._ensure_initialized()

        if not self._initialized or not self._graph:
            print("[WebSourceIndexer] Not initialized, skipping indexing")
            return False

        try:
            metadata = metadata or {}

            # Create WebSource document node
            self._graph.query(
                """
                MERGE (ws:WebSource {id: $ws_id})
                SET ws.url = $url,
                    ws.title = $title,
                    ws.domain = $domain,
                    ws.content_preview = $content_preview,
                    ws.word_count = $word_count,
                    ws.indexed_at = datetime(),
                    ws.source_type = 'web'
                """,
                {
                    "ws_id": web_source_id,
                    "url": url,
                    "title": title,
                    "domain": metadata.get("domain", ""),
                    "content_preview": content[:500] if content else "",
                    "word_count": len(content.split()) if content else 0
                }
            )

            # Also create a Document node for compatibility with existing RAG
            doc_id = f"doc_{web_source_id}"
            self._graph.query(
                """
                MERGE (d:Document {id: $doc_id})
                SET d.type = 'web',
                    d.source_url = $url,
                    d.title = $title,
                    d.indexed_at = datetime()
                WITH d
                MATCH (ws:WebSource {id: $ws_id})
                MERGE (ws)-[:HAS_DOCUMENT]->(d)
                """,
                {
                    "doc_id": doc_id,
                    "ws_id": web_source_id,
                    "url": url,
                    "title": title
                }
            )

            # Process chunks with embeddings
            chunk_texts = [c.get("content", "") for c in chunks]

            # Generate embeddings in batches
            embeddings = []
            if self._embedding_service and chunk_texts:
                try:
                    embeddings = self._embedding_service.embed_batch(
                        chunk_texts,
                        input_type="passage"
                    )
                except Exception as e:
                    print(f"[WebSourceIndexer] Embedding generation failed: {e}")
                    embeddings = []

            # Index chunks
            for i, chunk in enumerate(chunks):
                chunk_id = chunk.get("id", f"chunk_{uuid.uuid4().hex[:8]}")
                chunk_content = chunk.get("content", "")

                if i < len(embeddings):
                    # Store chunk with embedding
                    self._graph.query(
                        """
                        MERGE (c:Chunk {id: $chunk_id})
                        SET c.content = $content,
                            c.index = $index,
                            c.embedding = $embedding,
                            c.source_url = $url,
                            c.source_type = 'web'
                        WITH c
                        MATCH (d:Document {id: $doc_id})
                        MERGE (d)-[:CONTAINS]->(c)
                        """,
                        {
                            "chunk_id": chunk_id,
                            "content": chunk_content,
                            "index": i,
                            "embedding": embeddings[i],
                            "url": url,
                            "doc_id": doc_id
                        }
                    )
                else:
                    # Store chunk without embedding
                    self._graph.query(
                        """
                        MERGE (c:Chunk {id: $chunk_id})
                        SET c.content = $content,
                            c.index = $index,
                            c.source_url = $url,
                            c.source_type = 'web'
                        WITH c
                        MATCH (d:Document {id: $doc_id})
                        MERGE (d)-[:CONTAINS]->(c)
                        """,
                        {
                            "chunk_id": chunk_id,
                            "content": chunk_content,
                            "index": i,
                            "url": url,
                            "doc_id": doc_id
                        }
                    )

                # Extract and link entities (basic NER)
                entities = self._extract_entities(chunk_content)
                for entity in entities[:10]:  # Limit to 10 entities per chunk
                    self._graph.query(
                        """
                        MERGE (e:Entity {name: $entity_name})
                        WITH e
                        MATCH (c:Chunk {id: $chunk_id})
                        MERGE (c)-[:MENTIONS]->(e)
                        """,
                        {"entity_name": entity, "chunk_id": chunk_id}
                    )

            print(f"[WebSourceIndexer] Indexed {len(chunks)} chunks for {url}")
            return True

        except Exception as e:
            print(f"[WebSourceIndexer] Indexing failed: {e}")
            return False

    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract named entities from text.
        Basic implementation - can be enhanced with NER models.
        """
        import re

        entities = set()

        # Extract capitalized phrases (potential proper nouns)
        capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
        entities.update(capitalized[:5])

        # Extract technical terms (camelCase, PascalCase, UPPERCASE)
        tech_terms = re.findall(r'\b([A-Z][a-z]+[A-Z][a-zA-Z]*|[A-Z]{2,})\b', text)
        entities.update(tech_terms[:5])

        # Extract code-like patterns
        code_patterns = re.findall(r'\b([a-z]+_[a-z_]+|[a-z]+\.[a-z]+)\b', text)
        entities.update(code_patterns[:5])

        return list(entities)

    async def delete_web_source_index(self, web_source_id: str) -> bool:
        """Delete a web source and its chunks from Neo4j"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_delete_web_source_index,
            web_source_id
        )

    def _sync_delete_web_source_index(self, web_source_id: str) -> bool:
        """Synchronous deletion implementation"""
        self._ensure_initialized()

        if not self._initialized or not self._graph:
            return False

        try:
            doc_id = f"doc_{web_source_id}"

            # Delete chunks
            self._graph.query(
                """
                MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)
                DETACH DELETE c
                """,
                {"doc_id": doc_id}
            )

            # Delete document
            self._graph.query(
                """
                MATCH (d:Document {id: $doc_id})
                DETACH DELETE d
                """,
                {"doc_id": doc_id}
            )

            # Delete web source
            self._graph.query(
                """
                MATCH (ws:WebSource {id: $ws_id})
                DETACH DELETE ws
                """,
                {"ws_id": web_source_id}
            )

            print(f"[WebSourceIndexer] Deleted index for {web_source_id}")
            return True

        except Exception as e:
            print(f"[WebSourceIndexer] Deletion failed: {e}")
            return False

    async def get_indexed_stats(self) -> Dict[str, int]:
        """Get statistics about indexed web sources"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_get_indexed_stats
        )

    def _sync_get_indexed_stats(self) -> Dict[str, int]:
        """Synchronous stats retrieval"""
        self._ensure_initialized()

        if not self._initialized or not self._graph:
            return {"web_sources": 0, "chunks": 0, "entities": 0}

        try:
            result = self._graph.query(
                """
                MATCH (ws:WebSource)
                WITH count(ws) as ws_count
                MATCH (c:Chunk {source_type: 'web'})
                WITH ws_count, count(c) as chunk_count
                MATCH (c:Chunk {source_type: 'web'})-[:MENTIONS]->(e:Entity)
                RETURN ws_count, chunk_count, count(DISTINCT e) as entity_count
                """
            )

            if result:
                return {
                    "web_sources": result[0].get("ws_count", 0),
                    "chunks": result[0].get("chunk_count", 0),
                    "entities": result[0].get("entity_count", 0)
                }
            return {"web_sources": 0, "chunks": 0, "entities": 0}

        except Exception:
            return {"web_sources": 0, "chunks": 0, "entities": 0}


# Singleton instance
_web_source_indexer: Optional[WebSourceIndexer] = None


def get_web_source_indexer() -> WebSourceIndexer:
    """Get or create web source indexer instance"""
    global _web_source_indexer
    if _web_source_indexer is None:
        _web_source_indexer = WebSourceIndexer()
    return _web_source_indexer
