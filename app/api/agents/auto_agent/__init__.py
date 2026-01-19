"""
Auto Agent Module

Enterprise-grade AI orchestration system implementing a Meta-Agent (Auto Agent)
that coordinates multiple sub-agents with mandatory Planner and Verifier agents,
comprehensive memory integration, and advanced failure handling.

Architecture:
    User Prompt → AutoAgentOrchestrator
        ↓
    Memory Manager → Load context
        ↓
    Planner Agent → Create ExecutionPlan (MANDATORY)
        ↓
    Parallel Executor → Execute sub-agents
        ↓
    Verifier Agent → Validate results (MANDATORY)
        ↓
    Answer Composer → Strip reasoning, format response
        ↓
    Final Response with Next Actions
"""

from .types import (
    # Enums
    VerificationDecision,
    IssueType,
    IssueSeverity,
    PlanStatus,

    # Retry Config
    EnhancedRetryConfig,

    # Plan Types
    PlannedTask,
    PlannedTaskModel,
    ExecutionPlan,
    ExecutionPlanModel,

    # Verification Types
    Issue,
    VerificationResult,
    VerificationResultModel,

    # Memory Types
    UserMemory,
    SystemMemory,
    ConversationMemory,
    AutoAgentMemoryContext,

    # Answer Types
    ComposedAnswer,

    # Streaming
    AutoAgentStreamChunk,

    # Result
    AutoAgentExecutionResult,
)

from .orchestrator import AutoAgentOrchestrator, get_auto_agent_orchestrator
from .planner_agent import AutoPlannerAgent, get_auto_planner_agent
from .verifier_agent import VerifierAgent, get_verifier_agent
from .answer_composer import AnswerComposer, get_answer_composer
from .memory_manager import AutoAgentMemoryManager, get_memory_manager
from .confidence_scorer import ConfidenceScorer, get_confidence_scorer

__all__ = [
    # Enums
    "VerificationDecision",
    "IssueType",
    "IssueSeverity",
    "PlanStatus",

    # Retry Config
    "EnhancedRetryConfig",

    # Plan Types
    "PlannedTask",
    "PlannedTaskModel",
    "ExecutionPlan",
    "ExecutionPlanModel",

    # Verification Types
    "Issue",
    "VerificationResult",
    "VerificationResultModel",

    # Memory Types
    "UserMemory",
    "SystemMemory",
    "ConversationMemory",
    "AutoAgentMemoryContext",

    # Answer Types
    "ComposedAnswer",

    # Streaming
    "AutoAgentStreamChunk",

    # Result
    "AutoAgentExecutionResult",

    # Components
    "AutoAgentOrchestrator",
    "get_auto_agent_orchestrator",
    "AutoPlannerAgent",
    "get_auto_planner_agent",
    "VerifierAgent",
    "get_verifier_agent",
    "AnswerComposer",
    "get_answer_composer",
    "AutoAgentMemoryManager",
    "get_memory_manager",
    "ConfidenceScorer",
    "get_confidence_scorer",
]
