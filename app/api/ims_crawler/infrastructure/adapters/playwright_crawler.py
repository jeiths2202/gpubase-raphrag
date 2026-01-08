"""
Playwright Crawler Adapter - Concrete implementation using Playwright

Web automation implementation for crawling IMS system.
"""

import asyncio
import logging
from typing import List, Optional, Set
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from datetime import datetime
from uuid import uuid4

from ...domain.entities import Issue, Attachment, UserCredentials, IssueStatus, IssuePriority
from ...domain.entities.attachment import AttachmentType
from ..ports.crawler_port import CrawlerPort
from ..services.credential_encryption_service import CredentialEncryptionService

logger = logging.getLogger(__name__)


class PlaywrightCrawler(CrawlerPort):
    """
    Playwright-based crawler implementation.

    Uses async Playwright for browser automation and web scraping.
    """

    def __init__(
        self,
        encryption_service: CredentialEncryptionService,
        attachments_dir: Path,
        headless: bool = True
    ):
        """
        Initialize Playwright crawler.

        Args:
            encryption_service: Service to decrypt user credentials
            attachments_dir: Directory to store downloaded attachments
            headless: Whether to run browser in headless mode
        """
        self.encryption = encryption_service
        self.attachments_dir = Path(attachments_dir)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

        # Browser resources (lazy initialized)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False

    async def _ensure_browser(self) -> None:
        """Ensure browser is initialized (lazy initialization)."""
        # Check if browser needs to be (re)initialized
        browser_needs_init = self._browser is None
        if not browser_needs_init:
            try:
                # Check if browser is still connected
                browser_needs_init = not self._browser.is_connected()
            except:
                browser_needs_init = True

        if browser_needs_init:
            # Clean up any existing playwright instance
            if self._playwright:
                try:
                    await self._playwright.stop()
                except:
                    pass
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = None  # Reset context when browser is restarted
            logger.info("Browser initialized")

        # Always create fresh context and page for each session
        # This prevents stale context issues when crawler is reused
        if self._context:
            try:
                await self._context.close()
            except:
                pass

        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        self._authenticated = False  # Reset auth state with new context
        logger.info("Fresh browser context created")

    async def authenticate(self, credentials: UserCredentials) -> bool:
        """
        Authenticate with IMS system.

        Args:
            credentials: Encrypted user credentials

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If authentication fails
        """
        await self._ensure_browser()

        try:
            # Decrypt credentials
            username, password = self.encryption.decrypt_credentials(
                credentials.encrypted_username,
                credentials.encrypted_password
            )

            # Navigate to IMS login page (TmaxSoft IMS uses /tody/auth/login.do)
            ims_url = credentials.ims_base_url
            login_url = f"{ims_url}/tody/auth/login.do"
            await self._page.goto(login_url)
            logger.info(f"Navigating to {login_url}")

            # Wait for login form to be visible
            await self._page.wait_for_selector('input[name="id"]', timeout=15000)

            # Fill login form (IMS uses 'id' not 'username')
            await self._page.fill('input[name="id"]', username)
            await self._page.fill('input[name="password"]', password)

            # Submit login (IMS uses image button)
            await self._page.click('input[type="image"]')

            # Wait for navigation after login
            await self._page.wait_for_load_state('networkidle', timeout=15000)

            # Verify authentication success
            current_url = self._page.url
            if '/login' not in current_url and '/auth/login' not in current_url and '/error' not in current_url:
                self._authenticated = True
                logger.info("Authentication successful")
                return True
            else:
                logger.error("Authentication failed - still on login page")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise

    async def search_issues(
        self,
        query: str,
        credentials: UserCredentials,
        max_results: int = 100
    ) -> List[Issue]:
        """
        Search for issues matching the query.

        Args:
            query: IMS search syntax query
            credentials: User credentials for authentication
            max_results: Maximum number of issues to return

        Returns:
            List of Issue entities

        Raises:
            CrawlerError: If search fails
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        try:
            # Navigate to search page
            search_url = f"{credentials.ims_base_url}/search?q={query}"
            await self._page.goto(search_url)
            await self._page.wait_for_load_state('networkidle')

            # Extract issue links from search results
            issue_elements = await self._page.query_selector_all('.issue-row a.issue-link')

            issues = []
            for idx, element in enumerate(issue_elements[:max_results]):
                try:
                    # Extract issue ID and URL
                    issue_url = await element.get_attribute('href')
                    issue_id = issue_url.split('/')[-1] if issue_url else f"unknown-{idx}"

                    # Extract basic info from search results
                    title_elem = await element.query_selector('.issue-title')
                    title = await title_elem.inner_text() if title_elem else "Untitled"

                    # Create minimal Issue entity (details will be populated by crawl_issue_details)
                    issue = Issue(
                        id=uuid4(),
                        user_id=credentials.user_id,
                        ims_id=issue_id,
                        title=title.strip(),
                        description="",  # Will be populated later
                        status=IssueStatus.OPEN,  # Default
                        priority=IssuePriority.MEDIUM,  # Default
                        ims_url=f"{credentials.ims_base_url}{issue_url}" if not issue_url.startswith('http') else issue_url,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    issues.append(issue)

                except Exception as e:
                    logger.warning(f"Failed to extract issue {idx}: {e}")
                    continue

            logger.info(f"Found {len(issues)} issues from search")
            return issues

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    async def crawl_issue_details(
        self,
        issue_id: str,
        credentials: UserCredentials
    ) -> Issue:
        """
        Crawl detailed information for a single issue.

        Args:
            issue_id: IMS issue identifier
            credentials: User credentials

        Returns:
            Complete Issue entity with all details

        Raises:
            CrawlerError: If crawling fails
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        try:
            # Navigate to issue page
            issue_url = f"{credentials.ims_base_url}/issue/{issue_id}"
            await self._page.goto(issue_url)
            await self._page.wait_for_load_state('networkidle')

            # Extract issue details
            title_elem = await self._page.query_selector('h1.issue-title')
            title = await title_elem.inner_text() if title_elem else "Untitled"

            desc_elem = await self._page.query_selector('.issue-description')
            description = await desc_elem.inner_text() if desc_elem else ""

            status_elem = await self._page.query_selector('.issue-status')
            status_text = await status_elem.inner_text() if status_elem else "OPEN"
            status = self._parse_status(status_text)

            priority_elem = await self._page.query_selector('.issue-priority')
            priority_text = await priority_elem.inner_text() if priority_elem else "MEDIUM"
            priority = self._parse_priority(priority_text)

            reporter_elem = await self._page.query_selector('.issue-reporter')
            reporter = await reporter_elem.inner_text() if reporter_elem else "Unknown"

            assignee_elem = await self._page.query_selector('.issue-assignee')
            assignee = await assignee_elem.inner_text() if assignee_elem else None

            project_elem = await self._page.query_selector('.issue-project')
            project_key = await project_elem.inner_text() if project_elem else "UNKNOWN"

            # Extract labels
            label_elements = await self._page.query_selector_all('.issue-label')
            labels = []
            for label_elem in label_elements:
                label_text = await label_elem.inner_text()
                labels.append(label_text.strip())

            # Create Issue entity
            issue = Issue(
                id=uuid4(),
                user_id=credentials.user_id,
                ims_id=issue_id,
                title=title.strip(),
                description=description.strip(),
                status=status,
                priority=priority,
                reporter=reporter.strip(),
                assignee=assignee.strip() if assignee else None,
                project_key=project_key.strip(),
                labels=labels,
                ims_url=issue_url,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            logger.info(f"Crawled issue details: {issue_id}")
            return issue

        except Exception as e:
            logger.error(f"Failed to crawl issue {issue_id}: {e}")
            raise

    async def download_attachments(
        self,
        issue: Issue,
        credentials: UserCredentials
    ) -> List[Attachment]:
        """
        Download and process attachments for an issue.

        Args:
            issue: Issue entity
            credentials: User credentials

        Returns:
            List of Attachment entities with extracted text

        Raises:
            CrawlerError: If download/processing fails
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        attachments = []

        try:
            # Navigate to issue page if not already there
            if self._page.url != issue.ims_url:
                await self._page.goto(issue.ims_url)
                await self._page.wait_for_load_state('networkidle')

            # Find attachment links
            attachment_elements = await self._page.query_selector_all('.attachment-link')

            for idx, attach_elem in enumerate(attachment_elements):
                try:
                    # Extract attachment metadata
                    filename = await attach_elem.get_attribute('data-filename')
                    if not filename:
                        filename_elem = await attach_elem.query_selector('.attachment-name')
                        filename = await filename_elem.inner_text() if filename_elem else f"attachment_{idx}"

                    download_url = await attach_elem.get_attribute('href')

                    # Determine file type
                    file_type = self._determine_file_type(filename)

                    # Create issue-specific directory
                    issue_dir = self.attachments_dir / self._sanitize_filename(issue.ims_id)
                    issue_dir.mkdir(exist_ok=True)

                    # Download file
                    filepath = issue_dir / self._sanitize_filename(filename)

                    # Use Playwright's download functionality
                    async with self._page.expect_download() as download_info:
                        await attach_elem.click()

                    download = await download_info.value
                    await download.save_as(str(filepath))

                    logger.info(f"Downloaded: {filename}")

                    # Create Attachment entity
                    attachment = Attachment(
                        id=uuid4(),
                        issue_id=issue.id,
                        filename=filename,
                        file_type=file_type,
                        file_size=filepath.stat().st_size if filepath.exists() else 0,
                        download_url=download_url,
                        local_path=str(filepath),
                        extracted_text=None,  # Will be populated by attachment processor
                        created_at=datetime.utcnow()
                    )

                    attachments.append(attachment)

                except Exception as e:
                    logger.warning(f"Failed to download attachment {idx}: {e}")
                    continue

            logger.info(f"Downloaded {len(attachments)} attachments for issue {issue.ims_id}")
            return attachments

        except Exception as e:
            logger.error(f"Failed to download attachments: {e}")
            return []

    async def crawl_related_issues(
        self,
        issue: Issue,
        credentials: UserCredentials,
        max_depth: int = 1
    ) -> List[Issue]:
        """
        Recursively crawl issues related to the given issue.

        Args:
            issue: Source issue
            credentials: User credentials
            max_depth: Maximum recursion depth

        Returns:
            List of related Issue entities

        Raises:
            CrawlerError: If crawling fails
        """
        if max_depth <= 0:
            return []

        if not self._authenticated:
            await self.authenticate(credentials)

        related_issues = []
        crawled_ids: Set[str] = {issue.ims_id}

        try:
            # Navigate to issue page
            if self._page.url != issue.ims_url:
                await self._page.goto(issue.ims_url)
                await self._page.wait_for_load_state('networkidle')

            # Find related issue links
            related_elements = await self._page.query_selector_all('.related-issue a')

            for related_elem in related_elements:
                try:
                    # Extract related issue ID
                    related_url = await related_elem.get_attribute('href')
                    related_id = related_url.split('/')[-1] if related_url else None

                    if not related_id or related_id in crawled_ids:
                        continue

                    # Crawl related issue details
                    related_issue = await self.crawl_issue_details(related_id, credentials)
                    related_issues.append(related_issue)
                    crawled_ids.add(related_id)

                    # Recursively crawl deeper levels
                    if max_depth > 1:
                        deeper_issues = await self.crawl_related_issues(
                            related_issue, credentials, max_depth - 1
                        )
                        for deeper_issue in deeper_issues:
                            if deeper_issue.ims_id not in crawled_ids:
                                related_issues.append(deeper_issue)
                                crawled_ids.add(deeper_issue.ims_id)

                except Exception as e:
                    logger.warning(f"Failed to crawl related issue: {e}")
                    continue

            logger.info(f"Found {len(related_issues)} related issues for {issue.ims_id}")
            return related_issues

        except Exception as e:
            logger.error(f"Failed to crawl related issues: {e}")
            return []

    async def close(self) -> None:
        """Clean up browser resources."""
        if self._page:
            await self._page.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._authenticated = False
        logger.info("Browser resources cleaned up")

    # Helper methods

    @staticmethod
    def _parse_status(status_text: str) -> IssueStatus:
        """Parse status text to IssueStatus enum."""
        status_upper = status_text.upper().strip()
        try:
            return IssueStatus[status_upper]
        except KeyError:
            logger.warning(f"Unknown status: {status_text}, defaulting to OPEN")
            return IssueStatus.OPEN

    @staticmethod
    def _parse_priority(priority_text: str) -> IssuePriority:
        """Parse priority text to IssuePriority enum."""
        priority_upper = priority_text.upper().strip()
        try:
            return IssuePriority[priority_upper]
        except KeyError:
            logger.warning(f"Unknown priority: {priority_text}, defaulting to MEDIUM")
            return IssuePriority.MEDIUM

    @staticmethod
    def _determine_file_type(filename: str) -> AttachmentType:
        """Determine file type from filename extension."""
        ext = Path(filename).suffix.lower()

        if ext in ['.pdf']:
            return AttachmentType.PDF
        elif ext in ['.doc', '.docx']:
            return AttachmentType.DOCUMENT
        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            return AttachmentType.IMAGE
        elif ext in ['.txt', '.log']:
            return AttachmentType.TEXT
        else:
            return AttachmentType.OTHER

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename for filesystem safety."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_length = 250 - len(ext)
            filename = name[:max_name_length] + ('.' + ext if ext else '')

        return filename
