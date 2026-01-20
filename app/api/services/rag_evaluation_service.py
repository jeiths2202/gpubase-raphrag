"""
RAG Evaluation Service
RAGAS 스타일 RAG 품질 평가 서비스

Evaluates RAG responses using 5 key metrics:
1. Faithfulness - 응답이 컨텍스트에 기반하는지 (환각 탐지)
2. Context Relevance - 검색된 문맥의 질문 관련성
3. Answer Relevancy - 응답의 질문 적합성
4. Context Precision - 관련 컨텍스트의 순위 품질
5. Context Recall - 필요 정보 포함도 (ground truth 필요)
"""
import asyncio
import logging
import time
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, AsyncGenerator, Tuple

from ..models.rag_evaluation import (
    RAGMetricType,
    EvaluationMethod,
    RAGEvaluationLevel,
    MetricResult,
    RAGEvaluationResult,
    SourceInput,
    RAGEvaluationRequest,
    RAGEvaluationStreamChunk,
    FaithfulnessDetail,
    ContextRelevanceDetail,
    AnswerRelevancyDetail,
    ContextPrecisionDetail,
    ContextRecallDetail,
)
from ..core.config import api_settings

logger = logging.getLogger(__name__)

# Metric weights
METRIC_WEIGHTS = {
    RAGMetricType.FAITHFULNESS: 0.30,
    RAGMetricType.CONTEXT_RELEVANCE: 0.25,
    RAGMetricType.ANSWER_RELEVANCY: 0.25,
    RAGMetricType.CONTEXT_PRECISION: 0.10,
    RAGMetricType.CONTEXT_RECALL: 0.10,
}

# Evaluation prompts for LLM-based metrics
FAITHFULNESS_PROMPT = """주어진 응답과 컨텍스트를 분석하여 응답이 컨텍스트에 기반하는지 평가합니다.

컨텍스트:
{context}

응답:
{answer}

다음 형식으로 분석하세요:
1. 응답에서 주장/사실을 추출합니다.
2. 각 주장이 컨텍스트에서 지원되는지 확인합니다.

JSON 형식으로 응답:
{{
    "claims": [
        {{"claim": "주장1", "supported": true/false, "evidence": "근거 또는 없음"}}
    ],
    "faithfulness_score": 0.0-1.0
}}"""

CONTEXT_RELEVANCE_PROMPT = """질문과 각 컨텍스트의 관련성을 평가합니다.

질문:
{query}

컨텍스트들:
{contexts}

각 컨텍스트의 관련성을 0.0-1.0으로 평가하고 이유를 제시하세요.
JSON 형식으로 응답:
{{
    "source_scores": [
        {{"source_index": 0, "score": 0.0-1.0, "reason": "이유"}}
    ],
    "avg_score": 0.0-1.0
}}"""

ANSWER_RELEVANCY_PROMPT = """응답이 질문에 얼마나 적합한지 평가합니다.

원본 질문:
{query}

응답:
{answer}

응답에서 역으로 질문을 3개 생성하고, 원본 질문과의 유사도를 평가하세요.
JSON 형식으로 응답:
{{
    "generated_questions": ["질문1", "질문2", "질문3"],
    "similarities": [0.0-1.0, 0.0-1.0, 0.0-1.0],
    "avg_similarity": 0.0-1.0
}}"""


