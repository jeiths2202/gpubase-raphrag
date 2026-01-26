"""
Base Repository Interface
Generic repository pattern for data access abstraction.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypeVar, Generic, Optional, List, Dict, Any
from uuid import UUID


# Type aliases
EntityId = str | UUID


@dataclass
class Entity:
    """Base entity with common fields"""
    id: EntityId
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, UUID):
                result[key] = str(value)
            elif hasattr(value, 'to_dict'):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result


T = TypeVar('T', bound=Entity)


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository defining standard CRUD operations.

    All repository implementations must inherit from this class
    and implement the abstract methods.
    """

    @abstractmethod
    async def create(self, entity: T) -> T:
        """
        Create a new entity.

        Args:
            entity: Entity to create

        Returns:
            Created entity with generated ID
        """
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: EntityId) -> Optional[T]:
        """
        Get entity by ID.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """
        Get all entities with optional pagination and filtering.

        Args:
            skip: Number of entities to skip
            limit: Maximum number of entities to return
            filters: Optional filter criteria

        Returns:
            List of entities
        """
        pass

    @abstractmethod
    async def update(self, entity_id: EntityId, data: Dict[str, Any]) -> Optional[T]:
        """
        Update an existing entity.

        Args:
            entity_id: Entity identifier
            data: Fields to update

        Returns:
            Updated entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, entity_id: EntityId) -> bool:
        """
        Delete an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, entity_id: EntityId) -> bool:
        """
        Check if entity exists.

        Args:
            entity_id: Entity identifier

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities matching filters.

        Args:
            filters: Optional filter criteria

        Returns:
            Number of matching entities
        """
        pass


class TransactionalRepository(BaseRepository[T], ABC):
    """Repository with transaction support"""

    @abstractmethod
    async def begin_transaction(self) -> Any:
        """Begin a new transaction"""
        pass

    @abstractmethod
    async def commit(self) -> None:
        """Commit current transaction"""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback current transaction"""
        pass


class BulkOperationsMixin(ABC, Generic[T]):
    """Mixin for bulk operations support"""

    @abstractmethod
    async def bulk_create(self, entities: List[T]) -> List[T]:
        """Create multiple entities"""
        pass

    @abstractmethod
    async def bulk_update(self, updates: List[Dict[str, Any]]) -> int:
        """Update multiple entities, returns count of updated"""
        pass

    @abstractmethod
    async def bulk_delete(self, entity_ids: List[EntityId]) -> int:
        """Delete multiple entities, returns count of deleted"""
        pass
