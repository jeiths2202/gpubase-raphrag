"""
Requests-based Crawler Adapter - Lightweight HTTP implementation

Uses requests library instead of Playwright for faster, lighter crawling.
No browser overhead - pure HTTP requests with HTML parsing.
"""

import re
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
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
        products: List[str]
    ) -> List[Issue]:
        """Synchronous search implementation."""
        session = self._ensure_session()

        all_issues: List[Issue] = []
        total_count = None
        page = 1
        max_pages = 50  # Safety limit

        logger.info(f"Searching for '{query}' in {len(products)} products")

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
            response = session.get(search_url, params=params, headers={
                'Referer': f"{base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
            }, timeout=60)

            # Get total count on first page
            if total_count is None:
                total_count = self._get_total_count(response.text)
                logger.info(f"Total count: {total_count}")

            # Parse issues from this page
            page_issues = self._parse_search_results(response.text, user_id, base_url)
            logger.info(f"Page {page}: {len(page_issues)} issues")

            if not page_issues:
                break

            all_issues.extend(page_issues)

            # Check if we have all issues
            if len(all_issues) >= total_count:
                break

            page += 1

        logger.info(f"Search completed: {len(all_issues)} issues (Total: {total_count})")
        return all_issues

    async def search_issues(
        self,
        query: str,
        credentials: UserCredentials,
        product_codes: Optional[List[str]] = None
    ) -> List[Issue]:
        """
        Search for issues matching the query with pagination.

        Note: IMS server ignores pageSize parameter and returns 10 items per page.
        This method automatically fetches all pages.

        Args:
            query: Search keyword
            credentials: User credentials for authentication
            product_codes: Optional list of product codes to filter

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
            products
        )

    def _get_total_count(self, html: str) -> int:
        """Extract total count from search result HTML."""
        # Method 1: Look for "Total X" pattern
        match = re.search(r'[Tt]otal[:\s]+(\d+)', html)
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
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                crawled_at=datetime.utcnow(),
            )
            issues.append(issue)

        return issues

    def _crawl_issue_details_sync(
        self,
        issue_id: str,
        user_id,
        base_url: str,
        fallback_issue: Issue = None
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

            return self._parse_issue_detail(
                response.text, issue_id, user_id, base_url, fallback_issue
            )

        except Exception as e:
            logger.error(f"Failed to crawl issue {issue_id}: {e}")
            if fallback_issue:
                return fallback_issue
            raise

    async def crawl_issue_details(
        self,
        issue_id: str,
        credentials: UserCredentials,
        fallback_issue: Issue = None
    ) -> Issue:
        """
        Crawl detailed information for a single issue.

        Args:
            issue_id: IMS issue identifier
            credentials: User credentials
            fallback_issue: Optional issue from search results to use as fallback

        Returns:
            Complete Issue entity with all details
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
            fallback_issue
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
            pattern = rf'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
            match = re.search(pattern, html, re.DOTALL | re.I)
            if match:
                value = re.sub(r'<[^>]+>', '', match.group(1))
                return value.replace('&nbsp;', ' ').strip()
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
        action_pattern = r'<input[^>]*name=["\']actionId["\'][^>]*value=["\'](\d+)["\'][^>]*>'
        action_matches = re.findall(action_pattern, html)
        actions_count = len(action_matches)

        # Parse status
        status = IssueStatus.OPEN
        status_text = get_table_field('Status')
        if status_text:
            status_upper = status_text.upper()
            if 'CLOSED' in status_upper or 'CLOSED_P' in status_upper:
                status = IssueStatus.CLOSED
            elif 'RESOLVED' in status_upper:
                status = IssueStatus.RESOLVED
            elif 'PROGRESS' in status_upper or 'ASSIGNED' in status_upper:
                status = IssueStatus.IN_PROGRESS
            elif 'REJECT' in status_upper:
                status = IssueStatus.REJECTED
            elif 'PENDING' in status_upper:
                status = IssueStatus.PENDING

        # Build issue entity
        return Issue(
            id=uuid4(),
            user_id=user_id,
            ims_id=issue_id,
            title=re.sub(r'\s+', ' ', subject).strip() or f"Issue {issue_id}",
            description=issue_details[:5000],
            status=status,
            priority=IssuePriority.MEDIUM,
            category=get_table_field('Category') or (fallback_issue.category if fallback_issue else ''),
            product=get_table_field('Product') or (fallback_issue.product if fallback_issue else ''),
            version=get_table_field('Version') or (fallback_issue.version if fallback_issue else ''),
            module=get_table_field('Module') or (fallback_issue.module if fallback_issue else ''),
            customer=get_table_field('Customer') or (fallback_issue.customer if fallback_issue else ''),
            reporter=get_table_field('Reporter') or get_table_field('Register') or (fallback_issue.reporter if fallback_issue else ''),
            project_key=get_table_field('Project') or (fallback_issue.project_key if fallback_issue else ''),
            issue_details=issue_details[:5000],
            comments_count=actions_count,
            issued_date=fallback_issue.issued_date if fallback_issue else None,
            source_url=f"{base_url}/tody/ims/issue/issueView.do?issueId={issue_id}",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            crawled_at=datetime.utcnow(),
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
        """Synchronous fetch of related issue IDs."""
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
                        related_id = str(item.get('issueId', ''))
                        if related_id:
                            related_ids.append(related_id)
            except Exception as e:
                logger.warning(f"Failed to parse related issues JSON: {e}")

            return related_ids

        except Exception as e:
            logger.error(f"Failed to fetch related issue IDs: {e}")
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
        batch_size: int = 10
    ) -> List[Issue]:
        """
        Crawl multiple issues in parallel using thread pool.

        Args:
            issues: List of issues to crawl
            credentials: User credentials
            batch_size: Number of concurrent requests

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

        # Process in batches
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = sorted_issues[batch_start:batch_end]

            logger.info(f"Crawling batch: issues {batch_start + 1}-{batch_end} of {total}")

            # Crawl batch concurrently
            tasks = [
                self.crawl_issue_details(issue.ims_id, credentials, issue)
                for issue in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Exception for issue {batch[i].ims_id}: {result}")
                    crawled_results.append(batch[i])  # Use fallback
                else:
                    crawled_results.append(result)

        logger.info(f"Parallel crawl completed: {len(crawled_results)} issues")
        return crawled_results

    async def close(self) -> None:
        """Clean up resources."""
        if self._session:
            self._session.close()
            self._session = None

        self._authenticated = False
        logger.info("Requests crawler resources cleaned up")
