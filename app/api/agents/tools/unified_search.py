"""
Unified Search Tool - Orchestrator
Combines Neo4j vector search with PostgreSQL structure metadata.

This module serves as the main orchestrator, delegating to component modules:
- query_preprocessing: Query validation and semantic analysis
- summary_search: Summary-first BM25 search
- database_search: Neo4j and PostgreSQL search
- search_fusion: Result fusion algorithms
- structure_enrichment: Section/table enrichment
- clip_search: CLIP image search
- learning_llm: Fine-tuned LLM answers
- relevance_grading: RAG accuracy grading
- response_builder: Output formatting
"""
import logging
from typing import Dict, Any, Optional, List

from ..types import ToolResult, AgentContext
from .adaptive_search import _extract_error_codes
from ...services.scoring_config_service import get_scoring_config_sync

# Import base class with constants
from .unified_search_base import (
    UnifiedSearchBase,
    ENABLE_RAG_ACCURACY_GRADING,
    ENABLE_LEARNING_LLM,
    LEARNING_LLM_MIN_CONFIDENCE,
    LEARNING_LLM_VERIFICATION_THRESHOLD,
    DEFAULT_TOP_K,
    DEFAULT_SEARCH_MODE,
    ENABLE_RRF_FUSION,
    SEMANTIC_QUERY_PREPROCESSING,
)

# Import component modules
from .query_preprocessing import (
    preprocess_query,
    enhance_query_with_entities,
    merge_detected_with_semantic,
)
from .unified_search_utils import detect_query_intent, check_intent_result_match
from .search_fusion import (
    rrf_fusion,
    simple_hybrid_merge,
    apply_web_priority,
    apply_exact_phrase_priority,
)
from .summary_search import (
    summary_first_search,
    get_multi_product_results,
    try_vision_enrichment,
    build_response_from_summaries,
)
from .database_search import (
    neo4j_vector_search,
    postgres_keyword_search,
    exact_phrase_search,
)
from .chunk_processing import fetch_linked_chunks
from .clip_search import clip_image_search, extract_relevant_pages
from .structure_enrichment import enrich_with_structure
from .learning_llm import (
    try_learning_llm,
    verify_with_summaries,
    build_learning_llm_response,
)
from .response_builder import build_unified_search_result
from .relevance_grading import apply_relevance_grading

logger = logging.getLogger(__name__)


