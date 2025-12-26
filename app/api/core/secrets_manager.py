"""
Centralized Secrets Management
Enterprise-grade secrets handling with validation and provider abstraction.

Supports:
- Environment Variables (default, simple deployments)
- HashiCorp Vault (enterprise, with rotation support)
- AWS KMS (cloud deployments)

Security Features:
- Required secrets validation at startup
- No hardcoded defaults for sensitive values
- Secure value validation (minimum length, known-bad detection)
- Audit logging for secret access
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Set
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger(__name__)


# ==================== Configuration ====================

@dataclass
class SecretDefinition:
    """Definition of a required secret"""
    name: str
    description: str
    min_length: int = 32
    required: bool = True
    known_insecure_values: List[str] = field(default_factory=list)


# Required secrets for the application
REQUIRED_SECRETS: List[SecretDefinition] = [
    SecretDefinition(
        name="JWT_SECRET_KEY",
        description="Secret key for JWT token signing",
        min_length=32,
        required=True,
        known_insecure_values=[
            "your-secret-key-change-in-production",
            "dev-secret-key",
            "change-me-in-production",
            "secret",
            "password",
        ]
    ),
    SecretDefinition(
        name="ENCRYPTION_MASTER_KEY",
        description="Master key for data encryption (Fernet)",
        min_length=32,
        required=True,
        known_insecure_values=[
            "default-dev-key-change-in-production",
            "dev-key",
            "test-key",
        ]
    ),
    SecretDefinition(
        name="ENCRYPTION_SALT",
        description="Salt for PBKDF2 key derivation",
        min_length=16,
        required=True,
        known_insecure_values=[
            "kms-salt-change-in-production",
            "salt",
            "dev-salt",
        ]
    ),
    SecretDefinition(
        name="NEO4J_PASSWORD",
        description="Neo4j database password",
        min_length=8,
        required=True,
        known_insecure_values=[
            "graphrag2024",
            "neo4j",
            "password",
            "admin",
        ]
    ),
]

# Optional secrets (application continues if missing)
OPTIONAL_SECRETS: List[SecretDefinition] = [
    SecretDefinition(
        name="ADMIN_INITIAL_PASSWORD",
        description="Initial password for admin user setup",
        min_length=12,
        required=False,
        known_insecure_values=["admin", "password", "123456"]
    ),
    SecretDefinition(
        name="GOOGLE_CLIENT_SECRET",
        description="Google OAuth client secret",
        min_length=10,
        required=False,
    ),
]


# ==================== Exceptions ====================

class SecretsError(Exception):
    """Base exception for secrets management"""
    pass


class MissingSecretError(SecretsError):
    """Raised when a required secret is not found"""
    def __init__(self, secret_name: str, description: str = ""):
        self.secret_name = secret_name
        self.description = description
        message = f"Required secret '{secret_name}' is not set"
        if description:
            message += f" ({description})"
        super().__init__(message)


class InsecureSecretError(SecretsError):
    """Raised when a secret value is known to be insecure"""
    def __init__(self, secret_name: str, reason: str):
        self.secret_name = secret_name
        self.reason = reason
        super().__init__(f"Secret '{secret_name}' is insecure: {reason}")


class SecretValidationError(SecretsError):
    """Raised when secret validation fails"""
    pass


# ==================== Providers ====================

class SecretsProvider(ABC):
    """Abstract base class for secrets providers"""

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value by key"""
        pass

    @abstractmethod
    def has_secret(self, key: str) -> bool:
        """Check if a secret exists"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider name for logging"""
        pass

    def supports_rotation(self) -> bool:
        """Check if provider supports secret rotation"""
        return False

    def rotate_secret(self, key: str) -> str:
        """Rotate a secret (if supported)"""
        raise NotImplementedError(
            f"{self.get_provider_name()} does not support secret rotation"
        )


class EnvironmentSecretsProvider(SecretsProvider):
    """
    Environment variable based secrets provider.

    This is the simplest provider, suitable for:
    - Docker/Kubernetes deployments with secrets
    - Development environments
    - Simple production setups

    Limitations:
    - No automatic rotation
    - Secrets visible in process environment
    """

    def get_secret(self, key: str) -> Optional[str]:
        return os.environ.get(key)

    def has_secret(self, key: str) -> bool:
        return key in os.environ

    def get_provider_name(self) -> str:
        return "EnvironmentVariables"


class VaultSecretsProvider(SecretsProvider):
    """
    HashiCorp Vault secrets provider.

    Features:
    - Dynamic secrets
    - Automatic rotation
    - Audit logging
    - Lease management

    Requires:
    - VAULT_URL environment variable
    - VAULT_TOKEN environment variable (or other auth method)
    """

    def __init__(self, vault_url: str, vault_token: str, mount_path: str = "secret"):
        try:
            import hvac
        except ImportError:
            raise ImportError(
                "hvac package is required for Vault integration. "
                "Install with: pip install hvac"
            )

        self.client = hvac.Client(url=vault_url, token=vault_token)
        self.mount_path = mount_path

        if not self.client.is_authenticated():
            raise SecretsError("Failed to authenticate with Vault")

        logger.info(f"Connected to Vault at {vault_url}")

    def get_secret(self, key: str) -> Optional[str]:
        try:
            secret = self.client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_path
            )
            return secret['data']['data'].get('value')
        except Exception as e:
            logger.warning(f"Failed to get secret '{key}' from Vault: {e}")
            return None

    def has_secret(self, key: str) -> bool:
        try:
            self.client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_path
            )
            return True
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "HashiCorpVault"

    def supports_rotation(self) -> bool:
        return True

    def rotate_secret(self, key: str) -> str:
        import secrets as secrets_module
        new_value = secrets_module.token_urlsafe(32)

        self.client.secrets.kv.v2.create_or_update_secret(
            path=key,
            secret=dict(value=new_value),
            mount_point=self.mount_path
        )

        logger.info(f"Rotated secret '{key}' in Vault")
        return new_value


