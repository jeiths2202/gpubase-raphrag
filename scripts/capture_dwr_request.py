#!/usr/bin/env python3
"""
Capture actual DWR request format from browser.
"""
import asyncio
import sys
import io
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.async_api import async_playwright

IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


async def capture_dwr():
    print("=" * 70)
    print("Capturing DWR Request Format")
    print("=" * 70)

    captured_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Capture all requests
        async def on_request(request):
            if '/dwr/' in request.url and 'call' in request.url:
                captured_requests.append({
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'post_data': request.post_data
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

        # Navigate to search page
        print("[2] Navigating to search page...")
        await page.goto(f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Trigger DWR call
        print("[3] Triggering DWR call...")
        await page.evaluate('''() => {
            return new Promise((resolve) => {
                ProductDwr.findVersions('129', function(data) {
                    resolve(data);
                });
            });
        }''')

        await asyncio.sleep(2)

        # Get cookies
        cookies = await context.cookies()

        await browser.close()

    print("\n" + "=" * 70)
    print("## Captured DWR Request")
    print("=" * 70)

    if captured_requests:
        req = captured_requests[0]
        print(f"\nURL: {req['url']}")
        print(f"\nMethod: {req['method']}")
        print("\nHeaders:")
        for k, v in req['headers'].items():
            print(f"    {k}: {v}")
        print("\nPOST Body:")
        if req['post_data']:
            for line in req['post_data'].split('\n'):
                print(f"    {line}")

        print("\n" + "=" * 70)
        print("## Cookies")
        print("=" * 70)
        for cookie in cookies:
            if 'ims.tmaxsoft.com' in cookie.get('domain', ''):
                print(f"    {cookie['name']}: {cookie['value'][:50]}...")

        print("\n" + "=" * 70)
        print("## Key Findings")
        print("=" * 70)

        # Extract script session id
        if req['post_data']:
            import re
            session_match = re.search(r'scriptSessionId=([^\n]+)', req['post_data'])
            http_session = re.search(r'httpSessionId=([^\n]+)', req['post_data'])

            if session_match:
                print(f"\n  scriptSessionId: {session_match.group(1)}")
            if http_session:
                print(f"  httpSessionId: {http_session.group(1)}")

    else:
        print("\nNo DWR requests captured!")


if __name__ == "__main__":
    asyncio.run(capture_dwr())
