"""
Security Service
Enterprise security features: MFA, encryption, rate limiting

SECURITY NOTE:
- Encryption keys are loaded from environment variables (no defaults)
- Application will fail to start if required secrets are not set
- For production, use AWS KMS or HashiCorp Vault via secrets_manager
"""
import os
import base64
import hashlib
import hmac
import time
import secrets
import pyotp
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


# ================== Encryption Key Validation ==================

# Known insecure values that should never be used
INSECURE_ENCRYPTION_KEYS = [
    "default-dev-key-change-in-production",
    "dev-key",
    "test-key",
    "secret",
    "password",
]

INSECURE_SALT_VALUES = [
    "kms-salt-change-in-production",
    "salt",
    "dev-salt",
    "test-salt",
]


def _validate_encryption_key(key: str, name: str) -> str:
    """Validate encryption key meets security requirements"""
    if not key:
        raise RuntimeError(
            f"{name} environment variable is required. "
            f"Set it before starting the application. "
            f"Generate a secure value with: openssl rand -base64 32"
        )
    if len(key) < 32:
        raise RuntimeError(
            f"{name} must be at least 32 characters (got {len(key)}). "
            f"Generate a secure value with: openssl rand -base64 32"
        )
    if key.lower() in [v.lower() for v in INSECURE_ENCRYPTION_KEYS]:
        raise RuntimeError(
            f"{name} contains an insecure default value. "
            f"Generate a secure value with: openssl rand -base64 32"
        )
    return key


def _validate_salt(salt: str) -> str:
    """Validate salt meets security requirements"""
    if not salt:
        raise RuntimeError(
            "ENCRYPTION_SALT environment variable is required. "
            "Set it before starting the application. "
            "Generate a secure value with: openssl rand -base64 16"
        )
    if len(salt) < 16:
        raise RuntimeError(
            f"ENCRYPTION_SALT must be at least 16 characters (got {len(salt)}). "
            "Generate a secure value with: openssl rand -base64 16"
        )
    if salt.lower() in [v.lower() for v in INSECURE_SALT_VALUES]:
        raise RuntimeError(
            "ENCRYPTION_SALT contains an insecure default value. "
            "Generate a secure value with: openssl rand -base64 16"
        )
    return salt


# ================== Token Encryption ==================

class TokenEncryption:
    """
    Secure token encryption using Fernet (AES-128-CBC).

    SECURITY REQUIREMENTS:
    - ENCRYPTION_MASTER_KEY must be set (min 32 chars)
    - ENCRYPTION_SALT must be set (min 16 chars)
    - No hardcoded defaults - will fail if not configured

    For production:
    - Use AWS KMS or HashiCorp Vault for key management
    - Rotate keys periodically
    - Enable audit logging
    """

    _instance: Optional['TokenEncryption'] = None
    _key: Optional[bytes] = None
    _initialized: bool = False

    def __init__(self):
        self._init_key()

    def _init_key(self):
        """Initialize encryption key from environment variables"""
        # Get and validate master key - NO DEFAULTS
        master_key_raw = os.environ.get("ENCRYPTION_MASTER_KEY")
        master_key = _validate_encryption_key(master_key_raw, "ENCRYPTION_MASTER_KEY")

        # Get and validate salt - NO DEFAULTS
        salt_raw = os.environ.get("ENCRYPTION_SALT")
        salt = _validate_salt(salt_raw)

        # Derive encryption key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        self._key = derived_key
        self._initialized = True

        logger.info("TokenEncryption initialized with secure key derivation")

    @classmethod
    def get_instance(cls) -> 'TokenEncryption':
        """Get singleton instance with lazy initialization"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing or key rotation)"""
        cls._instance = None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return base64 encoded ciphertext"""
        if not plaintext:
            return ""
        if not self._initialized:
            raise RuntimeError("TokenEncryption not properly initialized")

        fernet = Fernet(self._key)
        encrypted = fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64 encoded ciphertext"""
        if not ciphertext:
            return ""
        if not self._initialized:
            raise RuntimeError("TokenEncryption not properly initialized")

        try:
            fernet = Fernet(self._key)
            encrypted = base64.urlsafe_b64decode(ciphertext.encode())
            decrypted = fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            logger.warning(f"Decryption failed: {e}")
            # Don't return ciphertext on failure - this could leak encrypted data
            raise ValueError("Failed to decrypt data")


# ================== MFA / TOTP ==================

