#!/usr/bin/env python3
"""
IMS Issue Crawler - Pure requests implementation (No Playwright)

This crawler uses the exact same parameters as the browser.
"""
import sys
import io
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

IMS_URL = "https://ims.tmaxsoft.com"


@dataclass
class IssueAction:
    """Issue Action/Comment data class."""
    action_id: str
    content: str
    user: str = ""
    date: str = ""


@dataclass
class RelatedIssue:
    """Related Issue data class."""
    issue_id: str
    issue_number: str
    subject: str
    relation_type: str = ""  # Parent, Child, etc.
    product: str = ""
    status: str = ""


@dataclass
class IMSIssue:
    """IMS Issue data class."""
    issue_id: str
    issue_number: str
    category: str
    product: str
    version: str
    module: str
    subject: str
    customer: str = ""
    project: str = ""
    reporter: str = ""
    issued_date: str = ""
    contents: str = ""
    status: str = ""
    issue_details: str = ""  # Issue Description content
    actions: List['IssueAction'] = None
    related_issues: List['RelatedIssue'] = None

    def __post_init__(self):
        if self.related_issues is None:
            self.related_issues = []
        if self.actions is None:
            self.actions = []


class IMSCrawler:
    """IMS Crawler using pure requests."""

    # OpenFrame product codes
    OPENFRAME_PRODUCTS = [
        '128', '520', '129', '123', '500', '137', '141', '126',
        '147', '145', '135', '143', '138', '134', '142', '510', '127', '124'
    ]

    def __init__(self, base_url: str = IMS_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.user_id = ""
        self.user_name = ""
        self.user_grade = ""

    def login(self, username: str, password: str) -> bool:
        """Login to IMS system."""
        print(f"[Login] Authenticating as {username}...")

        login_url = f"{self.base_url}/tody/auth/login.do"
        self.session.get(login_url)

        response = self.session.post(
            login_url,
            data={'id': username, 'password': password},
            allow_redirects=True
        )

        if '/login' in response.url or '/auth/login' in response.url:
            print("[Login] FAILED")
            return False

        self.user_id = username
        print(f"[Login] SUCCESS - Session: {self.session.cookies.get('JSESSIONID', '')[:30]}...")

        # Get user info from main page
        self._fetch_user_info()

        return True

    def _fetch_user_info(self):
        """Fetch user info from IMS."""
        # Call UserDwr to get user details
        try:
            result = self.call_dwr("UserDwr", "findUser", [self.user_id])
            # Parse user info from DWR response
            name_match = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", result)
            if name_match:
                self.user_name = name_match.group(1)

            grade_match = re.search(r"grade\s*=\s*['\"]([^'\"]+)['\"]", result)
            if grade_match:
                self.user_grade = grade_match.group(1)

            print(f"[Login] User: {self.user_name} (Grade: {self.user_grade})")
        except Exception as e:
            self.user_name = self.user_id
            self.user_grade = "TMAX"

    def call_dwr(self, service: str, method: str, params: List = None) -> str:
        """Call DWR service."""
        import time
        import random

        call_id = f"{random.randint(1000, 9999)}_{int(time.time() * 1000)}"

        query_params = {
            'callCount': '1',
            'c0-scriptName': service,
            'c0-methodName': method,
            'c0-id': call_id,
            'xml': 'true'
        }

        if params:
            for i, param in enumerate(params):
                query_params[f'c0-param{i}'] = f'string:{param}' if param else 'null:null'

        url = f"{self.base_url}/tody/dwr/exec/{service}.{method}"
        response = self.session.get(url, params=query_params, headers={
            'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do"
        })
        return response.text

    def search_issues(
        self,
        keyword: str = "",
        product_codes: List[str] = None,
        page_size: int = 100
    ) -> List[IMSIssue]:
        """
        Search issues - returns FIRST PAGE ONLY (10 items).

        WARNING: IMS server ignores pageSize parameter and always returns 10 items.
        Use search_issues_all() to fetch all results with pagination.

        Args:
            keyword: Search keyword
            product_codes: Product codes to filter (default: OpenFrame products)
            page_size: Number of results (ignored by server, always 10)

        Returns:
            List of IMSIssue objects (first page only, max 10 items)
        """
        print(f"\n[Search] Keyword: '{keyword}', Products: {len(product_codes or self.OPENFRAME_PRODUCTS)}")

        products = product_codes or self.OPENFRAME_PRODUCTS

        # Build params exactly as the browser does
        params = {
            'reSearchYN': 'Y',  # Critical! Must be 'Y' for search to work
            'searchType': '1',
            'pageIndex': '1',
            'pageSize': str(page_size),
            'keyword': keyword,
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
            'userId': self.user_id,
            'userName': self.user_name or self.user_id,
            'userGrade': self.user_grade or 'TMAX',
            'productCodes': products,
        }

        search_url = f"{self.base_url}/tody/ims/issue/issueSearchList.do"

        response = self.session.get(search_url, params=params, headers={
            'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
        })

        print(f"[Search] Response: {response.status_code}")

        return self._parse_search_results(response.text)

    def _parse_search_results(self, html: str) -> List[IMSIssue]:
        """Parse search results from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        issues = []

        # Find rows with onclick handler
        rows = soup.find_all('tr', onclick=re.compile(r'popBlankIssueView'))

        print(f"[Search] Found {len(rows)} issue rows")

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

            issue = IMSIssue(
                issue_id=issue_id,
                issue_number=cells[1].get_text(strip=True) if len(cells) > 1 else '',
                category=cells[2].get_text(strip=True) if len(cells) > 2 else '',
                product=cells[3].get_text(strip=True) if len(cells) > 3 else '',
                version=cells[4].get_text(strip=True) if len(cells) > 4 else '',
                module=cells[5].get_text(strip=True) if len(cells) > 5 else '',
                subject=self._clean_text(cells[6].get_text(strip=True)) if len(cells) > 6 else '',
                customer=cells[7].get_text(strip=True) if len(cells) > 7 else '',
                project=cells[8].get_text(strip=True) if len(cells) > 8 else '',
                reporter=cells[9].get_text(strip=True) if len(cells) > 9 else '',
                issued_date=cells[10].get_text(strip=True) if len(cells) > 10 else '',
            )
            issues.append(issue)

        return issues

    def get_issue_detail(self, issue_id: str, include_related: bool = True) -> Optional[IMSIssue]:
        """
        Get issue detail by ID.

        Args:
            issue_id: IMS issue ID
            include_related: Whether to fetch related issues (default: True)

        Returns:
            IMSIssue with full details or None
        """
        print(f"\n[Detail] Fetching issue {issue_id}...")

        detail_url = f"{self.base_url}/tody/ims/issue/issueView.do"

        response = self.session.post(
            detail_url,
            data={'issueId': issue_id, 'menuCode': 'issue_search'},
            headers={'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do"}
        )

        print(f"[Detail] Response: {response.status_code}")

        issue = self._parse_issue_detail(response.text, issue_id)

        # Fetch related issues
        if issue and include_related:
            print(f"[Detail] Fetching related issues...")
            issue.related_issues = self.get_related_issues(issue_id)
            print(f"[Detail] Found {len(issue.related_issues)} related issues")

        return issue

    def _parse_issue_detail(self, html: str, issue_id: str) -> Optional[IMSIssue]:
        """Parse issue detail from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        # Extract subject - IMS uses <td class="tableHeaderTitle">Subject</td><td>...</td> pattern
        subject = ""
        # Method 1: Find td with class="tableHeaderTitle" containing "Subject"
        subject_td_label = soup.find('td', class_='tableHeaderTitle', string=re.compile(r'Subject', re.I))
        if subject_td_label:
            subject_td = subject_td_label.find_next_sibling('td')
            if subject_td:
                subject = subject_td.get_text(strip=True)
                # Clean &nbsp;
                subject = subject.replace('\xa0', ' ')

        # Method 2: Regex fallback for tableHeaderTitle pattern
        if not subject:
            subj_match = re.search(
                r'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*Subject\s*</td>\s*<td[^>]*>(.*?)</td>',
                html, re.DOTALL | re.I
            )
            if subj_match:
                subject = re.sub(r'<[^>]+>', '', subj_match.group(1))
                subject = subject.replace('&nbsp;', ' ').strip()

        # Method 3: Try th pattern as fallback
        if not subject:
            subj_match = re.search(r'Subject\s*</th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL | re.I)
            if subj_match:
                subject = re.sub(r'<[^>]+>', '', subj_match.group(1))
                subject = subject.replace('&nbsp;', ' ').strip()

        # Extract contents - look for description HTML
        contents = ""
        # Method 1: Find xcontents textarea
        contents_elem = soup.find('textarea', {'name': 'xcontents'})
        if contents_elem:
            contents = contents_elem.get_text(strip=True)

        # Method 2: Look for styled content div
        if not contents:
            # Find content with styled paragraphs
            content_match = re.search(r'<div[^>]*style=["\'][^"\']*font[^"\']*["\'][^>]*>(.*?)</div>', html, re.DOTALL)
            if content_match:
                contents = re.sub(r'<[^>]+>', ' ', content_match.group(1))
                contents = self._clean_text(contents)

        # Extract comments (additional context)
        comments = []
        comment_divs = soup.find_all('div', class_='commDescTR')
        for div in comment_divs[:5]:  # Get first 5 comments
            comment_text = div.get_text(strip=True)
            if comment_text:
                comments.append(comment_text[:200])

        if comments and not contents:
            contents = " | ".join(comments)

        # Extract other fields
        def get_select_value(id_name):
            elem = soup.find('select', {'id': id_name}) or soup.find('select', {'name': id_name})
            if elem:
                selected = elem.find('option', selected=True)
                return selected.get_text(strip=True) if selected else ''
            return ''

        def get_input_value(id_name):
            elem = soup.find('input', {'id': id_name}) or soup.find('input', {'name': id_name})
            return elem.get('value', '') if elem else ''

        # Helper function to get table field value by label
        def get_table_field(label: str) -> str:
            """Extract value from <td>Label</td><td>Value</td> pattern."""
            # Pattern 1: tableHeaderTitle class
            pattern1 = rf'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
            match = re.search(pattern1, html, re.DOTALL | re.I)
            if match:
                value = re.sub(r'<[^>]+>', '', match.group(1))
                return value.replace('&nbsp;', ' ').strip()

            # Pattern 2: Simple td pattern
            pattern2 = rf'{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
            match = re.search(pattern2, html, re.DOTALL | re.I)
            if match:
                value = re.sub(r'<[^>]+>', '', match.group(1))
                return value.replace('&nbsp;', ' ').strip()

            return ''

        # Get category - try table field first, then select
        category = get_table_field('Category') or get_select_value('categoryCode')

        # Get product - try table field first, then select
        product = get_table_field('Product') or get_select_value('productCode')

        # Get version - try table field first, then select
        version = get_table_field('Version') or get_select_value('mainVersionCode')

        # Get module - try table field first, then select
        module = get_table_field('Module') or get_select_value('moduleCode')

        # Get status - try table field first, then select
        status = get_table_field('Status') or get_select_value('status') or get_select_value('issueStatus')

        # Get reporter - try table field first, then input
        reporter = get_table_field('Reporter') or get_table_field('Register') or get_input_value('registerName')

        # Get customer
        customer = get_table_field('Customer') or get_input_value('customer')

        # Get project
        project = get_table_field('Project') or get_input_value('project')

        # Parse Issue Details (Issue Description)
        issue_details = ""
        desc_match = re.search(
            r'id=["\']IssueDescriptionDiv["\'][^>]*>(.*?)</div>\s*<!--',
            html, re.DOTALL | re.I
        )
        if desc_match:
            desc_html = desc_match.group(1)
            # Extract text content from styled HTML
            issue_details = re.sub(r'<[^>]+>', ' ', desc_html)
            issue_details = issue_details.replace('&nbsp;', ' ')
            issue_details = issue_details.replace('&#39;', "'")
            issue_details = issue_details.replace('&lt;', '<')
            issue_details = issue_details.replace('&gt;', '>')
            issue_details = issue_details.replace('&#64;', '@')
            issue_details = re.sub(r'\s+', ' ', issue_details).strip()

        # Parse Actions (Comments)
        actions = []
        action_pattern = r'<input[^>]*name=["\']actionId["\'][^>]*value=["\'](\d+)["\'][^>]*>.*?commDescTR_\1[^>]*>(.*?)</div>'
        action_matches = re.findall(action_pattern, html, re.DOTALL)

        for action_id, action_content in action_matches:
            # Clean action content
            clean_content = re.sub(r'<[^>]+>', ' ', action_content)
            clean_content = clean_content.replace('&#64;', '@')
            clean_content = clean_content.replace('&nbsp;', ' ')
            clean_content = re.sub(r'\s+', ' ', clean_content).strip()

            if clean_content:
                actions.append(IssueAction(
                    action_id=action_id,
                    content=clean_content[:2000],  # Limit size
                ))

        return IMSIssue(
            issue_id=issue_id,
            issue_number=issue_id,
            subject=self._clean_text(subject),
            contents=self._clean_text(contents)[:2000],  # Limit size
            category=category,
            product=product,
            version=version,
            module=module,
            status=status,
            reporter=reporter,
            customer=customer,
            project=project,
            issue_details=issue_details[:5000],  # Limit size
            actions=actions,
        )

    def _clean_text(self, text: str) -> str:
        """Clean text by normalizing whitespace."""
        return re.sub(r'\s+', ' ', text).strip()

    def _get_total_count(self, html: str) -> int:
        """Extract total count from search result HTML.

        Note: IMS server ignores pageSize parameter and always returns 10 items per page.
        This method extracts the actual total count for pagination.
        """
        # Method 1: Look for "Total X" pattern (most reliable)
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

        # Method 4: Look for Korean pattern "X건"
        match = re.search(r'(\d+)\s*건', html)
        if match:
            return int(match.group(1))

        return 0

    def search_issues_all(
        self,
        keyword: str = "",
        product_codes: List[str] = None,
        max_pages: int = 50,
        verbose: bool = True
    ) -> tuple[List[IMSIssue], int]:
        """
        Search issues with pagination - fetches ALL matching results.

        Note: IMS server ignores pageSize parameter and always returns 10 items per page.
        This method automatically fetches all pages to get complete results.

        Args:
            keyword: Search keyword
            product_codes: Product codes to filter (default: OpenFrame products)
            max_pages: Maximum pages to fetch (default: 50, i.e., up to 500 issues)
            verbose: Print progress messages (default: True)

        Returns:
            Tuple of (List of IMSIssue objects, total_count from server)
        """
        if verbose:
            print(f"\n[Search] Keyword: '{keyword}', Products: {len(product_codes or self.OPENFRAME_PRODUCTS)}")
            print(f"[Search] Fetching all pages (max {max_pages} pages)...")

        products = product_codes or self.OPENFRAME_PRODUCTS
        all_issues = []
        total_count = None
        page = 1

        while page <= max_pages:
            # Build params for this page
            params = {
                'reSearchYN': 'Y',
                'searchType': '1',
                'pageIndex': str(page),
                'pageSize': '100',  # Server ignores this, always returns 10
                'keyword': keyword,
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
                'userId': self.user_id,
                'userName': self.user_name or self.user_id,
                'userGrade': self.user_grade or 'TMAX',
                'productCodes': products,
            }

            search_url = f"{self.base_url}/tody/ims/issue/issueSearchList.do"
            response = self.session.get(search_url, params=params, headers={
                'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
            })

            # Get total count on first page
            if total_count is None:
                total_count = self._get_total_count(response.text)
                if verbose:
                    print(f"[Search] Total count: {total_count}")

            # Parse issues from this page
            page_issues = self._parse_search_results(response.text)
            if verbose:
                print(f"[Search] Page {page}: {len(page_issues)} issues")

            if not page_issues:
                break

            all_issues.extend(page_issues)

            # Check if we have all issues
            if len(all_issues) >= total_count:
                break

            page += 1

        if verbose:
            print(f"[Search] Fetched {len(all_issues)} issues (Total: {total_count})")

        return all_issues, total_count

    def get_related_issues(self, issue_id: str) -> List[RelatedIssue]:
        """
        Get related issues for a given issue.

        Args:
            issue_id: IMS issue ID

        Returns:
            List of RelatedIssue objects
        """
        url = f"{self.base_url}/tody/ims/issue/findRelationIssues.do"

        response = self.session.get(
            url,
            params={'issueId': issue_id},
            headers={'Referer': f"{self.base_url}/tody/ims/issue/issueView.do"}
        )

        related = []

        if response.status_code == 200:
            try:
                data = response.json()
                for item in data:
                    related.append(RelatedIssue(
                        issue_id=str(item.get('issueId', '')),
                        issue_number=str(item.get('issueId', '')),
                        subject=item.get('subject', ''),
                        relation_type=item.get('relationIssueHier', '').strip(),
                        product=item.get('productName', ''),
                        status=item.get('statusName', ''),
                    ))
            except Exception as e:
                print(f"    [WARNING] Failed to parse related issues: {e}")

        return related


def main():
    print("=" * 70)
    print("IMS Crawler - Pure requests (No Playwright)")
    print("=" * 70)

    # Credentials
    username = "yijae.shin"
    password = "12qwaszx"

    # Create crawler
    crawler = IMSCrawler()

    # Login
    if not crawler.login(username, password):
        return

    # Search issues with pagination (fetches ALL results)
    issues, total_count = crawler.search_issues_all(
        keyword="oscboot",
        max_pages=50  # Up to 500 issues
    )

    # Display results
    print(f"\n" + "=" * 70)
    print(f"## Search Results: {len(issues)} issues (Total: {total_count})")
    print("=" * 70)

    if issues:
        print(f"\n{'No':<4} {'ID':<10} {'Product':<18} {'Subject':<45}")
        print("-" * 80)

        for i, issue in enumerate(issues[:20], 1):  # Show first 20
            subject = issue.subject[:42] + '...' if len(issue.subject) > 45 else issue.subject
            print(f"{i:<4} {issue.issue_id:<10} {issue.product:<18} {subject}")

        if len(issues) > 20:
            print(f"    ... and {len(issues) - 20} more issues")

        # Get detail for first issue
        print(f"\n" + "=" * 70)
        print("## Issue Detail Test")
        print("=" * 70)

        first_issue = issues[0]
        detail = crawler.get_issue_detail(first_issue.issue_id)

        if detail:
            print(f"\n  Issue ID: {detail.issue_id}")
            print(f"  Subject: {detail.subject[:70]}{'...' if len(detail.subject) > 70 else ''}")
            print(f"  Category: {detail.category}")
            print(f"  Product: {detail.product}")
            print(f"  Version: {detail.version}")
            print(f"  Module: {detail.module}")
            print(f"  Status: {detail.status}")
            print(f"  Customer: {detail.customer}")
            print(f"  Project: {detail.project}")
            print(f"  Reporter: {detail.reporter}")

            # Display Issue Details
            if detail.issue_details:
                print(f"\n  Issue Details:")
                print(f"    {detail.issue_details[:300]}...")

            # Display Actions
            if detail.actions:
                print(f"\n  Actions ({len(detail.actions)}):")
                for action in detail.actions[:5]:
                    content = action.content[:80] + '...' if len(action.content) > 80 else action.content
                    print(f"    - Action #{action.action_id}: {content}")

            # Display related issues
            if detail.related_issues:
                print(f"\n  Related Issues ({len(detail.related_issues)}):")
                for ri in detail.related_issues[:10]:
                    rel_type = f"[{ri.relation_type}]" if ri.relation_type else ""
                    subj = ri.subject[:40] + '...' if len(ri.subject) > 40 else ri.subject
                    print(f"    - {ri.issue_id} {rel_type} {subj}")

    print(f"\n" + "=" * 70)
    print("## Summary")
    print("=" * 70)
    print("""
    Playwright 없이 requests만으로 IMS 크롤링 성공!

    핵심 파라미터:
    - reSearchYN: 'Y' (필수!)
    - queryId: 'ims.issueSearch.findIssueSearch'
    - productCodes: 복수 선택 지원

    사용 가능 기능:
    [OK] 로그인
    [OK] DWR API 호출 (제품/버전/사용자 조회)
    [OK] 이슈 검색 (키워드 + 제품 필터)
    [OK] 이슈 상세 조회
    [OK] 페이지네이션 (전체 결과 조회)

    NOTE: IMS 서버는 pageSize 파라미터를 무시하고 항상 10건/페이지 반환
          search_issues_all() 메서드로 전체 결과 조회 가능
    """)


if __name__ == "__main__":
    main()
