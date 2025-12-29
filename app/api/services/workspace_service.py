"""
Workspace State Persistence Service

Business logic for managing persistent AI workspace state.
Handles menu states, conversations, graph states, and session management.

Architecture Pattern: Service Layer (Clean Architecture)
- Services encapsulate business logic
- Services coordinate between repositories and external services
- Services handle transactions and complex workflows
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4

from ..models.workspace import (
    MenuType,
    GraphType,
    MenuStateSave,
    MenuState,
    GraphStateSave,
    GraphState,
    WorkspaceSessionUpdate,
    WorkspaceSession,
    WorkspaceStateResponse,
    Conversation,
    ConversationCreate,
    ConversationUpdate,
    Message,
    MessageCreate,
    ChatMessageRequest,
    ChatMessageResponse,
    UserDocumentCreate,
    UserDocumentUpdate,
    UserDocument,
    WorkspacePreferences
)
from ..repositories.conversation_repository import (
    ConversationRepository,
    ConversationEntity,
    MessageEntity
)
from ..core.logging_framework import get_logger, LogCategory

logger = get_logger("kms.workspace")


class WorkspaceService:
    """
    Service for managing persistent workspace state.

    Responsibilities:
    - Save and load menu states for all 9 menu types
    - Manage conversation history and messages
    - Persist graph states (mindmap, knowledge graph)
    - Track workspace sessions and user activity
    - Provide atomic operations for state consistency
    """

    def __init__(self, conversation_repository: Optional[ConversationRepository] = None):
        """
        Initialize workspace service with PostgreSQL repository.

        Args:
            conversation_repository: PostgreSQL repository for conversation persistence
        """
        # PostgreSQL repository for conversations
        self._conversation_repo = conversation_repository

        # In-memory storage for other features (to be migrated to PostgreSQL)
        self._menu_states: Dict[str, MenuState] = {}  # key: f"{user_id}:{menu_type}"
        self._graph_states: Dict[str, GraphState] = {}  # key: f"{user_id}:{graph_type}:{graph_name}"
        self._workspace_sessions: Dict[UUID, WorkspaceSession] = {}
        self._user_documents: Dict[str, UserDocument] = {}  # key: f"{user_id}:{document_id}"

        logger.info(
            f"WorkspaceService initialized (PostgreSQL: {self._conversation_repo is not None})",
            category=LogCategory.BUSINESS
        )

    # ========================================================================
    # MENU STATE PERSISTENCE
    # ========================================================================

    async def save_menu_state(
        self,
        user_id: str,
        menu_state: MenuStateSave
    ) -> MenuState:
        """
        Save menu state for a specific user and menu type.

        Design Decision: Upsert pattern (insert or update)
        - Ensures one state per user per menu
        - Atomic operation prevents race conditions
        - Updated timestamp tracks last modification

        Args:
            user_id: User identifier
            menu_state: Menu state data to save

        Returns:
            Saved menu state with timestamps

        Example:
            >>> await service.save_menu_state(
            ...     user_id=uuid4(),
            ...     menu_state=MenuStateSave(
            ...         menu_type="chat",
            ...         state={"activeConversationId": "uuid-123", "scrollPosition": 420}
            ...     )
            ... )
        """
        key = f"{user_id}:{menu_state.menu_type}"

        # Check if state exists
        existing_state = self._menu_states.get(key)

        if existing_state:
            # Update existing state
            existing_state.state = menu_state.state
            existing_state.updated_at = datetime.utcnow()
            state = existing_state
        else:
            # Create new state
            state = MenuState(
                id=uuid4(),
                user_id=user_id,
                menu_type=menu_state.menu_type,
                state=menu_state.state,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self._menu_states[key] = state

        logger.debug(
            f"Saved menu state: {menu_state.menu_type} for user {user_id}",
            category=LogCategory.BUSINESS,
            extra_data={"menu_type": menu_state.menu_type, "state_size": len(menu_state.state)}
        )

        return state

    async def get_menu_state(
        self,
        user_id: str,
        menu_type: MenuType
    ) -> Optional[MenuState]:
        """
        Retrieve menu state for a specific user and menu type.

        Args:
            user_id: User identifier
            menu_type: Type of menu to retrieve state for

        Returns:
            Menu state if exists, None otherwise
        """
        key = f"{user_id}:{menu_type}"
        return self._menu_states.get(key)

    async def get_all_menu_states(
        self,
        user_id: str
    ) -> Dict[MenuType, Dict[str, Any]]:
        """
        Retrieve all menu states for a user.

        Returns:
            Dictionary mapping menu type to state object
        """
        result = {}

        for key, state in self._menu_states.items():
            if state.user_id == user_id:
                result[state.menu_type] = state.state

        logger.debug(
            f"Retrieved {len(result)} menu states for user {user_id}",
            category=LogCategory.BUSINESS
        )

        return result

    # ========================================================================
    # GRAPH STATE PERSISTENCE
    # ========================================================================

    async def save_graph_state(
        self,
        user_id: str,
        graph_state: GraphStateSave
    ) -> GraphState:
        """
        Save graph state (mindmap or knowledge graph).

        Design Decision: Allow multiple graphs per user per type
        - Users can have multiple mindmaps/knowledge graphs
        - Each graph identified by (user_id, graph_type, graph_name)
        - State includes nodes, edges, viewport, and visual layout

        Args:
            user_id: User identifier
            graph_state: Graph state data to save

        Returns:
            Saved graph state with metadata
        """
        key = f"{user_id}:{graph_state.graph_type}:{graph_state.graph_name}"

        # Extract node/edge counts from state for quick access
        state_dict = graph_state.state
        node_count = len(state_dict.get("nodes", []))
        edge_count = len(state_dict.get("edges", []))

        # Check if state exists
        existing_state = self._graph_states.get(key)

        if existing_state:
            # Update existing state
            existing_state.state = graph_state.state
            existing_state.node_count = node_count
            existing_state.edge_count = edge_count
            existing_state.updated_at = datetime.utcnow()
            state = existing_state
        else:
            # Create new state
            state = GraphState(
                id=uuid4(),
                user_id=user_id,
                graph_type=graph_state.graph_type,
                graph_name=graph_state.graph_name,
                state=graph_state.state,
                node_count=node_count,
                edge_count=edge_count,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self._graph_states[key] = state

        logger.debug(
            f"Saved graph state: {graph_state.graph_type}/{graph_state.graph_name} for user {user_id}",
            category=LogCategory.BUSINESS,
            extra_data={
                "graph_type": graph_state.graph_type,
                "graph_name": graph_state.graph_name,
                "node_count": node_count,
                "edge_count": edge_count
            }
        )

        return state

    async def get_graph_states(
        self,
        user_id: str,
        graph_type: Optional[GraphType] = None
    ) -> List[GraphState]:
        """
        Retrieve graph states for a user.

        Args:
            user_id: User identifier
            graph_type: Optional filter by graph type

        Returns:
            List of graph states
        """
        result = []

        for state in self._graph_states.values():
            if state.user_id == user_id:
                if graph_type is None or state.graph_type == graph_type:
                    result.append(state)

        return result

    # ========================================================================
    # WORKSPACE SESSION MANAGEMENT
    # ========================================================================

    async def update_workspace_session(
        self,
        user_id: str,
        session_update: WorkspaceSessionUpdate
    ) -> WorkspaceSession:
        """
        Update workspace session (last active menu, preferences, etc).

        Design Decision: Single session per user
        - Tracks last active context for restore on login
        - Stores global preferences
        - Updates activity timestamp for session monitoring

        Args:
            user_id: User identifier
            session_update: Session data to update

        Returns:
            Updated workspace session
        """
        session = self._workspace_sessions.get(user_id)

        if not session:
            # Create new session
            session = WorkspaceSession(
                id=uuid4(),
                user_id=user_id,
                last_active_menu=session_update.last_active_menu or "chat",
                last_conversation_id=session_update.last_conversation_id,
                preferences=session_update.preferences or WorkspacePreferences(),
                last_login_at=datetime.utcnow(),
                last_activity_at=datetime.utcnow(),
                session_count=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self._workspace_sessions[user_id] = session
        else:
            # Update existing session
            if session_update.last_active_menu is not None:
                session.last_active_menu = session_update.last_active_menu
            if session_update.last_conversation_id is not None:
                session.last_conversation_id = session_update.last_conversation_id
            if session_update.preferences is not None:
                session.preferences = session_update.preferences

            session.last_activity_at = datetime.utcnow()
            session.updated_at = datetime.utcnow()

        logger.debug(
            f"Updated workspace session for user {user_id}",
            category=LogCategory.BUSINESS,
            extra_data={"last_active_menu": session.last_active_menu}
        )

        return session

    async def get_workspace_session(
        self,
        user_id: str
    ) -> Optional[WorkspaceSession]:
        """
        Retrieve workspace session for a user.

        Args:
            user_id: User identifier

        Returns:
            Workspace session if exists, None otherwise
        """
        return self._workspace_sessions.get(user_id)

    async def get_or_create_session(
        self,
        user_id: str
    ) -> WorkspaceSession:
        """
        Get existing workspace session or create a default one.

        This method ensures a session always exists for workspace state loading.
        Creates a session with sensible defaults if none exists.

        Args:
            user_id: User identifier

        Returns:
            Workspace session (existing or newly created)
        """
        session = await self.get_workspace_session(user_id)
        if not session:
            # Create default session with sensible preferences
            default_preferences = WorkspacePreferences(
                theme="auto",
                language="en",
                notifications=True,
                layout="comfortable",
                auto_save_interval=5000
            )
            session = await self.update_workspace_session(
                user_id,
                WorkspaceSessionUpdate(
                    last_active_menu="chat",
                    preferences=default_preferences
                )
            )
        return session

    # ========================================================================
    # COMPLETE WORKSPACE STATE RESTORE
    # ========================================================================

    async def load_workspace_state(
        self,
        user_id: str
    ) -> WorkspaceStateResponse:
        """
        Load complete workspace state for user on login.

        This is the KEY method for workspace restoration.
        Returns everything needed to restore the exact UI state.

        Design Decision: Single atomic load operation
        - Reduces database round-trips
        - Ensures consistent snapshot of workspace state
        - Includes all menu states, graph states, and session context

        Args:
            user_id: User identifier

        Returns:
            Complete workspace state including:
            - All menu states
            - All graph states
            - Recent conversations
            - Workspace session with preferences
            - Last active context

        Example Response:
            {
                "menu_states": {
                    "chat": {"activeConversationId": "uuid-123"},
                    "documents": {"selectedDocuments": ["doc1", "doc2"]}
                },
                "graph_states": {
                    "mindmap": [...],
                    "knowledge_graph": [...]
                },
                "recent_conversations": [...],
                "session": {...},
                "last_active_menu": "chat",
                "last_conversation_id": "uuid-123"
            }
        """
        logger.info(
            f"Loading complete workspace state for user {user_id}",
            category=LogCategory.BUSINESS
        )

        # Load all menu states
        menu_states = await self.get_all_menu_states(user_id)

        # Load all graph states
        mindmap_states = await self.get_graph_states(user_id, graph_type="mindmap")
        kg_states = await self.get_graph_states(user_id, graph_type="knowledge_graph")

        graph_states = {
            "mindmap": [state.model_dump() for state in mindmap_states],
            "knowledge_graph": [state.model_dump() for state in kg_states]
        }

        # Load recent conversations (limit to 20 most recent)
        recent_conversations = await self.get_recent_conversations(user_id, limit=20)

        # Load workspace session
        session = await self.get_workspace_session(user_id)

        if not session:
            # Create default session if doesn't exist
            session = await self.update_workspace_session(
                user_id,
                WorkspaceSessionUpdate(
                    last_active_menu="chat",
                    preferences=WorkspacePreferences()
                )
            )

        # Build response
        workspace_state = WorkspaceStateResponse(
            menu_states=menu_states,
            graph_states=graph_states,
            recent_conversations=recent_conversations,
            session=session,
            last_active_menu=session.last_active_menu,
            last_conversation_id=session.last_conversation_id
        )

        logger.info(
            f"Loaded workspace state for user {user_id}",
            category=LogCategory.BUSINESS,
            extra_data={
                "menu_states_count": len(menu_states),
                "graph_states_count": len(mindmap_states) + len(kg_states),
                "conversations_count": len(recent_conversations)
            }
        )

        return workspace_state

    # ========================================================================
    # HELPER METHODS: Entity <-> Model Conversion
    # ========================================================================

    def _entity_to_conversation(self, entity: ConversationEntity) -> Conversation:
        """Convert ConversationEntity to Conversation model"""
        return Conversation(
            id=UUID(entity.id),
            user_id=entity.user_id,
            title=entity.title or "New Conversation",
            model_name="nemotron-nano-9b",  # Default model
            temperature=0.7,  # Default temperature
            max_tokens=2048,  # Default max tokens
            is_archived=entity.is_archived,
            is_pinned=entity.is_starred,  # Map is_starred to is_pinned
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            last_message_at=None,  # Not directly available
            message_count=entity.message_count,
            parent_conversation_id=None,
            fork_point_message_id=None
        )

    def _conversation_to_entity(
        self,
        conversation: Conversation,
        user_id: str
    ) -> ConversationEntity:
        """Convert Conversation model to ConversationEntity"""
        return ConversationEntity(
            id=str(conversation.id) if conversation.id else None,
            user_id=user_id,
            title=conversation.title,
            message_count=conversation.message_count,
            total_tokens=0,  # Will be updated by triggers
            is_archived=conversation.is_archived,
            is_starred=conversation.is_pinned,
            is_deleted=False,
            strategy="auto",  # Default
            language="auto",  # Default
            metadata={},
            created_at=conversation.created_at,
            updated_at=conversation.updated_at
        )

    def _entity_to_message(self, entity: MessageEntity) -> Message:
        """Convert MessageEntity to Message model"""
        return Message(
            id=UUID(entity.id),
            conversation_id=UUID(entity.conversation_id),
            role=entity.role,
            content=entity.content,
            context_documents=entity.sources or [],
            retrieval_strategy=None,  # Not stored in entity
            token_count=entity.total_tokens,
            prompt_tokens=entity.input_tokens,
            completion_tokens=entity.output_tokens,
            created_at=entity.created_at,
            parent_message_id=UUID(entity.parent_message_id) if entity.parent_message_id else None,
            is_regenerated=False,  # Can be derived from parent_message_id
            regeneration_count=0,  # Not tracked in entity
            metadata=entity.rag_context or {}
        )

    # ========================================================================
    # CONVERSATION MANAGEMENT
    # ========================================================================

    async def create_conversation(
        self,
        user_id: str,
        conversation_data: ConversationCreate
    ) -> Conversation:
        """Create a new conversation in PostgreSQL"""
        if self._conversation_repo is None:
            logger.error(
                "No conversation repository configured, cannot create conversation",
                category=LogCategory.SYSTEM
            )
            raise RuntimeError("Database repository not configured")

        # Create workspace Conversation model
        conversation = Conversation(
            id=uuid4(),
            user_id=user_id,
            title=conversation_data.title,
            model_name=conversation_data.model_name,
            temperature=conversation_data.temperature,
            max_tokens=conversation_data.max_tokens,
            is_archived=conversation_data.is_archived,
            is_pinned=conversation_data.is_pinned,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=0
        )

        # Convert to entity and persist to PostgreSQL
        entity = self._conversation_to_entity(conversation, user_id)
        created_entity = await self._conversation_repo.create(entity)

        # Convert back to workspace model (with database-generated fields)
        result = self._entity_to_conversation(created_entity)

        logger.info(
            f"Created conversation {result.id} for user {user_id}",
            category=LogCategory.BUSINESS
        )

        return result

    async def get_recent_conversations(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[Conversation]:
        """Get recent conversations for a user from PostgreSQL"""
        if self._conversation_repo is None:
            logger.warning(
                "No conversation repository configured, returning empty list",
                category=LogCategory.SYSTEM
            )
            return []

        # Fetch from PostgreSQL repository
        conversation_entities = await self._conversation_repo.get_by_user(
            user_id=user_id,
            limit=limit,
            include_archived=False,
            include_deleted=False
        )

        # Convert entities to workspace Conversation models
        conversations = [
            self._entity_to_conversation(entity)
            for entity in conversation_entities
        ]

        logger.info(
            f"Retrieved {len(conversations)} conversations for user {user_id}",
            category=LogCategory.BUSINESS
        )

        return conversations

    async def add_message(
        self,
        message_data: MessageCreate
    ) -> Message:
        """Add a message to a conversation in PostgreSQL"""
        if self._conversation_repo is None:
            logger.error(
                "No conversation repository configured, cannot add message",
                category=LogCategory.SYSTEM
            )
            raise RuntimeError("Database repository not configured")

        # Add message through repository
        entity = await self._conversation_repo.add_message(
            conversation_id=str(message_data.conversation_id),
            role=message_data.role.value,
            content=message_data.content,
            parent_message_id=None,  # TODO: Support branching if needed
            input_tokens=0,  # TODO: Calculate or pass from caller
            output_tokens=0,  # TODO: Calculate or pass from caller
            total_tokens=0,  # TODO: Calculate or pass from caller
            model=None,  # TODO: Get from conversation settings
            sources=message_data.context_documents,
            rag_context={"retrieval_strategy": message_data.retrieval_strategy.value if message_data.retrieval_strategy else None}
        )

        # Convert entity to workspace Message model
        message = self._entity_to_message(entity)

        logger.info(
            f"Added message {message.id} to conversation {message_data.conversation_id}",
            category=LogCategory.BUSINESS
        )

        return message

    async def get_conversation_messages(
        self,
        conversation_id: UUID
    ) -> List[Message]:
        """Get all messages for a conversation from PostgreSQL"""
        if self._conversation_repo is None:
            logger.warning(
                "No conversation repository configured, returning empty list",
                category=LogCategory.SYSTEM
            )
            return []

        # Fetch messages from repository
        message_entities = await self._conversation_repo.get_messages(
            conversation_id=str(conversation_id),
            include_inactive_branches=False,
            include_deleted=False
        )

        # Convert entities to workspace Message models
        messages = [
            self._entity_to_message(entity)
            for entity in message_entities
        ]

        logger.info(
            f"Retrieved {len(messages)} messages for conversation {conversation_id}",
            category=LogCategory.BUSINESS
        )

        return messages

    # ========================================================================
    # USER DOCUMENT MANAGEMENT
    # ========================================================================

    async def add_user_document(
        self,
        user_id: str,
        document_data: UserDocumentCreate
    ) -> UserDocument:
        """Add document to user's library"""
        key = f"{user_id}:{document_data.document_id}"

        existing_doc = self._user_documents.get(key)

        if existing_doc:
            # Update existing document
            existing_doc.document_title = document_data.document_title or existing_doc.document_title
            existing_doc.is_favorite = document_data.is_favorite
            existing_doc.tags = document_data.tags
            existing_doc.notes = document_data.notes
            existing_doc.last_accessed_at = datetime.utcnow()
            existing_doc.access_count += 1
            existing_doc.updated_at = datetime.utcnow()
            return existing_doc

        # Create new document
        document = UserDocument(
            id=uuid4(),
            user_id=user_id,
            document_id=document_data.document_id,
            document_title=document_data.document_title,
            document_type=document_data.document_type,
            is_favorite=document_data.is_favorite,
            is_archived=document_data.is_archived,
            tags=document_data.tags,
            notes=document_data.notes,
            last_accessed_at=datetime.utcnow(),
            access_count=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self._user_documents[key] = document

        logger.debug(
            f"Added document {document_data.document_id} to user {user_id} library",
            category=LogCategory.BUSINESS
        )

        return document

    # ========================================================================
    # COMPLETE WORKSPACE RESTORATION
    # ========================================================================

# Singleton instance
_workspace_service = None


def get_workspace_service() -> WorkspaceService:
    """
    Get workspace service singleton instance with PostgreSQL repository injection.

    Uses the container to retrieve the conversation repository (PostgreSQL or in-memory fallback).
    """
    global _workspace_service
    if _workspace_service is None:
        from ..core.container import Container

        # Get conversation repository from container (PostgreSQL or fallback)
        try:
            container = Container.get_instance()
            conversation_repo = container.get("conversation_repository")
            _workspace_service = WorkspaceService(conversation_repository=conversation_repo)

            logger.info(
                "Workspace service initialized with PostgreSQL repository",
                category=LogCategory.BUSINESS
            )
        except KeyError:
            # Fallback to service without repository (will use in-memory or return empty)
            _workspace_service = WorkspaceService()
            logger.warning(
                "Workspace service initialized without conversation repository",
                category=LogCategory.SYSTEM
            )

    return _workspace_service
