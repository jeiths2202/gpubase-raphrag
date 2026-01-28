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

# Learning LLM Feature Toggle
ENABLE_LEARNING_LLM = os.getenv("ENABLE_LEARNING_LLM", "false").lower() == "true"
LEARNING_LLM_MIN_CONFIDENCE = float(os.getenv("LEARNING_LLM_MIN_CONFIDENCE", "0.6"))
LEARNING_LLM_VERIFICATION_THRESHOLD = float(os.getenv("LEARNING_LLM_VERIFICATION_THRESHOLD", "0.7"))

# Default top_k based on LLM context size
_USE_LARGE_CONTEXT = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"
DEFAULT_TOP_K = 5 if _USE_LARGE_CONTEXT else 3

# Search mode: "hybrid", "vector_only", "keyword_only"
DEFAULT_SEARCH_MODE = os.getenv("UNIFIED_SEARCH_MODE", "hybrid").lower()
if DEFAULT_SEARCH_MODE not in ("hybrid", "vector_only", "keyword_only"):
    logger.warning(f"Invalid UNIFIED_SEARCH_MODE '{DEFAULT_SEARCH_MODE}', using 'hybrid'")
    DEFAULT_SEARCH_MODE = "hybrid"

# RRF (Reciprocal Rank Fusion) toggle
# When disabled, hybrid mode returns Neo4j results with PostgreSQL boost markers only
ENABLE_RRF_FUSION = os.getenv("ENABLE_RRF_FUSION", "false").lower() == "true"


# =============================================================
# INTENT-RESULT MATCHING FOR SUMMARY-FIRST SEARCH
# =============================================================

# Query intent patterns
_ERROR_INTENT_PATTERNS = re.compile(
    r'에러|error|오류|エラー|실패|fail|exception|장애|障害|원인|cause|이유|reason|해결|solution|fix|대처|対処',
    re.IGNORECASE
)
_COMMAND_INTENT_PATTERNS = re.compile(
    r'명령|command|cmd|사용법|usage|how\s*to|방법|옵션|option|파라미터|parameter|argument|구문|syntax|실행|execute|run',
    re.IGNORECASE
)
_GLOSSARY_INTENT_PATTERNS = re.compile(
    r'뭐|what\s*is|무엇|정의|definition|의미|mean|약어|abbreviation|용어|term|설명|explain|概要',
    re.IGNORECASE
)


def _detect_query_intent(query: str) -> set:
    """
    Detect the intent of a query based on keyword patterns.

    Returns a set of intents: 'error', 'command', 'glossary', 'general'
    """
    intents = set()

    if _ERROR_INTENT_PATTERNS.search(query):
        intents.add('error')
    if _COMMAND_INTENT_PATTERNS.search(query):
        intents.add('command')
    if _GLOSSARY_INTENT_PATTERNS.search(query):
        intents.add('glossary')

    # If no specific intent detected, it's general
    if not intents:
        intents.add('general')

    return intents


