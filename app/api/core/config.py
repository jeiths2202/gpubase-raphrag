"""
API Configuration for KMS System
Extends the existing config with API-specific settings
"""
import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings

# Import existing config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from config import config as rag_config


class APISettings(BaseSettings):
    """API-specific settings"""

    # Application
    APP_NAME: str = "KMS API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Debug mode")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8501"]

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="JWT secret key"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

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
