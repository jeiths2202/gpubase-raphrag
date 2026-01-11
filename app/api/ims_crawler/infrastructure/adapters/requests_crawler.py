"""
Requests-based Crawler Adapter - Lightweight HTTP implementation

Uses requests library instead of Playwright for faster, lighter crawling.
No browser overhead - pure HTTP requests with HTML parsing.
"""

import re
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timezone
from uuid import uuid4

import requests
from bs4 import BeautifulSoup

from ...domain.entities import Issue, Attachment, UserCredentials, IssueStatus, IssuePriority
from ...domain.entities.attachment import AttachmentType
from ..ports.crawler_port import CrawlerPort
from ..services.credential_encryption_service import CredentialEncryptionService

logger = logging.getLogger(__name__)


class RequestsBasedCrawler(CrawlerPort):
    """
    Requests-based crawler implementation.

    Lightweight alternative to PlaywrightCrawler using pure HTTP requests.
    Faster and uses less memory than browser-based crawling.

    Key differences from Playwright:
    - No JavaScript execution (server-side rendering only)
    - No browser overhead (~50MB vs ~500MB)
    - Faster request/response cycle
    - Pagination handled via multiple HTTP requests
    """

    # OpenFrame product codes for filtering
    OPENFRAME_PRODUCTS = [
        '128', '520', '129', '123', '500', '137', '141', '126',
        '147', '145', '135', '143', '138', '134', '142', '510', '127', '124',
        '640', '425',  # ProSort, ProTrieve
    ]

    def __init__(
        self,
        encryption_service: CredentialEncryptionService,
        base_url: str = "https://ims.tmaxsoft.com",
        max_workers: int = 5
    ):
        """
        Initialize requests-based crawler.

        Args:
            encryption_service: Service to decrypt user credentials
            base_url: IMS base URL
            max_workers: Max concurrent requests for parallel crawling
        """
        self.encryption = encryption_service
        self.base_url = base_url
        self.max_workers = max_workers

        # Session management
        self._session: Optional[requests.Session] = None
        self._authenticated = False
        self._user_id = ""
        self._user_name = ""
        self._user_grade = ""

    def _ensure_session(self) -> requests.Session:
        """Ensure HTTP session is initialized."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6',
            })
        return self._session

    def _authenticate_sync(self, credentials: UserCredentials) -> bool:
        """Synchronous authentication implementation."""
        session = self._ensure_session()

        # Decrypt credentials
        username, password = self.encryption.decrypt_credentials(
            credentials.encrypted_username,
            credentials.encrypted_password
        )

        # Use base_url from credentials if provided
        base_url = credentials.ims_base_url or self.base_url

        # Get login page first (for cookies)
        login_url = f"{base_url}/tody/auth/login.do"
        session.get(login_url, timeout=30)

        # Submit login form
        response = session.post(
            login_url,
            data={'id': username, 'password': password},
            allow_redirects=True,
            timeout=30
        )

        # Check if login succeeded
        if '/login' in response.url or '/auth/login' in response.url:
            logger.error("Authentication failed - redirected back to login")
            self._authenticated = False
            return False

        # Extract user info from session
        self._user_id = username
        self._authenticated = True

        # Try to extract user info from response
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            user_name_elem = soup.find('input', {'name': 'userName'})
            user_grade_elem = soup.find('input', {'name': 'userGrade'})
            if user_name_elem:
                self._user_name = user_name_elem.get('value', username)
            if user_grade_elem:
                self._user_grade = user_grade_elem.get('value', 'TMAX')
        except Exception:
            self._user_name = username
            self._user_grade = 'TMAX'

        jsessionid = session.cookies.get('JSESSIONID', '')[:20]
        logger.info(f"[IMS Crawler] Authentication successful - Session: {jsessionid}...")
        logger.info(f"Authentication successful - Session: {jsessionid}...")
        return True

    async def authenticate(self, credentials: UserCredentials) -> bool:
        """
        Authenticate with IMS system using user credentials.

        Args:
            credentials: Encrypted user credentials

        Returns:
            True if authentication successful
        """
        try:
            # Run synchronous HTTP requests in thread pool
            return await asyncio.to_thread(self._authenticate_sync, credentials)
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self._authenticated = False
            raise

    def _search_issues_sync(
        self,
        query: str,
        user_id,
        base_url: str,
        products: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[Issue]:
        """Synchronous search implementation."""
        session = self._ensure_session()

        all_issues: List[Issue] = []
        total_count = None
        page = 1
        max_pages = 100  # Safety limit increased

        logger.info(f"[IMS Crawler] Searching for '{query}' in {len(products)} products")
        logger.info(f"Searching for '{query}' in {len(products)} products")

        if progress_callback:
            progress_callback({
                "phase": "search_start",
                "query": query,
                "products_count": len(products)
            })

        while page <= max_pages:
            # Build search params
            params = {
                'reSearchYN': 'Y',  # Required!
                'searchType': '1',
                'pageIndex': str(page),
                'pageSize': '100',  # Server ignores this, always returns 10
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
                'userId': self._user_id,
                'userName': self._user_name or self._user_id,
                'userGrade': self._user_grade or 'TMAX',
                'productCodes': products,
            }

            search_url = f"{base_url}/tody/ims/issue/issueSearchList.do"
            logger.info(f"[IMS Crawler] Requesting page {page}...")
            try:
                response = session.get(search_url, params=params, headers={
                    'Referer': f"{base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
                }, timeout=60)
                logger.info(f"[IMS Crawler] Response status: {response.status_code}, length: {len(response.text)}")
            except Exception as e:
                logger.info(f"[IMS Crawler] Request error: {e}")
                raise

            # Get total count on first page
            if total_count is None:
                total_count = self._get_total_count(response.text)
                total_pages = (total_count + 9) // 10  # 10 items per page
                logger.info(f"[IMS Crawler] Total count: {total_count} ({total_pages} pages)")
                logger.info(f"Total count: {total_count}")
                if progress_callback:
                    progress_callback({
                        "phase": "search_count",
                        "total_count": total_count,
                        "total_pages": total_pages
                    })

            # Parse issues from this page
            page_issues = self._parse_search_results(response.text, user_id, base_url)
            total_pages = (total_count + 9) // 10 if total_count else 1
            progress_pct = min(100, int((page / total_pages) * 100))
            logger.info(f"[IMS Crawler] Page {page}/{total_pages}: {len(page_issues)} issues ({progress_pct}%)")
            logger.info(f"Page {page}: {len(page_issues)} issues")

            if progress_callback:
                progress_callback({
                    "phase": "search_page",
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_issues": len(page_issues),
                    "fetched_count": len(all_issues) + len(page_issues),
                    "total_count": total_count,
                    "progress_percent": progress_pct
                })

            if not page_issues:
                break

            all_issues.extend(page_issues)

            # Check if we have all issues
            if len(all_issues) >= total_count:
                break

            page += 1

        logger.info(f"[IMS Crawler] Search completed: {len(all_issues)} issues (Total: {total_count})")
        logger.info(f"Search completed: {len(all_issues)} issues (Total: {total_count})")

        if progress_callback:
            progress_callback({
                "phase": "search_complete",
                "fetched_count": len(all_issues),
                "total_count": total_count
            })

        return all_issues

    async def search_issues(
        self,
        query: str,
        credentials: UserCredentials,
        product_codes: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> List[Issue]:
        """
        Search for issues matching the query with pagination.

        Note: IMS server ignores pageSize parameter and returns 10 items per page.
        This method automatically fetches all pages.

        Args:
            query: Search keyword
            credentials: User credentials for authentication
            product_codes: Optional list of product codes to filter
            progress_callback: Optional callback for progress updates

        Returns:
            List of Issue entities
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        base_url = credentials.ims_base_url or self.base_url
        products = product_codes or self.OPENFRAME_PRODUCTS

        # Run synchronous HTTP requests in thread pool
        return await asyncio.to_thread(
            self._search_issues_sync,
            query,
            credentials.user_id,
            base_url,
            products,
            progress_callback
        )

    def _get_total_count(self, html: str) -> int:
        """Extract total count from search result HTML."""
        # Method 1: Look for "[ Total X ]" pattern (IMS search result format)
        match = re.search(r'\[\s*[Tt]otal\s+(\d+)\s*\]', html)
        if match:
            return int(match.group(1))

        # Method 2: Look for hidden input with totalCount
        soup = BeautifulSoup(html, 'html.parser')
        total_input = soup.find('input', {'id': 'totalCount'}) or soup.find('input', {'name': 'totalCount'})
        if total_input and total_input.get('value'):
            try:
                return int(total_input.get('value'))
            except ValueError:
                pass

        # Method 3: Look for JS variable
        match = re.search(r'totalCount["\']?\s*[=:]\s*["\']?(\d+)', html)
        if match:
            return int(match.group(1))

        # Method 4: Fallback - Look for "Total X" pattern (less specific)
        match = re.search(r'[Tt]otal[:\s]+(\d+)', html)
        if match:
            return int(match.group(1))

        return 0

    def _parse_search_results(self, html: str, user_id, base_url: str) -> List[Issue]:
        """Parse issues from search results HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        issues = []

        # Find rows with onclick handler
        rows = soup.find_all('tr', onclick=re.compile(r'popBlankIssueView'))

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue

            # Extract issue ID from onclick
            onclick = row.get('onclick', '')
            id_match = re.search(r"popBlankIssueView\s*\(\s*['\"](\d+)['\"]", onclick)
            issue_id = id_match.group(1) if id_match else ''

            if not issue_id:
                continue

            # Extract fields from cells
            # Cell structure: No(0), IssueNum(1), Category(2), Product(3), Version(4), Module(5), Subject(6), Customer(7), Project(8), Reporter(9), Date(10)
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

            # Normalize title whitespace
            title = re.sub(r'\s+', ' ', get_cell_text(6)).strip()

            issue = Issue(
                id=uuid4(),
                user_id=user_id,
                ims_id=issue_id,
                title=title or f"Issue {issue_id}",
                description="",
                status=IssueStatus.OPEN,
                priority=IssuePriority.MEDIUM,
                category=get_cell_text(2),
                product=get_cell_text(3),
                version=get_cell_text(4),
                module=get_cell_text(5),
                customer=get_cell_text(7),
                project_key=get_cell_text(8),
                reporter=get_cell_text(9),
                issued_date=issued_date,
                source_url=f"{base_url}/tody/ims/issue/issueView.do?issueId={issue_id}",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                crawled_at=datetime.now(timezone.utc),
            )
            issues.append(issue)

        return issues

    def _crawl_issue_details_sync(
        self,
        issue_id: str,
        user_id,
        base_url: str,
        fallback_issue: Issue = None,
        fetch_related: bool = True
    ) -> Issue:
        """Synchronous issue detail crawling implementation."""
        session = self._ensure_session()

        try:
            # Fetch issue detail page
            detail_url = f"{base_url}/tody/ims/issue/issueView.do"
            response = session.post(
                detail_url,
                data={'issueId': issue_id, 'menuCode': 'issue_search'},
                headers={'Referer': f"{base_url}/tody/ims/issue/issueSearchList.do"},
                timeout=60
            )

            issue = self._parse_issue_detail(
                response.text, issue_id, user_id, base_url, fallback_issue
            )

            # Fetch related issue IDs if requested
            if fetch_related:
                all_related_ids = []
                patch_ids = []

                # 1. Fetch from Related Issue API
                related_ids = self._fetch_related_issue_ids_sync(issue_id, base_url)
                if related_ids:
                    all_related_ids.extend(related_ids)
                    logger.debug(f"Issue {issue_id}: {len(related_ids)} from Related Issue API")

                # 2. Fetch from Patch List API
                patch_params = self._parse_patch_list_params(response.text)
                if patch_params:
                    patch_ids = self._fetch_patch_list_issue_ids_sync(patch_params, base_url)
                    if patch_ids:
                        all_related_ids.extend(patch_ids)
                        logger.debug(f"Issue {issue_id}: {len(patch_ids)} from Patch List API")

                # Deduplicate while preserving order
                seen = set()
                unique_ids = []
                for id in all_related_ids:
                    if id not in seen and id != issue_id:  # Exclude self
                        seen.add(id)
                        unique_ids.append(id)

                issue.related_issue_ids = unique_ids
                if unique_ids:
                    logger.info(f"Issue {issue_id} has {len(unique_ids)} related issues (Related: {len(related_ids)}, Patch: {len(patch_ids)})")

            return issue

        except Exception as e:
            logger.error(f"Failed to crawl issue {issue_id}: {e}")
            if fallback_issue:
                return fallback_issue
            raise

    async def crawl_issue_details(
        self,
        issue_id: str,
        credentials: UserCredentials,
        fallback_issue: Issue = None,
        fetch_related: bool = True
    ) -> Issue:
        """
        Crawl detailed information for a single issue.

        Args:
            issue_id: IMS issue identifier
            credentials: User credentials
            fallback_issue: Optional issue from search results to use as fallback
            fetch_related: Whether to fetch related issue IDs (default True)

        Returns:
            Complete Issue entity with all details including related_issue_ids
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        base_url = credentials.ims_base_url or self.base_url

        # Run synchronous HTTP request in thread pool
        return await asyncio.to_thread(
            self._crawl_issue_details_sync,
            issue_id,
            credentials.user_id,
            base_url,
            fallback_issue,
            fetch_related
        )

    def _parse_issue_detail(
        self,
        html: str,
        issue_id: str,
        user_id,
        base_url: str,
        fallback_issue: Issue = None
    ) -> Issue:
        """Parse issue detail from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        def get_table_field(label: str) -> str:
            """Extract value from table row with given label."""
            # Method 1: Look for tableHeaderTitle pattern
            pattern = rf'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
            match = re.search(pattern, html, re.DOTALL | re.I)
            if match:
                value = re.sub(r'<[^>]+>', '', match.group(1))
                return value.replace('&nbsp;', ' ').strip()

            # Method 2: Look for th/td pattern
            pattern2 = rf'<th[^>]*>\s*{label}\s*</th>\s*<td[^>]*>(.*?)</td>'
            match2 = re.search(pattern2, html, re.DOTALL | re.I)
            if match2:
                value = re.sub(r'<[^>]+>', '', match2.group(1))
                return value.replace('&nbsp;', ' ').strip()

            # Method 3: Use BeautifulSoup for more flexible matching
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

        # Use fallback title if needed
        if not subject and fallback_issue:
            subject = fallback_issue.title

        # Parse Issue Details (description)
        issue_details = ""
        desc_match = re.search(r'id=["\']IssueDescriptionDiv["\'][^>]*>(.*?)</div>\s*<!--', html, re.DOTALL | re.I)
        if desc_match:
            desc_html = desc_match.group(1)
            issue_details = re.sub(r'<[^>]+>', ' ', desc_html)
            issue_details = issue_details.replace('&nbsp;', ' ').replace('&#39;', "'")
            issue_details = issue_details.replace('&lt;', '<').replace('&gt;', '>')
            issue_details = issue_details.replace('&#64;', '@')
            issue_details = re.sub(r'\s+', ' ', issue_details).strip()

        # Parse Actions/Comments
        actions_count = 0
        action_log_text = ""
        action_pattern = r'<input[^>]*name=["\']actionId["\'][^>]*value=["\'](\d+)["\'][^>]*>'
        action_matches = re.findall(action_pattern, html)
        actions_count = len(action_matches)

        # Extract Action Log text content from CommentsDiv
        # IMS Action Log structure: <div id="CommentsDiv"> -> <div class="commDescTR data"> -> content
        action_texts = []

        # Pattern 1: Extract from commDescTR divs (main action content)
        comm_desc_pattern = r'<div[^>]*class=["\'][^"\']*commDescTR[^"\']*["\'][^>]*>(.*?)</div>'
        comm_desc_matches = re.findall(comm_desc_pattern, html, re.DOTALL | re.I)
        for match in comm_desc_matches:
            text = re.sub(r'<[^>]+>', ' ', match)
            text = text.replace('&nbsp;', ' ').replace('&#39;', "'")
            text = text.replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&#64;', '@')
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 5:
                action_texts.append(text)

        # Pattern 2: Extract from CommentsDiv if pattern 1 didn't find anything
        if not action_texts:
            comments_div = re.search(r'<div[^>]*id=["\']CommentsDiv["\'][^>]*>(.*?)</div>\s*(?:</div>|<table)', html, re.DOTALL | re.I)
            if comments_div:
                section_html = comments_div.group(1)
                text = re.sub(r'<[^>]+>', ' ', section_html)
                text = text.replace('&nbsp;', ' ').replace('&#39;', "'")
                text = text.replace('&lt;', '<').replace('&gt;', '>')
                text = text.replace('&#64;', '@')
                text = re.sub(r'\s+', ' ', text).strip()
                if text and len(text) > 10:
                    action_texts.append(text)

        # Combine all action texts
        action_log_text = " | ".join(action_texts)[:10000]  # Limit to 10KB

        # Parse status (keep raw value for display)
        status = IssueStatus.OPEN
        status_raw = ""
        status_text = get_table_field('Status')
        if status_text:
            status_raw = status_text  # Store raw value
            logger.info(f"[IMS Parser] Issue {issue_id} Status: '{status_text}'")
            status_upper = status_text.upper()
            if 'CLOSED' in status_upper or 'CLOSED_P' in status_upper:
                status = IssueStatus.CLOSED
            elif 'RESOLVED' in status_upper:
                status = IssueStatus.RESOLVED
            elif 'PROGRESS' in status_upper or 'ASSIGNED' in status_upper:
                status = IssueStatus.IN_PROGRESS
            elif 'REJECT' in status_upper:
                status = IssueStatus.REJECTED
            elif 'PENDING' in status_upper or 'POSTPONED' in status_upper:
                status = IssueStatus.PENDING

        # Parse priority (keep raw value for display)
        priority = IssuePriority.MEDIUM
        priority_raw = ""
        priority_text = get_table_field('Priority') or get_table_field('Urgency')
        if priority_text:
            priority_raw = priority_text  # Store raw value
            logger.info(f"[IMS Parser] Issue {issue_id} Priority: '{priority_text}'")
            priority_upper = priority_text.upper()
            if 'CRITICAL' in priority_upper or 'URGENT' in priority_upper or 'VERY HIGH' in priority_upper or '긴급' in priority_text:
                priority = IssuePriority.CRITICAL
            elif 'HIGH' in priority_upper or '높음' in priority_text:
                priority = IssuePriority.HIGH
            elif 'LOW' in priority_upper or '낮음' in priority_text:
                priority = IssuePriority.LOW
            elif 'TRIVIAL' in priority_upper or '사소' in priority_text:
                priority = IssuePriority.TRIVIAL
            # MEDIUM is default (Normal)
        else:
            logger.info(f"[IMS Parser] Issue {issue_id} Priority not found, using default MEDIUM")

        # Build issue entity
        return Issue(
            id=uuid4(),
            user_id=user_id,
            ims_id=issue_id,
            title=re.sub(r'\s+', ' ', subject).strip() or f"Issue {issue_id}",
            description=issue_details[:5000],
            status=status,
            priority=priority,
            status_raw=status_raw,
            priority_raw=priority_raw,
            category=get_table_field('Category') or (fallback_issue.category if fallback_issue else ''),
            product=get_table_field('Product') or (fallback_issue.product if fallback_issue else ''),
            version=get_table_field('Version') or (fallback_issue.version if fallback_issue else ''),
            module=get_table_field('Module') or (fallback_issue.module if fallback_issue else ''),
            customer=get_table_field('Customer') or (fallback_issue.customer if fallback_issue else ''),
            reporter=get_table_field('Reporter') or get_table_field('Register') or (fallback_issue.reporter if fallback_issue else ''),
            project_key=get_table_field('Project') or (fallback_issue.project_key if fallback_issue else ''),
            issue_details=issue_details[:5000],
            action_no=str(actions_count) if actions_count else "",
            action_log_text=action_log_text,
            comments_count=actions_count,
            issued_date=fallback_issue.issued_date if fallback_issue else None,
            source_url=f"{base_url}/tody/ims/issue/issueView.do?issueId={issue_id}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            crawled_at=datetime.now(timezone.utc),
        )

    async def download_attachments(
        self,
        issue: Issue,
        credentials: UserCredentials
    ) -> List[Attachment]:
        """
        Download and process attachments for an issue.

        Note: Not implemented for requests-based crawler.
        Returns empty list.
        """
        # TODO: Implement attachment download if needed
        logger.warning(f"Attachment download not implemented for requests crawler")
        return []

    def _fetch_related_issue_ids_sync(self, ims_id: str, base_url: str) -> List[str]:
        """Synchronous fetch of related issue IDs.

        API Response structure:
        - relationIssueId=0: root issue (self)
        - relationIssueId=N: child issue related to issue N

        Only returns actual related issues, excluding the root (self).
        """
        session = self._ensure_session()

        try:
            response = session.get(
                f"{base_url}/tody/ims/issue/findRelationIssues.do",
                params={'issueId': ims_id},
                timeout=30
            )

            related_ids = []
            try:
                data = response.json()
                if isinstance(data, list):
                    for item in data:
                        # Skip root issue (relationIssueId=0 means it's the queried issue itself)
                        relation_issue_id = item.get('relationIssueId', 0)
                        if relation_issue_id == 0:
                            continue

                        related_id = str(item.get('issueId', ''))
                        if related_id:
                            related_ids.append(related_id)
            except Exception as e:
                logger.warning(f"Failed to parse related issues JSON: {e}")

            return related_ids

        except Exception as e:
            logger.error(f"Failed to fetch related issue IDs: {e}")
            return []

    def _parse_patch_list_params(self, html: str) -> dict:
        """
        Parse Patch List popup parameters from issue detail HTML.

        Looks for: popupPatchList('projectCode','siteCode', 'productCode', 'projectName', 'siteName')

        Returns:
            Dict with projectCode, siteCode, productCode, projectName, siteName
            or empty dict if not found
        """
        # Match pattern: popupPatchList('param1','param2', 'param3', 'param4', 'param5')
        pattern = r"popupPatchList\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
        match = re.search(pattern, html)

        if match:
            return {
                'projectCode': match.group(1),
                'siteCode': match.group(2),
                'productCode': match.group(3),
                'projectName': match.group(4),
                'siteName': match.group(5)
            }
        return {}

    def _fetch_patch_list_issue_ids_sync(self, patch_params: dict, base_url: str) -> List[str]:
        """
        Fetch Patch List and extract Issue Numbers.

        Calls /tody/ims/patch/patchList.do and parses the HTML response
        to extract Issue Numbers from the table.

        Args:
            patch_params: Dict with projectCode, siteCode, productCode, projectName, siteName
            base_url: IMS base URL

        Returns:
            List of IMS issue IDs from Patch List
        """
        if not patch_params:
            return []

        session = self._ensure_session()

        try:
            url = f"{base_url}/tody/ims/patch/patchList.do"
            response = session.get(url, params=patch_params, timeout=60)

            if response.status_code != 200:
                logger.warning(f"Patch List API returned {response.status_code}")
                return []

            # Parse HTML to extract Issue Numbers
            soup = BeautifulSoup(response.text, 'html.parser')
            issue_ids = []

            # Method 1: Look for links to issueView.do
            issue_links = soup.find_all('a', href=lambda h: h and 'issueView' in h)
            for link in issue_links:
                href = link.get('href', '')
                # Extract issueId from URL like: issueView.do?issueId=123456
                id_match = re.search(r'issueId=(\d+)', href)
                if id_match:
                    issue_ids.append(id_match.group(1))

            # Method 2: Look for table cells with Issue No pattern (5-6 digit numbers)
            if not issue_ids:
                # Find table rows
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        for cell in cells:
                            text = cell.get_text(strip=True)
                            # Look for 5-6 digit issue numbers (IMS IDs range from 10000+)
                            if text.isdigit() and 5 <= len(text) <= 6:
                                issue_ids.append(text)

            # Remove duplicates while preserving order
            seen = set()
            unique_ids = []
            for id in issue_ids:
                if id not in seen:
                    seen.add(id)
                    unique_ids.append(id)

            if unique_ids:
                logger.info(f"Patch List: found {len(unique_ids)} issue IDs: {unique_ids[:5]}...")

            return unique_ids

        except Exception as e:
            logger.warning(f"Failed to fetch Patch List: {e}")
            return []

    async def crawl_related_issues(
        self,
        issue: Issue,
        credentials: UserCredentials,
        max_depth: int = 1
    ) -> List[Issue]:
        """
        Crawl issues related to the given issue.

        Args:
            issue: Source issue
            credentials: User credentials
            max_depth: Maximum recursion depth

        Returns:
            List of related Issue entities
        """
        if max_depth <= 0:
            return []

        if not self._authenticated:
            await self.authenticate(credentials)

        base_url = credentials.ims_base_url or self.base_url

        # Fetch related issue IDs in thread pool
        related_ids = await asyncio.to_thread(
            self._fetch_related_issue_ids_sync,
            issue.ims_id,
            base_url
        )

        # Crawl each related issue (already async-safe)
        related_issues = []
        for related_id in related_ids:
            try:
                related_issue = await self.crawl_issue_details(
                    related_id, credentials
                )
                related_issues.append(related_issue)
            except Exception as e:
                logger.warning(f"Failed to crawl related issue {related_id}: {e}")

        return related_issues

    async def crawl_issues_parallel(
        self,
        issues: List[Issue],
        credentials: UserCredentials,
        batch_size: int = 10,
        progress_callback: Optional[callable] = None
    ) -> List[Issue]:
        """
        Crawl multiple issues in parallel using thread pool.

        Args:
            issues: List of issues to crawl
            credentials: User credentials
            batch_size: Number of concurrent requests
            progress_callback: Optional callback for progress updates

        Returns:
            List of crawled Issue entities sorted by ims_id descending
        """
        if not issues:
            return []

        if not self._authenticated:
            await self.authenticate(credentials)

        # Sort by ims_id descending
        sorted_issues = sorted(
            issues,
            key=lambda x: int(x.ims_id) if x.ims_id.isdigit() else 0,
            reverse=True
        )

        crawled_results: List[Issue] = []
        total = len(sorted_issues)
        total_batches = (total + batch_size - 1) // batch_size

        if progress_callback:
            progress_callback({
                "phase": "crawl_start",
                "total_issues": total,
                "total_batches": total_batches,
                "batch_size": batch_size
            })

        # Process in batches
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = sorted_issues[batch_start:batch_end]
            batch_num = batch_start // batch_size + 1
            progress_pct = min(100, int((batch_num / total_batches) * 100))

            logger.info(f"[IMS Crawler] Crawling batch {batch_num}/{total_batches}: issues {batch_start + 1}-{batch_end} of {total} ({progress_pct}%)")
            logger.info(f"Crawling batch {batch_num}/{total_batches}: issues {batch_start + 1}-{batch_end} of {total}")

            if progress_callback:
                progress_callback({
                    "phase": "crawl_batch_start",
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_start": batch_start + 1,
                    "batch_end": batch_end,
                    "total_issues": total,
                    "progress_percent": progress_pct
                })

            # Crawl batch concurrently
            tasks = [
                self.crawl_issue_details(issue.ims_id, credentials, issue)
                for issue in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            success_count = 0
            fail_count = 0
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Exception for issue {batch[i].ims_id}: {result}")
                    crawled_results.append(batch[i])  # Use fallback
                    fail_count += 1
                else:
                    crawled_results.append(result)
                    success_count += 1

            if progress_callback:
                progress_callback({
                    "phase": "crawl_batch_complete",
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_success": success_count,
                    "batch_fail": fail_count,
                    "crawled_count": len(crawled_results),
                    "total_issues": total,
                    "progress_percent": progress_pct
                })

        if progress_callback:
            progress_callback({
                "phase": "crawl_complete",
                "crawled_count": len(crawled_results),
                "total_issues": total
            })

        logger.info(f"Parallel crawl completed: {len(crawled_results)} issues")
        return crawled_results

    async def close(self) -> None:
        """Clean up resources."""
        if self._session:
            self._session.close()
            self._session = None

        self._authenticated = False
        logger.info("Requests crawler resources cleaned up")
