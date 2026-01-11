"""
Agent Execution Trace Repository

PostgreSQL repository for agent execution traces, spans, tool calls, and evaluations.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
import json

from asyncpg import Pool

from ...models.agent_trace import (
    AgentExecutionTrace,
    AgentTraceSpan,
    AgentToolCall,
    AgentEvaluation,
    AgentTraceDetail,
    AgentTraceListItem,
    AgentTraceStatus,
    SpanStatus,
    ToolCallStatus,
    DAGStructure,
    DAGTask,
)

logger = logging.getLogger(__name__)


class AgentTraceRepository:
    """Repository for agent execution trace persistence."""

    def __init__(self, pool: Pool):
        self.pool = pool

    # ========================================================================
    # Trace Operations
    # ========================================================================

    async def create_trace(
        self,
        trace: AgentExecutionTrace,
    ) -> UUID:
        """Create a new agent execution trace."""
        async with self.pool.acquire() as conn:
            dag_json = None
            if trace.dag_structure:
                dag_json = json.dumps(trace.dag_structure.model_dump())

            await conn.execute(
                """
                INSERT INTO agent_execution_traces (
                    trace_id, user_id, session_id, conversation_id,
                    agent_type, is_enterprise, task_description,
                    dag_structure, start_time, status, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                trace.trace_id,
                trace.user_id,
                trace.session_id,
                trace.conversation_id,
                trace.agent_type,
                trace.is_enterprise,
                trace.task_description[:5000],  # Truncate for storage
                dag_json,
                trace.start_time,
                trace.status.value,
                json.dumps(trace.metadata),
            )

            logger.info(f"[AgentTraceRepo] Created trace: {trace.trace_id}")
            return trace.trace_id

    async def update_trace_status(
        self,
        trace_id: UUID,
        status: AgentTraceStatus,
        end_time: Optional[datetime] = None,
        total_latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        final_answer: Optional[str] = None,
        total_steps: Optional[int] = None,
        successful_steps: Optional[int] = None,
        failed_steps: Optional[int] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """Update trace status and metrics."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_execution_traces
                SET status = $2,
                    end_time = COALESCE($3, end_time),
                    total_latency_ms = COALESCE($4, total_latency_ms),
                    error_message = COALESCE($5, error_message),
                    final_answer = COALESCE($6, final_answer),
                    total_steps = COALESCE($7, total_steps),
                    successful_steps = COALESCE($8, successful_steps),
                    failed_steps = COALESCE($9, failed_steps),
                    retry_count = COALESCE($10, retry_count),
                    updated_at = CURRENT_TIMESTAMP
                WHERE trace_id = $1
                """,
                trace_id,
                status.value,
                end_time,
                total_latency_ms,
                error_message,
                final_answer[:10000] if final_answer else None,
                total_steps,
                successful_steps,
                failed_steps,
                retry_count,
            )

    async def update_dag_structure(
        self,
        trace_id: UUID,
        dag_structure: DAGStructure,
    ) -> None:
        """Update DAG structure for a trace."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_execution_traces
                SET dag_structure = $2, updated_at = CURRENT_TIMESTAMP
                WHERE trace_id = $1
                """,
                trace_id,
                json.dumps(dag_structure.model_dump()),
            )

    async def get_trace_by_id(self, trace_id: UUID) -> Optional[AgentTraceDetail]:
        """Get full trace with spans, tool calls, and evaluations."""
        async with self.pool.acquire() as conn:
            # Get trace
            row = await conn.fetchrow(
                """
                SELECT * FROM agent_execution_traces WHERE trace_id = $1
                """,
                trace_id,
            )
            if not row:
                return None

            # Get spans
            span_rows = await conn.fetch(
                """
                SELECT * FROM agent_trace_spans
                WHERE trace_id = $1
                ORDER BY start_time
                """,
                trace_id,
            )

            # Get tool calls
            tool_rows = await conn.fetch(
                """
                SELECT * FROM agent_tool_calls
                WHERE trace_id = $1
                ORDER BY start_time
                """,
                trace_id,
            )

            # Get evaluations
            eval_rows = await conn.fetch(
                """
                SELECT * FROM agent_evaluations
                WHERE trace_id = $1
                ORDER BY created_at
                """,
                trace_id,
            )

            return self._row_to_trace_detail(row, span_rows, tool_rows, eval_rows)

    async def list_traces(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        conversation_id: Optional[UUID] = None,
        status: Optional[AgentTraceStatus] = None,
        is_enterprise: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AgentTraceListItem]:
        """List traces with filtering."""
        async with self.pool.acquire() as conn:
            conditions = ["user_id = $1"]
            params: List[Any] = [user_id]
            param_idx = 2

            if agent_type:
                conditions.append(f"agent_type = ${param_idx}")
                params.append(agent_type)
                param_idx += 1

            if conversation_id:
                conditions.append(f"conversation_id = ${param_idx}")
                params.append(conversation_id)
                param_idx += 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1

            if is_enterprise is not None:
                conditions.append(f"is_enterprise = ${param_idx}")
                params.append(is_enterprise)
                param_idx += 1

            where_clause = " AND ".join(conditions)
            params.extend([limit, skip])

            rows = await conn.fetch(
                f"""
                SELECT trace_id, agent_type, is_enterprise, task_description,
                       status, total_latency_ms, total_steps, failed_steps, created_at
                FROM agent_execution_traces
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                *params,
            )

            return [
                AgentTraceListItem(
                    trace_id=row["trace_id"],
                    agent_type=row["agent_type"],
                    is_enterprise=row["is_enterprise"],
                    task_description=row["task_description"][:200],
                    status=AgentTraceStatus(row["status"]),
                    total_latency_ms=row["total_latency_ms"],
                    total_steps=row["total_steps"],
                    failed_steps=row["failed_steps"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # ========================================================================
    # Span Operations
    # ========================================================================

    async def add_span(self, span: AgentTraceSpan) -> UUID:
        """Add a span to a trace."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_trace_spans (
                    span_id, trace_id, parent_span_id, task_id,
                    span_name, span_type, agent_type,
                    start_time, end_time, latency_ms,
                    status, error_message, depth, execution_order, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                span.span_id,
                span.trace_id,
                span.parent_span_id,
                span.task_id,
                span.span_name[:200],
                span.span_type.value,
                span.agent_type,
                span.start_time,
                span.end_time,
                span.latency_ms,
                span.status.value,
                span.error_message,
                span.depth,
                span.execution_order,
                json.dumps(span.metadata),
            )

            return span.span_id

    async def update_span_status(
        self,
        span_id: UUID,
        status: SpanStatus,
        end_time: Optional[datetime] = None,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update span status."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_trace_spans
                SET status = $2,
                    end_time = COALESCE($3, end_time),
                    latency_ms = COALESCE($4, latency_ms),
                    error_message = COALESCE($5, error_message)
                WHERE span_id = $1
                """,
                span_id,
                status.value,
                end_time,
                latency_ms,
                error_message,
            )

    async def get_spans_by_trace(self, trace_id: UUID) -> List[AgentTraceSpan]:
        """Get all spans for a trace."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM agent_trace_spans
                WHERE trace_id = $1
                ORDER BY start_time
                """,
                trace_id,
            )
            return [self._row_to_span(row) for row in rows]

    # ========================================================================
    # Tool Call Operations
    # ========================================================================

    async def add_tool_call(self, tool_call: AgentToolCall) -> UUID:
        """Add a tool call record."""
        async with self.pool.acquire() as conn:
            # Truncate large input/output
            input_json = self._truncate_json(tool_call.input_args, max_size=10000)
            output_json = self._truncate_json(tool_call.output_result, max_size=50000)

            await conn.execute(
                """
                INSERT INTO agent_tool_calls (
                    tool_call_id, span_id, trace_id, tool_name,
                    input_args, output_result, status, error_message,
                    start_time, end_time, latency_ms
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                tool_call.tool_call_id,
                tool_call.span_id,
                tool_call.trace_id,
                tool_call.tool_name,
                input_json,
                output_json,
                tool_call.status.value,
                tool_call.error_message,
                tool_call.start_time,
                tool_call.end_time,
                tool_call.latency_ms,
            )

            return tool_call.tool_call_id

    async def update_tool_call_status(
        self,
        tool_call_id: UUID,
        status: ToolCallStatus,
        output_result: Optional[Dict[str, Any]] = None,
        end_time: Optional[datetime] = None,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update tool call status and result."""
        async with self.pool.acquire() as conn:
            output_json = self._truncate_json(output_result, max_size=50000)

            await conn.execute(
                """
                UPDATE agent_tool_calls
                SET status = $2,
                    output_result = COALESCE($3, output_result),
                    end_time = COALESCE($4, end_time),
                    latency_ms = COALESCE($5, latency_ms),
                    error_message = COALESCE($6, error_message)
                WHERE tool_call_id = $1
                """,
                tool_call_id,
                status.value,
                output_json,
                end_time,
                latency_ms,
                error_message,
            )

    # ========================================================================
    # Evaluation Operations
    # ========================================================================

    async def add_evaluation(self, evaluation: AgentEvaluation) -> UUID:
        """Add an evaluation record."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_evaluations (
                    eval_id, span_id, trace_id, task_id,
                    passed, score, criteria, issues,
                    retry_recommended, retry_reason
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                evaluation.eval_id,
                evaluation.span_id,
                evaluation.trace_id,
                evaluation.task_id,
                evaluation.passed,
                evaluation.score,
                json.dumps(evaluation.criteria.model_dump()),
                json.dumps(evaluation.issues),
                evaluation.retry_recommended,
                evaluation.retry_reason,
            )

            return evaluation.eval_id

    # ========================================================================
    # DAG Task Status Updates
    # ========================================================================

    async def update_dag_task_status(
        self,
        trace_id: UUID,
        task_id: str,
        status: SpanStatus,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update a task's status in the DAG structure."""
        async with self.pool.acquire() as conn:
            # Get current DAG
            row = await conn.fetchrow(
                "SELECT dag_structure FROM agent_execution_traces WHERE trace_id = $1",
                trace_id,
            )
            if not row or not row["dag_structure"]:
                return

            dag_data = json.loads(row["dag_structure"])

            # Update task status
            for task in dag_data.get("tasks", []):
                if task.get("task_id") == task_id:
                    task["status"] = status.value
                    if start_time:
                        task["start_time"] = start_time.isoformat()
                    if end_time:
                        task["end_time"] = end_time.isoformat()
                    if latency_ms is not None:
                        task["latency_ms"] = latency_ms
                    if error:
                        task["error"] = error
                    break

            # Save updated DAG
            await conn.execute(
                """
                UPDATE agent_execution_traces
                SET dag_structure = $2, updated_at = CURRENT_TIMESTAMP
                WHERE trace_id = $1
                """,
                trace_id,
                json.dumps(dag_data),
            )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _truncate_json(
        self,
        data: Optional[Dict[str, Any]],
        max_size: int = 10000,
    ) -> Optional[str]:
        """Truncate JSON data to fit storage limits."""
        if data is None:
            return None

        json_str = json.dumps(data, ensure_ascii=False, default=str)
        if len(json_str) > max_size:
            return json_str[:max_size - 50] + '..."truncated"}'
        return json_str

    def _row_to_span(self, row) -> AgentTraceSpan:
        """Convert database row to AgentTraceSpan."""
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AgentTraceSpan(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            parent_span_id=row["parent_span_id"],
            task_id=row["task_id"],
            span_name=row["span_name"],
            span_type=row["span_type"],
            agent_type=row["agent_type"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            latency_ms=row["latency_ms"],
            status=SpanStatus(row["status"]),
            error_message=row["error_message"],
            depth=row["depth"],
            execution_order=row["execution_order"],
            metadata=metadata or {},
            created_at=row["created_at"],
        )

    def _row_to_tool_call(self, row) -> AgentToolCall:
        """Convert database row to AgentToolCall."""
        input_args = row["input_args"]
        if isinstance(input_args, str):
            input_args = json.loads(input_args)

        output_result = row["output_result"]
        if isinstance(output_result, str):
            output_result = json.loads(output_result)

        return AgentToolCall(
            tool_call_id=row["tool_call_id"],
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            tool_name=row["tool_name"],
            input_args=input_args or {},
            output_result=output_result,
            status=ToolCallStatus(row["status"]),
            error_message=row["error_message"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            latency_ms=row["latency_ms"],
            created_at=row["created_at"],
        )

    def _row_to_evaluation(self, row) -> AgentEvaluation:
        """Convert database row to AgentEvaluation."""
        from ...models.agent_trace import EvaluationCriteriaModel

        criteria = row["criteria"]
        if isinstance(criteria, str):
            criteria = json.loads(criteria)

        issues = row["issues"]
        if isinstance(issues, str):
            issues = json.loads(issues)

        return AgentEvaluation(
            eval_id=row["eval_id"],
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            task_id=row["task_id"],
            passed=row["passed"],
            score=row["score"],
            criteria=EvaluationCriteriaModel(**criteria) if criteria else EvaluationCriteriaModel(),
            issues=issues or [],
            retry_recommended=row["retry_recommended"],
            retry_reason=row["retry_reason"],
            created_at=row["created_at"],
        )

    def _row_to_trace_detail(
        self,
        trace_row,
        span_rows,
        tool_rows,
        eval_rows,
    ) -> AgentTraceDetail:
        """Convert database rows to AgentTraceDetail."""
        dag_structure = None
        if trace_row["dag_structure"]:
            dag_data = trace_row["dag_structure"]
            if isinstance(dag_data, str):
                dag_data = json.loads(dag_data)
            dag_structure = DAGStructure(
                tasks=[DAGTask(**t) for t in dag_data.get("tasks", [])],
                execution_batches=dag_data.get("execution_batches", []),
                parallelism_type=dag_data.get("parallelism_type", "none"),
            )

        metadata = trace_row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AgentTraceDetail(
            trace_id=trace_row["trace_id"],
            user_id=trace_row["user_id"],
            session_id=trace_row["session_id"],
            conversation_id=trace_row["conversation_id"],
            agent_type=trace_row["agent_type"],
            is_enterprise=trace_row["is_enterprise"],
            task_description=trace_row["task_description"],
            dag_structure=dag_structure,
            start_time=trace_row["start_time"],
            end_time=trace_row["end_time"],
            total_latency_ms=trace_row["total_latency_ms"],
            status=AgentTraceStatus(trace_row["status"]),
            error_message=trace_row["error_message"],
            total_steps=trace_row["total_steps"],
            successful_steps=trace_row["successful_steps"],
            failed_steps=trace_row["failed_steps"],
            retry_count=trace_row["retry_count"],
            final_answer=trace_row["final_answer"],
            spans=[self._row_to_span(r) for r in span_rows],
            tool_calls=[self._row_to_tool_call(r) for r in tool_rows],
            evaluations=[self._row_to_evaluation(r) for r in eval_rows],
            metadata=metadata or {},
            created_at=trace_row["created_at"],
            updated_at=trace_row["updated_at"],
        )


# Singleton
_agent_trace_repo_instance: Optional[AgentTraceRepository] = None


def get_agent_trace_repository(pool: Optional[Pool] = None) -> AgentTraceRepository:
    """Get or create the agent trace repository singleton."""
    global _agent_trace_repo_instance
    if _agent_trace_repo_instance is None:
        if pool is None:
            raise ValueError("Pool required for first initialization")
        _agent_trace_repo_instance = AgentTraceRepository(pool)
    return _agent_trace_repo_instance


def initialize_agent_trace_repository(pool: Pool) -> AgentTraceRepository:
    """Initialize the agent trace repository with a pool."""
    global _agent_trace_repo_instance
    _agent_trace_repo_instance = AgentTraceRepository(pool)
    return _agent_trace_repo_instance
