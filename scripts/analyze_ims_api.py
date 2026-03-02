#!/usr/bin/env python3
"""
IMS API Structure Analyzer

This script logs into IMS and captures all network requests to understand
the API structure used by the frontend.
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.async_api import async_playwright, Request, Response

# IMS Credentials
IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


class IMSApiAnalyzer:
    """Analyze IMS API calls by monitoring network traffic."""

    def __init__(self):
        self.api_calls = []
        self.xhr_calls = []
        self.form_submissions = []
        self.static_resources = []

    def categorize_request(self, request: Request):
        """Categorize a network request."""
        url = request.url
        method = request.method
        resource_type = request.resource_type

        entry = {
            "url": url,
            "method": method,
            "resource_type": resource_type,
            "headers": dict(request.headers),
            "post_data": request.post_data if method == "POST" else None,
            "timestamp": datetime.now().isoformat()
        }

        # Categorize by type
        if resource_type in ["xhr", "fetch"]:
            self.xhr_calls.append(entry)
        elif resource_type == "document" and method == "POST":
            self.form_submissions.append(entry)
        elif ".do" in url or "/api/" in url or "/tody/" in url:
            self.api_calls.append(entry)
        elif resource_type in ["stylesheet", "script", "image", "font"]:
            self.static_resources.append(entry)
        else:
            self.api_calls.append(entry)

    async def on_response(self, response: Response):
        """Capture response data for API calls."""
        request = response.request
        url = request.url

        # Only capture API responses
        if request.resource_type in ["xhr", "fetch"] or ".do" in url:
            try:
                content_type = response.headers.get("content-type", "")
                body = None

                if "json" in content_type:
                    try:
                        body = await response.json()
                    except:
                        body = await response.text()
                elif "text" in content_type or "html" in content_type:
                    text = await response.text()
                    body = text[:500] + "..." if len(text) > 500 else text

                # Find matching request and add response
                for call in self.xhr_calls + self.api_calls:
                    if call["url"] == url:
                        call["response_status"] = response.status
                        call["response_headers"] = dict(response.headers)
                        call["response_body_preview"] = body
                        break
            except Exception as e:
                pass


async def analyze_ims_apis():
    """Main function to analyze IMS APIs."""
    print("=" * 70)
    print("IMS API Structure Analyzer")
    print("=" * 70)

    analyzer = IMSApiAnalyzer()

    async with async_playwright() as p:
        # Launch browser (visible for debugging)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Set up request/response listeners
        page.on("request", lambda req: analyzer.categorize_request(req))
        page.on("response", lambda res: asyncio.create_task(analyzer.on_response(res)))

        print(f"\n[1] Navigating to login page: {IMS_URL}/tody/auth/login.do")
        await page.goto(f"{IMS_URL}/tody/auth/login.do")
        await page.wait_for_load_state("networkidle")

        print("[2] Logging in...")
        await page.fill('input[name="id"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('input[type="image"]')
        await page.wait_for_load_state("networkidle")

        # Check if login successful
        current_url = page.url
        if "/login" in current_url or "/auth/login" in current_url:
            print("[ERROR] Login failed - still on login page")
            await browser.close()
            return

        print(f"[3] Login successful! Current URL: {current_url}")

        # Navigate to issue search page
        print("\n[4] Navigating to issue search page...")
        search_url = f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
        await page.goto(search_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Capture the page's JavaScript functions
        print("\n[5] Analyzing JavaScript functions...")
        js_functions = await page.evaluate('''() => {
            const functions = [];
            for (const key in window) {
                if (typeof window[key] === 'function' &&
                    !key.startsWith('_') &&
                    key.length > 2 &&
                    (key.includes('search') || key.includes('Search') ||
                     key.includes('issue') || key.includes('Issue') ||
                     key.includes('list') || key.includes('List') ||
                     key.includes('pop') || key.includes('go') ||
                     key.includes('fn') || key.includes('ajax') ||
                     key.includes('Api') || key.includes('api'))) {
                    try {
                        functions.push({
                            name: key,
                            source: window[key].toString().substring(0, 300)
                        });
                    } catch (e) {
                        functions.push({name: key, source: '[native code]'});
                    }
                }
            }
            return functions;
        }''')

        # Analyze forms on the page
        print("\n[6] Analyzing forms...")
        forms = await page.evaluate('''() => {
            const forms = [];
            document.querySelectorAll('form').forEach(form => {
                const fields = [];
                form.querySelectorAll('input, select, textarea').forEach(el => {
                    fields.push({
                        tag: el.tagName,
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        className: el.className || ''
                    });
                });
                forms.push({
                    name: form.name || '',
                    action: form.action || '',
                    method: form.method || '',
                    id: form.id || '',
                    fields: fields
                });
            });
            return forms;
        }''')

        # Try to trigger a search to capture API calls
        print("\n[7] Performing a search to capture API calls...")

        # Find and fill keyword input
        keyword_input = await page.query_selector('#keyword')
        if keyword_input:
            await keyword_input.fill("OpenFrame")

        # Click search button
        try:
            await page.evaluate('''() => {
                if (typeof goReportSearch === 'function' && document.issueSearchForm) {
                    goReportSearch(document.issueSearchForm, '1');
                    return true;
                }
                return false;
            }''')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"   Search execution note: {e}")

        # Click on first issue row to capture detail page APIs
        print("\n[8] Opening an issue detail page...")
        try:
            first_row = await page.query_selector('table.dataTable tr[onclick*="popBlankIssueView"]')
            if first_row:
                onclick = await first_row.get_attribute('onclick')
                print(f"   Found issue row onclick: {onclick}")

                # Extract issue ID and navigate
                import re
                match = re.search(r"popBlankIssueView\s*\(\s*['\"](\d+)['\"]", onclick)
                if match:
                    issue_id = match.group(1)
                    detail_url = f"{IMS_URL}/tody/ims/issue/issueView.do?issueId={issue_id}"

                    # Open in new page to capture all requests
                    detail_page = await context.new_page()
                    detail_page.on("request", lambda req: analyzer.categorize_request(req))
                    detail_page.on("response", lambda res: asyncio.create_task(analyzer.on_response(res)))

                    await detail_page.goto(detail_url)
                    await detail_page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

                    # Analyze detail page structure
                    detail_forms = await detail_page.evaluate('''() => {
                        const forms = [];
                        document.querySelectorAll('form').forEach(form => {
                            const fields = [];
                            form.querySelectorAll('input, select, textarea').forEach(el => {
                                fields.push({
                                    tag: el.tagName,
                                    type: el.type || '',
                                    name: el.name || '',
                                    id: el.id || '',
                                    value: el.value?.substring(0, 100) || ''
                                });
                            });
                            forms.push({
                                name: form.name || '',
                                action: form.action || '',
                                method: form.method || '',
                                fields: fields
                            });
                        });
                        return forms;
                    }''')

                    await detail_page.close()
        except Exception as e:
            print(f"   Detail page note: {e}")

        # Navigate to other menus to capture more APIs
        print("\n[9] Exploring other menu endpoints...")
        menu_urls = [
            "/tody/ims/issue/issueRegister.do",  # Issue registration
            "/tody/ims/common/product/productList.do",  # Product list
            "/tody/ims/common/customer/customerList.do",  # Customer list
        ]

        for menu_url in menu_urls:
            try:
                full_url = f"{IMS_URL}{menu_url}"
                print(f"   Trying: {menu_url}")
                await page.goto(full_url, timeout=10000)
                await page.wait_for_load_state("networkidle", timeout=5000)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"   -> Not accessible or error: {str(e)[:50]}")

        # Wait a moment to capture any remaining async calls
        await asyncio.sleep(2)

        # Close browser
        await browser.close()

        # Generate report
        print("\n" + "=" * 70)
        print("API ANALYSIS REPORT")
        print("=" * 70)

        # Group API calls by endpoint pattern
        endpoint_patterns = defaultdict(list)
        for call in analyzer.api_calls + analyzer.xhr_calls + analyzer.form_submissions:
            url = call["url"]
            # Extract endpoint pattern
            if "/tody/" in url:
                endpoint = url.split("?")[0]
                endpoint = endpoint.replace(IMS_URL, "")
                endpoint_patterns[endpoint].append(call)

        print("\n## Discovered Endpoints (grouped by pattern):\n")
        for endpoint, calls in sorted(endpoint_patterns.items()):
            methods = set(c["method"] for c in calls)
            print(f"  {', '.join(methods):6s} {endpoint}")

            # Show sample parameters
            for call in calls[:1]:
                if call.get("post_data"):
                    print(f"         POST data: {call['post_data'][:100]}...")
                if "?" in call["url"]:
                    params = call["url"].split("?")[1]
                    print(f"         Query params: {params[:100]}")

        print(f"\n## Summary:")
        print(f"  - API/Document endpoints: {len(analyzer.api_calls)}")
        print(f"  - XHR/Fetch calls: {len(analyzer.xhr_calls)}")
        print(f"  - Form submissions: {len(analyzer.form_submissions)}")
        print(f"  - Static resources: {len(analyzer.static_resources)}")

        print("\n## JavaScript Functions (search/issue related):")
        for func in js_functions[:20]:
            print(f"  - {func['name']}")

        print("\n## Forms on Search Page:")
        for form in forms:
            print(f"  Form: {form['name'] or form['id'] or '(unnamed)'}")
            print(f"    Action: {form['action']}")
            print(f"    Method: {form['method']}")
            print(f"    Fields: {len(form['fields'])} fields")
            for field in form['fields'][:10]:
                print(f"      - {field['name'] or field['id']}: {field['type']} ({field['tag']})")

        # Save full report to JSON
        report = {
            "analyzed_at": datetime.now().isoformat(),
            "ims_url": IMS_URL,
            "endpoints": dict(endpoint_patterns),
            "api_calls": analyzer.api_calls,
            "xhr_calls": analyzer.xhr_calls,
            "form_submissions": analyzer.form_submissions,
            "js_functions": js_functions,
            "forms": forms
        }

        report_path = project_root / "ims_api_analysis_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n[+] Full report saved to: {report_path}")

        return report


if __name__ == "__main__":
    # Windows asyncio fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(analyze_ims_apis())