def _check_intent_result_match(query_intents: set, summary_results: list, query: str = "") -> bool:
    """
    Check if summary results match the detected query intent.

    Returns True if results are relevant to the query intent.
    """
    if not summary_results:
        return False

    # Get result types from summary results
    result_types = set()
    for result in summary_results:
        result_type = result.get("type", "").lower()
        if "error" in result_type:
            result_types.add('error')
        elif "command" in result_type:
            result_types.add('command')
        elif "glossary" in result_type or "term" in result_type:
            result_types.add('glossary')
        else:
            result_types.add('general')

    # ENCODING ISSUE WORKAROUND:
    # Korean/Japanese characters often get corrupted to "?" in the pipeline.
    # If query has "?" after a keyword and results are ONLY commands,
    # user likely asked about error/usage/etc - fall back to vector search.
    if query and '?' in query and result_types == {'command'}:
        # Query has corrupted characters and only command results
        # This suggests user asked about command + something else (error, usage details, etc.)
        # Fall back to vector search for better results
        return False

    # If general intent, any results are fine
    if 'general' in query_intents:
        return True

    # Check if any query intent matches result types
    # Error intent should match error results
    if 'error' in query_intents and 'error' not in result_types:
        return False

    # Command intent can match command results, but if user asks about
    # command errors specifically, we need error info too
    if 'error' in query_intents and 'command' in query_intents:
        # User asking about command errors - need error results
        if 'error' not in result_types:
            return False

    return True


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
                    "description": f"Search mode: hybrid (Neo4j+PostgreSQL), vector_only, keyword_only. RRF fusion controlled by ENABLE_RRF_FUSION env (default: false). Default mode: {DEFAULT_SEARCH_MODE}",
                    "enum": ["hybrid", "vector_only", "keyword_only"],
                    "default": DEFAULT_SEARCH_MODE
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

    # =============================================================
    # SUMMARY-FIRST SEARCH METHODS
    # =============================================================

    async def _summary_first_search(
        self,
        query: str,
        context: AgentContext,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute Summary-First search using BM25 over summaries.

        This is Phase 0 of the search pipeline, executing before
        expensive vector search operations.

        Args:
            query: Search query
            context: Agent context

        Returns:
            Dict with results, confidence, and context_string or None if disabled
        """
        try:
            from ...core.config import api_settings

            # Check if Summary-First search is enabled
            if not getattr(api_settings, 'SUMMARY_SEARCH_ENABLED', True):
                return None

            # Import services
            from ...services.summary_bm25_service import get_summary_bm25_service
            from ...services.summary_search_service import get_summary_search_service

            # Try BM25 service first (faster, more comprehensive)
            bm25_service = get_summary_bm25_service()
            if bm25_service.is_initialized:
                result = await bm25_service.comprehensive_search(
                    query=query,
                    top_k=getattr(api_settings, 'SUMMARY_SEARCH_TOP_K', 5)
                )

                if result.total_results > 0:
                    # Convert to dict format
                    return {
                        "results": [
                            {
                                "type": sr.document.doc_type.value,
                                "name": sr.document.name,
                                "description": sr.document.description,
                                "content": sr.document.content[:500],
                                "score": sr.score,
                                "source_file": sr.document.source_file,
                                "source_pdf": sr.document.source_pdf,
                                "page_numbers": sr.document.page_numbers,
                                "matched_terms": sr.matched_terms,
                            }
                            for sr in result.results
                        ],
                        "confidence": result.confidence.value,
                        "context_string": result.get_context_string(),
                        "page_references": [
                            {"pdf_path": ref.pdf_path, "page_number": ref.page_number}
                            for ref in result.page_references
                        ],
                        "detected_error_codes": result.detected_error_codes,
                        "detected_commands": result.detected_commands,
                        "detected_terms": result.detected_terms,
                    }

            # Fall back to legacy summary service
            legacy_service = get_summary_search_service()
            legacy_result = await legacy_service.comprehensive_search(query)

            if legacy_result.get("total_results", 0) > 0:
                return legacy_result

            return None

        except Exception as e:
            logger.warning(f"[SummaryFirst] Search failed, continuing to vector search: {e}")
            return None

    async def _get_multi_product_results(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get multi-product aggregated results for platform comparison.

        Args:
            query: Search query
            top_k: Maximum number of aggregated results

        Returns:
            List of multi-product result dicts with platform variants
        """
        try:
            from ...services.summary_bm25_service import get_summary_bm25_service

            bm25_service = get_summary_bm25_service()
            if not bm25_service.is_initialized:
                await bm25_service.initialize()

            multi_results = await bm25_service.search_multi_product(query, top_k=top_k)

            # Convert to serializable dict format
            result_dicts = []
            for mr in multi_results:
                variants_list = []
                for v in mr.variants:
                    variants_list.append({
                        "platform": v.platform,
                        "product_version": v.product_version,
                        "description": v.description,
                        "syntax": v.syntax,
                        "source_pdf": v.source_pdf,
                        "page_numbers": v.page_numbers,
                        "solution": v.solution,
                        "document_version": v.document_version
                    })

                result_dicts.append({
                    "name": mr.name,
                    "doc_type": mr.doc_type.value,
                    "variants": variants_list,
                    "has_differences": mr.has_differences,
                    "available_platforms": mr.available_platforms,
                    "score": mr.score
                })

            return result_dicts

        except Exception as e:
            logger.warning(f"[MultiProduct] Search failed: {e}")
            return []

    async def _build_response_from_summaries(
        self,
        summary_result: Dict[str, Any],
        query: str,
        context: AgentContext,
    ) -> ToolResult:
        """
        Build a ToolResult from summary search results.

        Called when Summary-First search has HIGH confidence.
        Now includes multi-product aggregation for platform comparison.

        Args:
            summary_result: Result from _summary_first_search
            query: Original query
            context: Agent context

        Returns:
            ToolResult with formatted summary results and multi-product info
        """
        results = summary_result.get("results", [])
        confidence = summary_result.get("confidence", "high")
        page_references = summary_result.get("page_references", [])

        # Get multi-product aggregated results for platform comparison
        multi_product_results = await self._get_multi_product_results(query, top_k=5)

        # Build output text
        output_parts = [
            f"📚 [Summary-First Search] Found {len(results)} direct match(es) with {confidence} confidence:\n"
        ]

        enriched_results = []

        for i, result in enumerate(results[:5]):
            result_type = result.get("type", "unknown")
            name = result.get("name", "Unknown")
            description = result.get("description", "")
            content = result.get("content", "")
            source_file = result.get("source_file", "")
            source_pdf = result.get("source_pdf", "")
            page_numbers = result.get("page_numbers", [])
            score = result.get("score", 0)

            # Format based on type
            if result_type == "error-codes":
                chunk_info = f"\n{i+1}. [ERROR CODE] {name}\n"
                chunk_info += f"   Score: {score:.2f}\n"
                if description:
                    chunk_info += f"   설명: {description}\n"
                solution = result.get("solution") or ""
                if solution:
                    chunk_info += f"   대처방법: {solution}\n"

            elif result_type == "commands":
                chunk_info = f"\n{i+1}. [COMMAND] {name}\n"
                chunk_info += f"   Score: {score:.2f}\n"
                if description:
                    chunk_info += f"   설명: {description[:200]}\n"
                syntax = result.get("syntax") or ""
                if syntax:
                    chunk_info += f"   구문: {syntax}\n"
                products = result.get("products") or result.get("product") or ""
                if products:
                    if isinstance(products, list):
                        products = ", ".join(products)
                    chunk_info += f"   제품: {products}\n"

            elif result_type == "glossary":
                chunk_info = f"\n{i+1}. [TERM] {name}\n"
                chunk_info += f"   Score: {score:.2f}\n"
                full_name = result.get("full_name") or ""
                if full_name:
                    chunk_info += f"   정식명칭: {full_name}\n"
                if description:
                    chunk_info += f"   설명: {description}\n"

            elif result_type == "apis":
                chunk_info = f"\n{i+1}. [API] {name}\n"
                chunk_info += f"   Score: {score:.2f}\n"
                if description:
                    chunk_info += f"   설명: {description[:200]}\n"
                syntax = result.get("syntax") or ""
                if syntax:
                    chunk_info += f"   프로토타입: {syntax}\n"

            else:
                chunk_info = f"\n{i+1}. [{result_type.upper()}] {name}\n"
                chunk_info += f"   Score: {score:.2f}\n"
                if content:
                    chunk_info += f"   Content: {content[:300]}...\n"

            # Add source info
            if source_file:
                chunk_info += f"   Source: {source_file}"
                if page_numbers:
                    pages_str = ", ".join(str(p) for p in page_numbers[:3])
                    chunk_info += f" (p.{pages_str})"
                chunk_info += "\n"

            output_parts.append(chunk_info)

            # Build enriched result for metadata
            enriched_results.append({
                "index": i + 1,
                "chunk_type": result_type.upper(),
                "title": name,
                "content": content or description or "",
                "rrf_score": score,
                "source": {
                    "document_name": source_pdf or source_file,
                    "source_file": source_file,
                    "page_start": page_numbers[0] if page_numbers else None,
                    "page_end": page_numbers[-1] if page_numbers else None,
                    "source_type": "summary",
                },
                "summary_match": True,
                "tables": [],
                "images": [],
            })

        # Add page reference info if available
        if page_references:
            output_parts.append(f"\n📄 Page References ({len(page_references)} page(s)):")
            seen_refs = set()
            for ref in page_references[:5]:
                ref_key = f"{ref.get('pdf_path')}:{ref.get('page_number')}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    output_parts.append(f"  - {ref.get('pdf_path')} p.{ref.get('page_number')}")

        # Build sources list for metadata
        sources = []
        seen_sources = set()
        for result in results[:5]:
            source_file = result.get("source_file", "")
            source_pdf = result.get("source_pdf", source_file)
            page_numbers = result.get("page_numbers", [])

            source_key = f"{source_pdf}:{page_numbers}"
            if source_key not in seen_sources:
                seen_sources.add(source_key)

                page_display = ""
                if page_numbers:
                    if len(page_numbers) == 1:
                        page_display = f"p.{page_numbers[0]}"
                    else:
                        page_display = f"p.{page_numbers[0]}-{page_numbers[-1]}"

                sources.append({
                    "source": f"{source_pdf} ({page_display})" if page_display else source_file,
                    "score": result.get("score", 0),
                    "page_number": page_numbers[0] if page_numbers else None,
                    "content": (result.get("description") or result.get("content") or "")[:200],
                    "doc_id": source_pdf,
                    "source_type": "summary",
                })

        # Store sources in context metadata
        if context.metadata is None:
            context.metadata = {}
        if 'sources' not in context.metadata:
            context.metadata['sources'] = []
        context.metadata['sources'].extend(sources)

        # Check if any multi-product results have platform differences
        has_platform_differences = any(
            mpr.get("has_differences", False) for mpr in multi_product_results
        )

        # Build product sections for frontend display
        product_sections = []
        for mpr in multi_product_results:
            if mpr.get("has_differences"):
                # Create separate sections for each platform variant
                for variant in mpr.get("variants", []):
                    section_content = f"## {variant['platform']}"
                    if variant.get("product_version"):
                        section_content += f" (v{variant['product_version']})"
                    section_content += f"\n{variant.get('description', '')}"
                    if variant.get("syntax"):
                        section_content += f"\n구문: `{variant['syntax']}`"

                    product_sections.append({
                        "platform": variant["platform"],
                        "version": variant.get("product_version"),
                        "content": section_content,
                        "source": variant.get("source_pdf"),
                        "page_numbers": variant.get("page_numbers", [])
                    })
            else:
                # Common content - use first variant
                variants = mpr.get("variants", [])
                if variants:
                    first_variant = variants[0]
                    product_sections.append({
                        "platform": "공통",
                        "content": first_variant.get("description", ""),
                        "available_platforms": mpr.get("available_platforms", []),
                        "source": first_variant.get("source_pdf"),
                        "page_numbers": first_variant.get("page_numbers", [])
                    })

        # Build result metadata with multi-product info
        result_metadata = {
            "results_count": len(enriched_results),
            "query": query,
            "search_mode": "summary_first",
            "confidence": confidence,
            "summary_search": True,
            "sources": sources,
            "individual_results": enriched_results,
            "detected_error_codes": summary_result.get("detected_error_codes", []),
            "detected_commands": summary_result.get("detected_commands", []),
            "detected_terms": summary_result.get("detected_terms", []),
            # Multi-product information for frontend
            "multi_product": len(multi_product_results) > 0,
            "multi_product_results": multi_product_results,
            "product_sections": product_sections,
            "has_platform_differences": has_platform_differences,
        }

        return self.create_success_result(
            "\n".join(output_parts),
            metadata=result_metadata
        )

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

    async def _graph_traversal_search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Graph-based search using Entity relationships.

        Strategy:
        1. Extract keywords from query
        2. Find Chunks containing those keywords (full-text in content)
        3. Find Entities related to those keywords
        4. Return chunks connected via MENTIONS relationships

        This complements vector search by finding exact keyword matches
        that semantic search might miss.
        """
        try:
            from neo4j import GraphDatabase

            uri = os.getenv("NEO4J_URI", "bolt://192.168.8.11:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "graphrag2024")

            driver = GraphDatabase.driver(uri, auth=(user, password))

            # Extract keywords from query (technical terms, product names)
            keywords = []
            # Pattern 1: Technical terms (alphanumeric with possible underscore/dash)
            tech_terms = re.findall(r'\b([a-zA-Z][a-zA-Z0-9_\-\.]{2,})\b', query)
            keywords.extend([t.lower() for t in tech_terms])

            # Pattern 2: Error codes
            error_codes = re.findall(r'-?\d{4,5}', query)
            keywords.extend(error_codes)

            # Remove common stopwords
            stopwords = {'about', 'what', 'how', 'the', 'for', 'and', 'with', 'this', 'that'}
            keywords = [k for k in keywords if k.lower() not in stopwords and len(k) > 2]

            if not keywords:
                driver.close()
                return []

            logger.info(f"[GraphSearch] Keywords: {keywords}")

            results = []
            with driver.session() as session:
                # Search for chunks containing keywords in content
                for keyword in keywords[:3]:  # Limit to top 3 keywords
                    cypher = """
                    MATCH (c:Chunk)-[:CONTAINS]-(d:Document)
                    WHERE toLower(c.content) CONTAINS toLower($keyword)
                    RETURN c.chunk_id as chunk_id,
                           c.content as content,
                           d.filename as doc_filename,
                           d.doc_id as doc_id,
                           c.page_number as page_number,
                           c.section_path as section_path
                    LIMIT $limit
                    """
                    result = session.run(cypher, keyword=keyword, limit=top_k)

                    for record in result:
                        # Calculate simple relevance based on keyword frequency
                        content = record["content"] or ""
                        keyword_count = content.lower().count(keyword.lower())

                        results.append({
                            "chunk_id": record["chunk_id"],
                            "content": content,
                            "doc_filename": record["doc_filename"],
                            "doc_id": record["doc_id"],
                            "page_number": record["page_number"],
                            "section_path": record["section_path"],
                            "source_type": "graph",
                            "graph_keyword": keyword,
                            "keyword_frequency": keyword_count,
                            "rank": 1  # Will be re-ranked in RRF
                        })

            driver.close()

            # Deduplicate by chunk_id
            seen = set()
            unique_results = []
            for r in results:
                cid = r.get("chunk_id")
                if cid and cid not in seen:
                    seen.add(cid)
                    unique_results.append(r)

            # Sort by keyword frequency
            unique_results.sort(key=lambda x: x.get("keyword_frequency", 0), reverse=True)

            # Assign ranks
            for i, r in enumerate(unique_results):
                r["rank"] = i + 1
                r["graph_rank"] = i + 1

            logger.info(f"[GraphSearch] Found {len(unique_results)} results via graph traversal")
            return unique_results[:top_k * 2]

        except Exception as e:
            logger.error(f"[GraphSearch] Error: {e}")
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

    def _simple_hybrid_merge(
        self,
        neo4j_results: List[Dict],
        postgres_results: List[Dict],
        error_codes: List[str]
    ) -> List[Dict]:
        """
        Simple hybrid merge WITHOUT RRF score calculation.

        Uses Neo4j vector scores directly, but marks results that also
        appear in PostgreSQL keyword search (for confidence indicator).

        This avoids RRF score inflation issues while still benefiting
        from both search sources.
        """
        # Build set of chunk_ids from PostgreSQL for quick lookup
        postgres_chunk_ids = set()
        for result in postgres_results:
            chunk_id = result.get("chunk_id")
            if chunk_id:
                postgres_chunk_ids.add(chunk_id)

        # Process Neo4j results (primary source)
        merged = []
        for result in neo4j_results:
            chunk_id = result.get("chunk_id")

            # Mark if also found in keyword search
            if chunk_id in postgres_chunk_ids:
                result["keyword_match"] = True
                result["source_type"] = "hybrid"  # Found in both
            else:
                result["keyword_match"] = False
                result["source_type"] = "vector"

            # Keep original Neo4j score (no RRF inflation)
            # Score is already in result from Neo4j
            merged.append(result)

        # Add PostgreSQL-only results (not in Neo4j)
        neo4j_chunk_ids = {r.get("chunk_id") for r in neo4j_results if r.get("chunk_id")}
        for result in postgres_results:
            chunk_id = result.get("chunk_id")
            if chunk_id and chunk_id not in neo4j_chunk_ids:
                result["keyword_match"] = True
                result["source_type"] = "keyword"
                # Use a low default score for keyword-only results
                if "score" not in result:
                    result["score"] = 0.1
                merged.append(result)

        # Sort by score (Neo4j scores are primary)
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Error code boost (apply simple boost, not RRF)
        if error_codes:
            for result in merged:
                content = result.get("content", "").lower()
                for code in error_codes:
                    if code.lower() in content:
                        result["error_match"] = True
                        break

        logger.info(f"[UnifiedSearch] Simple hybrid merge: {len(merged)} results "
                   f"({sum(1 for r in merged if r.get('keyword_match'))} with keyword match)")
        return merged

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
        search_mode = kwargs.get("search_mode", DEFAULT_SEARCH_MODE)

        # Get original_query early for fallback checks (LLM may strip special characters)
        original_user_query = context.metadata.get('original_query', '') if context.metadata else ''

        # =============================================================
        # OPTION C: FORCE ORIGINAL QUERY (Block LLM modifications)
        # =============================================================
        # LLM often "improves" queries which HURTS search accuracy:
        #   "tjesmgr 에러" → "Tibero tjesmgr エラー" (adds wrong product)
        #   "VSAM 설명" → "OpenFrame VSAM 제품 소개 및 주요 기능" (adds filler)
        #
        # Solution: Always use the original user query for search.
        # Cross-language translation (Korean→Japanese) is handled separately
        # by LLMQueryExpansionService in hybrid_rag.py.
        # =============================================================
        llm_modified_query = query  # Save for logging
        if original_user_query:
            # Strip @ prefix from original for comparison
            original_clean = original_user_query.lstrip('@').strip()
            query_clean = query.lstrip('@').strip()

            if query_clean != original_clean:
                logger.warning(
                    f"[OPTION C] Blocking LLM query modification: "
                    f"'{query_clean[:50]}' → forced back to '{original_clean[:50]}'"
                )
                query = original_user_query  # Force use original

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

        # Track query correction (Option C already handled LLM modification blocking above)
        llm_query = llm_modified_query  # The query LLM tried to use
        query_was_corrected = (llm_modified_query != query)

        # Phase 1: Character corruption check only (Option C handles LLM expansion)
        original_query = context.metadata.get('original_query', '') if context.metadata else ''
        if original_query and query != original_query:
            # Check for character corruption (e.g., Japanese → Chinese substitution)
            validated_query, was_corrupted = _validate_query(query, original_query)
            if was_corrupted:
                logger.info(f"Query corruption fixed: '{query}' → '{validated_query}'")
                query = validated_query
                search_query = validated_query
                query_was_corrected = True

        # Agent-Driven RAG: Check for search scope from context
        search_scope = getattr(context, 'search_scope', None) if context else None
        has_scope = search_scope and (search_scope.documents or search_scope.sections)
        if has_scope:
            logger.info(f"Using scoped search: {len(search_scope.documents)} docs, {len(search_scope.sections)} sections")

        logger.info(f"Search request: query='{query[:50]}...', mode={search_mode}, web_priority={prioritize_web_sources}, scoped={has_scope}")

        if not query:
            return self.create_error_result("Query is required")

        # =============================================================
        # LEARNING LLM PHASE: Fine-tuned LLM for domain knowledge
        # =============================================================
        # Phase -1: Try Learning LLM first for domain-specific answers
        # The Learning LLM is fine-tuned on summaries data and can answer
        # error code, command, and terminology questions directly
        if ENABLE_LEARNING_LLM:
            learning_llm_result = await self._try_learning_llm(
                query=search_query,
                context=context,
            )
            if learning_llm_result:
                llm_confidence = learning_llm_result.get("confidence", 0.0)
                logger.info(f"[LearningLLM] Got response with confidence={llm_confidence:.2f}")

                if llm_confidence >= LEARNING_LLM_MIN_CONFIDENCE:
                    # Verify the answer against summaries data
                    verification_result = await self._verify_with_summaries(
                        learning_llm_result=learning_llm_result,
                        context=context,
                    )
                    logger.debug(f"[LearningLLM] Verification result: {verification_result}")

                    if verification_result and verification_result.get("is_valid"):
                        verification_score = verification_result.get("verification_score", 0.0)
                        logger.info(f"[LearningLLM] Verified answer: score={verification_score:.2f}, threshold={LEARNING_LLM_VERIFICATION_THRESHOLD}")

                        if verification_score >= LEARNING_LLM_VERIFICATION_THRESHOLD:
                            logger.info(f"[LearningLLM] Score >= threshold, returning verified response")

                            # Get multi-product results for platform comparison
                            multi_product_results = await self._get_multi_product_results(search_query, top_k=5)
                            if multi_product_results:
                                logger.info(f"[LearningLLM] Added {len(multi_product_results)} multi-product results")

                            # High confidence, verified answer - return directly
                            verified_response = await self._build_learning_llm_response(
                                learning_llm_result=learning_llm_result,
                                verification_result=verification_result,
                                query=query,
                                context=context,
                                multi_product_results=multi_product_results,
                            )
                            output_len = len(verified_response.get('output', '')) if isinstance(verified_response, dict) else len(verified_response.output or '')
                            logger.info(f"[LearningLLM] Built verified response, output_len={output_len}")
                            return verified_response
                        else:
                            # Medium confidence - will continue to Summary-First/Vector search
                            # but enrich with Learning LLM context
                            logger.info(f"[LearningLLM] Moderate verification ({verification_score:.2f}), continuing to vector search")
                    else:
                        logger.info("[LearningLLM] Verification failed, falling back to vector search")
                else:
                    logger.info(f"[LearningLLM] Low confidence ({llm_confidence:.2f}), skipping")

        # =============================================================
        # SUMMARY-FIRST SEARCH: BM25 over summaries before vector search
        # =============================================================
        # Phase 0: Summary-first search for error codes, commands, terms
        # This provides fast (<50ms) accurate retrieval before expensive vector search
        summary_first_result = await self._summary_first_search(
            query=search_query,
            context=context,
        )

        if summary_first_result:
            confidence = summary_first_result.get("confidence", "low")
            summary_results = summary_first_result.get("results", [])

            # Detect query intent and check if results match
            # Use original_user_query for intent detection to avoid encoding issues
            intent_query = original_user_query if original_user_query else query
            query_intents = _detect_query_intent(intent_query)
            result_types = set(r.get("type", "") for r in summary_results)
            intent_matches = _check_intent_result_match(query_intents, summary_results, intent_query)
            print(f"[SummaryFirst] Intent detection: intent_query='{intent_query[:50]}', intents={query_intents}, result_types={result_types}, matches={intent_matches}")

            if confidence == "high" and summary_results and intent_matches:
                # High confidence AND intent matches: return summary results directly
                logger.info(f"[SummaryFirst] High confidence match, intent={query_intents}, returning {len(summary_results)} summary results")
                return await self._build_response_from_summaries(
                    summary_result=summary_first_result,
                    query=query,
                    context=context,
                )
            elif confidence == "high" and summary_results and not intent_matches:
                # High confidence but intent mismatch: fall back to vector search
                result_types = set(r.get("type", "") for r in summary_results)
                logger.info(f"[SummaryFirst] Intent mismatch - query_intent={query_intents}, result_types={result_types}, falling back to vector search")

            elif confidence == "medium" and summary_results and intent_matches:
                # Medium confidence with intent match: enrich query with summary context for vector search
                context_string = summary_first_result.get("context_string", "")
                if context_string:
                    search_query = f"{search_query}\n\n컨텍스트: {context_string}"
                    logger.info(f"[SummaryFirst] Medium confidence, intent={query_intents}, enriching query with summary context")

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

                # Phase 2.4: Graph traversal search (keyword-based)
                if search_mode == "hybrid":
                    graph_results = await self._graph_traversal_search(
                        query=original_query or query,
                        top_k=top_k
                    )
                    logger.debug(f"Graph traversal returned {len(graph_results)} results")

                    # Merge graph results into neo4j_results for RRF fusion
                    if graph_results:
                        existing_ids = {r.get("chunk_id") for r in neo4j_results if r.get("chunk_id")}
                        for gr in graph_results:
                            if gr.get("chunk_id") not in existing_ids:
                                # Add graph results with adjusted rank
                                gr["neo4j_rank"] = len(neo4j_results) + gr.get("graph_rank", 1)
                                neo4j_results.append(gr)
                        logger.info(f"[UnifiedSearch] Merged {len(graph_results)} graph results")

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

            # Phase 3: Result Fusion
            if search_mode == "hybrid":
                if ENABLE_RRF_FUSION:
                    # Full RRF fusion with score calculation
                    fused_results = self._rrf_fusion(
                        neo4j_results=neo4j_results,
                        postgres_results=postgres_results,
                        error_codes=error_codes,
                        prioritize_web=prioritize_web_sources
                    )
                else:
                    # RRF disabled: Use Neo4j results, mark keyword matches from PostgreSQL
                    fused_results = self._simple_hybrid_merge(
                        neo4j_results=neo4j_results,
                        postgres_results=postgres_results,
                        error_codes=error_codes
                    )
                    logger.info(f"[UnifiedSearch] RRF disabled, using simple hybrid merge")
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

            # Add multi-product results for platform comparison
            try:
                multi_product_results = await self._get_multi_product_results(query, top_k=5)
                if multi_product_results:
                    result_metadata["multi_product"] = True
                    result_metadata["multi_product_results"] = multi_product_results
                    result_metadata["has_platform_differences"] = any(
                        mpr.get("has_differences", False) for mpr in multi_product_results
                    )
                    logger.info(f"[UnifiedSearch] Added {len(multi_product_results)} multi-product results")
            except Exception as mpr_err:
                logger.warning(f"[UnifiedSearch] Failed to get multi-product results: {mpr_err}")

            return self.create_success_result(
                "\n".join(output_parts),
                metadata=result_metadata
            )

        except Exception as e:
            logger.error(f"Unified search error: {e}", exc_info=True)
            return self.create_error_result(f"Unified search error: {str(e)}")

    # =============================================================
    # LEARNING LLM INTEGRATION METHODS
    # =============================================================

    async def _try_learning_llm(
        self,
        query: str,
        context: Optional[AgentContext] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fine-tuned Learning LLM으로 답변 시도

        Learning LLM은 Summaries 데이터로 학습되어 에러코드, 명령어,
        용어 관련 질문에 직접 답변할 수 있습니다.

        Returns:
            Dict with 'answer', 'confidence', 'mentioned_codes', 'mentioned_terms'
            or None if LLM is not available
        """
        try:
            # Use Learning LLM service (which manages the adapter lifecycle)
            from app.api.services.learning_llm_service import get_learning_llm_service

            service = get_learning_llm_service()
            if not service or not service.enabled:
                logger.debug("[LearningLLM] Service not available or disabled")
                return None

            # Check if service is initialized and has adapter
            if not service._is_initialized or not service._adapter:
                logger.debug("[LearningLLM] Service not initialized")
                return None

            # Build context string from conversation history (if available)
            context_str = None
            if context and context.metadata:
                # Use recent conversation context if available
                history = context.metadata.get("conversation_history", [])
                if history:
                    recent = history[-3:] if len(history) > 3 else history
                    context_str = "\n".join([
                        f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                        for msg in recent
                    ])

            # Call Learning LLM with confidence scoring via adapter
            logger.info(f"[LearningLLM] Generating answer for: {query[:50]}...")
            result = await service._adapter.generate_with_confidence(
                question=query,
                context=context_str,
                max_new_tokens=1024,
                temperature=0.3,  # Low temperature for consistent answers
            )

            if not result or not result.answer:
                logger.debug("[LearningLLM] No result or empty answer")
                return None

            logger.info(f"[LearningLLM] Generated: answer_len={len(result.answer)}, confidence={result.confidence:.2f}")

            return {
                "answer": result.answer,
                "confidence": result.confidence,
                "mentioned_codes": result.mentioned_codes,
                "mentioned_terms": result.mentioned_terms,
                "mentioned_commands": result.mentioned_commands,
                "raw_response": result.raw_response,
            }

        except ImportError as e:
            logger.warning(f"[LearningLLM] Import error: {e}")
            return None
        except Exception as e:
            logger.warning(f"[LearningLLM] Exception: {e}")
            return None

    async def _verify_with_summaries(
        self,
        learning_llm_result: Dict[str, Any],
        context: Optional[AgentContext] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Summary 데이터로 Learning LLM 답변 검증

        Learning LLM이 생성한 답변에서 언급된 에러코드, 명령어, 용어가
        실제 Summary 데이터에 존재하는지 확인합니다.

        Returns:
            Dict with 'is_valid', 'verification_score', 'source_references'
            or None if verification service is not available
        """
        try:
            # Lazy import to avoid circular dependencies
            from app.api.services.answer_verification_service import (
                get_answer_verification_service
            )

            service = get_answer_verification_service()

            answer = learning_llm_result.get("answer", "")
            mentioned_codes = learning_llm_result.get("mentioned_codes", [])
            mentioned_terms = learning_llm_result.get("mentioned_terms", [])
            mentioned_commands = learning_llm_result.get("mentioned_commands", [])

            result = await service.verify_answer(
                answer=answer,
                mentioned_codes=mentioned_codes,
                mentioned_terms=mentioned_terms,
                mentioned_commands=mentioned_commands,
            )

            return result.to_dict()

        except ImportError as e:
            logger.debug(f"[LearningLLM] Verification service import error: {e}")
            return None
        except Exception as e:
            logger.warning(f"[LearningLLM] Verification error: {e}")
            return None

    async def _build_learning_llm_response(
        self,
        learning_llm_result: Dict[str, Any],
        verification_result: Dict[str, Any],
        query: str,
        context: Optional[AgentContext] = None,
        multi_product_results: Optional[List[Dict[str, Any]]] = None,
    ) -> ToolResult:
        """
        검증된 Learning LLM 응답을 ToolResult로 변환

        PDF 페이지 인용과 함께 검증된 답변을 반환합니다.
        """
        answer = learning_llm_result.get("answer", "")
        confidence = learning_llm_result.get("confidence", 0.0)
        verification_score = verification_result.get("verification_score", 0.0)
        source_references = verification_result.get("source_references", [])
        additional_context = verification_result.get("additional_context", "")

        # Build output text
        output_parts = []
        output_parts.append(f"📚 Knowledge Base Answer (Confidence: {confidence:.0%}, Verified: {verification_score:.0%})")
        output_parts.append("")
        output_parts.append(answer)

        # Add verification context
        if additional_context:
            output_parts.append("")
            output_parts.append("📋 Verified Context:")
            output_parts.append(additional_context)

        # Add source references
        if source_references:
            output_parts.append("")
            output_parts.append("📖 Sources:")
            for ref in source_references[:5]:
                ref_type = ref.get("type", "document")
                if ref_type == "error_code":
                    output_parts.append(
                        f"  • Error {ref.get('code')}: {ref.get('source_pdf')} "
                        f"(p.{ref.get('page_numbers', ['?'])[0] if ref.get('page_numbers') else '?'})"
                    )
                elif ref_type == "command":
                    output_parts.append(
                        f"  • Command {ref.get('name')}: {ref.get('source_pdf')} "
                        f"(p.{ref.get('page_numbers', ['?'])[0] if ref.get('page_numbers') else '?'})"
                    )
                elif ref_type == "term":
                    output_parts.append(
                        f"  • Term {ref.get('name')}: {ref.get('source_pdf')}"
                    )

        # Build metadata
        result_metadata = {
            "source": "learning_llm",
            "query": query,
            "confidence": confidence,
            "verification_score": verification_score,
            "verified_codes": verification_result.get("verified_codes", []),
            "verified_terms": verification_result.get("verified_terms", []),
            "verified_commands": verification_result.get("verified_commands", []),
            "unverified_codes": verification_result.get("unverified_codes", []),
            "hallucination_patterns": verification_result.get("hallucination_patterns", []),
            "sources": [
                {
                    "source": ref.get("source_pdf", "Learning LLM"),
                    "page_number": ref.get("page_numbers", [1])[0] if ref.get("page_numbers") else 1,
                    "content": f"{ref.get('type')}: {ref.get('code') or ref.get('name')}",
                    "source_type": "verified_knowledge",
                }
                for ref in source_references
            ],
        }

        # Add multi-product results for platform comparison
        if multi_product_results:
            result_metadata["multi_product"] = True
            result_metadata["multi_product_results"] = multi_product_results
            result_metadata["has_platform_differences"] = any(
                mpr.get("has_differences", False) for mpr in multi_product_results
            )
            logger.info(f"[LearningLLM] Added {len(multi_product_results)} multi-product results to metadata")

        # Store sources in context metadata
        if context and context.metadata is not None:
            if 'sources' not in context.metadata:
                context.metadata['sources'] = []
            context.metadata['sources'].extend(result_metadata["sources"])

        return self.create_success_result(
            "\n".join(output_parts),
            metadata=result_metadata
        )
