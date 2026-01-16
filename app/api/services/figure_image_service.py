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
        include_data: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get images from specific pages of a document.

        This is useful when sources reference specific pages and we want to
        display images from those pages regardless of figure reference detection.

        Args:
            document_id: Document ID to fetch images from
            page_numbers: List of page numbers to get images from
            include_data: Whether to include base64 encoded image data

        Returns:
            List of image data dicts ready for frontend display
        """
        if not page_numbers or not document_id:
            return []

        try:
            images = await self._repository.get_by_page_numbers(
                document_id=document_id,
                page_numbers=page_numbers,
                include_data=include_data
            )
            logger.info(f"Found {len(images)} images for pages {page_numbers} in document {document_id}")

            result = []
            for img in images:
                img_data = self._format_image_for_frontend(img, include_data)
                if img_data:
                    result.append(img_data)

            return result

        except Exception as e:
            logger.error(f"Error fetching images for pages {page_numbers}: {e}")
            return []

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
        # Group page numbers by document ID
        doc_pages: Dict[str, set] = {}
        for source in sources:
            doc_id = source.get("doc_id") or source.get("document_id")
            page_num = source.get("page_number") or source.get("page")

            if doc_id and page_num is not None:
                if doc_id not in doc_pages:
                    doc_pages[doc_id] = set()
                doc_pages[doc_id].add(page_num)

        if not doc_pages:
            logger.debug("No valid document/page combinations found in sources")
            return []

        # Fetch images for each document
        all_images = []
        for doc_id, pages in doc_pages.items():
            images = await self.get_images_for_pages(
                document_id=doc_id,
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
