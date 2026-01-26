#!/usr/bin/env python3
"""
IMS DWR (Direct Web Remoting) Direct Call Test

This script tests direct DWR calls without browser automation.
DWR uses a specific HTTP POST format to invoke server-side Java methods.
"""
import asyncio
import sys
import re
import json
import io
from pathlib import Path

# Fix Windows console encoding for Korean
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.async_api import async_playwright

# IMS Credentials
IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


async def test_dwr_calls():
    """Test DWR direct calls."""
    print("=" * 70)
    print("IMS DWR Direct Call Test")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Login first to get session
        print("\n[1] Logging in to get session...")
        await page.goto(f"{IMS_URL}/tody/auth/login.do")
        await page.wait_for_load_state("networkidle")
        await page.fill('input[name="id"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('input[type="image"]')
        await page.wait_for_load_state("networkidle")

        if "/login" in page.url or "/auth/login" in page.url:
            print("[ERROR] Login failed")
            await browser.close()
            return

        print("[OK] Login successful")

        # Get cookies for session
        cookies = await context.cookies()
        session_cookie = None
        for cookie in cookies:
            if cookie['name'] == 'JSESSIONID':
                session_cookie = cookie['value']
                print(f"[OK] Session ID: {session_cookie[:20]}...")
                break

        # Navigate to a page with DWR to initialize it
        await page.goto(f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        print("\n" + "=" * 70)
        print("## Testing DWR Calls")
        print("=" * 70)

        # Test 1: ProductDwr.findVersions - Get versions for a product
        print("\n### Test 1: ProductDwr.findVersions(productCode='129')")
        print("    (OpenFrame Base versions)")

        result1 = await page.evaluate('''() => {
            return new Promise((resolve, reject) => {
                if (typeof ProductDwr === 'undefined') {
                    resolve({error: 'ProductDwr not defined'});
                    return;
                }

                ProductDwr.findVersions('129', function(data) {
                    resolve({success: true, data: data});
                });

                // Timeout after 5 seconds
                setTimeout(() => resolve({error: 'timeout'}), 5000);
            });
        }''')

        if result1.get('success'):
            print(f"    [OK] Found {len(result1.get('data', []))} versions")
            for v in result1.get('data', [])[:5]:
                print(f"        - {v}")
        else:
            print(f"    [ERROR] {result1.get('error')}")

        # Test 2: ProductDwr.findModules - Get modules for a product
        print("\n### Test 2: ProductDwr.findModules(productCode='129')")
        print("    (OpenFrame Base modules)")

        result2 = await page.evaluate('''() => {
            return new Promise((resolve, reject) => {
                if (typeof ProductDwr === 'undefined') {
                    resolve({error: 'ProductDwr not defined'});
                    return;
                }

                ProductDwr.findModules('129', function(data) {
                    resolve({success: true, data: data});
                });

                setTimeout(() => resolve({error: 'timeout'}), 5000);
            });
        }''')

        if result2.get('success'):
            print(f"    [OK] Found {len(result2.get('data', []))} modules")
            for m in result2.get('data', [])[:10]:
                if isinstance(m, dict):
                    print(f"        - {m.get('moduleName', m.get('name', m))}")
                else:
                    print(f"        - {m}")
        else:
            print(f"    [ERROR] {result2.get('error')}")

        # Test 3: UserDwr.findUsersByName - Search users
        print("\n### Test 3: UserDwr.findUsersByName(searchText='shin')")

        result3 = await page.evaluate('''() => {
            return new Promise((resolve, reject) => {
                if (typeof UserDwr === 'undefined') {
                    resolve({error: 'UserDwr not defined'});
                    return;
                }

                UserDwr.findUsersByName('shin', function(data) {
                    resolve({success: true, data: data});
                });

                setTimeout(() => resolve({error: 'timeout'}), 5000);
            });
        }''')

        if result3.get('success'):
            users = result3.get('data', [])
            print(f"    [OK] Found {len(users)} users")
            for u in users[:5]:
                if isinstance(u, dict):
                    print(f"        - {u.get('userName', u.get('name', u))} ({u.get('userId', u.get('id', ''))})")
                else:
                    print(f"        - {u}")
        else:
            print(f"    [ERROR] {result3.get('error')}")

        # Test 4: IssueCategoryDwr.findCategories - Get all categories
        print("\n### Test 4: IssueCategoryDwr.findCategories()")

        result4 = await page.evaluate('''() => {
            return new Promise((resolve, reject) => {
                if (typeof IssueCategoryDwr === 'undefined') {
                    resolve({error: 'IssueCategoryDwr not defined'});
                    return;
                }

                IssueCategoryDwr.findCategories(function(data) {
                    resolve({success: true, data: data});
                });

                setTimeout(() => resolve({error: 'timeout'}), 5000);
            });
        }''')

        if result4.get('success'):
            categories = result4.get('data', [])
            print(f"    [OK] Found {len(categories)} categories")
            for c in categories[:10]:
                if isinstance(c, dict):
                    print(f"        - {c.get('categoryName', c.get('name', c))} (code: {c.get('categoryCode', c.get('code', ''))})")
                else:
                    print(f"        - {c}")
        else:
            print(f"    [ERROR] {result4.get('error')}")

        # Test 5: Check what other DWR interfaces might exist
        print("\n### Test 5: Scanning for additional DWR interfaces...")

        dwr_scan = await page.evaluate('''() => {
            const dwrInterfaces = [];
            const possibleNames = [
                'IssueDwr', 'IssueSearchDwr', 'IssueListDwr',
                'ProjectDwr', 'CustomerDwr', 'AttachDwr',
                'CommentDwr', 'BoardDwr', 'NoticeDwr',
                'ReportDwr', 'FilterDwr', 'SearchDwr',
                'CommonDwr', 'CodeDwr', 'ManagerDwr'
            ];

            for (const name of possibleNames) {
                if (window[name] && typeof window[name] === 'object') {
                    const methods = [];
                    for (const key in window[name]) {
                        if (typeof window[name][key] === 'function') {
                            methods.push(key);
                        }
                    }
                    if (methods.length > 0) {
                        dwrInterfaces.push({name, methods});
                    }
                }
            }

            return dwrInterfaces;
        }''')

        if dwr_scan:
            for iface in dwr_scan:
                print(f"\n    Found: {iface['name']}")
                for method in iface['methods']:
                    print(f"        - {method}()")
        else:
            print("    No additional DWR interfaces found")

        # Test 6: Try raw DWR HTTP call format
        print("\n" + "=" * 70)
        print("## Testing Raw DWR HTTP Protocol")
        print("=" * 70)

        # Capture DWR call format
        print("\n### Capturing DWR request format...")

        dwr_requests = []

        def capture_request(request):
            if '/dwr/' in request.url and request.method == 'POST':
                dwr_requests.append({
                    'url': request.url,
                    'method': request.method,
                    'post_data': request.post_data,
                    'headers': dict(request.headers)
                })

        page.on('request', capture_request)

        # Trigger a DWR call
        await page.evaluate('''() => {
            return new Promise((resolve) => {
                ProductDwr.findVersions('129', function(data) {
                    resolve(data);
                });
            });
        }''')

        await asyncio.sleep(1)

        if dwr_requests:
            print("\n    Captured DWR Request:")
            req = dwr_requests[0]
            print(f"    URL: {req['url']}")
            print(f"    Method: {req['method']}")
            print(f"    Content-Type: {req['headers'].get('content-type', 'N/A')}")
            print(f"\n    POST Body:")
            if req['post_data']:
                for line in req['post_data'].split('\n')[:15]:
                    print(f"        {line}")

        await browser.close()

        # Summary
        print("\n" + "=" * 70)
        print("## DWR Call Summary")
        print("=" * 70)
        print("""
DWR (Direct Web Remoting) allows calling Java methods from JavaScript.

Request Format:
  POST /tody/dwr/call/plaincall/{ServiceName}.{methodName}.dwr
  Content-Type: text/plain

Request Body Format:
  callCount=1
  windowName=
  c0-scriptName={ServiceName}
  c0-methodName={methodName}
  c0-id=0
  c0-param0=string:{value}
  batchId={incrementing_id}
  instanceId=0
  page=/tody/ims/issue/issueSearchList.do
  scriptSessionId={session_id}

Response Format (JavaScript):
  //#DWR-INSERT
  //#DWR-REPLY
  dwr.engine._remoteHandleCallback('0','0',[{...data...}]);

Python requests equivalent:
  import requests
  session = requests.Session()
  # Login first...
  response = session.post(
      'https://ims.tmaxsoft.com/tody/dwr/call/plaincall/ProductDwr.findVersions.dwr',
      data='callCount=1\\nc0-scriptName=ProductDwr\\nc0-methodName=findVersions\\nc0-param0=string:129',
      headers={'Content-Type': 'text/plain'}
  )
""")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_dwr_calls())
