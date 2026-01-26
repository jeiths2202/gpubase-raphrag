"""
Workspace State Persistence Models

Pydantic models for persistent AI workspace system.
Supports multi-menu state management with JSONB flexibility.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo


# ============================================================================
# ENUMS AND TYPES
# ============================================================================

MenuType = Literal[
    "chat",
    "documents",
    "web_sources",
    "notes",
    "ai_content",
    "projects",
    "mindmap",
    "knowledge_graph",
    "knowledge_base"
]

GraphType = Literal["mindmap", "knowledge_graph"]

MessageRole = Literal["user", "assistant", "system"]

RetrievalStrategy = Literal["vector", "graph", "hybrid", "code"]


# ============================================================================
# CONVERSATION MODELS
# ============================================================================

class ConversationBase(BaseModel):
    """Base conversation model"""
    title: str = "New Conversation"
    model_name: str = "nemotron-nano-9b"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32000)
    is_archived: bool = False
    is_pinned: bool = False


class ConversationCreate(ConversationBase):
    """Request model for creating a conversation"""
    pass


class ConversationUpdate(BaseModel):
    """Request model for updating a conversation"""
    title: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    is_archived: Optional[bool] = None
    is_pinned: Optional[bool] = None


class Conversation(ConversationBase):
    """Full conversation model"""
    id: UUID
    user_id: str  # Changed from UUID to support string user IDs
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    parent_conversation_id: Optional[UUID] = None
    fork_point_message_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# MESSAGE MODELS
# ============================================================================

class MessageBase(BaseModel):
    """Base message model"""
    role: MessageRole
    content: str
    context_documents: Optional[List[Dict[str, Any]]] = None
    retrieval_strategy: Optional[RetrievalStrategy] = None


class MessageCreate(MessageBase):
    """Request model for creating a message"""
    conversation_id: UUID


class Message(MessageBase):
    """Full message model"""
    id: UUID
    conversation_id: UUID
    token_count: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    created_at: datetime
    version: int = 1
    parent_message_id: Optional[UUID] = None
    is_regenerated: bool = False
    regeneration_count: int = 0
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# MENU STATE MODELS
# ============================================================================

class MenuStateBase(BaseModel):
    """Base menu state model"""
    menu_type: MenuType
    state: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v, info: ValidationInfo):
        """Validate state structure based on menu type"""
        menu_type = info.data.get('menu_type') if info.data else None

        # Define required/recommended fields per menu type
        menu_schemas = {
            'chat': ['activeConversationId', 'scrollPosition'],
            'documents': ['selectedDocuments', 'filterSettings'],
            'mindmap': ['activeGraphId', 'viewportState'],
            'knowledge_graph': ['activeGraphId', 'selectedNodes'],
        }

        # This is just validation - we don't enforce strict schema
        # to allow flexibility for future extensions
        return v


class MenuStateSave(MenuStateBase):
    """Request model for saving menu state"""
    pass


class MenuState(MenuStateBase):
    """Full menu state model"""
    id: UUID
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# GRAPH STATE MODELS
# ============================================================================

class GraphNode(BaseModel):
    """Graph node structure"""
    id: str
    label: str
    x: float
    y: float
    type: str = "concept"
    metadata: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    """Graph edge structure"""
    source: str
    target: str
    label: Optional[str] = None
    weight: Optional[float] = 1.0


class GraphViewport(BaseModel):
    """Graph viewport state"""
    zoom: float = 1.0
    center_x: float = 0.0
    center_y: float = 0.0


class GraphStateStructure(BaseModel):
    """Structured graph state"""
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    viewport: GraphViewport = Field(default_factory=GraphViewport)
    selected_nodes: List[str] = []
    layout: Literal["force-directed", "hierarchical", "manual"] = "force-directed"


class GraphStateBase(BaseModel):
    """Base graph state model"""
    graph_type: GraphType
    graph_name: str
    state: Dict[str, Any] = Field(default_factory=dict)


class GraphStateSave(GraphStateBase):
    """Request model for saving graph state"""
    pass


class GraphState(GraphStateBase):
    """Full graph state model"""
    id: UUID
    user_id: str
    node_count: int = 0
    edge_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# WORKSPACE SESSION MODELS
# ============================================================================

class WorkspacePreferences(BaseModel):
    """User workspace preferences"""
    theme: Literal["light", "dark", "auto"] = "dark"
    language: Literal["en", "ko", "ja"] = "en"
    notifications: bool = True
    layout: Literal["comfortable", "compact"] = "comfortable"
    auto_save_interval: int = 5000  # milliseconds


class WorkspaceSessionBase(BaseModel):
    """Base workspace session model"""
    last_active_menu: MenuType = "chat"
    last_conversation_id: Optional[UUID] = None
    preferences: WorkspacePreferences = Field(default_factory=WorkspacePreferences)


class WorkspaceSessionUpdate(BaseModel):
    """Request model for updating workspace session"""
    last_active_menu: Optional[MenuType] = None
    last_conversation_id: Optional[UUID] = None
    preferences: Optional[WorkspacePreferences] = None


class WorkspaceSession(WorkspaceSessionBase):
    """Full workspace session model"""
    id: UUID
    user_id: str
    last_login_at: Optional[datetime] = None
    last_activity_at: datetime
    session_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# COMPOSITE RESPONSE MODELS
# ============================================================================

class WorkspaceStateResponse(BaseModel):
    """Complete workspace state for user login/restore"""
    # Menu states indexed by menu type
    menu_states: Dict[MenuType, Dict[str, Any]] = Field(default_factory=dict)

    # Graph states indexed by graph type and name
    graph_states: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    # Recent conversations
    recent_conversations: List[Conversation] = []

    # Workspace session info
    session: WorkspaceSession

    # Last active context
    last_active_menu: MenuType = "chat"
    last_conversation_id: Optional[UUID] = None


class ChatMessageRequest(BaseModel):
    """Request model for chat message with RAG"""
    conversation_id: Optional[UUID] = None  # None = create new conversation
    message: str
    context_document_ids: Optional[List[str]] = None
    retrieval_strategy: Optional[RetrievalStrategy] = "hybrid"
    model_name: Optional[str] = "nemotron-nano-9b"
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(2048, ge=1, le=32000)


class ChatMessageResponse(BaseModel):
    """Response model for chat message"""
    conversation_id: UUID
    user_message: Message
    assistant_message: Message
    conversation: Conversation


# ============================================================================
# USER DOCUMENT MODELS
# ============================================================================

class UserDocumentBase(BaseModel):
    """Base user document model"""
    document_id: str
    document_title: Optional[str] = None
    document_type: Optional[str] = None
    is_favorite: bool = False
    is_archived: bool = False
    tags: List[str] = []
    notes: Optional[str] = None


class UserDocumentCreate(UserDocumentBase):
    """Request model for adding document to user library"""
    pass


class UserDocumentUpdate(BaseModel):
    """Request model for updating user document"""
    is_favorite: Optional[bool] = None
    is_archived: Optional[bool] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class UserDocument(UserDocumentBase):
    """Full user document model"""
    id: UUID
    user_id: str
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
# ============================================================================
# FORCE PYDANTIC V2 MODEL SCHEMA REBUILD
# ============================================================================
# Required after changing field types (UUID -> str) to update cached schemas

MenuState.model_rebuild()
GraphState.model_rebuild()
WorkspaceSession.model_rebuild()
Conversation.model_rebuild()
Message.model_rebuild()
UserDocument.model_rebuild()
WorkspaceStateResponse.model_rebuild()
