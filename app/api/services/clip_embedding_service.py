"""
CLIP Embedding Service

Provides multimodal embeddings using CLIP (Contrastive Language-Image Pre-training).
Supports both image and text embeddings in the same vector space.

Features:
- Image-to-image similarity search
- Text-to-image search (find images by text description)
- Image-to-text search (find text by image)
- Hybrid search combining VLM descriptions and CLIP embeddings

Models:
- clip-ViT-B-32: 512 dimensions, faster
- clip-ViT-L-14: 768 dimensions, more accurate
"""
import asyncio
import base64
import io
import logging
import os
from typing import Optional, List, Dict, Any, Union, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CLIPConfig:
    """CLIP service configuration."""

    # Model selection
    MODEL_NAME = os.getenv("CLIP_MODEL", "clip-ViT-B-32")

    # Dimensions by model
    MODEL_DIMENSIONS = {
        "clip-ViT-B-32": 512,
        "clip-ViT-L-14": 768,
        "clip-ViT-B-16": 512,
    }

    # Processing settings
    MAX_IMAGE_SIZE = int(os.getenv("CLIP_MAX_IMAGE_SIZE", "1024"))
    BATCH_SIZE = int(os.getenv("CLIP_BATCH_SIZE", "8"))

    # Cache settings
    ENABLE_CACHE = os.getenv("CLIP_ENABLE_CACHE", "true").lower() == "true"

    @classmethod
    def get_dimension(cls) -> int:
        """Get embedding dimension for current model."""
        return cls.MODEL_DIMENSIONS.get(cls.MODEL_NAME, 512)


