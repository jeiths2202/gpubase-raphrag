"""Summary Response Builder Module

Contains functions for building ToolResult from summary search results.
"""
import logging
from typing import Dict, Any, Optional, List, Set

from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


def build_response_from_summaries(
    summary_result: Dict[str, Any],
    query: str,
    context: AgentContext,
    multi_product_results: List[Dict[str, Any]],
    vision_enrichment: Optional[Dict[str, Any]],
    create_success_result_fn,
) -> ToolResult:
    """
    Build a ToolResult from summary search results.

    Args:
        summary_result: Result from summary_first_search
        query: Original query
        context: Agent context
        multi_product_results: Multi-product aggregation results
        vision_enrichment: Vision analysis results
        create_success_result_fn: Function to create ToolResult

    Returns:
        ToolResult with formatted summary results
    """
    results = summary_result.get("results", [])
    confidence = summary_result.get("confidence", "high")
    page_references = summary_result.get("page_references", [])

    # Build output text
    output_parts = [
        f"[Summary-First Search] Found {len(results)} direct match(es) with {confidence} confidence:\n"
    ]

    enriched_results = []
    for i, result in enumerate(results[:5]):
        chunk_info = _format_summary_result(i, result)
        output_parts.append(chunk_info)
        enriched_results.append(_build_enriched_result(i, result))

    # Add page reference info
    if page_references:
        _add_page_references(output_parts, page_references)

    # Build sources list
    sources = _build_sources_list(results)

    # Store sources in context
    if context.metadata is None:
        context.metadata = {}
    if 'sources' not in context.metadata:
        context.metadata['sources'] = []
    context.metadata['sources'].extend(sources)

    # Check platform differences
    has_platform_differences = any(
        mpr.get("has_differences", False) for mpr in multi_product_results
    )

    # Build product sections
    product_sections = _build_product_sections(multi_product_results)

    # Add Vision enrichment to output
    _add_vision_enrichment(output_parts, vision_enrichment)

    # Build result metadata
    result_metadata = _build_result_metadata(
        enriched_results, query, confidence, sources, summary_result,
        multi_product_results, product_sections, has_platform_differences,
        vision_enrichment
    )

    return create_success_result_fn(
        "\n".join(output_parts),
        metadata=result_metadata
    )


def _format_summary_result(index: int, result: Dict[str, Any]) -> str:
    """Format a single summary result into text."""
    result_type = result.get("type", "unknown")
    name = result.get("name", "Unknown")
    description = result.get("description", "")
    content = result.get("content", "")
    source_file = result.get("source_file", "")
    page_numbers = result.get("page_numbers", [])
    score = result.get("score", 0)

    # Format based on type
    if result_type == "error-codes":
        chunk_info = f"\n{index+1}. [ERROR CODE] {name}\n"
        chunk_info += f"   Score: {score:.2f}\n"
        if description:
            chunk_info += f"   Description: {description}\n"
        solution = result.get("solution") or ""
        if solution:
            chunk_info += f"   Solution: {solution}\n"

    elif result_type == "commands":
        chunk_info = f"\n{index+1}. [COMMAND] {name}\n"
        chunk_info += f"   Score: {score:.2f}\n"
        if description:
            chunk_info += f"   Description: {description[:200]}\n"
        syntax = result.get("syntax") or ""
        if syntax:
            chunk_info += f"   Syntax: {syntax}\n"
        products = result.get("products") or result.get("product") or ""
        if products:
            if isinstance(products, list):
                products = ", ".join(products)
            chunk_info += f"   Products: {products}\n"

    elif result_type == "glossary":
        chunk_info = f"\n{index+1}. [TERM] {name}\n"
        chunk_info += f"   Score: {score:.2f}\n"
        full_name = result.get("full_name") or ""
        if full_name:
            chunk_info += f"   Full Name: {full_name}\n"
        if description:
            chunk_info += f"   Description: {description}\n"

    elif result_type == "apis":
        chunk_info = f"\n{index+1}. [API] {name}\n"
        chunk_info += f"   Score: {score:.2f}\n"
        if description:
            chunk_info += f"   Description: {description[:200]}\n"
        syntax = result.get("syntax") or ""
        if syntax:
            chunk_info += f"   Prototype: {syntax}\n"

    else:
        chunk_info = f"\n{index+1}. [{result_type.upper()}] {name}\n"
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

    return chunk_info


