"""
Scoring Configuration Service

Manages RAG scoring configuration with:
- Environment fallback
- Database persistence
- Runtime override via Admin API
- Configuration history tracking
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID, uuid4

from ..models.scoring_config import (
    ScoringConfig,
    ScoringConfigDB,
    ScoringConfigHistory,
    ParameterMetadata,
    RRFConfig,
    BoostConfig,
    BM25Config,
    ConfidenceConfig,
    EvaluationConfig,
    LengthScoreConfig,
    KeywordExtractionConfig,
    SearchConfig,
    StreamingConfig,
    CacheConfig,
    HybridScoreConfig,
)

logger = logging.getLogger(__name__)


class ScoringConfigService:
    """
    Centralized scoring configuration management.

    Configuration priority (low to high):
    1. Default values (Pydantic defaults)
    2. Environment variables
    3. Database (PostgreSQL)
    4. Runtime override (Admin API)
    """

    def __init__(self, db_pool=None, cache=None, repository=None):
        self._db_pool = db_pool
        self._cache = cache
        self._repository = repository  # PostgresScoringConfigRepository
        self._runtime_override: Optional[ScoringConfig] = None
        self._cached_config: Optional[ScoringConfig] = None
        self._cache_key = "scoring_config:active"

    def set_repository(self, repository) -> None:
        """Set the repository instance (for lazy initialization)."""
        self._repository = repository

    async def get_active_config(self) -> ScoringConfig:
        """
        Get currently active scoring configuration.

        Priority:
        1. Runtime override (if set)
        2. Cache
        3. Database
        4. Environment + Defaults
        """
        # Runtime override has highest priority
        if self._runtime_override:
            return self._runtime_override

        # Try cache
        if self._cache:
            try:
                cached = await self._cache.get(self._cache_key)
                if cached:
                    return ScoringConfig.model_validate_json(cached)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

        # Try database via repository
        if self._repository:
            try:
                db_config = await self._repository.get_active_config()
                if db_config:
                    await self._set_cache(db_config)
                    self._cached_config = db_config
                    return db_config
            except Exception as e:
                logger.warning(f"Database read error: {e}")

        # Fallback to environment + defaults
        return self._load_from_env()

    def get_active_config_sync(self) -> ScoringConfig:
        """
        Synchronous version for non-async contexts.
        Returns cached config or loads from environment.
        """
        if self._runtime_override:
            return self._runtime_override

        if self._cached_config:
            return self._cached_config

        self._cached_config = self._load_from_env()
        return self._cached_config

    def _load_from_env(self) -> ScoringConfig:
        """Load configuration from environment variables."""

        def get_float(key: str, default: float) -> float:
            return float(os.getenv(key, default))

        def get_int(key: str, default: int) -> int:
            return int(os.getenv(key, default))

        def get_bool(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() in ('true', '1', 'yes')

        return ScoringConfig(
            rrf=RRFConfig(
                k=get_int("SCORING_RRF_K", 60),
                neo4j_weight=get_float("SCORING_RRF_NEO4J_WEIGHT", 1.0),
                postgres_weight=get_float("SCORING_RRF_POSTGRES_WEIGHT", 1.0),
            ),
            boost=BoostConfig(
                title_match_enabled=get_bool("SCORING_BOOST_TITLE_ENABLED", True),
                title_match_boost=get_float("SCORING_BOOST_TITLE", 1.5),
                error_code_enabled=get_bool("SCORING_BOOST_ERROR_CODE_ENABLED", True),
                error_code_boost=get_float("SCORING_BOOST_ERROR_CODE", 1.5),
                exact_phrase_boost=get_float("SCORING_BOOST_EXACT_PHRASE", 5.0),
                exact_phrase_base_add=get_float("SCORING_BOOST_EXACT_PHRASE_BASE", 1.0),
                partial_phrase_boost=get_float("SCORING_BOOST_PARTIAL_PHRASE", 2.0),
                partial_phrase_base_add=get_float("SCORING_BOOST_PARTIAL_PHRASE_BASE", 0.5),
                web_priority_boost=get_float("SCORING_BOOST_WEB_PRIORITY", 3.0),
                web_priority_penalty=get_float("SCORING_BOOST_WEB_PENALTY", 0.3),
            ),
            bm25=BM25Config(
                k1=get_float("SCORING_BM25_K1", 1.5),
                b=get_float("SCORING_BM25_B", 0.75),
                # Extended BM25 settings (v2.0)
                min_score_threshold=get_float("SCORING_BM25_MIN_SCORE", 0.01),
                max_feature_lines=get_int("SCORING_BM25_MAX_FEATURES", 5),
            ),
            confidence=ConfidenceConfig(
                high_threshold=get_float("SCORING_CONFIDENCE_HIGH", 0.7),
                medium_threshold=get_float("SCORING_CONFIDENCE_MEDIUM", 0.4),
                low_threshold=get_float("SCORING_CONFIDENCE_LOW", 0.3),
                score_high_threshold=get_float("SCORING_SCORE_HIGH", 0.8),
                score_medium_threshold=get_float("SCORING_SCORE_MEDIUM", 0.6),
                score_low_threshold=get_float("SCORING_SCORE_LOW", 0.4),
                # Extended confidence settings (v2.0)
                grounding_max_bonus=get_float("SCORING_CONF_GROUNDING_MAX_BONUS", 0.1),
                source_ratio_weight=get_float("SCORING_CONF_SOURCE_RATIO_WEIGHT", 0.9),
                completeness_execution_weight=get_float("SCORING_CONF_COMPLETENESS_EXEC", 0.6),
                completeness_length_weight=get_float("SCORING_CONF_COMPLETENESS_LEN", 0.4),
                default_confidence=get_float("SCORING_CONF_DEFAULT", 0.85),
                source_present_confidence=get_float("SCORING_CONF_SOURCE_PRESENT", 0.85),
                no_source_confidence=get_float("SCORING_CONF_NO_SOURCE", 0.3),
                classify_confidence_scale=get_float("SCORING_CONF_CLASSIFY_SCALE", 1.5),
                classify_confidence_cap=get_float("SCORING_CONF_CLASSIFY_CAP", 0.99),
            ),
            evaluation=EvaluationConfig(
                base_score=get_float("SCORING_EVAL_BASE", 0.5),
                hallucination_penalty=get_float("SCORING_EVAL_HALLUCINATION_PENALTY", 0.5),
                source_mismatch_penalty=get_float("SCORING_EVAL_SOURCE_MISMATCH_PENALTY", 0.2),
                format_error_penalty=get_float("SCORING_EVAL_FORMAT_ERROR_PENALTY", 0.15),
                pass_threshold=get_float("SCORING_EVAL_PASS_THRESHOLD", 0.6),
                retry_threshold=get_float("SCORING_EVAL_RETRY_THRESHOLD", 0.4),
            ),
            keyword_extraction=KeywordExtractionConfig(
                llm_timeout=get_float("SCORING_KEYWORD_LLM_TIMEOUT", 3.0),
                llm_max_tokens=get_int("SCORING_KEYWORD_LLM_MAX_TOKENS", 200),
                cache_max_size=get_int("SCORING_KEYWORD_CACHE_SIZE", 1000),
                cache_ttl_seconds=get_int("SCORING_KEYWORD_CACHE_TTL", 3600),
            ),
            search=SearchConfig(
                default_top_k=get_int("SCORING_SEARCH_DEFAULT_TOP_K", 5),
                max_top_k=get_int("SCORING_SEARCH_MAX_TOP_K", 20),
                keyword_only_default_score=get_float("SCORING_SEARCH_KEYWORD_ONLY_SCORE", 0.1),
                no_result_rank=get_int("SCORING_SEARCH_NO_RESULT_RANK", 999),
                linked_chunk_score_multiplier=get_float("SCORING_SEARCH_LINKED_CHUNK_MULTIPLIER", 0.8),
                linked_chunk_default_score=get_float("SCORING_SEARCH_LINKED_CHUNK_DEFAULT_SCORE", 0.5),
                # Extended search settings (v2.0)
                session_min_score=get_float("SCORING_SEARCH_SESSION_MIN", 0.3),
                external_min_score=get_float("SCORING_SEARCH_EXTERNAL_MIN", 0.3),
                global_skip_threshold=get_float("SCORING_SEARCH_GLOBAL_SKIP", 0.7),
                scoped_min_similarity=get_float("SCORING_SEARCH_SCOPED_MIN", 0.2),
                multi_product_min_score=get_float("SCORING_SEARCH_MULTI_PRODUCT_MIN", 0.3),
            ),
            # NEW: Streaming config (v2.0)
            streaming=StreamingConfig(
                delay_seconds=get_float("SCORING_STREAMING_DELAY", 0.02),
            ),
            # NEW: Cache config (v2.0)
            cache=CacheConfig(
                scoring_cache_ttl=get_int("SCORING_CACHE_TTL", 3600),
            ),
        )

    async def _set_cache(self, config: ScoringConfig) -> None:
        """Cache the configuration."""
        if not self._cache:
            return

        try:
            await self._cache.set(
                self._cache_key,
                config.model_dump_json(),
                ex=config.cache.scoring_cache_ttl  # Configurable TTL
            )
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    async def update_config(
        self,
        new_config: ScoringConfig,
        user_id: Optional[UUID] = None,
        reason: Optional[str] = None
    ) -> ScoringConfig:
        """
        Update scoring configuration.

        - Saves to database
        - Records history
        - Invalidates cache
        """
        # Save to database via repository
        if self._repository:
            try:
                await self._repository.update_config(
                    config=new_config,
                    user_id=user_id,
                    reason=reason
                )
                logger.info(f"Config saved to DB by {user_id}: {reason}")
            except Exception as e:
                logger.warning(f"Database save error: {e}")

        # Update runtime override
        self._runtime_override = new_config
        self._cached_config = new_config

        # Invalidate cache
        if self._cache:
            try:
                await self._cache.delete(self._cache_key)
            except Exception as e:
                logger.warning(f"Cache invalidation error: {e}")

        return new_config

    def set_runtime_override(self, config: ScoringConfig) -> None:
        """Set runtime override (in-memory only)."""
        self._runtime_override = config
        self._cached_config = config
        logger.info("Runtime config override set")

    def clear_runtime_override(self) -> None:
        """Clear runtime override, revert to DB/env config."""
        self._runtime_override = None
        self._cached_config = None
        logger.info("Runtime config override cleared")

    async def get_config_history(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[ScoringConfigHistory]:
        """Get configuration change history."""
        if not self._repository:
            return []

        try:
            return await self._repository.get_history(limit=limit, offset=offset)
        except Exception as e:
            logger.warning(f"Failed to get config history: {e}")
            return []

    async def rollback_config(
        self,
        history_id: UUID,
        user_id: Optional[UUID] = None
    ) -> ScoringConfig:
        """Rollback to a previous configuration."""
        if not self._repository:
            raise NotImplementedError("Repository not configured for rollback")

        rolled_back = await self._repository.rollback_to_version(
            history_id=history_id,
            user_id=user_id
        )

        if not rolled_back:
            raise ValueError(f"History entry {history_id} not found")

        # Update runtime state
        self._runtime_override = rolled_back
        self._cached_config = rolled_back

        # Invalidate cache
        if self._cache:
            try:
                await self._cache.delete(self._cache_key)
            except Exception:
                pass

        return rolled_back

    def get_parameter_metadata(self) -> Dict[str, ParameterMetadata]:
        """
        Extract parameter metadata from Pydantic models.

        Returns metadata for all configurable parameters including:
        - Description
        - Default value
        - Min/max range
        - Effect description
        - Trade-off warnings
        """
        metadata = {}

        # Extract from each config class
        config_classes = [
            ("rrf", RRFConfig),
            ("boost", BoostConfig),
            ("bm25", BM25Config),
            ("confidence", ConfidenceConfig),
            ("evaluation", EvaluationConfig),
            ("length_score", LengthScoreConfig),
            ("keyword_extraction", KeywordExtractionConfig),
            ("search", SearchConfig),
        ]

        for prefix, config_class in config_classes:
            for field_name, field_info in config_class.model_fields.items():
                full_name = f"{prefix}.{field_name}"
                extra = field_info.json_schema_extra or {}

                metadata[full_name] = ParameterMetadata(
                    name=full_name,
                    description=field_info.description or "",
                    default=field_info.default,
                    min_value=getattr(field_info, 'ge', None),
                    max_value=getattr(field_info, 'le', None),
                    effect=extra.get('effect'),
                    trade_off=extra.get('trade_off'),
                    recommended_range=extra.get('recommended_range'),
                    category=extra.get('category', prefix),
                )

        return metadata

    def validate_config(self, config: ScoringConfig) -> List[str]:
        """
        Validate configuration and return list of warnings.

        Checks for:
        - Conflicting settings
        - Extreme values
        - Potential issues
        """
        warnings = []

        # RRF checks
        if config.rrf.k < 30:
            warnings.append("RRF k < 30 may over-emphasize top ranks")
        if config.rrf.k > 100:
            warnings.append("RRF k > 100 may make ranks too similar")

        # Boost checks
        if config.boost.title_match_boost > 3.0:
            warnings.append("High title boost may ignore content quality")
        if config.boost.exact_phrase_boost > 7.0:
            warnings.append("Very high exact phrase boost may cause ranking issues")

        # Confidence checks
        if config.confidence.high_threshold < config.confidence.medium_threshold:
            warnings.append("High threshold should be greater than medium threshold")
        if config.confidence.medium_threshold < config.confidence.low_threshold:
            warnings.append("Medium threshold should be greater than low threshold")

        # Evaluation checks
        if config.evaluation.pass_threshold < config.evaluation.retry_threshold:
            warnings.append("Pass threshold should be greater than retry threshold")

        return warnings


# Singleton instance
_scoring_config_service: Optional[ScoringConfigService] = None


def get_scoring_config_service(
    db_session=None,
    cache=None
) -> ScoringConfigService:
    """Get or create the scoring config service singleton."""
    global _scoring_config_service

    if _scoring_config_service is None:
        _scoring_config_service = ScoringConfigService(db_session, cache)

    return _scoring_config_service


async def get_scoring_config() -> ScoringConfig:
    """Convenience function to get current scoring config."""
    service = get_scoring_config_service()
    return await service.get_active_config()


def get_scoring_config_sync() -> ScoringConfig:
    """Synchronous convenience function."""
    service = get_scoring_config_service()
    return service.get_active_config_sync()


# ═══════════════════════════════════════════════════════════════════════════════
# Hybrid Score Config Extensions (v1.0 - Hardcoding Elimination)
# ═══════════════════════════════════════════════════════════════════════════════

# Hybrid config singleton
_hybrid_config: Optional[HybridScoreConfig] = None


def _load_hybrid_from_env() -> HybridScoreConfig:
    """Load Hybrid Score configuration from environment variables."""

    def get_float(key: str, default: float) -> float:
        return float(os.getenv(key, default))

    def get_int(key: str, default: int) -> int:
        return int(os.getenv(key, default))

    return HybridScoreConfig(
        # Weight Distribution
        vector_weight=get_float("HYBRID_VECTOR_WEIGHT", 0.6),
        graph_weight=get_float("HYBRID_GRAPH_WEIGHT", 0.4),
        bm25_weight=get_float("HYBRID_BM25_WEIGHT", 0.3),
        semantic_weight=get_float("HYBRID_SEMANTIC_WEIGHT", 0.7),

        # Topic Density
        topic_density_base=get_float("HYBRID_TOPIC_BASE", 0.4),
        topic_density_weight=get_float("HYBRID_TOPIC_WEIGHT", 0.2),
        topic_density_min_threshold=get_float("HYBRID_TOPIC_MIN", 0.15),

        # Source Priority
        error_code_priority=get_float("HYBRID_ERROR_PRIORITY", 1.0),
        verified_result_boost=get_float("HYBRID_VERIFIED_BOOST", 1.5),
        glossary_boost=get_float("HYBRID_GLOSSARY_BOOST", 1.1),

        # Overlap Boost
        topic_boost_increment=get_float("HYBRID_TOPIC_INCREMENT", 0.2),
        vector_boost_increment=get_float("HYBRID_VECTOR_INCREMENT", 0.1),
        graph_boost_increment=get_float("HYBRID_GRAPH_INCREMENT", 0.1),
        keyword_match_boost=get_float("HYBRID_KEYWORD_BOOST", 0.1),

        # Normalization
        entity_match_normalization_divisor=get_float("HYBRID_ENTITY_NORM", 5.0),
        normalization_epsilon=get_float("HYBRID_NORM_EPSILON", 1e-8),
        min_relevance_score=get_float("RAG_MIN_RELEVANCE_SCORE", 0.3),

        # Search Multipliers
        deep_analysis_multiplier=get_int("HYBRID_DEEP_MULT", 4),
        comprehensive_query_multiplier=get_int("HYBRID_COMP_MULT", 2),
        topic_search_multiplier=get_int("HYBRID_TOPIC_MULT", 3),
        min_entity_k=get_int("HYBRID_MIN_ENTITY_K", 5),

        # Result Limits
        simple_query_results=get_int("HYBRID_SIMPLE_RESULTS", 5),
        standard_query_results=get_int("HYBRID_STANDARD_RESULTS", 10),
        comprehensive_query_results=get_int("HYBRID_COMP_RESULTS", 20),

        # Document Source Weights
        session_document_weight=get_float("HYBRID_SESSION_WEIGHT", 2.0),
        external_document_weight=get_float("HYBRID_EXTERNAL_WEIGHT", 2.5),
    )


def get_hybrid_config() -> HybridScoreConfig:
    """
    Get Hybrid Score configuration.

    Loads from environment variables on first call, then caches.
    Thread-safe singleton pattern.

    Returns:
        HybridScoreConfig instance
    """
    global _hybrid_config

    if _hybrid_config is None:
        _hybrid_config = _load_hybrid_from_env()
        logger.info("HybridScoreConfig loaded from environment")

    return _hybrid_config


def get_hybrid_config_sync() -> HybridScoreConfig:
    """Synchronous convenience function for HybridScoreConfig."""
    return get_hybrid_config()


def update_hybrid_config(updates: Dict[str, Any]) -> HybridScoreConfig:
    """
    Update Hybrid Score configuration at runtime.

    Args:
        updates: Dictionary of field names to new values

    Returns:
        Updated HybridScoreConfig
    """
    global _hybrid_config

    current = get_hybrid_config()
    current_dict = current.model_dump()
    current_dict.update(updates)

    _hybrid_config = HybridScoreConfig.model_validate(current_dict)
    logger.info(f"HybridScoreConfig updated: {list(updates.keys())}")

    return _hybrid_config


def reload_hybrid_config() -> HybridScoreConfig:
    """
    Reload Hybrid Score configuration from environment.

    Clears cache and reloads from environment variables.
    """
    global _hybrid_config
    _hybrid_config = None
    return get_hybrid_config()


def get_hybrid_parameter_metadata() -> Dict[str, ParameterMetadata]:
    """
    Extract parameter metadata from HybridScoreConfig.

    Returns metadata for all configurable parameters including:
    - Description
    - Default value
    - Min/max range
    - Effect description
    - Category
    """
    metadata = {}

    for field_name, field_info in HybridScoreConfig.model_fields.items():
        extra = field_info.json_schema_extra or {}

        metadata[field_name] = ParameterMetadata(
            name=field_name,
            description=field_info.description or "",
            default=field_info.default,
            min_value=getattr(field_info, 'ge', None),
            max_value=getattr(field_info, 'le', None),
            effect=extra.get('effect'),
            trade_off=extra.get('trade_off'),
            recommended_range=extra.get('recommended_range'),
            category=extra.get('category', 'hybrid'),
        )

    return metadata


def validate_hybrid_config(config: HybridScoreConfig) -> List[str]:
    """
    Validate HybridScoreConfig and return list of warnings.

    Checks for:
    - Weight sum issues
    - Extreme values
    - Potential issues
    """
    warnings = []

    # Weight sum checks
    if abs((config.vector_weight + config.graph_weight) - 1.0) > 0.01:
        warnings.append(
            f"vector_weight ({config.vector_weight}) + graph_weight ({config.graph_weight}) "
            f"= {config.vector_weight + config.graph_weight}, should be 1.0"
        )

    if abs((config.bm25_weight + config.semantic_weight) - 1.0) > 0.01:
        warnings.append(
            f"bm25_weight ({config.bm25_weight}) + semantic_weight ({config.semantic_weight}) "
            f"= {config.bm25_weight + config.semantic_weight}, should be 1.0"
        )

    # Topic density formula range check
    max_topic_score = config.topic_density_base + config.topic_density_weight
    if max_topic_score > 1.0:
        warnings.append(
            f"Topic score can exceed 1.0: {config.topic_density_base} + {config.topic_density_weight} = {max_topic_score}"
        )

    # Boost checks
    if config.glossary_boost > 1.5:
        warnings.append("High glossary_boost may over-prioritize glossary results")

    if config.keyword_match_boost > 0.3:
        warnings.append("High keyword_match_boost may over-weight keyword matches")

    # Relevance threshold check
    if config.min_relevance_score > 0.5:
        warnings.append("High min_relevance_score may filter too many results")

    return warnings
