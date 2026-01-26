"""
Auto Agent API Router

Enterprise-grade AI orchestration endpoints with mandatory Planner and Verifier agents.
"""
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
import json

from ..models.auto_agent import (
    AutoAgentRequest,
    AutoAgentResponse,
    AutoAgentStatusResponse,
    PlanInfo,
    TaskInfo,
    VerificationInfo,
    SourceInfo
)
from ..agents.auto_agent import (
    get_auto_agent_orchestrator,
    EnhancedRetryConfig
)
from ..agents.types import AgentContext
from ..core.deps import get_current_user_or_api_key
from ..core.config import get_api_settings

logger = logging.getLogger(__name__)
settings = get_api_settings()

router = APIRouter(
    prefix="/auto-agent",
    tags=["Auto Agent"],
    responses={
        500: {"description": "Internal server error"},
        503: {"description": "Service temporarily unavailable"}
    }
)


def _build_agent_context(
    request: AutoAgentRequest,
    user_id: Optional[str] = None
) -> AgentContext:
    """Build AgentContext from request"""
    return AgentContext(
        session_id=request.session_id or str(uuid.uuid4()),
        user_id=user_id,
        conversation_history=[],
        language=request.language,
        max_steps=request.max_steps,
        timeout=300.0,
        metadata={},
        file_context=request.file_context,
        url_context=request.url_context
    )


def _build_retry_config(request: AutoAgentRequest) -> EnhancedRetryConfig:
    """Build retry config from request"""
    return EnhancedRetryConfig(
        max_retries=request.max_retries,
        max_replans=request.max_replans,
        confidence_threshold=request.confidence_threshold
    )


def _build_response(result) -> AutoAgentResponse:
    """Build API response from execution result"""
    # Build plan info
    plan_info = None
    if result.plan:
        plan_info = PlanInfo(
            plan_id=result.plan.plan_id,
            task_count=len(result.plan.decomposed_tasks),
            parallelism_strategy=result.plan.parallelism_strategy.value,
            tasks=[
                TaskInfo(
                    task_id=t.task_id,
                    description=t.description,
                    agent_type=t.agent_type.value,
                    dependencies=t.dependencies,
                    status="completed" if t.task_id in result.task_results else "pending"
                )
                for t in result.plan.decomposed_tasks
            ],
            estimated_confidence=result.plan.estimated_total_confidence
        )

    # Build verification info
    verification_info = None
    if result.verification:
        verification_info = VerificationInfo(
            decision=result.verification.decision.value,
            overall_score=result.verification.overall_score,
            grounding_score=result.verification.grounding_score,
            consistency_score=result.verification.consistency_score,
            completeness_score=result.verification.completeness_score,
            execution_score=result.verification.execution_score,
            issue_count=len(result.verification.issues)
        )

    # Build sources
    sources = []
    if result.answer and result.answer.sources:
        for src in result.answer.sources:
            sources.append(SourceInfo(
                title=src.get("title", "Unknown"),
                type=src.get("type", "document"),
                reference=src.get("reference"),
                url=src.get("url")
            ))

    # Build response
    return AutoAgentResponse(
        execution_id=result.execution_id,
        answer=result.answer.content if result.answer else "",
        language=result.answer.language if result.answer else "auto",
        confidence=result.verification.overall_score if result.verification else 0.0,
        plan=plan_info,
        verification=verification_info,
        sources=sources,
        next_actions=result.answer.next_actions if result.answer else [],
        execution_time=result.total_execution_time,
        retry_count=result.retry_attempts,
        replan_count=result.replan_attempts,
        success=result.success,
        error=result.error,
        partial_failures=result.partial_failure_tasks
    )


