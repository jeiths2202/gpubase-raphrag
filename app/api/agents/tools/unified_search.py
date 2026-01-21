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
                    "description": "Optional document ID to filter results"
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
            try:
                from ...core.deps import get_rag_service
                self._rag_service = get_rag_service()
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
        try:
            result = await self.rag_service.query(
                question=query,
                strategy="vector",
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
                    "origin": "neo4j"
                })

            logger.info(f"[UnifiedSearch] Neo4j returned {len(neo4j_results)} results")
            return neo4j_results

        except Exception as e:
            logger.error(f"Neo4j vector search error: {e}")
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

            # Build document filter
            doc_filter_sql = ""
            if doc_filter:
                doc_filter_sql = f"AND pdf_id = '{doc_filter}'"

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
            clip_results = await image_repo.search_by_clip_embedding(
                query_embedding=clip_query_embedding,
                document_id=doc_id,
                limit=limit * 3,
                min_similarity=0.20
            )

            # Filter by relevant pages
            clip_images = []
            seen_pages = set()

            for img in clip_results:
                if img.get('similarity', 0) < 0.20:
                    continue

                page_num = img.get('page_number')
                # Only include images from pages that matched text chunks
                if relevant_pages and page_num not in relevant_pages:
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
        k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF) to combine search results.

        RRF score = 1/(k + rank_v) + 1/(k + rank_k) + error_boost
        Where k=60 is a constant that prevents extreme rankings.
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

        logger.info(f"[UnifiedSearch] RRF fusion produced {len(sorted_chunks)} unique results")
        return sorted_chunks

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
                "source": {
                    "document_name": doc_name,
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_path": result.get("section_path"),
                    "section_title": result.get("section_title"),
                    "doc_id": pdf_id
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
            query: Search query
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

        # Track query correction
        llm_query = query
        query_was_corrected = False

        # Phase 1: Preprocessing - Validate query against original
        original_query = context.metadata.get('original_query', '') if context.metadata else ''
        if original_query and query != original_query:
            validated_query, was_corrupted = _validate_query(query, original_query)
            if was_corrupted:
                print(f"[UnifiedSearch] Query corruption fixed: '{query}' → '{validated_query}'", flush=True)
                query = validated_query
                query_was_corrected = True

        print(f"[UnifiedSearch] Called with query: {query[:50]}..., mode={search_mode}", flush=True)
        logger.info(f"[UnifiedSearch] Called with query: {query[:50]}..., mode={search_mode}")

        if not query:
            return self.create_error_result("Query is required")

        # Extract error codes for boosting
        error_codes = _extract_error_codes(query)
        if error_codes:
            print(f"[UnifiedSearch] Detected error codes: {error_codes}", flush=True)
            logger.info(f"[UnifiedSearch] Detected error codes: {error_codes}")

        try:
            # Phase 2: Parallel Search
            neo4j_results = []
            postgres_results = []

            language = kwargs.get("language", context.language if context else "auto")

            # Execute searches based on mode
            if search_mode in ("hybrid", "vector_only"):
                neo4j_results = await self._neo4j_vector_search(
                    query=query,
                    top_k=top_k,
                    language=language,
                    context=context
                )

            if search_mode in ("hybrid", "keyword_only"):
                postgres_results = await self._postgres_keyword_search(
                    query=query,
                    top_k=top_k,
                    doc_filter=doc_filter,
                    error_codes=error_codes
                )

            # Check if we got any results
            if not neo4j_results and not postgres_results:
                return self.create_success_result(
                    "No relevant content found. Try rephrasing your query or using different keywords.",
                    metadata={"results_count": 0, "query": query}
                )

            # Phase 3: RRF Fusion
            if search_mode == "hybrid":
                fused_results = self._rrf_fusion(
                    neo4j_results=neo4j_results,
                    postgres_results=postgres_results,
                    error_codes=error_codes
                )
            elif search_mode == "vector_only":
                fused_results = neo4j_results
            else:
                fused_results = postgres_results

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

                if error_boosted:
                    chunk_info += f"   KEYWORD MATCH - ANSWER IS IN CONTENT BELOW:\n"

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

                    sources.append({
                        "source": f"{doc_name} ({page_display})",
                        "score": result.get("rrf_score", 0),
                        "page_number": page_start,
                        "content": result.get("content", "")[:200],
                        "doc_id": source.get("doc_id")
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
