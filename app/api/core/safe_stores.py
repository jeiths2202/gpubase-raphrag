"""
Thread-Safe and Memory-Bounded Stores
Safe implementations of vector stores with concurrency protection.
"""
import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import logging

from .concurrency import AsyncLockManager, get_session_lock_manager, get_user_lock_manager
from .cache import CacheConfig, CacheStats
from .metrics import get_metrics_registry

logger = logging.getLogger(__name__)


@dataclass
class StoreConfig:
    """Configuration for bounded stores"""
    max_entries_per_scope: int = 10000       # Max entries per session/user
    max_total_entries: int = 100000          # Max total entries
    max_memory_mb: float = 500.0             # Max memory in MB
    entry_ttl_seconds: float = 7200.0        # Entry TTL (2 hours)
    cleanup_interval_seconds: float = 300.0  # Cleanup every 5 minutes


@dataclass
class StoreEntry:
    """Entry in the store"""
    chunk_id: str
    embedding: np.ndarray
    metadata: Dict[str, Any]
    created_at: float
    expires_at: float
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SafeInMemoryVectorStore:
    """
    Thread-safe, memory-bounded in-memory vector store.

    Features:
    - Per-scope async locking (no global lock contention)
    - Maximum entry limits per scope and total
    - Memory usage limits
    - TTL-based expiration
    - Automatic cleanup
    - Metrics collection

    Example:
        store = SafeInMemoryVectorStore("sessions", config)

        async with store.lock_scope("session_123"):
            await store.add_chunks("session_123", chunks)
            results = await store.search("session_123", query_embedding)
    """

    def __init__(
        self,
        name: str,
        config: Optional[StoreConfig] = None,
        lock_manager: Optional[AsyncLockManager] = None
    ):
        self.name = name
        self.config = config or StoreConfig()
        self._lock_manager = lock_manager or AsyncLockManager()

        # scope_id -> list of StoreEntry
        self._store: Dict[str, List[StoreEntry]] = defaultdict(list)
        self._chunk_lookup: Dict[str, Dict[str, Any]] = {}

        # Stats
        self._total_entries = 0
        self._total_memory_bytes = 0
        self._stats = {
            "searches": 0,
            "additions": 0,
            "evictions": 0,
            "expired": 0
        }

        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Metrics
        self._metrics = get_metrics_registry()

    async def add_chunks(
        self,
        scope_id: str,
        chunks: List[Dict[str, Any]],
        ttl: Optional[float] = None
    ) -> int:
        """
        Add chunks to the store for a scope.

        Args:
            scope_id: Session/user ID
            chunks: List of chunks with 'id', 'embedding', 'content', and 'metadata'
            ttl: Optional TTL override

        Returns:
            Number of chunks added
        """
        ttl = ttl if ttl is not None else self.config.entry_ttl_seconds
        now = time.time()
        added = 0

        async with self._lock_manager.acquire(f"{self.name}:{scope_id}"):
            # Check limits
            await self._ensure_capacity(scope_id, len(chunks))

            for chunk in chunks:
                embedding = chunk.get("embedding")
                if embedding is None:
                    continue

                # Convert to numpy array
                if not isinstance(embedding, np.ndarray):
                    embedding = np.array(embedding, dtype=np.float32)

                # Estimate size
                size_bytes = embedding.nbytes + 200  # Metadata estimate

                entry = StoreEntry(
                    chunk_id=chunk.get("id", f"chunk_{now}_{added}"),
                    embedding=embedding,
                    metadata={
                        "content": chunk.get("content", ""),
                        "document_id": chunk.get("document_id"),
                        "source_name": chunk.get("source_name"),
                        **chunk.get("metadata", {})
                    },
                    created_at=now,
                    expires_at=now + ttl,
                    size_bytes=size_bytes
                )

                self._store[scope_id].append(entry)
                self._chunk_lookup[entry.chunk_id] = {
                    "scope_id": scope_id,
                    "content": chunk.get("content", ""),
                    "metadata": entry.metadata
                }

                self._total_entries += 1
                self._total_memory_bytes += size_bytes
                added += 1

            self._stats["additions"] += added

            # Update metrics
            self._metrics.get("documents_active").set(
                self._total_entries,
                source=self.name
            )

        return added

    async def search(
        self,
        scope_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks.

        Args:
            scope_id: Session/user ID
            query_embedding: Query vector
            top_k: Number of results
            min_score: Minimum similarity score

        Returns:
            List of results with content, score, and metadata
        """
        async with self._lock_manager.acquire(f"{self.name}:{scope_id}"):
            entries = self._store.get(scope_id, [])
            if not entries:
                return []

            query_vector = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vector)

            if query_norm == 0:
                return []

            results = []
            expired_indices = []

            for i, entry in enumerate(entries):
                # Check expiration
                if entry.is_expired:
                    expired_indices.append(i)
                    continue

                # Cosine similarity
                embedding_norm = np.linalg.norm(entry.embedding)
                if embedding_norm == 0:
                    continue

                score = float(np.dot(query_vector, entry.embedding) / (query_norm * embedding_norm))

                if score >= min_score:
                    results.append({
                        "chunk_id": entry.chunk_id,
                        "content": entry.metadata.get("content", ""),
                        "score": score,
                        "source_name": entry.metadata.get("source_name"),
                        "document_id": entry.metadata.get("document_id"),
                        "metadata": entry.metadata
                    })

            # Remove expired (reverse order to maintain indices)
            for i in reversed(expired_indices):
                self._remove_entry(scope_id, i)

            self._stats["expired"] += len(expired_indices)
            self._stats["searches"] += 1

            # Sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

    async def clear_scope(self, scope_id: str) -> int:
        """Clear all entries for a scope"""
        async with self._lock_manager.acquire(f"{self.name}:{scope_id}"):
            entries = self._store.get(scope_id, [])
            count = len(entries)

            for entry in entries:
                self._total_entries -= 1
                self._total_memory_bytes -= entry.size_bytes
                if entry.chunk_id in self._chunk_lookup:
                    del self._chunk_lookup[entry.chunk_id]

            if scope_id in self._store:
                del self._store[scope_id]

            return count

    def _remove_entry(self, scope_id: str, index: int):
        """Remove entry at index (must be called with lock held)"""
        if scope_id in self._store and index < len(self._store[scope_id]):
            entry = self._store[scope_id].pop(index)
            self._total_entries -= 1
            self._total_memory_bytes -= entry.size_bytes

            if entry.chunk_id in self._chunk_lookup:
                del self._chunk_lookup[entry.chunk_id]

    async def _ensure_capacity(self, scope_id: str, needed: int):
        """Evict entries if necessary (must be called with lock held)"""
        # Check per-scope limit
        scope_entries = self._store.get(scope_id, [])
        while len(scope_entries) + needed > self.config.max_entries_per_scope:
            if not scope_entries:
                break
            self._remove_entry(scope_id, 0)  # Remove oldest
            scope_entries = self._store.get(scope_id, [])
            self._stats["evictions"] += 1

        # Check total limit
        while self._total_entries + needed > self.config.max_total_entries:
            # Find scope with most entries
            if not self._store:
                break
            largest_scope = max(self._store.keys(), key=lambda s: len(self._store[s]))
            if self._store[largest_scope]:
                self._remove_entry(largest_scope, 0)
                self._stats["evictions"] += 1
            else:
                break

        # Check memory limit
        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)
        entry_estimate = needed * 20000  # ~20KB per entry estimate
        while self._total_memory_bytes + entry_estimate > max_bytes:
            if not self._store:
                break
            # Remove from largest scope
            largest_scope = max(self._store.keys(), key=lambda s: len(self._store[s]))
            if self._store[largest_scope]:
                self._remove_entry(largest_scope, 0)
                self._stats["evictions"] += 1
            else:
                break

    async def cleanup_expired(self) -> int:
        """Remove all expired entries across all scopes"""
        total_removed = 0

        for scope_id in list(self._store.keys()):
            async with self._lock_manager.acquire(f"{self.name}:{scope_id}"):
                entries = self._store.get(scope_id, [])
                expired_indices = [
                    i for i, entry in enumerate(entries)
                    if entry.is_expired
                ]

                for i in reversed(expired_indices):
                    self._remove_entry(scope_id, i)
                    total_removed += 1

        self._stats["expired"] += total_removed
        return total_removed

    async def start_background_cleanup(self):
        """Start background cleanup task"""
        if self._cleanup_task is None:
            self._shutdown = False
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_background_cleanup(self):
        """Stop background cleanup task"""
        self._shutdown = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.cleanup_interval_seconds)
                removed = await self.cleanup_expired()
                if removed > 0:
                    logger.info(f"Store '{self.name}': cleaned up {removed} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Store cleanup error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics"""
        return {
            "name": self.name,
            "total_entries": self._total_entries,
            "total_scopes": len(self._store),
            "total_memory_mb": round(self._total_memory_bytes / (1024 * 1024), 2),
            "max_memory_mb": self.config.max_memory_mb,
            "searches": self._stats["searches"],
            "additions": self._stats["additions"],
            "evictions": self._stats["evictions"],
            "expired": self._stats["expired"]
        }

    def get_scope_stats(self, scope_id: str) -> Dict[str, Any]:
        """Get stats for a specific scope"""
        entries = self._store.get(scope_id, [])
        return {
            "scope_id": scope_id,
            "entry_count": len(entries),
            "memory_bytes": sum(e.size_bytes for e in entries)
        }

    @property
    def total_entries(self) -> int:
        return self._total_entries

    @property
    def scope_count(self) -> int:
        return len(self._store)


# ==================== Factory Functions ====================

_session_store: Optional[SafeInMemoryVectorStore] = None
_user_store: Optional[SafeInMemoryVectorStore] = None


def get_session_vector_store() -> SafeInMemoryVectorStore:
    """Get the global session vector store"""
    global _session_store
    if _session_store is None:
        config = StoreConfig(
            max_entries_per_scope=5000,
            max_total_entries=50000,
            max_memory_mb=250.0,
            entry_ttl_seconds=7200.0  # 2 hours
        )
        _session_store = SafeInMemoryVectorStore(
            "sessions",
            config,
            get_session_lock_manager()
        )
    return _session_store


def get_user_vector_store() -> SafeInMemoryVectorStore:
    """Get the global user vector store"""
    global _user_store
    if _user_store is None:
        config = StoreConfig(
            max_entries_per_scope=10000,
            max_total_entries=100000,
            max_memory_mb=500.0,
            entry_ttl_seconds=86400.0  # 24 hours
        )
        _user_store = SafeInMemoryVectorStore(
            "users",
            config,
            get_user_lock_manager()
        )
    return _user_store
