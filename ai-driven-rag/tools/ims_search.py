"""IMS (Issue Management System) search tool - Real-time crawling from IMS website."""
import re
import asyncio
import logging
from typing import Any, List, Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import Tool

logger = logging.getLogger(__name__)


class IMSCrawler:
    """
    Lightweight IMS crawler for real-time search.

    Credentials can be set via:
    1. set_credentials() method (user input at runtime)
    2. Constructor arguments
    3. Environment variables (fallback)
    """

    def __init__(
        self,
        base_url: str = "https://ims.tmaxsoft.com",
        username: str = "",
        password: str = "",
        product_codes: List[str] | None = None,
    ):
        self.base_url = base_url
        self._username = username
        self._password = password
        self.product_codes = product_codes or []

        self._session: Optional[requests.Session] = None
        self._authenticated = False
        self._user_name = ""
        self._user_grade = ""

    def set_credentials(self, username: str, password: str) -> None:
        """Set IMS credentials dynamically (from user input)."""
        self._username = username
        self._password = password
        # Reset authentication state to force re-login
        self._authenticated = False
        if self._session:
            self._session.close()
            self._session = None
        logger.info(f"[IMS Crawler] Credentials set for user: {username}")

    def has_credentials(self) -> bool:
        """Check if credentials are configured."""
        return bool(self._username and self._password)

    def clear_credentials(self) -> None:
        """Clear stored credentials and session."""
        self._username = ""
        self._password = ""
        self._authenticated = False
        if self._session:
            self._session.close()
            self._session = None
        logger.info("[IMS Crawler] Credentials cleared")

    def _ensure_session(self) -> requests.Session:
        """Ensure HTTP session is initialized."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            })
        return self._session

    def _authenticate_sync(self) -> bool:
        """Synchronous authentication."""
        if not self._username or not self._password:
            logger.error("[IMS Crawler] No credentials provided (IMS_USERNAME, IMS_PASSWORD)")
            return False

        session = self._ensure_session()

        # Get login page first (for cookies)
        login_url = f"{self.base_url}/tody/auth/login.do"
        session.get(login_url, timeout=30)

        # Submit login form
        response = session.post(
            login_url,
            data={'id': self._username, 'password': self._password},
            allow_redirects=True,
            timeout=30
        )

        # Check if login succeeded
        if '/login' in response.url or '/auth/login' in response.url:
            logger.error("[IMS Crawler] Authentication failed - redirected back to login")
            self._authenticated = False
            return False

        self._authenticated = True

        # Try to extract user info
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            user_name_elem = soup.find('input', {'name': 'userName'})
            user_grade_elem = soup.find('input', {'name': 'userGrade'})
            if user_name_elem:
                self._user_name = user_name_elem.get('value', self._username)
            if user_grade_elem:
                self._user_grade = user_grade_elem.get('value', 'TMAX')
        except Exception:
            self._user_name = self._username
            self._user_grade = 'TMAX'

        logger.info(f"[IMS Crawler] Authentication successful for user: {self._username}")
        return True

    async def authenticate(self) -> bool:
        """Authenticate with IMS system."""
        return await asyncio.to_thread(self._authenticate_sync)

    def _search_issues_sync(
        self,
        query: str,
        limit: int = 50,
    ) -> List[dict]:
        """Synchronous search implementation."""
        session = self._ensure_session()
        all_issues: List[dict] = []
        total_count = None
        page = 1
        max_pages = 5  # Limit pages for performance

        logger.info(f"[IMS Crawler] Searching for '{query}' in {len(self.product_codes)} products")

        while page <= max_pages:
            params = {
                'reSearchYN': 'Y',
                'searchType': '1',
                'pageIndex': str(page),
                'pageSize': '100',
                'keyword': query,
                'menuCode': 'issue_search',
                'menuLink': '/ims/issue/issueSearchList.do',
                'moveSearchAction': 'ims/issue/issueSearchList.do',
                'orderType': 'desc',
                'listType': '1',
                'queryId': 'ims.issueSearch.findIssueSearch',
                'queryIdDetail': 'ims.profile.findUserIssueColumns',
                'reportType': 'R101',
                'reportLink': '/util/saveSearchList.do',
                'taggingWordOption': 'equals',
                'userId': self._username,
                'userName': self._user_name or self._username,
                'userGrade': self._user_grade or 'TMAX',
                'productCodes': self.product_codes,
            }

            search_url = f"{self.base_url}/tody/ims/issue/issueSearchList.do"
            try:
                response = session.get(search_url, params=params, headers={
                    'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
                }, timeout=60)
            except Exception as e:
                logger.error(f"[IMS Crawler] Request error: {e}")
                break

            # Get total count on first page
            if total_count is None:
                total_count = self._get_total_count(response.text)
                logger.info(f"[IMS Crawler] Total count: {total_count}")

            # Parse issues from this page
            page_issues = self._parse_search_results(response.text)
            logger.info(f"[IMS Crawler] Page {page}: {len(page_issues)} issues")

            if not page_issues:
                break

            all_issues.extend(page_issues)

            # Check if we have enough
            if len(all_issues) >= limit or len(all_issues) >= total_count:
                break

            page += 1

        logger.info(f"[IMS Crawler] Search completed: {len(all_issues)} issues")
        return all_issues[:limit]

    async def search_issues(
        self,
        query: str,
        limit: int = 50,
    ) -> List[dict]:
        """Search issues from IMS."""
        if not self._authenticated:
            authenticated = await self.authenticate()
            if not authenticated:
                return []

        return await asyncio.to_thread(self._search_issues_sync, query, limit)

    def _get_total_count(self, html: str) -> int:
        """Extract total count from search result HTML."""
        match = re.search(r'\[\s*[Tt]otal\s+(\d+)\s*\]', html)
        if match:
            return int(match.group(1))

        soup = BeautifulSoup(html, 'html.parser')
        total_input = soup.find('input', {'id': 'totalCount'})
        if total_input and total_input.get('value'):
            try:
                return int(total_input.get('value'))
            except ValueError:
                pass

        match = re.search(r'totalCount["\']?\s*[=:]\s*["\']?(\d+)', html)
        if match:
            return int(match.group(1))

        return 0

    def _parse_search_results(self, html: str) -> List[dict]:
        """Parse issues from search results HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        issues = []

        rows = soup.find_all('tr', onclick=re.compile(r'popBlankIssueView'))

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue

            onclick = row.get('onclick', '')
            id_match = re.search(r"popBlankIssueView\s*\(\s*['\"](\d+)['\"]", onclick)
            issue_id = id_match.group(1) if id_match else ''

            if not issue_id:
                continue

            def get_cell_text(idx: int) -> str:
                if len(cells) > idx:
                    return cells[idx].get_text(strip=True)
                return ''

            # Parse issued date
            issued_date = None
            date_str = get_cell_text(10)
            if date_str:
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']:
                    try:
                        issued_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue

            title = re.sub(r'\s+', ' ', get_cell_text(6)).strip()

            issue = {
                "ims_id": issue_id,
                "title": title or f"Issue {issue_id}",
                "category": get_cell_text(2),
                "product": get_cell_text(3),
                "version": get_cell_text(4),
                "module": get_cell_text(5),
                "customer": get_cell_text(7),
                "project": get_cell_text(8),
                "reporter": get_cell_text(9),
                "issued_date": issued_date.isoformat() if issued_date else "",
                "url": f"{self.base_url}/tody/ims/issue/issueView.do?issueId={issue_id}&menuCode=issue_search",
                "source": "ims_live",
            }
            issues.append(issue)

        return issues

    def _get_issue_detail_sync(self, issue_id: str) -> dict:
        """Get detailed information about a specific issue."""
        session = self._ensure_session()

        try:
            detail_url = f"{self.base_url}/tody/ims/issue/issueView.do"
            response = session.post(
                detail_url,
                data={'issueId': issue_id, 'menuCode': 'issue_search'},
                headers={'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do"},
                timeout=60
            )

            return self._parse_issue_detail(response.text, issue_id)

        except Exception as e:
            logger.error(f"[IMS Crawler] Failed to get issue detail {issue_id}: {e}")
            return {"ims_id": issue_id, "error": str(e)}

    async def get_issue_detail(self, issue_id: str) -> dict:
        """Get detailed information about a specific issue."""
        if not self._authenticated:
            authenticated = await self.authenticate()
            if not authenticated:
                return {"ims_id": issue_id, "error": "Authentication failed"}

        return await asyncio.to_thread(self._get_issue_detail_sync, issue_id)

    def _parse_issue_detail(self, html: str, issue_id: str) -> dict:
        """Parse issue detail from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        def get_table_field(label: str) -> str:
            pattern = rf'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
            match = re.search(pattern, html, re.DOTALL | re.I)
            if match:
                value = re.sub(r'<[^>]+>', '', match.group(1))
                return value.replace('&nbsp;', ' ').strip()

            for td in soup.find_all('td', class_='tableHeaderTitle'):
                if label.lower() in td.get_text(strip=True).lower():
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        return next_td.get_text(strip=True).replace('\xa0', ' ')
            return ''

        # Extract subject
        subject = ""
        subject_td = soup.find('td', class_='tableHeaderTitle', string=re.compile(r'Subject', re.I))
        if subject_td:
            subject_value = subject_td.find_next_sibling('td')
            if subject_value:
                subject = subject_value.get_text(strip=True).replace('\xa0', ' ')
        if not subject:
            subject = get_table_field('Subject')

        # Parse Issue Details (description)
        issue_details = ""
        desc_match = re.search(r'id=["\']IssueDescriptionDiv["\'][^>]*>(.*?)</div>\s*<!--', html, re.DOTALL | re.I)
        if desc_match:
            desc_html = desc_match.group(1)
            issue_details = re.sub(r'<[^>]+>', ' ', desc_html)
            issue_details = issue_details.replace('&nbsp;', ' ').replace('&#39;', "'")
            issue_details = re.sub(r'\s+', ' ', issue_details).strip()

        # Parse Action Log
        action_texts = []
        comm_desc_pattern = r'<div[^>]*class=["\'][^"\']*commDescTR[^"\']*["\'][^>]*>(.*?)</div>'
        comm_desc_matches = re.findall(comm_desc_pattern, html, re.DOTALL | re.I)
        for match in comm_desc_matches:
            text = re.sub(r'<[^>]+>', ' ', match)
            text = text.replace('&nbsp;', ' ').replace('&#39;', "'")
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 5:
                action_texts.append(text)
        action_log_text = " | ".join(action_texts)[:5000]

        return {
            "ims_id": issue_id,
            "title": re.sub(r'\s+', ' ', subject).strip() or f"Issue {issue_id}",
            "description": issue_details[:3000],
            "status": get_table_field('Status'),
            "priority": get_table_field('Priority') or get_table_field('Urgency'),
            "category": get_table_field('Category'),
            "product": get_table_field('Product'),
            "version": get_table_field('Version'),
            "module": get_table_field('Module'),
            "customer": get_table_field('Customer'),
            "reporter": get_table_field('Reporter') or get_table_field('Register'),
            "project": get_table_field('Project'),
            "action_log": action_log_text,
            "url": f"{self.base_url}/tody/ims/issue/issueView.do?issueId={issue_id}&menuCode=issue_search",
            "source": "ims_live",
        }

    def close(self):
        """Close HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
        self._authenticated = False


# Singleton crawler instance
_ims_crawler: IMSCrawler | None = None


def _get_ims_crawler() -> IMSCrawler:
    """Get or create IMS crawler singleton."""
    global _ims_crawler
    if _ims_crawler is None:
        from config import config
        # Initialize with env vars as fallback, but credentials can be set later via ims_login
        _ims_crawler = IMSCrawler(
            base_url=config.ims_base_url,
            username=config.ims_username,  # May be empty
            password=config.ims_password,  # May be empty
            product_codes=config.ims_product_codes,
        )
        logger.info(f"[IMS Crawler] Initialized with base_url={config.ims_base_url}")
    return _ims_crawler


def _set_ims_credentials(username: str, password: str) -> None:
    """Set IMS credentials on the crawler singleton."""
    crawler = _get_ims_crawler()
    crawler.set_credentials(username, password)


class IMSSearchTool(Tool):
    """Search issues from TmaxSoft IMS by crawling in real-time."""

    name = "ims_search"
    description = """Search issues/bugs from IMS (Issue Management System) in real-time.
Use this tool when:
- User asks about bugs, issues, defects, or problems
- User mentions IMS, issue tracking, or bug reports
- User asks about specific error cases or customer issues
- Query contains issue IDs or bug numbers

Returns list of issues with title, status, priority, and product info.

⚠️ IMPORTANT: If login_required=true is returned, use ims_login tool to get credentials from user FIRST, then retry ims_search."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - use EXACT user keywords, do not add extra terms",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 20)",
                "default": 20,
            },
            "get_details": {
                "type": "boolean",
                "description": "Whether to fetch detailed info for each issue (slower)",
                "default": False,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str,
        limit: int = 20,
        get_details: bool = False,
    ) -> dict:
        """Execute IMS search via real-time crawling."""
        try:
            crawler = _get_ims_crawler()

            # Check if credentials are configured
            if not crawler.has_credentials():
                return {
                    "query": query,
                    "error": "IMS 로그인이 필요합니다. ims_login 도구를 사용하여 사용자에게 ID/비밀번호를 요청하세요.",
                    "results": [],
                    "total": 0,
                    "login_required": True,
                }

            # Search issues
            issues = await crawler.search_issues(query, limit=limit)

            if not issues:
                return {
                    "query": query,
                    "results": [],
                    "total": 0,
                    "message": "No issues found or authentication failed",
                    "search_strategy": "ims_live",
                }

            # Optionally fetch detailed info
            if get_details and issues:
                detailed_issues = []
                for issue in issues[:min(5, len(issues))]:  # Limit detail fetching
                    detail = await crawler.get_issue_detail(issue["ims_id"])
                    # Merge basic info with details
                    merged = {**issue, **detail}
                    detailed_issues.append(merged)
                # Add remaining issues without details
                detailed_issues.extend(issues[5:])
                issues = detailed_issues

            return {
                "query": query,
                "results": issues,
                "total": len(issues),
                "search_strategy": "ims_live",
                "login_required": False,
            }

        except Exception as e:
            logger.error(f"[IMS Search] Error: {e}")
            return {
                "query": query,
                "error": str(e),
                "results": [],
                "total": 0,
            }

    async def close(self):
        """Close crawler resources."""
        global _ims_crawler
        if _ims_crawler:
            _ims_crawler.close()
            _ims_crawler = None


class IMSDetailTool(Tool):
    """Get detailed information about a specific IMS issue."""

    name = "ims_detail"
    description = """Get detailed information about a specific IMS issue.
Use this tool when:
- User asks for details about a specific issue ID
- User wants to see the full description, action log, or comments
- After ims_search to get more info about specific results

⚠️ Requires IMS login first. If login_required=true, use ims_login tool."""

    parameters = {
        "type": "object",
        "properties": {
            "issue_id": {
                "type": "string",
                "description": "IMS issue ID (e.g., '304640')",
            },
        },
        "required": ["issue_id"],
    }

    async def execute(self, issue_id: str) -> dict:
        """Get detailed information about a specific issue."""
        try:
            crawler = _get_ims_crawler()

            if not crawler.has_credentials():
                return {
                    "issue_id": issue_id,
                    "error": "IMS 로그인이 필요합니다.",
                    "login_required": True,
                }

            return await crawler.get_issue_detail(issue_id)

        except Exception as e:
            logger.error(f"[IMS Detail] Error: {e}")
            return {
                "issue_id": issue_id,
                "error": str(e),
            }

    async def close(self):
        """No cleanup needed - shares crawler with IMSSearchTool."""
        pass


class IMSLoginTool(Tool):
    """Tool for IMS login - receives credentials from user."""

    name = "ims_login"
    description = """Set IMS login credentials received from user.
Use this tool when:
- ims_search returns login_required=true
- User provides their IMS ID and password

IMPORTANT:
- If user has NOT provided credentials yet, return a message asking for ID/password
- If user HAS provided credentials, call this tool with username and password parameters

Example flow:
1. ims_search returns login_required=true
2. Ask user: "IMS 검색을 위해 로그인이 필요합니다. IMS ID와 비밀번호를 입력해주세요."
3. User responds with credentials
4. Call ims_login(username="user_id", password="user_pw")
5. Retry ims_search"""

    parameters = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "IMS login ID provided by user",
            },
            "password": {
                "type": "string",
                "description": "IMS password provided by user",
            },
        },
        "required": ["username", "password"],
    }

    async def execute(self, username: str, password: str) -> dict:
        """Set IMS credentials and verify login."""
        if not username or not password:
            return {
                "success": False,
                "error": "Username and password are required",
                "message": "IMS ID와 비밀번호를 모두 입력해주세요.",
            }

        try:
            # Set credentials on the crawler
            _set_ims_credentials(username, password)

            # Try to authenticate
            crawler = _get_ims_crawler()
            authenticated = await crawler.authenticate()

            if authenticated:
                return {
                    "success": True,
                    "message": f"IMS 로그인 성공: {username}",
                    "username": username,
                }
            else:
                # Clear failed credentials
                crawler.clear_credentials()
                return {
                    "success": False,
                    "error": "Authentication failed",
                    "message": "IMS 로그인 실패. ID와 비밀번호를 확인해주세요.",
                }

        except Exception as e:
            logger.error(f"[IMS Login] Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"IMS 로그인 중 오류 발생: {e}",
            }

    async def close(self):
        """No cleanup needed."""
        pass


class IMSLogoutTool(Tool):
    """Tool to clear IMS credentials."""

    name = "ims_logout"
    description = """Clear stored IMS credentials and logout.
Use this tool when:
- User wants to logout from IMS
- Need to switch to different IMS account"""

    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self) -> dict:
        """Clear IMS credentials."""
        crawler = _get_ims_crawler()
        crawler.clear_credentials()
        return {
            "success": True,
            "message": "IMS 로그아웃 완료",
        }

    async def close(self):
        """No cleanup needed."""
        pass
