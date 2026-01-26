"""
Vision Cache Service

Caching layer for Vision LLM results to reduce costs and improve performance.
Supports both in-memory and Redis backends.
"""

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from app.api.models.vision import (
    DocumentVisionResult,
    DocumentVisualProfile,
    ImageAnalysisResult,
    UnifiedQueryResponse,
)

logger = logging.getLogger(__name__)


class VisionCacheService:
    """
    Vision result caching service.

    Caches:
    - Document visual profiles (long TTL: 7 days)
    - Document analysis results (long TTL: 7 days)
    - Query responses (short TTL: 1 hour)
    - Image analysis results (medium TTL: 24 hours)

    Cache keys are based on content hashes for consistency.
    """

    # Default TTL values (in seconds)
    DEFAULT_PROFILE_TTL = 7 * 24 * 3600  # 7 days
    DEFAULT_ANALYSIS_TTL = 7 * 24 * 3600  # 7 days
    DEFAULT_QUERY_TTL = 3600  # 1 hour
    DEFAULT_IMAGE_TTL = 24 * 3600  # 24 hours

    def __init__(
        self,
        cache_backend: Optional[Any] = None,
        profile_ttl: int = None,
        analysis_ttl: int = None,
        query_ttl: int = None,
        image_ttl: int = None,
    ):
        """
        Initialize cache service.

        Args:
            cache_backend: Optional Redis or other cache backend.
                           If None, uses in-memory dict cache.
            profile_ttl: TTL for document profiles (seconds)
            analysis_ttl: TTL for document analysis (seconds)
            query_ttl: TTL for query responses (seconds)
            image_ttl: TTL for image analysis (seconds)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._backend = cache_backend
        self._profile_ttl = profile_ttl or self.DEFAULT_PROFILE_TTL
        self._analysis_ttl = analysis_ttl or self.DEFAULT_ANALYSIS_TTL
        self._query_ttl = query_ttl or self.DEFAULT_QUERY_TTL
        self._image_ttl = image_ttl or self.DEFAULT_IMAGE_TTL

        # Statistics
        self._hits = 0
        self._misses = 0

    # ==================== Document Profile Cache ====================

    async def get_document_profile(
        self,
        document_id: str,
        content_hash: Optional[str] = None,
    ) -> Optional[DocumentVisualProfile]:
        """
        Get cached document visual profile.

        Args:
            document_id: Document identifier
            content_hash: Optional content hash for cache validation

        Returns:
            Cached profile or None if not found/expired
        """
        cache_key = self._make_key("profile", document_id, content_hash)
        return await self._get(cache_key, DocumentVisualProfile)

    async def cache_document_profile(
        self,
        document_id: str,
        profile: DocumentVisualProfile,
        content_hash: Optional[str] = None,
    ) -> None:
        """
        Cache document visual profile.

        Args:
            document_id: Document identifier
            profile: Visual profile to cache
            content_hash: Optional content hash for cache key
        """
        cache_key = self._make_key("profile", document_id, content_hash)
        await self._set(cache_key, profile.to_dict(), self._profile_ttl)

    # ==================== Document Analysis Cache ====================

    async def get_document_analysis(
        self,
        document_id: str,
        profile_hash: Optional[str] = None,
    ) -> Optional[DocumentVisionResult]:
        """
        Get cached document vision analysis result.

        Args:
            document_id: Document identifier
            profile_hash: Hash of visual profile for cache validation

        Returns:
            Cached analysis result or None
        """
        cache_key = self._make_key("analysis", document_id, profile_hash)
        data = await self._get_raw(cache_key)

        if data:
            try:
                return self._deserialize_vision_result(data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached analysis: {e}")
                return None

        return None

    async def cache_document_analysis(
        self,
        document_id: str,
        result: DocumentVisionResult,
        profile_hash: Optional[str] = None,
    ) -> None:
        """
        Cache document vision analysis result.

        Args:
            document_id: Document identifier
            result: Vision analysis result to cache
            profile_hash: Hash of visual profile for cache key
        """
        cache_key = self._make_key("analysis", document_id, profile_hash)
        data = result.to_dict()
        await self._set(cache_key, data, self._analysis_ttl)

    # ==================== Query Response Cache ====================

    async def get_query_response(
        self,
        query_hash: str,
        context_hash: str,
    ) -> Optional[UnifiedQueryResponse]:
        """
        Get cached query response.

        Args:
            query_hash: Hash of the query
            context_hash: Hash of the context (retrieved documents)

        Returns:
            Cached response or None
        """
        cache_key = self._make_key("query", query_hash, context_hash)
        data = await self._get_raw(cache_key)

        if data:
            try:
                return self._deserialize_query_response(data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached query response: {e}")
                return None

        return None

    async def cache_query_response(
        self,
        query_hash: str,
        context_hash: str,
        response: UnifiedQueryResponse,
    ) -> None:
        """
        Cache query response.

        Args:
            query_hash: Hash of the query
            context_hash: Hash of the context
            response: Response to cache
        """
        cache_key = self._make_key("query", query_hash, context_hash)
        data = response.to_dict()
        await self._set(cache_key, data, self._query_ttl)

    # ==================== Image Analysis Cache ====================

    async def get_image_analysis(
        self,
        image_hash: str,
        task: str,
    ) -> Optional[ImageAnalysisResult]:
        """
        Get cached image analysis result.

        Args:
            image_hash: Hash of the image content
            task: Analysis task performed

        Returns:
            Cached analysis or None
        """
        cache_key = self._make_key("image", image_hash, task)
        data = await self._get_raw(cache_key)

        if data:
            try:
                return ImageAnalysisResult(
                    image_id=data.get("image_id", ""),
                    page_number=data.get("page_number"),
                    description=data.get("description", ""),
                    extracted_text=data.get("extracted_text"),
                    extracted_data=data.get("extracted_data"),
                    confidence=data.get("confidence", 1.0),
                    processing_time_ms=data.get("processing_time_ms", 0.0),
                )
            except Exception as e:
                logger.warning(f"Failed to deserialize cached image analysis: {e}")
                return None

        return None

    async def cache_image_analysis(
        self,
        image_hash: str,
        task: str,
        result: ImageAnalysisResult,
    ) -> None:
        """
        Cache image analysis result.

        Args:
            image_hash: Hash of the image content
            task: Analysis task
            result: Analysis result to cache
        """
        cache_key = self._make_key("image", image_hash, task)
        data = {
            "image_id": result.image_id,
            "page_number": result.page_number,
            "description": result.description,
            "extracted_text": result.extracted_text,
            "extracted_data": result.extracted_data,
            "confidence": result.confidence,
            "processing_time_ms": result.processing_time_ms,
        }
        await self._set(cache_key, data, self._image_ttl)

    # ==================== Cache Management ====================

    async def invalidate_document(self, document_id: str) -> int:
        """
        Invalidate all cached entries for a document.

        Args:
            document_id: Document to invalidate

        Returns:
            Number of entries invalidated
        """
        count = 0
        prefix = f"vision:profile:{document_id}"
        analysis_prefix = f"vision:analysis:{document_id}"

        if self._backend:
            # Redis backend
            keys = await self._backend.keys(f"{prefix}*")
            keys.extend(await self._backend.keys(f"{analysis_prefix}*"))
            if keys:
                count = await self._backend.delete(*keys)
        else:
            # In-memory backend
            keys_to_delete = [
                k for k in self._cache
                if k.startswith(prefix) or k.startswith(analysis_prefix)
            ]
            for key in keys_to_delete:
                del self._cache[key]
            count = len(keys_to_delete)

        logger.info(f"Invalidated {count} cache entries for document {document_id}")
        return count

    async def clear_expired(self) -> int:
        """
        Clear expired entries from in-memory cache.

        Returns:
            Number of entries cleared
        """
        if self._backend:
            # Redis handles expiration automatically
            return 0

        now = datetime.now(timezone.utc)
        keys_to_delete = [
            k for k, v in self._cache.items()
            if v.get("expires_at") and v["expires_at"] < now
        ]

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "entries": len(self._cache) if not self._backend else "unknown",
        }

    # ==================== Internal Methods ====================

    def _make_key(self, prefix: str, *parts: str) -> str:
        """Create cache key from parts."""
        clean_parts = [p for p in parts if p]
        return f"vision:{prefix}:{':'.join(clean_parts)}"

    async def _get_raw(self, key: str) -> Optional[Dict]:
        """Get raw cached data."""
        if self._backend:
            data = await self._backend.get(key)
            if data:
                self._hits += 1
                return json.loads(data)
            self._misses += 1
            return None
        else:
            entry = self._cache.get(key)
            if entry:
                # Check expiration
                if entry.get("expires_at") and entry["expires_at"] < datetime.now(timezone.utc):
                    del self._cache[key]
                    self._misses += 1
                    return None
                self._hits += 1
                return entry.get("data")
            self._misses += 1
            return None

    async def _get(self, key: str, dataclass_type: type) -> Optional[Any]:
        """Get and deserialize cached data."""
        data = await self._get_raw(key)
        if data:
            try:
                return dataclass_type(**data)
            except Exception:
                return None
        return None

    async def _set(self, key: str, data: Dict, ttl: int) -> None:
        """Set cached data with TTL."""
        if self._backend:
            await self._backend.setex(key, ttl, json.dumps(data))
        else:
            self._cache[key] = {
                "data": data,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
            }

    def _deserialize_vision_result(self, data: Dict) -> DocumentVisionResult:
        """Deserialize DocumentVisionResult from dict."""
        # This is a simplified deserialization
        # Full implementation would handle all nested dataclasses
        profile_data = data.get("visual_profile", {})
        profile = DocumentVisualProfile(
            document_id=profile_data.get("document_id", ""),
            mime_type=profile_data.get("mime_type", ""),
            extension=profile_data.get("extension", ""),
        )

        return DocumentVisionResult(
            document_id=data.get("document_id", ""),
            visual_profile=profile,
            extracted_images=[],  # Images not cached (too large)
            analysis_results=[],
            all_extracted_text=data.get("all_extracted_text", ""),
            processing_time_ms=data.get("processing_time_ms", 0.0),
            vision_model_used=data.get("vision_model_used"),
            total_cost=data.get("total_cost", 0.0),
        )

    def _deserialize_query_response(self, data: Dict) -> UnifiedQueryResponse:
        """Deserialize UnifiedQueryResponse from dict."""
        from app.api.models.vision import (
            RoutingInfo,
            SourceInfo,
            ResponseMetadata,
        )

        routing_data = data.get("routing", {})
        routing = RoutingInfo(
            selected_llm=routing_data.get("selected_llm", "text"),
            reasoning=routing_data.get("reasoning", ""),
            query_type=routing_data.get("query_type", "vector"),
            visual_signals_detected=routing_data.get("visual_signals_detected", False),
        )

        sources = [
            SourceInfo(
                document_id=s.get("document_id", ""),
                filename=s.get("filename", ""),
                page_number=s.get("page_number"),
                chunk_text=s.get("chunk_text", ""),
                relevance_score=s.get("relevance_score", 0.0),
                has_visual_content=s.get("has_visual_content", False),
            )
            for s in data.get("sources", [])
        ]

        metadata_data = data.get("metadata", {})
        metadata = ResponseMetadata(
            total_tokens=metadata_data.get("total_tokens", 0),
            latency_ms=metadata_data.get("latency_ms", 0.0),
            model_used=metadata_data.get("model_used", ""),
            vision_model_used=metadata_data.get("vision_model_used"),
            cache_hit=True,  # This is from cache
        )

        return UnifiedQueryResponse(
            answer=data.get("answer", ""),
            confidence=data.get("confidence", 0.0),
            routing=routing,
            sources=sources,
            visual_analysis=None,  # Visual analysis not cached (too large)
            metadata=metadata,
        )


def hash_content(content: bytes) -> str:
    """Generate SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()[:16]


def hash_query(query: str, language: str = "") -> str:
    """Generate hash for a query."""
    content = f"{query}:{language}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_context(documents: list) -> str:
    """Generate hash for document context."""
    doc_ids = sorted([str(d.get("id", "")) for d in documents])
    content = ":".join(doc_ids)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
