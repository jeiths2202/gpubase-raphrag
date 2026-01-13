"""
Multimodal RAG Service

Orchestrates image extraction, embedding, storage, and retrieval for
multimodal RAG (text + images).

Features:
- PDF image extraction with PyMuPDF
- Image description generation with Ollama bakllava
- Image embedding and PostgreSQL storage
- Similarity search for image retrieval
- Integration with existing RAG pipeline
"""
import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..repositories.image_embedding_repository import (
    ImageEmbeddingEntity,
    ImageSearchResult,
)

logger = logging.getLogger(__name__)


class MultimodalRAGService:
    """
    Service for multimodal RAG operations.

    Orchestrates:
    - Image extraction from documents
    - VLM-based image description
    - Image embedding generation
    - Storage and retrieval from PostgreSQL
    """

    def __init__(
        self,
        image_repository,  # PostgresImageEmbeddingRepository
        vlm_service=None,  # OllamaVLMService
        image_preprocessor=None,  # ImagePreprocessor
        embedding_service=None,  # ImageEmbeddingService
    ):
        """
        Initialize the multimodal RAG service.

        Args:
            image_repository: Repository for image storage
            vlm_service: Optional VLM service (lazy loaded if not provided)
            image_preprocessor: Optional preprocessor (lazy loaded if not provided)
            embedding_service: Optional embedding service (lazy loaded if not provided)
        """
        self._repository = image_repository
        self._vlm_service = vlm_service
        self._preprocessor = image_preprocessor
        self._embedding_service = embedding_service

    def _get_vlm_service(self):
        """Lazy load VLM service."""
        if self._vlm_service is None:
            from .ollama_vlm_service import get_ollama_vlm_service
            self._vlm_service = get_ollama_vlm_service()
        return self._vlm_service

    def _get_preprocessor(self):
        """Lazy load image preprocessor."""
        if self._preprocessor is None:
            from .image_preprocessor import ImagePreprocessor
            self._preprocessor = ImagePreprocessor()
        return self._preprocessor

    def _get_embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            from .multimodal_embedding import ImageEmbeddingService
            self._embedding_service = ImageEmbeddingService()
        return self._embedding_service

    # ==================== Document Processing ====================

    async def process_pdf_images(
        self,
        pdf_path: Path,
        document_id: str,
        extract_embedded: bool = True,
        generate_descriptions: bool = True,
        generate_embeddings: bool = True,
        min_image_size: tuple = (100, 100),
    ) -> Dict[str, Any]:
        """
        Extract and process all images from a PDF document.

        Args:
            pdf_path: Path to PDF file
            document_id: Document identifier for storage
            extract_embedded: Whether to extract embedded images
            generate_descriptions: Generate VLM descriptions
            generate_embeddings: Generate and store embeddings
            min_image_size: Minimum image dimensions

        Returns:
            Processing result with image count and status
        """
        preprocessor = self._get_preprocessor()
        result = {
            "document_id": document_id,
            "images_found": 0,
            "images_processed": 0,
            "images_stored": 0,
            "errors": [],
        }

        try:
            # Extract embedded images from PDF
            if extract_embedded:
                processed_images = await preprocessor.extract_embedded_images(
                    pdf_path, min_size=min_image_size
                )
                result["images_found"] = len(processed_images)

                # Process each image
                for idx, processed_image in enumerate(processed_images):
                    try:
                        image_id = f"{document_id}_img_{idx:03d}"

                        entity = await self._create_image_entity(
                            image_data=processed_image.image_bytes,
                            document_id=document_id,
                            image_id=image_id,
                            page_number=processed_image.page_number,
                            mime_type=processed_image.mime_type,
                            width=processed_image.processed_size[0],
                            height=processed_image.processed_size[1],
                            generate_description=generate_descriptions,
                            generate_embedding=generate_embeddings,
                        )

                        # Store in repository
                        await self._repository.store_image(entity)
                        result["images_stored"] += 1
                        result["images_processed"] += 1

                    except Exception as e:
                        logger.error(f"Error processing image {idx}: {e}")
                        result["errors"].append({
                            "image_index": idx,
                            "error": str(e)
                        })

            logger.info(
                f"Processed PDF {document_id}: "
                f"{result['images_stored']}/{result['images_found']} images"
            )

        except Exception as e:
            logger.error(f"PDF processing error for {document_id}: {e}")
            result["errors"].append({"error": str(e)})

        return result

    async def _create_image_entity(
        self,
        image_data: bytes,
        document_id: str,
        image_id: str,
        page_number: Optional[int] = None,
        mime_type: str = "image/png",
        width: Optional[int] = None,
        height: Optional[int] = None,
        position: Optional[Dict[str, float]] = None,
        generate_description: bool = True,
        generate_embedding: bool = True,
    ) -> ImageEmbeddingEntity:
        """
        Create an ImageEmbeddingEntity with optional description and embedding.

        Args:
            image_data: Raw image bytes
            document_id: Parent document ID
            image_id: Unique image ID
            page_number: Page number in document
            mime_type: MIME type of image
            width: Image width
            height: Image height
            position: Position on page
            generate_description: Whether to generate VLM description
            generate_embedding: Whether to generate embedding

        Returns:
            ImageEmbeddingEntity ready for storage
        """
        description = None
        alt_text = None
        embedding = None

        # Generate description using VLM
        if generate_description:
            try:
                vlm = self._get_vlm_service()
                desc_result = await vlm.describe_image(image_data)
                description = desc_result.get("description", "")
                alt_text = desc_result.get("alt_text", "")
            except Exception as e:
                logger.warning(f"Description generation failed: {e}")

        # Generate embedding
        if generate_embedding:
            try:
                embedding_service = self._get_embedding_service()
                embedding = await embedding_service.embed_image(image_data)
            except Exception as e:
                logger.warning(f"Embedding generation failed: {e}")

        return ImageEmbeddingEntity(
            id=str(uuid.uuid4()),
            document_id=document_id,
            image_id=image_id,
            page_number=page_number,
            image_data=image_data,
            mime_type=mime_type,
            width=width,
            height=height,
            file_size=len(image_data),
            position=position,
            description=description,
            alt_text=alt_text,
            embedding=embedding,
            metadata={},
        )

    # ==================== Image Search ====================

    async def search_images(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.1,
        document_id: Optional[str] = None,
        include_data: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search for images by text query.

        Converts the query to an embedding and searches for similar images.

        Args:
            query: Text query
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold
            document_id: Optional filter by document
            include_data: Whether to include image binary data

        Returns:
            List of matching images with metadata
        """
        try:
            # Get query embedding using the embedding service
            embedding_service = self._get_embedding_service()

            # For text-to-image search, we use the VLM to generate
            # a conceptual embedding from the query text
            vlm = self._get_vlm_service()
            query_embedding = await vlm._get_text_embedding(query)

            # Search for similar images
            results = await self._repository.search_similar(
                query_embedding=query_embedding,
                limit=limit,
                min_similarity=min_similarity,
                document_id=document_id,
            )

            # Format results
            formatted_results = []
            for result in results:
                item = {
                    "image_id": result.image_id,
                    "document_id": result.document_id,
                    "page_number": result.page_number,
                    "description": result.description,
                    "similarity": result.similarity,
                }

                if include_data and result.image_data:
                    # Convert to base64 for API response
                    item["image_base64"] = base64.b64encode(
                        result.image_data
                    ).decode("utf-8")
                    item["mime_type"] = result.mime_type

                formatted_results.append(item)

            return formatted_results

        except Exception as e:
            logger.error(f"Image search error: {e}")
            return []

    async def search_images_by_image(
        self,
        image_data: bytes,
        limit: int = 5,
        min_similarity: float = 0.3,
        document_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar images using an image query.

        Args:
            image_data: Query image bytes
            limit: Maximum results
            min_similarity: Minimum similarity threshold
            document_id: Optional document filter

        Returns:
            List of similar images
        """
        try:
            # Get embedding for query image
            embedding_service = self._get_embedding_service()
            query_embedding = await embedding_service.embed_image(image_data)

            # Search
            results = await self._repository.search_similar(
                query_embedding=query_embedding,
                limit=limit,
                min_similarity=min_similarity,
                document_id=document_id,
            )

            return [
                {
                    "image_id": r.image_id,
                    "document_id": r.document_id,
                    "page_number": r.page_number,
                    "description": r.description,
                    "similarity": r.similarity,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Image-to-image search error: {e}")
            return []

    # ==================== Image Retrieval ====================

    async def get_image(
        self,
        image_id: str,
        include_data: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single image by ID.

        Args:
            image_id: Image identifier
            include_data: Whether to include binary data

        Returns:
            Image data dict or None
        """
        entity = await self._repository.get_by_image_id(
            image_id, include_data=include_data
        )

        if not entity:
            return None

        result = {
            "id": entity.id,
            "image_id": entity.image_id,
            "document_id": entity.document_id,
            "page_number": entity.page_number,
            "description": entity.description,
            "alt_text": entity.alt_text,
            "width": entity.width,
            "height": entity.height,
            "mime_type": entity.mime_type,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
        }

        if include_data and entity.image_data:
            result["image_base64"] = base64.b64encode(
                entity.image_data
            ).decode("utf-8")

        return result

    async def get_document_images(
        self,
        document_id: str,
        include_data: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get all images for a document.

        Args:
            document_id: Document identifier
            include_data: Whether to include binary data

        Returns:
            List of image metadata
        """
        entities = await self._repository.get_by_document_id(
            document_id, include_data=include_data
        )

        results = []
        for entity in entities:
            item = {
                "image_id": entity.image_id,
                "page_number": entity.page_number,
                "description": entity.description,
                "alt_text": entity.alt_text,
                "width": entity.width,
                "height": entity.height,
                "mime_type": entity.mime_type,
            }

            if include_data and entity.image_data:
                item["image_base64"] = base64.b64encode(
                    entity.image_data
                ).decode("utf-8")

            results.append(item)

        return results

    # ==================== Cleanup ====================

    async def delete_document_images(
        self,
        document_id: str,
    ) -> int:
        """
        Delete all images for a document.

        Args:
            document_id: Document identifier

        Returns:
            Number of deleted images
        """
        count = await self._repository.delete_by_document_id(document_id)
        logger.info(f"Deleted {count} images for document {document_id}")
        return count

    # ==================== RAG Integration ====================

    async def enhance_rag_context(
        self,
        query: str,
        text_results: List[Dict[str, Any]],
        max_images: int = 3,
        min_similarity: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Enhance RAG results with relevant images.

        Args:
            query: Original query
            text_results: Text search results
            max_images: Maximum images to add
            min_similarity: Minimum image similarity

        Returns:
            Enhanced context with images
        """
        enhanced = {
            "text_results": text_results,
            "images": [],
        }

        try:
            # Extract document IDs from text results
            doc_ids = list(set(
                r.get("document_id") for r in text_results
                if r.get("document_id")
            ))

            # Search for relevant images in those documents
            for doc_id in doc_ids[:3]:  # Limit document scope
                images = await self.search_images(
                    query=query,
                    limit=max_images,
                    min_similarity=min_similarity,
                    document_id=doc_id,
                    include_data=True,
                )
                enhanced["images"].extend(images)

            # Also do a global image search
            if len(enhanced["images"]) < max_images:
                global_images = await self.search_images(
                    query=query,
                    limit=max_images - len(enhanced["images"]),
                    min_similarity=min_similarity,
                    include_data=True,
                )
                enhanced["images"].extend(global_images)

            # Deduplicate and limit
            seen_ids = set()
            unique_images = []
            for img in enhanced["images"]:
                if img["image_id"] not in seen_ids:
                    seen_ids.add(img["image_id"])
                    unique_images.append(img)
                if len(unique_images) >= max_images:
                    break

            enhanced["images"] = unique_images

        except Exception as e:
            logger.error(f"RAG enhancement error: {e}")

        return enhanced


# Factory function
def get_multimodal_rag_service(image_repository) -> MultimodalRAGService:
    """
    Get MultimodalRAGService instance.

    Args:
        image_repository: PostgresImageEmbeddingRepository instance

    Returns:
        MultimodalRAGService instance
    """
    return MultimodalRAGService(image_repository=image_repository)
