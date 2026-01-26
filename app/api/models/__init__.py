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

from .content import (
    ContentType,
    ContentStatus,
    GenerateContentRequest,
    GeneratedContent,
    ContentListItem,
    GenerateContentResponse,
    ContentDetailResponse,
    SummaryContent,
    FAQContent,
    FAQItem,
    StudyGuideContent,
    BriefingContent,
    TimelineContent,
    TOCContent,
    KeyTopicsContent,
)

from .note import (
    NoteType,
    NoteSource,
    CreateNoteRequest,
    UpdateNoteRequest,
    CreateFolderRequest,
    UpdateFolderRequest,
    SaveAIResponseRequest,
    ExportNotesRequest,
    SearchNotesRequest,
    NoteFolder,
    NoteListItem,
    NoteDetail,
    NoteExportResult,
    NoteSearchResult,
    NoteStats,
)

from .project import (
    ProjectVisibility,
    ProjectRole,
    TemplateCategory,
    CreateProjectRequest,
    UpdateProjectRequest,
    ShareProjectRequest,
    CloneProjectRequest,
    CreateTemplateRequest,
    ProjectMember,
    ProjectStats,
    ProjectListItem,
    ProjectDetail,
    ProjectTemplate,
    CloneProjectResponse,
    ShareProjectResponse,
    ProjectActivityItem,
)

from .rag_evaluation import (
    RAGMetricType,
    EvaluationMethod,
    RAGEvaluationLevel,
    FaithfulnessDetail,
    ContextRelevanceDetail,
    AnswerRelevancyDetail,
    ContextPrecisionDetail,
    ContextRecallDetail,
    MetricResult,
    RAGEvaluationResult,
    SourceInput,
    RAGEvaluationRequest,
    RAGEvaluationResponse,
    RAGEvaluationStreamChunk,
    RAGEvaluationStatsRequest,
    RAGEvaluationStats,
    RAGEvaluationListItem,
)

from .user_feedback import (
    FeedbackType,
    FeedbackCategory,
    PositiveFeedbackCategory,
    FeedbackStatus,
    CitationFeedbackType,
    QuickFeedbackRequest,
    DetailedFeedbackRequest,
    CitationFeedbackRequest,
    FeedbackResponse,
    FeedbackSummary,
    FeedbackDetail,
    HITLSignal,
    HITLStats,
    ConsistencyCheckRequest,
    ConsistencyCheckResponse,
    ConsistencyStats,
    EnhancedCitation,
    CitationDisplayConfig,
    UserFeedbackStats,
)

from .analytics_dashboard import (
    TimeGranularity,
    MetricType,
    TrendDirection,
    PopularQuery,
    SearchTrend,
    UnansweredQuery,
    QueryAnalytics,
    QualityMetric,
    QualityDistribution,
    QualityTrend,
    ResponseQualityAnalytics,
    HourlyUsage,
    DailyUsage,
    UserSegment,
    UserActivity,
    UsagePatternAnalytics,
    DocumentCitation,
    ChunkEffectiveness,
    ContentGap,
    ContentEffectivenessAnalytics,
    LatencyMetric,
    ThroughputMetric,
    ErrorMetric,
    ComponentHealth,
    PerformanceTrend,
    SystemPerformanceAnalytics,
    DashboardSummary,
    AnalyticsRequest,
    AnalyticsExportRequest,
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
    # Content
    "ContentType", "ContentStatus", "GenerateContentRequest", "GeneratedContent",
    "ContentListItem", "GenerateContentResponse", "ContentDetailResponse",
    "SummaryContent", "FAQContent", "FAQItem", "StudyGuideContent",
    "BriefingContent", "TimelineContent", "TOCContent", "KeyTopicsContent",
    # Note
    "NoteType", "NoteSource", "CreateNoteRequest", "UpdateNoteRequest",
    "CreateFolderRequest", "UpdateFolderRequest", "SaveAIResponseRequest",
    "ExportNotesRequest", "SearchNotesRequest", "NoteFolder", "NoteListItem",
    "NoteDetail", "NoteExportResult", "NoteSearchResult", "NoteStats",
    # Project
    "ProjectVisibility", "ProjectRole", "TemplateCategory",
    "CreateProjectRequest", "UpdateProjectRequest", "ShareProjectRequest",
    "CloneProjectRequest", "CreateTemplateRequest", "ProjectMember",
    "ProjectStats", "ProjectListItem", "ProjectDetail", "ProjectTemplate",
    "CloneProjectResponse", "ShareProjectResponse", "ProjectActivityItem",
    # RAG Evaluation
    "RAGMetricType", "EvaluationMethod", "RAGEvaluationLevel",
    "FaithfulnessDetail", "ContextRelevanceDetail", "AnswerRelevancyDetail",
    "ContextPrecisionDetail", "ContextRecallDetail", "MetricResult",
    "RAGEvaluationResult", "SourceInput", "RAGEvaluationRequest",
    "RAGEvaluationResponse", "RAGEvaluationStreamChunk",
    "RAGEvaluationStatsRequest", "RAGEvaluationStats", "RAGEvaluationListItem",
    # User Feedback
    "FeedbackType", "FeedbackCategory", "PositiveFeedbackCategory",
    "FeedbackStatus", "CitationFeedbackType", "QuickFeedbackRequest",
    "DetailedFeedbackRequest", "CitationFeedbackRequest", "FeedbackResponse",
    "FeedbackSummary", "FeedbackDetail", "HITLSignal", "HITLStats",
    "ConsistencyCheckRequest", "ConsistencyCheckResponse", "ConsistencyStats",
    "EnhancedCitation", "CitationDisplayConfig", "UserFeedbackStats",
    # Analytics Dashboard
    "TimeGranularity", "MetricType", "TrendDirection",
    "PopularQuery", "SearchTrend", "UnansweredQuery", "QueryAnalytics",
    "QualityMetric", "QualityDistribution", "QualityTrend", "ResponseQualityAnalytics",
    "HourlyUsage", "DailyUsage", "UserSegment", "UserActivity", "UsagePatternAnalytics",
    "DocumentCitation", "ChunkEffectiveness", "ContentGap", "ContentEffectivenessAnalytics",
    "LatencyMetric", "ThroughputMetric", "ErrorMetric", "ComponentHealth",
    "PerformanceTrend", "SystemPerformanceAnalytics",
    "DashboardSummary", "AnalyticsRequest", "AnalyticsExportRequest",
]
