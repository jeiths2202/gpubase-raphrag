"""Response Builder Module

Contains functions for building search result output and metadata.
"""
import json
import logging
from typing import Dict, Any, Optional, List, Set

from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


def format_enriched_results_output(
    enriched_results: List[Dict[str, Any]],
    clip_images: List[Dict[str, Any]],
    exact_phrases: List[str],
    prioritize_web_sources: bool,
) -> List[str]:
    """
    Format enriched results into output text parts.

    Args:
        enriched_results: Enriched search results
        clip_images: CLIP image search results
        exact_phrases: Exact phrases from query
        prioritize_web_sources: Whether web sources are prioritized

    Returns:
        List of output text parts
    """
    output_parts = []

    # Header
    if exact_phrases:
        exact_count = sum(1 for r in enriched_results if r.get("exact_phrase_match"))
        output_parts.append(
            f"[Exact Phrase Mode] Found {len(enriched_results)} result(s) - "
            f"{exact_count} exact match(es) for \"{' '.join(exact_phrases)}\":\n"
        )
    elif prioritize_web_sources:
        output_parts.append(
            f"[Web Priority Mode] Found {len(enriched_results)} relevant result(s) - "
            f"web sources prioritized:\n"
        )
    else:
        output_parts.append(f"Found {len(enriched_results)} relevant result(s) via unified search:\n")

    # Format each result
    for result in enriched_results:
        chunk_info = _format_single_result(result)
        output_parts.append(chunk_info)

    # Add image info
    if clip_images:
        output_parts.append(f"\n{len(clip_images)} query-matched image(s):")
        for img in clip_images[:5]:
            output_parts.append(
                f"  - Image: {img['image_id']} (Page {img['page_number']}, "
                f"Similarity: {img['similarity']:.1%})\n"
                f"    URL: {img['url']}"
            )

    return output_parts


def _format_single_result(result: Dict[str, Any]) -> str:
    """Format a single search result into text."""
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
        chunk_info += f"   Web Source: {result_source_url}\n"

    if error_boosted:
        chunk_info += f"   KEYWORD MATCH - ANSWER IS IN CONTENT BELOW:\n"

    # Show exact phrase match status
    if result.get("exact_phrase_match"):
        chunk_info += f"   EXACT PHRASE MATCH - HIGH PRIORITY RESULT\n"
    elif result.get("exact_phrase_partial"):
        chunk_info += f"   Partial phrase match\n"

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

    return chunk_info


def build_sources_list(
    enriched_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build sources list from enriched results for metadata.

    Args:
        enriched_results: Enriched search results

    Returns:
        List of source dictionaries
    """
    sources = []
    seen_sources: Set[str] = set()

    for result in enriched_results:
        source = result.get("source", {})
        doc_name = source.get("document_name", "Unknown")
        page_start = source.get("page_start")
        page_end = source.get("page_end")
        doc_id = source.get("doc_id", "")
        source_type = source.get("source_type", "document")
        source_url = source.get("source_url", "")
        content = result.get("content", "")
        rrf_score = result.get("rrf_score", 0)

        # Create unique key
        source_key = f"{doc_id}:{page_start}:{page_end}"
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        # Format page display
        if page_start:
            if page_start == page_end or not page_end:
                page_display = f"p.{page_start}"
            else:
                page_display = f"p.{page_start}-{page_end}"
            source_display = f"{doc_name} ({page_display})"
        else:
            source_display = doc_name

        sources.append({
            "source": source_display,
            "score": rrf_score,
            "page_number": page_start,
            "content": content[:200] if content else "",
            "doc_id": doc_id,
            "source_type": source_type,
            "source_url": source_url,
        })

    return sources


def build_result_metadata(
    enriched_results: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    query: str,
    search_mode: str,
    grading_metadata: Dict[str, Any],
    query_was_corrected: bool,
    original_query: str,
    exact_phrases: List[str],
    prioritize_web_sources: bool,
    multi_product_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build result metadata dictionary.

    Args:
        enriched_results: Enriched search results
        sources: Built sources list
        query: Search query
        search_mode: Search mode used
        grading_metadata: RAG accuracy grading metadata
        query_was_corrected: Whether query was corrected
        original_query: Original user query
        exact_phrases: Exact phrases from query
        prioritize_web_sources: Whether web sources are prioritized
        multi_product_results: Multi-product aggregation results

    Returns:
        Result metadata dictionary
    """
    metadata = {
        "results_count": len(enriched_results),
        "query": query,
        "search_mode": search_mode,
        "sources": sources,
        "individual_results": enriched_results,
        "exact_phrase_mode": bool(exact_phrases),
        "exact_phrases": exact_phrases,
        "web_priority_mode": prioritize_web_sources,
    }

    # Add query correction info
    if query_was_corrected:
        metadata["query_corrected"] = True
        metadata["original_query"] = original_query

    # Add grading metadata
    if grading_metadata:
        metadata.update(grading_metadata)

    # Add multi-product results
    if multi_product_results:
        metadata["multi_product"] = True
        metadata["multi_product_results"] = multi_product_results
        metadata["has_platform_differences"] = any(
            mpr.get("has_differences", False) for mpr in multi_product_results
        )

    return metadata


def build_unified_search_result(
    enriched_results: List[Dict[str, Any]],
    clip_images: List[Dict[str, Any]],
    query: str,
    search_mode: str,
    context: AgentContext,
    grading_metadata: Dict[str, Any],
    query_was_corrected: bool,
    original_query: str,
    exact_phrases: List[str],
    prioritize_web_sources: bool,
    multi_product_results: Optional[List[Dict[str, Any]]],
    create_success_result_fn,
) -> ToolResult:
    """
    Build the final ToolResult for unified search.

    Args:
        enriched_results: Enriched search results
        clip_images: CLIP image search results
        query: Search query
        search_mode: Search mode used
        context: Agent context
        grading_metadata: RAG accuracy grading metadata
        query_was_corrected: Whether query was corrected
        original_query: Original user query
        exact_phrases: Exact phrases from query
        prioritize_web_sources: Whether web sources are prioritized
        multi_product_results: Multi-product aggregation results
        create_success_result_fn: Function to create ToolResult

    Returns:
        ToolResult with formatted output and metadata
    """
    # Format output text
    output_parts = format_enriched_results_output(
        enriched_results=enriched_results,
        clip_images=clip_images,
        exact_phrases=exact_phrases,
        prioritize_web_sources=prioritize_web_sources,
    )

    # Build sources list
    sources = build_sources_list(enriched_results)

    # Store sources in context metadata
    if context and context.metadata is not None:
        if 'sources' not in context.metadata:
            context.metadata['sources'] = []
        context.metadata['sources'].extend(sources)

    # Build result metadata
    result_metadata = build_result_metadata(
        enriched_results=enriched_results,
        sources=sources,
        query=query,
        search_mode=search_mode,
        grading_metadata=grading_metadata,
        query_was_corrected=query_was_corrected,
        original_query=original_query,
        exact_phrases=exact_phrases,
        prioritize_web_sources=prioritize_web_sources,
        multi_product_results=multi_product_results,
    )

    return create_success_result_fn(
        "\n".join(output_parts),
        metadata=result_metadata
    )
