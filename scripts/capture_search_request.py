#!/usr/bin/env python3
"""
Capture actual search request from browser to understand the exact format.
"""
import asyncio
import sys
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"

OPENFRAME_PRODUCTS = ['128', '520', '129', '123', '500', '137', '141', '126',
    '147', '145', '135', '143', '138', '134', '142', '510', '127', '124']


async def capture_search():
    print("=" * 70)
    print("Capturing Search Request Format")
    print("=" * 70)

    captured_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Capture requests
        def on_request(request):
            if 'issueSearchList.do' in request.url:
                captured_requests.append({
                    'url': request.url,
                    'method': request.method,
                    'post_data': request.post_data,
                    'headers': dict(request.headers)
                })

        page.on('request', on_request)

        # Login
        print("\n[1] Logging in...")
        await page.goto(f"{IMS_URL}/tody/auth/login.do")
        await page.wait_for_load_state("networkidle")
        await page.fill('input[name="id"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('input[type="image"]')
        await page.wait_for_load_state("networkidle")
        print("    Login successful")

        # Go to search page
        print("\n[2] Navigating to search page...")
        await page.goto(f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Select products
        print("\n[3] Selecting OpenFrame products...")
        product_select = await page.query_selector('#productCodes')
        if product_select:
            await product_select.select_option(value=OPENFRAME_PRODUCTS)
            print(f"    Selected {len(OPENFRAME_PRODUCTS)} products")

        # Enter keyword
        print("\n[4] Entering keyword: oscboot")
        keyword_input = await page.query_selector('#keyword')
        if keyword_input:
            await keyword_input.fill('oscboot')

        # Clear captured requests before search
        captured_requests.clear()

        # Execute search
        print("\n[5] Executing search and capturing request...")
        try:
            async with page.expect_navigation(timeout=30000):
                await page.evaluate('''() => {
                    if (typeof goReportSearch === 'function' && document.issueSearchForm) {
                        goReportSearch(document.issueSearchForm, '1');
                        return true;
                    }
                    return false;
                }''')
        except Exception as e:
            print(f"    Note: {e}")

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        # Get result count
        result_count = await page.evaluate('''() => {
            const rows = document.querySelectorAll('table.dataTable tr[onclick*="popBlankIssueView"]');
            return rows.length;
        }''')
        print(f"\n[6] Search results: {result_count} issues found")

        await browser.close()

    # Analyze captured requests
    print("\n" + "=" * 70)
    print("## Captured Search Request")
    print("=" * 70)

    if captured_requests:
        for i, req in enumerate(captured_requests):
            print(f"\n### Request {i+1}")
            print(f"URL: {req['url'][:100]}...")
            print(f"Method: {req['method']}")

            if req['method'] == 'GET':
                # Parse query string
                parsed = urlparse(req['url'])
                params = parse_qs(parsed.query)
                print("\nQuery Parameters:")
                for key, values in sorted(params.items()):
                    if len(values) == 1:
                        print(f"  {key}: {values[0][:50]}")
                    else:
                        print(f"  {key}: {values[:5]}{'...' if len(values) > 5 else ''}")

            elif req['method'] == 'POST' and req['post_data']:
                print("\nPOST Data:")
                # Parse form data
                params = parse_qs(req['post_data'])
                for key, values in sorted(params.items()):
                    if key == 'productCodes':
                        print(f"  {key}: [{len(values)} values]")
                    elif len(values) == 1:
                        val = values[0][:50] if len(values[0]) > 50 else values[0]
                        print(f"  {key}: {val}")
                    else:
                        print(f"  {key}: {values}")

        # Generate Python code
        print("\n" + "=" * 70)
        print("## Python requests code")
        print("=" * 70)

        if captured_requests:
            req = captured_requests[-1]  # Last request (the search)
            if req['method'] == 'GET':
                parsed = urlparse(req['url'])
                params = parse_qs(parsed.query)

                print("\n```python")
                print("import requests")
                print("")
                print("session = requests.Session()")
                print("# ... login first ...")
                print("")
                print("params = {")
                for key, values in sorted(params.items()):
                    if len(values) == 1:
                        print(f"    '{key}': '{values[0]}',")
                    else:
                        print(f"    '{key}': {values},")
                print("}")
                print("")
                print(f"response = session.get('{IMS_URL}/tody/ims/issue/issueSearchList.do', params=params)")
                print("```")

    else:
        print("\nNo search requests captured!")


if __name__ == "__main__":
    asyncio.run(capture_search())
