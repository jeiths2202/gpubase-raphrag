"""
Scoring Configuration Models

Centralized configuration for all RAG scoring parameters.
Eliminates hardcoded values across the codebase.

All parameters are configurable via:
1. Environment variables (fallback)
2. Database (persistent storage)
3. Admin API (runtime override)
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
from uuid import UUID


class ScoreNormalization(str, Enum):
    """Score normalization methods"""
    MIN_MAX = "min_max"           # (x - min) / (max - min)
    Z_SCORE = "z_score"           # (x - mean) / std
    LOG_SCALE = "log_scale"       # log(1 + x)
    SIGMOID = "sigmoid"           # 1 / (1 + exp(-x))
    NONE = "none"                 # No normalization


class RRFConfig(BaseModel):
    """Reciprocal Rank Fusion Configuration"""

    k: int = Field(
        default=60,
        ge=1, le=1000,
        description="RRF smoothing parameter. Higher values reduce rank difference impact.",
        json_schema_extra={
            "effect": "Controls score difference between ranks",
            "trade_off": "High: ignores rank differences, Low: over-emphasizes top ranks",
            "recommended_range": [30, 100],
            "category": "rrf"
        }
    )

    neo4j_weight: float = Field(
        default=1.0,
        ge=0.0, le=3.0,
        description="Weight for Neo4j (Vector) search results",
        json_schema_extra={
            "effect": "Prioritizes semantic similarity results",
            "trade_off": "High: semantic priority, ignores keyword matching",
            "category": "rrf"
        }
    )

    postgres_weight: float = Field(
        default=1.0,
        ge=0.0, le=3.0,
        description="Weight for PostgreSQL (BM25) search results",
        json_schema_extra={
            "effect": "Prioritizes keyword matching results",
            "trade_off": "High: exact keyword priority, ignores similar expressions",
            "category": "rrf"
        }
    )


class BoostConfig(BaseModel):
    """Score Boosting Configuration"""

    # Title Match Boost
    title_match_enabled: bool = Field(
        default=True,
        description="Enable title match boosting"
    )

    title_match_boost: float = Field(
        default=1.5,
        ge=1.0, le=5.0,
        description="Boost multiplier when query keyword matches document title",
        json_schema_extra={
            "effect": "Promotes documents with matching titles",
            "trade_off": "High: title dependency increases, content quality ignored",
            "category": "boost"
        }
    )

    # Error Code Boost
    error_code_enabled: bool = Field(
        default=True,
        description="Enable error code boosting"
    )

    error_code_boost: float = Field(
        default=1.5,
        ge=1.0, le=3.0,
        description="Boost multiplier for error code matches",
        json_schema_extra={
            "effect": "Promotes error code documentation",
            "trade_off": "High: prioritizes error docs even if less relevant",
            "category": "boost"
        }
    )

    # Exact Phrase Boost (quoted search)
    exact_phrase_boost: float = Field(
        default=5.0,
        ge=1.0, le=10.0,
        description="Boost multiplier for exact phrase matches (quoted search)",
        json_schema_extra={
            "effect": "Strongly promotes exact phrase matches",
            "trade_off": "High: may miss semantically similar content",
            "category": "boost"
        }
    )

    exact_phrase_base_add: float = Field(
        default=1.0,
        ge=0.0, le=5.0,
        description="Base score addition for exact phrase matches"
    )

    partial_phrase_boost: float = Field(
        default=2.0,
        ge=1.0, le=5.0,
        description="Boost multiplier for partial phrase matches",
        json_schema_extra={
            "effect": "Moderately promotes partial matches",
            "category": "boost"
        }
    )

    partial_phrase_base_add: float = Field(
        default=0.5,
        ge=0.0, le=2.0,
        description="Base score addition for partial phrase matches"
    )

    # Web Source Priority (@ mode)
    web_priority_boost: float = Field(
        default=3.0,
        ge=1.0, le=5.0,
        description="Boost multiplier for web sources in @ mode",
        json_schema_extra={
            "effect": "Strongly promotes web sources when @ prefix used",
            "category": "boost"
        }
    )

    web_priority_penalty: float = Field(
        default=0.3,
        ge=0.1, le=1.0,
        description="Penalty multiplier for non-web sources in @ mode",
        json_schema_extra={
            "effect": "Demotes non-web sources in @ mode",
            "trade_off": "Low: may hide relevant internal docs",
            "category": "boost"
        }
    )

    # Web source boost in normal mode
    web_normal_boost_enabled: bool = Field(
        default=True,
        description="Enable moderate web boosting in normal mode"
    )

    web_normal_rank_threshold: int = Field(
        default=5,
        ge=1, le=20,
        description="Max Neo4j rank for web boost eligibility"
    )

    web_normal_rank_offset: int = Field(
        default=2,
        ge=0, le=10,
        description="Simulated PostgreSQL rank offset for web sources"
    )

    # Source count bonus (for grounding confidence)
    source_count_bonus: float = Field(
        default=0.02,
        ge=0.0, le=0.1,
        description="Bonus per source for grounding confidence calculation"
    )


class BM25Config(BaseModel):
    """BM25 Algorithm Configuration"""

    k1: float = Field(
        default=1.5,
        ge=0.0, le=3.0,
        description="Term frequency saturation. Higher values increase TF impact.",
        json_schema_extra={
            "effect": "Controls term frequency influence",
            "trade_off": "High: overvalues frequent terms, Low: overvalues rare terms",
            "recommended_range": [1.2, 2.0],
            "category": "bm25"
        }
    )

    b: float = Field(
        default=0.75,
        ge=0.0, le=1.0,
        description="Document length normalization. 1.0 = full normalization.",
        json_schema_extra={
            "effect": "Controls document length penalty",
            "trade_off": "High: favors short docs, Low: favors long docs",
            "recommended_range": [0.5, 0.9],
            "category": "bm25"
        }
    )

    # Extended BM25 settings (NEW - for hardcoding removal)
    min_score_threshold: float = Field(
        default=0.01,
        ge=0.0, le=0.1,
        description="Minimum BM25 score to include in results",
        json_schema_extra={
            "effect": "Filters extremely low BM25 scores",
            "trade_off": "Higher values increase precision, lower values increase recall",
            "category": "bm25"
        }
    )

    max_feature_lines: int = Field(
        default=5,
        ge=1, le=20,
        description="Maximum feature lines to include in partial match",
        json_schema_extra={
            "effect": "Limits feature context in results",
            "category": "bm25"
        }
    )


class ConfidenceConfig(BaseModel):
    """Confidence Level Thresholds"""

    high_threshold: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="High confidence threshold (use summary directly)",
        json_schema_extra={
            "effect": "Determines when to trust summary results alone",
            "trade_off": "High: conservative (more vector fallback), Low: aggressive",
            "category": "confidence"
        }
    )

    medium_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Medium confidence threshold (combine summary + vector)",
        json_schema_extra={
            "effect": "Transition point between search strategies",
            "category": "confidence"
        }
    )

    low_threshold: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Low confidence threshold (prioritize vector search)"
    )

    # Score classification thresholds
    score_high_threshold: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Score threshold for 'high' classification"
    )

    score_medium_threshold: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Score threshold for 'medium' classification"
    )

    score_low_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Score threshold for 'low' classification"
    )

    # Agent base confidence values
    agent_base_rag: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Base confidence for RAG agent"
    )
    agent_base_ims: float = Field(
        default=0.80,
        ge=0.0, le=1.0,
        description="Base confidence for IMS agent"
    )
    agent_base_code: float = Field(
        default=0.75,
        ge=0.0, le=1.0,
        description="Base confidence for Code agent"
    )
    agent_base_vision: float = Field(
        default=0.70,
        ge=0.0, le=1.0,
        description="Base confidence for Vision agent"
    )
    agent_base_planner: float = Field(
        default=0.90,
        ge=0.0, le=1.0,
        description="Base confidence for Planner agent"
    )

    # Score component weights
    weight_execution: float = Field(
        default=0.25,
        ge=0.0, le=1.0,
        description="Weight for execution confidence component"
    )
    weight_grounding: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="Weight for grounding confidence component"
    )
    weight_consistency: float = Field(
        default=0.20,
        ge=0.0, le=1.0,
        description="Weight for consistency confidence component"
    )
    weight_completeness: float = Field(
        default=0.25,
        ge=0.0, le=1.0,
        description="Weight for completeness confidence component"
    )

    # Length score thresholds
    length_very_short: int = Field(
        default=50,
        ge=0,
        description="Length threshold for very short answers (low score)"
    )
    length_short: int = Field(
        default=100,
        ge=0,
        description="Length threshold for short answers"
    )
    length_medium: int = Field(
        default=500,
        ge=0,
        description="Length threshold for medium answers"
    )
    length_score_very_short: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Score for very short answers"
    )
    length_score_short: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Score for short answers"
    )
    length_score_medium: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Score for medium length answers"
    )
    length_score_full: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Score for full length answers"
    )

    # Contradiction penalty thresholds
    contradiction_few_threshold: int = Field(
        default=2,
        ge=0,
        description="Threshold for few contradictions"
    )
    contradiction_few_score: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Score when few contradictions detected"
    )
    contradiction_many_score: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Score when many contradictions detected"
    )

    # Extended confidence settings (NEW - for hardcoding removal)
    grounding_max_bonus: float = Field(
        default=0.1,
        ge=0.0, le=0.5,
        description="Maximum bonus for source count in grounding calculation",
        json_schema_extra={
            "effect": "Caps the benefit of having many sources",
            "category": "confidence"
        }
    )

    source_ratio_weight: float = Field(
        default=0.9,
        ge=0.0, le=1.0,
        description="Weight of source ratio in grounding confidence (rest is bonus)",
        json_schema_extra={
            "effect": "Balance between source ratio and bonus",
            "category": "confidence"
        }
    )

    completeness_execution_weight: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Weight of execution ratio in completeness calculation",
        json_schema_extra={
            "effect": "Importance of task completion vs answer length",
            "category": "confidence"
        }
    )

    completeness_length_weight: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Weight of length score in completeness calculation",
        json_schema_extra={
            "effect": "Importance of answer length vs task completion",
            "category": "confidence"
        }
    )

    default_confidence: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Default confidence when explicit calculation not available",
        json_schema_extra={
            "effect": "Fallback confidence value",
            "category": "confidence"
        }
    )

    source_present_confidence: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Confidence when sources are present",
        json_schema_extra={
            "effect": "Base confidence with sources",
            "category": "confidence"
        }
    )

    no_source_confidence: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Confidence when no sources found",
        json_schema_extra={
            "effect": "Base confidence without sources (low)",
            "category": "confidence"
        }
    )

    classify_confidence_scale: float = Field(
        default=1.5,
        ge=1.0, le=3.0,
        description="Scale factor for classification confidence",
        json_schema_extra={
            "effect": "Amplifies classification probability to confidence",
            "category": "confidence"
        }
    )

    classify_confidence_cap: float = Field(
        default=0.99,
        ge=0.5, le=1.0,
        description="Maximum cap for classification confidence",
        json_schema_extra={
            "effect": "Prevents overconfident classifications",
            "category": "confidence"
        }
    )


class EvaluationConfig(BaseModel):
    """Answer Evaluation Configuration"""

    # Base score
    base_score: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Starting score for evaluation"
    )

    # Hallucination penalties
    hallucination_penalty: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Penalty for detected hallucination",
        json_schema_extra={
            "effect": "Reduces score when hallucination detected",
            "category": "evaluation"
        }
    )

    source_mismatch_penalty: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Penalty for source mismatch"
    )

    format_error_penalty: float = Field(
        default=0.15,
        ge=0.0, le=1.0,
        description="Penalty for format errors"
    )

    reasoning_error_penalty: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="Penalty for reasoning errors"
    )

    repeated_error_penalty: float = Field(
        default=0.15,
        ge=0.0, le=1.0,
        description="Penalty per repeated error pattern"
    )

    grammar_error_penalty: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Penalty for grammar/language errors"
    )

    contradiction_penalty: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Penalty for contradictions"
    )

    # Positive adjustments
    code_ratio_weight: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Weight for code content ratio bonus"
    )

    term_ratio_weight: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Weight for technical term ratio bonus"
    )

    command_bonus: float = Field(
        default=0.1,
        ge=0.0, le=0.5,
        description="Bonus per verified command"
    )

    command_bonus_max: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Maximum total command bonus"
    )

    length_bonus: float = Field(
        default=0.05,
        ge=0.0, le=0.2,
        description="Bonus for appropriate response length"
    )

    length_penalty: float = Field(
        default=0.05,
        ge=0.0, le=0.2,
        description="Penalty for overly verbose response"
    )

    # Verification thresholds
    pass_threshold: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Threshold for verification pass",
        json_schema_extra={
            "effect": "Minimum score to pass verification",
            "category": "evaluation"
        }
    )

    retry_threshold: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Threshold for retry recommendation"
    )

    # Confidence criteria adjustment
    confidence_criteria_offset: float = Field(
        default=0.2,
        ge=0.0, le=0.5,
        description="Offset from min_confidence for criteria matching"
    )

    # Relevance matching
    relevance_match_ratio: float = Field(
        default=0.3,
        ge=0.1, le=1.0,
        description="Ratio of task words required for relevance match"
    )


class LengthScoreConfig(BaseModel):
    """Length-based Score Configuration"""

    very_short_threshold: int = Field(
        default=50,
        ge=10, le=200,
        description="Character threshold for very short responses"
    )

    very_short_score: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Score for very short responses"
    )

    short_threshold: int = Field(
        default=100,
        ge=50, le=500,
        description="Character threshold for short responses"
    )

    short_score: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Score for short responses"
    )

    medium_threshold: int = Field(
        default=500,
        ge=100, le=2000,
        description="Character threshold for medium responses"
    )

    medium_score: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Score for medium responses"
    )

    long_score: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Score for long responses"
    )


class KeywordExtractionConfig(BaseModel):
    """Keyword Extraction Configuration"""

    llm_timeout: float = Field(
        default=3.0,
        ge=1.0, le=30.0,
        description="LLM timeout for keyword extraction (seconds)"
    )

    llm_max_tokens: int = Field(
        default=200,
        ge=50, le=1000,
        description="Max tokens for LLM keyword extraction response"
    )

    cache_max_size: int = Field(
        default=1000,
        ge=100, le=10000,
        description="Maximum cache entries for keyword extraction"
    )

    cache_ttl_seconds: int = Field(
        default=3600,
        ge=300, le=86400,
        description="Cache TTL for keyword extraction (seconds)"
    )


class SearchConfig(BaseModel):
    """Search Configuration"""

    default_top_k: int = Field(
        default=5,
        ge=1, le=50,
        description="Default number of results to return"
    )

    max_top_k: int = Field(
        default=20,
        ge=5, le=100,
        description="Maximum allowed top_k value"
    )

    keyword_only_default_score: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="Default score for keyword-only results (no vector match)"
    )

    no_result_rank: int = Field(
        default=999,
        ge=100, le=9999,
        description="Rank assigned when result not found in a source"
    )

    linked_chunk_score_multiplier: float = Field(
        default=0.8,
        ge=0.1, le=1.0,
        description="Score multiplier for linked chunks (lower than primary)",
        json_schema_extra={
            "effect": "Controls how linked chunks are scored relative to primary",
            "trade_off": "Low: linked chunks demoted heavily, High: no distinction from primary",
            "category": "search"
        }
    )

    linked_chunk_default_score: float = Field(
        default=0.5,
        ge=0.1, le=1.0,
        description="Default score for linked chunks when primary score is missing"
    )

    # Session/External search minimum scores (NEW - for hardcoding removal)
    session_min_score: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum score for session document search",
        json_schema_extra={
            "effect": "Filters out low-scoring session results",
            "trade_off": "High: misses weak matches, Low: includes noise",
            "category": "search"
        }
    )

    external_min_score: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum score for external resource search",
        json_schema_extra={
            "effect": "Filters out low-scoring external results",
            "category": "search"
        }
    )

    # Global search skip threshold
    global_skip_threshold: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Average score threshold to skip global search when user sources are sufficient",
        json_schema_extra={
            "effect": "Determines when to skip global knowledge base",
            "trade_off": "High: more conservative (always global search), Low: aggressive skip",
            "category": "search"
        }
    )

    # Scoped search minimum similarity
    scoped_min_similarity: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Minimum similarity for scoped (document/section restricted) search",
        json_schema_extra={
            "effect": "Controls inclusivity of scoped search results",
            "category": "search"
        }
    )

    # Multi-product search minimum score
    multi_product_min_score: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum score for multi-product search results",
        json_schema_extra={
            "effect": "Filters multi-product results",
            "category": "search"
        }
    )


class StreamingConfig(BaseModel):
    """Streaming response configuration (NEW - for hardcoding removal)"""

    delay_seconds: float = Field(
        default=0.02,
        ge=0.0, le=0.5,
        description="Delay between streaming chunks (seconds)",
        json_schema_extra={
            "effect": "Controls streaming smoothness",
            "trade_off": "Higher: smoother but slower, Lower: faster but choppy",
            "category": "streaming"
        }
    )


class CacheConfig(BaseModel):
    """Caching configuration (NEW - for hardcoding removal)"""

    scoring_cache_ttl: int = Field(
        default=3600,
        ge=60, le=86400,
        description="TTL for scoring configuration cache (seconds)",
        json_schema_extra={
            "effect": "How long scoring config is cached",
            "category": "cache"
        }
    )


class ScoringConfig(BaseModel):
    """Master Scoring Configuration - All RAG scoring parameters"""

    rrf: RRFConfig = Field(default_factory=RRFConfig)
    boost: BoostConfig = Field(default_factory=BoostConfig)
    bm25: BM25Config = Field(default_factory=BM25Config)
    confidence: ConfidenceConfig = Field(default_factory=ConfidenceConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    length_score: LengthScoreConfig = Field(default_factory=LengthScoreConfig)
    keyword_extraction: KeywordExtractionConfig = Field(default_factory=KeywordExtractionConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)

    # NEW: Extended configs for hardcoding removal
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)

    # Global settings
    normalization: ScoreNormalization = Field(
        default=ScoreNormalization.MIN_MAX,
        description="Score normalization method"
    )

    enable_simulation_mode: bool = Field(
        default=False,
        description="Simulation mode (returns debug info, no actual response)"
    )

    class Config:
        json_schema_extra = {
            "title": "RAG Scoring Configuration",
            "description": "Complete configuration for RAG search scoring system (v2.0 - hardcoding eliminated)"
        }


# Database Models

class ScoringConfigDB(BaseModel):
    """Database representation of scoring configuration"""
    id: UUID
    name: str
    description: Optional[str] = None
    config: ScoringConfig
    is_active: bool = False
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None


class ScoringConfigHistory(BaseModel):
    """History record for configuration changes"""
    id: UUID
    config_id: UUID
    config: "ScoringConfig"  # The configuration at this version
    changed_by: Optional[UUID] = None
    changed_at: datetime
    reason: Optional[str] = None
    version: int = 1


class ParameterMetadata(BaseModel):
    """Metadata for a single parameter"""
    name: str
    description: str
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    effect: Optional[str] = None
    trade_off: Optional[str] = None
    recommended_range: Optional[List[float]] = None
    category: Optional[str] = None


# Simulation Models

class SimulationStep(BaseModel):
    """Single step in simulation"""
    name: str
    description: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    score_impact: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)


class RankedDocument(BaseModel):
    """Document in final ranking"""
    rank: int
    document_id: str
    title: str
    final_score: float
    confidence_level: str  # "high", "medium", "low"
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)


class SimulationResult(BaseModel):
    """Complete simulation result"""
    query: str
    config: "ScoringConfig"
    steps: List[SimulationStep] = Field(default_factory=list)
    final_ranking: List[RankedDocument] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    debug_info: Dict[str, Any] = Field(default_factory=dict)


class RankChange(BaseModel):
    """Rank change between configurations"""
    document_id: str
    title: str = ""
    old_rank: int
    new_rank: int
    change: int  # Positive = moved up
    direction: str = "up"  # "up" or "down"


class ComparisonResult(BaseModel):
    """Comparison between two configurations"""
    query: str
    config_a: "ScoringConfig"
    config_b: "ScoringConfig"
    result_a: SimulationResult
    result_b: SimulationResult
    rank_changes: List[Dict[str, Any]] = Field(default_factory=list)
    new_entries: List[RankedDocument] = Field(default_factory=list)
    removed_entries: List[RankedDocument] = Field(default_factory=list)
    score_deltas: Dict[str, float] = Field(default_factory=dict)


class TestCase(BaseModel):
    """Single test case for batch testing"""
    query: str
    expected_documents: List[str] = Field(default_factory=list)
    expected_top_n: int = 5
    description: Optional[str] = None


class TestCaseResult(BaseModel):
    """Result of a single test case"""
    test_case: TestCase
    passed: bool
    actual_ranking: List[RankedDocument] = Field(default_factory=list)
    found_expected: List[str] = Field(default_factory=list)
    missing_expected: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class BatchTestResult(BaseModel):
    """Result of batch testing"""
    config: "ScoringConfig"
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    results: List[TestCaseResult] = Field(default_factory=list)
    improved_cases: List[TestCaseResult] = Field(default_factory=list)
    degraded_cases: List[TestCaseResult] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Hybrid Score Configuration (v1.0 - Hardcoding Elimination)
# ═══════════════════════════════════════════════════════════════════════════════


class HybridScoreConfig(BaseModel):
    """
    Hybrid Score 계산에 필요한 모든 파라미터.

    이 설정은 hybrid_rag.py, rag_service.py, hybrid_search_service.py에서
    하드코딩되어 있던 모든 스코어링 상수를 외부 설정으로 추출합니다.

    모든 파라미터는 환경변수로 오버라이드 가능합니다.
    """

    # ═══════════════════════════════════════════════════════════════
    # Weight Distribution (가중치 분배)
    # ═══════════════════════════════════════════════════════════════

    vector_weight: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Vector search 결과 가중치 (semantic similarity)",
        json_schema_extra={
            "env_var": "HYBRID_VECTOR_WEIGHT",
            "effect": "높을수록 의미적 유사성 중시",
            "trade_off": "너무 높으면 키워드 매칭 무시",
            "source_file": "hybrid_rag.py:1092",
            "category": "weight"
        }
    )

    graph_weight: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Graph search 결과 가중치 (entity matching). 권장: 1 - vector_weight",
        json_schema_extra={
            "env_var": "HYBRID_GRAPH_WEIGHT",
            "effect": "높을수록 엔티티 관계 중시",
            "source_file": "hybrid_rag.py:1104",
            "category": "weight"
        }
    )

    bm25_weight: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="BM25 keyword search 가중치",
        json_schema_extra={
            "env_var": "HYBRID_BM25_WEIGHT",
            "effect": "키워드 정확 매칭 우선도",
            "source_file": "hybrid_search_service.py:27",
            "category": "weight"
        }
    )

    semantic_weight: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Semantic search 가중치 (BM25와 쌍)",
        json_schema_extra={
            "env_var": "HYBRID_SEMANTIC_WEIGHT",
            "effect": "의미 기반 검색 우선도",
            "source_file": "hybrid_search_service.py:28",
            "category": "weight"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Topic Density Scoring (토픽 밀도 스코어링)
    # Formula: combined_score = base + (density * weight)
    # ═══════════════════════════════════════════════════════════════

    topic_density_base: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Topic density 스코어 기본값",
        json_schema_extra={
            "env_var": "HYBRID_TOPIC_BASE",
            "formula": "combined_score = topic_density_base + (topic_density * topic_density_weight)",
            "source_file": "hybrid_rag.py:1075",
            "category": "topic"
        }
    )

    topic_density_weight: float = Field(
        default=0.2,
        ge=0.0, le=0.6,
        description="Topic density 값에 곱해지는 가중치",
        json_schema_extra={
            "env_var": "HYBRID_TOPIC_WEIGHT",
            "range_effect": "결과 범위: [base, base + weight]",
            "source_file": "hybrid_rag.py:1075",
            "category": "topic"
        }
    )

    topic_density_min_threshold: float = Field(
        default=0.15,
        ge=0.0, le=1.0,
        description="최소 topic density 임계값 (이하는 무시)",
        json_schema_extra={
            "env_var": "HYBRID_TOPIC_MIN",
            "effect": "낮은 밀도 문서 필터링",
            "source_file": "hybrid_rag.py:1640",
            "category": "topic"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Source Priority (소스별 우선순위)
    # ═══════════════════════════════════════════════════════════════

    error_code_priority: float = Field(
        default=1.0,
        ge=0.0, le=2.0,
        description="에러 코드 검색 결과 우선순위 (최고 우선)",
        json_schema_extra={
            "env_var": "HYBRID_ERROR_PRIORITY",
            "effect": "에러 코드 결과가 항상 최상위",
            "source_file": "hybrid_rag.py:1062",
            "category": "priority"
        }
    )

    verified_result_boost: float = Field(
        default=1.5,
        ge=1.0, le=3.0,
        description="검증된 결과 부스트 배수",
        json_schema_extra={
            "env_var": "HYBRID_VERIFIED_BOOST",
            "effect": "검증된 문서 스코어 증폭",
            "source_file": "hybrid_rag.py:604",
            "category": "priority"
        }
    )

    glossary_boost: float = Field(
        default=1.1,
        ge=1.0, le=2.0,
        description="용어집 결과 부스트 배수 (10% 증가)",
        json_schema_extra={
            "env_var": "HYBRID_GLOSSARY_BOOST",
            "effect": "용어집 문서 우선",
            "source_file": "hybrid_rag.py:527",
            "category": "priority"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Overlap Boost (중복 발견 시 부스트)
    # ═══════════════════════════════════════════════════════════════

    topic_boost_increment: float = Field(
        default=0.2,
        ge=0.0, le=0.5,
        description="Topic density에서도 발견된 청크 추가 부스트",
        json_schema_extra={
            "env_var": "HYBRID_TOPIC_INCREMENT",
            "effect": "여러 소스에서 발견 시 신뢰도 증가",
            "source_file": "hybrid_rag.py:1082",
            "category": "overlap"
        }
    )

    vector_boost_increment: float = Field(
        default=0.1,
        ge=0.0, le=0.5,
        description="Vector에서도 발견된 청크 추가 부스트",
        json_schema_extra={
            "env_var": "HYBRID_VECTOR_INCREMENT",
            "source_file": "hybrid_rag.py:1099",
            "category": "overlap"
        }
    )

    graph_boost_increment: float = Field(
        default=0.1,
        ge=0.0, le=0.5,
        description="Graph에서도 발견된 청크 추가 부스트",
        json_schema_extra={
            "env_var": "HYBRID_GRAPH_INCREMENT",
            "source_file": "hybrid_rag.py:1115",
            "category": "overlap"
        }
    )

    keyword_match_boost: float = Field(
        default=0.1,
        ge=0.0, le=0.5,
        description="키워드 매칭당 추가 부스트 (per keyword)",
        json_schema_extra={
            "env_var": "HYBRID_KEYWORD_BOOST",
            "formula": "score *= (1 + keyword_match_boost * match_count)",
            "source_file": "hybrid_rag.py:1137",
            "category": "overlap"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Normalization (정규화)
    # ═══════════════════════════════════════════════════════════════

    entity_match_normalization_divisor: float = Field(
        default=5.0,
        ge=1.0, le=20.0,
        description="엔티티 매칭 수 정규화 분모 (match_count / divisor)",
        json_schema_extra={
            "env_var": "HYBRID_ENTITY_NORM",
            "effect": "5개 매칭 = 1.0 스코어",
            "source_file": "hybrid_rag.py:794",
            "category": "normalization"
        }
    )

    normalization_epsilon: float = Field(
        default=1e-8,
        ge=0.0, le=1e-6,
        description="0 나누기 방지용 epsilon",
        json_schema_extra={
            "env_var": "HYBRID_NORM_EPSILON",
            "source_file": "hybrid_search_service.py:133",
            "category": "normalization"
        }
    )

    min_relevance_score: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="최소 관련성 스코어 (이하 필터링)",
        json_schema_extra={
            "env_var": "RAG_MIN_RELEVANCE_SCORE",
            "effect": "낮은 스코어 결과 제거",
            "source_file": "hybrid_rag.py:1157",
            "category": "normalization"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Search Multipliers (검색 배수)
    # ═══════════════════════════════════════════════════════════════

    deep_analysis_multiplier: int = Field(
        default=4,
        ge=1, le=10,
        description="Deep analysis 쿼리 시 결과 배수 (top_k * multiplier)",
        json_schema_extra={
            "env_var": "HYBRID_DEEP_MULT",
            "effect": "심층 분석 시 더 많은 결과 수집",
            "source_file": "hybrid_rag.py:138",
            "category": "multiplier"
        }
    )

    comprehensive_query_multiplier: int = Field(
        default=2,
        ge=1, le=5,
        description="Comprehensive 쿼리 시 결과 배수",
        json_schema_extra={
            "env_var": "HYBRID_COMP_MULT",
            "source_file": "hybrid_rag.py:140",
            "category": "multiplier"
        }
    )

    topic_search_multiplier: int = Field(
        default=3,
        ge=1, le=10,
        description="Topic density 검색 시 결과 배수",
        json_schema_extra={
            "env_var": "HYBRID_TOPIC_MULT",
            "source_file": "hybrid_rag.py:226",
            "category": "multiplier"
        }
    )

    min_entity_k: int = Field(
        default=5,
        ge=1, le=20,
        description="엔티티당 최소 k값",
        json_schema_extra={
            "env_var": "HYBRID_MIN_ENTITY_K",
            "formula": "k_per_entity = max(k, min_entity_k)",
            "source_file": "hybrid_rag.py:314",
            "category": "multiplier"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Result Limits (결과 수 제한)
    # ═══════════════════════════════════════════════════════════════

    simple_query_results: int = Field(
        default=5,
        ge=1, le=20,
        description="단순 쿼리 결과 수",
        json_schema_extra={
            "env_var": "HYBRID_SIMPLE_RESULTS",
            "source_file": "hybrid_rag.py:1170-1177",
            "category": "limit"
        }
    )

    standard_query_results: int = Field(
        default=10,
        ge=5, le=50,
        description="표준 쿼리 결과 수",
        json_schema_extra={
            "env_var": "HYBRID_STANDARD_RESULTS",
            "source_file": "hybrid_rag.py:1170-1177",
            "category": "limit"
        }
    )

    comprehensive_query_results: int = Field(
        default=20,
        ge=10, le=100,
        description="포괄적 쿼리 결과 수",
        json_schema_extra={
            "env_var": "HYBRID_COMP_RESULTS",
            "source_file": "hybrid_rag.py:1170-1177",
            "category": "limit"
        }
    )

    # ═══════════════════════════════════════════════════════════════
    # Document Source Weights (문서 소스 가중치)
    # ═══════════════════════════════════════════════════════════════

    session_document_weight: float = Field(
        default=2.0,
        ge=1.0, le=5.0,
        description="세션 문서(사용자 업로드) 가중치 배수",
        json_schema_extra={
            "env_var": "HYBRID_SESSION_WEIGHT",
            "effect": "사용자가 첨부한 문서 우선",
            "source_file": "rag_service.py:493",
            "category": "source_weight"
        }
    )

    external_document_weight: float = Field(
        default=2.5,
        ge=1.0, le=5.0,
        description="외부 연결 문서 가중치 배수",
        json_schema_extra={
            "env_var": "HYBRID_EXTERNAL_WEIGHT",
            "effect": "외부 소스 연결 문서 우선",
            "source_file": "rag_service.py:559",
            "category": "source_weight"
        }
    )

    class Config:
        json_schema_extra = {
            "title": "Hybrid Score Configuration",
            "description": "hybrid_rag.py, rag_service.py에서 추출된 모든 스코어링 파라미터 (v1.0)",
            "version": "1.0",
            "total_parameters": 24
        }
