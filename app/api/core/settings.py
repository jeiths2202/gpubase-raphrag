"""
Centralized Configuration Management
Type-safe configuration with validation and environment variable support.
"""
from typing import Optional, List, Dict, Any, Type, TypeVar
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os
import yaml
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Environment(str, Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Log level"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kms"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_pool_size: int = 5
    postgres_max_overflow: int = 10

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""

    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_async_url(self) -> str:
        """Get async PostgreSQL connection URL"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@dataclass
class LLMSettings:
    """LLM configuration"""
    provider: str = "openai"  # openai, anthropic, azure, local
    default_model: str = "gpt-4"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1024  # Match BGE-M3 dense output

    # API keys (from environment)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None

    # Settings
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 60
    max_retries: int = 3


@dataclass
class VectorStoreSettings:
    """Vector store configuration"""
    provider: str = "memory"  # memory, pinecone, qdrant, weaviate, milvus

    # Pinecone
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None
    pinecone_index: str = "kms-index"

    # Qdrant
    qdrant_url: Optional[str] = None
    qdrant_api_key: Optional[str] = None

    # Common settings
    collection_name: str = "documents"
    dimensions: int = 1024  # Match BGE-M3 dense output


@dataclass
class SecuritySettings:
    """Security configuration

    SECURITY NOTE:
    - jwt_secret is required and has no default value
    - Must be set via environment variable JWT_SECRET_KEY
    - Minimum 32 characters required for production security
    """
    jwt_secret: Optional[str] = None  # REQUIRED: Set via JWT_SECRET_KEY env var
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    refresh_token_expiration_days: int = 7

    # Password policy
    min_password_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = False

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # MFA
    mfa_issuer: str = "KMS"
    mfa_digits: int = 6
    mfa_interval: int = 30

    # Encryption
    encryption_key: Optional[str] = None


@dataclass
class LoggingSettings:
    """Logging configuration"""
    level: LogLevel = LogLevel.INFO
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    json_format: bool = False

    # Token logging (for debugging LLM calls)
    enable_token_logging: bool = False

    # Request logging
    log_requests: bool = True
    log_responses: bool = False
    log_request_body: bool = False

    # Performance
    slow_request_threshold_ms: int = 500

    # Tracing
    enable_tracing: bool = False
    trace_sampling_rate: float = 0.1
    otlp_endpoint: Optional[str] = None


@dataclass
class CacheSettings:
    """Cache configuration"""
    enabled: bool = True
    provider: str = "memory"  # memory, redis

    # Redis
    redis_url: Optional[str] = None

    # TTL settings
    default_ttl: int = 3600
    embedding_cache_ttl: int = 86400
    query_cache_ttl: int = 1800


@dataclass
class RAGSettings:
    """RAG configuration"""
    # Chunking (limited by embedding model's 512 token limit)
    chunk_size: int = 800
    chunk_overlap: int = 300

    # Retrieval
    default_top_k: int = 5
    hybrid_alpha: float = 0.7  # Vector vs keyword weight

    # Session documents
    session_weight: float = 1.5
    max_session_docs: int = 10

    # External resources
    external_weight: float = 1.2
    max_external_sources: int = 5


@dataclass
class VisionSettings:
    """Vision LLM configuration for image-based document processing"""

    # Primary Vision LLM
    provider: str = "openai"  # openai, anthropic, local
    model: str = "gpt-4o"
    api_key: Optional[str] = None

    # Fallback Vision LLM
    fallback_provider: str = "anthropic"
    fallback_model: str = "claude-3-5-sonnet-20241022"
    fallback_api_key: Optional[str] = None

    # Cost Control
    monthly_budget: float = 1000.0  # USD
    max_cost_per_request: float = 0.50  # USD
    enable_cost_tracking: bool = True

    # Performance
    max_images_per_request: int = 20
    max_image_dimension: int = 2048
    batch_size: int = 5
    timeout: int = 60

    # Image Preprocessing
    default_image_format: str = "PNG"
    jpeg_quality: int = 85
    pdf_dpi: int = 150

    # Routing Thresholds
    visual_complexity_threshold: float = 0.4
    image_area_ratio_threshold: float = 0.3

    # Caching
    cache_enabled: bool = True
    cache_ttl_hours: int = 168  # 7 days for document analysis

    # Feature Flags
    enable_chart_extraction: bool = True
    enable_table_extraction: bool = True
    enable_diagram_analysis: bool = True
    enable_ocr: bool = True


@dataclass
class AdaptiveEmbeddingSettings:
    """Adaptive PDF embedding configuration

    Settings for structure-preserving PDF chunking and embedding.
    """
    # Chunking boundaries
    max_chunk_size: int = 1500  # Maximum characters per chunk
    min_chunk_size: int = 100   # Minimum characters per chunk
    overlap_size: int = 100     # Overlap between adjacent chunks

    # Structure analysis
    min_section_length: int = 50  # Minimum chars for valid section

    # Table/Section preservation
    preserve_tables: bool = True
    preserve_sections: bool = True

    # Parallel embedding
    embedding_concurrency: int = 5       # Max concurrent embedding requests
    embedding_timeout: float = 30.0      # Timeout per chunk (seconds)
    embedding_retry_count: int = 3       # Retry attempts on failure
    retry_base_delay: float = 1.0        # Base delay for exponential backoff
    retry_max_delay: float = 30.0        # Max delay between retries

    # Coverage validation
    min_coverage_threshold: float = 0.95  # Minimum acceptable coverage
    warn_on_low_coverage: bool = True

    # Quality evaluation
    quality_min_similarity: float = 0.3   # Minimum similarity threshold
    quality_top_k: int = 5                # Default K for top-k metrics
    quality_excellent_threshold: float = 0.9
    quality_good_threshold: float = 0.7
    quality_fair_threshold: float = 0.5


@dataclass
class AppSettings:
    """Main application configuration"""
    # Basic settings
    app_name: str = "KMS"
    app_version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm: LLMSettings = field(default_factory=LLMSettings)
    vector_store: VectorStoreSettings = field(default_factory=VectorStoreSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    rag: RAGSettings = field(default_factory=RAGSettings)
    vision: VisionSettings = field(default_factory=VisionSettings)
    adaptive_embedding: AdaptiveEmbeddingSettings = field(default_factory=AdaptiveEmbeddingSettings)

    # Extra settings
    extra: Dict[str, Any] = field(default_factory=dict)


class SettingsLoader:
    """Configuration loader with environment variable and file support"""

    ENV_PREFIX = "KMS_"

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> AppSettings:
        """
        Load configuration from file and environment variables.

        Priority (highest to lowest):
        1. Environment variables
        2. Config file
        3. Default values
        """
        # Start with defaults
        settings = AppSettings()

        # Load from file if provided
        if config_path and config_path.exists():
            settings = cls._load_from_file(config_path, settings)

        # Override with environment variables
        settings = cls._load_from_env(settings)

        # Apply environment-specific settings
        settings = cls._apply_environment_defaults(settings)

        return settings

    @classmethod
    def _load_from_file(cls, path: Path, settings: AppSettings) -> AppSettings:
        """Load configuration from YAML file"""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data:
                return settings

            return cls._merge_config(settings, data)

        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
            return settings

    @classmethod
    def _load_from_env(cls, settings: AppSettings) -> AppSettings:
        """Load configuration from environment variables"""
        # Basic settings
        if env := os.getenv("APP_ENVIRONMENT"):
            try:
                settings.environment = Environment(env.lower())
            except ValueError:
                pass

        settings.debug = os.getenv("DEBUG", "false").lower() == "true"
        settings.host = os.getenv("HOST", settings.host)
        settings.port = int(os.getenv("PORT", settings.port))

        # Database
        settings.database.postgres_host = os.getenv("POSTGRES_HOST", settings.database.postgres_host)
        settings.database.postgres_port = int(os.getenv("POSTGRES_PORT", settings.database.postgres_port))
        settings.database.postgres_db = os.getenv("POSTGRES_DB", settings.database.postgres_db)
        settings.database.postgres_user = os.getenv("POSTGRES_USER", settings.database.postgres_user)
        settings.database.postgres_password = os.getenv("POSTGRES_PASSWORD", settings.database.postgres_password)
        settings.database.neo4j_uri = os.getenv("NEO4J_URI", settings.database.neo4j_uri)
        settings.database.neo4j_username = os.getenv("NEO4J_USERNAME", settings.database.neo4j_username)
        settings.database.neo4j_password = os.getenv("NEO4J_PASSWORD", settings.database.neo4j_password)

        # LLM
        settings.llm.provider = os.getenv("LLM_PROVIDER", settings.llm.provider)
        settings.llm.default_model = os.getenv("DEFAULT_LLM_MODEL", settings.llm.default_model)
        settings.llm.embedding_model = os.getenv("EMBEDDING_MODEL", settings.llm.embedding_model)
        settings.llm.openai_api_key = os.getenv("OPENAI_API_KEY")
        settings.llm.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        settings.llm.azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        settings.llm.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

        # Vector Store
        settings.vector_store.provider = os.getenv("VECTOR_STORE_TYPE", settings.vector_store.provider)
        settings.vector_store.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        settings.vector_store.pinecone_environment = os.getenv("PINECONE_ENVIRONMENT")
        settings.vector_store.qdrant_url = os.getenv("QDRANT_URL")
        settings.vector_store.qdrant_api_key = os.getenv("QDRANT_API_KEY")

        # Security
        settings.security.jwt_secret = os.getenv("JWT_SECRET", settings.security.jwt_secret)
        settings.security.encryption_key = os.getenv("ENCRYPTION_KEY")

        # Logging
        if log_level := os.getenv("LOG_LEVEL"):
            try:
                settings.logging.level = LogLevel(log_level.upper())
            except ValueError:
                pass
        settings.logging.enable_token_logging = os.getenv("ENABLE_TOKEN_LOGGING", "false").lower() == "true"
        settings.logging.enable_tracing = os.getenv("ENABLE_TRACING", "false").lower() == "true"
        settings.logging.otlp_endpoint = os.getenv("OTLP_ENDPOINT")

        # Cache
        settings.cache.enabled = os.getenv("ENABLE_CACHE", "true").lower() == "true"
        settings.cache.redis_url = os.getenv("REDIS_URL")

        # Vision LLM
        settings.vision.provider = os.getenv("VISION_PROVIDER", settings.vision.provider)
        settings.vision.model = os.getenv("VISION_MODEL", settings.vision.model)
        settings.vision.api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY")
        settings.vision.fallback_provider = os.getenv("VISION_FALLBACK_PROVIDER", settings.vision.fallback_provider)
        settings.vision.fallback_model = os.getenv("VISION_FALLBACK_MODEL", settings.vision.fallback_model)
        settings.vision.fallback_api_key = os.getenv("VISION_FALLBACK_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if budget := os.getenv("VISION_MONTHLY_BUDGET"):
            settings.vision.monthly_budget = float(budget)
        if max_cost := os.getenv("VISION_MAX_COST_PER_REQUEST"):
            settings.vision.max_cost_per_request = float(max_cost)
        if max_images := os.getenv("VISION_MAX_IMAGES_PER_REQUEST"):
            settings.vision.max_images_per_request = int(max_images)
        if max_dim := os.getenv("VISION_MAX_IMAGE_DIMENSION"):
            settings.vision.max_image_dimension = int(max_dim)
        settings.vision.cache_enabled = os.getenv("VISION_CACHE_ENABLED", "true").lower() == "true"
        if cache_ttl := os.getenv("VISION_CACHE_TTL_HOURS"):
            settings.vision.cache_ttl_hours = int(cache_ttl)

        # Adaptive Embedding
        if max_chunk := os.getenv("ADAPTIVE_MAX_CHUNK_SIZE"):
            settings.adaptive_embedding.max_chunk_size = int(max_chunk)
        if min_chunk := os.getenv("ADAPTIVE_MIN_CHUNK_SIZE"):
            settings.adaptive_embedding.min_chunk_size = int(min_chunk)
        if overlap := os.getenv("ADAPTIVE_OVERLAP_SIZE"):
            settings.adaptive_embedding.overlap_size = int(overlap)
        if min_section := os.getenv("ADAPTIVE_MIN_SECTION_LENGTH"):
            settings.adaptive_embedding.min_section_length = int(min_section)
        settings.adaptive_embedding.preserve_tables = os.getenv(
            "ADAPTIVE_PRESERVE_TABLES", "true"
        ).lower() == "true"
        settings.adaptive_embedding.preserve_sections = os.getenv(
            "ADAPTIVE_PRESERVE_SECTIONS", "true"
        ).lower() == "true"
        if concurrency := os.getenv("ADAPTIVE_EMBEDDING_CONCURRENCY"):
            settings.adaptive_embedding.embedding_concurrency = int(concurrency)
        if timeout := os.getenv("ADAPTIVE_EMBEDDING_TIMEOUT"):
            settings.adaptive_embedding.embedding_timeout = float(timeout)
        if retry := os.getenv("ADAPTIVE_EMBEDDING_RETRY_COUNT"):
            settings.adaptive_embedding.embedding_retry_count = int(retry)
        if coverage := os.getenv("ADAPTIVE_MIN_COVERAGE_THRESHOLD"):
            settings.adaptive_embedding.min_coverage_threshold = float(coverage)

        return settings

    @classmethod
    def _merge_config(cls, settings: AppSettings, data: Dict[str, Any]) -> AppSettings:
        """Merge dictionary data into config"""
        for key, value in data.items():
            if hasattr(settings, key):
                attr = getattr(settings, key)
                if isinstance(attr, (DatabaseConfig, LLMSettings, VectorStoreSettings,
                                     SecuritySettings, LoggingSettings, CacheSettings,
                                     RAGSettings, VisionSettings, AdaptiveEmbeddingSettings)):
                    # Nested config
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if hasattr(attr, sub_key):
                                setattr(attr, sub_key, sub_value)
                else:
                    setattr(settings, key, value)

        return settings

    @classmethod
    def _apply_environment_defaults(cls, settings: AppSettings) -> AppSettings:
        """Apply environment-specific defaults"""
        if settings.environment == Environment.DEVELOPMENT:
            settings.debug = True
            settings.logging.level = LogLevel.DEBUG
            settings.logging.enable_token_logging = True

        elif settings.environment == Environment.PRODUCTION:
            settings.debug = False
            settings.logging.level = LogLevel.INFO
            settings.logging.json_format = True
            settings.logging.enable_token_logging = False

        # SECURITY: Validate jwt_secret is set (required in all environments)
        if not settings.security.jwt_secret:
            raise ValueError(
                "JWT_SECRET_KEY environment variable is required. "
                "Generate a secure key with: openssl rand -base64 32"
            )

        return settings


# Global settings instance
_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """Get global settings instance"""
    global _settings
    if _settings is None:
        _settings = SettingsLoader.load()
    return _settings


def reset_settings() -> None:
    """Reset settings (for testing)"""
    global _settings
    _settings = None
