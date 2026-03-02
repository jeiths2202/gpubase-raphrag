"""
LiveKit Service - Room 관리 및 Token 생성

원격 전문가 화면 공유 (Premium Support) 기능의 핵심 서비스.
LiveKit Server와 통신하여 Room 생성, JWT Token 발급, 세션 추적을 담당.
"""
import logging
import uuid
from typing import Optional, Dict, List
from datetime import datetime

from app.api.core.config import api_settings
from app.api.models.premium_support import (
    SessionInfo,
    SessionStatus,
    ExpertStatus,
    CreateSessionResponse,
    JoinSessionResponse,
    ExpertStatusResponse,
    LiveKitHealthResponse,
)

logger = logging.getLogger("kms.livekit")


class LiveKitService:
    """LiveKit Room/Token 관리 서비스 (Singleton)"""

    _instance: Optional["LiveKitService"] = None

    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._livekit_available = False
        self._api = None
        self._init_client()

    def _init_client(self):
        """LiveKit Python SDK 클라이언트 초기화 (lazy import)"""
        try:
            from livekit.api import LiveKitAPI, AccessToken, VideoGrants
            self._api_module = {
                "LiveKitAPI": LiveKitAPI,
                "AccessToken": AccessToken,
                "VideoGrants": VideoGrants,
            }
            self._livekit_available = True
            logger.info("LiveKit SDK initialized successfully")
        except ImportError:
            self._api_module = None
            self._livekit_available = False
            logger.warning("livekit-api package not installed. Premium Support disabled.")

    async def create_session(
        self,
        user_id: str,
        user_name: str,
        chat_context: Optional[str] = None,
    ) -> CreateSessionResponse:
        """Room 생성 + 사용자 Token 발급"""
        room_name = f"support-{uuid.uuid4().hex[:8]}"
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

        # LiveKit Room 생성
        try:
            api = self._api_module["LiveKitAPI"](
                api_settings.LIVEKIT_SERVER_URL,
                api_settings.LIVEKIT_API_KEY,
                api_settings.LIVEKIT_API_SECRET,
            )
            await api.room.create_room(
                name=room_name,
                empty_timeout=300,
                max_participants=2,
            )
            await api.aclose()
        except Exception as e:
            logger.error(f"Failed to create LiveKit room: {e}")
            raise RuntimeError(f"LiveKit room creation failed: {e}")

        # 사용자 Token 생성
        token = self._generate_token(
            identity=user_id,
            name=user_name,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )

        # 세션 추적 저장
        self._sessions[room_name] = SessionInfo(
            session_id=session_id,
            room_name=room_name,
            user_id=user_id,
            user_name=user_name,
            status=SessionStatus.WAITING,
            chat_context=chat_context,
            created_at=datetime.utcnow(),
        )

        logger.info(f"Session created: {session_id} room={room_name} user={user_name}")

        return CreateSessionResponse(
            room_name=room_name,
            token=token,
            server_url=api_settings.LIVEKIT_WS_URL,
            session_id=session_id,
        )

    async def join_session(
        self,
        room_name: str,
        expert_id: str,
        expert_name: str,
    ) -> JoinSessionResponse:
        """전문가 세션 참여 Token 발급"""
        session = self._sessions.get(room_name)
        if not session:
            raise ValueError(f"Session not found: {room_name}")

        if session.status == SessionStatus.ENDED:
            raise ValueError(f"Session already ended: {room_name}")

        token = self._generate_token(
            identity=expert_id,
            name=expert_name,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )

        # 세션 상태 업데이트
        session.status = SessionStatus.ACTIVE
        session.expert_id = expert_id
        session.expert_name = expert_name

        logger.info(f"Expert joined: {expert_name} -> room={room_name}")

        return JoinSessionResponse(
            token=token,
            server_url=api_settings.LIVEKIT_WS_URL,
            room_name=room_name,
            user_name=session.user_name,
            chat_context=session.chat_context,
        )

    def _generate_token(
        self,
        identity: str,
        name: str,
        room: str,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        """LiveKit JWT Token 생성"""
        if not self._livekit_available:
            raise RuntimeError("LiveKit SDK not available")

        AccessToken = self._api_module["AccessToken"]
        VideoGrants = self._api_module["VideoGrants"]

        token = AccessToken(
            api_settings.LIVEKIT_API_KEY,
            api_settings.LIVEKIT_API_SECRET,
        )
        token.identity = identity
        token.name = name
        token.add_grant(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
            )
        )
        token.ttl = 600  # 10분

        return token.to_jwt()

    async def end_session(self, room_name: str) -> None:
        """세션 종료 + Room 삭제"""
        if room_name in self._sessions:
            self._sessions[room_name].status = SessionStatus.ENDED
            logger.info(f"Session ended: room={room_name}")

        # LiveKit Room 삭제
        try:
            api = self._api_module["LiveKitAPI"](
                api_settings.LIVEKIT_SERVER_URL,
                api_settings.LIVEKIT_API_KEY,
                api_settings.LIVEKIT_API_SECRET,
            )
            await api.room.delete_room(name=room_name)
            await api.aclose()
        except Exception as e:
            logger.warning(f"Failed to delete LiveKit room {room_name}: {e}")

        # 메모리에서 제거
        self._sessions.pop(room_name, None)

    def get_waiting_sessions(self) -> List[SessionInfo]:
        """대기 중인 세션 목록"""
        return [
            s for s in self._sessions.values()
            if s.status == SessionStatus.WAITING
        ]

    def get_all_active_sessions(self) -> List[SessionInfo]:
        """모든 활성 세션 (WAITING + ACTIVE)"""
        return [
            s for s in self._sessions.values()
            if s.status in (SessionStatus.WAITING, SessionStatus.ACTIVE)
        ]

    async def get_expert_status(self) -> ExpertStatusResponse:
        """전문가 가용 상태 조회"""
        sessions = self.get_all_active_sessions()
        # Phase 1: 단순 상태 반환. Phase 2에서 전문가 접속 추적 추가
        return ExpertStatusResponse(
            status=ExpertStatus.AVAILABLE,
            available_experts=1,
            active_sessions=len(sessions),
        )

    async def check_health(self) -> LiveKitHealthResponse:
        """LiveKit 서버 상태 확인"""
        if not self._livekit_available:
            return LiveKitHealthResponse(
                available=False,
                server_url=api_settings.LIVEKIT_WS_URL,
                rooms_count=0,
            )

        try:
            api = self._api_module["LiveKitAPI"](
                api_settings.LIVEKIT_SERVER_URL,
                api_settings.LIVEKIT_API_KEY,
                api_settings.LIVEKIT_API_SECRET,
            )
            rooms = await api.room.list_rooms()
            await api.aclose()
            return LiveKitHealthResponse(
                available=True,
                server_url=api_settings.LIVEKIT_WS_URL,
                rooms_count=len(rooms),
            )
        except Exception as e:
            logger.warning(f"LiveKit health check failed: {e}")
            return LiveKitHealthResponse(
                available=False,
                server_url=api_settings.LIVEKIT_WS_URL,
                rooms_count=0,
            )


# Singleton factory
_livekit_service: Optional[LiveKitService] = None


def get_livekit_service() -> LiveKitService:
    global _livekit_service
    if _livekit_service is None:
        _livekit_service = LiveKitService()
    return _livekit_service
