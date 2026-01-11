"""
Playwright Crawler Adapter - Concrete implementation using Playwright

Web automation implementation for crawling IMS system.
"""

import sys
import re
import asyncio
import logging
from typing import List, Optional, Set
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from datetime import datetime, timezone
from uuid import uuid4

# Windows asyncio fix: Enable subprocess support for Playwright
# SelectorEventLoop (default on Windows) doesn't support subprocesses
# ProactorEventLoop is required for asyncio.create_subprocess_exec()
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from ...domain.entities import Issue, Attachment, UserCredentials, IssueStatus, IssuePriority
from ...domain.entities.attachment import AttachmentType
from ..ports.crawler_port import CrawlerPort
from ..services.credential_encryption_service import CredentialEncryptionService
from ....core.config import get_api_settings

logger = logging.getLogger(__name__)

# Load API settings for timeout configuration
_api_settings = get_api_settings()


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

            logger.info("Starting Playwright browser...")

            # Windows: uvicorn reload is disabled in main.py, so ProactorEventLoop is always used
            # This ensures async subprocess creation works correctly for Playwright
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=self.headless)
                self._context = None
                logger.info("Browser initialized successfully")
            except NotImplementedError as nie:
                # This happens if SelectorEventLoop is used (should not happen with our fix)
                logger.error(f"Playwright failed - likely SelectorEventLoop issue: {nie}")
                raise RuntimeError(
                    "Playwright requires ProactorEventLoop on Windows. "
                    "Ensure you are running: python -m app.api.main --mode develop"
                ) from nie
            except Exception as e:
                logger.error(f"Playwright startup failed: {e}")
                raise RuntimeError(
                    f"Playwright cannot start: {e}"
                ) from e

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
            await self._page.wait_for_selector('input[name="id"]', timeout=_api_settings.IMS_CRAWLER_LOGIN_TIMEOUT)

            # Fill login form (IMS uses 'id' not 'username')
            await self._page.fill('input[name="id"]', username)
            await self._page.fill('input[name="password"]', password)

            # Submit login (IMS uses image button)
            await self._page.click('input[type="image"]')

            # Wait for navigation after login
            await self._page.wait_for_load_state('networkidle', timeout=_api_settings.IMS_CRAWLER_NAVIGATION_TIMEOUT)

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

    # Default products to select for search (TmaxSoft IMS product codes)
    # OpenFrame products, ProSort, ProTrieve
    DEFAULT_PRODUCT_CODES = [
        # OpenFrame products
        '128',   # OpenFrame AIM
        '520',   # OpenFrame ASM
        '129',   # OpenFrame Base
        '123',   # OpenFrame Batch
        '500',   # OpenFrame COBOL
        '137',   # OpenFrame Common
        '141',   # OpenFrame GW
        '126',   # OpenFrame HiDB
        '147',   # OpenFrame ISPF
        '145',   # OpenFrame Manager
        '135',   # OpenFrame Map GUI Editor
        '143',   # OpenFrame Miner
        '138',   # OpenFrame OSC
        '134',   # OpenFrame OSI
        '142',   # OpenFrame OpenStudio Web
        '510',   # OpenFrame PLI
        '127',   # OpenFrame Studio
        '124',   # OpenFrame TACF
        # Other products
        '640',   # ProSort
        '425',   # ProTrieve
    ]

    # Product name patterns for fallback matching
    DEFAULT_PRODUCTS = [
        'OpenFrame',  # Will match all products starting with OpenFrame
        'ProSort',
        'ProTrieve',
    ]

    @staticmethod
    def _transform_to_ims_query(query: str) -> str:
        """
        Transform natural language query to IMS search syntax.

        IMS Search Pattern Rules:
        1. Space-separated words = OR search
           ex) "티맥스 티베로" → searches for '티맥스' OR '티베로'

        2. +word (no space before word) = AND search
           ex) "IMS +에러" → 'IMS' AND '에러'

        3. 'phrase' (single quotes) = exact match
           ex) '에러 로그' → exact match for "에러 로그"

        4. Can combine above rules
           ex) "티맥스 '에러 로그' +티베로" → '티맥스' or '에러 로그' with '티베로'

        5. Issue Number, Bug Number - multiple values separated by space

        Args:
            query: Natural language search query

        Returns:
            IMS-compatible search query string
        """
        if not query:
            return ""

        # The query is already in IMS format, just clean it up
        cleaned_query = query.strip()

        # Log the transformation for debugging
        logger.debug(f"Query transformation: '{query}' -> '{cleaned_query}'")

        return cleaned_query

    async def search_issues(
        self,
        query: str,
        credentials: UserCredentials,
        product_codes: Optional[List[str]] = None
    ) -> List[Issue]:
        """
        Search for issues matching the query.

        Args:
            query: IMS search syntax query (supports OR/AND/exact match patterns)
                   - Space-separated words = OR search (word1 word2)
                   - +word = AND search (word1 +word2)
                   - 'phrase' = exact match ('exact phrase')
            credentials: User credentials for authentication
            product_codes: Optional list of product codes to filter (e.g., ['128', '520']).
                          If None, uses DEFAULT_PRODUCT_CODES.

        Returns:
            List of Issue entities

        Raises:
            CrawlerError: If search fails
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        try:
            # Transform query to IMS search syntax
            ims_query = self._transform_to_ims_query(query)
            logger.info(f"Search query: '{query}' -> IMS query: '{ims_query}'")

            # Navigate to IMS issue search page
            search_url = f"{credentials.ims_base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
            await self._page.goto(search_url)
            await self._page.wait_for_load_state('networkidle')
            logger.info(f"Navigated to search page: {search_url}")

            # Wait for search form to load
            await self._page.wait_for_selector('#SearchDiv', timeout=_api_settings.IMS_CRAWLER_SELECTOR_TIMEOUT)

            # Debug: Dump form structure to understand the DOM
            await self._debug_dump_search_form()

            # Select products (use provided product_codes or default)
            codes_to_select = product_codes if product_codes else self.DEFAULT_PRODUCT_CODES
            await self._select_products(codes_to_select)

            # Enter search keyword - try multiple selectors
            keyword_input = await self._find_keyword_input()
            if keyword_input:
                await keyword_input.fill(ims_query)
                logger.info(f"Entered search keyword: {ims_query}")
            else:
                logger.warning("Could not find keyword input field - search may return all results")

            # Click search button - this triggers a form submission that reloads the page
            # We need to wait for the navigation to complete before extracting results
            try:
                # Start waiting for navigation before clicking
                async with self._page.expect_navigation(timeout=_api_settings.IMS_CRAWLER_NAVIGATION_TIMEOUT, wait_until='networkidle'):
                    await self._click_search_button()
                logger.info("Search form submitted and page navigation completed")
            except Exception as nav_error:
                # If expect_navigation fails, the page might not navigate (AJAX search)
                logger.info(f"Navigation wait completed or timed out: {nav_error}")
                await self._page.wait_for_load_state('networkidle')

            # Wait for results to be visible
            # Try to wait for common result indicators
            await asyncio.sleep(2)  # Additional wait for dynamic content

            # Wait for result table or result count to appear
            try:
                await self._page.wait_for_selector(
                    'table.list, #listTable, div.listCnt, span.total, #resultDiv table, table.dataTable',
                    timeout=_api_settings.IMS_CRAWLER_SELECTOR_TIMEOUT
                )
            except Exception:
                logger.warning("Could not find result table selector, proceeding anyway")

            # Change page size to show all results (DataTables pagination fix)
            await self._set_page_size_to_all()

            # Extract issue rows from search results table
            issues = await self._extract_search_results(credentials)

            logger.info(f"Found {len(issues)} issues from search")
            return issues

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    async def _set_page_size_to_all(self) -> None:
        """Change page size to show all results.

        TmaxSoft IMS uses a custom #pageSize select element with options:
        10, 20, 30, 50, 100, 500, 1000

        The onchange handler triggers a page navigation/reload.
        """
        try:
            print("[PageSize] Attempting to change page size to 1000...", flush=True)

            # TmaxSoft IMS uses #pageSize select element
            page_size_select = await self._page.query_selector('#pageSize')
            if page_size_select:
                print("[PageSize] Found #pageSize selector", flush=True)

                # Check current value
                current_value = await page_size_select.evaluate('el => el.value')
                print(f"[PageSize] Current page size: {current_value}", flush=True)

                if current_value == '1000':
                    print("[PageSize] Already set to 1000, skipping", flush=True)
                    return

                # Select 1000 - this triggers pageSizeChange() which causes page navigation
                # We need to wait for the navigation to complete
                try:
                    async with self._page.expect_navigation(timeout=_api_settings.IMS_CRAWLER_NAVIGATION_TIMEOUT):
                        await page_size_select.select_option(value='1000')
                    print("[PageSize] Navigation completed after page size change", flush=True)
                except Exception as nav_error:
                    print(f"[PageSize] Navigation wait: {nav_error}", flush=True)
                    # Even if navigation fails, wait for page to stabilize
                    await asyncio.sleep(2)

                # Wait for page to fully load
                await self._page.wait_for_load_state('networkidle')
                await self._page.wait_for_load_state('domcontentloaded')

                # Wait for table to be rendered
                try:
                    await self._page.wait_for_selector('table.dataTable tbody tr', timeout=_api_settings.IMS_CRAWLER_SELECTOR_TIMEOUT)
                    print("[PageSize] Table rows found after page size change", flush=True)
                except Exception:
                    print("[PageSize] Table rows selector timeout, continuing anyway", flush=True)

                # Additional stabilization wait
                await asyncio.sleep(1)
                print("[PageSize] Page reloaded with 1000 rows", flush=True)
                return

            # Fallback: try other common selectors
            fallback_selectors = [
                'select[name="pageSize"]',
                'select.custom-select[name="pageSize"]',
            ]

            for selector in fallback_selectors:
                page_size_select = await self._page.query_selector(selector)
                if page_size_select:
                    print(f"[PageSize] Found fallback selector: {selector}", flush=True)
                    try:
                        async with self._page.expect_navigation(timeout=_api_settings.IMS_CRAWLER_NAVIGATION_TIMEOUT):
                            await page_size_select.select_option(value='1000')
                    except Exception:
                        await asyncio.sleep(2)
                    await self._page.wait_for_load_state('networkidle')
                    print("[PageSize] Selected page size: 1000 (fallback)", flush=True)
                    return

            print("[PageSize] No page size selector found", flush=True)

        except Exception as e:
            print(f"[PageSize] Failed to set page size: {e}", flush=True)

    async def _debug_dump_search_form(self) -> None:
        """Dump search form structure for debugging."""
        try:
            # Get all form elements in SearchDiv
            form_structure = await self._page.evaluate('''() => {
                const searchDiv = document.querySelector('#SearchDiv');
                if (!searchDiv) return { error: 'SearchDiv not found' };

                const result = {
                    selects: [],
                    inputs: [],
                    checkboxes: [],
                    buttons: [],
                    links: []
                };

                // Find all select elements
                searchDiv.querySelectorAll('select').forEach(sel => {
                    const options = Array.from(sel.options).slice(0, 10).map(opt => ({
                        value: opt.value,
                        text: opt.textContent?.trim().substring(0, 50)
                    }));
                    result.selects.push({
                        name: sel.name,
                        id: sel.id,
                        className: sel.className,
                        optionCount: sel.options.length,
                        sampleOptions: options
                    });
                });

                // Find all text inputs
                searchDiv.querySelectorAll('input[type="text"], input:not([type])').forEach(inp => {
                    result.inputs.push({
                        name: inp.name,
                        id: inp.id,
                        className: inp.className,
                        placeholder: inp.placeholder,
                        value: inp.value
                    });
                });

                // Find all checkboxes
                searchDiv.querySelectorAll('input[type="checkbox"]').forEach(chk => {
                    const label = chk.parentElement?.textContent?.trim().substring(0, 30) || '';
                    result.checkboxes.push({
                        name: chk.name,
                        id: chk.id,
                        value: chk.value,
                        checked: chk.checked,
                        label: label
                    });
                });

                // Find all buttons
                searchDiv.querySelectorAll('input[type="button"], input[type="submit"], button').forEach(btn => {
                    result.buttons.push({
                        type: btn.type,
                        value: btn.value,
                        id: btn.id,
                        className: btn.className,
                        onclick: btn.getAttribute('onclick')?.substring(0, 50)
                    });
                });

                // Find links with onclick
                searchDiv.querySelectorAll('a[onclick]').forEach(link => {
                    result.links.push({
                        text: link.textContent?.trim().substring(0, 30),
                        onclick: link.getAttribute('onclick')?.substring(0, 50)
                    });
                });

                return result;
            }''')

            logger.info(f"=== SEARCH FORM STRUCTURE ===")
            logger.info(f"Selects: {form_structure.get('selects', [])}")
            logger.info(f"Text Inputs: {form_structure.get('inputs', [])}")
            logger.info(f"Checkboxes: {form_structure.get('checkboxes', [])}")
            logger.info(f"Buttons: {form_structure.get('buttons', [])}")
            logger.info(f"Links: {form_structure.get('links', [])}")
            logger.info(f"=== END FORM STRUCTURE ===")

        except Exception as e:
            logger.warning(f"Failed to dump form structure: {e}")

    async def _find_keyword_input(self):
        """Find keyword input field with multiple fallback selectors."""
        # Primary selector for TmaxSoft IMS: input#keyword
        selectors = [
            '#keyword',                    # TmaxSoft IMS primary keyword field
            'input[name="keyword"]',       # By name attribute
            '#searchKeyword',
            'input[name="searchKeyword"]',
            'input[name="searchWord"]',
            'input[name="searchText"]',
            '#searchWord',
            # TmaxSoft IMS specific selectors
            'input[name="issueSearchVO.searchText"]',
            'input[name="issueSearchVO.searchKeyword"]',
        ]

        for selector in selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    # Verify it's a text input
                    input_type = await element.get_attribute('type')
                    if input_type is None or input_type == 'text':
                        logger.info(f"Found keyword input with selector: {selector}")
                        return element
            except Exception:
                continue

        # Fallback: Try to find by class or position
        fallback_selectors = [
            'input.width290px[type="text"]',  # TmaxSoft IMS uses this class
            '#SearchDiv input[type="text"]:not([readonly])',
        ]

        for selector in fallback_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    logger.info(f"Found keyword input with fallback selector: {selector}")
                    return element
            except Exception:
                continue

        logger.warning("Could not find keyword input with any known selector")
        return None

    async def _click_search_button(self) -> bool:
        """Click the search button with multiple fallback strategies."""
        # Primary Strategy: TmaxSoft IMS uses goReportSearch() function
        try:
            search_executed = await self._page.evaluate('''() => {
                // TmaxSoft IMS specific search function
                if (typeof goReportSearch === 'function' && document.issueSearchForm) {
                    goReportSearch(document.issueSearchForm, '1');
                    return 'goReportSearch';
                }
                return null;
            }''')

            if search_executed:
                logger.info(f"Executed search via JavaScript function: {search_executed}")
                return True
        except Exception as e:
            logger.debug(f"goReportSearch execution failed: {e}")

        # Fallback Strategy 1: Click the Search button/link
        selectors = [
            'a[onclick*="goReportSearch"]',    # TmaxSoft IMS search link
            'a:has-text("Search")',
            'input[type="button"][value*="Search"]',
            'input[type="button"][value*="검색"]',
            'input[type="submit"][value*="검색"]',
            'button:has-text("검색")',
            'a[onclick*="search"]',
            '#btnSearch',
            '#searchBtn',
        ]

        for selector in selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    await element.click()
                    logger.info(f"Clicked search button with selector: {selector}")
                    return True
            except Exception:
                continue

        # Fallback Strategy 2: Try other common search function names
        try:
            search_executed = await self._page.evaluate('''() => {
                const searchFunctions = ['fnSearch', 'search', 'doSearch', 'searchList', 'issueSearch'];
                for (const fn of searchFunctions) {
                    if (typeof window[fn] === 'function') {
                        window[fn]();
                        return fn;
                    }
                }
                return null;
            }''')

            if search_executed:
                logger.info(f"Executed search via JavaScript function: {search_executed}")
                return True
        except Exception as e:
            logger.debug(f"JavaScript search execution failed: {e}")

        # Last resort: press Enter
        await self._page.keyboard.press('Enter')
        logger.info("Pressed Enter to submit search (fallback)")
        return True

    async def _select_products(self, product_codes: List[str]) -> None:
        """Select products for search based on provided product codes.

        Args:
            product_codes: List of product codes to select (e.g., ['128', '520'])
        """
        try:
            logger.info(f"Selecting {len(product_codes)} products: {product_codes[:5]}...")

            # Primary Strategy: TmaxSoft IMS uses select#productCodes (multi-select)
            product_select = await self._page.query_selector('#productCodes')
            if product_select:
                logger.info("Found product select element: #productCodes")

                # Select products by their code values directly
                try:
                    await product_select.select_option(value=product_codes)
                    logger.info(f"Selected {len(product_codes)} products by code values")
                    return
                except Exception as e:
                    logger.warning(f"Failed to select by code values: {e}")
                    # Fallback: try selecting by text matching
                    options = await product_select.query_selector_all('option')
                    values_to_select = []

                    for option in options:
                        text = await option.inner_text()
                        value = await option.get_attribute('value')

                        # Check if value is in our provided codes
                        if value in product_codes:
                            values_to_select.append(value)
                            logger.info(f"Will select product: {text} (value={value})")
                        # Or check by name pattern for fallback
                        elif any(text.startswith(prod) or prod in text for prod in self.DEFAULT_PRODUCTS):
                            if value in self.DEFAULT_PRODUCT_CODES and value in product_codes:
                                values_to_select.append(value)
                                logger.info(f"Will select product by name: {text} (value={value})")

                    if values_to_select:
                        await product_select.select_option(value=values_to_select)
                        logger.info(f"Selected {len(values_to_select)} products by fallback matching")
                        return

            # Fallback Strategy 1: Look for other select elements
            select_selectors = [
                'select[name="productCodes"]',
                'select[name*="product"]',
                'select[name*="Product"]',
                'select[id*="product"]',
            ]

            for selector in select_selectors:
                product_select = await self._page.query_selector(selector)
                if product_select:
                    logger.info(f"Found product select with selector: {selector}")
                    options = await product_select.query_selector_all('option')
                    values_to_select = []

                    for option in options:
                        text = await option.inner_text()
                        value = await option.get_attribute('value')

                        # Check by code
                        if value in product_codes:
                            values_to_select.append(value)
                            logger.info(f"Will select product option: {text} (value={value})")

                    if values_to_select:
                        is_multiple = await product_select.get_attribute('multiple')
                        if is_multiple:
                            await product_select.select_option(value=values_to_select)
                        else:
                            await product_select.select_option(value=values_to_select[0])
                        logger.info(f"Selected {len(values_to_select)} product options")
                        return

            # Fallback Strategy 2: Look for checkboxes
            product_checkboxes = await self._page.query_selector_all('input[type="checkbox"][name*="product"]')
            if product_checkboxes:
                logger.info(f"Found {len(product_checkboxes)} product checkboxes")
                selected_count = 0
                for checkbox in product_checkboxes:
                    try:
                        value = await checkbox.get_attribute('value')
                        label = await checkbox.evaluate('el => el.parentElement?.textContent?.trim().substring(0, 50) || el.value || ""')

                        should_select = value in product_codes

                        if should_select:
                            is_checked = await checkbox.is_checked()
                            if not is_checked:
                                await checkbox.click()
                                selected_count += 1
                                logger.info(f"Selected product checkbox: {label}")
                    except Exception as e:
                        logger.debug(f"Failed to process checkbox: {e}")
                        continue

                if selected_count > 0:
                    logger.info(f"Selected {selected_count} product checkboxes")
                    return

            logger.warning("Could not find product selection element")

        except Exception as e:
            logger.warning(f"Failed to select products: {e}")

    async def _select_products_in_popup(self) -> None:
        """Select products in a popup dialog."""
        try:
            # Wait for popup to appear
            await asyncio.sleep(0.3)

            # Look for checkboxes in popup/modal
            popup_selectors = [
                '.popup input[type="checkbox"]',
                '.modal input[type="checkbox"]',
                '#productLayer input[type="checkbox"]',
                '[role="dialog"] input[type="checkbox"]',
                '.layer input[type="checkbox"]',
            ]

            for selector in popup_selectors:
                checkboxes = await self._page.query_selector_all(selector)
                if checkboxes:
                    logger.info(f"Found {len(checkboxes)} checkboxes in popup")
                    for checkbox in checkboxes:
                        label = await checkbox.evaluate('el => el.parentElement?.textContent?.trim().substring(0, 50) || el.value || ""')

                        should_select = any(
                            label.startswith(prod) or prod in label
                            for prod in self.DEFAULT_PRODUCTS
                        )

                        if should_select:
                            is_checked = await checkbox.is_checked()
                            if not is_checked:
                                await checkbox.click()
                                logger.info(f"Selected product in popup: {label}")

                    # Click confirm/OK button in popup
                    confirm_selectors = [
                        '.popup input[type="button"][value*="확인"]',
                        '.modal button:has-text("확인")',
                        '.modal button:has-text("OK")',
                        '[role="dialog"] button:has-text("확인")',
                        'input[type="button"][value="확인"]',
                    ]
                    for btn_selector in confirm_selectors:
                        confirm_btn = await self._page.query_selector(btn_selector)
                        if confirm_btn:
                            await confirm_btn.click()
                            logger.info("Clicked confirm button in popup")
                            break
                    return

        except Exception as e:
            logger.warning(f"Failed to select products in popup: {e}")

    async def _select_products_by_pattern(self) -> None:
        """Select products by finding elements with matching text patterns."""
        try:
            # Use JavaScript to find and click elements containing product names
            result = await self._page.evaluate('''(products) => {
                const selected = [];

                // Find all clickable elements containing product names
                const clickables = document.querySelectorAll('input[type="checkbox"], a, span, div, td');

                for (const el of clickables) {
                    const text = el.textContent?.trim() || el.value || '';

                    for (const product of products) {
                        if (text.includes(product)) {
                            // If it's a checkbox, check it
                            if (el.type === 'checkbox' && !el.checked) {
                                el.click();
                                selected.push(text.substring(0, 50));
                            }
                            // If it's inside a row with a checkbox, click the checkbox
                            else if (el.tagName !== 'INPUT') {
                                const row = el.closest('tr');
                                if (row) {
                                    const checkbox = row.querySelector('input[type="checkbox"]');
                                    if (checkbox && !checkbox.checked) {
                                        checkbox.click();
                                        selected.push(text.substring(0, 50));
                                    }
                                }
                            }
                            break;
                        }
                    }
                }

                return selected;
            }''', self.DEFAULT_PRODUCTS)

            if result:
                logger.info(f"Selected products by pattern: {result}")
            else:
                logger.warning("No products found matching the pattern")

        except Exception as e:
            logger.warning(f"Pattern-based product selection failed: {e}")

    async def _extract_search_results(
        self,
        credentials: UserCredentials
    ) -> List[Issue]:
        """Extract issues from search results table.

        TmaxSoft IMS uses DataTables with the following structure:
        - Table class: 'table table-bordered dataTable'
        - Parent div class: 'dataTables_wrapper'
        - Row onclick: popBlankIssueView('issueId', 'menuCode')
        - Cell structure: No, Issue Number, Category, Product, Version, Module, Subject, Customer, Project, Reporter
        """
        issues = []
        extracted_ids = set()  # Track extracted issue IDs to avoid duplicates
        import re

        try:
            page_num = 1
            max_pages = 20  # Safety limit

            while page_num <= max_pages:
                # TmaxSoft IMS DataTables selector (most specific first)
                result_rows = await self._page.query_selector_all('table.dataTable tr[onclick*="popBlankIssueView"]')
                if not result_rows:
                    result_rows = await self._page.query_selector_all('table.dataTable tbody tr')
                if not result_rows:
                    result_rows = await self._page.query_selector_all('.dataTables_wrapper table tr:not(:first-child)')
                if not result_rows:
                    # Fallback to older selectors
                    result_rows = await self._page.query_selector_all('table.list tbody tr')
                if not result_rows:
                    result_rows = await self._page.query_selector_all('#listTable tbody tr')

                print(f"[Extract] Page {page_num}: Found {len(result_rows)} result rows", flush=True)

                new_issues_on_page = 0
                for idx, row in enumerate(result_rows):
                    try:
                        # Extract cells from each row
                        cells = await row.query_selector_all('td')
                        if len(cells) < 3:
                            print(f"[Extract] Row {idx}: Skipped - only {len(cells)} cells", flush=True)
                            continue

                        issue_id = ""
                        issue_url = ""
                        title = ""

                        # Primary method: Extract issue ID from row onclick handler
                        # Format: popBlankIssueView('350475', 'issue_search')
                        row_onclick = await row.get_attribute('onclick')
                        if row_onclick:
                            id_match = re.search(r"popBlankIssueView\s*\(\s*['\"](\d+)['\"]", row_onclick)
                            if id_match:
                                issue_id = id_match.group(1)
                                logger.debug(f"Extracted issue ID from onclick: {issue_id}")

                        # Debug: Log row info and ALL cell contents (ASCII-safe for Windows)
                        if idx == 0:  # Only first row to understand structure
                            logger.info(f"[Extract] Row {idx}: cells={len(cells)}, onclick={'yes' if row_onclick else 'no'}, issue_id={issue_id}")
                            # Print ALL cell contents for debugging (all 31 cells)
                            for ci in range(len(cells)):
                                cell_text = await cells[ci].evaluate('el => el.textContent || ""')
                                cell_text = cell_text.strip()[:80]  # Truncate for readability
                                # Use ASCII-safe encoding for Windows console
                                safe_text = cell_text.encode('ascii', 'replace').decode('ascii')
                                logger.info(f"[Extract] Row {idx} Cell {ci}: '{safe_text}'")

                        # TmaxSoft IMS cell structure:
                        # Cell 0: Row number (8194)
                        # Cell 1: Issue Number (350475)
                        # Cell 2: Category (Technical Support)
                        # Cell 3: Product (OpenFrame Base)
                        # Cell 4: Version (7.3)
                        # Cell 5: Module (General)
                        # Cell 6: Subject (title)
                        # Cell 7: Customer
                        # Cell 8: Project
                        # Cell 9: Reporter
                        # Cell 10: Issued Date (등록일)
                        # Cell 11: Issue Details (상세 내용)
                        # Cell 12: Action No (액션 번호)

                        # Extract all fields from cells
                        category = ""
                        product = ""
                        version = ""
                        module = ""
                        customer = ""
                        issued_date = None
                        reporter = ""
                        issue_details = ""
                        action_no = ""

                        # Debug: Print first 3 rows' extraction data
                        debug_row = idx < 3

                        if not issue_id and len(cells) > 1:
                            # Get issue ID from cell 1 (Issue Number column)
                            issue_num_cell = await cells[1].inner_text()
                            cell1_text = issue_num_cell.strip()
                            if cell1_text.isdigit():
                                issue_id = cell1_text
                            elif idx < 5:
                                print(f"[Extract] Row {idx}: Cell 1 text '{cell1_text}' is not a digit", flush=True)

                        # Extract Category (cell 2)
                        if len(cells) > 2:
                            category = (await cells[2].evaluate('el => el.textContent || ""')).strip()

                        # Extract Product (cell 3)
                        if len(cells) > 3:
                            product = (await cells[3].evaluate('el => el.textContent || ""')).strip()

                        # Extract Version (cell 4)
                        if len(cells) > 4:
                            version = (await cells[4].evaluate('el => el.textContent || ""')).strip()

                        # Extract Module (cell 5)
                        if len(cells) > 5:
                            module = (await cells[5].evaluate('el => el.textContent || ""')).strip()

                        # Extract Issue Details (cell 11)
                        if len(cells) > 11:
                            issue_details = (await cells[11].evaluate('el => el.textContent || ""')).strip()

                        # Extract Action No (cell 12)
                        if len(cells) > 12:
                            action_no = (await cells[12].evaluate('el => el.textContent || ""')).strip()

                        # Debug: Print extracted column data for first 3 rows
                        if debug_row:
                            print(f"[Extract] Row {idx} Columns: cat='{category[:20]}' prod='{product[:20]}' ver='{version}' mod='{module[:20]}' details='{issue_details[:30]}' action='{action_no}'", flush=True)

                        # Skip if already extracted (pagination duplicate prevention)
                        if issue_id in extracted_ids:
                            continue
                        extracted_ids.add(issue_id)

                        # Get title from cell 6 (Subject column)
                        # Title may be inside <a> tag or other nested elements
                        if len(cells) > 6:
                            subject_cell = cells[6]
                            # Try getting text from <a> tag first (most common)
                            link_elem = await subject_cell.query_selector('a')
                            if link_elem:
                                title = await link_elem.inner_text()
                            else:
                                # Try getting all text content using JavaScript
                                title = await subject_cell.evaluate('el => el.textContent || el.innerText || ""')
                            # Normalize whitespace: replace multiple spaces/newlines/tabs with single space
                            title = re.sub(r'\s+', ' ', title).strip() if title else ""
                            # Use ASCII-safe logging for Windows
                            safe_title = (title[:100] if title else 'EMPTY').encode('ascii', 'replace').decode('ascii')
                            logger.debug(f"Row {idx}: Subject cell text = '{safe_title}'")

                        # Extract Customer (cell 7)
                        if len(cells) > 7:
                            customer = (await cells[7].evaluate('el => el.textContent || ""')).strip()

                        # Extract Reporter (cell 9)
                        if len(cells) > 9:
                            reporter = (await cells[9].evaluate('el => el.textContent || ""')).strip()

                        # Extract Issued Date (cell 10)
                        if len(cells) > 10:
                            date_str = (await cells[10].evaluate('el => el.textContent || ""')).strip()
                            if date_str:
                                try:
                                    # Try common date formats
                                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%d-%m-%Y', '%d/%m/%Y']:
                                        try:
                                            issued_date = datetime.strptime(date_str, fmt)
                                            break
                                        except ValueError:
                                            continue
                                except Exception:
                                    pass

                        # Fallback: try to get title from other cells with longer text
                        if not title or len(title) < 3:
                            for cell_idx in range(len(cells)):
                                if cell_idx < len(cells):
                                    cell_text = await cells[cell_idx].evaluate('el => el.textContent || ""')
                                    # Normalize whitespace
                                    cell_text = re.sub(r'\s+', ' ', cell_text).strip()
                                    # Subject/title usually has longer text than other cells
                                    if len(cell_text) > 10 and not cell_text.isdigit():
                                        title = cell_text
                                        logger.debug(f"Row {idx}: Found title from cell {cell_idx}: '{title[:50]}'")
                                        break

                        if not issue_id:
                            print(f"[Extract] Row {idx}: No issue_id found, skipping", flush=True)
                            continue

                        # Create Issue entity with all extracted fields
                        issue = Issue(
                            id=uuid4(),
                            user_id=credentials.user_id,
                            ims_id=issue_id,
                            title=title.strip() if title else f"Issue {issue_id}",
                            description="",
                            status=IssueStatus.OPEN,
                            priority=IssuePriority.MEDIUM,
                            # IMS-specific fields
                            category=category,
                            product=product,
                            version=version,
                            module=module,
                            customer=customer,
                            issued_date=issued_date,
                            issue_details=issue_details,
                            action_no=action_no,
                            reporter=reporter,
                            source_url=issue_url or f"{credentials.ims_base_url}/tody/ims/issue/issueView.do?issueId={issue_id}",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        issues.append(issue)
                        new_issues_on_page += 1
                        logger.debug(f"Extracted issue: {issue_id} - {title[:50] if title else 'No title'}")

                    except Exception as e:
                        logger.warning(f"Failed to extract issue from row {idx}: {e}")
                        continue

                print(f"[Extract] Page {page_num}: Extracted {new_issues_on_page} new issues (total: {len(issues)})", flush=True)

                # With page size set to 1000, we should have all results on one page
                # Only check for next page if we have exactly the page limit (indicating more pages)
                if len(result_rows) < 1000:
                    print(f"[Extract] All {len(issues)} issues extracted (less than page limit)", flush=True)
                    break

                # Check for next page button if needed
                next_button = await self._page.query_selector('.dataTables_paginate .next:not(.disabled), .paginate_button.next:not(.disabled)')
                if next_button:
                    # Check if next button is disabled
                    next_class = await next_button.get_attribute('class') or ''
                    if 'disabled' in next_class:
                        print("[Extract] Next button is disabled - reached last page", flush=True)
                        break

                    print(f"[Extract] Clicking next page button...", flush=True)
                    await next_button.click()
                    await asyncio.sleep(1)
                    await self._page.wait_for_load_state('networkidle')
                    page_num += 1
                else:
                    print("[Extract] No next page button found - single page or last page", flush=True)
                    break

        except Exception as e:
            print(f"[Extract] Failed to extract search results: {e}", flush=True)

        print(f"[Extract] Total issues extracted from all pages: {len(issues)}", flush=True)
        return issues

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

        Raises:
            CrawlerError: If crawling fails
        """
        if not self._authenticated:
            await self.authenticate(credentials)

        try:
            # TmaxSoft IMS issue detail URL format
            issue_url = f"{credentials.ims_base_url}/tody/ims/issue/issueView.do?issueId={issue_id}"
            logger.info(f"Navigating to issue detail page: {issue_url}")

            await self._page.goto(issue_url)
            await self._page.wait_for_load_state('networkidle')

            # TmaxSoft IMS specific selectors
            # Try multiple selectors for title
            title = ""
            title_selectors = [
                '#subject',  # TmaxSoft IMS subject field
                'input[name="subject"]',
                '.issue-subject',
                '#issueSubject',
                'td:has-text("Subject") + td',
                'h1.issue-title',
                '.detail-title',
                '#detailSubject'
            ]

            for selector in title_selectors:
                try:
                    title_elem = await self._page.query_selector(selector)
                    if title_elem:
                        # Check if it's an input element
                        tag_name = await title_elem.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name == 'input':
                            title = await title_elem.get_attribute('value') or ""
                        else:
                            title = await title_elem.inner_text()
                        title = title.strip()
                        if title and title != "Untitled":
                            logger.debug(f"Found title with selector '{selector}': {title[:50]}")
                            break
                except Exception:
                    continue

            # Fallback to issue from search results if title not found
            if not title or title == "Untitled":
                if fallback_issue and fallback_issue.title:
                    title = fallback_issue.title
                    logger.debug(f"Using fallback title from search: {title[:50]}")
                else:
                    title = f"Issue {issue_id}"

            # Try multiple selectors for description
            description = ""
            desc_selectors = [
                '#contents',  # TmaxSoft IMS contents field
                'textarea[name="contents"]',
                '.issue-description',
                '#issueContents',
                '.detail-description',
                '#detailContents'
            ]

            for selector in desc_selectors:
                try:
                    desc_elem = await self._page.query_selector(selector)
                    if desc_elem:
                        tag_name = await desc_elem.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name == 'textarea':
                            description = await desc_elem.evaluate('el => el.value || el.textContent || ""')
                        else:
                            description = await desc_elem.inner_text()
                        description = description.strip()
                        if description:
                            break
                except Exception:
                    continue

            # Status - TmaxSoft IMS format
            status = IssueStatus.OPEN
            status_selectors = ['#status', 'select[name="status"]', '.issue-status']
            for selector in status_selectors:
                try:
                    status_elem = await self._page.query_selector(selector)
                    if status_elem:
                        status_text = await status_elem.evaluate('el => el.value || el.textContent || ""')
                        status = self._parse_status(status_text.strip())
                        break
                except Exception:
                    continue

            # Priority
            priority = IssuePriority.MEDIUM
            priority_selectors = ['#priority', 'select[name="priority"]', '.issue-priority']
            for selector in priority_selectors:
                try:
                    priority_elem = await self._page.query_selector(selector)
                    if priority_elem:
                        priority_text = await priority_elem.evaluate('el => el.value || el.textContent || ""')
                        priority = self._parse_priority(priority_text.strip())
                        break
                except Exception:
                    continue

            # Reporter
            reporter = "Unknown"
            reporter_selectors = ['#reporter', 'input[name="reporter"]', '.issue-reporter']
            for selector in reporter_selectors:
                try:
                    reporter_elem = await self._page.query_selector(selector)
                    if reporter_elem:
                        reporter = await reporter_elem.evaluate('el => el.value || el.textContent || ""')
                        reporter = reporter.strip() or "Unknown"
                        break
                except Exception:
                    continue

            # Assignee
            assignee = None
            assignee_selectors = ['#assignee', 'input[name="assignee"]', '.issue-assignee']
            for selector in assignee_selectors:
                try:
                    assignee_elem = await self._page.query_selector(selector)
                    if assignee_elem:
                        assignee = await assignee_elem.evaluate('el => el.value || el.textContent || ""')
                        assignee = assignee.strip() or None
                        break
                except Exception:
                    continue

            # Project
            project_key = "UNKNOWN"
            project_selectors = ['#project', 'select[name="project"]', '.issue-project']
            for selector in project_selectors:
                try:
                    project_elem = await self._page.query_selector(selector)
                    if project_elem:
                        project_key = await project_elem.evaluate('el => el.value || el.textContent || ""')
                        project_key = project_key.strip() or "UNKNOWN"
                        break
                except Exception:
                    continue

            # Labels
            labels = []
            try:
                label_elements = await self._page.query_selector_all('.issue-label, .label-tag, .tag')
                for label_elem in label_elements:
                    label_text = await label_elem.inner_text()
                    if label_text.strip():
                        labels.append(label_text.strip())
            except Exception:
                pass

            # Create Issue entity, preserving IMS-specific fields from fallback_issue if available
            issue = Issue(
                id=uuid4(),
                user_id=credentials.user_id,
                ims_id=issue_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                # Preserve IMS-specific fields from search results (fallback_issue)
                category=fallback_issue.category if fallback_issue else "",
                product=fallback_issue.product if fallback_issue else "",
                version=fallback_issue.version if fallback_issue else "",
                module=fallback_issue.module if fallback_issue else "",
                customer=fallback_issue.customer if fallback_issue else "",
                issued_date=fallback_issue.issued_date if fallback_issue else None,
                issue_details=fallback_issue.issue_details if fallback_issue else "",
                action_no=fallback_issue.action_no if fallback_issue else "",
                # Metadata from detail page
                reporter=reporter or (fallback_issue.reporter if fallback_issue else ""),
                assignee=assignee,
                project_key=project_key,
                labels=labels,
                source_url=issue_url,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            logger.info(f"Crawled issue details: {issue_id} - '{title[:50]}'")
            return issue

        except Exception as e:
            logger.error(f"Failed to crawl issue {issue_id}: {e}")
            # Return fallback issue if available
            if fallback_issue:
                logger.info(f"Returning fallback issue for {issue_id}")
                return fallback_issue
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
            if self._page.url != issue.source_url:
                await self._page.goto(issue.source_url)
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
                        created_at=datetime.now(timezone.utc)
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
            if self._page.url != issue.source_url:
                await self._page.goto(issue.source_url)
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

    async def crawl_issues_parallel(
        self,
        issues: List[Issue],
        credentials: UserCredentials,
        batch_size: int = 10,
        progress_callback: Optional[callable] = None
    ) -> List[Issue]:
        """
        Crawl multiple issues in parallel using multiple browser pages.

        Args:
            issues: List of issues to crawl (from search results)
            credentials: User credentials
            batch_size: Number of concurrent pages to use (default: 10)
            progress_callback: Optional callback for progress updates

        Returns:
            List of crawled Issue entities sorted by ims_id descending
        """
        if not issues:
            return []

        if not self._authenticated:
            await self.authenticate(credentials)

        # Sort issues by ims_id descending (largest first) for output order
        sorted_issues = sorted(issues, key=lambda x: int(x.ims_id) if x.ims_id.isdigit() else 0, reverse=True)

        crawled_results: List[Issue] = []
        total_issues = len(sorted_issues)
        total_batches = (total_issues + batch_size - 1) // batch_size

        if progress_callback:
            progress_callback({
                "phase": "crawl_start",
                "total_issues": total_issues,
                "total_batches": total_batches,
                "batch_size": batch_size
            })

        # Process in batches
        for batch_start in range(0, total_issues, batch_size):
            batch_end = min(batch_start + batch_size, total_issues)
            batch = sorted_issues[batch_start:batch_end]
            batch_num = batch_start // batch_size + 1
            progress_pct = min(100, int((batch_num / total_batches) * 100))

            print(f"[Parallel] Crawling batch {batch_num}/{total_batches}: issues {batch_start + 1}-{batch_end} of {total_issues} ({progress_pct}%)", flush=True)

            if progress_callback:
                progress_callback({
                    "phase": "crawl_batch_start",
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_start": batch_start + 1,
                    "batch_end": batch_end,
                    "total_issues": total_issues,
                    "progress_percent": progress_pct
                })

            # Create pages for this batch
            pages: List[Page] = []
            try:
                for _ in batch:
                    page = await self._context.new_page()
                    pages.append(page)

                # Crawl all issues in batch concurrently
                async def crawl_single_issue(page: Page, issue: Issue) -> Issue:
                    """Crawl a single issue using the provided page."""
                    try:
                        issue_url = f"{credentials.ims_base_url}/tody/ims/issue/issueView.do?issueId={issue.ims_id}"
                        await page.goto(issue_url)
                        await page.wait_for_load_state('networkidle')

                        # Extract title
                        title = ""
                        title_selectors = [
                            '#subject', 'input[name="subject"]', '.issue-subject',
                            '#issueSubject', 'h1.issue-title', '.detail-title', '#detailSubject'
                        ]
                        for selector in title_selectors:
                            try:
                                title_elem = await page.query_selector(selector)
                                if title_elem:
                                    tag_name = await title_elem.evaluate('el => el.tagName.toLowerCase()')
                                    if tag_name == 'input':
                                        title = await title_elem.get_attribute('value') or ""
                                    else:
                                        title = await title_elem.inner_text()
                                    title = title.strip()
                                    if title and title != "Untitled":
                                        break
                            except:
                                continue

                        if not title or title == "Untitled":
                            title = issue.title if issue.title else f"Issue {issue.ims_id}"

                        # Extract description
                        description = ""
                        desc_selectors = [
                            '#contents', 'textarea[name="contents"]', '.issue-description',
                            '#issueContents', '.detail-description', '#detailContents'
                        ]
                        for selector in desc_selectors:
                            try:
                                desc_elem = await page.query_selector(selector)
                                if desc_elem:
                                    tag_name = await desc_elem.evaluate('el => el.tagName.toLowerCase()')
                                    if tag_name == 'textarea':
                                        description = await desc_elem.evaluate('el => el.value || el.textContent || ""')
                                    else:
                                        description = await desc_elem.inner_text()
                                    description = description.strip()
                                    if description:
                                        break
                            except:
                                continue

                        # Status
                        status = IssueStatus.OPEN
                        status_selectors = ['#status', 'select[name="status"]', '.issue-status']
                        for selector in status_selectors:
                            try:
                                status_elem = await page.query_selector(selector)
                                if status_elem:
                                    status_text = await status_elem.evaluate('el => el.value || el.textContent || ""')
                                    status = self._parse_status(status_text.strip())
                                    break
                            except:
                                continue

                        # Priority
                        priority = IssuePriority.MEDIUM
                        priority_selectors = ['#priority', 'select[name="priority"]', '.issue-priority']
                        for selector in priority_selectors:
                            try:
                                priority_elem = await page.query_selector(selector)
                                if priority_elem:
                                    priority_text = await priority_elem.evaluate('el => el.value || el.textContent || ""')
                                    priority = self._parse_priority(priority_text.strip())
                                    break
                            except:
                                continue

                        # Reporter
                        reporter = issue.reporter if issue.reporter else "Unknown"

                        # Assignee
                        assignee = issue.assignee

                        # Project
                        project_key = issue.project_key if issue.project_key else "UNKNOWN"

                        # Labels
                        labels = issue.labels if issue.labels else []

                        # Create Issue entity, preserving IMS-specific fields from original issue
                        crawled_issue = Issue(
                            id=uuid4(),
                            user_id=credentials.user_id,
                            ims_id=issue.ims_id,
                            title=title,
                            description=description,
                            status=status,
                            priority=priority,
                            # Preserve IMS-specific fields from search results
                            category=issue.category,
                            product=issue.product,
                            version=issue.version,
                            module=issue.module,
                            customer=issue.customer,
                            issued_date=issue.issued_date,
                            issue_details=issue.issue_details,
                            action_no=issue.action_no,
                            # Metadata
                            reporter=reporter,
                            assignee=assignee,
                            project_key=project_key,
                            labels=labels,
                            source_url=issue_url,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )

                        return crawled_issue

                    except Exception as e:
                        logger.warning(f"[Parallel] Failed to crawl {issue.ims_id}: {e}")
                        # Return the original issue as fallback
                        return issue

                # Execute parallel crawling for this batch
                tasks = [crawl_single_issue(pages[i], batch[i]) for i in range(len(batch))]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect results
                success_count = 0
                fail_count = 0
                for i, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.warning(f"[Parallel] Exception for issue {batch[i].ims_id}: {result}")
                        crawled_results.append(batch[i])  # Use original as fallback
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
                        "total_issues": total_issues,
                        "progress_percent": progress_pct
                    })

            finally:
                # Clean up pages after batch
                for page in pages:
                    try:
                        await page.close()
                    except:
                        pass

        if progress_callback:
            progress_callback({
                "phase": "crawl_complete",
                "crawled_count": len(crawled_results),
                "total_issues": total_issues
            })

        # Results are already in descending order by ims_id
        print(f"[Parallel] Completed crawling {len(crawled_results)} issues", flush=True)
        return crawled_results

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
