"""
Agent System Package
Provides AI agents with tool-calling capabilities for the HybridRAG KMS.

Main components:
- BaseAgent: Abstract base class for all agents
- AgentExecutor: ReAct loop implementation
- AgentOrchestrator: Agent selection and execution management
- Tools: Vector search, graph query, IMS search, etc.
- Specialized agents: RAG, IMS, Vision, Code, Planner
"""
from .types import (
    AgentType,
    AgentContext,
    AgentResult,
    AgentRequest,
    AgentResponse,
    AgentStreamChunk,
    ToolCall,
    ToolResult,
)
from .base import BaseAgent, SimpleAgent
from .executor import AgentExecutor, get_executor
from .orchestrator import AgentOrchestrator, get_orchestrator
from .registry import (
    ToolRegistry,
    AgentRegistry,
    get_tool_registry,
    get_agent_registry,
)
from .permissions import PermissionManager, get_permission_manager
from .master_system_constraint import (
    get_master_constraint,
    build_constrained_system_prompt,
    validate_constraint_present,
    validate_constraint_integrity,
    log_compliance_violation,
    get_constraint_enforcer,
    MasterConstraintEnforcer,
    ConstraintViolationError,
    ComplianceViolationType,
    MASTER_SYSTEM_CONSTRAINT,
)

# Import specialized agents
from .agents import (
    RAGAgent,
    IMSAgent,
    VisionAgent,
    CodeAgent,
    PlannerAgent,
)

__all__ = [
    # Types
    "AgentType",
    "AgentContext",
    "AgentResult",
    "AgentRequest",
    "AgentResponse",
    "AgentStreamChunk",
    "ToolCall",
    "ToolResult",
    # Base classes
    "BaseAgent",
    "SimpleAgent",
    # Core components
    "AgentExecutor",
    "get_executor",
    "AgentOrchestrator",
    "get_orchestrator",
    # Registries
    "ToolRegistry",
    "AgentRegistry",
    "get_tool_registry",
    "get_agent_registry",
    # Permissions
    "PermissionManager",
    "get_permission_manager",
    # Specialized agents
    "RAGAgent",
    "IMSAgent",
    "VisionAgent",
    "CodeAgent",
    "PlannerAgent",
    # Master System Constraint
    "get_master_constraint",
    "build_constrained_system_prompt",
    "validate_constraint_present",
    "validate_constraint_integrity",
    "log_compliance_violation",
    "get_constraint_enforcer",
    "MasterConstraintEnforcer",
    "ConstraintViolationError",
    "ComplianceViolationType",
    "MASTER_SYSTEM_CONSTRAINT",
]
