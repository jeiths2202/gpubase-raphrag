"""
Deep Agent Integration
기존 에이전트 시스템과 Deep Agent를 통합하는 모듈

비즈니스 로직 수정 없이 Deep Agent를 기존 시스템에서 사용할 수 있도록 함
"""
import os
import logging
from typing import Optional, Dict, Any

from ..types import AgentType
from ..registry import AgentRegistry, get_agent_registry
from .deep_agent_adapter import DeepAgentAdapter, create_rag_deep_agent

logger = logging.getLogger(__name__)

# 환경 변수로 Deep Agent 사용 여부 제어
ENABLE_DEEP_AGENT = os.getenv("ENABLE_DEEP_AGENT", "false").lower() == "true"
DEEP_AGENT_TYPES = os.getenv("DEEP_AGENT_TYPES", "").split(",")  # 예: "rag,planner"


def register_deep_agent(
    agent_type: AgentType,
    registry: Optional[AgentRegistry] = None,
    **kwargs
) -> bool:
    """
    Deep Agent를 기존 AgentRegistry에 등록

    Args:
        agent_type: 등록할 에이전트 타입
        registry: AgentRegistry 인스턴스 (None이면 싱글톤 사용)
        **kwargs: DeepAgentAdapter 추가 인자

    Returns:
        등록 성공 여부
    """
    registry = registry or get_agent_registry()

    try:
        # DeepAgentAdapter를 반환하는 팩토리 클래스 생성
        class DeepAgentFactory:
            def __init__(self, **init_kwargs):
                self.kwargs = init_kwargs
                self._agent_type = agent_type

            def __call__(self, **call_kwargs):
                merged = {**self.kwargs, **call_kwargs}
                # agent_type은 별도로 처리 (create_rag_deep_agent에서는 불필요)
                merged.pop("agent_type", None)
                if self._agent_type == AgentType.RAG:
                    return create_rag_deep_agent(**merged)
                else:
                    return DeepAgentAdapter(agent_type=self._agent_type, **merged)

        # 팩토리를 에이전트 클래스로 등록
        factory = DeepAgentFactory(**kwargs)
        registry.register_class(agent_type, factory)

        logger.info(f"Registered Deep Agent for type: {agent_type.value}")
        return True

    except Exception as e:
        logger.error(f"Failed to register Deep Agent for {agent_type.value}: {e}")
        return False


def enable_deep_agents(
    agent_types: Optional[list] = None,
    registry: Optional[AgentRegistry] = None,
) -> Dict[str, bool]:
    """
    여러 에이전트 타입에 Deep Agent 활성화

    Args:
        agent_types: 활성화할 에이전트 타입 목록 (None이면 환경변수 사용)
        registry: AgentRegistry 인스턴스

    Returns:
        각 타입별 등록 성공 여부
    """
    registry = registry or get_agent_registry()

    # 환경변수에서 타입 읽기
    if agent_types is None:
        agent_types = []
        for type_str in DEEP_AGENT_TYPES:
            type_str = type_str.strip().lower()
            if type_str:
                try:
                    agent_types.append(AgentType(type_str))
                except ValueError:
                    logger.warning(f"Unknown agent type: {type_str}")

    results = {}
    for agent_type in agent_types:
        results[agent_type.value] = register_deep_agent(agent_type, registry)

    return results


def get_deep_agent(
    agent_type: AgentType,
    **kwargs
) -> DeepAgentAdapter:
    """
    Deep Agent 인스턴스 직접 생성 (레지스트리 우회)

    Args:
        agent_type: 에이전트 타입
        **kwargs: DeepAgentAdapter 추가 인자

    Returns:
        DeepAgentAdapter 인스턴스
    """
    if agent_type == AgentType.RAG:
        return create_rag_deep_agent(**kwargs)
    else:
        return DeepAgentAdapter(
            agent_type=agent_type,
            **kwargs
        )


def is_deep_agent_enabled() -> bool:
    """Deep Agent가 환경변수로 활성화되어 있는지 확인"""
    return ENABLE_DEEP_AGENT


def auto_register_deep_agents():
    """
    환경변수 설정에 따라 자동으로 Deep Agent 등록

    사용법:
        1. 환경변수 설정:
           ENABLE_DEEP_AGENT=true
           DEEP_AGENT_TYPES=rag,planner

        2. 앱 시작 시 호출:
           from app.api.agents.adapters.integration import auto_register_deep_agents
           auto_register_deep_agents()
    """
    if not ENABLE_DEEP_AGENT:
        logger.debug("Deep Agent disabled by environment variable")
        return {}

    results = enable_deep_agents()

    if results:
        logger.info(f"Auto-registered Deep Agents: {results}")
    else:
        logger.debug("No Deep Agent types configured for auto-registration")

    return results
