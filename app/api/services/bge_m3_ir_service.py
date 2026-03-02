"""
BGE-M3 IR Pipeline Service

BGE-M3 기반 Hybrid IR (Sparse + Dense + Reranker) 파이프라인.
Query → BGE-M3 encode → Neo4j Vector Index search → Top-K 문서

표준 패턴:
  [문서 임베딩] → Neo4j에 이미 저장됨 (1회, 오프라인)
  [쿼리 시]     → BGE-M3로 쿼리만 임베딩 → Neo4j vector search → 결과 반환

API Endpoints (192.168.8.11:12801):
  - POST /v1/embeddings  → dense vectors (1024d)
  - POST /v1/sparse      → sparse weights {token_id: weight}
  - POST /v1/hybrid      → dense + sparse 동시
"""
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass
class HybridEmbedding:
    """BGE-M3 hybrid 인코딩 결과"""
    dense: List[float]
    sparse_weights: Dict[str, float]


# 제품 ID → Neo4j Document.filename 필터 패턴 (lowercase)
_PRODUCT_FILTER_MAP: Dict[str, List[str]] = {
    "openframe_mvs": ["openframe"],
    "openframe_base": ["of_base"],
    "openframe_batch": ["of_batch", "tjes"],
    "openframe_osc": ["of_osc"],
    "openframe_osi": ["of_osi"],
    "openframe_aim": ["of_aim"],
    "openframe_tacf": ["of_tacf"],
    "openframe_hidb": ["of_hidb"],
    "openframe_ndb": ["of_ndb"],
    "tibero7": ["tibero"],
    "jeus": ["jeus"],
    "tmax": ["tmax"],
    "webtob": ["webtob"],
    "ofasm": ["ofasm"],
    "ofcobol": ["ofcobol"],
    "protrieve": ["protrieve"],
    "prosync": ["prosync"],
    "ofstudio": ["ofstudio"],
    "ofminer": ["ofminer"],
    "prosort": ["prosort"],
}


