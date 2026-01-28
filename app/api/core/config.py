"""
API Configuration for KMS System
Extends the existing config with API-specific settings

SECURITY NOTE:
- JWT_SECRET_KEY is loaded from environment variables (no default)
- Application will fail to start if required secrets are not set
- Use secrets_manager for centralized secrets handling
"""
import os
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Import existing config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from config import config as rag_config


# Known insecure values that should never be used in production
INSECURE_SECRET_VALUES = [
    "your-secret-key-change-in-production",
    "dev-secret-key",
    "change-me-in-production",
    "secret",
    "password",
    "test",
]


class APISettings(BaseSettings):
    """API-specific settings with secure defaults"""

    # Application
    APP_NAME: str = "KMS API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Debug mode")
    APP_ENV: str = Field(default="production", description="Application environment")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # CORS - Configurable via environment
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"],
        description="Allowed CORS origins"
    )
    CORS_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed CORS methods"
    )
    CORS_HEADERS: List[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID"],
        description="Allowed CORS headers"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )

    # PostgreSQL Database
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field(..., description="PostgreSQL password (REQUIRED)")
    POSTGRES_DB: str = Field(default="kms_db", description="PostgreSQL database name")

    def get_postgres_dsn(self) -> str:
        """Get PostgreSQL connection string"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # JWT Authentication - NO DEFAULT for secret key
    JWT_SECRET_KEY: str = Field(
        ...,  # Required, no default
        description="JWT secret key (REQUIRED, min 32 characters)"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator('JWT_SECRET_KEY')
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret key for security requirements"""
        if not v:
            raise ValueError(
                "JWT_SECRET_KEY is required. "
                "Set it via environment variable or .env file."
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters (got {len(v)}). "
                "Generate a secure key with: openssl rand -base64 32"
            )
        if v.lower() in [s.lower() for s in INSECURE_SECRET_VALUES]:
            raise ValueError(
                "JWT_SECRET_KEY contains an insecure default value. "
                "Generate a secure key with: openssl rand -base64 32"
            )
        return v

    @field_validator('APP_ENV')
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate and normalize application environment"""
        normalized = v.lower()
        if normalized in ["dev", "development"]:
            return "development"
        if normalized in ["prod", "production"]:
            return "production"
        if normalized in ["test", "testing"]:
            return "testing"
        return normalized

    # LLM Settings
    LLM_MAX_TOKENS: int = Field(
        default=2048,
        description="Maximum tokens for LLM responses (default: 2048, max context is 8192)"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.7,
        description="Default temperature for LLM generation"
    )
    LLM_MAX_CONTEXT_LENGTH: int = Field(
        default=6000,
        description="Maximum context length for LLM inputs"
    )

    # Embedding Settings
    EMBEDDING_MODEL_NAME: str = Field(
        default="nvidia/nv-embedqa-mistral-7b-v2",
        description="Embedding model name"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=4096,
        description="Embedding vector dimension"
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        description="Batch size for embedding operations"
    )
    EMBEDDING_MAX_TEXT_LENGTH: int = Field(
        default=8192,
        description="Maximum text length for embedding input"
    )
    EMBEDDING_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout for embedding operations in seconds"
    )
    EMBEDDING_URL: str = Field(
        default="http://localhost:12801/v1",
        description="Embedding service URL"
    )

    # Code Agent Settings
    CODE_AGENT_MODEL: str = Field(
        default="mistral-nemo-12b",
        description="Model ID for code generation agent"
    )
    CODE_EXECUTION_TIMEOUT: int = Field(
        default=30,
        description="Timeout for code execution in seconds"
    )

    # Vector Search Settings
    VECTOR_SEARCH_TOP_K: int = Field(
        default=5,
        description="Default number of results for vector search"
    )
    VECTOR_SEARCH_MAX_K: int = Field(
        default=20,
        description="Maximum number of results for vector search"
    )

    # RAG Content Settings
    RAG_CONTENT_MAX_CHARS: int = Field(
        default=2000,
        description="Maximum characters for content truncation in RAG results"
    )
    RAG_CONTENT_PREVIEW_CHARS: int = Field(
        default=500,
        description="Characters for content preview/summary"
    )
    RAG_TOOL_RESULT_CHARS: int = Field(
        default=6000,
        description="Maximum characters for tool results in standard mode"
    )
    RAG_TOOL_RESULT_CHARS_LARGE: int = Field(
        default=15000,
        description="Maximum characters for tool results in large context mode"
    )

    # RAG Score Weights
    RAG_TOPIC_DENSITY_BOOST: float = Field(
        default=0.1,
        description="Maximum boost factor for topic density matches (0.0-1.0)"
    )
    RAG_TOPIC_ONLY_BASE_SCORE: float = Field(
        default=0.3,
        description="Base score for topic-density-only results"
    )
    RAG_TOPIC_ONLY_WEIGHT: float = Field(
        default=0.2,
        description="Weight for topic density in topic-only results"
    )

    # Source Reliability Settings
    RELIABILITY_HIGH_THRESHOLD: float = Field(
        default=0.7,
        description="Threshold for high reliability (0.7+)"
    )
    RELIABILITY_MEDIUM_THRESHOLD: float = Field(
        default=0.4,
        description="Threshold for medium reliability (0.4-0.7)"
    )

    # Document Compare Settings
    COMPARE_MAX_DOCUMENTS: int = Field(
        default=5,
        description="Maximum documents that can be compared at once"
    )
    COMPARE_SECTIONS_PER_DOC: int = Field(
        default=3,
        description="Number of relevant sections to retrieve per document"
    )
    COMPARE_SUMMARY_MAX_TOKENS: int = Field(
        default=500,
        description="Maximum tokens for comparison summary"
    )

    # Rate Limiting
    RATE_LIMIT_QUERY: int = 60  # requests per minute
    RATE_LIMIT_UPLOAD: int = 10  # requests per minute
    RATE_LIMIT_DEFAULT: int = 120  # requests per minute

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf"]
    UPLOAD_DIR: str = "./uploads"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # IMS Crawler Timeouts (in milliseconds)
    IMS_CRAWLER_DEFAULT_TIMEOUT: int = Field(
        default=30000,
        description="Default timeout for IMS crawler operations (ms)"
    )
    IMS_CRAWLER_LOGIN_TIMEOUT: int = Field(
        default=30000,
        description="Timeout for login form wait (ms)"
    )
    IMS_CRAWLER_NAVIGATION_TIMEOUT: int = Field(
        default=30000,
        description="Timeout for page navigation (ms)"
    )
    IMS_CRAWLER_SELECTOR_TIMEOUT: int = Field(
        default=30000,
        description="Timeout for element selector wait (ms)"
    )
    IMS_CRAWLER_TYPE: str = Field(
        default="requests",
        description="Crawler type: 'playwright' (browser-based) or 'requests' (lightweight HTTP)"
    )
    IMS_CRAWLER_TIMEOUT: int = Field(
        default=3600000,
        description="Overall timeout for IMS agent operations in milliseconds (default: 1 hour)"
    )

    # IMS Query Cache Settings
    IMS_QUERY_CACHE_HOURS: int = Field(
        default=24,
        description="Hours to cache IMS query results before re-crawling (0 = always re-crawl)"
    )
    IMS_QUERY_CACHE_CLEANUP_ENABLED: bool = Field(
        default=True,
        description="Enable automatic cleanup of expired crawl jobs"
    )

    # Email/SMTP Configuration
    SMTP_ENABLED: bool = Field(default=False, description="Enable SMTP email sending")
    SMTP_HOST: str = Field(default="localhost", description="SMTP server host")
    SMTP_PORT: int = Field(default=25, description="SMTP server port (25 for local relay, 587 for TLS)")
    SMTP_USE_TLS: bool = Field(default=False, description="Use TLS for SMTP connection")
    SMTP_USERNAME: Optional[str] = Field(default=None, description="SMTP username (optional)")
    SMTP_PASSWORD: Optional[str] = Field(default=None, description="SMTP password (optional)")
    SMTP_FROM_EMAIL: str = Field(default="noreply@kms.local", description="Sender email address")
    SMTP_FROM_NAME: str = Field(default="KMS System", description="Sender name")
    USE_SENDMAIL: bool = Field(default=True, description="Use Linux sendmail if available")
    SENDMAIL_PATH: str = Field(default="/usr/sbin/sendmail", description="Path to sendmail binary")

    # External Connectors - Notion OAuth
    NOTION_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Notion OAuth client ID (from Notion integration)"
    )
    NOTION_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Notion OAuth client secret (from Notion integration)"
    )

    # External Connectors - Google Drive OAuth
    GOOGLE_DRIVE_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Google Drive OAuth client ID"
    )
    GOOGLE_DRIVE_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Google Drive OAuth client secret"
    )

    # External Connectors - GitHub OAuth
    GITHUB_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="GitHub OAuth client ID"
    )
    GITHUB_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="GitHub OAuth client secret"
    )

    # External Connectors - Atlassian (Confluence) OAuth
    ATLASSIAN_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Atlassian OAuth client ID (from developer.atlassian.com)"
    )
    ATLASSIAN_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Atlassian OAuth client secret"
    )

    # External Connectors - Microsoft (OneNote) OAuth
    MICROSOFT_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Microsoft OAuth client ID (from Azure AD App Registration)"
    )
    MICROSOFT_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Microsoft OAuth client secret"
    )

    # Remote GPU Monitoring Settings
    REMOTE_GPU_HOST: Optional[str] = Field(
        default=None,
        description="Remote server hostname/IP for GPU monitoring (e.g., 192.168.8.11)"
    )
    REMOTE_GPU_SSH_PORT: int = Field(
        default=22,
        description="SSH port for remote GPU server"
    )
    REMOTE_GPU_SSH_USER: str = Field(
        default="ofuser",
        description="SSH username for remote GPU server"
    )
    REMOTE_GPU_SSH_KEY_PATH: Optional[str] = Field(
        default=None,
        description="Path to SSH private key for remote GPU server (optional, uses default if not set)"
    )
    REMOTE_GPU_SSH_PASSWORD: Optional[str] = Field(
        default=None,
        description="SSH password for remote GPU server (optional, key-based auth preferred)"
    )
    REMOTE_GPU_CACHE_TTL: int = Field(
        default=5,
        description="Cache TTL for GPU status in seconds"
    )

    # RAG Evaluation Settings
    RAG_EVALUATION_ENABLED: bool = Field(
        default=True,
        description="Enable RAG response quality evaluation"
    )

    # Query Clarification (Human-in-the-Loop)
    ENABLE_QUERY_CLARIFICATION: bool = Field(
        default=False,
        description="Enable query clarification for ambiguous queries (Human-in-the-Loop)"
    )

    # Structured Answer Settings (ChatGPT-style Output)
    ENABLE_STRUCTURED_ANSWER: bool = Field(
        default=True,
        description="Enable ChatGPT-style structured answer blocks for improved rendering"
    )
    STRUCTURED_ANSWER_MIN_CONFIDENCE: float = Field(
        default=0.01,  # RRF scores typically range 0.01-0.05
        description="Minimum confidence threshold for structured answer sources"
    )
    RAG_EVALUATION_TIMEOUT: float = Field(
        default=30.0,
        description="Timeout for evaluation operations in seconds"
    )
    RAG_EVALUATION_MIN_SOURCES: int = Field(
        default=1,
        description="Minimum sources required for evaluation"
    )
    RAG_EVALUATION_AUTO_EVALUATE: bool = Field(
        default=False,
        description="Automatically evaluate RAG responses in agent stream"
    )

    # Summary-First Search Configuration
    SUMMARY_SEARCH_ENABLED: bool = Field(
        default=True,
        description="Enable Summary-First RAG search (BM25 over summaries before vector search)"
    )
    SUMMARY_HIGH_CONFIDENCE_THRESHOLD: float = Field(
        default=0.7,
        description="Score threshold for high confidence (use summary directly)"
    )
    SUMMARY_MEDIUM_CONFIDENCE_THRESHOLD: float = Field(
        default=0.4,
        description="Score threshold for medium confidence (combine summary + vector)"
    )
    PDF_PAGE_CACHE_SIZE: int = Field(
        default=100,
        description="LRU cache size for PDF page content"
    )
    VECTOR_FALLBACK_ENABLED: bool = Field(
        default=True,
        description="Enable vector search fallback when summary confidence is low"
    )
    SUMMARY_SEARCH_TOP_K: int = Field(
        default=5,
        description="Number of summary results to fetch"
    )

    # Corporate SSO
    CORP_EMAIL_DOMAINS: str = Field(
        default="*",
        description="Comma-separated list of corporate email domains for SSO (use '*' to allow all)"
    )

    @field_validator('CORP_EMAIL_DOMAINS')
    @classmethod
    def parse_corp_domains(cls, v: str) -> str:
        """Parse and validate corporate email domains"""
        if not v or v.strip() == "":
            return "*"  # Allow all if not configured
        return v.strip()

    def get_corp_domains_list(self) -> List[str]:
        """Get corporate domains as a list"""
        if self.CORP_EMAIL_DOMAINS == "*":
            return []  # Empty list means allow all
        return [d.strip().lower() for d in self.CORP_EMAIL_DOMAINS.split(",") if d.strip()]

    def is_corp_email(self, email: str) -> bool:
        """Check if email is from a corporate domain"""
        if not email or "@" not in email:
            return False

        # Allow all if wildcard is set
        if self.CORP_EMAIL_DOMAINS == "*":
            return True

        domain = email.split("@")[1].lower()
        corp_domains = self.get_corp_domains_list()
        return domain in corp_domains

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_api_settings() -> APISettings:
    """Get cached API settings"""
    return APISettings()


# Export both API settings and RAG config
api_settings = get_api_settings()
