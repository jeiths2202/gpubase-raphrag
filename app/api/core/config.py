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
from pydantic_settings import BaseSettings

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_api_settings() -> APISettings:
    """Get cached API settings"""
    return APISettings()


# Export both API settings and RAG config
api_settings = get_api_settings()
