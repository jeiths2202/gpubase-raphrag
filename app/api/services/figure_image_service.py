"""
Figure Image Service
Provides functionality to detect figure references in LLM responses
and retrieve corresponding images for display.
"""
import base64
import logging
from typing import List, Dict, Any, Optional

from ..services.figure_reference_extractor import get_figure_detector, FigureReferenceDetector
from ..infrastructure.postgres.image_embedding_repository import PostgresImageEmbeddingRepository
from ..repositories.image_embedding_repository import ImageEmbeddingEntity

logger = logging.getLogger(__name__)


class FigureImageService:
    """
    Service for detecting figure references in responses and retrieving images.

    Workflow:
    1. Detect figure references in LLM response text (e.g., "図1.1", "Figure 2")
    2. Convert to normalized form (e.g., "fig_1_1", "fig_2")
    3. Query database for matching images
    4. Return images formatted for frontend display
    """

    def __init__(
        self,
        image_repository: PostgresImageEmbeddingRepository,
        detector: Optional[FigureReferenceDetector] = None
    ):
        """
        Initialize service.

        Args:
            image_repository: Repository for image operations
            detector: Optional custom figure reference detector
        """
        self._repository = image_repository
        self._detector = detector or get_figure_detector()

    async def get_images_for_response(
        self,
        response_text: str,
        document_ids: List[str],
        include_data: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Detect figure references in response and retrieve matching images.

        Args:
            response_text: LLM response text to search for figure references
            document_ids: List of document IDs to search for images in
            include_data: Whether to include base64 encoded image data

        Returns:
            List of image data dicts ready for frontend display
        """
        # Detect figure references in the response
        references = self._detector.detect_references(response_text)

        if not references:
            logger.debug("No figure references detected in response")
            return []

        logger.info(f"Detected figure references: {references}")

        # Collect images from all documents
        all_images = []

        for document_id in document_ids:
            try:
                images = await self._repository.get_by_figure_references(
                    document_id=document_id,
                    figure_references=references,
                    include_data=include_data
                )
                all_images.extend(images)
                logger.debug(f"Found {len(images)} images in document {document_id}")
            except Exception as e:
                logger.error(f"Error fetching images for document {document_id}: {e}")

        # Convert to frontend format
        result = []
        for img in all_images:
            img_data = self._format_image_for_frontend(img, include_data)
            if img_data:
                result.append(img_data)

        logger.info(f"Returning {len(result)} images for figure references")
        return result

    def _format_image_for_frontend(
        self,
        entity: ImageEmbeddingEntity,
        include_data: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Format an image entity for frontend display."""
        try:
            result = {
                "id": entity.image_id,
                "document_id": entity.document_id,
                "page_number": entity.page_number,
                "figure_reference": entity.figure_reference,
                "figure_caption": entity.figure_caption,
                "description": entity.description or entity.figure_caption or "",
                "width": entity.width,
                "height": entity.height,
                "mime_type": entity.mime_type
            }

            if include_data and entity.image_data:
                # Base64 encode the image data for inline display
                b64_data = base64.b64encode(entity.image_data).decode('utf-8')
                result["data"] = f"data:{entity.mime_type};base64,{b64_data}"

            return result

        except Exception as e:
            logger.error(f"Error formatting image {entity.image_id}: {e}")
            return None

    async def has_figure_references(self, text: str) -> bool:
        """
        Quick check if text contains any figure references.

        Args:
            text: Text to check

        Returns:
            True if any figure references detected
        """
        refs = self._detector.detect_references(text)
        return len(refs) > 0

    def detect_references(self, text: str) -> List[str]:
        """
        Detect figure references in text.

        Args:
            text: Text to search

        Returns:
            List of normalized reference strings
        """
        return self._detector.detect_references(text)

    async def get_images_for_pages(
        self,
        document_id: str,
        page_numbers: List[int],
        include_data: bool = True,
        expand_search: bool = True,
        max_images: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get images from specific pages of a document.

        This is useful when sources reference specific pages and we want to
        display images from those pages regardless of figure reference detection.

        Args:
            document_id: Document ID to fetch images from
            page_numbers: List of page numbers to get images from
            include_data: Whether to include base64 encoded image data
            expand_search: If True and no images found on specified pages,
                          try nearby pages or first images in document
            max_images: Maximum number of images to return

        Returns:
            List of image data dicts ready for frontend display
        """
        if not page_numbers or not document_id:
            return []

        try:
            print(f"[get_images_for_pages] doc_id: {document_id}, pages: {page_numbers}", flush=True)

            # First try exact page matches
            images = await self._repository.get_by_page_numbers(
                document_id=document_id,
                page_numbers=page_numbers,
                include_data=include_data
            )
            print(f"[get_images_for_pages] Found {len(images)} images on exact pages", flush=True)

            # If no images found and expand_search is enabled, try expanded search
            if not images and expand_search:
                # Expand page range by ±10 pages
                min_page = max(1, min(page_numbers) - 10)
                max_page = max(page_numbers) + 10
                expanded_pages = list(range(min_page, max_page + 1))
                print(f"[get_images_for_pages] Expanding search to pages {min_page}-{max_page}", flush=True)

                images = await self._repository.get_by_page_numbers(
                    document_id=document_id,
                    page_numbers=expanded_pages,
                    include_data=include_data
                )
                print(f"[get_images_for_pages] Found {len(images)} images in expanded range", flush=True)

                # If still no images, get first images from the document
                if not images:
                    print(f"[get_images_for_pages] Trying to get any images from document", flush=True)
                    all_images = await self._repository.get_by_document_id(
                        document_id=document_id,
                        include_data=include_data
                    )
                    images = all_images[:max_images]  # Limit to max_images
                    print(f"[get_images_for_pages] Found {len(images)} images in document", flush=True)

            logger.info(f"Found {len(images)} images for pages {page_numbers} in document {document_id}")

            result = []
            for img in images[:max_images]:
                img_data = self._format_image_for_frontend(img, include_data)
                if img_data:
                    result.append(img_data)

            return result

        except Exception as e:
            print(f"[get_images_for_pages] ERROR: {e}", flush=True)
            logger.error(f"Error fetching images for pages {page_numbers}: {e}")
            return []

    async def _resolve_document_id(self, doc_ref: str) -> Optional[str]:
        """
        Resolve a document reference (filename or id) to actual document_id.

        The doc_id in sources might be a filename like 'OF_OSC_7.1_Mapping-Support-Guide.pdf'
        but images are stored with document_id like 'doc_97b8dc5fbb00'.
        This method resolves the filename to the actual document_id that has images.
        """
        # If it already looks like a document hash, return as is
        if doc_ref.startswith("doc_"):
            return doc_ref

        try:
            async with self._repository._pool.acquire() as conn:
                # Remove .pdf extension if present for matching
                base_name = doc_ref.rsplit('.', 1)[0] if '.' in doc_ref else doc_ref
                logger.debug(f"[_resolve_document_id] Looking for base_name: {base_name}")

                # PRIORITY 1: Find document_id that actually has images in image_embeddings
                # This is the most reliable way since images are stored with doc_* format
                result = await conn.fetchval('''
                    SELECT DISTINCT ie.document_id
                    FROM image_embeddings ie
                    JOIN documents d ON d.id = ie.document_id
                    WHERE d.filename LIKE $1 OR d.original_name LIKE $1
                    LIMIT 1
                ''', f"{base_name}%")

                if result:
                    print(f"[_resolve_document_id] Found via image_embeddings: {result}", flush=True)
                    logger.debug(f"Resolved document '{doc_ref}' via image_embeddings to '{result}'")
                    return result

                # PRIORITY 2: Look in documents table, preferring doc_* format
                rows = await conn.fetch('''
                    SELECT id FROM documents
                    WHERE filename LIKE $1 OR original_name LIKE $1
                    ORDER BY CASE WHEN id LIKE 'doc_%' THEN 0 ELSE 1 END
                    LIMIT 2
                ''', f"{base_name}%")

                if rows:
                    result = rows[0]['id']
                    print(f"[_resolve_document_id] Found via documents table: {result}", flush=True)
                    logger.debug(f"Resolved document '{doc_ref}' via documents to '{result}'")
                    return result

                print(f"[_resolve_document_id] No document found for: {base_name}", flush=True)

        except Exception as e:
            print(f"[_resolve_document_id] ERROR: {e}", flush=True)
            logger.warning(f"Failed to resolve document '{doc_ref}': {e}")

        # Fallback: return the original ref
        return doc_ref

    async def get_images_for_sources(
        self,
        sources: List[Dict[str, Any]],
        include_data: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get images based on RAG source documents.

        Extracts document IDs and page numbers from sources and fetches
        corresponding images.

        Args:
            sources: List of source dicts with doc_id and page_number fields
            include_data: Whether to include base64 encoded image data

        Returns:
            List of image data dicts ready for frontend display
        """
        # Debug: print raw sources
        print(f"[FigureImageService.get_images_for_sources] Called with {len(sources)} sources", flush=True)
        if sources:
            print(f"[FigureImageService.get_images_for_sources] First source: {sources[0]}", flush=True)

        # Group page numbers by document ID
        doc_pages: Dict[str, set] = {}
        for source in sources:
            doc_id = source.get("doc_id") or source.get("document_id")
            page_num = source.get("page_number") or source.get("page")
            print(f"[FigureImageService.get_images_for_sources] Parsed source - doc_id: {doc_id}, page_num: {page_num}", flush=True)

            if doc_id and page_num is not None:
                if doc_id not in doc_pages:
                    doc_pages[doc_id] = set()
                doc_pages[doc_id].add(page_num)

        if not doc_pages:
            print("[FigureImageService.get_images_for_sources] doc_pages is EMPTY - returning early!", flush=True)
            logger.debug("No valid document/page combinations found in sources")
            return []

        # Resolve document IDs (filename to hash) and fetch images
        print(f"[FigureImageService] doc_pages: {list(doc_pages.keys())}", flush=True)
        all_images = []
        for doc_ref, pages in doc_pages.items():
            # Resolve filename to actual document_id
            print(f"[FigureImageService] Resolving doc_ref: {doc_ref}", flush=True)
            resolved_id = await self._resolve_document_id(doc_ref)
            print(f"[FigureImageService] Resolved to: {resolved_id}", flush=True)
            logger.info(f"Fetching images for doc '{doc_ref}' (resolved: '{resolved_id}'), pages: {pages}")

            images = await self.get_images_for_pages(
                document_id=resolved_id,
                page_numbers=list(pages),
                include_data=include_data
            )
            all_images.extend(images)

        logger.info(f"Retrieved {len(all_images)} images from {len(doc_pages)} documents")
        return all_images


# Singleton instance
_service: Optional[FigureImageService] = None


def get_figure_image_service(
    image_repository: PostgresImageEmbeddingRepository
) -> FigureImageService:
    """
    Get or create FigureImageService instance.

    Args:
        image_repository: Repository for image operations

    Returns:
        FigureImageService instance
    """
    global _service
    if _service is None:
        _service = FigureImageService(image_repository)
    return _service


def reset_figure_image_service():
    """Reset the singleton instance (for testing)."""
    global _service
    _service = None
