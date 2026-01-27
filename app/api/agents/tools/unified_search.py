"""
Unified Search Tool
Combines Neo4j vector search accuracy with PostgreSQL structure metadata.

Architecture:
    User Query
        │
        ▼
    PREPROCESSING
     - _validate_query() (LLM corruption recovery)
     - _extract_error_codes() (error code detection)
     - LLM Query Expansion (semantic expansion)
        │
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
    Neo4j Vector      Postgres Keyword    CLIP Image
    (Primary)         (Secondary)         (Optional)
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                    RRF Score Fusion
                           ▼
                  Structure Enrichment
                   (sections, tables)
                           ▼
                      Final Results
"""
import logging
import os
import re
from typing import Dict, Any, Optional, List, Tuple, Set
import json

from .base import BaseTool
from ..types import ToolResult, AgentContext
from .adaptive_search import _validate_query, _extract_error_codes

logger = logging.getLogger(__name__)

# Default top_k based on LLM context size
_USE_LARGE_CONTEXT = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"
DEFAULT_TOP_K = 5 if _USE_LARGE_CONTEXT else 3


class UnifiedSearchTool(BaseTool):
    """
    Unified Search Tool combining Neo4j accuracy with PostgreSQL structure.

    Features:
    - Semantic search via Neo4j (verified asymmetric embeddings)
    - RRF hybrid ranking (semantic + keyword)
    - PDF structure (sections, tables, images)
    - CLIP text-to-image search
    - Error code detection and boosting
    """

    def __init__(self, rag_service=None):
        super().__init__(
            name="unified_search",
            description="""PRIMARY search tool - combines Neo4j accuracy with PostgreSQL structure.
Use this FIRST for any knowledge base query. Features:
- Semantic search via Neo4j (verified asymmetric embeddings)
- RRF hybrid ranking (semantic + keyword)
- PDF structure preservation (sections, tables, images)
- CLIP text-to-image search
- Error code detection and boosting
Returns relevant document chunks with full context and source information."""
        )
        self._rag_service = rag_service
        self._adaptive_service = None
        self._embedding_service = None
        self._clip_service = None

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query - MUST be the EXACT user question without modification"
                },
                "top_k": {
                    "type": "integer",
                    "description": f"Number of results to return (default: {DEFAULT_TOP_K})",
                    "default": DEFAULT_TOP_K
                },
                "doc_filter": {
                    "type": "string",
                    "description": "Optional: ONLY use if the user explicitly mentions a specific document name. Use the EXACT filename or product name from the user query. Do NOT invent or guess document names from search results. Leave empty if unsure."
                },
                "include_images": {
                    "type": "boolean",
                    "description": "Include CLIP-based image search (default: true)",
                    "default": True
                },
                "include_tables": {
                    "type": "boolean",
                    "description": "Auto-include related tables (default: true)",
                    "default": True
                },
                "search_mode": {
                    "type": "string",
                    "description": "Search mode: hybrid, vector_only, or keyword_only",
                    "enum": ["hybrid", "vector_only", "keyword_only"],
                    "default": "hybrid"
                }
            },
            "required": ["query"]
        }

    @property
    def rag_service(self):
        """Lazy load RAG service for Neo4j vector search"""
        if self._rag_service is None:
            logger.debug("Lazy loading RAG service...")
            try:
                from ...core.deps import get_rag_service
                self._rag_service = get_rag_service()
                logger.debug(f"RAG service loaded: {self._rag_service is not None}")
            except Exception as e:
                logger.error(f"Failed to get RAG service: {e}")
        return self._rag_service

    async def _get_adaptive_service(self):
        """Lazy load adaptive service for PostgreSQL operations"""
        if self._adaptive_service is None:
            try:
                from ...core.deps import get_adaptive_embedding_service
                self._adaptive_service = await get_adaptive_embedding_service()
            except Exception as e:
                logger.error(f"Failed to get adaptive service: {e}")
        return self._adaptive_service

    async def _get_embedding_service(self):
        """Lazy load embedding service"""
        if self._embedding_service is None:
            try:
                from ...services.multimodal_embedding import TextEmbeddingService
                self._embedding_service = TextEmbeddingService()
            except Exception as e:
                logger.error(f"Failed to get embedding service: {e}")
        return self._embedding_service

    async def _get_clip_service(self):
        """Lazy load CLIP embedding service for text-to-image search"""
        if self._clip_service is None:
            try:
                from ...services.clip_embedding_service import get_clip_embedding_service
                self._clip_service = get_clip_embedding_service()
            except Exception as e:
                logger.error(f"Failed to get CLIP service: {e}")
        return self._clip_service

    async def _execute_pg_query(self, query: str) -> List[Dict]:
        """Execute a raw SQL query on PostgreSQL"""
        try:
            import asyncpg
            from ...core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"PostgreSQL query failed: {e}")
            return []

    async def _neo4j_vector_search(
        self,
        query: str,
        top_k: int,
        language: str,
        context: AgentContext
    ) -> List[Dict[str, Any]]:
        """Execute vector search via Neo4j using RAGService"""
        logger.debug(f"Neo4j vector search: rag_service={self.rag_service is not None}")
        try:
            if self.rag_service is None:
                logger.error("RAG service is None - cannot execute Neo4j search")
                return []
            result = await self.rag_service.query(
                question=query,
                strategy="hybrid",  # Use hybrid for glossary-enhanced search
                language=language,
                top_k=top_k * 2,  # Fetch more for fusion
                session_id=context.session_id,
                user_id=context.user_id
            )

            sources = result.get("sources", [])
            neo4j_results = []

            for i, source in enumerate(sources):
                neo4j_results.append({
                    "chunk_id": source.get("doc_id", f"neo4j_{i}"),
                    "content": source.get("content", ""),
                    "score": source.get("score", 0.0),
                    "source": source.get("doc_name") or source.get("source", "Unknown"),
                    "doc_id": source.get("doc_id", ""),
                    "page_number": source.get("page_number"),
                    "rank": i + 1,
                    "origin": "neo4j",
                    # Web source specific fields
                    "source_type": source.get("source_type", "document"),
                    "source_url": source.get("source_url", "")
                })

            logger.info(f"Neo4j returned {len(neo4j_results)} results")
            return neo4j_results

        except Exception as e:
            logger.error(f"Neo4j vector search error: {e}", exc_info=True)
            return []

    async def _postgres_keyword_search(
        self,
        query: str,
        top_k: int,
        doc_filter: Optional[str] = None,
        error_codes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Execute keyword search via PostgreSQL ts_rank"""
        try:
            # Build search terms for ts_query
            # Escape special characters and join with OR
            terms = query.split()
            ts_terms = " | ".join([t.replace("'", "''") for t in terms if t])

            # Build error code boost condition
            error_boost_sql = ""
            if error_codes:
                error_patterns = " OR ".join([
                    f"content ILIKE '%{code}%'" for code in error_codes
                ])
                error_boost_sql = f"""
                    CASE WHEN ({error_patterns}) THEN 1.5 ELSE 1.0 END as error_boost,
                """

            # Build document filter - support both doc_id and document name patterns
            doc_filter_sql = ""
            if doc_filter:
                # Sanitize input to prevent SQL injection
                safe_filter = doc_filter.replace("'", "''")
                if doc_filter.startswith("doc_"):
                    # Exact document ID match
                    doc_filter_sql = f"AND pdf_id = '{safe_filter}'"
                else:
                    # Fuzzy match against document name (for category/product names)
                    # Use 'documents' table (id column) instead of non-existent 'pdf_documents'
                    doc_filter_sql = f"AND pdf_id IN (SELECT id FROM documents WHERE filename ILIKE '%{safe_filter}%' OR original_name ILIKE '%{safe_filter}%')"
                    logger.info(f"[UnifiedSearch] doc_filter '{doc_filter}' is not a doc_id, using fuzzy filename match")

            # PostgreSQL full-text search with ts_rank
            sql = f"""
                SELECT
                    chunk_id,
                    pdf_id,
                    content,
                    chunk_type,
                    page_start,
                    page_end,
                    section_title,
                    section_path,
                    relations,
                    {error_boost_sql}
                    ts_rank(
                        to_tsvector('simple', content),
                        plainto_tsquery('simple', '{ts_terms}')
                    ) as keyword_score
                FROM adaptive_pdf_chunks
                WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', '{ts_terms}')
                {doc_filter_sql}
                ORDER BY keyword_score DESC
                LIMIT {top_k * 2}
            """

            rows = await self._execute_pg_query(sql)

            postgres_results = []
            for i, row in enumerate(rows):
                score = row.get("keyword_score", 0)
                error_boost = row.get("error_boost", 1.0)
                final_score = score * (error_boost if error_boost else 1.0)

                postgres_results.append({
                    "chunk_id": row.get("chunk_id"),
                    "content": row.get("content", ""),
                    "score": final_score,
                    "source": row.get("pdf_id", "Unknown"),
                    "doc_id": row.get("pdf_id", ""),
                    "page_start": row.get("page_start"),
                    "page_end": row.get("page_end"),
                    "section_title": row.get("section_title"),
                    "section_path": row.get("section_path"),
                    "chunk_type": row.get("chunk_type", "TEXT"),
                    "relations": row.get("relations", {}),
                    "rank": i + 1,
                    "origin": "postgres",
                    "error_boosted": error_boost > 1.0 if error_boost else False
                })

            logger.info(f"[UnifiedSearch] PostgreSQL returned {len(postgres_results)} results")
            return postgres_results

        except Exception as e:
            logger.error(f"PostgreSQL keyword search error: {e}")
            return []

    async def _exact_phrase_search(
        self,
        exact_phrases: List[str],
        top_k: int = 10,
        web_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks containing exact phrases in Neo4j.
        This is a direct string match search to complement vector search.

        Args:
            exact_phrases: List of exact phrases to search for
            top_k: Maximum number of results
            web_only: If True, only search web sources (for @ prefix mode)
        """
        if not exact_phrases:
            return []

        try:
            from neo4j import GraphDatabase

            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")

            driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password)
            )

            results = []
            with driver.session() as session:
                for phrase in exact_phrases:
                    # Search for chunks containing the exact phrase (case-insensitive)
                    phrase_lower = phrase.lower()

                    # Build query based on web_only filter
                    if web_only:
                        # Only search web source chunks
                        query_result = session.run("""
                            MATCH (c:Chunk)
                            WHERE toLower(c.content) CONTAINS $phrase
                              AND c.source_type = 'web'
                            OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                            RETURN c.id AS chunk_id,
                                   c.content AS content,
                                   c.source_type AS source_type,
                                   c.source_url AS source_url,
                                   c.index AS chunk_index,
                                   d.id AS doc_id,
                                   d.title AS doc_title
                            LIMIT $limit
                        """, phrase=phrase_lower, limit=top_k)
                    else:
                        # Search all chunks
                        query_result = session.run("""
                            MATCH (c:Chunk)
                            WHERE toLower(c.content) CONTAINS $phrase
                            OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                            RETURN c.id AS chunk_id,
                                   c.content AS content,
                                   c.source_type AS source_type,
                                   c.source_url AS source_url,
                                   c.index AS chunk_index,
                                   d.id AS doc_id,
                                   d.title AS doc_title
                            LIMIT $limit
                        """, phrase=phrase_lower, limit=top_k)

                    for record in query_result:
                        content = record["content"] or ""
                        source_type = record["source_type"] or "document"
                        doc_id = record["doc_id"] or record["chunk_id"]

                        results.append({
                            "chunk_id": record["chunk_id"],
                            "content": content,
                            "score": 1.0,  # High score for exact match
                            "source": doc_id,
                            "doc_id": doc_id,
                            "document_name": record["doc_title"] or doc_id,
                            "source_type": source_type,
                            "source_url": record["source_url"] or "",
                            "rank": len(results) + 1,
                            "origin": "exact_phrase",
                            "exact_phrase_match": True,
                            "matched_phrases": [phrase]
                        })

            driver.close()

            logger.info(f"Exact phrase search found {len(results)} results for phrases: {exact_phrases}")
            return results

        except Exception as e:
            logger.error(f"Exact phrase search error: {e}")
            return []

    async def _fetch_linked_chunks(
        self,
        results: List[Dict[str, Any]],
        num_following: int = 2,
        web_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch subsequent chunks for each result to include related content.
        This helps include tables/lists that follow headers.

        Args:
            results: Search results to expand
            num_following: Number of subsequent chunks to fetch (default: 2)
            web_only: If True, only link web source chunks

        Returns:
            Expanded results with linked chunks appended
        """
        if not results or num_following <= 0:
            return results

        try:
            from neo4j import GraphDatabase

            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")

            driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password)
            )

            linked_chunks = []
            seen_chunk_ids = set()

            # Track original chunk IDs to avoid duplicates
            for r in results:
                chunk_id = r.get("chunk_id")
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)

            with driver.session() as session:
                for result in results:
                    chunk_id = result.get("chunk_id")
                    source_type = result.get("source_type", "document")

                    # Skip if web_only and this isn't a web source
                    if web_only and source_type != "web":
                        continue

                    if not chunk_id:
                        continue

                    # First, get the index of this chunk
                    index_result = session.run("""
                        MATCH (c:Chunk)
                        WHERE c.id = $chunk_id
                        RETURN c.index AS chunk_index, c.source_type AS source_type
                    """, chunk_id=chunk_id)

                    index_record = index_result.single()
                    if not index_record or index_record["chunk_index"] is None:
                        continue

                    current_index = index_record["chunk_index"]
                    chunk_source_type = index_record["source_type"] or "document"

                    # Fetch subsequent chunks with consecutive indexes
                    # For web sources, we fetch chunks with indexes current+1 to current+num_following
                    if chunk_source_type == "web":
                        following_query = """
                            MATCH (c:Chunk)
                            WHERE c.source_type = 'web'
                              AND c.index > $current_index
                              AND c.index <= $max_index
                            RETURN c.id AS chunk_id,
                                   c.content AS content,
                                   c.source_type AS source_type,
                                   c.source_url AS source_url,
                                   c.index AS chunk_index
                            ORDER BY c.index ASC
                        """
                    else:
                        following_query = """
                            MATCH (c:Chunk)
                            WHERE c.index > $current_index
                              AND c.index <= $max_index
                            OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                            RETURN c.id AS chunk_id,
                                   c.content AS content,
                                   c.source_type AS source_type,
                                   c.source_url AS source_url,
                                   c.index AS chunk_index,
                                   d.id AS doc_id,
                                   d.title AS doc_title
                            ORDER BY c.index ASC
                        """

                    following_result = session.run(
                        following_query,
                        current_index=current_index,
                        max_index=current_index + num_following
                    )

                    for record in following_result:
                        linked_chunk_id = record["chunk_id"]
                        if linked_chunk_id in seen_chunk_ids:
                            continue  # Skip duplicates

                        seen_chunk_ids.add(linked_chunk_id)
                        content = record["content"] or ""

                        # Create linked chunk result
                        linked_chunk = {
                            "chunk_id": linked_chunk_id,
                            "content": content,
                            "score": result.get("score", 0.5) * 0.8,  # Slightly lower score
                            "source": result.get("source", ""),
                            "doc_id": result.get("doc_id", ""),
                            "document_name": result.get("document_name", ""),
                            "source_type": record["source_type"] or "document",
                            "source_url": record["source_url"] or result.get("source_url", ""),
                            "rank": result.get("rank", 999) + record["chunk_index"] - current_index,
                            "origin": "linked_chunk",
                            "linked_from": chunk_id,
                            "chunk_index": record["chunk_index"],
                            "is_linked_chunk": True
                        }
                        linked_chunks.append(linked_chunk)

            driver.close()

            if linked_chunks:
                logger.debug(f"Fetched {len(linked_chunks)} linked chunks")

            # Append linked chunks to results (they will be sorted by RRF later)
            return results + linked_chunks

        except Exception as e:
            logger.error(f"Chunk linking error: {e}")
            return results

    async def _clip_image_search(
        self,
        query: str,
        relevant_pages: Set[int],
        doc_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Execute CLIP-based text-to-image search"""
        clip_service = await self._get_clip_service()
        if not clip_service:
            return []

        try:
            from ...core.deps import get_postgres_pool
            from ...infrastructure.postgres.image_repository import PostgresImageRepository

            # Generate CLIP embedding for query text
            clip_query_embedding = await clip_service.embed_text(query)
            if not clip_query_embedding or sum(1 for v in clip_query_embedding if v != 0.0) == 0:
                return []

            pool = await get_postgres_pool()
            image_repo = PostgresImageRepository(pool)

            # Search similar images by CLIP embedding
            # Use higher threshold (0.25) for better relevance filtering
            min_sim = 0.25
            clip_results = await image_repo.search_by_clip_embedding(
                query_embedding=clip_query_embedding,
                document_id=doc_id,
                limit=limit * 3,
                min_similarity=min_sim
            )

            # Filter by relevant pages - REQUIRE page match for technical queries
            clip_images = []
            seen_pages = set()

            for img in clip_results:
                similarity = img.get('similarity', 0)
                if similarity < min_sim:
                    continue

                page_num = img.get('page_number')
                # STRICT: Only include images from pages that matched text chunks
                # This prevents unrelated images from appearing
                if not relevant_pages or page_num not in relevant_pages:
                    continue

                if page_num not in seen_pages:
                    seen_pages.add(page_num)
                    clip_images.append({
                        "image_id": img.get("image_id"),
                        "document_id": img.get("document_id"),
                        "page_number": page_num,
                        "similarity": img.get("similarity", 0),
                        "url": f"/api/v1/documents/adaptive/images/{img['image_id']}/raw"
                    })

                if len(clip_images) >= limit:
                    break

            logger.info(f"[UnifiedSearch] CLIP returned {len(clip_images)} images")
            return clip_images

        except Exception as e:
            logger.error(f"CLIP image search error: {e}")
            return []

    def _rrf_fusion(
        self,
        neo4j_results: List[Dict],
        postgres_results: List[Dict],
        error_codes: List[str],
        k: int = 60,
        prioritize_web: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF) to combine search results.

        RRF score = 1/(k + rank_v) + 1/(k + rank_k) + error_boost
        Where k=60 is a constant that prevents extreme rankings.

        Args:
            prioritize_web: If True (triggered by @ prefix), heavily boost web sources
        """
        # Create lookup maps by chunk_id or content hash
        all_chunks = {}

        # Process Neo4j results
        for result in neo4j_results:
            key = result.get("chunk_id") or hash(result.get("content", "")[:200])
            all_chunks[key] = {
                **result,
                "neo4j_rank": result.get("rank", 999),
                "postgres_rank": 999,
                "rrf_score": 0.0
            }

        # Process PostgreSQL results
        for result in postgres_results:
            key = result.get("chunk_id") or hash(result.get("content", "")[:200])
            if key in all_chunks:
                # Update existing with postgres rank
                all_chunks[key]["postgres_rank"] = result.get("rank", 999)
                all_chunks[key]["postgres_data"] = result
            else:
                # Add new chunk from postgres
                all_chunks[key] = {
                    **result,
                    "neo4j_rank": 999,
                    "postgres_rank": result.get("rank", 999),
                    "rrf_score": 0.0
                }

        # Calculate RRF scores
        for key, chunk in all_chunks.items():
            neo4j_rank = chunk.get("neo4j_rank", 999)
            postgres_rank = chunk.get("postgres_rank", 999)

            # Base RRF score
            rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + postgres_rank)

            source_type = chunk.get("source_type", "")

            # @ prefix mode: heavily prioritize web sources
            if prioritize_web:
                if source_type == "web":
                    # Web sources get massive boost (3x multiplier + rank simulation)
                    simulated_postgres_rank = min(neo4j_rank, 3)  # Treat as top-3 in postgres
                    rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + simulated_postgres_rank)
                    rrf_score *= 3.0  # Triple the score for web sources
                    chunk["web_priority_boosted"] = True
                else:
                    # Non-web sources get penalized in @ mode
                    rrf_score *= 0.3
                    chunk["web_priority_penalized"] = True
            else:
                # Normal mode: moderate web source boosting for fairness
                # Web source boosting: if source only exists in Neo4j (no PostgreSQL match)
                # and has high vector rank, boost it to be competitive
                if source_type == "web" and postgres_rank == 999 and neo4j_rank <= 5:
                    # Simulate as if it had a postgres_rank of neo4j_rank + 2
                    simulated_postgres_rank = neo4j_rank + 2
                    rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + simulated_postgres_rank)
                    chunk["web_boosted"] = True

            # Error code boosting
            content = chunk.get("content", "")
            if error_codes and any(code in content for code in error_codes):
                rrf_score *= 1.5
                chunk["error_boosted"] = True

            chunk["rrf_score"] = rrf_score

        # Sort by RRF score
        sorted_chunks = sorted(
            all_chunks.values(),
            key=lambda x: x.get("rrf_score", 0),
            reverse=True
        )

        # @ prefix mode: filter to web sources only
        if prioritize_web:
            web_only_chunks = [c for c in sorted_chunks if c.get("source_type") == "web"]
            if web_only_chunks:
                logger.info(f"[UnifiedSearch] RRF fusion (web priority mode): returning {len(web_only_chunks)} web-only results")
                return web_only_chunks
            else:
                # No web sources found - return all with warning
                logger.warning(f"[UnifiedSearch] Web priority mode but no web sources found, returning {len(sorted_chunks)} general results")

        logger.info(f"[UnifiedSearch] RRF fusion produced {len(sorted_chunks)} unique results")
        return sorted_chunks

    def _apply_web_priority(self, results: List[Dict]) -> List[Dict]:
        """
        Apply web source priority for vector_only mode.
        Returns only web sources when @ prefix is used.
        """
        web_results = []

        for result in results:
            if result.get("source_type") == "web":
                result["web_priority_boosted"] = True
                web_results.append(result)

        if web_results:
            logger.info(f"[UnifiedSearch] Web priority: returning {len(web_results)} web-only results")
            return web_results
        else:
            # No web sources found - return all with warning
            logger.warning(f"[UnifiedSearch] Web priority mode but no web sources found, returning {len(results)} general results")
            return results

    def _apply_exact_phrase_priority(
        self,
        results: List[Dict],
        exact_phrases: List[str]
    ) -> List[Dict]:
        """
        Prioritize results containing exact phrases (quoted search).
        Results with exact matches are moved to the top with boosted scores.

        Args:
            results: Search results to reorder
            exact_phrases: List of exact phrases to match (from "quoted" parts of query)

        Returns:
            Reordered results with exact matches first
        """
        if not exact_phrases or not results:
            return results

        exact_match_results = []
        partial_match_results = []
        no_match_results = []

        for result in results:
            content = result.get("content", "").lower()

            # Check for exact phrase matches
            match_count = 0
            matched_phrases = []
            for phrase in exact_phrases:
                phrase_lower = phrase.lower()
                if phrase_lower in content:
                    match_count += 1
                    matched_phrases.append(phrase)

            if match_count == len(exact_phrases):
                # All phrases matched - highest priority
                result["exact_phrase_match"] = True
                result["matched_phrases"] = matched_phrases
                # Boost score significantly for exact matches
                original_score = result.get("rrf_score", result.get("score", 0.1))
                result["rrf_score"] = original_score * 5.0 + 1.0  # Major boost
                exact_match_results.append(result)
            elif match_count > 0:
                # Partial match - medium priority
                result["exact_phrase_partial"] = True
                result["matched_phrases"] = matched_phrases
                original_score = result.get("rrf_score", result.get("score", 0.1))
                result["rrf_score"] = original_score * 2.0 + 0.5  # Moderate boost
                partial_match_results.append(result)
            else:
                # No match - lowest priority
                no_match_results.append(result)

        # Sort each group by score
        exact_match_results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
        partial_match_results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
        no_match_results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)

        # Combine: exact matches first, then partial, then others
        combined = exact_match_results + partial_match_results + no_match_results

        logger.debug(
            f"Exact phrase priority: {len(exact_match_results)} exact, "
            f"{len(partial_match_results)} partial, {len(no_match_results)} no match"
        )

        return combined

    def _fix_markdown_table_separators(self, content: str) -> str:
        """Fix markdown tables missing separator line"""
        lines = content.split('\n')
        result_lines = []
        table_rows = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            is_table_row = stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 2
            is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', stripped)) if stripped else False

            if is_table_row or is_separator:
                if not in_table:
                    in_table = True
                table_rows.append(stripped)
            elif stripped == '' and in_table:
                continue
            else:
                if table_rows:
                    result_lines.extend(self._finalize_table(table_rows))
                    table_rows = []
                    in_table = False
                result_lines.append(line)

        if table_rows:
            result_lines.extend(self._finalize_table(table_rows))

        return '\n'.join(result_lines)

    def _finalize_table(self, rows: list) -> list:
        """Add separator after first row if missing"""
        if not rows:
            return rows

        result = [rows[0]]

        if len(rows) > 1:
            is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', rows[1]))
            if not is_separator:
                cols = len([c for c in rows[0].split('|') if c.strip()])
                separator = '|' + '|'.join([' --- ' for _ in range(cols)]) + '|'
                result.append(separator)

        result.extend(rows[1:])
        return result

    async def _enrich_with_structure(
        self,
        fused_results: List[Dict],
        clip_images: List[Dict],
        include_tables: bool = True,
        top_k: int = 5
    ) -> Tuple[List[Dict], Dict]:
        """
        Enrich results with PostgreSQL structure metadata.

        Adds:
        - Section hierarchy from adaptive_pdf_chunks
        - Related tables from same pages
        - CLIP images linked to chunks
        """
        enriched_results = []
        related_tables_by_page = {}

        # Collect page info for table lookup
        page_conditions = set()
        for result in fused_results[:top_k]:
            pdf_id = result.get("doc_id") or result.get("pdf_id")
            page_start = result.get("page_start") or result.get("page_number")
            page_end = result.get("page_end") or page_start

            if pdf_id and page_start:
                for p in range(page_start, (page_end or page_start) + 1):
                    page_conditions.add((pdf_id, p))

        # Fetch related tables if enabled
        if include_tables and page_conditions:
            try:
                conditions = " OR ".join([
                    f"(pdf_id = '{pid}' AND page_start = {page})"
                    for pid, page in page_conditions
                ])
                table_query = f"""
                    SELECT chunk_id, pdf_id, content, page_start, section_title
                    FROM adaptive_pdf_chunks
                    WHERE chunk_type = 'TABLE_CHUNK' AND ({conditions})
                """
                table_results = await self._execute_pg_query(table_query)

                for tr in table_results:
                    key = (tr['pdf_id'], tr['page_start'])
                    if key not in related_tables_by_page:
                        related_tables_by_page[key] = []
                    fixed_markdown = self._fix_markdown_table_separators(tr['content'])
                    related_tables_by_page[key].append({
                        "markdown": fixed_markdown,
                        "chunk_id": tr['chunk_id'],
                        "section_title": tr.get('section_title')
                    })

                logger.info(f"[UnifiedSearch] Found {sum(len(v) for v in related_tables_by_page.values())} related tables")
            except Exception as e:
                logger.error(f"Error fetching related tables: {e}")

        # Build enriched results
        for i, result in enumerate(fused_results[:top_k]):
            pdf_id = result.get("doc_id") or result.get("pdf_id") or result.get("source")
            page_start = result.get("page_start") or result.get("page_number")
            page_end = result.get("page_end") or page_start
            content = result.get("content", "")

            # Find images related to this chunk
            chunk_images = []
            for img in clip_images:
                img_page = img.get('page_number')
                if img_page and page_start and page_end:
                    if page_start <= img_page <= page_end:
                        chunk_images.append(img)

            # Extract or add related tables
            tables = []
            chunk_type = result.get("chunk_type", "TEXT")

            if chunk_type in ('TABLE', 'TABLE_CHUNK'):
                fixed_content = self._fix_markdown_table_separators(content)
                tables.append({"markdown": fixed_content})
            else:
                # Extract markdown tables from content
                table_pattern = r'(\|[^\n]+\|\n(?:\|[-:]+\|[-:|\s]+\n)?(?:\|[^\n]+\|\n)+)'
                table_matches = re.findall(table_pattern, content)
                for table_match in table_matches:
                    tables.append({"markdown": table_match.strip()})

                # Add related tables from same pages
                if related_tables_by_page and pdf_id and page_start:
                    for p in range(page_start, (page_end or page_start) + 1):
                        key = (pdf_id, p)
                        if key in related_tables_by_page:
                            for related_table in related_tables_by_page[key]:
                                if not any(t.get('markdown') == related_table['markdown'] for t in tables):
                                    tables.append(related_table)

            # Format page display
            if page_start == page_end or not page_end:
                page_display = f"p.{page_start}" if page_start else "p.?"
            else:
                page_display = f"p.{page_start}-{page_end}"

            doc_name = result.get("document_name") or result.get("source") or pdf_id or "Unknown"

            # Get web source info
            source_type = result.get("source_type", "document")
            source_url = result.get("source_url", "")

            enriched_result = {
                "index": i + 1,
                "chunk_id": result.get("chunk_id"),
                "chunk_type": chunk_type,
                "title": result.get("section_title") or f"{doc_name} ({page_display})",
                "content": content,
                "rrf_score": result.get("rrf_score", 0),
                "neo4j_rank": result.get("neo4j_rank"),
                "postgres_rank": result.get("postgres_rank"),
                "error_boosted": result.get("error_boosted", False),
                # Exact phrase match flags
                "exact_phrase_match": result.get("exact_phrase_match", False),
                "exact_phrase_partial": result.get("exact_phrase_partial", False),
                "matched_phrases": result.get("matched_phrases", []),
                "source": {
                    "document_name": doc_name,
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_path": result.get("section_path"),
                    "section_title": result.get("section_title"),
                    "doc_id": pdf_id,
                    # Web source specific fields
                    "source_type": source_type,
                    "source_url": source_url
                },
                "images": chunk_images,
                "tables": tables,
                "relations": result.get("relations", {})
            }

            enriched_results.append(enriched_result)

        return enriched_results, related_tables_by_page

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """
        Execute unified search combining Neo4j and PostgreSQL.

        Args:
            context: Agent execution context
            query: Search query (prefix with @ to prioritize web sources)
            top_k: Number of results (default: 3/5 based on context)
            doc_filter: Optional document ID filter
            include_images: Include CLIP image search (default: true)
            include_tables: Auto-include related tables (default: true)
            search_mode: hybrid, vector_only, or keyword_only

        Returns:
            ToolResult with fused search results
        """
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", DEFAULT_TOP_K)
        doc_filter = kwargs.get("doc_filter")
        include_images = kwargs.get("include_images", True)
        include_tables = kwargs.get("include_tables", True)
        search_mode = kwargs.get("search_mode", "hybrid")

        # Get original_query early for fallback checks (LLM may strip special characters)
        original_user_query = context.metadata.get('original_query', '') if context.metadata else ''

        # Feature: "@" prefix for web source priority search
        # Example: "@어셈블러 자산 수정 방법" → prioritize web sources
        # Check both tool query and original_query (LLM may strip @ prefix)
        prioritize_web_sources = False
        if query.startswith("@"):
            prioritize_web_sources = True
            query = query[1:].strip()  # Remove @ prefix
        elif original_user_query.startswith("@"):
            # LLM stripped the @ prefix, restore web priority mode
            prioritize_web_sources = True

        if prioritize_web_sources:
            logger.info(f"Web source priority mode activated for query: {query[:50]}...")

        # Feature: Exact phrase matching with double quotes
        # Example: '"정확한 문구"' → prioritize results containing exact phrase
        # Check both tool query and original_query (LLM may strip quotes)
        exact_phrases = []
        quote_pattern = r'"([^"]+)"'

        # First check tool query for quotes
        quote_matches = re.findall(quote_pattern, query)

        # If no quotes in tool query, check original_query from context
        if not quote_matches and original_user_query:
            quote_matches = re.findall(quote_pattern, original_user_query)

        if quote_matches:
            exact_phrases = [phrase.strip() for phrase in quote_matches if phrase.strip()]
            # Remove quotes from query for normal search, but keep the phrase
            search_query = re.sub(quote_pattern, r'\1', query)
            logger.info(f"Exact phrase matching enabled: {exact_phrases}")
        else:
            search_query = query

        # Track query correction
        llm_query = query
        query_was_corrected = False

        # Phase 1: Preprocessing - Validate query against original
        original_query = context.metadata.get('original_query', '') if context.metadata else ''
        if original_query and query != original_query:
            # Check 1: Character corruption (e.g., Japanese → Chinese substitution)
            validated_query, was_corrupted = _validate_query(query, original_query)
            if was_corrupted:
                logger.info(f"Query corruption fixed: '{query}' → '{validated_query}'")
                query = validated_query
                search_query = validated_query
                query_was_corrected = True

            # Check 2: LLM query expansion detection (AGGRESSIVE)
            # LLM often "improves" queries which HURTS vector search accuracy
            # Examples of bad expansions:
            #   "tjesmgr" → "tjesmgr 제품 소개 및 주요 기능 설명" (0 results)
            #   "tjesmgr 설명" → works fine
            else:
                # Strategy: Extract key term and use simpler query for better vector match
                # Key terms are usually: product names, commands, error codes, technical terms

                # Extract key term from original (first word that looks like a product/command)
                key_term_match = re.search(r'([a-zA-Z][a-zA-Z0-9_\-\.]+)', original_query)
                key_term = key_term_match.group(1) if key_term_match else None

                # Also check for error codes
                error_match = re.search(r'(-?\d{4,5})', original_query)
                error_code = error_match.group(1) if error_match else None

                should_use_original = False

                # Rule 1: If LLM query is >20% longer, likely bad expansion
                if len(query) > len(original_query) * 1.2:
                    should_use_original = True
                    logger.debug(f"LLM expanded query by {len(query)/len(original_query)*100-100:.0f}%")

                # Rule 2: If LLM added Korean filler words that hurt search
                filler_patterns = ['제품 소개', '주요 기능', '상세 설명', '에 대해', '에 관해', '관련 정보']
                for filler in filler_patterns:
                    if filler in query and filler not in original_query:
                        should_use_original = True
                        logger.debug(f"LLM added filler phrase: '{filler}'")
                        break

                # Rule 3: If key term exists, use simplified query: "{key_term}"
                if should_use_original:
                    if key_term:
                        # Use just the key term for best vector match
                        simplified_query = key_term
                        if error_code:
                            simplified_query = f"{key_term} {error_code}"
                        logger.info(f"Simplified query for better vector match: '{simplified_query}' (from LLM: '{query[:40]}...')")
                        query = simplified_query
                        search_query = simplified_query
                    else:
                        # No key term found, use original
                        logger.info(f"Reverted to original query: {original_query[:40]}...")
                        query = original_query
                        search_query = original_query
                    query_was_corrected = True

        # Agent-Driven RAG: Check for search scope from context
        search_scope = getattr(context, 'search_scope', None) if context else None
        has_scope = search_scope and (search_scope.documents or search_scope.sections)
        if has_scope:
            logger.info(f"Using scoped search: {len(search_scope.documents)} docs, {len(search_scope.sections)} sections")

        logger.info(f"Search request: query='{query[:50]}...', mode={search_mode}, web_priority={prioritize_web_sources}, scoped={has_scope}")

        if not query:
            return self.create_error_result("Query is required")

        # Extract error codes for boosting
        error_codes = _extract_error_codes(query)
        if error_codes:
            logger.info(f"Detected error codes: {error_codes}")

        try:
            # Phase 2: Parallel Search
            neo4j_results = []
            postgres_results = []

            language = kwargs.get("language", context.language if context else "auto")

            # Agent-Driven RAG: Use scoped search if scope is provided
            if has_scope and self.rag_service:
                try:
                    scoped_result = await self.rag_service.search_with_scope(
                        query=search_query,
                        documents=search_scope.documents,
                        sections=search_scope.sections,
                        top_k=top_k,
                        language=language
                    )
                    if scoped_result.get("success"):
                        neo4j_results = [
                            {
                                "chunk_id": src.get("doc_id", f"scoped_{i}"),
                                "content": src.get("content", ""),
                                "score": src.get("score", 0.0),
                                "source": src.get("doc_name") or src.get("source", "Unknown"),
                                "doc_id": src.get("doc_id", ""),
                                "page_number": src.get("page_number"),
                                "rank": i + 1,
                                "origin": "scoped",
                            }
                            for i, src in enumerate(scoped_result.get("sources", []))
                        ]
                        logger.info(f"Scoped search returned {len(neo4j_results)} results")
                except Exception as scope_err:
                    logger.warning(f"[UnifiedSearch] Scoped search failed, falling back to normal: {scope_err}")
                    has_scope = False  # Fall back to normal search

            # Execute normal searches if no scope or scope failed
            logger.debug(f"Search execution: has_scope={has_scope}, search_mode={search_mode}")
            if not has_scope:
                # Execute searches based on mode (use search_query which has quotes removed)
                if search_mode in ("hybrid", "vector_only"):
                    logger.debug(f"Calling Neo4j search with query='{search_query[:50]}...'")
                    neo4j_results = await self._neo4j_vector_search(
                        query=search_query,
                        top_k=top_k,
                        language=language,
                        context=context
                    )
                    logger.debug(f"Neo4j returned {len(neo4j_results)} results")

                if search_mode in ("hybrid", "keyword_only"):
                    logger.debug(f"Calling PostgreSQL search with doc_filter='{doc_filter}'")
                    postgres_results = await self._postgres_keyword_search(
                        query=search_query,
                        top_k=top_k,
                        doc_filter=doc_filter,
                        error_codes=error_codes
                    )
                    logger.debug(f"PostgreSQL returned {len(postgres_results)} results")

            # Phase 2.5: Exact phrase search (if quotes were used)
            exact_phrase_results = []
            if exact_phrases:
                exact_phrase_results = await self._exact_phrase_search(
                    exact_phrases=exact_phrases,
                    top_k=top_k * 2,
                    web_only=prioritize_web_sources  # @ prefix = web sources only
                )
                # Add exact phrase results to neo4j_results so they get included in fusion
                if exact_phrase_results:
                    # Prepend exact matches to neo4j results with high rank
                    for i, result in enumerate(exact_phrase_results):
                        result["rank"] = i + 1  # Top ranks
                        result["neo4j_rank"] = i + 1
                    neo4j_results = exact_phrase_results + neo4j_results

            # Phase 2.7: Chunk Linking - fetch subsequent chunks for headers/titles
            # This ensures tables/lists that follow headers are included
            if neo4j_results:
                neo4j_results = await self._fetch_linked_chunks(
                    results=neo4j_results,
                    num_following=2,  # Fetch 2 subsequent chunks
                    web_only=prioritize_web_sources
                )

            # Check if we got any results - with RETRY using key term
            if not neo4j_results and not postgres_results:
                # Retry with key term only if original query was different
                key_term_match = re.search(r'([a-zA-Z][a-zA-Z0-9_\-\.]+)', original_query or query)
                retry_query = key_term_match.group(1) if key_term_match else None

                if retry_query and retry_query.lower() != query.lower():
                    logger.info(f"Retrying search with key term: '{retry_query}' (original: '{query[:30]}...')")

                    # Retry Neo4j search with key term
                    try:
                        neo4j_results = await self._neo4j_vector_search(
                            query=retry_query,
                            top_k=top_k * 2,
                            doc_filter=doc_filter,
                            search_scope=search_scope
                        )
                        logger.debug(f"Retry returned {len(neo4j_results)} results with key term")
                    except Exception as retry_e:
                        logger.warning(f"[UnifiedSearch] Retry Neo4j search failed: {retry_e}")
                        neo4j_results = []

                # Still no results after retry
                if not neo4j_results and not postgres_results:
                    return self.create_success_result(
                        "No relevant content found. Try rephrasing your query or using different keywords.",
                        metadata={"results_count": 0, "query": query, "retry_attempted": bool(retry_query)}
                    )

            # Phase 3: RRF Fusion
            if search_mode == "hybrid":
                fused_results = self._rrf_fusion(
                    neo4j_results=neo4j_results,
                    postgres_results=postgres_results,
                    error_codes=error_codes,
                    prioritize_web=prioritize_web_sources
                )
            elif search_mode == "vector_only":
                fused_results = neo4j_results
                # Apply web source filter/boost for vector_only mode
                if prioritize_web_sources:
                    fused_results = self._apply_web_priority(fused_results)
            else:
                fused_results = postgres_results

            # Phase 3.5: Exact phrase matching - prioritize results containing exact phrases
            if exact_phrases:
                fused_results = self._apply_exact_phrase_priority(fused_results, exact_phrases)

            # Extract relevant pages for image search
            relevant_pages = set()
            relevant_doc_id = None
            for result in fused_results[:top_k]:
                page = result.get("page_start") or result.get("page_number")
                if page:
                    relevant_pages.add(page)
                    relevant_pages.add(page - 1)
                    relevant_pages.add(page + 1)
                if not relevant_doc_id:
                    relevant_doc_id = result.get("doc_id") or result.get("pdf_id")

            # CLIP image search (optional)
            clip_images = []
            if include_images and relevant_pages:
                clip_images = await self._clip_image_search(
                    query=query,
                    relevant_pages=relevant_pages,
                    doc_id=doc_filter or relevant_doc_id,
                    limit=5
                )

            # Phase 4: Structure Enrichment
            enriched_results, _ = await self._enrich_with_structure(
                fused_results=fused_results,
                clip_images=clip_images,
                include_tables=include_tables,
                top_k=top_k
            )

            # Format output text
            if exact_phrases:
                exact_count = sum(1 for r in enriched_results if r.get("exact_phrase_match"))
                output_parts = [f"🎯 [Exact Phrase Mode] Found {len(enriched_results)} result(s) - {exact_count} exact match(es) for \"{' '.join(exact_phrases)}\":\n"]
            elif prioritize_web_sources:
                output_parts = [f"🌐 [Web Priority Mode] Found {len(enriched_results)} relevant result(s) - web sources prioritized:\n"]
            else:
                output_parts = [f"Found {len(enriched_results)} relevant result(s) via unified search:\n"]

            for result in enriched_results:
                chunk_type = result.get("chunk_type", "TEXT")
                rrf_score = result.get("rrf_score", 0)
                source = result.get("source", {})
                doc_name = source.get("document_name", "Unknown")
                page_start = source.get("page_start", "?")
                page_end = source.get("page_end", "?")
                section_title = source.get("section_title", "")
                section_path = source.get("section_path", "")
                content = result.get("content", "")
                error_boosted = result.get("error_boosted", False)

                # Format page display
                if page_start == page_end or not page_end:
                    page_display = f"p.{page_start}"
                else:
                    page_display = f"p.{page_start}-{page_end}"

                source_display = f"{doc_name} ({page_display})"

                chunk_info = (
                    f"\n{result['index']}. [{chunk_type}] RRF Score: {rrf_score:.4f}\n"
                    f"   Source: {source_display}\n"
                )

                # Show web source URL if available
                result_source_type = source.get("source_type", "document")
                result_source_url = source.get("source_url", "")
                if result_source_type == "web" and result_source_url:
                    chunk_info += f"   🌐 Web Source: {result_source_url}\n"

                if error_boosted:
                    chunk_info += f"   ⚠️ KEYWORD MATCH - ANSWER IS IN CONTENT BELOW:\n"

                # Show exact phrase match status
                if result.get("exact_phrase_match"):
                    chunk_info += f"   🎯 EXACT PHRASE MATCH - HIGH PRIORITY RESULT\n"
                elif result.get("exact_phrase_partial"):
                    chunk_info += f"   ✓ Partial phrase match\n"

                if section_title:
                    chunk_info += f"   Section: {section_title}\n"
                if section_path:
                    chunk_info += f"   Path: {section_path}\n"

                # Truncate content if too long
                if len(content) > 800:
                    content = content[:800] + "..."
                chunk_info += f"   Content:\n   {content}\n"

                # Relations info
                relations = result.get("relations", {})
                if isinstance(relations, str):
                    try:
                        relations = json.loads(relations)
                    except:
                        relations = {}

                related = []
                if relations.get('previous'):
                    related.append("has previous")
                if relations.get('next'):
                    related.append("has next")
                if relations.get('parent'):
                    related.append("has parent section")
                if relations.get('children'):
                    related.append(f"{len(relations['children'])} child chunks")

                if related:
                    chunk_info += f"   Related: {', '.join(related)}\n"

                output_parts.append(chunk_info)

            # Add image info
            if clip_images:
                output_parts.append(f"\n {len(clip_images)} query-matched image(s):")
                for img in clip_images[:5]:
                    output_parts.append(
                        f"  - Image: {img['image_id']} (Page {img['page_number']}, "
                        f"Similarity: {img['similarity']:.1%})\n"
                        f"    URL: {img['url']}"
                    )

            # Build sources list for metadata
            sources = []
            seen_sources = set()
            for result in enriched_results:
                source = result.get("source", {})
                doc_name = source.get("document_name", "Unknown")
                page_start = source.get("page_start")
                page_end = source.get("page_end")
                source_key = f"{doc_name}:{page_start}-{page_end}"

                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    if page_start == page_end or not page_end:
                        page_display = f"p.{page_start}"
                    else:
                        page_display = f"p.{page_start}-{page_end}"

                    source_type = source.get("source_type", "document")
                    source_url = source.get("source_url", "")

                    sources.append({
                        "source": f"{doc_name} ({page_display})",
                        "score": result.get("rrf_score", 0),
                        "page_number": page_start,
                        "content": result.get("content", "")[:200],
                        "doc_id": source.get("doc_id"),
                        # Web source specific fields
                        "source_type": source_type,
                        "source_url": source_url
                    })

            # Store sources in context metadata
            if context.metadata is None:
                context.metadata = {}
            if 'sources' not in context.metadata:
                context.metadata['sources'] = []
            context.metadata['sources'].extend(sources)

            # Build result metadata
            result_metadata = {
                "results_count": len(enriched_results),
                "query": query,
                "search_mode": search_mode,
                "web_priority_mode": prioritize_web_sources,
                "neo4j_count": len(neo4j_results),
                "postgres_count": len(postgres_results),
                "error_codes_detected": error_codes,
                "sources": sources,
                "image_count": len(clip_images),
                "images": clip_images,
                "individual_results": enriched_results,
            }

            if query_was_corrected:
                result_metadata["query_corrected"] = True
                result_metadata["original_llm_query"] = llm_query
                result_metadata["corrected_query"] = query

            return self.create_success_result(
                "\n".join(output_parts),
                metadata=result_metadata
            )

        except Exception as e:
            logger.error(f"Unified search error: {e}", exc_info=True)
            return self.create_error_result(f"Unified search error: {str(e)}")
