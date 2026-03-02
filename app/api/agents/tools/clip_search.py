"""CLIP Search Module

Contains CLIP-based image search functionality for unified search.
"""
import logging
from typing import Dict, Any, Optional, List, Set

logger = logging.getLogger(__name__)


async def clip_image_search(
    clip_service,
    query: str,
    relevant_pages: Set[int],
    doc_id: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Execute CLIP-based text-to-image search

    Args:
        clip_service: CLIP service instance
        query: Search query
        relevant_pages: Set of page numbers to filter images
        doc_id: Optional document ID filter
        limit: Maximum number of images to return

    Returns:
        List of image results with URLs
    """
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
        min_sim = 0.30  # Higher threshold for better relevance
        clip_results = await image_repo.search_by_clip_embedding(
            query_embedding=clip_query_embedding,
            document_id=doc_id,
            limit=limit * 3,
            min_similarity=min_sim
        )

        logger.debug(f"[CLIP] Search for doc_id={doc_id}, relevant_pages={relevant_pages}, got {len(clip_results)} raw results")

        # Filter by relevant pages
        clip_images = []
        seen_pages = set()

        for img in clip_results:
            similarity = img.get('similarity', 0)
            if similarity < min_sim:
                logger.debug(f"[CLIP] Skipping image {img.get('image_id')} - similarity {similarity:.3f} < {min_sim}")
                continue

            page_num = img.get('page_number')
            img_doc_id = img.get('document_id')

            # STRICT: Only include images from target document AND matching pages
            if doc_id and img_doc_id and img_doc_id != doc_id:
                logger.debug(f"[CLIP] Skipping image - doc mismatch: {img_doc_id} != {doc_id}")
                continue

            if not relevant_pages or page_num not in relevant_pages:
                logger.debug(f"[CLIP] Skipping image - page {page_num} not in relevant_pages {relevant_pages}")
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

        logger.info(f"[CLIP] Returned {len(clip_images)} images")
        return clip_images

    except Exception as e:
        logger.error(f"CLIP image search error: {e}")
        return []


def extract_relevant_pages(
    fused_results: List[Dict[str, Any]],
) -> Dict[str, Set[int]]:
    """
    Extract relevant pages from fused results, grouped by document.

    Args:
        fused_results: Search results with page information

    Returns:
        Dict mapping doc_id to set of relevant page numbers
    """
    doc_pages = {}

    for result in fused_results:
        doc_id = result.get("doc_id") or result.get("pdf_id") or result.get("source")

        if not doc_id:
            continue

        if doc_id not in doc_pages:
            doc_pages[doc_id] = set()

        # Add page numbers from result
        page_start = result.get("page_start") or result.get("page_number")
        page_end = result.get("page_end") or page_start

        if page_start:
            if page_end and page_end != page_start:
                # Add range
                for p in range(page_start, page_end + 1):
                    doc_pages[doc_id].add(p)
            else:
                doc_pages[doc_id].add(page_start)

    return doc_pages
