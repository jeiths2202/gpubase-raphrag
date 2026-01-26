#!/usr/bin/env python3
"""
IMS Issue Search Test

Test searching for issues with keyword 'oscboot' in OpenFrame products.
"""
import asyncio
import sys
import io
import json
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

# OpenFrame product codes
OPENFRAME_PRODUCTS = [
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
]


async def search_issues():
    print("=" * 70)
    print("IMS Issue Search Test")
    print("Keyword: oscboot")
    print("Products: OpenFrame series")
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

        if "/login" in page.url:
            print("[ERROR] Login failed")
            await browser.close()
            return

        print("[OK] Login successful")

        # Navigate to search page
        print("\n[2] Navigating to issue search page...")
        search_url = f"{IMS_URL}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search"
        await page.goto(search_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # First, check if there's an IssueDwr for searching
        print("\n[3] Checking for Issue DWR service...")
        dwr_check = await page.evaluate('''() => {
            const dwrServices = [];
            const names = ['IssueDwr', 'IssueSearchDwr', 'SearchDwr', 'ReportDwr'];
            for (const name of names) {
                if (window[name]) {
                    const methods = Object.keys(window[name]).filter(k => typeof window[name][k] === 'function');
                    dwrServices.push({name, methods});
                }
            }
            return dwrServices;
        }''')

        if dwr_check:
            print("    Found DWR services:")
            for svc in dwr_check:
                print(f"    - {svc['name']}: {svc['methods']}")
        else:
            print("    No Issue DWR service found (search uses form submission)")

        # Select OpenFrame products
        print("\n[4] Selecting OpenFrame products...")
        product_select = await page.query_selector('#productCodes')
        if product_select:
            try:
                await product_select.select_option(value=OPENFRAME_PRODUCTS)
                print(f"    Selected {len(OPENFRAME_PRODUCTS)} OpenFrame products")
            except Exception as e:
                print(f"    Product selection error: {e}")

        # Enter search keyword
        print("\n[5] Entering keyword: oscboot")
        keyword_input = await page.query_selector('#keyword')
        if keyword_input:
            await keyword_input.fill('oscboot')
            print("    Keyword entered")
        else:
            print("    [WARNING] Keyword input not found")

        # Execute search
        print("\n[6] Executing search...")
        try:
            async with page.expect_navigation(timeout=30000):
                await page.evaluate('''() => {
                    if (typeof goReportSearch === 'function' && document.issueSearchForm) {
                        goReportSearch(document.issueSearchForm, '1');
                        return true;
                    }
                    return false;
                }''')
            print("    Search submitted")
        except Exception as e:
            print(f"    Navigation: {e}")

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Extract results
        print("\n[7] Extracting search results...")

        # Get result count
        result_info = await page.evaluate('''() => {
            // Try to find total count
            const countEl = document.querySelector('.total') || document.querySelector('.listCnt');
            const countText = countEl ? countEl.textContent : '';

            // Count rows
            const rows = document.querySelectorAll('table.dataTable tbody tr, table.list tbody tr');

            return {
                countText: countText,
                rowCount: rows.length
            };
        }''')

        print(f"    Rows found: {result_info['rowCount']}")

        # Extract issue data
        issues = await page.evaluate('''() => {
            const issues = [];
            const rows = document.querySelectorAll('table.dataTable tr[onclick*="popBlankIssueView"]');

            for (let i = 0; i < Math.min(rows.length, 20); i++) {
                const row = rows[i];
                const cells = row.querySelectorAll('td');

                if (cells.length >= 7) {
                    const onclick = row.getAttribute('onclick') || '';
                    const idMatch = onclick.match(/popBlankIssueView\s*\(\s*['"](\d+)['"]/);

                    issues.push({
                        issueId: idMatch ? idMatch[1] : '',
                        issueNumber: cells[1]?.textContent?.trim() || '',
                        category: cells[2]?.textContent?.trim() || '',
                        product: cells[3]?.textContent?.trim() || '',
                        version: cells[4]?.textContent?.trim() || '',
                        module: cells[5]?.textContent?.trim() || '',
                        subject: cells[6]?.textContent?.trim().substring(0, 80) || ''
                    });
                }
            }

            return issues;
        }''')

        print(f"\n" + "=" * 70)
        print(f"## Search Results: {len(issues)} issues found")
        print("=" * 70)

        if issues:
            print(f"\n{'No':<4} {'Issue ID':<10} {'Product':<20} {'Subject':<50}")
            print("-" * 90)
            for i, issue in enumerate(issues[:15], 1):
                subject = issue['subject'][:47] + '...' if len(issue['subject']) > 50 else issue['subject']
                print(f"{i:<4} {issue['issueId']:<10} {issue['product']:<20} {subject}")

            # Show full details for first 3
            print(f"\n" + "=" * 70)
            print("## First 3 Issues Detail")
            print("=" * 70)
            for issue in issues[:3]:
                print(f"\n  Issue ID: {issue['issueId']}")
                print(f"  Number: {issue['issueNumber']}")
                print(f"  Category: {issue['category']}")
                print(f"  Product: {issue['product']}")
                print(f"  Version: {issue['version']}")
                print(f"  Module: {issue['module']}")
                print(f"  Subject: {issue['subject']}")
        else:
            print("\n  No issues found with keyword 'oscboot'")

            # Try to get page content for debugging
            page_text = await page.evaluate('() => document.body.innerText.substring(0, 500)')
            print(f"\n  Page preview: {page_text[:300]}...")

        await browser.close()

        return issues


if __name__ == "__main__":
    asyncio.run(search_issues())
