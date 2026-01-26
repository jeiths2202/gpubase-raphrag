"""
RAG Evaluation Repository
PostgreSQL 기반 RAG 평가 결과 저장소
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID
import asyncpg

from ..models.rag_evaluation import (
    RAGMetricType,
    RAGEvaluationLevel,
    RAGEvaluationResult,
    RAGEvaluationStats,
    RAGEvaluationListItem,
    SourceInput,
    MetricResult,
)

logger = logging.getLogger(__name__)


class RAGEvaluationRepository:
    """RAG 평가 결과 저장소"""

    def __init__(self, pool: asyncpg.Pool):
        """
        Args:
            pool: PostgreSQL connection pool
        """
        self._pool = pool

    @classmethod
    def from_pool(cls, pool: asyncpg.Pool) -> "RAGEvaluationRepository":
        """Create repository from existing pool"""
        return cls(pool)

    async def _ensure_table_exists(self) -> None:
        """테이블 존재 확인 및 생성"""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_evaluations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    evaluation_id UUID UNIQUE NOT NULL,
                    trace_id UUID,
                    conversation_id UUID,
                    user_id VARCHAR(100) NOT NULL,
                    query TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sources_count INTEGER NOT NULL DEFAULT 0,
                    sources_json JSONB,
                    faithfulness_score FLOAT,
                    context_relevance_score FLOAT,
                    answer_relevancy_score FLOAT,
                    context_precision_score FLOAT,
                    context_recall_score FLOAT,
                    overall_score FLOAT NOT NULL,
                    overall_level VARCHAR(20) NOT NULL,
                    metric_details JSONB,
                    issues JSONB,
                    recommendations JSONB,
                    evaluation_time_ms INTEGER,
                    ground_truth_provided BOOLEAN DEFAULT FALSE,
                    language VARCHAR(10) DEFAULT 'ko',
                    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create indexes if not exist
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rag_eval_user_id
                ON rag_evaluations(user_id, evaluated_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rag_eval_level
                ON rag_evaluations(overall_level)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rag_eval_score
                ON rag_evaluations(overall_score DESC)
            """)

    async def save(
        self,
        result: RAGEvaluationResult,
        user_id: str,
        sources: Optional[List[SourceInput]] = None,
    ) -> str:
        """
        평가 결과 저장

        Args:
            result: 평가 결과
            user_id: 사용자 ID
            sources: 원본 소스 데이터 (저장용)

        Returns:
            evaluation_id
        """
        try:
            # 메트릭 점수 추출
            faithfulness_score = None
            context_relevance_score = None
            answer_relevancy_score = None
            context_precision_score = None
            context_recall_score = None

            metric_details = {}
            for metric_type, metric_result in result.metrics.items():
                metric_details[metric_type.value] = {
                    "score": metric_result.score,
                    "method": metric_result.method.value,
                    "weight": metric_result.weight,
                    "explanation": metric_result.explanation,
                    "details": metric_result.details,
                }

                if metric_type == RAGMetricType.FAITHFULNESS:
                    faithfulness_score = metric_result.score
                elif metric_type == RAGMetricType.CONTEXT_RELEVANCE:
                    context_relevance_score = metric_result.score
                elif metric_type == RAGMetricType.ANSWER_RELEVANCY:
                    answer_relevancy_score = metric_result.score
                elif metric_type == RAGMetricType.CONTEXT_PRECISION:
                    context_precision_score = metric_result.score
                elif metric_type == RAGMetricType.CONTEXT_RECALL:
                    context_recall_score = metric_result.score

            # 소스 JSON 변환
            sources_json = None
            if sources:
                sources_json = json.dumps([s.model_dump() for s in sources])

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO rag_evaluations (
                        evaluation_id, trace_id, conversation_id, user_id,
                        query, answer, sources_count, sources_json,
                        faithfulness_score, context_relevance_score,
                        answer_relevancy_score, context_precision_score,
                        context_recall_score, overall_score, overall_level,
                        metric_details, issues, recommendations,
                        evaluation_time_ms, ground_truth_provided, evaluated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, $15,
                        $16, $17, $18, $19, $20, $21
                    )
                    """,
                    UUID(result.evaluation_id),
                    UUID(result.trace_id) if result.trace_id else None,
                    UUID(result.conversation_id) if result.conversation_id else None,
                    user_id,
                    result.query,
                    result.answer,
                    result.sources_count,
                    sources_json,
                    faithfulness_score,
                    context_relevance_score,
                    answer_relevancy_score,
                    context_precision_score,
                    context_recall_score,
                    result.overall_score,
                    result.overall_level.value,
                    json.dumps(metric_details),
                    json.dumps(result.issues),
                    json.dumps(result.recommendations),
                    result.evaluation_time_ms,
                    bool(context_recall_score is not None),
                    result.evaluated_at,
                )

            logger.info(f"[RAGEvalRepo] Saved evaluation {result.evaluation_id}")
            return result.evaluation_id

        except Exception as e:
            logger.error(f"[RAGEvalRepo] Failed to save evaluation: {e}")
            raise

    async def get_by_id(self, evaluation_id: str) -> Optional[RAGEvaluationResult]:
        """ID로 평가 결과 조회"""
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM rag_evaluations
                    WHERE evaluation_id = $1
                    """,
                    UUID(evaluation_id)
                )

            if not row:
                return None

            return self._row_to_result(row)

        except Exception as e:
            logger.error(f"[RAGEvalRepo] Failed to get evaluation: {e}")
            return None

    async def list_evaluations(
        self,
        user_id: Optional[str] = None,
        level_filter: Optional[RAGEvaluationLevel] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[RAGEvaluationListItem]:
        """평가 목록 조회"""
        try:
            conditions = []
            params = []
            param_idx = 1

            if user_id:
                conditions.append(f"user_id = ${param_idx}")
                params.append(user_id)
                param_idx += 1

            if level_filter:
                conditions.append(f"overall_level = ${param_idx}")
                params.append(level_filter.value)
                param_idx += 1

            if start_date:
                conditions.append(f"evaluated_at >= ${param_idx}")
                params.append(start_date)
                param_idx += 1

            if end_date:
                conditions.append(f"evaluated_at <= ${param_idx}")
                params.append(end_date)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                SELECT evaluation_id, query, overall_score, overall_level,
                       issues, evaluated_at
                FROM rag_evaluations
                {where_clause}
                ORDER BY evaluated_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [
                RAGEvaluationListItem(
                    evaluation_id=str(row["evaluation_id"]),
                    query=row["query"][:100],
                    overall_score=row["overall_score"],
                    overall_level=RAGEvaluationLevel(row["overall_level"]),
                    issues_count=len(json.loads(row["issues"]) if row["issues"] else []),
                    evaluated_at=row["evaluated_at"],
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"[RAGEvalRepo] Failed to list evaluations: {e}")
            return []

    async def get_stats(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> RAGEvaluationStats:
        """평가 통계 조회"""
        try:
            conditions = []
            params = []
            param_idx = 1

            if user_id:
                conditions.append(f"user_id = ${param_idx}")
                params.append(user_id)
                param_idx += 1

            if start_date:
                conditions.append(f"evaluated_at >= ${param_idx}")
                params.append(start_date)
                param_idx += 1

            if end_date:
                conditions.append(f"evaluated_at <= ${param_idx}")
                params.append(end_date)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            async with self._pool.acquire() as conn:
                # 기본 통계
                stats_row = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(*) as total,
                        AVG(overall_score) as avg_score,
                        AVG(faithfulness_score) as avg_faithfulness,
                        AVG(context_relevance_score) as avg_context_relevance,
                        AVG(answer_relevancy_score) as avg_answer_relevancy,
                        AVG(context_precision_score) as avg_context_precision,
                        AVG(context_recall_score) as avg_context_recall
                    FROM rag_evaluations
                    {where_clause}
                    """,
                    *params
                )

                # 등급별 분포
                level_rows = await conn.fetch(
                    f"""
                    SELECT overall_level, COUNT(*) as count
                    FROM rag_evaluations
                    {where_clause}
                    GROUP BY overall_level
                    """,
                    *params
                )

                # 자주 발생하는 이슈
                issue_rows = await conn.fetch(
                    f"""
                    SELECT issue, COUNT(*) as count
                    FROM rag_evaluations,
                         LATERAL jsonb_array_elements_text(issues) as issue
                    {where_clause}
                    GROUP BY issue
                    ORDER BY count DESC
                    LIMIT 10
                    """,
                    *params
                )

            level_distribution = {
                RAGEvaluationLevel.EXCELLENT: 0,
                RAGEvaluationLevel.GOOD: 0,
                RAGEvaluationLevel.FAIR: 0,
                RAGEvaluationLevel.POOR: 0,
            }
            for row in level_rows:
                level = RAGEvaluationLevel(row["overall_level"])
                level_distribution[level] = row["count"]

            common_issues = [
                {"issue": row["issue"], "count": row["count"]}
                for row in issue_rows
            ]

            return RAGEvaluationStats(
                total_evaluations=stats_row["total"] or 0,
                avg_overall_score=round(stats_row["avg_score"] or 0, 3),
                avg_metrics={
                    "faithfulness": round(stats_row["avg_faithfulness"] or 0, 3),
                    "context_relevance": round(stats_row["avg_context_relevance"] or 0, 3),
                    "answer_relevancy": round(stats_row["avg_answer_relevancy"] or 0, 3),
                    "context_precision": round(stats_row["avg_context_precision"] or 0, 3),
                    "context_recall": round(stats_row["avg_context_recall"] or 0, 3),
                },
                level_distribution=level_distribution,
                common_issues=common_issues,
            )

        except Exception as e:
            logger.error(f"[RAGEvalRepo] Failed to get stats: {e}")
            return RAGEvaluationStats(
                total_evaluations=0,
                avg_overall_score=0.0,
                avg_metrics={},
                level_distribution={},
                common_issues=[],
            )

    def _row_to_result(self, row: asyncpg.Record) -> RAGEvaluationResult:
        """DB row to RAGEvaluationResult"""
        metric_details = json.loads(row["metric_details"]) if row["metric_details"] else {}

        metrics = {}
        for metric_name, detail in metric_details.items():
            metric_type = RAGMetricType(metric_name)
            from ..models.rag_evaluation import EvaluationMethod
            metrics[metric_type] = MetricResult(
                metric_type=metric_type,
                score=detail["score"],
                method=EvaluationMethod(detail["method"]),
                weight=detail["weight"],
                explanation=detail["explanation"],
                details=detail.get("details"),
            )

        return RAGEvaluationResult(
            evaluation_id=str(row["evaluation_id"]),
            trace_id=str(row["trace_id"]) if row["trace_id"] else None,
            conversation_id=str(row["conversation_id"]) if row["conversation_id"] else None,
            query=row["query"],
            answer=row["answer"],
            sources_count=row["sources_count"],
            metrics=metrics,
            overall_score=row["overall_score"],
            overall_level=RAGEvaluationLevel(row["overall_level"]),
            issues=json.loads(row["issues"]) if row["issues"] else [],
            recommendations=json.loads(row["recommendations"]) if row["recommendations"] else [],
            evaluation_time_ms=row["evaluation_time_ms"],
            evaluated_at=row["evaluated_at"],
        )


# Singleton instance
_rag_evaluation_repository: Optional[RAGEvaluationRepository] = None


def get_rag_evaluation_repository() -> Optional[RAGEvaluationRepository]:
    """Get RAG evaluation repository singleton"""
    return _rag_evaluation_repository


def set_rag_evaluation_repository(repository: RAGEvaluationRepository) -> None:
    """Set RAG evaluation repository (for dependency injection)"""
    global _rag_evaluation_repository
    _rag_evaluation_repository = repository
