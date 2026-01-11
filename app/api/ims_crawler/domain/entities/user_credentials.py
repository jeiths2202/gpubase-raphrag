"""
User Credentials Entity - Encrypted IMS credentials per user
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4


@dataclass
class UserCredentials:
    """
    User Credentials entity for storing encrypted IMS authentication data.

    Each user stores their own IMS credentials encrypted with AES-256-GCM.
    Never stores plaintext passwords.
    """

    # Identity
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)  # HybridRAG user ID

    # IMS System
    ims_base_url: str = "https://ims.tmaxsoft.com"

    # Encrypted Credentials
    encrypted_username: bytes = b""  # AES-256-GCM encrypted
    encrypted_password: bytes = b""  # AES-256-GCM encrypted

    # Validation
    is_validated: bool = False
    last_validated_at: Optional[datetime] = None
    validation_error: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate entity invariants"""
        if not self.ims_base_url:
            raise ValueError("IMS base URL is required")

    def mark_as_validated(self) -> None:
        """Mark credentials as successfully validated"""
        self.is_validated = True
        self.last_validated_at = datetime.now(timezone.utc)
        self.validation_error = None
        self.updated_at = datetime.now(timezone.utc)

    def mark_as_invalid(self, error: str) -> None:
        """Mark credentials as invalid"""
        self.is_validated = False
        self.validation_error = error
        self.updated_at = datetime.now(timezone.utc)

    def update_credentials(self, encrypted_username: bytes, encrypted_password: bytes) -> None:
        """Update encrypted credentials"""
        self.encrypted_username = encrypted_username
        self.encrypted_password = encrypted_password
        self.is_validated = False  # Require re-validation
        self.updated_at = datetime.now(timezone.utc)

    def requires_validation(self) -> bool:
        """Check if credentials need validation"""
        return not self.is_validated or self.validation_error is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for persistence"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "ims_base_url": self.ims_base_url,
            "encrypted_username": self.encrypted_username.hex() if self.encrypted_username else "",
            "encrypted_password": self.encrypted_password.hex() if self.encrypted_password else "",
            "is_validated": self.is_validated,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "validation_error": self.validation_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserCredentials":
        """Create entity from dictionary"""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            user_id=UUID(data["user_id"]) if isinstance(data.get("user_id"), str) else data.get("user_id", uuid4()),
            ims_base_url=data.get("ims_base_url", "https://ims.tmaxsoft.com"),
            encrypted_username=bytes.fromhex(data["encrypted_username"]) if data.get("encrypted_username") else b"",
            encrypted_password=bytes.fromhex(data["encrypted_password"]) if data.get("encrypted_password") else b"",
            is_validated=data.get("is_validated", False),
            last_validated_at=datetime.fromisoformat(data["last_validated_at"]) if data.get("last_validated_at") else None,
            validation_error=data.get("validation_error"),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now(timezone.utc)),
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.now(timezone.utc)),
        )
