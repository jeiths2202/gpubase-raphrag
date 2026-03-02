"""Structure Enrichment Module

Contains result enrichment with PostgreSQL structure metadata.
"""
import logging
import re
from typing import Dict, Any, List, Tuple, Set

from .unified_search_utils import fix_markdown_table_separators
from .database_search import execute_pg_query

logger = logging.getLogger(__name__)


async def enrich_with_structure(
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

    Args:
        fused_results: Search results to enrich
        clip_images: CLIP image search results
        include_tables: Whether to include related tables
        top_k: Maximum results to process

    Returns:
        Tuple of (enriched_results, related_tables_by_page)
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
            table_results = await execute_pg_query(table_query)

            for tr in table_results:
                key = (tr['pdf_id'], tr['page_start'])
                if key not in related_tables_by_page:
                    related_tables_by_page[key] = []
                fixed_markdown = fix_markdown_table_separators(tr['content'])
                related_tables_by_page[key].append({
                    "markdown": fixed_markdown,
                    "chunk_id": tr['chunk_id'],
                    "section_title": tr.get('section_title')
                })

            logger.info(f"[Enrichment] Found {sum(len(v) for v in related_tables_by_page.values())} related tables")
        except Exception as e:
            logger.error(f"Error fetching related tables: {e}")

    # Build enriched results
    for i, result in enumerate(fused_results[:top_k]):
        pdf_id = result.get("doc_id") or result.get("pdf_id") or result.get("source")
        page_start = result.get("page_start") or result.get("page_number")
        page_end = result.get("page_end") or page_start
        content = result.get("content", "")

        # Find images related to this chunk
        chunk_images = _find_related_images(clip_images, pdf_id, page_start, page_end)

        # Extract or add related tables
        tables = _extract_tables(
            content, result, pdf_id, page_start, page_end, related_tables_by_page
        )

        # Format page display
        if page_start == page_end or not page_end:
            page_display = f"p.{page_start}" if page_start else "p.?"
        else:
            page_display = f"p.{page_start}-{page_end}"

        doc_name = result.get("document_name") or result.get("source") or pdf_id or "Unknown"
        source_type = result.get("source_type", "document")
        source_url = result.get("source_url", "")

        enriched_result = {
            "index": i + 1,
            "chunk_id": result.get("chunk_id"),
            "chunk_type": result.get("chunk_type", "TEXT"),
            "title": result.get("section_title") or f"{doc_name} ({page_display})",
            "content": content,
            "rrf_score": result.get("rrf_score", 0),
            "neo4j_rank": result.get("neo4j_rank"),
            "postgres_rank": result.get("postgres_rank"),
            "error_boosted": result.get("error_boosted", False),
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
                "source_type": source_type,
                "source_url": source_url
            },
            "images": chunk_images,
            "tables": tables,
            "relations": result.get("relations", {})
        }

        enriched_results.append(enriched_result)

    return enriched_results, related_tables_by_page


def _find_related_images(
    clip_images: List[Dict],
    pdf_id: str,
    page_start: int,
    page_end: int
) -> List[Dict]:
    """Find images related to a chunk by document and page match."""
    chunk_images = []

    for img in clip_images:
        img_page = img.get('page_number')
        img_doc_id = img.get('document_id')

        # Check document ID match first
        if img_doc_id and pdf_id and img_doc_id != pdf_id:
            continue

        if img_page and page_start and page_end:
            if page_start <= img_page <= page_end:
                chunk_images.append(img)

    return chunk_images


def _extract_tables(
    content: str,
    result: Dict,
    pdf_id: str,
    page_start: int,
    page_end: int,
    related_tables_by_page: Dict
) -> List[Dict]:
    """Extract tables from content and add related tables from same pages."""
    tables = []
    chunk_type = result.get("chunk_type", "TEXT")

    if chunk_type in ('TABLE', 'TABLE_CHUNK'):
        fixed_content = fix_markdown_table_separators(content)
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

    return tables