class UnifiedSearchTool(UnifiedSearchBase):
    """
    Unified Search Tool combining Neo4j accuracy with PostgreSQL structure.

    Orchestrates multiple search strategies:
    - Learning LLM for domain-specific answers
    - Summary-First BM25 search for exact matches
    - Neo4j vector search + PostgreSQL keyword search
    - RRF fusion and relevance grading
    """

    async def execute(
        self,
        query: str,
        context: AgentContext,
        top_k: int = DEFAULT_TOP_K,
        doc_filter: Optional[str] = None,
        include_images: bool = True,
        include_tables: bool = True,
        search_mode: str = DEFAULT_SEARCH_MODE,
        **kwargs,
    ) -> ToolResult:
        """Execute unified search combining multiple search strategies."""
        scoring_config = get_scoring_config_sync()

        # Phase 0: Query Preprocessing
        query, search_query, query_state = preprocess_query(
            query=query,
            context=context,
            query_understanding_service=self.query_understanding_service,
            enable_semantic_preprocessing=SEMANTIC_QUERY_PREPROCESSING,
        )

        if not query:
            return self.create_error_result("Query is required")

        original_user_query = query_state["original_user_query"]
        exact_phrases = query_state["exact_phrases"]
        prioritize_web_sources = query_state["prioritize_web_sources"]
        query_was_corrected = query_state["query_was_corrected"]
        semantic_entities = query_state["semantic_entities"]

        # Phase -1: Learning LLM
        if ENABLE_LEARNING_LLM:
            llm_result = await self._try_learning_llm_phase(search_query, context)
            if llm_result:
                return llm_result

        # Phase 0.5: Summary-First Search
        summary_result = await self._try_summary_first_phase(
            search_query, original_user_query, query, context, semantic_entities
        )
        if summary_result:
            return summary_result

        # Phase 1-5: Main Search Pipeline
        return await self._execute_main_pipeline(
            query, search_query, context, top_k, doc_filter,
            include_images, include_tables, search_mode, scoring_config,
            original_user_query, exact_phrases, prioritize_web_sources, query_was_corrected,
        )

    async def _try_learning_llm_phase(
        self, search_query: str, context: AgentContext
    ) -> Optional[ToolResult]:
        """Try Learning LLM for domain-specific answers."""
        result = await try_learning_llm(query=search_query, context=context)
        if not result:
            return None

        confidence = result.get("confidence", 0.0)
        if confidence < LEARNING_LLM_MIN_CONFIDENCE:
            return None

        verification = await verify_with_summaries(result, context)
        if not verification or not verification.get("is_valid"):
            return None

        if verification.get("verification_score", 0.0) < LEARNING_LLM_VERIFICATION_THRESHOLD:
            return None

        multi_product = await get_multi_product_results(search_query, top_k=5)
        return build_learning_llm_response(
            result, verification, search_query, context, multi_product, self.create_success_result
        )

    async def _try_summary_first_phase(
        self, search_query: str, original_user_query: str, query: str,
        context: AgentContext, semantic_entities: list
    ) -> Optional[ToolResult]:
        """Try Summary-First search before vector search."""
        enhanced_query = enhance_query_with_entities(search_query, semantic_entities)
        summary_result = await summary_first_search(query=enhanced_query, context=context)

        if not summary_result:
            return None

        confidence = summary_result.get("confidence", "low")
        summary_results = summary_result.get("results", [])
        intent_query = original_user_query or query
        query_intents = detect_query_intent(intent_query)
        intent_matches = check_intent_result_match(query_intents, summary_results, intent_query)

        detected_commands = summary_result.get("detected_commands", [])
        detected_error_codes = summary_result.get("detected_error_codes", [])
        detected_commands, detected_error_codes = merge_detected_with_semantic(
            detected_commands, detected_error_codes, semantic_entities
        )

        has_specific_match = detected_commands or detected_error_codes
        should_return = (
            confidence in ("high", "medium") and intent_matches and
            has_specific_match and summary_results
        )

        if not should_return:
            return None

        multi_product = await get_multi_product_results(search_query, top_k=5)
        vision = await try_vision_enrichment(search_query, summary_results, context)
        return build_response_from_summaries(
            summary_result, query, context, multi_product, vision, self.create_success_result
        )

    async def _execute_main_pipeline(
        self, query: str, search_query: str, context: AgentContext,
        top_k: int, doc_filter: Optional[str], include_images: bool,
        include_tables: bool, search_mode: str, scoring_config,
        original_user_query: str, exact_phrases: List[str],
        prioritize_web_sources: bool, query_was_corrected: bool,
    ) -> ToolResult:
        """Execute main search pipeline."""
        error_codes = _extract_error_codes(query)
        language = context.language if context and context.language else "ja"

        # Phase 2: Parallel Search
        neo4j_results, postgres_results = [], []
        if search_mode in ("hybrid", "vector_only"):
            neo4j_results = await neo4j_vector_search(
                self.rag_service, query, top_k, language, context
            )
        if search_mode in ("hybrid", "keyword_only"):
            postgres_results = await postgres_keyword_search(
                query, top_k, doc_filter, error_codes, scoring_config
            )

        # Phase 2.5: Exact Phrase Search
        exact_results = []
        if exact_phrases:
            exact_results = await exact_phrase_search(exact_phrases, top_k, prioritize_web_sources)

        # Phase 2.7: Chunk Linking
        if prioritize_web_sources and neo4j_results:
            neo4j_results = await fetch_linked_chunks(neo4j_results, 2, True, scoring_config)

        # Phase 3: Result Fusion
        fused_results = self._fuse_results(
            neo4j_results, postgres_results, search_mode, scoring_config
        )
        if prioritize_web_sources:
            fused_results = apply_web_priority(fused_results)
        if exact_phrases:
            fused_results = apply_exact_phrase_priority(fused_results, exact_phrases)

        # Phase 3.6: Context Pollution Prevention
        fused_results = self._apply_chunk_filter(fused_results, original_user_query, query)

        # Phase 3.7: CLIP Image Search
        clip_images = []
        if include_images:
            clip_images = await self._execute_clip_search(query, fused_results, doc_filter, top_k)

        # Phase 4: Structure Enrichment
        enriched_results, _ = await enrich_with_structure(
            fused_results, clip_images, include_tables, top_k
        )

        # Phase 4.5: Relevance Grading
        enriched_results, grading_metadata = await apply_relevance_grading(
            enriched_results, query, original_user_query, ENABLE_RAG_ACCURACY_GRADING
        )

        # Phase 5: Build Final Result
        multi_product = await get_multi_product_results(search_query, top_k=3)
        return build_unified_search_result(
            enriched_results, clip_images, query, search_mode, context,
            grading_metadata, query_was_corrected, original_user_query,
            exact_phrases, prioritize_web_sources, multi_product, self.create_success_result
        )

    def _fuse_results(
        self, neo4j_results: List[Dict], postgres_results: List[Dict],
        search_mode: str, scoring_config
    ) -> List[Dict]:
        """Fuse results from different search sources."""
        if search_mode == "vector_only":
            return neo4j_results
        if search_mode == "keyword_only":
            return postgres_results
        if ENABLE_RRF_FUSION and neo4j_results and postgres_results:
            return rrf_fusion(neo4j_results, postgres_results, scoring_config)
        if neo4j_results:
            return simple_hybrid_merge(neo4j_results, postgres_results)
        return postgres_results

    def _apply_chunk_filter(
        self, results: List[Dict], original_query: str, query: str
    ) -> List[Dict]:
        """Apply context pollution prevention filter."""
        try:
            from app.api.services.chunk_filter_service import get_chunk_filter_service
            chunk_filter = get_chunk_filter_service()
            return chunk_filter.filter_by_query_entity(original_query or query, results)
        except Exception as e:
            logger.warning(f"[ChunkFilter] Filtering failed: {e}")
            return results

    async def _execute_clip_search(
        self, query: str, fused_results: List[Dict],
        doc_filter: Optional[str], top_k: int
    ) -> List[Dict]:
        """Execute CLIP image search if applicable."""
        relevant_pages_by_doc = extract_relevant_pages(fused_results)
        relevant_doc_id = next(
            (r.get("doc_id") or r.get("pdf_id") for r in fused_results[:top_k]
             if r.get("doc_id") or r.get("pdf_id")), None
        )

        target_doc_id = doc_filter or relevant_doc_id
        if not target_doc_id or target_doc_id not in relevant_pages_by_doc:
            return []

        clip_service = await self._get_clip_service()
        if not clip_service:
            return []

        return await clip_image_search(
            clip_service, query, relevant_pages_by_doc[target_doc_id], target_doc_id, 5
        )