class CLIPEmbeddingService:
    """
    CLIP embedding service for multimodal similarity search.

    Provides unified embeddings for images and text in the same vector space,
    enabling cross-modal search capabilities.
    """

    def __init__(
        self,
        model_name: str = None,
        device: str = None,
        lazy_load: bool = True
    ):
        """
        Initialize CLIP service.

        Args:
            model_name: CLIP model name (default: clip-ViT-B-32)
            device: Device to use (cuda/cpu, auto-detected if None)
            lazy_load: Whether to load model lazily on first use
        """
        self.model_name = model_name or CLIPConfig.MODEL_NAME
        self.dimension = CLIPConfig.MODEL_DIMENSIONS.get(self.model_name, 512)
        self._device = device
        self._model = None
        self._processor = None
        self._lock = asyncio.Lock()
        self._loaded = False

        # Statistics
        self._stats = {
            "image_embeddings": 0,
            "text_embeddings": 0,
            "errors": 0,
            "model_loaded": False
        }

        if not lazy_load:
            self._load_model()

    @property
    def device(self) -> str:
        """Get device for model execution."""
        if self._device is None:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    def _load_model(self):
        """Load CLIP model."""
        if self._loaded:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading CLIP model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._loaded = True
            self._stats["model_loaded"] = True
            logger.info(f"CLIP model loaded on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise RuntimeError(f"CLIP model loading failed: {e}")

    def _ensure_loaded(self):
        """Ensure model is loaded."""
        if not self._loaded:
            self._load_model()

    def _preprocess_image(self, image_data: bytes) -> "Image.Image":
        """
        Preprocess image for CLIP.

        Args:
            image_data: Raw image bytes

        Returns:
            PIL Image object
        """
        from PIL import Image

        # Load image from bytes
        image = Image.open(io.BytesIO(image_data))

        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize if too large
        max_size = CLIPConfig.MAX_IMAGE_SIZE
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        return image

    async def embed_image(self, image_data: bytes) -> List[float]:
        """
        Generate CLIP embedding for an image.

        Args:
            image_data: Raw image bytes

        Returns:
            CLIP embedding vector
        """
        async with self._lock:
            try:
                self._ensure_loaded()

                # Preprocess image
                image = self._preprocess_image(image_data)

                # Generate embedding in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                embedding = await loop.run_in_executor(
                    None,
                    lambda: self._model.encode(
                        image,
                        convert_to_numpy=True,
                        normalize_embeddings=True
                    )
                )

                self._stats["image_embeddings"] += 1

                return embedding.tolist()

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"CLIP image embedding failed: {e}")
                return [0.0] * self.dimension

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate CLIP embedding for text.

        Args:
            text: Input text

        Returns:
            CLIP embedding vector (same space as image embeddings)
        """
        async with self._lock:
            try:
                self._ensure_loaded()

                # Generate embedding in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                embedding = await loop.run_in_executor(
                    None,
                    lambda: self._model.encode(
                        text,
                        convert_to_numpy=True,
                        normalize_embeddings=True
                    )
                )

                self._stats["text_embeddings"] += 1

                return embedding.tolist()

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"CLIP text embedding failed: {e}")
                return [0.0] * self.dimension

    async def embed_images(
        self,
        images: List[bytes],
        batch_size: int = None
    ) -> List[List[float]]:
        """
        Generate CLIP embeddings for multiple images.

        Args:
            images: List of image bytes
            batch_size: Batch size for processing

        Returns:
            List of CLIP embedding vectors
        """
        if not images:
            return []

        batch_size = batch_size or CLIPConfig.BATCH_SIZE
        embeddings = []

        async with self._lock:
            try:
                self._ensure_loaded()

                # Preprocess all images
                pil_images = []
                for img_data in images:
                    try:
                        pil_images.append(self._preprocess_image(img_data))
                    except Exception as e:
                        logger.warning(f"Image preprocessing failed: {e}")
                        pil_images.append(None)

                # Process in batches
                loop = asyncio.get_event_loop()
                for i in range(0, len(pil_images), batch_size):
                    batch = pil_images[i:i + batch_size]

                    # Filter out None values
                    valid_batch = [img for img in batch if img is not None]
                    valid_indices = [j for j, img in enumerate(batch) if img is not None]

                    if valid_batch:
                        # Run in thread pool to avoid blocking event loop
                        batch_embeddings = await loop.run_in_executor(
                            None,
                            lambda vb=valid_batch: self._model.encode(
                                vb,
                                convert_to_numpy=True,
                                normalize_embeddings=True,
                                batch_size=batch_size
                            )
                        )

                        # Reconstruct results with zeros for failed images
                        batch_results = [[0.0] * self.dimension] * len(batch)
                        for idx, emb in zip(valid_indices, batch_embeddings):
                            batch_results[idx] = emb.tolist()
                            self._stats["image_embeddings"] += 1

                        embeddings.extend(batch_results)
                    else:
                        embeddings.extend([[0.0] * self.dimension] * len(batch))

                return embeddings

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"CLIP batch embedding failed: {e}")
                return [[0.0] * self.dimension for _ in images]

    async def embed_texts(
        self,
        texts: List[str],
        batch_size: int = None
    ) -> List[List[float]]:
        """
        Generate CLIP embeddings for multiple texts.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing

        Returns:
            List of CLIP embedding vectors
        """
        if not texts:
            return []

        batch_size = batch_size or CLIPConfig.BATCH_SIZE

        async with self._lock:
            try:
                self._ensure_loaded()

                # Run in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None,
                    lambda: self._model.encode(
                        texts,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                        batch_size=batch_size
                    )
                )

                self._stats["text_embeddings"] += len(texts)

                return [emb.tolist() for emb in embeddings]

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"CLIP batch text embedding failed: {e}")
                return [[0.0] * self.dimension for _ in texts]

    async def compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0-1)
        """
        import numpy as np

        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Cosine similarity (embeddings are already normalized)
        similarity = np.dot(vec1, vec2)

        return float(similarity)

    async def find_similar_images(
        self,
        query_embedding: List[float],
        image_embeddings: List[Tuple[str, List[float]]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find most similar images to a query embedding.

        Args:
            query_embedding: Query embedding (from image or text)
            image_embeddings: List of (image_id, embedding) tuples
            top_k: Number of results to return

        Returns:
            List of results with image_id and similarity score
        """
        import numpy as np

        query_vec = np.array(query_embedding)

        results = []
        for image_id, emb in image_embeddings:
            similarity = float(np.dot(query_vec, np.array(emb)))
            results.append({
                "image_id": image_id,
                "similarity": similarity
            })

        # Sort by similarity (descending)
        results.sort(key=lambda x: x["similarity"], reverse=True)

        return results[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            **self._stats,
            "model_name": self.model_name,
            "dimension": self.dimension,
            "device": self.device if self._loaded else "not loaded"
        }

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded


class HybridImageEmbedding:
    """
    Hybrid embedding combining VLM description embeddings and CLIP embeddings.

    Provides:
    - Semantic search via VLM description (4096-dim NIM)
    - Visual similarity via CLIP (512-dim)
    - Weighted combination for hybrid search
    """

    def __init__(
        self,
        vlm_weight: float = 0.6,
        clip_weight: float = 0.4,
        enable_clip: bool = True
    ):
        """
        Initialize hybrid embedding service.

        Args:
            vlm_weight: Weight for VLM-based embedding (0-1)
            clip_weight: Weight for CLIP embedding (0-1)
            enable_clip: Whether to enable CLIP embeddings
        """
        self.vlm_weight = vlm_weight
        self.clip_weight = clip_weight
        self.enable_clip = enable_clip

        self._image_service = None
        self._clip_service = None
        self._logger = logging.getLogger(__name__)

    @property
    def image_service(self):
        """Lazy initialization of image embedding service."""
        if self._image_service is None:
            from .multimodal_embedding import ImageEmbeddingService
            self._image_service = ImageEmbeddingService()
        return self._image_service

    @property
    def clip_service(self):
        """Lazy initialization of CLIP service."""
        if self._clip_service is None and self.enable_clip:
            self._clip_service = CLIPEmbeddingService(lazy_load=True)
        return self._clip_service

    async def embed_image(
        self,
        image_data: bytes,
        context: Optional[str] = None,
        image_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate hybrid embeddings for an image.

        Args:
            image_data: Raw image bytes
            context: Optional document context
            image_type: Optional image type hint

        Returns:
            Dict with vlm_embedding, clip_embedding, and metadata
        """
        result = {
            "vlm_embedding": None,
            "clip_embedding": None,
            "description": None,
            "has_vlm": False,
            "has_clip": False
        }

        # Generate VLM-based embedding (description -> text embedding)
        try:
            vlm_result = await self.image_service.describe_and_embed_image(
                image_data=image_data,
                context=context,
                image_type=image_type
            )
            result["vlm_embedding"] = vlm_result.get("embedding")
            result["description"] = vlm_result.get("description")
            result["has_vlm"] = vlm_result.get("has_embedding", False)
        except Exception as e:
            self._logger.error(f"VLM embedding failed: {e}")

        # Generate CLIP embedding
        if self.enable_clip and self.clip_service:
            try:
                clip_embedding = await self.clip_service.embed_image(image_data)
                if sum(1 for v in clip_embedding if v != 0.0) > 0:
                    result["clip_embedding"] = clip_embedding
                    result["has_clip"] = True
            except Exception as e:
                self._logger.error(f"CLIP embedding failed: {e}")

        return result

    async def embed_images(
        self,
        images: List[bytes],
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate hybrid embeddings for multiple images.

        Args:
            images: List of image bytes
            context: Optional document context

        Returns:
            List of hybrid embedding results
        """
        results = []

        # Process VLM embeddings
        vlm_embeddings = await self.image_service.embed_images(images, context=context)

        # Process CLIP embeddings if enabled
        clip_embeddings = None
        if self.enable_clip and self.clip_service:
            try:
                clip_embeddings = await self.clip_service.embed_images(images)
            except Exception as e:
                self._logger.error(f"CLIP batch embedding failed: {e}")
                clip_embeddings = [[0.0] * self.clip_service.dimension for _ in images]

        # Combine results
        for i, img_data in enumerate(images):
            result = {
                "vlm_embedding": vlm_embeddings[i] if vlm_embeddings else None,
                "clip_embedding": clip_embeddings[i] if clip_embeddings else None,
                "has_vlm": vlm_embeddings[i] is not None and sum(1 for v in vlm_embeddings[i] if v != 0.0) > 0,
                "has_clip": clip_embeddings[i] is not None and sum(1 for v in clip_embeddings[i] if v != 0.0) > 0
            }
            results.append(result)

        return results

    async def search_by_text(
        self,
        query_text: str,
        image_embeddings: List[Dict[str, Any]],
        top_k: int = 5,
        use_vlm: bool = True,
        use_clip: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search images by text query.

        Uses both VLM description similarity and CLIP cross-modal search.

        Args:
            query_text: Text query
            image_embeddings: List of image embedding results
            top_k: Number of results
            use_vlm: Use VLM-based similarity
            use_clip: Use CLIP-based similarity

        Returns:
            Ranked list of results
        """
        import numpy as np

        results = []

        # Generate query embeddings
        vlm_query_emb = None
        clip_query_emb = None

        if use_vlm:
            vlm_query_emb = await self.image_service.text_embedder.embed_text(
                query_text, input_type="query"
            )

        if use_clip and self.clip_service:
            clip_query_emb = await self.clip_service.embed_text(query_text)

        # Calculate similarities
        for i, img_emb in enumerate(image_embeddings):
            vlm_sim = 0.0
            clip_sim = 0.0

            # VLM similarity
            if use_vlm and vlm_query_emb and img_emb.get("vlm_embedding"):
                vlm_sim = float(np.dot(
                    np.array(vlm_query_emb),
                    np.array(img_emb["vlm_embedding"])
                ))

            # CLIP similarity
            if use_clip and clip_query_emb and img_emb.get("clip_embedding"):
                clip_sim = float(np.dot(
                    np.array(clip_query_emb),
                    np.array(img_emb["clip_embedding"])
                ))

            # Weighted combination
            combined_sim = (
                self.vlm_weight * vlm_sim +
                self.clip_weight * clip_sim
            )

            results.append({
                "index": i,
                "vlm_similarity": vlm_sim,
                "clip_similarity": clip_sim,
                "combined_similarity": combined_sim
            })

        # Sort by combined similarity
        results.sort(key=lambda x: x["combined_similarity"], reverse=True)

        return results[:top_k]

    async def search_by_image(
        self,
        query_image: bytes,
        image_embeddings: List[Dict[str, Any]],
        top_k: int = 5,
        use_vlm: bool = True,
        use_clip: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search similar images by query image.

        Args:
            query_image: Query image bytes
            image_embeddings: List of image embedding results
            top_k: Number of results
            use_vlm: Use VLM-based similarity
            use_clip: Use CLIP-based similarity

        Returns:
            Ranked list of results
        """
        import numpy as np

        # Generate query embeddings
        query_emb = await self.embed_image(query_image)

        results = []

        for i, img_emb in enumerate(image_embeddings):
            vlm_sim = 0.0
            clip_sim = 0.0

            # VLM similarity (description-based)
            if use_vlm and query_emb.get("vlm_embedding") and img_emb.get("vlm_embedding"):
                vlm_sim = float(np.dot(
                    np.array(query_emb["vlm_embedding"]),
                    np.array(img_emb["vlm_embedding"])
                ))

            # CLIP similarity (visual)
            if use_clip and query_emb.get("clip_embedding") and img_emb.get("clip_embedding"):
                clip_sim = float(np.dot(
                    np.array(query_emb["clip_embedding"]),
                    np.array(img_emb["clip_embedding"])
                ))

            combined_sim = (
                self.vlm_weight * vlm_sim +
                self.clip_weight * clip_sim
            )

            results.append({
                "index": i,
                "vlm_similarity": vlm_sim,
                "clip_similarity": clip_sim,
                "combined_similarity": combined_sim
            })

        results.sort(key=lambda x: x["combined_similarity"], reverse=True)

        return results[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics."""
        stats = {
            "vlm_weight": self.vlm_weight,
            "clip_weight": self.clip_weight,
            "enable_clip": self.enable_clip
        }

        if self._image_service:
            stats["vlm_stats"] = self._image_service.get_stats()

        if self._clip_service:
            stats["clip_stats"] = self._clip_service.get_stats()

        return stats


# Factory functions
_clip_service: Optional[CLIPEmbeddingService] = None
_hybrid_service: Optional[HybridImageEmbedding] = None


def get_clip_embedding_service() -> CLIPEmbeddingService:
    """Get or create global CLIP embedding service."""
    global _clip_service
    if _clip_service is None:
        _clip_service = CLIPEmbeddingService(lazy_load=True)
    return _clip_service


def get_hybrid_image_embedding() -> HybridImageEmbedding:
    """Get or create global hybrid image embedding service."""
    global _hybrid_service
    if _hybrid_service is None:
        _hybrid_service = HybridImageEmbedding()
    return _hybrid_service


def reset_services():
    """Reset global services (for testing)."""
    global _clip_service, _hybrid_service
    _clip_service = None
    _hybrid_service = None
