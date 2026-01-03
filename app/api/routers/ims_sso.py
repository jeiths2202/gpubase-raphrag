"""
IMS SSO API Router
IMS 시스템 SSO 연결 및 인증 관련 API
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from ..models.base import SuccessResponse, MetaInfo
from ..ims_sso_connector.sso.service import IMSSSOService
from ..ims_sso_connector.sso.validator import IMSSSOValidator
from ..core.logging_framework import get_logger, LogCategory

router = APIRouter(prefix="/ims-sso", tags=["IMS SSO"])
logger = get_logger("kms.ims_sso")

# In-memory SSO service instances (keyed by session ID)
# In production, this should be moved to Redis or database
_sso_sessions = {}


class IMSSSOConnectRequest(BaseModel):
    """IMS SSO 연결 요청"""
    ims_url: str = Field(..., description="IMS 시스템 URL (예: https://ims.tmaxsoft.com)")
    chrome_profile: str = Field(default="Default", description="Chrome 프로필 이름")
    validation_endpoint: str = Field(default="/api/v1/me", description="인증 검증 엔드포인트")


class IMSSSOConnectResponse(BaseModel):
    """IMS SSO 연결 응답"""
    session_id: str = Field(..., description="SSO 세션 ID")
    ims_url: str = Field(..., description="연결된 IMS URL")
    user_info: Optional[dict] = Field(None, description="사용자 정보")


class IMSSSOStatusResponse(BaseModel):
    """IMS SSO 상태 응답"""
    is_connected: bool = Field(..., description="연결 상태")
    ims_url: Optional[str] = Field(None, description="연결된 IMS URL")
    user_info: Optional[dict] = Field(None, description="사용자 정보")


class IMSSSOQueryRequest(BaseModel):
    """IMS SSO 쿼리 요청"""
    session_id: str = Field(..., description="SSO 세션 ID")
    query: str = Field(..., description="AI Agent 쿼리")


class IMSSSOQueryResponse(BaseModel):
    """IMS SSO 쿼리 응답"""
    response: str = Field(..., description="AI Agent 응답")
    knowledge_id: Optional[str] = Field(None, description="생성된 지식 ID")


@router.post(
    "/connect",
    response_model=SuccessResponse[IMSSSOConnectResponse],
    summary="IMS SSO 연결",
    description="Chrome 쿠키를 사용하여 IMS 시스템에 SSO 연결합니다"
)
async def connect_ims_sso(request: IMSSSOConnectRequest):
    """
    IMS 시스템에 SSO 연결

    Chrome 브라우저에서 이미 로그인한 세션의 쿠키를 추출하여
    IMS 시스템에 인증된 요청을 보낼 수 있도록 합니다.
    """
    try:
        # Validate connection parameters
        is_valid, error_message = IMSSSOValidator.validate_connection_params(
            request.ims_url,
            request.chrome_profile
        )

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

        # Sanitize URL
        sanitized_url = IMSSSOValidator.sanitize_url(request.ims_url)

        # Create SSO service instance
        sso_service = IMSSSOService()

        # Connect to IMS system
        success, error, user_info = sso_service.connect(
            ims_url=sanitized_url,
            chrome_profile=request.chrome_profile,
            validation_endpoint=request.validation_endpoint
        )

        if not success:
            logger.warning(
                f"IMS SSO connection failed: {error}",
                category=LogCategory.SECURITY
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error or "IMS SSO 연결에 실패했습니다"
            )

        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())

        # Store SSO service instance
        _sso_sessions[session_id] = sso_service

        logger.info(
            f"IMS SSO connected successfully - Session: {session_id}, URL: {sanitized_url}",
            category=LogCategory.SECURITY
        )

        return SuccessResponse(
            data=IMSSSOConnectResponse(
                session_id=session_id,
                ims_url=sanitized_url,
                user_info=user_info
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"IMS SSO connection error: {str(e)}",
            category=LogCategory.SECURITY,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IMS SSO 연결 중 오류가 발생했습니다: {str(e)}"
        )


@router.get(
    "/status/{session_id}",
    response_model=SuccessResponse[IMSSSOStatusResponse],
    summary="IMS SSO 상태 확인",
    description="SSO 연결 상태를 확인합니다"
)
async def get_ims_sso_status(session_id: str):
    """
    IMS SSO 연결 상태 확인
    """
    try:
        sso_service = _sso_sessions.get(session_id)

        if not sso_service:
            return SuccessResponse(
                data=IMSSSOStatusResponse(
                    is_connected=False,
                    ims_url=None,
                    user_info=None
                )
            )

        return SuccessResponse(
            data=IMSSSOStatusResponse(
                is_connected=sso_service.is_connected(),
                ims_url=sso_service.ims_url,
                user_info=sso_service.user_info
            )
        )

    except Exception as e:
        logger.error(
            f"IMS SSO status check error: {str(e)}",
            category=LogCategory.SECURITY,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSO 상태 확인 중 오류가 발생했습니다: {str(e)}"
        )


@router.post(
    "/disconnect/{session_id}",
    response_model=SuccessResponse[dict],
    summary="IMS SSO 연결 해제",
    description="SSO 세션을 종료합니다"
)
async def disconnect_ims_sso(session_id: str):
    """
    IMS SSO 연결 해제
    """
    try:
        sso_service = _sso_sessions.get(session_id)

        if not sso_service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SSO 세션을 찾을 수 없습니다"
            )

        # Disconnect and remove session
        sso_service.disconnect()
        del _sso_sessions[session_id]

        logger.info(
            f"IMS SSO disconnected - Session: {session_id}",
            category=LogCategory.SECURITY
        )

        return SuccessResponse(
            data={"session_id": session_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"IMS SSO disconnect error: {str(e)}",
            category=LogCategory.SECURITY,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSO 연결 해제 중 오류가 발생했습니다: {str(e)}"
        )


@router.post(
    "/query",
    response_model=SuccessResponse[IMSSSOQueryResponse],
    summary="IMS AI 지식 생성 쿼리",
    description="SSO 세션을 사용하여 AI Agent에게 쿼리를 보냅니다"
)
async def query_ims_ai(request: IMSSSOQueryRequest):
    """
    IMS AI Agent 쿼리

    SSO 세션을 통해 IMS 시스템의 정보를 기반으로
    AI Agent가 지식을 생성합니다.
    """
    try:
        sso_service = _sso_sessions.get(request.session_id)

        if not sso_service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SSO 세션을 찾을 수 없습니다. 먼저 연결해주세요."
            )

        if not sso_service.is_connected():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSO 세션이 만료되었습니다. 다시 연결해주세요."
            )

        # TODO: Implement actual AI Agent integration
        # For now, return a mock response
        response_text = f"IMS 시스템의 정보를 바탕으로 답변드립니다.\n\n'{request.query}'에 대한 지식을 생성하고 있습니다..."

        # TODO: Save knowledge to database and return knowledge_id

        logger.info(
            f"IMS AI query processed - Session: {request.session_id}",
            category=LogCategory.REQUEST
        )

        return SuccessResponse(
            data=IMSSSOQueryResponse(
                response=response_text,
                knowledge_id=None  # Will be actual ID after implementation
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"IMS AI query error: {str(e)}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 쿼리 처리 중 오류가 발생했습니다: {str(e)}"
        )
