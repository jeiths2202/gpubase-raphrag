"""Knowledge Retrieval Agent

진단 결과를 바탕으로 기존 Knowledge Base에서 에러 가이드 + 유사 사례를 검색합니다.

3단계 검색:
  1. ABEND Registry → 정적 매핑 (즉시, 0ms)
  2. SummarySearchService → error-codes/*.md (정확 매칭, <10ms)
  3. SummaryBM25Service → 에러 메시지 전문 검색 (BM25, <50ms)
"""
import logging
from typing import Optional

from app.api.models.jcl_diagnosis import (
    DiagnosisResult, KnowledgeResult, ErrorGuide, SimilarCase
)
from app.api.services.summary_search_service import get_summary_search_service
from app.api.services.summary_bm25_service import get_summary_bm25_service
from .abend_code_registry import ABEND_REGISTRY

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """에러 가이드 + 유사 사례 검색"""

    async def search(self, diagnosis: DiagnosisResult) -> KnowledgeResult:
        """진단 결과 기반 지식 검색"""
        result = KnowledgeResult()

        if not diagnosis.primary_error:
            return result

        # ──── Stage 1: ABEND 레지스트리 즉시 조회 ────
        abend_info = ABEND_REGISTRY.get(diagnosis.primary_error.code)
        if abend_info:
            result.error_guides.append(ErrorGuide(
                code=diagnosis.primary_error.code,
                description=abend_info.get("description", ""),
                cause=abend_info.get("cause", ""),
                solution="\n".join(abend_info.get("common_causes", [])),
                source_file="abend_code_registry (built-in)",
                confidence=1.0,
            ))

        # ──── Stage 2: Summary Search (에러코드 정확 매칭) ────
        summary_svc = get_summary_search_service()
        for error in diagnosis.all_errors[:5]:
            try:
                summary_result = await summary_svc.search_error_code(error.code)
                if summary_result:
                    result.error_guides.append(ErrorGuide(
                        code=error.code,
                        name=summary_result.get("name"),
                        module=summary_result.get("module"),
                        description=summary_result.get("description", ""),
                        cause=summary_result.get("cause", ""),
                        solution=summary_result.get("solution", ""),
                        source_file=summary_result.get("source_file"),
                        confidence=0.95,
                    ))
            except Exception as e:
                logger.debug(f"Summary search failed for {error.code}: {e}")

        # ──── Stage 3: BM25 전문 검색 (에러 메시지 기반) ────
        bm25_svc = get_summary_bm25_service()
        error_text = diagnosis.primary_error.message_line
        try:
            bm25_results = await bm25_svc.search(
                query=error_text,
                top_k=3,
            )
            for r in bm25_results:
                # SummarySearchResult: .document (SummaryDocument), .score
                if r.score > 0.3:
                    result.similar_cases.append(SimilarCase(
                        title=r.document.name or r.document.id,
                        description=(r.document.content or "")[:500],
                        similarity_score=r.score,
                        source=r.document.source_file or "",
                    ))
        except Exception as e:
            logger.debug(f"BM25 search failed: {e}")

        return result
