"""
Agent and Tool Registry
Centralized registry for managing agents and tools.
"""
from typing import Dict, List, Optional, Type
import logging

from .types import AgentType, ToolDefinition
from .base import BaseAgent
from .tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for agent tools.
    Singleton pattern with lazy initialization.
    """

    _instance: Optional['ToolRegistry'] = None
    _initialized: bool = False

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self):
        """Register default tools"""
        from .tools import (
            VectorSearchTool, GraphQueryTool, IMSSearchTool,
            DocumentReadTool, WebFetchTool, SafeBashTool
        )

        default_tools = [
            VectorSearchTool(),
            GraphQueryTool(),
            IMSSearchTool(),
            DocumentReadTool(),
            WebFetchTool(),
            SafeBashTool(),
        ]

        for tool in default_tools:
            self.register(tool)

        logger.info(f"Registered {len(default_tools)} default tools")

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_names(self) -> List[str]:
        """Get all tool names"""
        return list(self._tools.keys())

    def get_definitions(self, tool_names: Optional[List[str]] = None) -> List[ToolDefinition]:
        """Get tool definitions for LLM function calling"""
        if tool_names is None:
            tools = self._tools.values()
        else:
            tools = [self._tools[name] for name in tool_names if name in self._tools]

        return [tool.get_definition() for tool in tools]

    def get_tools_for_agent(self, agent_type: AgentType) -> List[BaseTool]:
        """Get tools available for a specific agent type"""
        # Default tool assignments per agent type
        agent_tools = {
            AgentType.RAG: ["vector_search", "graph_query", "document_read"],
            AgentType.IMS: ["ims_search", "web_fetch", "vector_search"],
            AgentType.VISION: ["document_read", "vector_search"],
            AgentType.CODE: ["document_read", "bash", "vector_search"],
            AgentType.PLANNER: ["vector_search", "graph_query", "ims_search", "document_read"],
        }

        tool_names = agent_tools.get(agent_type, [])
        return [self._tools[name] for name in tool_names if name in self._tools]


class AgentRegistry:
    """
    Registry for agents.
    Singleton pattern with lazy initialization.
    """

    _instance: Optional['AgentRegistry'] = None
    _initialized: bool = False

    def __init__(self):
        self._agents: Dict[AgentType, BaseAgent] = {}
        self._agent_classes: Dict[AgentType, Type[BaseAgent]] = {}

    @classmethod
    def get_instance(cls) -> 'AgentRegistry':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_agents()
        return cls._instance

    def _register_default_agents(self):
        """Register default agents"""
        # Lazy import to avoid circular dependencies
        from .agents import (
            RAGAgent, IMSAgent, VisionAgent, CodeAgent, PlannerAgent
        )

        self._agent_classes = {
            AgentType.RAG: RAGAgent,
            AgentType.IMS: IMSAgent,
            AgentType.VISION: VisionAgent,
            AgentType.CODE: CodeAgent,
            AgentType.PLANNER: PlannerAgent,
        }

        logger.info(f"Registered {len(self._agent_classes)} agent types")

    def register_class(self, agent_type: AgentType, agent_class: Type[BaseAgent]) -> None:
        """Register an agent class"""
        self._agent_classes[agent_type] = agent_class
        logger.debug(f"Registered agent class: {agent_type.value}")

    def get(self, agent_type: AgentType) -> BaseAgent:
        """Get or create an agent instance"""
        if agent_type not in self._agents:
            agent_class = self._agent_classes.get(agent_type)
            if agent_class is None:
                raise ValueError(f"No agent registered for type: {agent_type}")
            self._agents[agent_type] = agent_class()

        return self._agents[agent_type]

    def get_class(self, agent_type: AgentType) -> Optional[Type[BaseAgent]]:
        """Get an agent class"""
        return self._agent_classes.get(agent_type)

    def get_all_types(self) -> List[AgentType]:
        """Get all registered agent types"""
        return list(self._agent_classes.keys())

    def create_new(self, agent_type: AgentType, **kwargs) -> BaseAgent:
        """Create a new agent instance (not cached)"""
        agent_class = self._agent_classes.get(agent_type)
        if agent_class is None:
            raise ValueError(f"No agent registered for type: {agent_type}")
        return agent_class(**kwargs)


# Convenience functions
def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry"""
    return ToolRegistry.get_instance()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry"""
    return AgentRegistry.get_instance()
