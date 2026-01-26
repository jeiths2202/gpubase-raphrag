"""
RAG Evaluation Models
RAGAS 스타일의 RAG 품질 평가 모델

Metrics:
- Faithfulness: 응답이 컨텍스트에 기반하는지 (환각 탐지)
- Context Relevance: 검색된 문맥의 질문 관련성
- Answer Relevancy: 응답의 질문 적합성
- Context Precision: 관련 컨텍스트의 순위 품질
- Context Recall: 필요 정보 포함도
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class RAGMetricType(str, Enum):
    """RAG 평가 메트릭 유형"""
    FAITHFULNESS = "faithfulness"
    CONTEXT_RELEVANCE = "context_relevance"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"


class EvaluationMethod(str, Enum):
    """평가 방식"""
    LLM_BASED = "llm_based"
    RULE_BASED = "rule_based"
    HYBRID = "hybrid"


class RAGEvaluationLevel(str, Enum):
    """평가 등급"""
    EXCELLENT = "excellent"  # >= 0.8
    GOOD = "good"           # >= 0.6
    FAIR = "fair"           # >= 0.4
    POOR = "poor"           # < 0.4


# Detail Models for each metric
class FaithfulnessDetail(BaseModel):
    """Faithfulness 상세 결과 - claims 분석"""
    total_claims: int = Field(description="총 추출된 주장 수")
    supported_claims: int = Field(description="컨텍스트에서 지원되는 주장 수")
    unsupported_claims: List[str] = Field(default_factory=list, description="지원되지 않는 주장들")
    claim_analysis: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="각 주장별 분석 결과 [{claim, supported, evidence}]"
    )


class ContextRelevanceDetail(BaseModel):
    """Context Relevance 상세 결과 - 소스별 관련성"""
    source_scores: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="소스별 관련성 점수 [{source, score, reason}]"
    )
    avg_embedding_similarity: Optional[float] = Field(None, description="평균 임베딩 유사도")
    keyword_overlap_ratio: Optional[float] = Field(None, description="키워드 오버랩 비율")


class AnswerRelevancyDetail(BaseModel):
    """Answer Relevancy 상세 결과 - 생성 질문 비교"""
    generated_questions: List[str] = Field(
        default_factory=list,
        description="응답에서 역생성된 질문들"
    )
    question_similarities: List[float] = Field(
        default_factory=list,
        description="원본 질문과 생성 질문 간 유사도"
    )
    avg_similarity: float = Field(description="평균 유사도")


class ContextPrecisionDetail(BaseModel):
    """Context Precision 상세 결과 - 순위 품질"""
    rank_relevance: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="순위별 관련성 [{rank, relevant, score}]"
    )
    average_precision: float = Field(description="Average Precision (AP) 점수")
    precision_at_k: Dict[str, float] = Field(
        default_factory=dict,
        description="P@K 점수 {k: precision}"
    )


class ContextRecallDetail(BaseModel):
    """Context Recall 상세 결과 - 문장별 귀속"""
    ground_truth_sentences: int = Field(description="Ground truth 문장 수")
    attributed_sentences: int = Field(description="컨텍스트에 귀속된 문장 수")
    attribution_details: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="문장별 귀속 분석 [{sentence, attributed, source}]"
    )


class MetricResult(BaseModel):
    """개별 메트릭 결과"""
    metric_type: RAGMetricType = Field(description="메트릭 유형")
    score: float = Field(ge=0.0, le=1.0, description="점수 (0.0-1.0)")
    method: EvaluationMethod = Field(description="평가 방식")
    weight: float = Field(ge=0.0, le=1.0, description="가중치")
    details: Optional[Dict[str, Any]] = Field(None, description="상세 결과")
    explanation: str = Field(description="설명")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class RAGEvaluationResult(BaseModel):
    """RAG 평가 전체 결과"""
    evaluation_id: str = Field(description="평가 ID")
    trace_id: Optional[str] = Field(None, description="관련 Agent trace ID")
    conversation_id: Optional[str] = Field(None, description="대화 ID")

    # 입력
    query: str = Field(description="원본 질문")
    answer: str = Field(description="생성된 응답")
    sources_count: int = Field(description="사용된 소스 수")

    # 개별 메트릭
    metrics: Dict[RAGMetricType, MetricResult] = Field(
        default_factory=dict,
        description="메트릭별 결과"
    )

    # 종합 결과
    overall_score: float = Field(ge=0.0, le=1.0, description="종합 점수")
    overall_level: RAGEvaluationLevel = Field(description="종합 등급")

    # 분석
    issues: List[str] = Field(default_factory=list, description="발견된 문제점")
    recommendations: List[str] = Field(default_factory=list, description="개선 권장사항")

    # 메타데이터
    evaluation_time_ms: int = Field(description="평가 소요 시간 (ms)")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# API Request/Response Models
class SourceInput(BaseModel):
    """평가용 소스 입력"""
    content: str = Field(description="소스 내용")
    score: Optional[float] = Field(None, description="검색 점수")
    source: Optional[str] = Field(None, description="소스 출처")
    doc_id: Optional[str] = Field(None, description="문서 ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="추가 메타데이터")


class RAGEvaluationRequest(BaseModel):
    """RAG 평가 요청"""
    query: str = Field(..., min_length=1, description="질문")
    answer: str = Field(..., min_length=1, description="응답")
    sources: List[SourceInput] = Field(..., min_length=1, description="검색된 소스들")
    ground_truth: Optional[str] = Field(
        None,
        description="정답 (Context Recall 계산용)"
    )
    trace_id: Optional[str] = Field(None, description="Agent trace ID")
    conversation_id: Optional[str] = Field(None, description="대화 ID")
    metrics_to_evaluate: Optional[List[RAGMetricType]] = Field(
        None,
        description="평가할 메트릭 (None=전체)"
    )
    language: str = Field(default="ko", description="결과 언어 (ko, en, ja)")


class RAGEvaluationResponse(BaseModel):
    """RAG 평가 응답"""
    success: bool = Field(description="성공 여부")
    evaluation: Optional[RAGEvaluationResult] = Field(None, description="평가 결과")
    error: Optional[str] = Field(None, description="에러 메시지")


class RAGEvaluationStreamChunk(BaseModel):
    """평가 스트리밍 청크"""
    chunk_type: str = Field(description="청크 타입: metric_start, metric_done, evaluation_done")
    metric_type: Optional[RAGMetricType] = Field(None, description="현재 평가 중인 메트릭")
    metric_result: Optional[MetricResult] = Field(None, description="메트릭 결과")
    progress: Optional[float] = Field(None, description="진행률 (0.0-1.0)")
    message: Optional[str] = Field(None, description="상태 메시지")
    evaluation: Optional[RAGEvaluationResult] = Field(None, description="최종 평가 결과")


class RAGEvaluationStatsRequest(BaseModel):
    """평가 통계 조회 요청"""
    start_date: Optional[datetime] = Field(None, description="시작일")
    end_date: Optional[datetime] = Field(None, description="종료일")
    user_id: Optional[str] = Field(None, description="사용자 ID 필터")
    level_filter: Optional[RAGEvaluationLevel] = Field(None, description="등급 필터")


class RAGEvaluationStats(BaseModel):
    """평가 통계 응답"""
    total_evaluations: int = Field(description="총 평가 수")
    avg_overall_score: float = Field(description="평균 종합 점수")
    avg_metrics: Dict[str, float] = Field(description="메트릭별 평균")
    level_distribution: Dict[RAGEvaluationLevel, int] = Field(description="등급별 분포")
    common_issues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="자주 발생하는 문제 [{issue, count}]"
    )
    trend: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="시간별 추이 [{date, avg_score}]"
    )


class RAGEvaluationListItem(BaseModel):
    """평가 목록 아이템"""
    evaluation_id: str
    query: str
    overall_score: float
    overall_level: RAGEvaluationLevel
    issues_count: int
    evaluated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
