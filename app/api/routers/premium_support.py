"""
Premium Support Router - 원격 전문가 화면 공유 지원 (LiveKit)

Endpoints:
  POST /create-session    - Room 생성 + 사용자 Token 발급
  GET  /expert-status     - 전문가 가용 상태 조회
  GET  /sessions          - 활성 세션 목록 (전문가용)
  POST /join-session/{rn} - 전문가 세션 참여 Token 발급
  POST /end-session       - 세션 종료
  GET  /health            - LiveKit 서버 상태
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.core.config import api_settings
from app.api.core.deps import get_current_user
from app.api.services.livekit_service import get_livekit_service
from app.api.models.premium_support import (
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionRequest,
    JoinSessionResponse,
    SessionInfo,
    ExpertStatusResponse,
    LiveKitHealthResponse,
)

logger = logging.getLogger("kms.premium_support")
router = APIRouter(prefix="/support", tags=["premium-support"])


def _check_enabled():
    """Feature flag 확인"""
    if not api_settings.PREMIUM_SUPPORT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Premium Support is not enabled"
        )


@router.post(
    "/create-session",
    response_model=CreateSessionResponse,
    status_code=201,
    summary="지원 세션 생성",
    description="LiveKit Room 생성 + 사용자 Token 발급. 화면 공유 세션을 시작합니다.",
)
async def create_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    _check_enabled()

    service = get_livekit_service()
    health = await service.check_health()
    if not health.available:
        raise HTTPException(
            status_code=503,
            detail="LiveKit server is not available"
        )

    try:
        return await service.create_session(
            user_id=current_user.get("user_id", "unknown"),
            user_name=current_user.get("username", "Unknown User"),
            chat_context=request.chat_context,
        )
    except RuntimeError as e:
        logger.error(f"Session creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/expert-status",
    response_model=ExpertStatusResponse,
    summary="전문가 가용 상태",
)
async def get_expert_status(
    current_user: dict = Depends(get_current_user),
):
    _check_enabled()
    service = get_livekit_service()
    return await service.get_expert_status()


@router.get(
    "/sessions",
    response_model=List[SessionInfo],
    summary="활성 세션 목록 (전문가용)",
)
async def list_sessions(
    current_user: dict = Depends(get_current_user),
):
    _check_enabled()
    service = get_livekit_service()
    return service.get_all_active_sessions()


@router.post(
    "/join-session/{room_name}",
    response_model=JoinSessionResponse,
    summary="전문가 세션 참여",
)
async def join_session(
    room_name: str,
    current_user: dict = Depends(get_current_user),
):
    _check_enabled()
    service = get_livekit_service()
    try:
        return await service.join_session(
            room_name=room_name,
            expert_id=current_user.get("user_id", "unknown"),
            expert_name=current_user.get("username", "Expert"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/end-session",
    summary="세션 종료",
)
async def end_session(
    request: EndSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    _check_enabled()
    service = get_livekit_service()
    await service.end_session(request.room_name)
    return {"message": "Session ended successfully"}


@router.get(
    "/health",
    response_model=LiveKitHealthResponse,
    summary="LiveKit 서버 상태",
)
async def livekit_health():
    service = get_livekit_service()
    return await service.check_health()
