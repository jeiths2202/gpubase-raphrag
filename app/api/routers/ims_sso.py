"""
IMS SSO API Router
IMS 시스템 SSO 연결 및 인증 관련 API
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
import asyncio
from playwright.async_api import async_playwright

from ..models.base import SuccessResponse, MetaInfo
from ..ims_sso_connector.sso.service import IMSSSOService
from ..ims_sso_connector.sso.validator import IMSSSOValidator
from ..core.logging_framework import get_logger, LogCategory
from ..services.rag_service import RAGService
from ..services.knowledge_article_service import get_knowledge_service
from ..models.knowledge_article import CreateKnowledgeRequest, KnowledgeCategory, SupportedLanguage

router = APIRouter(prefix="/ims-sso", tags=["IMS SSO"])
logger = get_logger("kms.ims_sso")

# In-memory SSO service instances (keyed by session ID)
# In production, this should be moved to Redis or database
_sso_sessions = {}

# Import scrapers
from ..ims_sso_connector.scraper.ims_profile_scraper import scrape_ims_issues_with_profile
from ..ims_sso_connector.scraper.ims_cdp_scraper import scrape_ims_issues_cdp


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

    Flow:
    1. IMS 시스템에서 관련 정보 검색 (SSO 세션 사용)
    2. RAG 서비스로 AI 응답 생성
    3. Knowledge Article로 저장 (자동)
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

        logger.info(
            f"IMS AI query started - Session: {request.session_id}, Query: {request.query[:100]}",
            category=LogCategory.REQUEST
        )

        # Step 1: Try to retrieve relevant information from IMS system
        ims_context = None
        try:
            # Attempt common IMS search endpoints
            search_endpoints = [
                "/api/v1/search",
                "/api/search",
                "/search",
                "/api/v1/knowledge/search",
                "/api/knowledge"
            ]

            for endpoint in search_endpoints:
                response = sso_service.make_request(
                    endpoint=endpoint,
                    method="GET",
                    params={"q": request.query, "limit": 5},
                    timeout=5
                )

                if response and response.status_code == 200:
                    try:
                        ims_data = response.json()
                        if ims_data and (isinstance(ims_data, list) or
                                       (isinstance(ims_data, dict) and ims_data.get('data'))):
                            ims_context = ims_data
                            logger.info(
                                f"Retrieved IMS data from endpoint: {endpoint}",
                                category=LogCategory.REQUEST
                            )
                            break
                    except Exception:
                        continue

        except Exception as e:
            # IMS search failed, continue with RAG-only approach
            logger.warning(
                f"IMS system search failed (continuing with RAG): {str(e)}",
                category=LogCategory.REQUEST
            )

        # Step 2: Generate AI response using RAG service
        rag_service = RAGService.get_instance()

        # Build enhanced query with IMS context
        enhanced_query = request.query
        if ims_context:
            context_summary = _format_ims_context(ims_context)
            enhanced_query = f"""사용자 질문: {request.query}

IMS 시스템 참고 정보:
{context_summary}