def _build_enriched_result(index: int, result: Dict[str, Any]) -> Dict[str, Any]:
    """Build enriched result dictionary for metadata."""
    result_type = result.get("type", "unknown")
    name = result.get("name", "Unknown")
    description = result.get("description", "")
    content = result.get("content", "")
    source_file = result.get("source_file", "")
    source_pdf = result.get("source_pdf", "")
    page_numbers = result.get("page_numbers", [])
    score = result.get("score", 0)

    return {
        "index": index + 1,
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
    }


def _add_page_references(output_parts: List[str], page_references: List[Dict]) -> None:
    """Add page reference info to output."""
    output_parts.append(f"\nPage References ({len(page_references)} page(s)):")
    seen_refs: Set[str] = set()
    for ref in page_references[:5]:
        ref_key = f"{ref.get('pdf_path')}:{ref.get('page_number')}"
        if ref_key not in seen_refs:
            seen_refs.add(ref_key)
            output_parts.append(f"  - {ref.get('pdf_path')} p.{ref.get('page_number')}")


def _build_sources_list(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build sources list from results."""
    sources = []
    seen_sources: Set[str] = set()

    for result in results[:5]:
        source_file = result.get("source_file", "")
        source_pdf = result.get("source_pdf", source_file)
        page_numbers = result.get("page_numbers", [])

        source_key = f"{source_pdf}:{page_numbers}"
        if source_key in seen_sources:
            continue
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

    return sources


def _add_vision_enrichment(
    output_parts: List[str],
    vision_enrichment: Optional[Dict[str, Any]]
) -> None:
    """Add vision enrichment to output if available."""
    if not vision_enrichment or vision_enrichment.get("type") != "vision_enriched":
        return

    vision_answer = vision_enrichment.get("answer", "")
    vision_sources = vision_enrichment.get("sources", [])
    image_count = vision_enrichment.get("image_count", 0)

    if vision_answer:
        output_parts.append(f"\n\n[Vision Analysis] Analyzed {image_count} PDF page(s):\n")
        output_parts.append(vision_answer)
        if vision_sources:
            output_parts.append(f"\n\nVision Sources: {', '.join(vision_sources)}")


def _build_result_metadata(
    enriched_results: List[Dict],
    query: str,
    confidence: str,
    sources: List[Dict],
    summary_result: Dict[str, Any],
    multi_product_results: List[Dict[str, Any]],
    product_sections: List[Dict],
    has_platform_differences: bool,
    vision_enrichment: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build result metadata dictionary."""
    return {
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
        "multi_product": len(multi_product_results) > 0,
        "multi_product_results": multi_product_results,
        "product_sections": product_sections,
        "has_platform_differences": has_platform_differences,
        "vision_enriched": vision_enrichment is not None and vision_enrichment.get("type") == "vision_enriched",
        "vision_image_count": vision_enrichment.get("image_count", 0) if vision_enrichment else 0,
        "vision_sources": vision_enrichment.get("sources", []) if vision_enrichment else [],
    }


def _build_product_sections(multi_product_results: List[Dict[str, Any]]) -> List[Dict]:
    """Build product sections for frontend display."""
    product_sections = []

    for mpr in multi_product_results:
        if mpr.get("has_differences"):
            for variant in mpr.get("variants", []):
                section_content = f"## {variant['platform']}"
                if variant.get("product_version"):
                    section_content += f" (v{variant['product_version']})"
                section_content += f"\n{variant.get('description', '')}"
                if variant.get("syntax"):
                    section_content += f"\nSyntax: `{variant['syntax']}`"

                product_sections.append({
                    "platform": variant["platform"],
                    "version": variant.get("product_version"),
                    "content": section_content,
                    "source": variant.get("source_pdf"),
                    "page_numbers": variant.get("page_numbers", [])
                })
        else:
            variants = mpr.get("variants", [])
            if variants:
                first_variant = variants[0]
                product_sections.append({
                    "platform": "Common",
                    "content": first_variant.get("description", ""),
                    "available_platforms": mpr.get("available_platforms", []),
                    "source": first_variant.get("source_pdf"),
                    "page_numbers": first_variant.get("page_numbers", [])
                })

    return product_sections
