"""Pydantic models for request/response schemas"""

from .base import (
    MetaInfo,
    PaginationMeta,
    ErrorDetail,
    SuccessResponse,
    ErrorResponse,
    PaginatedResponse,
)

from .query import (
    StrategyType,
    LanguageType,
    QueryOptions,
    QueryRequest,
    QueryResponse,
    SourceInfo,
    QueryAnalysis,
    ClassifyResponse,
    ClassificationResult,
    ClassificationFeatures,
)

from .document import (
    DocumentStatus,
    EmbeddingStatus,
    DocumentListItem,
    DocumentDetail,
    DocumentUploadResponse,
    DocumentDeleteResponse,
    ChunkInfo,
    UploadStatusResponse,
)

from .history import (
    HistoryListItem,
    HistoryDetail,
    ConversationListItem,
    ConversationCreate,
)

from .stats import (
    SystemStats,
    QueryStatsDetail,
    DocumentStatsDetail,
)

from .health import (
    HealthStatus,
    HealthResponse,
)

from .auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UserInfo,
)

from .settings import (
    SystemSettings,
    SettingsUpdate,
    SettingsUpdateResponse,
)

__all__ = [
    # Base
    "MetaInfo", "PaginationMeta", "ErrorDetail",
    "SuccessResponse", "ErrorResponse", "PaginatedResponse",
    # Query
    "StrategyType", "LanguageType", "QueryOptions", "QueryRequest",
    "QueryResponse", "SourceInfo", "QueryAnalysis",
    "ClassifyResponse", "ClassificationResult", "ClassificationFeatures",
    # Document
    "DocumentStatus", "EmbeddingStatus", "DocumentListItem",
    "DocumentDetail", "DocumentUploadResponse", "DocumentDeleteResponse",
    "ChunkInfo", "UploadStatusResponse",
    # History
    "HistoryListItem", "HistoryDetail", "ConversationListItem", "ConversationCreate",
    # Stats
    "SystemStats", "QueryStatsDetail", "DocumentStatsDetail",
    # Health
    "HealthStatus", "HealthResponse",
    # Auth
    "LoginRequest", "TokenResponse", "RefreshRequest", "UserInfo",
    # Settings
    "SystemSettings", "SettingsUpdate", "SettingsUpdateResponse",
]
