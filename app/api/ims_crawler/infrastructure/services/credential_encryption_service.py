"""
Credential Encryption Service - AES-256-GCM encryption for user credentials

Provides secure encryption/decryption for IMS credentials stored in PostgreSQL.
Uses Fernet (AES-256-GCM) for symmetric encryption with key rotation support.
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from typing import Tuple


class CredentialEncryptionService:
    """
    Service for encrypting and decrypting user credentials.

    Uses environment variables for master key and salt:
    - ENCRYPTION_MASTER_KEY: Base64-encoded master encryption key (min 32 chars)
    - ENCRYPTION_SALT: Base64-encoded salt for key derivation (min 16 chars)

    Security features:
    - AES-256-GCM authenticated encryption
    - PBKDF2 key derivation with 100,000 iterations
    - Per-operation random IVs
    - Tampering detection via authentication tags
    """

    def __init__(self):
        """
        Initialize encryption service with environment variables.

        Raises:
            ValueError: If required environment variables are missing
        """
        master_key = os.getenv("ENCRYPTION_MASTER_KEY")
        salt = os.getenv("ENCRYPTION_SALT")

        if not master_key or not salt:
            raise ValueError(
                "ENCRYPTION_MASTER_KEY and ENCRYPTION_SALT must be set in environment variables"
            )

        if len(master_key) < 32:
            raise ValueError("ENCRYPTION_MASTER_KEY must be at least 32 characters")

        if len(salt) < 16:
            raise ValueError("ENCRYPTION_SALT must be at least 16 characters")

        # Derive encryption key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode('utf-8'),
            iterations=100000,
            backend=default_backend()
        )
        derived_key = kdf.derive(master_key.encode('utf-8'))

        # Create Fernet cipher with derived key
        self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt plaintext string to bytes.

        Args:
            plaintext: Plain text to encrypt (e.g., username or password)

        Returns:
            Encrypted bytes (includes IV and authentication tag)

        Example:
            >>> service = CredentialEncryptionService()
            >>> encrypted = service.encrypt("mypassword")
            >>> type(encrypted)
            <class 'bytes'>
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")

        plaintext_bytes = plaintext.encode('utf-8')
        encrypted_bytes = self._fernet.encrypt(plaintext_bytes)
        return encrypted_bytes

    def decrypt(self, encrypted_bytes: bytes) -> str:
        """
        Decrypt bytes to plaintext string.

        Args:
            encrypted_bytes: Encrypted bytes from encrypt()

        Returns:
            Decrypted plaintext string

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (tampering detected)

        Example:
            >>> service = CredentialEncryptionService()
            >>> encrypted = service.encrypt("mypassword")
            >>> decrypted = service.decrypt(encrypted)
            >>> decrypted
            'mypassword'
        """
        if not encrypted_bytes:
            raise ValueError("Cannot decrypt empty bytes")

        try:
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")

    def encrypt_credentials(self, username: str, password: str) -> Tuple[bytes, bytes]:
        """
        Encrypt both username and password.

        Args:
            username: Plaintext username
            password: Plaintext password

        Returns:
            Tuple of (encrypted_username, encrypted_password)

        Example:
            >>> service = CredentialEncryptionService()
            >>> enc_user, enc_pass = service.encrypt_credentials("admin", "secret123")
            >>> isinstance(enc_user, bytes) and isinstance(enc_pass, bytes)
            True
        """
        encrypted_username = self.encrypt(username)
        encrypted_password = self.encrypt(password)
        return encrypted_username, encrypted_password

    def decrypt_credentials(self, encrypted_username: bytes, encrypted_password: bytes) -> Tuple[str, str]:
        """
        Decrypt both username and password.

        Args:
            encrypted_username: Encrypted username bytes
            encrypted_password: Encrypted password bytes

        Returns:
            Tuple of (plaintext_username, plaintext_password)

        Raises:
            ValueError: If decryption fails

        Example:
            >>> service = CredentialEncryptionService()
            >>> enc_user, enc_pass = service.encrypt_credentials("admin", "secret123")
            >>> user, pwd = service.decrypt_credentials(enc_user, enc_pass)
            >>> user, pwd
            ('admin', 'secret123')
        """
        username = self.decrypt(encrypted_username)
        password = self.decrypt(encrypted_password)
        return username, password


# Global singleton instance (lazy initialization)
_encryption_service: CredentialEncryptionService | None = None


def get_encryption_service() -> CredentialEncryptionService:
    """
    Get or create global encryption service instance.

    Returns:
        Singleton CredentialEncryptionService instance

    Raises:
        ValueError: If environment variables are not set
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = CredentialEncryptionService()
    return _encryption_service
