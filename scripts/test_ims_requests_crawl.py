#!/usr/bin/env python3
"""
IMS Issue Crawler using pure requests (no Playwright)

Test if we can crawl IMS issues using only:
- requests (HTTP client)
- BeautifulSoup (HTML parsing)
"""
import sys
import io
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
from typing import List, Dict, Optional

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"

# OpenFrame product codes
OPENFRAME_PRODUCTS = [
    '128', '520', '129', '123', '500', '137', '141', '126',
    '147', '145', '135', '143', '138', '134', '142', '510', '127', '124'
]


class IMSRequestsCrawler:
    """IMS Crawler using requests library."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def login(self, username: str, password: str) -> bool:
        """Login to IMS system."""
        print(f"[1] Logging in as {username}...")

        # Get login page first (for any cookies/tokens)
        login_url = f"{self.base_url}/tody/auth/login.do"
        self.session.get(login_url)

        # Submit login form
        login_data = {
            'id': username,
            'password': password
        }

        response = self.session.post(login_url, data=login_data, allow_redirects=True)

        # Check if login successful
        if '/login' in response.url or '/auth/login' in response.url:
            print("[ERROR] Login failed - still on login page")
            return False

        print(f"[OK] Login successful")
        print(f"    Session: {self.session.cookies.get('JSESSIONID', 'N/A')[:40]}...")
        return True

    def search_issues(
        self,
        keyword: str = "",
        product_codes: List[str] = None,
        page_index: int = 1,
        page_size: int = 100
    ) -> Dict:
        """
        Search issues using form submission.

        Args:
            keyword: Search keyword
            product_codes: List of product codes to filter
            page_index: Page number (1-based)
            page_size: Number of results per page

        Returns:
            Dict with issues list and metadata
        """
        print(f"\n[2] Searching issues...")
        print(f"    Keyword: {keyword}")
        print(f"    Products: {len(product_codes or [])} selected")

        search_url = f"{self.base_url}/tody/ims/issue/issueSearchList.do"

        # Build form data
        form_data = {
            'searchType': '1',
            'menuCode': 'issue_search',
            'pageIndex': str(page_index),
            'pageSize': str(page_size),
            'keyword': keyword,
            'reSearchYN': 'N',
            'hintMsg': '',
            'clickColumn': '',
            'orderType': '',
            'paramProdCodes': '',
            'menuLink': '',
            'reportType': '',
        }

        # Add product codes (IMS expects multiple values with same key)
        if product_codes:
            form_data['productCodes'] = product_codes

        # Set referer header
        headers = {
            'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search",
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # Submit search form (GET with query params or POST)
        # IMS uses GET for search
        response = self.session.get(search_url, params=form_data, headers=headers)

        print(f"    Response status: {response.status_code}")
        print(f"    Response URL: {response.url[:80]}...")

        # Parse HTML response
        return self._parse_search_results(response.text)

    def _parse_search_results(self, html: str) -> Dict:
        """Parse search results from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        issues = []

        # Find the data table
        # IMS uses DataTables with class 'dataTable'
        table = soup.find('table', class_='dataTable')
        if not table:
            table = soup.find('table', class_='list')
        if not table:
            # Try to find any table with issue data
            tables = soup.find_all('table')
            for t in tables:
                if t.find('tr', onclick=True):
                    table = t
                    break

        if not table:
            print("    [WARNING] No data table found")
            # Save HTML for debugging
            with open('debug_search_response.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print("    Saved response to debug_search_response.html")
            return {'issues': [], 'total': 0, 'error': 'No table found'}

        # Find all rows with onclick handler
        rows = table.find_all('tr', onclick=re.compile(r'popBlankIssueView'))

        print(f"    Found {len(rows)} issue rows")

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue

            # Extract issue ID from onclick
            onclick = row.get('onclick', '')
            id_match = re.search(r"popBlankIssueView\s*\(\s*['\"](\d+)['\"]", onclick)
            issue_id = id_match.group(1) if id_match else ''

            issue = {
                'issue_id': issue_id,
                'issue_number': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                'category': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                'product': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                'version': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                'module': cells[5].get_text(strip=True) if len(cells) > 5 else '',
                'subject': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                'customer': cells[7].get_text(strip=True) if len(cells) > 7 else '',
                'reporter': cells[9].get_text(strip=True) if len(cells) > 9 else '',
                'issued_date': cells[10].get_text(strip=True) if len(cells) > 10 else '',
            }
            issues.append(issue)

        return {
            'issues': issues,
            'total': len(issues)
        }

    def get_issue_detail(self, issue_id: str) -> Dict:
        """
        Get issue detail by ID.

        Args:
            issue_id: IMS issue ID

        Returns:
            Dict with issue details
        """
        print(f"\n[3] Fetching issue detail: {issue_id}")

        detail_url = f"{self.base_url}/tody/ims/issue/issueView.do"

        # IMS uses POST for issue detail
        form_data = {
            'issueId': issue_id,
            'menuCode': 'issue_search'
        }

        headers = {
            'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
        }

        response = self.session.post(detail_url, data=form_data, headers=headers)

        print(f"    Response status: {response.status_code}")

        return self._parse_issue_detail(response.text, issue_id)

    def _parse_issue_detail(self, html: str, issue_id: str) -> Dict:
        """Parse issue detail from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        detail = {
            'issue_id': issue_id,
            'subject': '',
            'contents': '',
            'status': '',
            'priority': '',
            'category': '',
            'product': '',
            'version': '',
            'module': '',
            'reporter': '',
            'assignee': '',
            'customer': '',
            'project': '',
            'attachments': []
        }

        # Try to find subject/title
        subject_input = soup.find('input', {'id': 'subject'}) or soup.find('input', {'name': 'subject'})
        if subject_input:
            detail['subject'] = subject_input.get('value', '')

        # Try to find contents/description
        contents_elem = soup.find('textarea', {'id': 'contents'}) or soup.find('textarea', {'name': 'contents'})
        if contents_elem:
            detail['contents'] = contents_elem.get_text(strip=True)
        else:
            # Try div with contents
            contents_div = soup.find('div', {'id': 'contents'}) or soup.find('div', class_='contents')
            if contents_div:
                detail['contents'] = contents_div.get_text(strip=True)

        # Try to find other fields by common patterns
        field_mappings = [
            ('status', ['#status', 'select[name="status"]', '#issueStatus']),
            ('priority', ['#priority', 'select[name="priority"]']),
            ('category', ['#categoryCode', 'select[name="categoryCode"]']),
            ('product', ['#productCode', 'select[name="productCode"]']),
            ('reporter', ['#registerName', 'input[name="registerName"]']),
        ]

        for field_name, selectors in field_mappings:
            for selector in selectors:
                elem = soup.select_one(selector)
                if elem:
                    if elem.name == 'select':
                        selected = elem.find('option', selected=True)
                        detail[field_name] = selected.get_text(strip=True) if selected else ''
                    elif elem.name == 'input':
                        detail[field_name] = elem.get('value', '')
                    else:
                        detail[field_name] = elem.get_text(strip=True)
                    break

        # Find attachments
        attachment_links = soup.find_all('a', href=re.compile(r'fileDown|download'))
        for link in attachment_links:
            detail['attachments'].append({
                'name': link.get_text(strip=True),
                'url': link.get('href', '')
            })

        return detail

    def call_dwr(self, service: str, method: str, params: List = None) -> str:
        """
        Call DWR service directly.

        Args:
            service: DWR service name (e.g., 'ProductDwr')
            method: Method name (e.g., 'findVersions')
            params: List of parameters

        Returns:
            Raw response text
        """
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
                if param is None:
                    query_params[f'c0-param{i}'] = 'null:null'
                else:
                    query_params[f'c0-param{i}'] = f'string:{param}'

        url = f"{self.base_url}/tody/dwr/exec/{service}.{method}"
        headers = {
            'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do"
        }

        response = self.session.get(url, params=query_params, headers=headers)
        return response.text


def main():
    print("=" * 70)
    print("IMS Issue Crawler - Pure Requests (No Playwright)")
    print("=" * 70)

    crawler = IMSRequestsCrawler(IMS_URL)

    # Login
    if not crawler.login(USERNAME, PASSWORD):
        return

    # Test DWR call first
    print("\n" + "=" * 70)
    print("## Test 1: DWR API Call (ProductDwr)")
    print("=" * 70)
    dwr_result = crawler.call_dwr("ProductDwr", "findModules", ["129"])
    print(f"    DWR Response (first 200 chars):")
    print(f"    {dwr_result[:200]}...")

    # Search issues
    print("\n" + "=" * 70)
    print("## Test 2: Issue Search (Form Submit)")
    print("=" * 70)
    result = crawler.search_issues(
        keyword="oscboot",
        product_codes=OPENFRAME_PRODUCTS,
        page_size=20
    )

    if result.get('issues'):
        print(f"\n    Found {len(result['issues'])} issues")
        print(f"\n    {'No':<4} {'ID':<10} {'Product':<18} {'Subject':<45}")
        print("    " + "-" * 80)

        for i, issue in enumerate(result['issues'][:10], 1):
            subject = issue['subject'][:42] + '...' if len(issue['subject']) > 45 else issue['subject']
            print(f"    {i:<4} {issue['issue_id']:<10} {issue['product']:<18} {subject}")

        # Get detail for first issue
        if result['issues']:
            print("\n" + "=" * 70)
            print("## Test 3: Issue Detail (Form POST)")
            print("=" * 70)

            first_issue = result['issues'][0]
            detail = crawler.get_issue_detail(first_issue['issue_id'])

            print(f"\n    Issue ID: {detail['issue_id']}")
            print(f"    Subject: {detail['subject'][:60]}...")
            print(f"    Status: {detail['status']}")
            print(f"    Category: {detail['category']}")
            print(f"    Reporter: {detail['reporter']}")
            print(f"    Contents: {detail['contents'][:200]}..." if detail['contents'] else "    Contents: (empty)")
            print(f"    Attachments: {len(detail['attachments'])}")

    else:
        print("\n    No issues found or error occurred")

    # Summary
    print("\n" + "=" * 70)
    print("## Summary")
    print("=" * 70)
    print("""
    Playwright 없이 requests만으로:

    [OK] 로그인 - POST /tody/auth/login.do
    [OK] DWR 호출 - GET /tody/dwr/exec/{Service}.{method}
    [??] 이슈 검색 - GET /tody/ims/issue/issueSearchList.do (결과 확인 필요)
    [??] 이슈 상세 - POST /tody/ims/issue/issueView.do (결과 확인 필요)

    주의: IMS가 JavaScript로 동적 렌더링하는 경우 HTML 파싱이 안될 수 있음
    """)


if __name__ == "__main__":
    main()
