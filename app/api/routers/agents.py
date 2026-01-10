"""
Agent API Router
Provides endpoints for agent execution.
"""
from typing import Optional, List
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..agents import (
    AgentOrchestrator,
    get_orchestrator,
    AgentRequest,
    AgentResponse,
    AgentType,
    get_tool_registry,
    get_agent_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# Dependency for orchestrator
async def get_agent_orchestrator() -> AgentOrchestrator:
    """Get the agent orchestrator"""
    return get_orchestrator()


# Response models
class AgentInfo(BaseModel):
    """Agent information"""
    type: str
    name: str
    description: str
    tools: List[str]


class ToolInfo(BaseModel):
    """Tool information"""
    name: str
    description: str


class AgentListResponse(BaseModel):
    """Response for listing agents"""
    agents: List[AgentInfo]


class ToolListResponse(BaseModel):
    """Response for listing tools"""
    tools: List[ToolInfo]


@router.post("/execute", response_model=AgentResponse)
async def execute_agent(
    request: AgentRequest,
    current_user: dict = Depends(get_current_user),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator)
) -> AgentResponse:
    """
    Execute an agent task.

    The agent will be automatically selected based on the task,
    or you can specify a specific agent_type.

    Args:
        request: Agent execution request
        current_user: Authenticated user
        orchestrator: Agent orchestrator

    Returns:
        AgentResponse with answer and metadata
    """
    try:
        user_id = current_user.get("id") or current_user.get("sub")

        response = await orchestrator.execute(request, user_id=user_id)

        return response

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AGENT_ERROR", "message": str(e)}
        )


@router.post("/stream")
async def stream_agent(
    request: AgentRequest,
    current_user: dict = Depends(get_current_user),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator)
):
    """
    Stream agent execution using Server-Sent Events (SSE).

    Provides real-time updates as the agent thinks and acts.

    Args:
        request: Agent execution request
        current_user: Authenticated user
        orchestrator: Agent orchestrator

    Returns:
        StreamingResponse with SSE events
    """
    user_id = current_user.get("id") or current_user.get("sub")

    async def generate():
        try:
            async for chunk in orchestrator.stream(request, user_id=user_id):
                data = chunk.model_dump()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Agent streaming failed: {e}")
            yield f"data: {json.dumps({'chunk_type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/types", response_model=AgentListResponse)
async def list_agents(
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator)
) -> AgentListResponse:
    """
    List available agent types.

    Returns information about all registered agents.
    """
    agents = orchestrator.get_available_agents()
    return AgentListResponse(
        agents=[AgentInfo(**a) for a in agents]
    )


@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """
    List available tools.

    Returns information about all registered tools.
    """
    registry = get_tool_registry()
    tools = [
        ToolInfo(name=t.name, description=t.description)
        for t in registry.get_all()
    ]
    return ToolListResponse(tools=tools)


@router.post("/classify")
async def classify_task(
    task: str,
    use_llm: bool = False,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator)
) -> dict:
    """
    Classify a task to determine the appropriate agent type.

    Args:
        task: The task to classify
        use_llm: Whether to use LLM for classification (slower but more accurate)
        orchestrator: Agent orchestrator

    Returns:
        Classification result with agent type and confidence
    """
    if use_llm:
        agent_type = await orchestrator.classify_with_llm(task)
    else:
        agent_type = await orchestrator.classify_task(task)

    return {
        "task": task,
        "agent_type": agent_type.value,
        "method": "llm" if use_llm else "keyword"
    }


# Health check endpoint
@router.get("/health")
async def agent_health():
    """
    Check agent system health.

    Returns status of agent and tool registries.
    """
    try:
        tool_registry = get_tool_registry()
        agent_registry = get_agent_registry()

        return {
            "status": "healthy",
            "agents_registered": len(agent_registry.get_all_types()),
            "tools_registered": len(tool_registry.get_names())
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
