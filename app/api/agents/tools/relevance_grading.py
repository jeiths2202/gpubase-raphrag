"""Relevance Grading Module

Contains RAG accuracy relevance grading functionality.
"""
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


async def apply_relevance_grading(
    enriched_results: List[Dict[str, Any]],
    query: str,
    original_user_query: str,
    enable_grading: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Apply relevance grading to filter out irrelevant results.

    This prevents hallucinations like "osc.conf -> tjes.conf"
    by grading each result's relevance to the query.

    Args:
        enriched_results: Results to grade
        query: Search query (possibly modified by LLM)
        original_user_query: Original user query
        enable_grading: Whether grading is enabled

    Returns:
        Tuple of (graded_results, grading_metadata)
    """
    grading_metadata: Dict[str, Any] = {}

    if not enable_grading or not enriched_results:
        return enriched_results, grading_metadata

    try:
        from ...services.rag_accuracy_pipeline import get_rag_accuracy_pipeline

        rag_pipeline = get_rag_accuracy_pipeline()

        # Use original query for analysis (not LLM-modified)
        grading_query = original_user_query or query

        # Grade results
        grading_result, graded_results = rag_pipeline.grade_search_results(
            query=grading_query,
            search_results=enriched_results,
        )

        # Store grading metadata
        grading_metadata = {
            "relevance_grading_enabled": True,
            "relevant_count": grading_result.relevant_count,
            "partial_count": grading_result.partial_count,
            "irrelevant_count": grading_result.irrelevant_count,
            "exact_match_type": grading_result.query_analysis.exact_match_type.value,
            "exact_match_value": grading_result.query_analysis.exact_match_value,
            "primary_intent": grading_result.query_analysis.primary_intent.value,
        }

        # Replace with graded results (filtered)
        if graded_results:
            logger.info(
                f"[RAGAccuracy] Filtered to {len(graded_results)} results "
                f"(relevant={grading_result.relevant_count}, partial={grading_result.partial_count})"
            )
            return graded_results, grading_metadata
        else:
            # All results were irrelevant - keep originals but warn
            logger.warning(
                f"[RAGAccuracy] All {len(enriched_results)} results graded as irrelevant, "
                f"exact_match={grading_result.query_analysis.exact_match_value}"
            )
            grading_metadata["all_irrelevant"] = True
            return enriched_results, grading_metadata

    except Exception as grading_err:
        logger.error(f"[RAGAccuracy] Grading failed: {grading_err}")
        grading_metadata["grading_error"] = str(grading_err)
        return enriched_results, grading_metadata
