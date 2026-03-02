"""
Metadata Configuration Service
Central service for accessing metadata from PostgreSQL with Redis caching.
Replaces hardcoded values in opencode_service, summary_search_service, query_expansion_service.
"""
import logging
from typing import Optional, List, Dict, Tuple, Any
from datetime import timedelta

logger = logging.getLogger(__name__)

# Cache service instance (Redis or InMemory fallback)
_cache_service = None


async def _get_cache_service():
    """Lazy load cache service (Redis with InMemory fallback)."""
    global _cache_service
    if _cache_service is None:
        try:
            from ..ims_crawler.infrastructure.dependencies import get_cache_service
            _cache_service = await get_cache_service()
            logger.info("MetadataConfigService using shared cache service")
        except Exception as e:
            logger.warning(f"Failed to get cache service: {e}, using local fallback")
            from ..ims_crawler.infrastructure.services import InMemoryCacheService
            _cache_service = InMemoryCacheService(default_ttl=timedelta(minutes=5))
    return _cache_service


class MetadataConfigService:
    """
    Central metadata configuration service.
    - Loads configuration from PostgreSQL
    - Caches data with Redis (or InMemory fallback) for performance
    - Provides fallback to hardcoded values during migration
    """

    # Cache key prefix for metadata
    CACHE_PREFIX = "metadata:"
    CACHE_TTL = timedelta(minutes=5)

    def __init__(self, repository):
        """
        Initialize with MetadataRepository.

        Args:
            repository: MetadataRepository instance
        """
        self._repo = repository
        self._cache = None  # Lazy loaded

        # Fallback hardcoded values (used during migration or DB failure)
        self._FALLBACK_GLOSSARY = {
            "TJES": {"full_name": "Tmax Job Entry Subsystem", "category": "system"},
            "TACF": {"full_name": "Tmax Access Control Facility", "category": "system"},
            "HIDB": {"full_name": "Hierarchical Database", "category": "database"},
            "OSC": {"full_name": "Online Service Controller", "category": "system"},
        }

        self._FALLBACK_MAPPINGS = {
            "HIDB": "HiDB",
            "TJES": "TJES",
            "TACF": "TACF",
            "OSC": "OSC",
            "ADRDSSU": "Utility",
            "IDCAMS": "Utility",
        }

    async def _get_cache(self):
        """Get cache service instance (lazy load)."""
        if self._cache is None:
            self._cache = await _get_cache_service()
        return self._cache

    def _make_cache_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.CACHE_PREFIX}{key}"

    async def _cache_get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            cache = await self._get_cache()
            return await cache.get(self._make_cache_key(key))
        except Exception as e:
            logger.debug(f"Cache get failed for {key}: {e}")
            return None

    async def _cache_set(self, key: str, value: Any) -> bool:
        """Set value in cache with TTL."""
        try:
            cache = await self._get_cache()
            return await cache.set(self._make_cache_key(key), value, self.CACHE_TTL)
        except Exception as e:
            logger.debug(f"Cache set failed for {key}: {e}")
            return False

    # ==================== Glossary Terms ====================

    async def get_glossary_term(self, term: str) -> Optional[Dict[str, Any]]:
        """
        Get a single glossary term.

        Args:
            term: The term to look up (case-insensitive)

        Returns:
            Dictionary with term details or None
        """
        try:
            result = await self._repo.get_glossary_term(term)
            if result:
                return result
        except Exception as e:
            logger.warning(f"DB lookup failed for glossary term '{term}': {e}")

        # Fallback
        return self._FALLBACK_GLOSSARY.get(term.upper())

    async def get_all_glossary_terms(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all glossary terms as a dictionary.
        Cached in Redis for performance.

        Returns:
            Dictionary mapping term -> details
        """
        cache_key = "glossary_all"

        # Try cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            terms_list = await self._repo.get_glossary_terms(active_only=True)
            result = {t['term']: t for t in terms_list}
            await self._cache_set(cache_key, result)
            logger.debug(f"Loaded {len(result)} glossary terms from DB")
            return result
        except Exception as e:
            logger.warning(f"Failed to load glossary terms: {e}")
            return self._FALLBACK_GLOSSARY

    async def is_core_term(self, term: str) -> bool:
        """Check if a term is a core domain term."""
        glossary = await self.get_all_glossary_terms()
        return term.upper() in glossary

    # ==================== Document Mappings ====================

    async def get_document_pattern(self, keyword: str) -> Optional[str]:
        """
        Get document pattern for a keyword.

        Args:
            keyword: The keyword to look up

        Returns:
            Document pattern string or None
        """
        try:
            result = await self._repo.get_document_pattern(keyword)
            if result:
                return result
        except Exception as e:
            logger.warning(f"DB lookup failed for document pattern '{keyword}': {e}")

        # Fallback
        return self._FALLBACK_MAPPINGS.get(keyword.upper())

    async def get_all_document_mappings(self) -> Dict[str, str]:
        """
        Get all document mappings as keyword -> pattern dictionary.
        Cached in Redis for performance.

        Returns:
            Dictionary mapping keyword -> document_pattern
        """
        cache_key = "mappings_all"

        # Try cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            mappings_list = await self._repo.get_document_mappings(active_only=True)
            # Group by keyword, keeping lowest priority
            result = {}
            for m in mappings_list:
                kw = m['keyword']
                if kw not in result:
                    result[kw] = m['document_pattern']
            await self._cache_set(cache_key, result)
            logger.debug(f"Loaded {len(result)} document mappings from DB")
            return result
        except Exception as e:
            logger.warning(f"Failed to load document mappings: {e}")
            return self._FALLBACK_MAPPINGS

    async def find_document_for_keyword(self, text: str) -> Optional[str]:
        """
        Find document pattern for any keyword found in text.

        Args:
            text: Text to search for keywords

        Returns:
            Document pattern or None
        """
        mappings = await self.get_all_document_mappings()
        text_upper = text.upper()

        for keyword, pattern in mappings.items():
            if keyword in text_upper:
                return pattern
        return None

    # ==================== Error Code Ranges ====================

    async def get_error_file(self, error_code: int) -> Optional[str]:
        """
        Get the file path for an error code.

        Args:
            error_code: Error code (positive or negative)

        Returns:
            File path string or None
        """
        try:
            result = await self._repo.find_error_range(error_code)
            if result:
                return result['file_path']
        except Exception as e:
            logger.warning(f"DB lookup failed for error code {error_code}: {e}")

        return None

    async def get_all_error_ranges(self) -> List[Dict[str, Any]]:
        """
        Get all error code ranges.
        Cached in Redis for performance.

        Returns:
            List of error range dictionaries
        """
        cache_key = "error_ranges_all"

        # Try cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            result = await self._repo.get_error_ranges(active_only=True)
            await self._cache_set(cache_key, result)
            logger.debug(f"Loaded {len(result)} error ranges from DB")
            return result
        except Exception as e:
            logger.warning(f"Failed to load error ranges: {e}")
            return []

    async def get_error_module(self, error_code: int) -> Optional[str]:
        """Get the module name for an error code."""
        try:
            result = await self._repo.find_error_range(error_code)
            if result:
                return result['module']
        except Exception as e:
            logger.warning(f"DB lookup failed for error module {error_code}: {e}")
        return None

    # ==================== Synonyms ====================

    async def get_synonyms(self, term: str, language: str = None) -> List[str]:
        """
        Get synonyms for a term.

        Args:
            term: Base term
            language: Optional language filter (ja, ko, en)

        Returns:
            List of synonym strings
        """
        try:
            return await self._repo.get_synonyms_for_term(term, language)
        except Exception as e:
            logger.warning(f"DB lookup failed for synonyms '{term}': {e}")
            return []

    async def get_all_synonyms(self, language: str = None) -> Dict[str, List[str]]:
        """
        Get all synonyms grouped by base term.
        Cached in Redis for performance.

        Args:
            language: Optional language filter

        Returns:
            Dictionary mapping base_term -> list of synonyms
        """
        cache_key = f"synonyms_{language or 'all'}"

        # Try cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            synonyms_list = await self._repo.get_synonyms(language=language, active_only=True)
            result: Dict[str, List[str]] = {}
            for s in synonyms_list:
                base = s['base_term']
                if base not in result:
                    result[base] = []
                result[base].append(s['synonym'])
            await self._cache_set(cache_key, result)
            logger.debug(f"Loaded synonyms for {len(result)} terms from DB")
            return result
        except Exception as e:
            logger.warning(f"Failed to load synonyms: {e}")
            return {}

    # ==================== Visual Keywords ====================

    async def get_visual_keywords(self, language: str = None) -> List[str]:
        """
        Get visual keywords list.

        Args:
            language: Optional language filter

        Returns:
            List of visual keyword strings
        """
        cache_key = f"visual_kw_{language or 'all'}"

        # Try cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            keywords_list = await self._repo.get_visual_keywords(
                language=language, active_only=True
            )
            result = [kw['keyword'] for kw in keywords_list]
            await self._cache_set(cache_key, result)
            logger.debug(f"Loaded {len(result)} visual keywords from DB")
            return result
        except Exception as e:
            logger.warning(f"Failed to load visual keywords: {e}")
            # Fallback
            return ["図", "プロセス図", "フローチャート", "テーブル", "表",
                    "그림", "프로세스도", "플로우차트", "diagram", "flowchart"]

    async def is_visual_keyword(self, text: str) -> Tuple[bool, float]:
        """
        Check if text contains visual keywords and return weight.

        Args:
            text: Text to check

        Returns:
            Tuple of (is_visual, weight)
        """
        try:
            # Get all visual keywords with weights
            cache_key = "visual_kw_with_weights"

            # Try cache first
            keywords_list = await self._cache_get(cache_key)
            if keywords_list is None:
                keywords_list = await self._repo.get_visual_keywords(active_only=True)
                await self._cache_set(cache_key, keywords_list)

            max_weight = 0.0
            found = False

            for kw_data in keywords_list:
                keyword = kw_data['keyword']
                weight = kw_data.get('weight', 1.0)
                if keyword in text:
                    found = True
                    if weight > max_weight:
                        max_weight = weight

            return (found, max_weight) if found else (False, 0.0)

        except Exception as e:
            logger.warning(f"Visual keyword check failed: {e}")
            # Simple fallback check
            visual_fallback = ["図", "プロセス図", "diagram", "그림"]
            for kw in visual_fallback:
                if kw in text:
                    return (True, 1.0)
            return (False, 0.0)

    # ==================== Cache Management ====================

    async def refresh_cache(self):
        """Force refresh all cached data by clearing and pre-loading."""
        try:
            cache = await self._get_cache()
            # Clear all metadata cache keys
            await cache.clear_pattern(f"{self.CACHE_PREFIX}*")
            logger.info("Metadata Redis cache cleared")
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")

        # Pre-load common data
        await self.get_all_glossary_terms()
        await self.get_all_document_mappings()
        await self.get_all_error_ranges()
        logger.info("Metadata cache pre-loaded")

    async def invalidate(self, table: str = None):
        """
        Invalidate cache for specific table or all.

        Args:
            table: Table name (glossary, mappings, error_ranges, synonyms, visual_keywords)
                   or None for all
        """
        try:
            cache = await self._get_cache()

            if table is None:
                # Clear all metadata cache keys
                deleted = await cache.clear_pattern(f"{self.CACHE_PREFIX}*")
                logger.info(f"All metadata cache invalidated ({deleted} keys)")
            else:
                # Clear specific table cache keys
                deleted = await cache.clear_pattern(f"{self.CACHE_PREFIX}*{table}*")
                logger.info(f"Metadata cache invalidated for {table} ({deleted} keys)")

        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        try:
            cache = await self._get_cache()

            # Check key existence and TTL for common keys
            common_keys = ["glossary_all", "mappings_all", "error_ranges_all", "synonyms_all"]
            stats = {
                "cache_type": type(cache).__name__,
                "cache_prefix": self.CACHE_PREFIX,
                "ttl_seconds": int(self.CACHE_TTL.total_seconds()),
                "keys_status": {}
            }

            for key in common_keys:
                full_key = self._make_cache_key(key)
                exists = await cache.exists(key)
                ttl = await cache.get_ttl(key) if hasattr(cache, 'get_ttl') else None
                stats["keys_status"][key] = {
                    "exists": exists,
                    "ttl_remaining": ttl
                }

            return stats

        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {
                "cache_type": "unknown",
                "error": str(e)
            }


# Singleton instance
_metadata_config_service: Optional[MetadataConfigService] = None


async def get_metadata_config_service() -> MetadataConfigService:
    """Get or create MetadataConfigService singleton."""
    global _metadata_config_service

    if _metadata_config_service is None:
        from ..infrastructure.postgres.metadata_repository import get_metadata_repository
        repo = await get_metadata_repository()
        _metadata_config_service = MetadataConfigService(repo)
        logger.info("MetadataConfigService initialized")

    return _metadata_config_service


# Sync function for dependency injection
def get_metadata_config_service_sync() -> Optional[MetadataConfigService]:
    """Get existing MetadataConfigService (sync version for DI)."""
    return _metadata_config_service
