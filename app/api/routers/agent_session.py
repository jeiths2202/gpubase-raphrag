"""
Agent Session API Router
세션 상태 관리 및 복원 API
"""
import time
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_current_user
from ..services.agent_work_service import get_agent_work_service, SearchScope
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-session", tags=["Agent Session"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SessionStateResponse(BaseModel):
    """Session state for restoration."""
    timestamp: str = Field(..., description="Session timestamp")
    last_query: str = Field(..., description="Last query")
    selected_scope: Optional[dict] = Field(None, description="Selected search scope")
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    agent_type: str = Field("rag", description="Agent type")
    age_hours: float = Field(0.0, description="Session age in hours")
    can_restore: bool = Field(True, description="Whether session can be restored")


class RestoreSessionRequest(BaseModel):
    """Request to restore a session."""
    restore: bool = Field(True, description="Whether to restore the session")


class RestoreSessionResponse(BaseModel):
    """Response after session restoration."""
    restored: bool = Field(False, description="Whether session was restored")
    session: Optional[SessionStateResponse] = Field(None, description="Restored session state")


class SearchHistoryEntry(BaseModel):
    """A search history entry."""
    query: str
    timestamp: str
    selected_scope: Optional[dict] = None
    result_count: int = 0
    was_successful: bool = True


class SearchHistoryResponse(BaseModel):
    """Search history response."""
    history: List[SearchHistoryEntry] = Field(default_factory=list)
    total_items: int = Field(0)


class PreferencesResponse(BaseModel):
    """User preferences response."""
    default_documents: List[str] = Field(default_factory=list)
    language: str = Field("auto")
    always_confirm_scope: bool = Field(True)
    max_history_items: int = Field(50)
    auto_restore_session: bool = Field(True)


