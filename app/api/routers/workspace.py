"""
Workspace State Persistence API

RESTful API endpoints for persistent AI workspace management.
Supports multi-menu state persistence, conversation history, and graph states.
"""

from typing import Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

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
    ConversationCreate,
    ConversationUpdate,
    Conversation,
    MessageCreate,
    Message,
    UserDocumentCreate,
    UserDocumentUpdate,
    UserDocument
)
from ..models.base import SuccessResponse, MetaInfo
from ..services.workspace_service import get_workspace_service, WorkspaceService
from ..core.deps import get_current_user
from ..core.logging_framework import get_logger, LogCategory
import uuid as uuid_module

router = APIRouter(prefix="/workspace", tags=["Workspace"])
logger = get_logger("kms.workspace.api")


# ============================================================================
# MENU STATE ENDPOINTS
# ============================================================================

@router.post(
    "/state/save",
    summary="Save menu state",
    description="Persist UI state for a specific menu (chat, documents, mindmap, etc.)"
)

async def save_menu_state(
    menu_state: MenuStateSave,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """
    Save menu state for current user.

    **Design Pattern**: Upsert (Insert or Update)
    - One state per user per menu type
    - Atomic operation prevents race conditions
    - Timestamps track modifications

    **Request Example**:
    ```json
    {
        "menuType": "chat",
        "state": {
            "activeConversationId": "uuid-123",
            "scrollPosition": 420,
            "filterSettings": {"archived": false}
        }
    }
    ```

    **Response Example**:
    ```json
    {
        "success": true,
        "data": {
            "id": "uuid",
            "user_id": "uuid",
            "menu_type": "chat",
            "state": {...},
            "created_at": "2025-12-28T12:00:00",
            "updated_at": "2025-12-28T12:00:00"
        }
    }
    ```
    """
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]  # Keep as string, models use UUID internally if needed

    logger.info(
        f"Saving menu state: {menu_state.menu_type} for user {user_id}",
        category=LogCategory.REQUEST,
        extra_data={"menu_type": menu_state.menu_type, "request_id": request_id, "user_id_type": type(user_id).__name__}
    )

    try:
        logger.debug(f"Calling save_menu_state with user_id={user_id}, type={type(user_id)}")
        saved_state = await workspace_service.save_menu_state(user_id, menu_state)
        logger.debug(f"save_menu_state returned successfully, type of result={type(saved_state)}")

        # Return plain dict to completely bypass Pydantic validation
        return {
            "success": True,
            "data": saved_state.model_dump(mode='python'),
            "meta": {"request_id": request_id}
        }

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(
            f"Failed to save menu state: {str(e)}\nTraceback:\n{tb_str}",
            category=LogCategory.ERROR,
            extra_data={"error": str(e), "request_id": request_id, "traceback": tb_str}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "STATE_SAVE_ERROR", "message": "Failed to save menu state"}
        )


