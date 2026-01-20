"""
Long Context Management Models (32K+ Token Support)

Provides models for:
- Context window configuration for various LLM models
- Semantic chunking and compression
- Context priority and importance scoring
- Multi-turn conversation context optimization
- Token budget management
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ============================================
# Enums
# ============================================

class ContextPriority(str, Enum):
    """Priority level for context chunks"""
    CRITICAL = "critical"      # Must include (system prompt, current query)
    HIGH = "high"              # Strongly prefer (recent messages, key context)
    MEDIUM = "medium"          # Include if space (older relevant messages)
    LOW = "low"                # Include only if plenty of space
    OPTIONAL = "optional"      # Can be dropped first


class ChunkType(str, Enum):
    """Type of context chunk"""
    SYSTEM_PROMPT = "system_prompt"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    RAG_CONTEXT = "rag_context"
    SUMMARY = "summary"
    FILE_CONTEXT = "file_context"
    TOOL_RESULT = "tool_result"
    METADATA = "metadata"


class CompressionMethod(str, Enum):
    """Method used for context compression"""
    NONE = "none"
    TRUNCATION = "truncation"
    SUMMARIZATION = "summarization"
    SEMANTIC_EXTRACTION = "semantic_extraction"
    HYBRID = "hybrid"


class LLMModelFamily(str, Enum):
    """LLM model family for context window sizing"""
    GPT4 = "gpt4"                    # 8K-128K
    GPT4_TURBO = "gpt4_turbo"        # 128K
    CLAUDE = "claude"                 # 100K-200K
    NEMOTRON = "nemotron"            # 8K-32K
    MISTRAL = "mistral"              # 8K-32K
    LLAMA = "llama"                  # 8K-128K
    GEMINI = "gemini"                # 32K-1M
    CUSTOM = "custom"


# ============================================
# Context Configuration Models
# ============================================

class LLMContextConfig(BaseModel):
    """Configuration for LLM context window"""
    model_family: LLMModelFamily = Field(default=LLMModelFamily.NEMOTRON)
    model_name: Optional[str] = Field(None, description="Specific model name")

    # Token limits
    max_context_tokens: int = Field(default=32000, ge=1000, le=2000000)
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)

    # Reserved token budgets
    reserved_for_response: int = Field(default=4096, ge=500)
    reserved_for_system: int = Field(default=1000, ge=100)
    reserved_for_rag: int = Field(default=8000, ge=500)
    reserved_for_tools: int = Field(default=2000, ge=0)

    # Context management settings
    enable_compression: bool = Field(default=True)
    compression_threshold: float = Field(default=0.75, ge=0.5, le=1.0,
        description="Start compression when usage exceeds this ratio")
    summarization_threshold: int = Field(default=16000,
        description="Trigger summarization when tokens exceed this")

    # Turn management
    max_recent_turns: int = Field(default=20, ge=1, le=100)
    min_recent_turns: int = Field(default=4, ge=1, le=20)

    @property
    def available_context_tokens(self) -> int:
        """Calculate available tokens for conversation context"""
        return (
            self.max_context_tokens
            - self.reserved_for_response
            - self.reserved_for_system
            - self.reserved_for_rag
            - self.reserved_for_tools
        )


class ContextChunk(BaseModel):
    """Individual chunk of context with metadata"""
    chunk_id: str
    chunk_type: ChunkType
    content: str
    token_count: int = Field(ge=0)
    priority: ContextPriority = ContextPriority.MEDIUM

    # Source information
    source_id: Optional[str] = None  # message_id, doc_id, etc.
    source_type: Optional[str] = None
    created_at: Optional[datetime] = None

    # Relevance scoring
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    importance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    recency_score: float = Field(default=1.0, ge=0.0, le=1.0)

    # Compression info
    is_compressed: bool = False
    original_token_count: Optional[int] = None
    compression_method: Optional[CompressionMethod] = None

    @property
    def combined_score(self) -> float:
        """Calculate combined priority score for ranking"""
        priority_weights = {
            ContextPriority.CRITICAL: 1.0,
            ContextPriority.HIGH: 0.8,
            ContextPriority.MEDIUM: 0.5,
            ContextPriority.LOW: 0.3,
            ContextPriority.OPTIONAL: 0.1
        }
        base_weight = priority_weights.get(self.priority, 0.5)
        return base_weight * (
            0.4 * self.relevance_score +
            0.3 * self.importance_score +
            0.3 * self.recency_score
        )


class ContextWindow(BaseModel):
    """Complete context window with all chunks"""
    conversation_id: UUID
    chunks: List[ContextChunk] = Field(default_factory=list)

    # Token counts
    total_tokens: int = Field(default=0, ge=0)
    max_tokens: int = Field(default=32000)

    # Summary info
    has_summary: bool = False
    summary_covers_messages: int = 0

    # Compression info
    compression_applied: bool = False
    tokens_saved_by_compression: int = 0

    # Statistics
    messages_included: int = 0
    messages_truncated: int = 0
    rag_chunks_included: int = 0

    @property
    def usage_ratio(self) -> float:
        """Token usage ratio (0.0 to 1.0)"""
        return self.total_tokens / self.max_tokens if self.max_tokens > 0 else 0.0

    @property
    def available_tokens(self) -> int:
        """Remaining token budget"""
        return max(0, self.max_tokens - self.total_tokens)


# ============================================
# Compression Models
# ============================================

class CompressionRequest(BaseModel):
    """Request to compress context"""
    chunks: List[ContextChunk]
    target_tokens: int = Field(..., gt=0)
    method: CompressionMethod = CompressionMethod.HYBRID
    preserve_priority: ContextPriority = Field(
        default=ContextPriority.HIGH,
        description="Minimum priority to preserve without compression"
    )


class CompressionResult(BaseModel):
    """Result of context compression"""
    compressed_chunks: List[ContextChunk]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    method_used: CompressionMethod
    chunks_removed: int = 0
    chunks_truncated: int = 0
    chunks_summarized: int = 0

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.compressed_tokens


class SummarizationRequest(BaseModel):
    """Request to summarize messages"""
    messages: List[Dict[str, str]] = Field(..., description="[{role, content}]")
    existing_summary: Optional[str] = None
    target_tokens: int = Field(default=500, ge=100, le=2000)
    preserve_topics: List[str] = Field(default_factory=list)


class SummarizationResult(BaseModel):
    """Result of message summarization"""
    summary: str
    original_tokens: int
    summary_tokens: int
    compression_ratio: float
    messages_summarized: int
    key_topics: List[str] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)


# ============================================
# Context Building Models
# ============================================

class ContextBuildRequest(BaseModel):
    """Request to build context window"""
    conversation_id: UUID
    current_query: str
    rag_context: Optional[List[Dict[str, Any]]] = None
    file_context: Optional[List[Dict[str, Any]]] = None
    system_prompt: Optional[str] = None
    config: Optional[LLMContextConfig] = None

    # Optimization hints
    prioritize_recent: bool = True
    include_tool_history: bool = False
    max_rag_chunks: int = Field(default=10, ge=1, le=50)


class ContextBuildResult(BaseModel):
    """Result of context building"""
    context_window: ContextWindow
    formatted_messages: List[Dict[str, str]] = Field(default_factory=list)

    # Token breakdown
    system_tokens: int = 0
    summary_tokens: int = 0
    message_tokens: int = 0
    rag_tokens: int = 0
    query_tokens: int = 0
    total_tokens: int = 0

    # Optimization info
    compression_applied: bool = False
    summarization_applied: bool = False
    messages_dropped: int = 0
    rag_chunks_dropped: int = 0

    # Warnings
    warnings: List[str] = Field(default_factory=list)


# ============================================
# Token Budget Models
# ============================================

class TokenBudget(BaseModel):
    """Token budget allocation"""
    total_budget: int
    allocated: Dict[str, int] = Field(default_factory=dict)
    reserved: Dict[str, int] = Field(default_factory=dict)

    @property
    def total_allocated(self) -> int:
        return sum(self.allocated.values())

    @property
    def total_reserved(self) -> int:
        return sum(self.reserved.values())

    @property
    def available(self) -> int:
        return self.total_budget - self.total_allocated - self.total_reserved


class TokenUsageReport(BaseModel):
    """Detailed token usage report"""
    conversation_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Budget info
    budget: TokenBudget

    # Breakdown by type
    breakdown: Dict[str, int] = Field(default_factory=dict)

    # Efficiency metrics
    compression_savings: int = 0
    summarization_savings: int = 0
    efficiency_score: float = Field(default=1.0, ge=0.0, le=1.0)

    # Recommendations
    recommendations: List[str] = Field(default_factory=list)


# ============================================
# Context Management API Models
# ============================================

class ContextWindowStatusRequest(BaseModel):
    """Request for context window status"""
    conversation_id: UUID
    include_details: bool = True


class ContextWindowStatus(BaseModel):
    """Current context window status"""
    conversation_id: UUID
    total_messages: int = 0
    total_tokens: int = 0
    max_tokens: int = 32000

    # Usage
    usage_ratio: float = 0.0
    available_tokens: int = 0

    # Summarization
    has_active_summary: bool = False
    messages_summarized: int = 0
    summary_token_count: int = 0

    # Compression
    compression_level: str = "none"  # none, light, moderate, aggressive
    estimated_savings: int = 0

    # Health
    needs_optimization: bool = False
    optimization_reason: Optional[str] = None


class OptimizeContextRequest(BaseModel):
    """Request to optimize context window"""
    conversation_id: UUID
    target_usage_ratio: float = Field(default=0.7, ge=0.3, le=0.95)
    method: CompressionMethod = CompressionMethod.HYBRID
    preserve_recent_turns: int = Field(default=6, ge=2, le=20)


class OptimizeContextResult(BaseModel):
    """Result of context optimization"""
    success: bool
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    method_used: CompressionMethod

    # Details
    messages_summarized: int = 0
    chunks_compressed: int = 0
    chunks_removed: int = 0

    # New status
    new_status: ContextWindowStatus


# ============================================
# Model Context Limits Reference
# ============================================

MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    # OpenAI
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-3.5-turbo": 16385,

    # Anthropic
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-2": 100000,

    # NVIDIA NIM
    "nemotron-nano": 32000,
    "nemotron-mini": 32000,
    "mistral-nemo": 32000,

    # Meta
    "llama-3-8b": 8192,
    "llama-3-70b": 8192,
    "llama-3.1-8b": 128000,
    "llama-3.1-70b": 128000,

    # Google
    "gemini-pro": 32000,
    "gemini-1.5-pro": 1000000,

    # Default
    "default": 8192,
}


def get_model_context_limit(model_name: str) -> int:
    """Get context limit for a model name"""
    # Direct match
    if model_name in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model_name]

    # Partial match
    model_lower = model_name.lower()
    for key, value in MODEL_CONTEXT_LIMITS.items():
        if key in model_lower:
            return value

    return MODEL_CONTEXT_LIMITS["default"]