class UpdatePreferencesRequest(BaseModel):
    """Request to update preferences."""
    default_documents: Optional[List[str]] = None
    language: Optional[str] = None
    always_confirm_scope: Optional[bool] = None
    max_history_items: Optional[int] = Field(None, ge=10, le=200)
    auto_restore_session: Optional[bool] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/restore-check",
    response_model=SuccessResponse[SessionStateResponse],
    summary="세션 복원 가능 확인",
    description="이전 세션이 존재하고 복원 가능한지 확인합니다."
)
async def check_session_restore(
    max_age_hours: int = Query(24, ge=1, le=168, description="최대 세션 연령 (시간)"),
    current_user: dict = Depends(get_current_user)
):
    """Check if a previous session can be restored."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        agent_work_service = get_agent_work_service()
        session = await agent_work_service.get_session_for_restore(
            user_id=user_id,
            max_age_hours=max_age_hours
        )

        processing_time = int((time.time() - start_time) * 1000)

        if not session:
            # No session to restore
            return SuccessResponse(
                data=SessionStateResponse(
                    timestamp="",
                    last_query="",
                    selected_scope=None,
                    conversation_id=None,
                    agent_type="rag",
                    age_hours=0,
                    can_restore=False
                ),
                meta=MetaInfo(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
            )

        return SuccessResponse(
            data=SessionStateResponse(
                timestamp=session["timestamp"],
                last_query=session["last_query"],
                selected_scope=session["selected_scope"],
                conversation_id=session["conversation_id"],
                agent_type=session["agent_type"],
                age_hours=session["age_hours"],
                can_restore=True
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to check session restore: {e}")
        raise HTTPException(status_code=500, detail="Failed to check session")


@router.post(
    "/restore",
    response_model=SuccessResponse[RestoreSessionResponse],
    summary="세션 복원",
    description="이전 세션을 복원합니다."
)
async def restore_session(
    request: RestoreSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Restore or dismiss previous session."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        agent_work_service = get_agent_work_service()

        if not request.restore:
            # User chose not to restore - clear session
            await agent_work_service.clear_session(user_id)
            processing_time = int((time.time() - start_time) * 1000)

            return SuccessResponse(
                data=RestoreSessionResponse(
                    restored=False,
                    session=None
                ),
                meta=MetaInfo(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
            )

        # Get session to restore
        session = await agent_work_service.get_session_for_restore(
            user_id=user_id,
            max_age_hours=24
        )

        if not session:
            processing_time = int((time.time() - start_time) * 1000)
            return SuccessResponse(
                data=RestoreSessionResponse(
                    restored=False,
                    session=None
                ),
                meta=MetaInfo(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    request_id=request_id,
                    processing_time_ms=processing_time
                )
            )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=RestoreSessionResponse(
                restored=True,
                session=SessionStateResponse(
                    timestamp=session["timestamp"],
                    last_query=session["last_query"],
                    selected_scope=session["selected_scope"],
                    conversation_id=session["conversation_id"],
                    agent_type=session["agent_type"],
                    age_hours=session["age_hours"],
                    can_restore=True
                )
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to restore session: {e}")
        raise HTTPException(status_code=500, detail="Session restoration failed")


@router.get(
    "/history",
    response_model=SuccessResponse[SearchHistoryResponse],
    summary="검색 이력 조회",
    description="사용자의 검색 이력을 반환합니다."
)
async def get_search_history(
    limit: int = Query(20, ge=1, le=100, description="최대 항목 수"),
    current_user: dict = Depends(get_current_user)
):
    """Get user's search history."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        agent_work_service = get_agent_work_service()
        work_data = await agent_work_service.get_agent_work(user_id)

        history = []
        for entry in work_data.search_history[:limit]:
            history.append(SearchHistoryEntry(
                query=entry.query,
                timestamp=entry.timestamp,
                selected_scope=entry.selected_scope.to_dict() if entry.selected_scope else None,
                result_count=entry.result_count,
                was_successful=entry.was_successful
            ))

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=SearchHistoryResponse(
                history=history,
                total_items=len(work_data.search_history)
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get search history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")


@router.delete(
    "/history",
    response_model=SuccessResponse[dict],
    summary="검색 이력 삭제",
    description="사용자의 검색 이력을 삭제합니다."
)
async def clear_search_history(
    current_user: dict = Depends(get_current_user)
):
    """Clear user's search history."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        agent_work_service = get_agent_work_service()
        success = await agent_work_service.clear_history(user_id)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data={"cleared": success},
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to clear history: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear history")


@router.get(
    "/preferences",
    response_model=SuccessResponse[PreferencesResponse],
    summary="사용자 설정 조회",
    description="사용자의 Agent 관련 설정을 반환합니다."
)
async def get_preferences(
    current_user: dict = Depends(get_current_user)
):
    """Get user preferences."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        agent_work_service = get_agent_work_service()
        prefs = await agent_work_service.get_preferences(user_id)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=PreferencesResponse(**prefs),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve preferences")


@router.put(
    "/preferences",
    response_model=SuccessResponse[PreferencesResponse],
    summary="사용자 설정 업데이트",
    description="사용자의 Agent 관련 설정을 업데이트합니다."
)
async def update_preferences(
    request: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update user preferences."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Build update dict with only provided fields
        updates = {}
        if request.default_documents is not None:
            updates["default_documents"] = request.default_documents
        if request.language is not None:
            updates["language"] = request.language
        if request.always_confirm_scope is not None:
            updates["always_confirm_scope"] = request.always_confirm_scope
        if request.max_history_items is not None:
            updates["max_history_items"] = request.max_history_items
        if request.auto_restore_session is not None:
            updates["auto_restore_session"] = request.auto_restore_session

        agent_work_service = get_agent_work_service()
        await agent_work_service.update_preferences(user_id, updates)

        # Return updated preferences
        prefs = await agent_work_service.get_preferences(user_id)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=PreferencesResponse(**prefs),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to update preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")


@router.post(
    "/update-state",
    response_model=SuccessResponse[dict],
    summary="세션 상태 업데이트",
    description="현재 세션 상태를 저장합니다."
)
async def update_session_state(
    query: str = Query(..., description="현재 쿼리"),
    conversation_id: Optional[str] = Query(None, description="대화 ID"),
    agent_type: str = Query("rag", description="에이전트 타입"),
    selected_documents: Optional[List[str]] = Query(None, description="선택된 문서 ID"),
    selected_sections: Optional[List[str]] = Query(None, description="선택된 섹션 경로"),
    current_user: dict = Depends(get_current_user)
):
    """Update session state for later restoration."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Create scope if provided
        scope = None
        if selected_documents or selected_sections:
            scope = SearchScope(
                documents=selected_documents or [],
                sections=selected_sections or []
            )

        agent_work_service = get_agent_work_service()
        success = await agent_work_service.update_session_state(
            user_id=user_id,
            query=query,
            selected_scope=scope,
            conversation_id=conversation_id,
            agent_type=agent_type
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data={"updated": success},
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to update session state: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session state")