@router.get(
    "/state/load",
    summary="Load complete workspace state",
    description="Retrieve all workspace state for user login/restoration (menu states, graphs, conversations, session)"
)
async def load_workspace_state(
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """
    Load complete workspace state for current user.

    This endpoint returns all persisted state needed to restore the workspace:
    - All menu states (chat, documents, mindmap, etc.)
    - All graph states (mindmaps and knowledge graphs)
    - Recent conversations
    - Workspace session preferences

    Called automatically on user login to restore the workspace.
    """
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    logger.info(
        f"Loading complete workspace state for user {user_id}",
        category=LogCategory.REQUEST,
        extra_data={"request_id": request_id}
    )

    try:
        workspace_state = await workspace_service.load_workspace_state(user_id)

        return SuccessResponse(
            data=workspace_state.model_dump(mode='python') if hasattr(workspace_state, 'model_dump') else workspace_state,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        logger.error(
            f"Failed to load workspace state: {str(e)}",
            category=LogCategory.ERROR,
            extra_data={"request_id": request_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "WORKSPACE_LOAD_ERROR", "message": "Failed to load workspace state"}
        )


@router.get(
    "/state/{menu_type}",
    summary="Get menu state",
    description="Retrieve saved state for a specific menu type"
)
async def get_menu_state(
    menu_type: MenuType,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Retrieve menu state for current user and menu type"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    state = await workspace_service.get_menu_state(user_id, menu_type)

    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "STATE_NOT_FOUND", "message": f"No state found for menu: {menu_type}"}
        )

    return SuccessResponse(
        data=state.model_dump(mode='python') if hasattr(state, 'model_dump') else state,
        meta=MetaInfo(request_id=request_id)
    )


# ============================================================================
# GRAPH STATE ENDPOINTS
# ============================================================================

@router.post(
    "/graph/save",
    summary="Save graph state",
    description="Persist mindmap or knowledge graph state with nodes, edges, and viewport"
)
async def save_graph_state(
    graph_state: GraphStateSave,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """
    Save graph state (mindmap or knowledge graph).

    **Request Example**:
    ```json
    {
        "graph_type": "mindmap",
        "graph_name": "GPU Architecture Overview",
        "state": {
            "nodes": [
                {"id": "n1", "label": "GPU", "x": 100, "y": 200, "type": "concept"},
                {"id": "n2", "label": "RAG", "x": 300, "y": 200, "type": "concept"}
            ],
            "edges": [
                {"source": "n1", "target": "n2", "label": "enables"}
            ],
            "viewport": {"zoom": 1.0, "centerX": 200, "centerY": 200},
            "selectedNodes": ["n1"],
            "layout": "force-directed"
        }
    }
    ```
    """
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    logger.info(
        f"Saving graph state: {graph_state.graph_type}/{graph_state.graph_name} for user {user_id}",
        category=LogCategory.REQUEST,
        extra_data={
            "graph_type": graph_state.graph_type,
            "graph_name": graph_state.graph_name,
            "request_id": request_id
        }
    )

    try:
        saved_state = await workspace_service.save_graph_state(user_id, graph_state)

        return SuccessResponse(
            data=saved_state.model_dump(mode='python'),
            meta=MetaInfo(request_id=request_id)
        )

    except Exception as e:
        logger.error(
            f"Failed to save graph state: {str(e)}",
            category=LogCategory.ERROR,
            extra_data={"error": str(e), "request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "GRAPH_SAVE_ERROR", "message": "Failed to save graph state"}
        )


@router.get(
    "/graph/{graph_type}",
    summary="Get graph states",
    description="Retrieve all saved graphs of a specific type (mindmap or knowledge_graph)"
)
async def get_graph_states(
    graph_type: GraphType,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Retrieve all graph states of a specific type for current user"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    states = await workspace_service.get_graph_states(user_id, graph_type)

    return SuccessResponse(
        data=[state.model_dump(mode='python') for state in states] if states else [],
        meta=MetaInfo(request_id=request_id)
    )


# ============================================================================
# WORKSPACE SESSION ENDPOINTS
# ============================================================================

@router.put(
    "/session",
    summary="Update workspace session",
    description="Update last active menu, preferences, and session context"
)
async def update_workspace_session(
    session_update: WorkspaceSessionUpdate,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """
    Update workspace session.

    **Use Cases**:
    - Track last active menu for restore on login
    - Update user preferences (theme, language, notifications)
    - Record last active conversation

    **Request Example**:
    ```json
    {
        "last_active_menu": "chat",
        "last_conversation_id": "uuid-123",
        "preferences": {
            "theme": "dark",
            "language": "en",
            "notifications": true,
            "layout": "comfortable",
            "auto_save_interval": 5000
        }
    }
    ```
    """
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    logger.debug(
        f"Updating workspace session for user {user_id}",
        category=LogCategory.REQUEST,
        extra_data={"request_id": request_id}
    )

    try:
        session = await workspace_service.update_workspace_session(user_id, session_update)

        return SuccessResponse(
            data=session.model_dump(mode='python'),
            meta=MetaInfo(request_id=request_id)
        )

    except Exception as e:
        logger.error(
            f"Failed to update workspace session: {str(e)}",
            category=LogCategory.ERROR,
            extra_data={"error": str(e), "request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SESSION_UPDATE_ERROR", "message": "Failed to update session"}
        )


# ============================================================================
# COMPLETE WORKSPACE STATE RESTORE (KEY ENDPOINT)
# ============================================================================
# Note: This duplicate endpoint has been removed - using the implementation at line 126


# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@router.post(
    "/conversations",
    summary="Create conversation",
    description="Create a new RAG conversation"
)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Create a new conversation"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    conversation = await workspace_service.create_conversation(user_id, conversation_data)

    return SuccessResponse(
        data=conversation.model_dump(mode='python'),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/conversations/recent",
    summary="Get recent conversations",
    description="Retrieve recent conversations for current user"
)
async def get_recent_conversations(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Get recent conversations"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    conversations = await workspace_service.get_recent_conversations(user_id, limit)

    return SuccessResponse(
        data=[conv.model_dump(mode='python') for conv in conversations] if conversations else [],
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/messages",
    summary="Add message",
    description="Add a message to a conversation"
)
async def add_message(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Add a message to a conversation"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"

    message = await workspace_service.add_message(message_data)

    return SuccessResponse(
        data=message.model_dump(mode='python'),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="Get conversation messages",
    description="Retrieve all messages for a specific conversation"
)
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Get all messages for a conversation"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"

    messages = await workspace_service.get_conversation_messages(conversation_id)

    return SuccessResponse(
        data=[msg.model_dump(mode='python') for msg in messages],
        meta=MetaInfo(request_id=request_id)
    )


# ============================================================================
# USER DOCUMENT ENDPOINTS
# ============================================================================

@router.post(
    "/documents",
    summary="Add user document",
    description="Add document to user's library with tags, favorites, etc."
)
async def add_user_document(
    document_data: UserDocumentCreate,
    current_user: dict = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
):
    """Add document to user's library"""
    request_id = f"req_{uuid_module.uuid4().hex[:12]}"
    user_id = current_user["id"]

    document = await workspace_service.add_user_document(user_id, document_data)

    return SuccessResponse(
        data=document.model_dump(mode='python'),
        meta=MetaInfo(request_id=request_id)
    )
