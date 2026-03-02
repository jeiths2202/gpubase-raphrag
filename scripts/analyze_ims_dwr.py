#!/usr/bin/env python3
"""
IMS DWR (Direct Web Remoting) API Analyzer

This script analyzes DWR interfaces used by TmaxSoft IMS.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.async_api import async_playwright

# IMS Credentials
IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


async def analyze_dwr_and_ajax():
    """Analyze DWR interfaces and AJAX patterns."""
    print("=" * 70)
    print("IMS DWR & AJAX API Analyzer")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Login
        print("\n[1] Logging in...")
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

        # Navigate to search page
        await page.goto(f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Analyze DWR interfaces
        print("\n" + "=" * 70)
        print("## DWR (Direct Web Remoting) Interfaces")
        print("=" * 70)

        dwr_interfaces = await page.evaluate('''() => {
            const interfaces = {};

            // Check common DWR objects
            const dwrObjects = ['IssueCategoryDwr', 'ProductDwr', 'UserDwr', 'IssueDwr',
                               'ProjectDwr', 'CustomerDwr', 'AttachDwr', 'CommentDwr',
                               'BoardDwr', 'NoticeDwr', 'ReportDwr'];

            for (const name of dwrObjects) {
                if (window[name]) {
                    interfaces[name] = {
                        exists: true,
                        methods: []
                    };

                    // Extract method names
                    for (const key of Object.keys(window[name])) {
                        if (typeof window[name][key] === 'function') {
                            interfaces[name].methods.push(key);
                        }
                    }
                }
            }

            return interfaces;
        }''')

        for interface_name, info in dwr_interfaces.items():
            print(f"\n### {interface_name}")
            if info['methods']:
                for method in info['methods']:
                    print(f"    - {method}()")

        # Analyze global functions related to API calls
        print("\n" + "=" * 70)
        print("## Global JavaScript Functions (API-related)")
        print("=" * 70)

        api_functions = await page.evaluate('''() => {
            const funcs = [];
            const keywords = ['search', 'list', 'get', 'load', 'fetch', 'save', 'update',
                             'delete', 'insert', 'ajax', 'submit', 'pop', 'view', 'export',
                             'issue', 'product', 'customer', 'user', 'report'];

            for (const key in window) {
                if (typeof window[key] === 'function' && !key.startsWith('_')) {
                    const keyLower = key.toLowerCase();
                    if (keywords.some(kw => keyLower.includes(kw))) {
                        try {
                            const src = window[key].toString();
                            // Check if it makes AJAX/DWR calls
                            if (src.includes('Dwr.') || src.includes('ajax') ||
                                src.includes('$.post') || src.includes('$.get') ||
                                src.includes('.do') || src.includes('submit')) {
                                funcs.push({
                                    name: key,
                                    source: src.substring(0, 500),
                                    hasDwr: src.includes('Dwr.'),
                                    hasAjax: src.includes('ajax') || src.includes('$.post') || src.includes('$.get')
                                });
                            }
                        } catch (e) {}
                    }
                }
            }
            return funcs;
        }''')

        for func in sorted(api_functions, key=lambda x: x['name']):
            tags = []
            if func['hasDwr']:
                tags.append('DWR')
            if func['hasAjax']:
                tags.append('AJAX')
            print(f"\n  {func['name']}() [{', '.join(tags)}]")

        # Analyze form actions
        print("\n" + "=" * 70)
        print("## Form Actions (Endpoints)")
        print("=" * 70)

        forms = await page.evaluate('''() => {
            const forms = [];
            document.querySelectorAll('form').forEach(form => {
                if (form.action) {
                    forms.push({
                        name: form.name || form.id || '(unnamed)',
                        action: form.action,
                        method: form.method.toUpperCase()
                    });
                }
            });
            return forms;
        }''')

        for form in forms:
            action = form['action'].replace(IMS_URL, '')
            print(f"  {form['method']:4s} {action}")
            print(f"       (form: {form['name']})")

        # Navigate to issue register page to find more APIs
        print("\n" + "=" * 70)
        print("## Issue Registration Page APIs")
        print("=" * 70)

        await page.goto(f"{IMS_URL}/tody/ims/issue/issueRegister.do")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        register_apis = await page.evaluate('''() => {
            const apis = [];

            // Find DWR calls in the page
            const scripts = document.querySelectorAll('script');
            scripts.forEach(script => {
                const text = script.textContent || '';
                const dwrCalls = text.match(/(\w+Dwr\.\w+)/g);
                if (dwrCalls) {
                    dwrCalls.forEach(call => apis.push(call));
                }
            });

            // Check window functions
            const funcs = ['insertIssue', 'updateIssue', 'deleteIssue',
                          'getIssueInfo', 'saveIssue', 'submitIssue'];
            for (const fn of funcs) {
                if (typeof window[fn] === 'function') {
                    apis.push(`${fn}() exists`);
                }
            }

            return [...new Set(apis)];
        }''')

        for api in sorted(set(register_apis)):
            print(f"  - {api}")

        # Navigate to product list to understand master data APIs
        print("\n" + "=" * 70)
        print("## Product/Customer Master Data APIs")
        print("=" * 70)

        await page.goto(f"{IMS_URL}/tody/ims/common/product/productList.do")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        master_data = await page.evaluate('''() => {
            const result = {
                forms: [],
                scripts: [],
                links: []
            };

            // Forms
            document.querySelectorAll('form').forEach(form => {
                if (form.action) {
                    result.forms.push(form.action);
                }
            });

            // Links with .do
            document.querySelectorAll('a[href*=".do"]').forEach(a => {
                result.links.push(a.href);
            });

            // Script content for AJAX/DWR
            document.querySelectorAll('script').forEach(script => {
                const text = script.textContent || '';
                const matches = text.match(/['"](\/tody\/[^'"]+\.do)['"]/g);
                if (matches) {
                    matches.forEach(m => result.scripts.push(m.replace(/['"]/g, '')));
                }
            });

            return result;
        }''')

        all_endpoints = set()
        for form in master_data.get('forms', []):
            all_endpoints.add(form.replace(IMS_URL, ''))
        for link in master_data.get('links', []):
            all_endpoints.add(link.replace(IMS_URL, ''))
        for script in master_data.get('scripts', []):
            all_endpoints.add(script)

        for endpoint in sorted(all_endpoints):
            if endpoint and '/tody/' in endpoint:
                print(f"  {endpoint}")

        await browser.close()

        # Print summary for admin request
        print("\n" + "=" * 70)
        print("## SUMMARY: APIs to Request from Administrator")
        print("=" * 70)
        print("""
