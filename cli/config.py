"""
Configuration for CLI Agent
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """CLI configuration"""

    # API settings
    api_url: str = "http://localhost:9000/api/v1"
    timeout: int = 36000  # 36000 seconds (10 hours)

    # Display settings
    language: str = "ko"
    use_color: bool = True

    # Session settings
    auto_refresh: bool = True

    def __post_init__(self):
        # Ensure API URL has correct format
        self.api_url = self.api_url.rstrip("/")
        if not self.api_url.endswith("/api/v1"):
            self.api_url = f"{self.api_url}/api/v1"

    def is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        # Check common development indicators
        if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
            return True
        if os.environ.get("APP_ENV") == "develop":
            return True
        return False

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables"""
        return cls(
            api_url=os.environ.get("KMS_API_URL", "http://localhost:9000"),
            language=os.environ.get("KMS_LANGUAGE", "ko"),
            use_color=os.environ.get("KMS_NO_COLOR", "").lower() not in ("1", "true"),
        )
