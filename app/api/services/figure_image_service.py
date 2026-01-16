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
