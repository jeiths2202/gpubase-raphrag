"""
Base In-Memory Repository Implementation
"""
from datetime import datetime, timezone
from typing import TypeVar, Generic, Optional, List, Dict, Any
import asyncio

from ...repositories.base import BaseRepository, Entity, EntityId


T = TypeVar('T', bound=Entity)


class MemoryBaseRepository(BaseRepository[T], Generic[T]):
    """
    Base in-memory repository implementation.
    Thread-safe using asyncio locks.
    """

    def __init__(self):
        self._storage: Dict[str, T] = {}
        self._lock = asyncio.Lock()
        self._id_counter = 0

    def _generate_id(self) -> str:
        """Generate a unique ID"""
        self._id_counter += 1
        return f"mem_{self._id_counter:08d}"

    def _normalize_id(self, entity_id: EntityId) -> str:
        """Normalize entity ID to string"""
        return str(entity_id)

    def _matches_filters(self, entity: T, filters: Dict[str, Any]) -> bool:
        """Check if entity matches all filters"""
        for key, value in filters.items():
            entity_value = getattr(entity, key, None)
            if entity_value != value:
                return False
        return True

    async def create(self, entity: T) -> T:
        """Create a new entity"""
        async with self._lock:
            if not entity.id:
                entity.id = self._generate_id()

            entity_id = self._normalize_id(entity.id)
            entity.created_at = datetime.now(timezone.utc)
            entity.updated_at = datetime.now(timezone.utc)
            self._storage[entity_id] = entity
            return entity

    async def get_by_id(self, entity_id: EntityId) -> Optional[T]:
        """Get entity by ID"""
        return self._storage.get(self._normalize_id(entity_id))

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """Get all entities with pagination and filtering"""
        entities = list(self._storage.values())

        if filters:
            entities = [e for e in entities if self._matches_filters(e, filters)]

        # Sort by created_at descending
        entities.sort(key=lambda x: x.created_at, reverse=True)

        return entities[skip:skip + limit]

    async def update(self, entity_id: EntityId, data: Dict[str, Any]) -> Optional[T]:
        """Update an existing entity"""
        async with self._lock:
            entity_id = self._normalize_id(entity_id)
            entity = self._storage.get(entity_id)

            if not entity:
                return None

            for key, value in data.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)

            entity.updated_at = datetime.now(timezone.utc)
            return entity

    async def delete(self, entity_id: EntityId) -> bool:
        """Delete an entity"""
        async with self._lock:
            entity_id = self._normalize_id(entity_id)
            if entity_id in self._storage:
                del self._storage[entity_id]
                return True
            return False

    async def exists(self, entity_id: EntityId) -> bool:
        """Check if entity exists"""
        return self._normalize_id(entity_id) in self._storage

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count entities"""
        if not filters:
            return len(self._storage)

        return len([e for e in self._storage.values() if self._matches_filters(e, filters)])

    async def clear(self) -> None:
        """Clear all data (for testing)"""
        async with self._lock:
            self._storage.clear()
            self._id_counter = 0
