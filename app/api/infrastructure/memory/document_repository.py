"""
In-Memory Document Repository Implementation
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import MemoryBaseRepository
from ...repositories.document_repository import (
    DocumentRepository,
    DocumentEntity,
    DocumentStatus,
    ChunkEntity
)
from ...repositories.base import EntityId


class MemoryDocumentRepository(MemoryBaseRepository[DocumentEntity], DocumentRepository):
    """In-memory document repository implementation"""

    def __init__(self):
        super().__init__()
        self._chunks: Dict[str, List[ChunkEntity]] = {}  # document_id -> chunks
        self._chunk_index: Dict[str, ChunkEntity] = {}  # chunk_id -> chunk

    # ==================== Document Operations ====================

    async def get_by_name(self, name: str, user_id: Optional[str] = None) -> Optional[DocumentEntity]:
        for doc in self._storage.values():
            if doc.name == name:
                if user_id is None or doc.user_id == user_id:
                    return doc
        return None

    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[DocumentEntity]:
        docs = [d for d in self._storage.values() if d.project_id == project_id]
        docs.sort(key=lambda x: x.updated_at, reverse=True)
        return docs[skip:skip + limit]

    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        status: Optional[DocumentStatus] = None
    ) -> List[DocumentEntity]:
        docs = [d for d in self._storage.values() if d.user_id == user_id]
        if status:
            docs = [d for d in docs if d.status == status]
        docs.sort(key=lambda x: x.updated_at, reverse=True)
        return docs[skip:skip + limit]

    async def get_by_status(
        self,
        status: DocumentStatus,
        limit: int = 100
    ) -> List[DocumentEntity]:
        docs = [d for d in self._storage.values() if d.status == status]
        docs.sort(key=lambda x: x.created_at)
        return docs[:limit]

    async def search_by_tags(
        self,
        tags: List[str],
        match_all: bool = False
    ) -> List[DocumentEntity]:
        results = []
        for doc in self._storage.values():
            if match_all:
                if all(tag in doc.tags for tag in tags):
                    results.append(doc)
            else:
                if any(tag in doc.tags for tag in tags):
                    results.append(doc)
        return results

    async def update_status(
        self,
        document_id: EntityId,
        status: DocumentStatus,
        error_message: Optional[str] = None
    ) -> bool:
        doc = await self.get_by_id(document_id)
        if not doc:
            return False

        doc.status = status
        doc.updated_at = datetime.utcnow()
        if error_message:
            doc.metadata["error_message"] = error_message
        return True

    # ==================== Chunk Operations ====================

    async def add_chunks(
        self,
        document_id: EntityId,
        chunks: List[ChunkEntity]
    ) -> List[ChunkEntity]:
        doc_id = self._normalize_id(document_id)

        if doc_id not in self._chunks:
            self._chunks[doc_id] = []

        for chunk in chunks:
            chunk.document_id = doc_id
            self._chunks[doc_id].append(chunk)
            self._chunk_index[chunk.chunk_id] = chunk

        # Update document stats
        doc = await self.get_by_id(document_id)
        if doc:
            doc.chunk_count = len(self._chunks[doc_id])
            doc.total_tokens = sum(c.token_count for c in self._chunks[doc_id])

        return chunks

    async def get_chunks(
        self,
        document_id: EntityId,
        skip: int = 0,
        limit: int = 100
    ) -> List[ChunkEntity]:
        doc_id = self._normalize_id(document_id)
        chunks = self._chunks.get(doc_id, [])
        chunks.sort(key=lambda x: x.chunk_index)
        return chunks[skip:skip + limit]

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[ChunkEntity]:
        return self._chunk_index.get(chunk_id)

    async def delete_chunks(self, document_id: EntityId) -> int:
        doc_id = self._normalize_id(document_id)
        chunks = self._chunks.pop(doc_id, [])

        for chunk in chunks:
            self._chunk_index.pop(chunk.chunk_id, None)

        return len(chunks)

    async def update_chunk_embedding(
        self,
        chunk_id: str,
        embedding: List[float]
    ) -> bool:
        chunk = self._chunk_index.get(chunk_id)
        if not chunk:
            return False
        chunk.embedding = embedding
        return True

    # ==================== Search Operations ====================

    async def search_content(
        self,
        query: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 10
    ) -> List[DocumentEntity]:
        query_lower = query.lower()
        results = []

        for doc in self._storage.values():
            if user_id and doc.user_id != user_id:
                continue
            if project_id and doc.project_id != project_id:
                continue

            # Simple text matching
            if query_lower in doc.name.lower() or query_lower in doc.content.lower():
                results.append(doc)

        return results[:limit]

    async def get_recent(
        self,
        user_id: Optional[str] = None,
        days: int = 7,
        limit: int = 10
    ) -> List[DocumentEntity]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        docs = []

        for doc in self._storage.values():
            if user_id and doc.user_id != user_id:
                continue
            if doc.updated_at >= cutoff:
                docs.append(doc)

        docs.sort(key=lambda x: x.updated_at, reverse=True)
        return docs[:limit]

    # ==================== Bulk Operations ====================

    async def bulk_create(self, entities: List[DocumentEntity]) -> List[DocumentEntity]:
        results = []
        for entity in entities:
            results.append(await self.create(entity))
        return results

    async def bulk_update(self, updates: List[Dict[str, Any]]) -> int:
        count = 0
        for update in updates:
            entity_id = update.pop("id", None)
            if entity_id and await self.update(entity_id, update):
                count += 1
        return count

    async def bulk_delete(self, entity_ids: List[EntityId]) -> int:
        count = 0
        for entity_id in entity_ids:
            if await self.delete(entity_id):
                count += 1
        return count

    # ==================== Statistics ====================

    async def get_stats(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        docs = list(self._storage.values())

        if user_id:
            docs = [d for d in docs if d.user_id == user_id]
        if project_id:
            docs = [d for d in docs if d.project_id == project_id]

        total_chunks = sum(d.chunk_count for d in docs)
        total_tokens = sum(d.total_tokens for d in docs)
        total_size = sum(d.file_size for d in docs)

        status_counts = {}
        for doc in docs:
            status = doc.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "total_tokens": total_tokens,
            "total_size_bytes": total_size,
            "status_breakdown": status_counts
        }

    async def delete(self, entity_id: EntityId) -> bool:
        """Override to also delete chunks"""
        await self.delete_chunks(entity_id)
        return await super().delete(entity_id)
