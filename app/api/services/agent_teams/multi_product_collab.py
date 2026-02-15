"""
Pattern D: Multi-Product Collaboration Team

"TJESとOSCの違い" 같은 복수 제품 비교/연관 질문을
DAGBuilder로 분해 → ParallelExecutor 실행 → 결과 합성.
"""
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 비교/연관 키워드 (일본어, 한국어, 영어)
COMPARISON_KEYWORDS = {
    # 일본어
    "比較", "違い", "差", "相違", "異なる", "同じ",
    # 한국어
    "비교", "차이", "다른", "같은",
    # 영어
    "compare", "comparison", "difference", "differ",
    "vs", "versus", "between",
    # 접속사 (멀티제품 연결)
    "と", "や", "또는", "와", "과", "and", "or",
}


class MultiProductCollaborationService:
    """
    멀티제품 비교/연관 질문을 DAGBuilder + ParallelExecutor로 처리.
    기존 인프라를 최대한 재활용.
    """

    def is_multi_product_query(
        self, query: str, product_ids: List[str]
    ) -> bool:
        """
        멀티 제품 비교/연관 질문인지 판별.
        조건: 2+ 제품 라우팅 + 비교 키워드 존재
        """
        if len(product_ids) < 2:
            return False

        query_lower = query.lower()
        return any(kw in query_lower for kw in COMPARISON_KEYWORDS)

    async def execute_collaboration(
        self,
        query: str,
        product_ids: List[str],
        language: str = "ja",
        rag_service=None,
    ) -> Dict[str, Any]:
        """
        멀티제품 협업 실행.
        각 제품별로 독립 검색+생성 후 결과 합성.

        Returns:
            Dict with 'synthesized_answer', 'sub_results', 'products_used'
        """
        if not rag_service:
            return {"synthesized_answer": None, "sub_results": {}, "products_used": []}

        # 각 제품에 대해 독립적으로 검색+LLM 생성
        import asyncio

        async def _query_product(pid: str) -> Dict[str, Any]:
            try:
                search_ctx = await rag_service._multi_product_search(
                    query=query,
                    product_ids=[pid],
                    query_type=None,
                )
                if not search_ctx or not search_ctx.structured_results:
                    return {"product": pid, "answer": "", "score": 0.0}

                context = rag_service._build_llm_context(
                    search_ctx.structured_results
                )
                if not context:
                    return {"product": pid, "answer": "", "score": 0.0}

                # LLM 생성
                from ..learning_llm_service import get_learning_llm_service
                llm_service = get_learning_llm_service()
                if not llm_service:
                    return {"product": pid, "answer": context[:500], "score": 0.3}

                adapter_product = rag_service._map_to_adapter_product(pid)
                result = await llm_service.generate(
                    question=query,
                    context=context,
                    max_tokens=1024,
                    temperature=0.3,
                    product=adapter_product,
                )
                answer = result if isinstance(result, str) else str(result)
                best_score = search_ctx.structured_results[0].relevance_score

                return {"product": pid, "answer": answer, "score": best_score}
            except Exception as e:
                logger.warning(f"Collaboration query for {pid} failed: {e}")
                return {"product": pid, "answer": "", "score": 0.0}

        tasks = [_query_product(pid) for pid in product_ids]
        sub_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 정리
        valid_results = {}
        for r in sub_results:
            if isinstance(r, dict) and r.get("answer"):
                valid_results[r["product"]] = r

        if not valid_results:
            return {
                "synthesized_answer": None,
                "sub_results": {},
                "products_used": product_ids,
            }

        # 합성: 각 제품 답변을 구조화하여 결합
        synthesized = self._synthesize(query, valid_results, language)

        return {
            "synthesized_answer": synthesized,
            "sub_results": valid_results,
            "products_used": list(valid_results.keys()),
        }

    def _synthesize(
        self,
        query: str,
        results: Dict[str, Dict[str, Any]],
        language: str,
    ) -> str:
        """제품별 답변을 구조화 합성"""
        parts = []
        for pid, data in results.items():
            product_label = pid.replace("_", " ").title()
            parts.append(f"## {product_label}\n\n{data['answer']}")

        if len(parts) == 1:
            return parts[0]

        return "\n\n---\n\n".join(parts)