TmaxSoft IMS uses a combination of:
1. DWR (Direct Web Remoting) - Server-side Java methods exposed to JavaScript
2. Traditional Form submissions (.do endpoints)
3. AJAX calls for dynamic data loading

Key API Categories to request documentation for:

1. **Issue Management APIs**
   - Issue Search/List (issueSearchList.do)
   - Issue View/Detail (issueView.do)
   - Issue Create (issueRegister.do, issueInsert.do)
   - Issue Update (issueUpdate.do)
   - Issue Delete (issueDelete.do)

2. **DWR Services (Java RPC)**
   - IssueCategoryDwr - Issue category/type management
   - ProductDwr - Product master data
   - UserDwr - User lookup/search
   - ProjectDwr - Project management
   - CustomerDwr - Customer master data

3. **Master Data APIs**
   - Product List (productList.do)
   - Customer List (customerList.do)
   - User List (popupUserList.do)
   - Project List (popupProjectList.do)

4. **Report/Export APIs**
   - Excel Export (ajaxExcelDown)
   - Report Generation (goIssueRegistReport, goIssueCmpReport)

5. **File/Attachment APIs**
   - File Upload
   - File Download
   - Attachment management

6. **Filter/Search APIs**
   - filterIssuesAjax.do - Saved filter execution
   - Issue search with various parameters
""")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(analyze_dwr_and_ajax())
