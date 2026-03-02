"""
Premium Support Models - LiveKit 기반 원격 전문가 화면 공유
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class SessionStatus(str, Enum):
    """지원 세션 상태"""
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"


class ExpertStatus(str, Enum):
    """전문가 가용 상태"""
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"


# === Request Models ===

class CreateSessionRequest(BaseModel):
    """세션 생성 요청"""
    chat_context: Optional[str] = Field(
        None,
        description="현재 RAG 채팅 대화 요약 (전문가 참고용)",
        max_length=2000
    )


class EndSessionRequest(BaseModel):
    """세션 종료 요청"""
    room_name: str = Field(..., description="종료할 Room 이름")
    reason: Optional[str] = Field(None, description="종료 사유")


# === Response Models ===

class CreateSessionResponse(BaseModel):
    """세션 생성 응답 - LiveKit 연결 정보 포함"""
    room_name: str = Field(..., description="LiveKit Room 이름")
    token: str = Field(..., description="LiveKit JWT Token (사용자용)")
    server_url: str = Field(..., description="LiveKit WebSocket URL")
    session_id: str = Field(..., description="KMS 세션 추적 ID")


class JoinSessionResponse(BaseModel):
    """전문가 세션 참여 응답"""
    token: str = Field(..., description="LiveKit JWT Token (전문가용)")
    server_url: str = Field(..., description="LiveKit WebSocket URL")
    room_name: str
    user_name: str = Field(..., description="지원 요청한 사용자 이름")
    chat_context: Optional[str] = Field(None, description="사용자 채팅 컨텍스트")


class SessionInfo(BaseModel):
    """세션 정보"""
    session_id: str
    room_name: str
    user_id: str
    user_name: str
    status: SessionStatus
    chat_context: Optional[str] = None
    created_at: datetime
    expert_id: Optional[str] = None
    expert_name: Optional[str] = None


class ExpertStatusResponse(BaseModel):
    """전문가 가용 상태 응답"""
    status: ExpertStatus = ExpertStatus.AVAILABLE
    available_experts: int = Field(0, description="접속 가능 전문가 수")
    active_sessions: int = Field(0, description="현재 진행 중인 세션 수")
    estimated_wait: Optional[int] = Field(None, description="예상 대기 시간(초)")


class LiveKitHealthResponse(BaseModel):
    """LiveKit 서버 상태"""
    available: bool
    server_url: str
    rooms_count: int = 0