@dataclass
class MFASetup:
    """MFA setup information"""
    secret: str
    qr_code_uri: str
    backup_codes: List[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MFAVerification:
    """MFA verification result"""
    success: bool
    message: str
    remaining_attempts: int = 3


class MFAService:
    """
    Multi-Factor Authentication service using TOTP (Time-based One-Time Password).
    Compatible with Google Authenticator, Authy, etc.
    """

    # In-memory storage (use database in production)
    _user_secrets: Dict[str, str] = {}
    _backup_codes: Dict[str, List[str]] = {}
    _mfa_enabled: Dict[str, bool] = {}
    _failed_attempts: Dict[str, int] = defaultdict(int)

    ISSUER_NAME = "GPUBase KMS"
    BACKUP_CODE_COUNT = 10

    def setup_mfa(self, user_id: str, user_email: str) -> MFASetup:
        """
        Generate MFA setup for a user.
        Returns secret, QR code URI, and backup codes.
        """
        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Generate QR code URI
        totp = pyotp.TOTP(secret)
        qr_uri = totp.provisioning_uri(
            name=user_email,
            issuer_name=self.ISSUER_NAME
        )

        # Generate backup codes
        backup_codes = [
            secrets.token_hex(4).upper() for _ in range(self.BACKUP_CODE_COUNT)
        ]

        # Store (encrypt in production)
        encryption = TokenEncryption.get_instance()
        self._user_secrets[user_id] = encryption.encrypt(secret)
        self._backup_codes[user_id] = [
            hashlib.sha256(code.encode()).hexdigest()
            for code in backup_codes
        ]

        return MFASetup(
            secret=secret,
            qr_code_uri=qr_uri,
            backup_codes=backup_codes
        )

    def verify_totp(self, user_id: str, code: str) -> MFAVerification:
        """Verify TOTP code"""
        if user_id not in self._user_secrets:
            return MFAVerification(
                success=False,
                message="MFA not set up for this user"
            )

        # Check failed attempts
        if self._failed_attempts[user_id] >= 5:
            return MFAVerification(
                success=False,
                message="Too many failed attempts. Please wait or use backup code.",
                remaining_attempts=0
            )

        # Decrypt secret
        encryption = TokenEncryption.get_instance()
        secret = encryption.decrypt(self._user_secrets[user_id])

        # Verify TOTP
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):  # Allow 30 second window
            self._failed_attempts[user_id] = 0
            self._mfa_enabled[user_id] = True
            return MFAVerification(
                success=True,
                message="MFA verification successful"
            )

        self._failed_attempts[user_id] += 1
        return MFAVerification(
            success=False,
            message="Invalid code",
            remaining_attempts=5 - self._failed_attempts[user_id]
        )

    def verify_backup_code(self, user_id: str, code: str) -> MFAVerification:
        """Verify backup code (one-time use)"""
        if user_id not in self._backup_codes:
            return MFAVerification(
                success=False,
                message="No backup codes available"
            )

        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        if code_hash in self._backup_codes[user_id]:
            # Remove used backup code
            self._backup_codes[user_id].remove(code_hash)
            self._failed_attempts[user_id] = 0
            return MFAVerification(
                success=True,
                message="Backup code accepted"
            )

        return MFAVerification(
            success=False,
            message="Invalid backup code"
        )

    def is_mfa_enabled(self, user_id: str) -> bool:
        """Check if MFA is enabled for user"""
        return self._mfa_enabled.get(user_id, False)

    def disable_mfa(self, user_id: str) -> bool:
        """Disable MFA for user"""
        if user_id in self._user_secrets:
            del self._user_secrets[user_id]
        if user_id in self._backup_codes:
            del self._backup_codes[user_id]
        if user_id in self._mfa_enabled:
            del self._mfa_enabled[user_id]
        return True


# ================== Rate Limiting ==================

@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_time: int  # seconds until reset
    retry_after: Optional[int] = None


class RateLimiter:
    """
    Token bucket rate limiter with sliding window.
    Configurable per endpoint and per user.
    """

    # Storage: user_id:endpoint -> list of timestamps
    _requests: Dict[str, List[float]] = defaultdict(list)

    # Default limits (requests per minute)
    DEFAULT_LIMITS = {
        "query": 60,
        "upload": 10,
        "auth": 20,
        "default": 120
    }

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds

    def check_rate_limit(
        self,
        identifier: str,
        endpoint: str = "default",
        custom_limit: Optional[int] = None
    ) -> RateLimitResult:
        """
        Check if request is within rate limit.

        Args:
            identifier: User ID or IP address
            endpoint: Endpoint category (query, upload, auth, default)
            custom_limit: Override default limit

        Returns:
            RateLimitResult with allowed status
        """
        key = f"{identifier}:{endpoint}"
        now = time.time()
        window_start = now - self.window_seconds

        # Get limit for endpoint
        limit = custom_limit or self.DEFAULT_LIMITS.get(
            endpoint, self.DEFAULT_LIMITS["default"]
        )

        # Clean old requests
        self._requests[key] = [
            ts for ts in self._requests[key]
            if ts > window_start
        ]

        current_count = len(self._requests[key])

        if current_count >= limit:
            # Rate limited
            oldest_request = min(self._requests[key]) if self._requests[key] else now
            reset_time = int(oldest_request + self.window_seconds - now)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                retry_after=reset_time
            )

        # Allow request
        self._requests[key].append(now)
        return RateLimitResult(
            allowed=True,
            remaining=limit - current_count - 1,
            reset_time=self.window_seconds
        )

    def get_headers(self, result: RateLimitResult, limit: int) -> Dict[str, str]:
        """Generate rate limit headers for response"""
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(result.reset_time),
            **({"Retry-After": str(result.retry_after)} if result.retry_after else {})
        }