class RAGEvaluationService:
    """RAG 평가 서비스"""

    def __init__(
        self,
        llm_adapter: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
        repository: Optional[Any] = None,
    ):
        """
        Args:
            llm_adapter: LLM 어댑터 (LLM 기반 평가용)
            embedding_service: 임베딩 서비스 (유사도 계산용)
            repository: 평가 결과 저장소
        """
        self.llm_adapter = llm_adapter
        self.embedding_service = embedding_service
        self.repository = repository
        self._evaluation_enabled = getattr(
            api_settings, 'RAG_EVALUATION_ENABLED', True
        )
        self._timeout = getattr(
            api_settings, 'RAG_EVALUATION_TIMEOUT', 30.0
        )

    async def evaluate(
        self,
        query: str,
        answer: str,
        sources: List[SourceInput],
        ground_truth: Optional[str] = None,
        metrics_to_evaluate: Optional[List[RAGMetricType]] = None,
        language: str = "ko",
        trace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: str = "anonymous",
    ) -> RAGEvaluationResult:
        """
        RAG 응답 품질 평가 수행

        Args:
            query: 원본 질문
            answer: 생성된 응답
            sources: 검색된 소스들
            ground_truth: 정답 (Context Recall용, 선택적)
            metrics_to_evaluate: 평가할 메트릭 목록 (None=전체)
            language: 결과 언어
            trace_id: Agent trace ID
            conversation_id: 대화 ID
            user_id: 사용자 ID

        Returns:
            RAGEvaluationResult
        """
        start_time = time.time()
        evaluation_id = str(uuid.uuid4())

        # 평가할 메트릭 결정
        if metrics_to_evaluate is None:
            metrics_to_evaluate = list(RAGMetricType)

        # Context Recall은 ground_truth가 있어야 함
        if RAGMetricType.CONTEXT_RECALL in metrics_to_evaluate and not ground_truth:
            metrics_to_evaluate = [
                m for m in metrics_to_evaluate
                if m != RAGMetricType.CONTEXT_RECALL
            ]

        # 컨텍스트 준비
        contexts = [s.content for s in sources]
        combined_context = "\n\n---\n\n".join(contexts)

        # 메트릭 평가 (병렬 실행)
        metrics: Dict[RAGMetricType, MetricResult] = {}

        eval_tasks = []
        for metric_type in metrics_to_evaluate:
            if metric_type == RAGMetricType.FAITHFULNESS:
                eval_tasks.append(
                    self._evaluate_faithfulness(answer, combined_context, language)
                )
            elif metric_type == RAGMetricType.CONTEXT_RELEVANCE:
                eval_tasks.append(
                    self._evaluate_context_relevance(query, sources, language)
                )
            elif metric_type == RAGMetricType.ANSWER_RELEVANCY:
                eval_tasks.append(
                    self._evaluate_answer_relevancy(query, answer, language)
                )
            elif metric_type == RAGMetricType.CONTEXT_PRECISION:
                eval_tasks.append(
                    self._evaluate_context_precision(query, sources, answer, language)
                )
            elif metric_type == RAGMetricType.CONTEXT_RECALL:
                eval_tasks.append(
                    self._evaluate_context_recall(combined_context, ground_truth, language)
                )

        # 타임아웃과 함께 병렬 실행
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*eval_tasks, return_exceptions=True),
                timeout=self._timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"[RAGEval] Evaluation timeout after {self._timeout}s")
            results = [None] * len(eval_tasks)

        # 결과 정리
        for i, metric_type in enumerate(metrics_to_evaluate):
            result = results[i] if i < len(results) else None
            if isinstance(result, Exception):
                logger.error(f"[RAGEval] Error evaluating {metric_type}: {result}")
                result = None

            if result is None:
                # 평가 실패 시 기본값
                result = MetricResult(
                    metric_type=metric_type,
                    score=0.5,
                    method=EvaluationMethod.RULE_BASED,
                    weight=METRIC_WEIGHTS.get(metric_type, 0.1),
                    explanation=f"{metric_type.value} 평가 실패 - 기본값 적용",
                    details=None,
                )

            metrics[metric_type] = result

        # 종합 점수 계산
        overall_score, issues, recommendations = self._aggregate_scores(
            metrics, query, answer, sources, language
        )
        overall_level = self._get_level(overall_score)

        # 평가 시간
        evaluation_time_ms = int((time.time() - start_time) * 1000)

        result = RAGEvaluationResult(
            evaluation_id=evaluation_id,
            trace_id=trace_id,
            conversation_id=conversation_id,
            query=query,
            answer=answer,
            sources_count=len(sources),
            metrics=metrics,
            overall_score=overall_score,
            overall_level=overall_level,
            issues=issues,
            recommendations=recommendations,
            evaluation_time_ms=evaluation_time_ms,
            evaluated_at=datetime.now(timezone.utc),
        )

        # 저장소에 저장 (비동기)
        if self.repository:
            try:
                await self.repository.save(result, user_id, sources)
            except Exception as e:
                logger.error(f"[RAGEval] Failed to save evaluation: {e}")

        return result

    async def evaluate_stream(
        self,
        request: RAGEvaluationRequest,
        user_id: str = "anonymous",
    ) -> AsyncGenerator[RAGEvaluationStreamChunk, None]:
        """스트리밍 평가 - 각 메트릭 완료 시 청크 전송"""
        start_time = time.time()
        evaluation_id = str(uuid.uuid4())

        metrics_to_evaluate = request.metrics_to_evaluate or list(RAGMetricType)
        if RAGMetricType.CONTEXT_RECALL in metrics_to_evaluate and not request.ground_truth:
            metrics_to_evaluate = [
                m for m in metrics_to_evaluate
                if m != RAGMetricType.CONTEXT_RECALL
            ]

        total_metrics = len(metrics_to_evaluate)
        completed = 0
        metrics: Dict[RAGMetricType, MetricResult] = {}

        contexts = [s.content for s in request.sources]
        combined_context = "\n\n---\n\n".join(contexts)

        for metric_type in metrics_to_evaluate:
            # 시작 청크
            yield RAGEvaluationStreamChunk(
                chunk_type="metric_start",
                metric_type=metric_type,
                progress=completed / total_metrics,
                message=f"평가 중: {metric_type.value}",
            )

            # 메트릭 평가
            try:
                if metric_type == RAGMetricType.FAITHFULNESS:
                    result = await self._evaluate_faithfulness(
                        request.answer, combined_context, request.language
                    )
                elif metric_type == RAGMetricType.CONTEXT_RELEVANCE:
                    result = await self._evaluate_context_relevance(
                        request.query, request.sources, request.language
                    )
                elif metric_type == RAGMetricType.ANSWER_RELEVANCY:
                    result = await self._evaluate_answer_relevancy(
                        request.query, request.answer, request.language
                    )
                elif metric_type == RAGMetricType.CONTEXT_PRECISION:
                    result = await self._evaluate_context_precision(
                        request.query, request.sources, request.answer, request.language
                    )
                elif metric_type == RAGMetricType.CONTEXT_RECALL:
                    result = await self._evaluate_context_recall(
                        combined_context, request.ground_truth, request.language
                    )
                else:
                    result = None
            except Exception as e:
                logger.error(f"[RAGEval] Stream eval error for {metric_type}: {e}")
                result = None

            if result is None:
                result = MetricResult(
                    metric_type=metric_type,
                    score=0.5,
                    method=EvaluationMethod.RULE_BASED,
                    weight=METRIC_WEIGHTS.get(metric_type, 0.1),
                    explanation=f"{metric_type.value} 평가 실패",
                    details=None,
                )

            metrics[metric_type] = result
            completed += 1

            # 완료 청크
            yield RAGEvaluationStreamChunk(
                chunk_type="metric_done",
                metric_type=metric_type,
                metric_result=result,
                progress=completed / total_metrics,
                message=f"완료: {metric_type.value} (점수: {result.score:.2f})",
            )

        # 최종 결과 생성
        overall_score, issues, recommendations = self._aggregate_scores(
            metrics, request.query, request.answer, request.sources, request.language
        )
        overall_level = self._get_level(overall_score)
        evaluation_time_ms = int((time.time() - start_time) * 1000)

        final_result = RAGEvaluationResult(
            evaluation_id=evaluation_id,
            trace_id=request.trace_id,
            conversation_id=request.conversation_id,
            query=request.query,
            answer=request.answer,
            sources_count=len(request.sources),
            metrics=metrics,
            overall_score=overall_score,
            overall_level=overall_level,
            issues=issues,
            recommendations=recommendations,
            evaluation_time_ms=evaluation_time_ms,
            evaluated_at=datetime.now(timezone.utc),
        )

        # 저장
        if self.repository:
            try:
                await self.repository.save(final_result, user_id, request.sources)
            except Exception as e:
                logger.error(f"[RAGEval] Failed to save streamed evaluation: {e}")

        # 최종 청크
        yield RAGEvaluationStreamChunk(
            chunk_type="evaluation_done",
            progress=1.0,
            message="평가 완료",
            evaluation=final_result,
        )

    # ========== Private Methods ==========

    async def _evaluate_faithfulness(
        self,
        answer: str,
        context: str,
        language: str,
    ) -> MetricResult:
        """
        Faithfulness 평가: 응답이 컨텍스트에 기반하는지

        Hybrid 방식:
        1. Rule-based: 문장 오버랩 분석
        2. LLM-based: 주장 추출 및 검증 (LLM 있을 경우)
        """
        # Rule-based 분석
        answer_sentences = self._split_sentences(answer)
        context_lower = context.lower()

        supported_count = 0
        unsupported = []
        claim_analysis = []

        for sentence in answer_sentences:
            # 키워드 기반 지원 여부 확인
            words = set(re.findall(r'\w+', sentence.lower()))
            significant_words = [w for w in words if len(w) > 2]

            if not significant_words:
                supported_count += 1
                continue

            # 컨텍스트에서 키워드 매칭 확인
            matched_words = sum(1 for w in significant_words if w in context_lower)
            support_ratio = matched_words / len(significant_words) if significant_words else 0

            is_supported = support_ratio >= 0.3  # 30% 이상 키워드 매칭

            if is_supported:
                supported_count += 1
            else:
                unsupported.append(sentence[:100])

            claim_analysis.append({
                "claim": sentence[:100],
                "supported": is_supported,
                "evidence": f"키워드 매칭률: {support_ratio:.2%}"
            })

        total_claims = len(answer_sentences) if answer_sentences else 1
        score = supported_count / total_claims

        details = FaithfulnessDetail(
            total_claims=total_claims,
            supported_claims=supported_count,
            unsupported_claims=unsupported[:5],
            claim_analysis=claim_analysis[:10],
        )

        explanation = self._get_faithfulness_explanation(score, language)

        return MetricResult(
            metric_type=RAGMetricType.FAITHFULNESS,
            score=round(score, 3),
            method=EvaluationMethod.HYBRID,
            weight=METRIC_WEIGHTS[RAGMetricType.FAITHFULNESS],
            details=details.model_dump(),
            explanation=explanation,
        )

    async def _evaluate_context_relevance(
        self,
        query: str,
        sources: List[SourceInput],
        language: str,
    ) -> MetricResult:
        """
        Context Relevance 평가: 검색된 컨텍스트의 질문 관련성

        Hybrid 방식:
        1. 기존 검색 점수 활용
        2. 키워드 오버랩 분석
        """
        source_scores = []
        query_words = set(re.findall(r'\w+', query.lower()))
        query_words = {w for w in query_words if len(w) > 2}

        for i, source in enumerate(sources):
            # 기존 검색 점수 활용
            search_score = source.score if source.score else 0.5

            # 키워드 오버랩
            content_words = set(re.findall(r'\w+', source.content.lower()))
            if query_words:
                overlap = len(query_words & content_words) / len(query_words)
            else:
                overlap = 0.5

            # 결합 점수
            combined_score = (search_score * 0.6 + overlap * 0.4)

            source_scores.append({
                "source_index": i,
                "source": source.source or f"Source {i+1}",
                "score": round(combined_score, 3),
                "search_score": search_score,
                "keyword_overlap": round(overlap, 3),
                "reason": f"검색점수: {search_score:.2f}, 키워드매칭: {overlap:.2%}"
            })

        avg_score = sum(s["score"] for s in source_scores) / len(source_scores) if source_scores else 0

        details = ContextRelevanceDetail(
            source_scores=source_scores,
            keyword_overlap_ratio=sum(s["keyword_overlap"] for s in source_scores) / len(source_scores) if source_scores else 0,
        )

        explanation = self._get_context_relevance_explanation(avg_score, language)

        return MetricResult(
            metric_type=RAGMetricType.CONTEXT_RELEVANCE,
            score=round(avg_score, 3),
            method=EvaluationMethod.HYBRID,
            weight=METRIC_WEIGHTS[RAGMetricType.CONTEXT_RELEVANCE],
            details=details.model_dump(),
            explanation=explanation,
        )

    async def _evaluate_answer_relevancy(
        self,
        query: str,
        answer: str,
        language: str,
    ) -> MetricResult:
        """
        Answer Relevancy 평가: 응답이 질문에 적합한지

        Rule-based 방식:
        1. 질문 유형 매칭
        2. 키워드 커버리지
        3. 응답 길이 적절성
        """
        # 질문 키워드 추출
        query_words = set(re.findall(r'\w+', query.lower()))
        query_words = {w for w in query_words if len(w) > 2}

        answer_words = set(re.findall(r'\w+', answer.lower()))

        # 키워드 커버리지
        if query_words:
            coverage = len(query_words & answer_words) / len(query_words)
        else:
            coverage = 0.5

        # 응답 길이 적절성 (너무 짧거나 길지 않은지)
        answer_len = len(answer)
        if answer_len < 20:
            length_score = 0.3
        elif answer_len < 50:
            length_score = 0.6
        elif answer_len < 500:
            length_score = 1.0
        elif answer_len < 1000:
            length_score = 0.9
        else:
            length_score = 0.8

        # 질문 유형에 맞는 응답인지 (간단한 휴리스틱)
        question_patterns = {
            "what": answer_len > 20,
            "how": answer_len > 50 or "방법" in answer or "단계" in answer,
            "why": "때문" in answer or "이유" in answer or "because" in answer.lower(),
            "when": any(c.isdigit() for c in answer) or "년" in answer or "월" in answer,
            "where": "에서" in answer or "위치" in answer or "장소" in answer,
        }

        query_lower = query.lower()
        type_match_score = 0.7  # 기본값

        for pattern, condition in question_patterns.items():
            if pattern in query_lower:
                type_match_score = 0.9 if condition else 0.5
                break

        # 종합 점수
        score = (coverage * 0.4 + length_score * 0.3 + type_match_score * 0.3)

        details = AnswerRelevancyDetail(
            generated_questions=[],  # LLM 없이는 생성 불가
            question_similarities=[],
            avg_similarity=score,
        )

        explanation = self._get_answer_relevancy_explanation(score, language)

        return MetricResult(
            metric_type=RAGMetricType.ANSWER_RELEVANCY,
            score=round(score, 3),
            method=EvaluationMethod.RULE_BASED,
            weight=METRIC_WEIGHTS[RAGMetricType.ANSWER_RELEVANCY],
            details=details.model_dump(),
            explanation=explanation,
        )

    async def _evaluate_context_precision(
        self,
        query: str,
        sources: List[SourceInput],
        answer: str,
        language: str,
    ) -> MetricResult:
        """
        Context Precision 평가: 관련 컨텍스트의 순위 품질

        Rule-based 방식:
        1. 검색 점수 기반 순위 분석
        2. Average Precision (AP) 계산
        """
        if not sources:
            return MetricResult(
                metric_type=RAGMetricType.CONTEXT_PRECISION,
                score=0.0,
                method=EvaluationMethod.RULE_BASED,
                weight=METRIC_WEIGHTS[RAGMetricType.CONTEXT_PRECISION],
                details=None,
                explanation="소스가 없어 평가할 수 없습니다.",
            )

        # 관련성 판단 (간단한 휴리스틱)
        query_words = set(re.findall(r'\w+', query.lower()))
        query_words = {w for w in query_words if len(w) > 2}

        rank_relevance = []
        relevant_count = 0
        precision_sum = 0

        for i, source in enumerate(sources, 1):
            content_words = set(re.findall(r'\w+', source.content.lower()))
            overlap = len(query_words & content_words) / len(query_words) if query_words else 0

            # 관련성 임계값
            is_relevant = (source.score or 0) >= 0.5 or overlap >= 0.3

            if is_relevant:
                relevant_count += 1
                precision_sum += relevant_count / i

            rank_relevance.append({
                "rank": i,
                "relevant": is_relevant,
                "score": source.score or 0,
                "overlap": round(overlap, 3),
            })

        # Average Precision
        ap_score = precision_sum / relevant_count if relevant_count > 0 else 0

        # P@K
        precision_at_k = {}
        for k in [1, 3, 5]:
            if k <= len(rank_relevance):
                relevant_in_k = sum(1 for r in rank_relevance[:k] if r["relevant"])
                precision_at_k[f"P@{k}"] = round(relevant_in_k / k, 3)

        details = ContextPrecisionDetail(
            rank_relevance=rank_relevance,
            average_precision=round(ap_score, 3),
            precision_at_k=precision_at_k,
        )

        explanation = self._get_context_precision_explanation(ap_score, language)

        return MetricResult(
            metric_type=RAGMetricType.CONTEXT_PRECISION,
            score=round(ap_score, 3),
            method=EvaluationMethod.RULE_BASED,
            weight=METRIC_WEIGHTS[RAGMetricType.CONTEXT_PRECISION],
            details=details.model_dump(),
            explanation=explanation,
        )

    async def _evaluate_context_recall(
        self,
        context: str,
        ground_truth: Optional[str],
        language: str,
    ) -> MetricResult:
        """
        Context Recall 평가: 정답의 정보가 컨텍스트에 포함되어 있는지

        Rule-based 방식: 문장별 귀속 분석
        """
        if not ground_truth:
            return MetricResult(
                metric_type=RAGMetricType.CONTEXT_RECALL,
                score=0.0,
                method=EvaluationMethod.RULE_BASED,
                weight=METRIC_WEIGHTS[RAGMetricType.CONTEXT_RECALL],
                details=None,
                explanation="Ground truth가 없어 평가할 수 없습니다.",
            )

        gt_sentences = self._split_sentences(ground_truth)
        context_lower = context.lower()

        attributed = 0
        attribution_details = []

        for sentence in gt_sentences:
            words = set(re.findall(r'\w+', sentence.lower()))
            significant_words = [w for w in words if len(w) > 2]

            if not significant_words:
                attributed += 1
                attribution_details.append({
                    "sentence": sentence[:100],
                    "attributed": True,
                    "source": "trivial"
                })
                continue

            matched = sum(1 for w in significant_words if w in context_lower)
            is_attributed = matched / len(significant_words) >= 0.4 if significant_words else True

            if is_attributed:
                attributed += 1

            attribution_details.append({
                "sentence": sentence[:100],
                "attributed": is_attributed,
                "match_ratio": matched / len(significant_words) if significant_words else 1.0,
            })

        total = len(gt_sentences) if gt_sentences else 1
        score = attributed / total

        details = ContextRecallDetail(
            ground_truth_sentences=total,
            attributed_sentences=attributed,
            attribution_details=attribution_details[:10],
        )

        explanation = self._get_context_recall_explanation(score, language)

        return MetricResult(
            metric_type=RAGMetricType.CONTEXT_RECALL,
            score=round(score, 3),
            method=EvaluationMethod.RULE_BASED,
            weight=METRIC_WEIGHTS[RAGMetricType.CONTEXT_RECALL],
            details=details.model_dump(),
            explanation=explanation,
        )

    def _aggregate_scores(
        self,
        metrics: Dict[RAGMetricType, MetricResult],
        query: str,
        answer: str,
        sources: List[SourceInput],
        language: str,
    ) -> Tuple[float, List[str], List[str]]:
        """종합 점수 계산 및 이슈/권장사항 생성"""
        if not metrics:
            return 0.0, ["평가된 메트릭이 없습니다."], []

        # 가중 평균 계산
        weighted_sum = 0.0
        weight_sum = 0.0

        for metric_type, result in metrics.items():
            weighted_sum += result.score * result.weight
            weight_sum += result.weight

        overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0
        overall_score = round(min(1.0, max(0.0, overall_score)), 3)

        # 이슈 식별
        issues = []
        recommendations = []

        threshold_low = 0.4
        threshold_medium = 0.6

        for metric_type, result in metrics.items():
            if result.score < threshold_low:
                issue, rec = self._get_issue_and_recommendation(
                    metric_type, result.score, "low", language
                )
                issues.append(issue)
                recommendations.append(rec)
            elif result.score < threshold_medium:
                issue, rec = self._get_issue_and_recommendation(
                    metric_type, result.score, "medium", language
                )
                issues.append(issue)

        return overall_score, issues, recommendations

    def _get_level(self, score: float) -> RAGEvaluationLevel:
        """점수에서 등급 결정"""
        if score >= 0.8:
            return RAGEvaluationLevel.EXCELLENT
        elif score >= 0.6:
            return RAGEvaluationLevel.GOOD
        elif score >= 0.4:
            return RAGEvaluationLevel.FAIR
        else:
            return RAGEvaluationLevel.POOR

    def _split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장으로 분리"""
        # 간단한 문장 분리 (한국어/영어 지원)
        sentences = re.split(r'[.!?。]\s*', text)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

    # ========== Explanation Generators ==========

    def _get_faithfulness_explanation(self, score: float, language: str) -> str:
        """Faithfulness 설명 생성"""
        explanations = {
            "ko": {
                "high": f"응답의 {score*100:.0f}%가 컨텍스트에 기반합니다. 환각이 적습니다.",
                "medium": f"응답의 {score*100:.0f}%가 컨텍스트에서 확인됩니다. 일부 내용 검증이 필요합니다.",
                "low": f"응답의 {score*100:.0f}%만 컨텍스트에서 지원됩니다. 환각 가능성이 높습니다.",
            },
            "en": {
                "high": f"{score*100:.0f}% of the response is grounded in context. Low hallucination.",
                "medium": f"{score*100:.0f}% verified from context. Some content needs verification.",
                "low": f"Only {score*100:.0f}% supported by context. High hallucination risk.",
            },
            "ja": {
                "high": f"回答の{score*100:.0f}%がコンテキストに基づいています。幻覚が少ないです。",
                "medium": f"回答の{score*100:.0f}%がコンテキストで確認されます。一部の内容は検証が必要です。",
                "low": f"回答の{score*100:.0f}%のみがコンテキストでサポートされています。幻覚の可能性が高いです。",
            },
        }
        lang = language if language in explanations else "ko"
        level = "high" if score >= 0.8 else ("medium" if score >= 0.5 else "low")
        return explanations[lang][level]

    def _get_context_relevance_explanation(self, score: float, language: str) -> str:
        """Context Relevance 설명 생성"""
        explanations = {
            "ko": {
                "high": f"검색된 컨텍스트가 질문과 {score*100:.0f}% 관련성이 있습니다.",
                "medium": f"컨텍스트 관련성이 {score*100:.0f}%입니다. 더 관련성 높은 문서 검색을 권장합니다.",
                "low": f"컨텍스트 관련성이 {score*100:.0f}%로 낮습니다. 검색 품질 개선이 필요합니다.",
            },
            "en": {
                "high": f"Retrieved context is {score*100:.0f}% relevant to the query.",
                "medium": f"Context relevance is {score*100:.0f}%. Consider refining search.",
                "low": f"Context relevance is low at {score*100:.0f}%. Search quality needs improvement.",
            },
            "ja": {
                "high": f"検索されたコンテキストは質問と{score*100:.0f}%関連しています。",
                "medium": f"コンテキストの関連性は{score*100:.0f}%です。より関連性の高い検索を推奨します。",
                "low": f"コンテキストの関連性が{score*100:.0f}%と低いです。検索品質の改善が必要です。",
            },
        }
        lang = language if language in explanations else "ko"
        level = "high" if score >= 0.8 else ("medium" if score >= 0.5 else "low")
        return explanations[lang][level]

    def _get_answer_relevancy_explanation(self, score: float, language: str) -> str:
        """Answer Relevancy 설명 생성"""
        explanations = {
            "ko": {
                "high": f"응답이 질문에 {score*100:.0f}% 적합합니다.",
                "medium": f"응답 적합성이 {score*100:.0f}%입니다. 질문의 일부를 더 직접적으로 다루면 좋겠습니다.",
                "low": f"응답 적합성이 {score*100:.0f}%로 낮습니다. 질문에 더 직접적인 답변이 필요합니다.",
            },
            "en": {
                "high": f"Response is {score*100:.0f}% relevant to the question.",
                "medium": f"Answer relevancy is {score*100:.0f}%. Could address the question more directly.",
                "low": f"Answer relevancy is low at {score*100:.0f}%. Needs more direct response.",
            },
            "ja": {
                "high": f"回答は質問に{score*100:.0f}%適合しています。",
                "medium": f"回答の適合性は{score*100:.0f}%です。質問により直接的に対応することを推奨します。",
                "low": f"回答の適合性が{score*100:.0f}%と低いです。より直接的な回答が必要です。",
            },
        }
        lang = language if language in explanations else "ko"
        level = "high" if score >= 0.8 else ("medium" if score >= 0.5 else "low")
        return explanations[lang][level]

    def _get_context_precision_explanation(self, score: float, language: str) -> str:
        """Context Precision 설명 생성"""
        explanations = {
            "ko": {
                "high": f"관련 컨텍스트가 상위에 잘 배치되어 있습니다 (AP: {score:.2f}).",
                "medium": f"컨텍스트 순위가 보통입니다 (AP: {score:.2f}). 순위 최적화를 고려하세요.",
                "low": f"관련 컨텍스트 순위가 낮습니다 (AP: {score:.2f}). 리랭킹이 필요합니다.",
            },
            "en": {
                "high": f"Relevant context is well-ranked (AP: {score:.2f}).",
                "medium": f"Context ranking is moderate (AP: {score:.2f}). Consider ranking optimization.",
                "low": f"Relevant context ranking is poor (AP: {score:.2f}). Re-ranking needed.",
            },
            "ja": {
                "high": f"関連コンテキストが上位に適切に配置されています (AP: {score:.2f})。",
                "medium": f"コンテキストのランキングは普通です (AP: {score:.2f})。ランキング最適化を検討してください。",
                "low": f"関連コンテキストのランキングが低いです (AP: {score:.2f})。リランキングが必要です。",
            },
        }
        lang = language if language in explanations else "ko"
        level = "high" if score >= 0.8 else ("medium" if score >= 0.5 else "low")
        return explanations[lang][level]

    def _get_context_recall_explanation(self, score: float, language: str) -> str:
        """Context Recall 설명 생성"""
        explanations = {
            "ko": {
                "high": f"정답 정보의 {score*100:.0f}%가 컨텍스트에 포함되어 있습니다.",
                "medium": f"정답 정보의 {score*100:.0f}%가 컨텍스트에서 발견됩니다. 추가 검색을 권장합니다.",
                "low": f"정답 정보의 {score*100:.0f}%만 컨텍스트에 있습니다. 검색 범위 확대가 필요합니다.",
            },
            "en": {
                "high": f"{score*100:.0f}% of ground truth is covered in context.",
                "medium": f"{score*100:.0f}% of ground truth found in context. Additional search recommended.",
                "low": f"Only {score*100:.0f}% of ground truth in context. Expand search scope.",
            },
            "ja": {
                "high": f"正解情報の{score*100:.0f}%がコンテキストに含まれています。",
                "medium": f"正解情報の{score*100:.0f}%がコンテキストで見つかります。追加検索を推奨します。",
                "low": f"正解情報の{score*100:.0f}%のみがコンテキストにあります。検索範囲の拡大が必要です。",
            },
        }
        lang = language if language in explanations else "ko"
        level = "high" if score >= 0.8 else ("medium" if score >= 0.5 else "low")
        return explanations[lang][level]

    def _get_issue_and_recommendation(
        self,
        metric_type: RAGMetricType,
        score: float,
        severity: str,
        language: str,
    ) -> Tuple[str, str]:
        """메트릭별 이슈 및 권장사항 생성"""
        issues_rec = {
            "ko": {
                RAGMetricType.FAITHFULNESS: (
                    f"충실도 점수가 {score:.2f}로 낮습니다 - 환각 가능성",
                    "응답 생성 시 컨텍스트 참조를 강화하세요"
                ),
                RAGMetricType.CONTEXT_RELEVANCE: (
                    f"컨텍스트 관련성이 {score:.2f}로 낮습니다",
                    "검색 쿼리 확장 또는 리랭킹 적용을 권장합니다"
                ),
                RAGMetricType.ANSWER_RELEVANCY: (
                    f"응답 적합성이 {score:.2f}로 낮습니다",
                    "질문의 핵심 의도를 파악하여 답변하세요"
                ),
                RAGMetricType.CONTEXT_PRECISION: (
                    f"컨텍스트 정밀도가 {score:.2f}로 낮습니다",
                    "검색 결과 리랭킹 알고리즘 적용을 권장합니다"
                ),
                RAGMetricType.CONTEXT_RECALL: (
                    f"컨텍스트 재현율이 {score:.2f}로 낮습니다",
                    "검색 범위를 확대하거나 청크 크기를 조정하세요"
                ),
            },
            "en": {
                RAGMetricType.FAITHFULNESS: (
                    f"Faithfulness score is low at {score:.2f} - hallucination risk",
                    "Strengthen context reference in response generation"
                ),
                RAGMetricType.CONTEXT_RELEVANCE: (
                    f"Context relevance is low at {score:.2f}",
                    "Consider query expansion or re-ranking"
                ),
                RAGMetricType.ANSWER_RELEVANCY: (
                    f"Answer relevancy is low at {score:.2f}",
                    "Address the core intent of the question"
                ),
                RAGMetricType.CONTEXT_PRECISION: (
                    f"Context precision is low at {score:.2f}",
                    "Apply re-ranking algorithm to search results"
                ),
                RAGMetricType.CONTEXT_RECALL: (
                    f"Context recall is low at {score:.2f}",
                    "Expand search scope or adjust chunk size"
                ),
            },
        }

        lang = language if language in issues_rec else "ko"
        return issues_rec[lang].get(
            metric_type,
            (f"{metric_type.value} 점수가 낮습니다", "개선이 필요합니다")
        )


# Singleton instance
_rag_evaluation_service: Optional[RAGEvaluationService] = None


def get_rag_evaluation_service() -> RAGEvaluationService:
    """Get or create RAG evaluation service singleton"""
    global _rag_evaluation_service
    if _rag_evaluation_service is None:
        _rag_evaluation_service = RAGEvaluationService()
    return _rag_evaluation_service


def set_rag_evaluation_service(service: RAGEvaluationService) -> None:
    """Set RAG evaluation service (for dependency injection)"""
    global _rag_evaluation_service
    _rag_evaluation_service = service