위 IMS 시스템의 정보를 참고하여 사용자 질문에 답변해주세요."""

        # Call RAG service
        rag_result = await rag_service.query(
            question=enhanced_query,
            strategy="hybrid",  # Use hybrid for best results
            language="auto",  # Auto-detect language
            top_k=5
        )

        response_text = rag_result.get("answer", "답변을 생성할 수 없습니다.")
        sources = rag_result.get("sources", [])

        # Step 3: Save as Knowledge Article (automatic)
        knowledge_id = None
        try:
            knowledge_service = get_knowledge_service()

            # Create article with IMS source attribution
            article = await knowledge_service.create_article(
                request=CreateKnowledgeRequest(
                    title=request.query[:100],  # Truncate long queries
                    content=response_text,
                    summary=f"IMS 시스템 기반 AI 생성 지식",
                    category=KnowledgeCategory.TECHNICAL,
                    tags=["IMS", "AI생성", "SSO"],
                    primary_language=SupportedLanguage.KOREAN,
                    attachments=[{
                        "type": "ims_source",
                        "url": sso_service.ims_url,
                        "session_id": request.session_id
                    }]
                ),
                author_id=f"ims_sso_{request.session_id}",
                author_name="IMS AI Agent",
                author_department="IMS System"
            )

            knowledge_id = article.id
            logger.info(
                f"Knowledge article created: {knowledge_id}",
                category=LogCategory.REQUEST
            )

        except Exception as e:
            # Knowledge save failed, but we have the response
            logger.warning(
                f"Failed to save knowledge article: {str(e)}",
                category=LogCategory.REQUEST
            )

        logger.info(
            f"IMS AI query completed - Session: {request.session_id}, Knowledge ID: {knowledge_id}",
            category=LogCategory.REQUEST
        )

        return SuccessResponse(
            data=IMSSSOQueryResponse(
                response=response_text,
                knowledge_id=knowledge_id
            ),
            meta=MetaInfo(
                message="IMS 시스템과 AI를 통해 지식이 생성되었습니다",
                extra={
                    "ims_context_used": ims_context is not None,
                    "sources_count": len(sources),
                    "strategy": "hybrid"
                }
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


def _format_ims_context(ims_data: any) -> str:
    """
    Format IMS system data into readable context for AI

    Args:
        ims_data: Raw IMS API response data

    Returns:
        Formatted string for AI context
    """
    try:
        if isinstance(ims_data, list):
            # List of results
            formatted = []
            for idx, item in enumerate(ims_data[:5], 1):  # Max 5 items
                if isinstance(item, dict):
                    title = item.get('title', item.get('name', f'항목 {idx}'))
                    content = item.get('content', item.get('description', ''))
                    formatted.append(f"{idx}. {title}\n   {content[:200]}")
                else:
                    formatted.append(f"{idx}. {str(item)[:200]}")
            return "\n".join(formatted)

        elif isinstance(ims_data, dict):
            # Dictionary response
            if 'data' in ims_data:
                return _format_ims_context(ims_data['data'])

            # Format key-value pairs
            formatted = []
            for key, value in list(ims_data.items())[:10]:  # Max 10 fields
                if isinstance(value, (str, int, float, bool)):
                    formatted.append(f"- {key}: {value}")
                elif isinstance(value, list) and value:
                    formatted.append(f"- {key}: {len(value)}개 항목")
            return "\n".join(formatted)

        else:
            return str(ims_data)[:500]  # Truncate long strings

    except Exception:
        return "IMS 데이터 형식을 파싱할 수 없습니다."


def _convert_session_cookies_to_playwright(sso_service) -> list:
    """
    Convert requests.Session cookies to Playwright format

    Args:
        sso_service: IMSSSOService instance with established session

    Returns:
        List of cookies in Playwright format
    """
    from urllib.parse import urlparse

    playwright_cookies = []
    parsed_url = urlparse(sso_service.ims_url)
    domain = parsed_url.hostname

    # Get cookies from requests.Session
    for cookie in sso_service.session.cookies:
        playwright_cookie = {
            'name': cookie.name,
            'value': cookie.value,
            'domain': cookie.domain if cookie.domain else f'.{domain}',
            'path': cookie.path if cookie.path else '/',
            'expires': int(cookie.expires) if cookie.expires else -1,
            'httpOnly': bool(cookie.has_nonstandard_attr('HttpOnly')),
            'secure': cookie.secure if hasattr(cookie, 'secure') else True,
            'sameSite': 'Lax'
        }
        playwright_cookies.append(playwright_cookie)

    return playwright_cookies


class IMSScrapeIssuesRequest(BaseModel):
    """IMS 이슈 목록 스크래핑 요청"""
    session_id: str = Field(..., description="SSO 세션 ID")
    search_type: str = Field(default="1", description="검색 타입")
    menu_code: str = Field(default="issue_search", description="메뉴 코드")
    wait_for_selector: Optional[str] = Field(None, description="대기할 CSS 셀렉터")
    max_wait_time: int = Field(default=10000, description="최대 대기 시간 (밀리초)")


class IMSScrapeIssuesResponse(BaseModel):
    """IMS 이슈 목록 스크래핑 응답"""
    issues: list = Field(..., description="이슈 목록")
    count: int = Field(..., description="이슈 개수")
    scraping_method: str = Field(..., description="스크래핑 방법")


@router.post(
    "/scrape-issues",
    response_model=SuccessResponse[IMSScrapeIssuesResponse],
    summary="IMS 이슈 목록 스크래핑",
    description="SSO 세션을 사용하여 IMS 이슈 목록 페이지를 동적으로 스크래핑합니다"
)
async def scrape_ims_issues_endpoint(request: IMSScrapeIssuesRequest):
    """
    IMS 이슈 목록 페이지 스크래핑

    SSO 세션의 쿠키를 재사용하여 동적 웹 페이지 스크래핑 수행.
    Chrome이 실행 중이어도 작동합니다 (세션 쿠키 재사용).

    Flow:
    1. SSO 세션에서 쿠키 추출
    2. Playwright 형식으로 변환
    3. 동적 스크래핑 수행
    4. 이슈 목록 반환
    """
    try:
        # Get SSO service from session
        sso_service = _sso_sessions.get(request.session_id)

        if not sso_service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SSO 세션을 찾을 수 없습니다. 먼저 /connect를 호출하세요."
            )

        if not sso_service.is_connected():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSO 세션이 만료되었습니다. 다시 연결해주세요."
            )

        logger.info(
            f"IMS scraping started - Session: {request.session_id}, "
            f"SearchType: {request.search_type}",
            category=LogCategory.REQUEST
        )

        # Convert session cookies to Playwright format
        playwright_cookies = _convert_session_cookies_to_playwright(sso_service)

        if not playwright_cookies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SSO 세션에 쿠키가 없습니다"
            )

        logger.info(
            f"Converted {len(playwright_cookies)} cookies for scraping",
            category=LogCategory.REQUEST
        )

        # Import scraper
        from ..ims_sso_connector.scraper.ims_issue_scraper import IMSIssueScraper

        # Perform scraping with session cookies
        async with IMSIssueScraper(
            ims_url=sso_service.ims_url,
            cookies=playwright_cookies,  # Use SSO session cookies
            headless=True
        ) as scraper:
            issues = await scraper.scrape_issue_list(
                search_type=request.search_type,
                menu_code=request.menu_code,
                wait_for_selector=request.wait_for_selector,
                max_wait_time=request.max_wait_time
            )

        logger.info(
            f"IMS scraping completed - Session: {request.session_id}, "
            f"Issues found: {len(issues)}",
            category=LogCategory.REQUEST
        )

        return SuccessResponse(
            data=IMSScrapeIssuesResponse(
                issues=issues,
                count=len(issues),
                scraping_method="session_cookies"
            ),
            meta=MetaInfo(
                message=f"Successfully scraped {len(issues)} issues from IMS",
                extra={
                    "session_id": request.session_id,
                    "ims_url": sso_service.ims_url,
                    "search_type": request.search_type,
                    "chrome_not_required": True
                }
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"IMS scraping error: {str(e)}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"이슈 스크래핑 중 오류가 발생했습니다: {str(e)}"
        )


# ============================================================================
# Chrome Profile Scraping (No Cookie Copy Required)
# ============================================================================


class IMSScrapeWithProfileRequest(BaseModel):
    """Chrome 프로필을 사용한 IMS 스크래핑 요청"""
    ims_url: str = Field(default="https://ims.tmaxsoft.com", description="IMS 시스템 URL")
    user_data_dir: Optional[str] = Field(None, description="Chrome User Data 디렉토리 (None이면 자동 탐지)")
    profile: str = Field(default="Default", description="Chrome 프로필 이름")
    search_type: str = Field(default="1", description="검색 타입")
    menu_code: str = Field(default="issue_search", description="메뉴 코드")
    headless: bool = Field(default=True, description="헤드리스 모드")


class IMSScrapeWithProfileResponse(BaseModel):
    """Chrome 프로필 스크래핑 응답"""
    issues: List[Dict[str, Any]] = Field(..., description="스크래핑된 이슈 목록")
    count: int = Field(..., description="이슈 개수")
    scraping_method: str = Field(default="chrome_profile", description="스크래핑 방식")
    profile_used: str = Field(..., description="사용된 Chrome 프로필")


@router.post("/scrape-with-profile")
async def scrape_ims_with_profile(
    request: IMSScrapeWithProfileRequest
) -> SuccessResponse[IMSScrapeWithProfileResponse]:
    """
    Chrome 프로필의 로그인 세션을 사용하여 IMS 스크래핑

    ⚠️ 중요: Chrome이 실행 중이면 실패합니다.
    Chrome을 완전히 종료한 상태에서 호출해야 합니다.

    장점:
    - 쿠키 복사 불필요
    - 디버깅 모드 불필요
    - 로그인 세션 자동 인식
    - Production 환경에서 사용 가능

    사용 흐름:
    1. Chrome에서 https://ims.tmaxsoft.com 로그인
    2. Chrome 완전 종료
    3. 이 API 호출 (Playwright가 Chrome 프로필 사용)
    4. 스크래핑 완료 후 Chrome 재시작 가능
    """
    try:
        logger.info(
            f"IMS profile scraping started - URL: {request.ims_url}, Profile: {request.profile}",
            category=LogCategory.REQUEST
        )

        # Chrome 프로필을 사용하여 스크래핑
        issues = await scrape_ims_issues_with_profile(
            ims_url=request.ims_url,
            user_data_dir=request.user_data_dir,
            profile=request.profile,
            search_type=request.search_type,
            menu_code=request.menu_code,
            headless=request.headless
        )

        logger.info(
            f"IMS profile scraping completed - Issues found: {len(issues)}",
            category=LogCategory.REQUEST
        )

        return SuccessResponse(
            data=IMSScrapeWithProfileResponse(
                issues=issues,
                count=len(issues),
                scraping_method="chrome_profile",
                profile_used=request.profile
            ),
            meta=MetaInfo(
                message=f"Successfully scraped {len(issues)} issues from IMS using Chrome profile",
                extra={
                    "ims_url": request.ims_url,
                    "profile": request.profile,
                    "search_type": request.search_type,
                    "chrome_required": "must_be_closed",
                    "session_reuse": True
                }
            )
        )

    except RuntimeError as e:
        # Chrome 실행 중 오류
        if "Chrome is running" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chrome이 실행 중입니다. Chrome을 완전히 종료한 후 다시 시도해주세요."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스크래핑 오류: {str(e)}"
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chrome 프로필을 찾을 수 없습니다: {str(e)}"
        )

    except Exception as e:
        logger.error(
            f"IMS profile scraping error: {str(e)}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"이슈 스크래핑 중 오류가 발생했습니다: {str(e)}"
        )


# ============================================================================
# Chrome CDP Scraping (Chrome Stays Running) - RECOMMENDED
# ============================================================================


class IMSScrapeWithCDPRequest(BaseModel):
    """Chrome CDP를 사용한 IMS 스크래핑 요청"""
    ims_url: str = Field(default="https://ims.tmaxsoft.com", description="IMS 시스템 URL")
    cdp_endpoint: str = Field(default="http://localhost:9222", description="Chrome DevTools Protocol 엔드포인트")
    search_type: str = Field(default="1", description="검색 타입")
    menu_code: str = Field(default="issue_search", description="메뉴 코드")
    max_wait_time: int = Field(default=15000, description="최대 대기 시간 (ms)")


class IMSScrapeWithCDPResponse(BaseModel):
    """Chrome CDP 스크래핑 응답"""
    issues: List[Dict[str, Any]] = Field(..., description="스크래핑된 이슈 목록")
    count: int = Field(..., description="이슈 개수")
    scraping_method: str = Field(default="chrome_cdp", description="스크래핑 방식")
    cdp_endpoint: str = Field(..., description="사용된 CDP 엔드포인트")


@router.post("/scrape-with-cdp")
async def scrape_ims_with_cdp(
    request: IMSScrapeWithCDPRequest
) -> SuccessResponse[IMSScrapeWithCDPResponse]:
    """
    Chrome DevTools Protocol을 사용하여 실행 중인 Chrome으로 IMS 스크래핑

    ✅ 장점: Chrome을 종료하지 않고 사용 가능!

    Prerequisites:
    1. Chrome을 디버깅 모드로 시작:
       - 바탕화면의 'Chrome (Debug Mode)' 바로가기 사용
       - 또는 chrome.exe --remote-debugging-port=9222

    2. Chrome에서 https://ims.tmaxsoft.com 로그인

    3. Chrome을 실행한 상태로 이 API 호출

    장점:
    - Chrome 종료 불필요
    - 로그인 세션 자동 사용
    - 쿠키 복사 불필요
    - Production 환경 적합

    사용 흐름:
    1. Chrome (Debug Mode) 바로가기로 Chrome 시작
    2. https://ims.tmaxsoft.com 로그인
    3. 이 API 호출 (Chrome 실행 유지)
    4. 스크래핑 완료 후 Chrome 계속 사용 가능
    """
    try:
        logger.info(
            f"IMS CDP scraping started - URL: {request.ims_url}, CDP: {request.cdp_endpoint}",
            category=LogCategory.REQUEST
        )

        # Chrome CDP를 사용하여 스크래핑
        issues = await scrape_ims_issues_cdp(
            ims_url=request.ims_url,
            cdp_endpoint=request.cdp_endpoint,
            search_type=request.search_type,
            menu_code=request.menu_code,
            max_wait_time=request.max_wait_time
        )

        logger.info(
            f"IMS CDP scraping completed - Issues found: {len(issues)}",
            category=LogCategory.REQUEST
        )

        return SuccessResponse(
            data=IMSScrapeWithCDPResponse(
                issues=issues,
                count=len(issues),
                scraping_method="chrome_cdp",
                cdp_endpoint=request.cdp_endpoint
            ),
            meta=MetaInfo(
                message=f"Successfully scraped {len(issues)} issues from IMS using Chrome CDP",
                extra={
                    "ims_url": request.ims_url,
                    "cdp_endpoint": request.cdp_endpoint,
                    "search_type": request.search_type,
                    "chrome_required": "running_with_debug_mode",
                    "session_reuse": True,
                    "no_chrome_restart": True
                }
            )
        )

    except Exception as e:
        error_msg = str(e)

        # CDP 연결 오류 감지
        if "CDP" in error_msg or "connect" in error_msg.lower() or "9222" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Chrome 디버깅 모드가 실행 중이지 않습니다. "
                    "바탕화면의 'Chrome (Debug Mode)' 바로가기로 Chrome을 시작해주세요."
                )
            )

        logger.error(
            f"IMS CDP scraping error: {error_msg}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"이슈 스크래핑 중 오류가 발생했습니다: {error_msg}"
        )


# Cookie storage for Chrome Extension method
_stored_cookies = {}


class CookieData(BaseModel):
    """Individual cookie data from Chrome Extension"""
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None
    httpOnly: bool = False
    secure: bool = False
    sameSite: Optional[str] = None


class UploadCookiesRequest(BaseModel):
    """Request to upload cookies from Chrome Extension"""
    cookies: list[CookieData] = Field(..., description="List of cookies extracted from Chrome")


class UploadCookiesResponse(BaseModel):
    """Response after uploading cookies"""
    cookie_count: int = Field(..., description="Number of cookies stored")
    storage_id: str = Field(..., description="ID for retrieving these cookies later")


@router.post(
    "/upload-cookies",
    response_model=SuccessResponse[UploadCookiesResponse],
    summary="Upload IMS Cookies from Chrome Extension",
    description="Store cookies extracted from Chrome Extension for use in scraping"
)
async def upload_ims_cookies(request: UploadCookiesRequest):
    """
    Upload IMS Authentication Cookies from Chrome Extension

    This endpoint receives cookies extracted by the Chrome Extension
    from an active IMS session and stores them for use in Playwright scraping.

    Flow:
    1. User logs into IMS in their regular Chrome
    2. Chrome Extension extracts cookies via chrome.cookies API
    3. Extension POSTs cookies to this endpoint
    4. Backend stores cookies with unique ID
    5. Playwright uses stored cookies for scraping

    Benefits:
    - No Chrome restart needed
    - Works with SSO/OAuth authentication
    - Uses cookies from active session
    - No profile isolation issues
    """
    try:
        # Generate storage ID
        storage_id = str(uuid.uuid4())

        # Convert cookie data to Playwright format
        playwright_cookies = []
        for cookie in request.cookies:
            playwright_cookie = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "httpOnly": cookie.httpOnly,
                "secure": cookie.secure,
            }

            # Add optional fields
            if cookie.expires:
                playwright_cookie["expires"] = cookie.expires
            if cookie.sameSite:
                playwright_cookie["sameSite"] = cookie.sameSite

            playwright_cookies.append(playwright_cookie)

        # Store cookies
        _stored_cookies[storage_id] = {
            "cookies": playwright_cookies,
            "uploaded_at": uuid.uuid1().time,
            "cookie_count": len(playwright_cookies)
        }

        logger.info(
            f"Stored {len(playwright_cookies)} cookies with ID: {storage_id}",
            category=LogCategory.SECURITY
        )

        return SuccessResponse(
            data=UploadCookiesResponse(
                cookie_count=len(playwright_cookies),
                storage_id=storage_id
            ),
            meta=MetaInfo(
                request_id=str(uuid.uuid4())
            )
        )

    except Exception as e:
        logger.error(
            f"Cookie upload error: {str(e)}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"쿠키 업로드 중 오류가 발생했습니다: {str(e)}"
        )


class ScrapeWithCookiesRequest(BaseModel):
    """Request to scrape IMS using stored cookies"""
    storage_id: str = Field(..., description="Storage ID from upload-cookies endpoint")
    ims_url: str = Field(default="https://ims.tmaxsoft.com", description="IMS URL")
    search_type: str = Field(default="1", description="Search type")
    menu_code: str = Field(default="issue_search", description="Menu code")


class ScrapeWithCookiesResponse(BaseModel):
    """Response from cookie-based scraping"""
    issues: list[dict]
    count: int
    scraping_method: str
    storage_id: str


@router.post(
    "/scrape-with-cookies",
    response_model=SuccessResponse[ScrapeWithCookiesResponse],
    summary="Scrape IMS using stored cookies",
    description="Use cookies from Chrome Extension to scrape IMS without authentication"
)
async def scrape_ims_with_cookies(request: ScrapeWithCookiesRequest):
    """
    Scrape IMS using cookies uploaded from Chrome Extension

    Prerequisites:
    1. Use /upload-cookies to store cookies first
    2. Use the returned storage_id in this request

    This method:
    - Uses Playwright with stored cookies
    - No Chrome profile needed
    - No Chrome restart needed
    - Works with SSO authentication
    """
    try:
        # Retrieve stored cookies
        cookie_data = _stored_cookies.get(request.storage_id)

        if not cookie_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="저장된 쿠키를 찾을 수 없습니다. /upload-cookies를 먼저 호출해주세요."
            )

        cookies = cookie_data["cookies"]

        logger.info(
            f"Starting IMS scraping with {len(cookies)} stored cookies",
            category=LogCategory.REQUEST
        )

        # Playwright scraping with stored cookies
        playwright = None
        browser = None
        context = None
        page = None

        try:
            # 1. Start Playwright
            logger.info("Starting Playwright browser...", category=LogCategory.REQUEST)
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)

            # 2. Create browser context with cookies
            context = await browser.new_context()
            await context.add_cookies(cookies)
            logger.info(
                f"Added {len(cookies)} cookies to browser context",
                category=LogCategory.REQUEST
            )

            # 3. Create new page and navigate to IMS
            page = await context.new_page()
            url = f"{request.ims_url.rstrip('/')}/tody/ims/issue/issueSearchList.do?searchType={request.search_type}&menuCode={request.menu_code}"
            logger.info(f"Navigating to: {url}", category=LogCategory.REQUEST)

            await page.goto(url, wait_until='networkidle', timeout=30000)
            logger.info("Page loaded successfully", category=LogCategory.REQUEST)

            # 4. Wait for dynamic content to load
            await asyncio.sleep(2)

            # 5. Extract issues from DOM
            issues = await page.evaluate("""
                () => {
                    const issues = [];

                    // Method 1: Extract from table
                    const table = document.querySelector('table.issue-list, table.data-table, table[id*="issue"]');
                    if (table) {
                        const rows = table.querySelectorAll('tbody tr');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length > 0) {
                                const issue = {
                                    id: cells[0]?.textContent?.trim(),
                                    title: cells[1]?.textContent?.trim(),
                                    status: cells[2]?.textContent?.trim(),
                                    priority: cells[3]?.textContent?.trim(),
                                    assignee: cells[4]?.textContent?.trim(),
                                    created_at: cells[5]?.textContent?.trim(),
                                    updated_at: cells[6]?.textContent?.trim()
                                };
                                issues.push(issue);
                            }
                        });
                    }

                    // Method 2: Extract from data attributes
                    if (issues.length === 0) {
                        const items = document.querySelectorAll('[data-issue-id], .issue-item, .issue-row');
                        items.forEach(item => {
                            const issue = {
                                id: item.dataset.issueId || item.querySelector('[data-field="id"]')?.textContent,
                                title: item.dataset.issueTitle || item.querySelector('[data-field="title"]')?.textContent,
                                status: item.dataset.issueStatus || item.querySelector('[data-field="status"]')?.textContent,
                                priority: item.dataset.issuePriority || item.querySelector('[data-field="priority"]')?.textContent
                            };
                            if (issue.id) {
                                issues.push(issue);
                            }
                        });
                    }

                    // Method 3: Extract from JavaScript global variables
                    if (issues.length === 0 && window.issueList) {
                        return window.issueList;
                    }

                    if (issues.length === 0 && window.gridData) {
                        return window.gridData;
                    }

                    return issues;
                }
            """)

            logger.info(
                f"Extracted {len(issues)} issues from DOM",
                category=LogCategory.REQUEST
            )

            return SuccessResponse(
                data=ScrapeWithCookiesResponse(
                    issues=issues or [],
                    count=len(issues) if issues else 0,
                    scraping_method="playwright_with_cookies",
                    storage_id=request.storage_id
                ),
                meta=MetaInfo(
                    request_id=str(uuid.uuid4())
                )
            )

        finally:
            # Cleanup: Close browser resources
            if page:
                await page.close()
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Cookie-based scraping error: {str(e)}",
            category=LogCategory.REQUEST,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"쿠키 기반 스크래핑 중 오류가 발생했습니다: {str(e)}"
        )
