"""Credentials Repository Port"""
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID
from ...domain.entities import UserCredentials

class CredentialsRepositoryPort(ABC):
    @abstractmethod
    async def save(self, credentials: UserCredentials) -> None:
        pass

    @abstractmethod
    async def find_by_user_id(self, user_id: UUID) -> Optional[UserCredentials]:
        pass

    @abstractmethod
    async def delete_by_user_id(self, user_id: UUID) -> None:
        pass
