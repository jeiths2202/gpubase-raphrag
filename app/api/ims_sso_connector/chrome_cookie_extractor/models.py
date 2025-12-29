"""
Cookie data models for Chrome cookie extraction
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Cookie:
    """Chrome cookie data model"""
    name: str
    value: str
    domain: str
    path: str
    expires: Optional[datetime]
    is_secure: bool
    is_httponly: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'value': self.value,
            'domain': self.domain,
            'path': self.path,
            'expires': self.expires.isoformat() if self.expires else None,
            'is_secure': self.is_secure,
            'is_httponly': self.is_httponly
        }

    def to_requests_cookie(self) -> dict:
        """Convert to format compatible with requests.Session.cookies"""
        return {
            'name': self.name,
            'value': self.value,
            'domain': self.domain,
            'path': self.path,
            'secure': self.is_secure,
            'rest': {'HttpOnly': self.is_httponly},
            'expires': int(self.expires.timestamp()) if self.expires else None
        }
