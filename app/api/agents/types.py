"""
Agent System Types and Models
Defines core types, enums, and Pydantic models for the agent system.
"""
from enum import Enum
from typing import Dict, List, Any, Optional, TypedDict, Literal, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

if TYPE_CHECKING:
    from .intent import IntentResult


class AgentType(str, Enum):
    """Types of specialized agents"""
    RAG = "rag"
    IMS = "ims"
    VISION = "vision"
    CODE = "code"
    PLANNER = "planner"


class MessageRole(str, Enum):
    """Message roles in agent conversation"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolStatus(str, Enum):
    """Tool execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class PermissionAction(str, Enum):
    """Permission actions"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# TypedDicts for internal use
class ToolResult(TypedDict):
    """Result of a tool execution"""
    success: bool
    output: str
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]


class ToolCallDict(TypedDict):
    """Tool call request"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str


# Pydantic Models for API
class ToolCall(BaseModel):
    """Tool call request model"""
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique call ID")


class AgentMessage(BaseModel):
    """Message in agent conversation"""
    role: MessageRole
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # Tool name for tool messages
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolExecutionEvent(BaseModel):
    """Event emitted during tool execution (for streaming)"""
    event_type: Literal["tool_start", "tool_progress", "tool_end", "tool_error"]
    call_id: str
    tool_name: str
    status: ToolStatus
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ThinkingEvent(BaseModel):
    """Event emitted during agent thinking (for streaming)"""
    event_type: Literal["thinking_start", "thinking_delta", "thinking_end"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentEvent(BaseModel):
    """Union event for agent streaming"""
    event_type: str
    data: Union[ToolExecutionEvent, ThinkingEvent, Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Dataclasses for internal context
@dataclass
class AgentContext:
    """Context for agent execution"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    language: str = "auto"
    max_steps: int = 10
    timeout: float = 300.0  # 5 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Session-specific data
    uploaded_documents: List[str] = field(default_factory=list)
    external_resources: Dict[str, Any] = field(default_factory=dict)

    # Intent classification result (set by orchestrator)
    intent: Optional["IntentResult"] = None


@dataclass
class AgentResult:
    """Result of agent execution"""
    answer: str
    agent_type: AgentType
    steps: int
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ToolDefinition:
    """Tool definition for LLM function calling"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    required: List[str] = field(default_factory=list)


# API Request/Response Models
class AgentRequest(BaseModel):
    """API request for agent execution"""
    task: str = Field(..., description="Task or question for the agent")
    agent_type: Optional[AgentType] = Field(None, description="Specific agent type (auto-selected if not provided)")
    session_id: Optional[str] = Field(None, description="Session ID for context continuity")
    language: str = Field("auto", description="Response language (auto, en, ko, ja)")
    max_steps: int = Field(10, ge=1, le=50, description="Maximum reasoning steps")
    include_sources: bool = Field(True, description="Include sources in response")
    stream: bool = Field(False, description="Enable streaming response")


class AgentResponse(BaseModel):
    """API response from agent execution"""
    answer: str
    agent_type: AgentType
    session_id: str
    steps: int
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time: float
    success: bool = True
    error: Optional[str] = None


class ArtifactType(str, Enum):
    """Types of artifacts that can be extracted from agent responses"""
    CODE = "code"
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    DIFF = "diff"
    LOG = "log"


class AgentStreamChunk(BaseModel):
    """Streaming chunk from agent execution"""
    chunk_type: Literal["thinking", "tool_call", "tool_result", "text", "sources", "done", "error", "status", "artifact"]
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    # Artifact-specific fields
    artifact_id: Optional[str] = None
    artifact_type: Optional[str] = None  # code, text, markdown, html, json, diff, log
    artifact_title: Optional[str] = None
    artifact_language: Optional[str] = None  # python, javascript, typescript, etc.


# Permission Models
@dataclass
class PermissionRule:
    """Permission rule for tool access"""
    tool: str  # Tool name or "*" for all
    pattern: str  # Resource pattern (e.g., "*.py", "/api/*")
    action: PermissionAction
    description: Optional[str] = None


@dataclass
class AgentPermissions:
    """Permissions for an agent"""
    agent_type: AgentType
    rules: List[PermissionRule] = field(default_factory=list)
    default_action: PermissionAction = PermissionAction.DENY
