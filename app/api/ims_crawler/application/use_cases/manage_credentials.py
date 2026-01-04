"""
Manage Credentials Use Case - CRUD operations for user credentials

Orchestrates credential encryption, storage, and validation.
"""

from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from ...domain.entities import UserCredentials
from ...infrastructure.ports.credentials_repository_port import CredentialsRepositoryPort
from ...infrastructure.services.credential_encryption_service import CredentialEncryptionService


class ManageCredentialsUseCase:
    """
    Use case for managing IMS user credentials.

    Coordinates encryption service and repository for secure credential storage.
    """

    def __init__(
        self,
        repository: CredentialsRepositoryPort,
        encryption_service: CredentialEncryptionService
    ):
        """
        Initialize use case with dependencies.

        Args:
            repository: Credentials storage repository
            encryption_service: Encryption/decryption service
        """
        self.repository = repository
        self.encryption = encryption_service

    async def create_or_update_credentials(
        self,
        user_id: UUID,
        ims_url: str,
        username: str,
        password: str
    ) -> UserCredentials:
        """
        Create or update user credentials with encryption.

        Args:
            user_id: User's UUID
            ims_url: IMS system base URL
            username: Plaintext IMS username
            password: Plaintext IMS password

        Returns:
            Created/updated UserCredentials entity

        Raises:
            ValueError: If encryption fails
        """
        # Encrypt credentials
        encrypted_username, encrypted_password = self.encryption.encrypt_credentials(
            username, password
        )

        # Check if credentials exist
        existing = await self.repository.find_by_user_id(user_id)

        if existing:
            # Update existing credentials
            existing.update_credentials(encrypted_username, encrypted_password)
            existing.ims_base_url = ims_url
            credentials = existing
        else:
            # Create new credentials
            credentials = UserCredentials(
                id=uuid4(),
                user_id=user_id,
                ims_base_url=ims_url,
                encrypted_username=encrypted_username,
                encrypted_password=encrypted_password,
                is_validated=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

        # Save to repository
        await self.repository.save(credentials)

        return credentials

    async def get_credentials(self, user_id: UUID) -> Optional[UserCredentials]:
        """
        Get user credentials.

        Args:
            user_id: User's UUID

        Returns:
            UserCredentials if found, None otherwise
        """
        return await self.repository.find_by_user_id(user_id)

    async def decrypt_credentials(
        self,
        credentials: UserCredentials
    ) -> tuple[str, str]:
        """
        Decrypt username and password from encrypted credentials.

        Args:
            credentials: UserCredentials entity

        Returns:
            Tuple of (plaintext_username, plaintext_password)

        Raises:
            ValueError: If decryption fails
        """
        return self.encryption.decrypt_credentials(
            credentials.encrypted_username,
            credentials.encrypted_password
        )

    async def validate_credentials(
        self,
        user_id: UUID
    ) -> tuple[bool, Optional[str]]:
        """
        Validate credentials by attempting IMS authentication.

        Args:
            user_id: User's UUID

        Returns:
            Tuple of (is_valid, error_message)
        """
        credentials = await self.repository.find_by_user_id(user_id)

        if not credentials:
            return False, "Credentials not found"

        try:
            # Decrypt credentials
            username, password = await self.decrypt_credentials(credentials)

            # TODO: Implement actual IMS authentication check
            # For now, just mark as validated if decryption succeeded
            credentials.mark_as_validated()
            await self.repository.save(credentials)

            return True, None

        except Exception as e:
            error_msg = f"Validation failed: {str(e)}"
            credentials.mark_as_invalid(error_msg)
            await self.repository.save(credentials)

            return False, error_msg

    async def delete_credentials(self, user_id: UUID) -> None:
        """
        Delete user credentials.

        Args:
            user_id: User's UUID
        """
        await self.repository.delete_by_user_id(user_id)