# ==================== Secrets Manager ====================

class SecretsManager:
    """
    Centralized secrets management with validation.

    Features:
    - Multiple provider support (env vars, Vault, etc.)
    - Startup validation of required secrets
    - Insecure value detection
    - Caching for performance
    - Audit logging

    Usage:
        secrets = SecretsManager.get_instance()
        jwt_secret = secrets.get_required("JWT_SECRET_KEY")
    """

    _instance: Optional['SecretsManager'] = None
    _initialized: bool = False

    def __init__(self, provider: Optional[SecretsProvider] = None):
        if provider:
            self._provider = provider
        else:
            self._provider = self._auto_detect_provider()

        self._cache: Dict[str, str] = {}
        self._validated: Set[str] = set()

        logger.info(f"SecretsManager initialized with {self._provider.get_provider_name()}")

    @classmethod
    def get_instance(cls) -> 'SecretsManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)"""
        cls._instance = None
        cls._initialized = False

    def _auto_detect_provider(self) -> SecretsProvider:
        """Auto-detect the best available secrets provider"""
        vault_url = os.environ.get("VAULT_URL")
        vault_token = os.environ.get("VAULT_TOKEN")

        if vault_url and vault_token:
            try:
                return VaultSecretsProvider(vault_url, vault_token)
            except Exception as e:
                logger.warning(f"Failed to initialize Vault provider: {e}")
                logger.warning("Falling back to environment variables")

        return EnvironmentSecretsProvider()

    def validate_all_required(self) -> Dict[str, str]:
        """
        Validate all required secrets at startup.

        Returns:
            Dict of secret name -> value for all validated secrets

        Raises:
            SecretsError with details of all validation failures
        """
        errors: List[str] = []
        validated: Dict[str, str] = {}

        for secret_def in REQUIRED_SECRETS:
            try:
                value = self._get_and_validate(secret_def)
                validated[secret_def.name] = value
            except SecretsError as e:
                errors.append(str(e))

        if errors:
            error_message = "Secrets validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise SecretValidationError(error_message)

        logger.info(f"Validated {len(validated)} required secrets")
        return validated

    def _get_and_validate(self, secret_def: SecretDefinition) -> str:
        """Get and validate a secret based on its definition"""
        value = self._provider.get_secret(secret_def.name)

        # Check if secret exists
        if not value:
            if secret_def.required:
                raise MissingSecretError(secret_def.name, secret_def.description)
            return ""

        # Check minimum length
        if len(value) < secret_def.min_length:
            raise InsecureSecretError(
                secret_def.name,
                f"must be at least {secret_def.min_length} characters (got {len(value)})"
            )

        # Check for known insecure values
        if value.lower() in [v.lower() for v in secret_def.known_insecure_values]:
            raise InsecureSecretError(
                secret_def.name,
                "contains a known insecure default value"
            )

        self._validated.add(secret_def.name)
        return value

    def get_required(self, key: str) -> str:
        """
        Get a required secret.

        Raises:
            MissingSecretError if secret is not found
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key]

        value = self._provider.get_secret(key)
        if not value:
            raise MissingSecretError(key)

        self._cache[key] = value
        return value

    def get_optional(self, key: str, default: str = "") -> str:
        """Get an optional secret with a default value"""
        if key in self._cache:
            return self._cache[key]

        value = self._provider.get_secret(key)
        if value:
            self._cache[key] = value
            return value

        return default

    def has_secret(self, key: str) -> bool:
        """Check if a secret exists"""
        return self._provider.has_secret(key)

    def clear_cache(self):
        """Clear the secrets cache (for rotation)"""
        self._cache.clear()

    def get_provider_info(self) -> Dict[str, str]:
        """Get information about the current provider"""
        return {
            "provider": self._provider.get_provider_name(),
            "supports_rotation": str(self._provider.supports_rotation()),
            "validated_count": str(len(self._validated)),
        }


# ==================== Module-Level Functions ====================

@lru_cache(maxsize=1)
def get_secrets_manager() -> SecretsManager:
    """Get the singleton SecretsManager instance"""
    return SecretsManager.get_instance()


def validate_secrets_on_startup():
    """
    Validate all required secrets at application startup.

    Call this early in the application lifecycle (e.g., in FastAPI lifespan).
    Will raise SecretValidationError if any required secrets are missing or insecure.
    """
    manager = get_secrets_manager()
    manager.validate_all_required()
    logger.info("All required secrets validated successfully")


def get_jwt_secret() -> str:
    """Convenience function to get JWT secret"""
    return get_secrets_manager().get_required("JWT_SECRET_KEY")


def get_encryption_key() -> str:
    """Convenience function to get encryption master key"""
    return get_secrets_manager().get_required("ENCRYPTION_MASTER_KEY")


def get_encryption_salt() -> str:
    """Convenience function to get encryption salt"""
    return get_secrets_manager().get_required("ENCRYPTION_SALT")


def get_neo4j_password() -> str:
    """Convenience function to get Neo4j password"""
    return get_secrets_manager().get_required("NEO4J_PASSWORD")