# ================== Password Security ==================

class PasswordSecurity:
    """
    Secure password handling with bcrypt-like security.
    Includes password policies and history.
    """

    # Password history (user_id -> list of hashed passwords)
    _password_history: Dict[str, List[str]] = defaultdict(list)
    HISTORY_SIZE = 5

    # Password policies
    MIN_LENGTH = 12
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    @classmethod
    def validate_password(cls, password: str) -> Tuple[bool, List[str]]:
        """
        Validate password against policies.
        Returns (is_valid, list_of_violations)
        """
        violations = []

        if len(password) < cls.MIN_LENGTH:
            violations.append(f"Password must be at least {cls.MIN_LENGTH} characters")

        if cls.REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            violations.append("Password must contain at least one uppercase letter")

        if cls.REQUIRE_LOWERCASE and not any(c.islower() for c in password):
            violations.append("Password must contain at least one lowercase letter")

        if cls.REQUIRE_DIGIT and not any(c.isdigit() for c in password):
            violations.append("Password must contain at least one digit")

        if cls.REQUIRE_SPECIAL and not any(c in cls.SPECIAL_CHARS for c in password):
            violations.append(f"Password must contain at least one special character ({cls.SPECIAL_CHARS})")

        return (len(violations) == 0, violations)

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash password using PBKDF2 with SHA256"""
        salt = secrets.token_bytes(32)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            iterations=100000
        )
        return base64.b64encode(salt + key).decode()

    @classmethod
    def verify_password(cls, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        try:
            decoded = base64.b64decode(hashed.encode())
            salt = decoded[:32]
            stored_key = decoded[32:]
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode(),
                salt,
                iterations=100000
            )
            return hmac.compare_digest(key, stored_key)
        except Exception:
            return False

    @classmethod
    def check_password_history(cls, user_id: str, password: str) -> bool:
        """Check if password was used before"""
        for old_hash in cls._password_history.get(user_id, []):
            if cls.verify_password(password, old_hash):
                return False  # Password was used before
        return True

    @classmethod
    def update_password_history(cls, user_id: str, hashed_password: str):
        """Add password to history"""
        history = cls._password_history[user_id]
        history.append(hashed_password)
        if len(history) > cls.HISTORY_SIZE:
            cls._password_history[user_id] = history[-cls.HISTORY_SIZE:]


# ================== Session Security ==================

@dataclass
class SessionInfo:
    """User session information"""
    session_id: str
    user_id: str
    ip_address: str
    user_agent: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True


class SessionManager:
    """
    Secure session management with activity tracking.
    """

    _sessions: Dict[str, SessionInfo] = {}
    _user_sessions: Dict[str, List[str]] = defaultdict(list)

    SESSION_TIMEOUT_MINUTES = 30
    MAX_SESSIONS_PER_USER = 5

    def create_session(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str
    ) -> SessionInfo:
        """Create new session for user"""
        # Check max sessions
        user_session_ids = self._user_sessions[user_id]
        if len(user_session_ids) >= self.MAX_SESSIONS_PER_USER:
            # Remove oldest session
            oldest_id = user_session_ids[0]
            self.invalidate_session(oldest_id)

        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        session = SessionInfo(
            session_id=session_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)
        )

        self._sessions[session_id] = session
        self._user_sessions[user_id].append(session_id)

        return session

    def validate_session(self, session_id: str) -> Optional[SessionInfo]:
        """Validate and refresh session"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        now = datetime.now(timezone.utc)

        if not session.is_active or now > session.expires_at:
            self.invalidate_session(session_id)
            return None

        # Refresh session
        session.last_activity = now
        session.expires_at = now + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)

        return session

    def invalidate_session(self, session_id: str):
        """Invalidate a session"""
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            if session_id in self._user_sessions.get(session.user_id, []):
                self._user_sessions[session.user_id].remove(session_id)
            del self._sessions[session_id]

    def invalidate_all_user_sessions(self, user_id: str):
        """Invalidate all sessions for a user"""
        for session_id in list(self._user_sessions.get(user_id, [])):
            self.invalidate_session(session_id)

    def get_user_sessions(self, user_id: str) -> List[SessionInfo]:
        """Get all active sessions for a user"""
        return [
            self._sessions[sid]
            for sid in self._user_sessions.get(user_id, [])
            if sid in self._sessions and self._sessions[sid].is_active
        ]


# ================== Singleton Getters ==================

_mfa_service: Optional[MFAService] = None
_rate_limiter: Optional[RateLimiter] = None
_session_manager: Optional[SessionManager] = None


def get_mfa_service() -> MFAService:
    global _mfa_service
    if _mfa_service is None:
        _mfa_service = MFAService()
    return _mfa_service


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