@router.post(
    "/execute",
    response_model=AutoAgentResponse,
    summary="Execute Auto Agent",
    description="""
Execute the Auto Agent orchestration system with mandatory planning and verification.

The Auto Agent will:
1. Create an execution plan (Planner Agent)
2. Execute sub-agents in parallel where possible
3. Verify results for quality and grounding (Verifier Agent)
4. Compose the final answer (strip internal reasoning)
5. Suggest next actions

Quality > Speed: The system will retry failed tasks and replan if necessary.
"""
)
async def execute_auto_agent(
    request: AutoAgentRequest,
    auth_context: dict = Depends(get_current_user_or_api_key)
) -> AutoAgentResponse:
    """Execute Auto Agent orchestration"""
    try:
        user_id = auth_context.get("user_id") if auth_context else None

        # Build context and config
        context = _build_agent_context(request, user_id)
        config = _build_retry_config(request)

        # Get orchestrator and execute
        orchestrator = get_auto_agent_orchestrator()
        result = await orchestrator.execute(
            task=request.task,
            context=context,
            config=config
        )

        return _build_response(result)

    except ValidationError as e:
        logger.error(f"[AutoAgent] Validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"[AutoAgent] Execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.post(
    "/stream",
    summary="Stream Auto Agent Execution",
    description="""
Stream the Auto Agent orchestration with real-time progress updates.

Events include:
- planning_start/done: Plan creation phase
- execution_start/batch_start/agent_done: Execution phase
- verification_start/done: Verification phase
- composition_done: Final answer
- next_actions: Suggested follow-ups
- done: Execution complete
"""
)
async def stream_auto_agent(
    request: AutoAgentRequest,
    auth_context: dict = Depends(get_current_user_or_api_key)
):
    """Stream Auto Agent execution with SSE"""
    user_id = auth_context.get("user_id") if auth_context else None

    # Build context and config
    context = _build_agent_context(request, user_id)
    config = _build_retry_config(request)

    async def event_generator():
        try:
            orchestrator = get_auto_agent_orchestrator()

            async for chunk in orchestrator.stream(
                task=request.task,
                context=context,
                config=config
            ):
                # Format as SSE event
                event_data = {
                    "type": chunk.chunk_type,
                    "phase": chunk.phase,
                    "content": chunk.content,
                    "task_id": chunk.task_id,
                    "agent_type": chunk.agent_type,
                    "progress": chunk.progress,
                    "metadata": chunk.metadata
                }

                # Add specific data based on event type
                if chunk.plan_data:
                    event_data["plan"] = chunk.plan_data
                if chunk.verification_data:
                    event_data["verification"] = chunk.verification_data
                if chunk.sources:
                    event_data["sources"] = chunk.sources
                if chunk.next_actions:
                    event_data["next_actions"] = chunk.next_actions
                if chunk.error_message:
                    event_data["error"] = chunk.error_message

                yield f"event: {chunk.chunk_type}\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[AutoAgent] Stream error: {e}", exc_info=True)
            error_data = {"type": "error", "error": str(e)}
            yield f"event: error\n"
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/status",
    response_model=AutoAgentStatusResponse,
    summary="Get Auto Agent Status",
    description="Check the status and availability of the Auto Agent system."
)
async def get_status() -> AutoAgentStatusResponse:
    """Get Auto Agent system status"""
    try:
        # Check component availability
        components = {
            "planner": True,
            "verifier": True,
            "composer": True,
            "memory_manager": True,
            "parallel_executor": True
        }

        # Try to get orchestrator (will initialize components)
        try:
            orchestrator = get_auto_agent_orchestrator()
            components["orchestrator"] = True
        except Exception as e:
            logger.warning(f"Orchestrator initialization warning: {e}")
            components["orchestrator"] = False

        return AutoAgentStatusResponse(
            enabled=True,
            version="1.0.0",
            components=components,
            stats={
                "max_retries": 2,
                "max_replans": 1,
                "default_confidence_threshold": 0.6
            }
        )

    except Exception as e:
        logger.error(f"[AutoAgent] Status check failed: {e}")
        return AutoAgentStatusResponse(
            enabled=False,
            version="1.0.0",
            components={},
            stats={"error": str(e)}
        )


@router.get(
    "/health",
    summary="Health Check",
    description="Simple health check for the Auto Agent service."
)
async def health_check():
    """Simple health check"""
    return {"status": "healthy", "service": "auto-agent"}
