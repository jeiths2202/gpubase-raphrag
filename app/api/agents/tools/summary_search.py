"""Summary Search Module

Contains Summary-First search, multi-product search, and Vision enrichment.
"""
import logging
from typing import Dict, Any, Optional, List

from ..types import ToolResult, AgentContext
from .unified_search_base import ENABLE_VISION_ENRICHMENT

# Re-export build_response_from_summaries for backward compatibility
from .summary_response_builder import build_response_from_summaries

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    'summary_first_search',
    'get_multi_product_results',
    'try_vision_enrichment',
    'build_response_from_summaries',
]


async def summary_first_search(
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


async def get_multi_product_results(
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


async def try_vision_enrichment(
    query: str,
    summary_results: List[Dict[str, Any]],
    context: AgentContext,
) -> Optional[Dict[str, Any]]:
    """
    Try to enrich summary results with Vision LLM analysis.

    Analyzes PDF pages referenced in summary results using MiniCPM-V
    to extract tables, charts, and detailed visual content.

    Args:
        query: Original user query
        summary_results: Results from summary search
        context: Agent context

    Returns:
        Vision enrichment result or None if not applicable/failed
    """
    if not ENABLE_VISION_ENRICHMENT:
        return None

    # Check if results are suitable for vision analysis
    vision_worthy_types = {"command", "error_code", "config", "api", "glossary", "term"}
    has_vision_worthy = any(
        r.get("type") in vision_worthy_types or r.get("source_pdf") or r.get("page_numbers")
        for r in summary_results
    )

    if not has_vision_worthy and not summary_results:
        logger.debug("[VisionEnrichment] No vision-worthy results, skipping")
        return None

    try:
        from ...services.vision_knowledge_service import get_vision_knowledge_service

        vision_service = get_vision_knowledge_service()

        # Detect language from context or query
        language = "ja"  # Default to Japanese
        if context and context.language:
            language = context.language
        elif any(c in query for c in "가나다라마바사아자차카타파하"):
            language = "ko"
        elif all(ord(c) < 128 for c in query.replace(" ", "")):
            language = "en"

        # Call Vision Knowledge Service
        result = await vision_service.search_with_vision(
            query=query,
            language=language,
            max_pages=3,
        )

        if result.get("type") == "vision_enriched":
            return result

        return None

    except ImportError as ie:
        logger.warning(f"[VisionEnrichment] Service not available: {ie}")
        return None
    except Exception as e:
        logger.error(f"[VisionEnrichment] Error: {e}")
        return None
