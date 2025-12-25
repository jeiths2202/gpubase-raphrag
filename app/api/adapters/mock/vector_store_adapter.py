"""
Mock Vector Store Adapter
Mock implementation for testing and development.
"""
from typing import Optional, List, Dict, Any
import asyncio
import math

from ...ports.vector_store_port import (
    VectorStorePort,
    VectorStoreConfig,
    VectorDocument,
    SearchResult,
    SearchFilter,
    DistanceMetric
)


class MockVectorStoreAdapter(VectorStorePort):
    """
    Mock vector store adapter for testing and development.

    Uses in-memory storage with actual similarity computation.
    """

    def __init__(
        self,
        simulate_delay: bool = True,
        delay_ms: int = 10
    ):
        self.simulate_delay = simulate_delay
        self.delay_ms = delay_ms
        self._collections: Dict[str, Dict[str, VectorDocument]] = {}
        self._collection_configs: Dict[str, VectorStoreConfig] = {}

    def _compute_similarity(
        self,
        vec1: List[float],
        vec2: List[float],
        metric: DistanceMetric = DistanceMetric.COSINE
    ) -> float:
        """Compute similarity between two vectors"""
        if metric == DistanceMetric.COSINE:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

        elif metric == DistanceMetric.EUCLIDEAN:
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))
            return 1 / (1 + distance)

        elif metric == DistanceMetric.DOT_PRODUCT:
            return sum(a * b for a, b in zip(vec1, vec2))

        return 0.0

    def _apply_filters(
        self,
        doc: VectorDocument,
        filters: Optional[List[SearchFilter]]
    ) -> bool:
        """Check if document matches all filters"""
        if not filters:
            return True

        for f in filters:
            value = doc.metadata.get(f.field)

            if f.operator == "eq" and value != f.value:
                return False
            elif f.operator == "ne" and value == f.value:
                return False
            elif f.operator == "gt" and not (value is not None and value > f.value):
                return False
            elif f.operator == "gte" and not (value is not None and value >= f.value):
                return False
            elif f.operator == "lt" and not (value is not None and value < f.value):
                return False
            elif f.operator == "lte" and not (value is not None and value <= f.value):
                return False
            elif f.operator == "in" and value not in f.value:
                return False
            elif f.operator == "contains" and f.value not in str(value):
                return False

        return True

    async def create_collection(
        self,
        name: str,
        dimensions: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        config: Optional[VectorStoreConfig] = None
    ) -> bool:
        """Create a new collection"""
        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        if name in self._collections:
            return False

        self._collections[name] = {}
        self._collection_configs[name] = config or VectorStoreConfig(
            collection_name=name,
            dimensions=dimensions,
            distance_metric=distance_metric
        )
        return True

    async def delete_collection(self, name: str) -> bool:
        """Delete a collection"""
        if name not in self._collections:
            return False

        del self._collections[name]
        self._collection_configs.pop(name, None)
        return True

    async def list_collections(self) -> List[str]:
        """List all collections"""
        return list(self._collections.keys())

    async def collection_exists(self, name: str) -> bool:
        """Check if collection exists"""
        return name in self._collections

    async def insert(
        self,
        collection: str,
        documents: List[VectorDocument]
    ) -> List[str]:
        """Insert documents"""
        if collection not in self._collections:
            raise ValueError(f"Collection {collection} does not exist")

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000 * len(documents) / 10)

        ids = []
        for doc in documents:
            self._collections[collection][doc.id] = doc
            ids.append(doc.id)

        return ids

    async def upsert(
        self,
        collection: str,
        documents: List[VectorDocument]
    ) -> List[str]:
        """Upsert documents"""
        if collection not in self._collections:
            await self.create_collection(collection, len(documents[0].embedding) if documents else 1536)

        return await self.insert(collection, documents)

    async def delete(
        self,
        collection: str,
        ids: List[str]
    ) -> int:
        """Delete documents by ID"""
        if collection not in self._collections:
            return 0

        count = 0
        for doc_id in ids:
            if doc_id in self._collections[collection]:
                del self._collections[collection][doc_id]
                count += 1

        return count

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[List[SearchFilter]] = None,
        include_metadata: bool = True
    ) -> List[SearchResult]:
        """Search for similar vectors"""
        if collection not in self._collections:
            return []

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        config = self._collection_configs.get(collection)
        metric = config.distance_metric if config else DistanceMetric.COSINE

        results = []
        for doc in self._collections[collection].values():
            if not self._apply_filters(doc, filters):
                continue

            score = self._compute_similarity(query_vector, doc.embedding, metric)

            results.append(SearchResult(
                id=doc.id,
                score=score,
                content=doc.content if include_metadata else "",
                metadata=doc.metadata if include_metadata else {},
                document_id=doc.metadata.get("document_id"),
                chunk_index=doc.metadata.get("chunk_index")
            ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top_k]

    async def search_by_id(
        self,
        collection: str,
        document_id: str,
        top_k: int = 10,
        filters: Optional[List[SearchFilter]] = None
    ) -> List[SearchResult]:
        """Find similar documents"""
        if collection not in self._collections:
            return []

        doc = self._collections[collection].get(document_id)
        if not doc:
            return []

        results = await self.search(collection, doc.embedding, top_k + 1, filters)

        # Remove the source document
        return [r for r in results if r.id != document_id][:top_k]

    async def get_by_ids(
        self,
        collection: str,
        ids: List[str]
    ) -> List[VectorDocument]:
        """Get documents by IDs"""
        if collection not in self._collections:
            return []

        return [
            self._collections[collection][doc_id]
            for doc_id in ids
            if doc_id in self._collections[collection]
        ]

    async def count(
        self,
        collection: str,
        filters: Optional[List[SearchFilter]] = None
    ) -> int:
        """Count documents"""
        if collection not in self._collections:
            return 0

        if not filters:
            return len(self._collections[collection])

        return sum(
            1 for doc in self._collections[collection].values()
            if self._apply_filters(doc, filters)
        )

    async def health_check(self) -> bool:
        """Always healthy"""
        return True

    # ==================== Test Helpers ====================

    def clear_all(self) -> None:
        """Clear all collections"""
        self._collections.clear()
        self._collection_configs.clear()

    def get_collection_size(self, collection: str) -> int:
        """Get number of documents in collection"""
        return len(self._collections.get(collection, {}))
