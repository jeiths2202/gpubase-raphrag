"""
Mindmap Health Checker - Service health monitoring for mindmap generation
Vector Index 존재 여부, Neo4j 연결 상태, 필수 데이터 유무 확인

Phase 1 - H1: Vector Index 존재 확인 로직
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """서비스 상태"""
    HEALTHY = "healthy"      # 모든 검사 통과
    DEGRADED = "degraded"    # 일부 기능 제한
    UNHEALTHY = "unhealthy"  # 서비스 불가


@dataclass
class HealthCheckResult:
    """헬스 체크 결과"""
    status: HealthStatus
    checks: Dict[str, bool]
    messages: List[str]
    can_proceed: bool

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "checks": self.checks,
            "messages": self.messages,
            "can_proceed": self.can_proceed
        }


class MindmapHealthChecker:
    """
    마인드맵 서비스 상태 검사기

    기능:
    - Neo4j 연결 상태 확인
    - Vector Index 존재 여부 확인 (캐싱 적용)
    - 문서 데이터 유무 확인
    - Vector Index 자동 생성
    """

    CACHE_TTL = 60  # 60초 캐시

    def __init__(self, graph):
        """
        Args:
            graph: Neo4jGraph 인스턴스
        """
        self.graph = graph
        self._index_cache: Optional[bool] = None
        self._cache_timestamp: float = 0

    def check_all(self) -> HealthCheckResult:
        """
        모든 상태 검사 실행

        Returns:
            HealthCheckResult: 검사 결과
        """
        checks = {}
        messages = []

        # 1. Neo4j 연결 확인
        checks["neo4j_connection"] = self._check_neo4j_connection()
        if not checks["neo4j_connection"]:
            messages.append("Neo4j 데이터베이스에 연결할 수 없습니다")
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                checks=checks,
                messages=messages,
                can_proceed=False
            )

        # 2. Vector Index 확인
        checks["vector_index"] = self._check_vector_index()
        if not checks["vector_index"]:
            messages.append("Vector Index 'chunk_embedding'이 존재하지 않습니다. 자동 생성을 시도합니다.")

        # 3. 문서 데이터 확인
        checks["has_documents"] = self._check_has_documents()
        if not checks["has_documents"]:
            messages.append("분석할 문서가 없습니다. 먼저 문서를 업로드해주세요.")

        # 4. Chunk 데이터 확인
        checks["has_chunks"] = self._check_has_chunks()
        if not checks["has_chunks"]:
            messages.append("처리된 청크가 없습니다. 문서 처리가 필요합니다.")

        # 상태 결정
        all_passed = all(checks.values())
        critical_passed = checks.get("neo4j_connection", False)
        has_data = checks.get("has_documents", False) or checks.get("has_chunks", False)

        if all_passed:
            status = HealthStatus.HEALTHY
        elif critical_passed and has_data:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY

        can_proceed = critical_passed and has_data

        return HealthCheckResult(
            status=status,
            checks=checks,
            messages=messages,
            can_proceed=can_proceed
        )

    def _check_neo4j_connection(self) -> bool:
        """Neo4j 연결 상태 확인"""
        try:
            result = self.graph.query("RETURN 1 as test")
            return len(result) > 0
        except Exception as e:
            logger.error(f"Neo4j connection check failed: {e}")
            return False

    def _check_vector_index(self) -> bool:
        """
        Vector Index 존재 여부 확인 (캐싱 적용)

        캐시 TTL: 60초
        """
        current_time = time.time()

        # 캐시 유효성 확인
        if self._index_cache is not None and (current_time - self._cache_timestamp) < self.CACHE_TTL:
            return self._index_cache

        try:
            # Neo4j 5.x 방식
            query = """
            SHOW INDEXES
            WHERE name = 'chunk_embedding'
            """
            result = self.graph.query(query)
            self._index_cache = len(result) > 0
            self._cache_timestamp = current_time

            if self._index_cache:
                logger.info("Vector index 'chunk_embedding' found")
            else:
                logger.warning("Vector index 'chunk_embedding' not found")

            return self._index_cache
        except Exception as e:
            logger.error(f"Vector index check failed: {e}")
            # 오류 시 대체 쿼리 시도
            try:
                alt_query = """
                CALL db.indexes() YIELD name
                WHERE name = 'chunk_embedding'
                RETURN name
                """
                result = self.graph.query(alt_query)
                self._index_cache = len(result) > 0
                self._cache_timestamp = current_time
                return self._index_cache
            except Exception as e2:
                logger.error(f"Alternative index check also failed: {e2}")
                return False

    def _check_has_documents(self) -> bool:
        """문서 데이터 존재 여부 확인"""
        try:
            query = "MATCH (d:Document) RETURN count(d) as cnt LIMIT 1"
            result = self.graph.query(query)
            count = result[0]["cnt"] if result else 0
            return count > 0
        except Exception as e:
            logger.error(f"Document check failed: {e}")
            return False

    def _check_has_chunks(self) -> bool:
        """청크 데이터 존재 여부 확인"""
        try:
            query = "MATCH (c:Chunk) RETURN count(c) as cnt LIMIT 1"
            result = self.graph.query(query)
            count = result[0]["cnt"] if result else 0
            return count > 0
        except Exception as e:
            logger.error(f"Chunk check failed: {e}")
            return False

    def ensure_vector_index(self, embedding_dimension: int = 4096) -> bool:
        """
        Vector Index가 없으면 생성 시도

        Args:
            embedding_dimension: 임베딩 차원 (기본값: 4096)

        Returns:
            bool: 인덱스 존재 또는 생성 성공 여부
        """
        if self._check_vector_index():
            return True

        try:
            # Neo4j 5.x 방식 Vector Index 생성
            create_query = f"""
            CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
            FOR (c:Chunk) ON (c.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {embedding_dimension},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
            self.graph.query(create_query)
            logger.info(f"Vector index 'chunk_embedding' created successfully (dim={embedding_dimension})")

            # 캐시 무효화
            self._index_cache = None
            self._cache_timestamp = 0

            return True
        except Exception as e:
            logger.error(f"Failed to create vector index: {e}")

            # 대체 방식 시도 (이전 버전 Neo4j)
            try:
                alt_query = """
                CALL db.index.vector.createNodeIndex(
                    'chunk_embedding',
                    'Chunk',
                    'embedding',
                    4096,
                    'cosine'
                )
                """
                self.graph.query(alt_query)
                logger.info("Vector index created using alternative method")
                self._index_cache = None
                return True
            except Exception as e2:
                logger.error(f"Alternative index creation also failed: {e2}")
                return False

    def get_stats(self) -> dict:
        """
        데이터베이스 통계 조회

        Returns:
            dict: 문서, 청크, 엔티티 수
        """
        stats = {
            "documents": 0,
            "chunks": 0,
            "entities": 0,
            "mindmaps": 0
        }

        try:
            # 문서 수
            doc_result = self.graph.query("MATCH (d:Document) RETURN count(d) as cnt")
            stats["documents"] = doc_result[0]["cnt"] if doc_result else 0

            # 청크 수
            chunk_result = self.graph.query("MATCH (c:Chunk) RETURN count(c) as cnt")
            stats["chunks"] = chunk_result[0]["cnt"] if chunk_result else 0

            # 엔티티 수
            entity_result = self.graph.query("MATCH (e:Entity) RETURN count(e) as cnt")
            stats["entities"] = entity_result[0]["cnt"] if entity_result else 0

            # 마인드맵 수
            mindmap_result = self.graph.query("MATCH (m:Mindmap) RETURN count(m) as cnt")
            stats["mindmaps"] = mindmap_result[0]["cnt"] if mindmap_result else 0

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")

        return stats

    def invalidate_cache(self):
        """캐시 무효화"""
        self._index_cache = None
        self._cache_timestamp = 0
        logger.info("Health checker cache invalidated")
