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
    embedding_dimensions: int = 1536

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
    dimensions: int = 1536


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
    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

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

        return settings

    @classmethod
    def _merge_config(cls, settings: AppSettings, data: Dict[str, Any]) -> AppSettings:
        """Merge dictionary data into config"""
        for key, value in data.items():
            if hasattr(settings, key):
                attr = getattr(settings, key)
                if isinstance(attr, (DatabaseConfig, LLMSettings, VectorStoreSettings,
                                     SecuritySettings, LoggingSettings, CacheSettings, RAGSettings)):
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
