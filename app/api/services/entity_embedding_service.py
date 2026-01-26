"""
Entity Embedding Service

Service for generating entity embeddings and computing similarity-based
ML recommendations for query clarification.

This service enables context-aware entity recommendations by:
1. Generating embedding vectors for each possible entity
2. Computing query-entity similarity scores
3. Recommending the most relevant entity based on query context
"""
import logging
import math
from typing import Optional, List, Dict, Any, Tuple

from ..ports.embedding_port import EmbeddingPort
from ..models.clarification import PossibleEntity

logger = logging.getLogger(__name__)


class EntityEmbeddingService:
    """
    Service for generating and using entity embeddings.

    Provides:
    - Entity embedding generation from name, description, and keywords
    - Query-entity similarity computation
    - ML-based entity recommendation for ambiguous terms
    """

    def __init__(self, embedding_port: EmbeddingPort):
        """
        Initialize with embedding port.

        Args:
            embedding_port: Port for generating embeddings
        """
        self.embedding_port = embedding_port

    async def generate_entity_embedding(
        self,
        entity: PossibleEntity,
    ) -> List[float]:
        """
        Generate embedding for a single entity.

        Combines entity name, description, and keywords into a rich text
        representation for embedding.

        Args:
            entity: Entity to generate embedding for

        Returns:
            Embedding vector as list of floats
        """
        # 엔티티 정보를 결합하여 풍부한 텍스트 생성
        keywords_str = ", ".join(entity.keywords) if entity.keywords else ""
        text = f"{entity.name}. {entity.description}"
        if keywords_str:
            text += f" Keywords: {keywords_str}"

        try:
            result = await self.embedding_port.embed_text(text)
            return result.embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding for entity {entity.id}: {e}")
            raise

    async def generate_all_entity_embeddings(
        self,
        entities: List[PossibleEntity],
    ) -> Dict[str, List[float]]:
        """
        Generate embeddings for all entities of an ambiguous term.

        Args:
            entities: List of possible entities

        Returns:
            Dict mapping entity_id → embedding vector
        """
        embeddings = {}

        # 배치 처리를 위해 텍스트 준비
        texts = []
        entity_ids = []

        for entity in entities:
            keywords_str = ", ".join(entity.keywords) if entity.keywords else ""
            text = f"{entity.name}. {entity.description}"
            if keywords_str:
                text += f" Keywords: {keywords_str}"
            texts.append(text)
            entity_ids.append(entity.id)

        try:
            # 배치로 임베딩 생성
            batch_result = await self.embedding_port.embed_texts(texts)

            for entity_id, result in zip(entity_ids, batch_result.embeddings):
                embeddings[entity_id] = result.embedding

            logger.debug(f"Generated embeddings for {len(embeddings)} entities")
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise

    async def recommend_entity(
        self,
        query: str,
        possible_entities: List[PossibleEntity],
        entity_embeddings: Dict[str, List[float]],
    ) -> Tuple[str, str, float]:
        """
        Recommend the most relevant entity based on query context.

        Computes cosine similarity between query embedding and each
        entity embedding, returning the best match.

        Args:
            query: User query text
            possible_entities: List of possible entities to choose from
            entity_embeddings: Pre-computed embeddings for entities
                              (from ambiguous_terms.entity_embeddings)

        Returns:
            Tuple of (entity_id, entity_name, confidence_score)
            confidence_score is 0.0-1.0 where higher means more confident
        """
        if not possible_entities:
            raise ValueError("No possible entities provided")

        if not entity_embeddings:
            # 임베딩이 없으면 첫 번째 엔티티 반환 (낮은 신뢰도)
            logger.warning("No entity embeddings available, returning first entity")
            return possible_entities[0].id, possible_entities[0].name, 0.0

        try:
            # 쿼리 임베딩 생성
            query_result = await self.embedding_port.embed_query(query)
            query_embedding = query_result.embedding

            # 각 엔티티와 유사도 계산
            similarities = {}
            for entity in possible_entities:
                if entity.id in entity_embeddings:
                    entity_embedding = entity_embeddings[entity.id]
                    similarity = self._cosine_similarity(query_embedding, entity_embedding)
                    similarities[entity.id] = {
                        "similarity": similarity,
                        "name": entity.name,
                    }

            if not similarities:
                logger.warning("No matching embeddings found for any entity")
                return possible_entities[0].id, possible_entities[0].name, 0.0

            # 최고 유사도 엔티티 선택
            best_entity_id = max(similarities, key=lambda k: similarities[k]["similarity"])
            best_data = similarities[best_entity_id]

            # 유사도를 confidence로 변환 (0.5~1.0 범위를 0~1로 정규화)
            # 코사인 유사도가 0.5 이하면 신뢰도 0, 1.0이면 신뢰도 1
            raw_similarity = best_data["similarity"]
            confidence = max(0.0, min(1.0, (raw_similarity - 0.5) * 2))

            logger.debug(
                f"Entity recommendation: {best_entity_id} "
                f"(similarity={raw_similarity:.3f}, confidence={confidence:.3f})"
            )

            return best_entity_id, best_data["name"], confidence

        except Exception as e:
            logger.error(f"Failed to recommend entity: {e}")
            # 에러 발생 시 첫 번째 엔티티 반환
            return possible_entities[0].id, possible_entities[0].name, 0.0

    async def compute_all_similarities(
        self,
        query: str,
        possible_entities: List[PossibleEntity],
        entity_embeddings: Dict[str, List[float]],
    ) -> List[Dict[str, Any]]:
        """
        Compute similarities for all entities (for detailed analysis).

        Args:
            query: User query text
            possible_entities: List of possible entities
            entity_embeddings: Pre-computed embeddings

        Returns:
            List of dicts with entity_id, name, similarity, and confidence
            sorted by similarity (descending)
        """
        if not entity_embeddings:
            return []

        try:
            query_result = await self.embedding_port.embed_query(query)
            query_embedding = query_result.embedding

            results = []
            for entity in possible_entities:
                if entity.id in entity_embeddings:
                    entity_embedding = entity_embeddings[entity.id]
                    similarity = self._cosine_similarity(query_embedding, entity_embedding)
                    confidence = max(0.0, min(1.0, (similarity - 0.5) * 2))

                    results.append({
                        "entity_id": entity.id,
                        "entity_name": entity.name,
                        "similarity": similarity,
                        "confidence": confidence,
                    })

            # 유사도 내림차순 정렬
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results

        except Exception as e:
            logger.error(f"Failed to compute similarities: {e}")
            return []

    def _cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        if len(embedding1) != len(embedding2):
            logger.warning(
                f"Embedding dimension mismatch: {len(embedding1)} vs {len(embedding2)}"
            )
            return 0.0

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def health_check(self) -> bool:
        """
        Check if the embedding service is healthy.

        Returns:
            True if service is healthy
        """
        try:
            return await self.embedding_port.health_check()
        except Exception:
            return False


# =============================================================================
# Service Factory
# =============================================================================

_entity_embedding_service: Optional[EntityEmbeddingService] = None


def get_entity_embedding_service() -> EntityEmbeddingService:
    """Get the entity embedding service singleton."""
    global _entity_embedding_service
    if _entity_embedding_service is None:
        raise RuntimeError(
            "EntityEmbeddingService not initialized. "
            "Call initialize_entity_embedding_service first."
        )
    return _entity_embedding_service


def initialize_entity_embedding_service(
    embedding_port: EmbeddingPort,
) -> EntityEmbeddingService:
    """
    Initialize the entity embedding service singleton.

    Args:
        embedding_port: Port for generating embeddings

    Returns:
        Initialized EntityEmbeddingService
    """
    global _entity_embedding_service
    _entity_embedding_service = EntityEmbeddingService(embedding_port)
    logger.info("EntityEmbeddingService initialized")
    return _entity_embedding_service


def set_entity_embedding_service(service: EntityEmbeddingService) -> None:
    """Set the entity embedding service singleton."""
    global _entity_embedding_service
    _entity_embedding_service = service