class BgeM3IRService:
    """
    BGE-M3 기반 Hybrid IR 서비스 (Singleton)

    기능:
    1. Dense encoding (1024d) - /v1/embeddings
    2. Sparse encoding (learned sparse) - /v1/sparse
    3. Hybrid encoding (dense + sparse) - /v1/hybrid
    4. Neo4j Vector Index 기반 1차 검색
    5. RRF (Reciprocal Rank Fusion) 병합
    6. Dense reranking
    """

    _instance: Optional["BgeM3IRService"] = None

    def __init__(self):
        from ..core.config import api_settings
        self._base_url = getattr(api_settings, "BGE_M3_BASE_URL", "http://localhost:12801")
        self._timeout = getattr(api_settings, "IR_EMBED_TIMEOUT", 5.0)
        self._rrf_k = getattr(api_settings, "IR_RRF_K", 60)
        self._sparse_weight = getattr(api_settings, "IR_SPARSE_WEIGHT", 0.4)
        self._dense_weight = getattr(api_settings, "IR_DENSE_WEIGHT", 0.6)
        self._rerank_top_n = getattr(api_settings, "IR_RERANK_TOP_N", 20)

        # 실시간 인코딩 캐시 (hybrid_search/rerank fallback용)
        self._doc_cache: Dict[str, HybridEmbedding] = {}

        # Neo4j driver (lazy init)
        self._neo4j_driver = None

        logger.info(
            f"BgeM3IRService initialized: base_url={self._base_url}, "
            f"rrf_k={self._rrf_k}, sparse_w={self._sparse_weight}, dense_w={self._dense_weight}"
        )

    # =========================================================================
    # Neo4j driver
    # =========================================================================

    def _get_neo4j_driver(self):
        """Neo4j driver 획득 (lazy singleton)"""
        if self._neo4j_driver is None:
            from neo4j import GraphDatabase
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")
            self._neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        return self._neo4j_driver

    @staticmethod
    def _product_to_filters(product_id: str) -> List[str]:
        """제품 ID → Neo4j Document.filename 필터 패턴 리스트 (lowercase)"""
        filters = _PRODUCT_FILTER_MAP.get(product_id)
        if filters:
            return filters
        # 매핑 없으면 product_id 자체를 필터로 사용
        return [product_id.lower()]

    # =========================================================================
    # BGE-M3 API 호출
    # =========================================================================

    async def encode_dense(self, texts: List[str]) -> Optional[List[List[float]]]:
        """BGE-M3 /v1/embeddings → dense vectors (1024d)"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/embeddings",
                    json={"input": texts, "model": "bge-m3"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
        except Exception as e:
            logger.warning(f"BGE-M3 dense encoding failed: {e}")
            return None

    async def encode_sparse(self, texts: List[str]) -> Optional[List[Dict[str, float]]]:
        """BGE-M3 /v1/sparse → sparse weights {token_id: weight}"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/sparse",
                    json={"input": texts, "model": "bge-m3"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [item["sparse_weights"] for item in data["data"]]
        except Exception as e:
            logger.warning(f"BGE-M3 sparse encoding failed: {e}")
            return None

    async def encode_hybrid(self, texts: List[str]) -> Optional[List[HybridEmbedding]]:
        """BGE-M3 /v1/hybrid → dense + sparse 동시 반환"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/hybrid",
                    json={"input": texts, "model": "bge-m3"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    HybridEmbedding(
                        dense=item["dense"],
                        sparse_weights=item["sparse_weights"],
                    )
                    for item in data["data"]
                ]
        except Exception as e:
            logger.warning(f"BGE-M3 hybrid encoding failed: {e}")
            return None

    async def health_check(self) -> bool:
        """BGE-M3 서버 상태 확인"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/v1/health/ready")
                return resp.status_code == 200
        except Exception:
            return False

    # =========================================================================
    # Neo4j Vector Index 기반 검색
    # =========================================================================

    async def neo4j_vector_search(
        self,
        query: str,
        product_id: str,
        top_k: int = 50,
    ) -> List[Dict]:
        """
        Neo4j Vector Index 기반 검색 (리치 결과 반환).

        1. query → BGE-M3 encode_dense() → 1024d vector
        2. Neo4j CALL db.index.vector.queryNodes() → cosine similarity
        3. Document filename으로 product 필터링
        4. Return list of dicts: {content, title, chunk_id, doc_name, page_number, score}
        """
        t0 = time.monotonic()

        # 1) 쿼리 임베딩 (BGE-M3 원격 API)
        query_vecs = await self.encode_dense([query[:512]])
        if not query_vecs:
            logger.warning("BGE-M3 dense encoding failed for Neo4j vector search")
            return []
        query_embedding = query_vecs[0]

        # 2) Neo4j vector search (product 필터링 포함)
        filters = self._product_to_filters(product_id)
        driver = self._get_neo4j_driver()

        try:
            with driver.session() as session:
                result = session.run(
                    """
                    CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
                    YIELD node, score
                    MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
                    WHERE ANY(pattern IN $filters WHERE toLower(d.filename) CONTAINS pattern)
                    RETURN
                        node.content as content,
                        node.id as chunk_id,
                        d.filename as doc_name,
                        node.page_number as page_number,
                        score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    embedding=query_embedding,
                    k=top_k * 4,  # 제품 필터링 전 여유분 확보
                    filters=filters,
                    limit=top_k,
                )

                results = []
                for record in result:
                    content = record["content"] or ""
                    title = content.split("\n")[0][:80] if content else ""
                    results.append({
                        "content": content,
                        "title": title,
                        "chunk_id": record["chunk_id"],
                        "doc_name": record["doc_name"] or "",
                        "page_number": record["page_number"],
                        "score": record["score"],
                    })

            elapsed = time.monotonic() - t0
            if results:
                logger.info(
                    f"Neo4j vector search: product={product_id}, "
                    f"query='{query[:30]}...', results={len(results)}, "
                    f"top_score={results[0]['score']:.4f}, elapsed={elapsed:.3f}s"
                )
            else:
                logger.info(
                    f"Neo4j vector search: product={product_id}, "
                    f"query='{query[:30]}...', results=0, elapsed={elapsed:.3f}s"
                )
            return results
        except Exception as e:
            logger.error(f"Neo4j vector search failed: {e}")
            return []

    async def primary_search(
        self,
        query: str,
        product_id: str,
        domain_filter: Optional[List[str]] = None,
        top_k: int = 50,
    ) -> List[Tuple[str, float]]:
        """
        Neo4j Vector Index 기반 1차 검색 (backward-compatible interface).

        Returns:
            List of (section_key, score) tuples, sorted by score desc.
            section_key format: "{product_id}::pdf_manuals::{doc_name}::{title}"
        """
        results = await self.neo4j_vector_search(query, product_id, top_k)
        return [
            (
                f"{product_id}::pdf_manuals::{r['doc_name']}::{r['title']}",
                r["score"],
            )
            for r in results
        ]

    # =========================================================================
    # Hybrid IR Search (fallback path - keyword 후보 대상 리랭킹)
    # =========================================================================

    async def hybrid_search(
        self,
        query: str,
        candidate_sections: List[Dict],
        keyword_scores: List[float],
        product_id: str,
        top_k: int = 3,
    ) -> List[Tuple[int, float]]:
        """
        BGE-M3 Hybrid IR Pipeline:
        1) Query hybrid encoding
        2) Dense similarity + Sparse similarity 각각 계산
        3) RRF 병합
        4) Top-K 반환
        """
        if not candidate_sections:
            return []

        n = len(candidate_sections)
        t0 = time.monotonic()

        # 1) Query hybrid encoding
        query_emb = await self.encode_hybrid([query[:512]])
        if query_emb is None:
            # BGE-M3 실패 → keyword 점수만으로 반환
            logger.debug("BGE-M3 unavailable, falling back to keyword scores")
            ranked = sorted(range(n), key=lambda i: keyword_scores[i], reverse=True)
            return [(i, keyword_scores[i]) for i in ranked[:top_k]]

        query_dense = query_emb[0].dense
        query_sparse = query_emb[0].sparse_weights

        # 2) 문서 임베딩 확보 (캐시 or 실시간)
        doc_embeddings = await self._get_doc_embeddings(
            candidate_sections, product_id
        )

        # 3) Dense similarity 계산
        dense_scores = []
        for i, doc_emb in enumerate(doc_embeddings):
            if doc_emb and doc_emb.dense:
                sim = self._cosine_similarity(query_dense, doc_emb.dense)
                dense_scores.append((i, sim))
            else:
                dense_scores.append((i, 0.0))

        # 4) Sparse similarity 계산
        sparse_scores = []
        for i, doc_emb in enumerate(doc_embeddings):
            if doc_emb and doc_emb.sparse_weights:
                sim = self._sparse_dot_product(query_sparse, doc_emb.sparse_weights)
                sparse_scores.append((i, sim))
            else:
                max_kw = max(keyword_scores) if keyword_scores else 1.0
                norm_kw = keyword_scores[i] / max_kw if max_kw > 0 else 0.0
                sparse_scores.append((i, norm_kw))

        # 5) RRF 병합
        dense_scores.sort(key=lambda x: x[1], reverse=True)
        sparse_scores.sort(key=lambda x: x[1], reverse=True)

        rrf_scores = self._rrf_fusion(dense_scores, sparse_scores)

        elapsed = time.monotonic() - t0
        logger.info(
            f"IR hybrid_search: {n} candidates → top-{top_k} in {elapsed:.3f}s "
            f"(dense_w={self._dense_weight}, sparse_w={self._sparse_weight})"
        )

        return rrf_scores[:top_k]

    async def rerank(
        self,
        query: str,
        candidate_sections: List[Dict],
        product_id: str,
        top_k: int = 3,
    ) -> List[Tuple[int, float]]:
        """Dense similarity 기반 정밀 reranking."""
        if not candidate_sections:
            return []

        query_dense = await self.encode_dense([query[:512]])
        if query_dense is None:
            return [(i, 0.0) for i in range(min(top_k, len(candidate_sections)))]

        q_vec = query_dense[0]

        doc_embeddings = await self._get_doc_embeddings(
            candidate_sections, product_id
        )

        scores = []
        for i, doc_emb in enumerate(doc_embeddings):
            if doc_emb and doc_emb.dense:
                sim = self._cosine_similarity(q_vec, doc_emb.dense)
                scores.append((i, sim))
            else:
                scores.append((i, 0.0))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _get_doc_embeddings(
        self,
        sections: List[Dict],
        product_id: str,
    ) -> List[Optional[HybridEmbedding]]:
        """캐시에서 문서 임베딩 조회. 미캐시 시 실시간 계산."""
        result: List[Optional[HybridEmbedding]] = []
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, section in enumerate(sections):
            cache_key = self._make_cache_key(product_id, section)
            cached = self._doc_cache.get(cache_key)
            if cached:
                result.append(cached)
            else:
                result.append(None)
                uncached_indices.append(i)
                uncached_texts.append(self._section_to_text(section)[:512])

        # 미캐시 문서 실시간 인코딩
        if uncached_texts:
            embeddings = await self.encode_hybrid(uncached_texts)
            if embeddings:
                for j, idx in enumerate(uncached_indices):
                    if j < len(embeddings):
                        emb = embeddings[j]
                        result[idx] = emb
                        cache_key = self._make_cache_key(product_id, sections[idx])
                        self._doc_cache[cache_key] = emb

        return result

    def _rrf_fusion(
        self,
        dense_ranked: List[Tuple[int, float]],
        sparse_ranked: List[Tuple[int, float]],
    ) -> List[Tuple[int, float]]:
        """Reciprocal Rank Fusion (RRF)"""
        k = self._rrf_k
        scores: Dict[int, float] = {}

        for rank, (idx, _score) in enumerate(dense_ranked):
            scores[idx] = scores.get(idx, 0.0) + self._dense_weight / (k + rank + 1)

        for rank, (idx, _score) in enumerate(sparse_ranked):
            scores[idx] = scores.get(idx, 0.0) + self._sparse_weight / (k + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """두 벡터의 코사인 유사도"""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _sparse_dot_product(
        sparse_a: Dict[str, float],
        sparse_b: Dict[str, float],
    ) -> float:
        """두 sparse vector의 dot product (공통 토큰만)"""
        if not sparse_a or not sparse_b:
            return 0.0
        score = 0.0
        if len(sparse_a) <= len(sparse_b):
            for token, weight_a in sparse_a.items():
                weight_b = sparse_b.get(token)
                if weight_b is not None:
                    score += weight_a * weight_b
        else:
            for token, weight_b in sparse_b.items():
                weight_a = sparse_a.get(token)
                if weight_a is not None:
                    score += weight_a * weight_b
        return score

    @staticmethod
    def _make_cache_key(product_id: str, section: Dict) -> str:
        """섹션의 캐시 키 생성"""
        domain = section.get("domain", "unknown")
        title = section.get("title", "")[:50]
        source = section.get("source_file", "")
        return f"{product_id}::{domain}::{source}::{title}"

    @staticmethod
    def _section_to_text(section: Dict, max_chars: int = 800) -> str:
        """섹션을 검색용 텍스트로 변환 (BGE-M3 max 512 tokens ~ 800 chars)"""
        title = section.get("title", "")
        content = section.get("content", "")
        text = f"{title}\n{content}"
        return text[:max_chars] if len(text) > max_chars else text


# =========================================================================
# Singleton accessor
# =========================================================================

_ir_service: Optional[BgeM3IRService] = None


def get_bge_m3_ir_service() -> BgeM3IRService:
    """BGE-M3 IR Service 싱글톤 반환"""
    global _ir_service
    if _ir_service is None:
        _ir_service = BgeM3IRService()
    return _ir_service
