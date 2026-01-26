"""
IMS Related Issues Page Structure Analysis Script

Analyzes the structure of Related Issue section and Patch List popup
to understand how to extract related issue information.
"""

import requests
from bs4 import BeautifulSoup
import re
import json


def login_to_ims(session: requests.Session, username: str, password: str) -> bool:
    """Login to IMS system."""
    base_url = "https://ims.tmaxsoft.com"
    login_url = f"{base_url}/tody/auth/login.do"

    # Get login page first (for cookies)
    session.get(login_url, timeout=30)

    # Submit login
    response = session.post(
        login_url,
        data={'id': username, 'password': password},
        allow_redirects=True,
        timeout=30
    )

    # Check login success
    if '/login' in response.url or '/auth/login' in response.url:
        print("[ERROR] Login failed - redirected to login page")
        return False

    jsessionid = session.cookies.get('JSESSIONID', '')[:20]
    print(f"[OK] Login successful - Session: {jsessionid}...")
    return True


def fetch_issue_detail(session: requests.Session, issue_id: str) -> str:
    """Fetch issue detail page HTML."""
    base_url = "https://ims.tmaxsoft.com"
    detail_url = f"{base_url}/tody/ims/issue/issueView.do"

    response = session.post(
        detail_url,
        data={'issueId': issue_id, 'menuCode': 'issue_list'},
        headers={'Referer': f"{base_url}/tody/ims/issue/issueSearchList.do"},
        timeout=60
    )

    print(f"[OK] Fetched issue {issue_id} - {len(response.text)} bytes")
    return response.text


def analyze_related_issues_section(html: str) -> dict:
    """Analyze Related Issue section in the HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "found": False,
        "section_html": "",
        "related_issues": [],
        "api_endpoint": "",
        "js_functions": []
    }

    # 1. Find Related Issue section
    related_section = None
    for td in soup.find_all('td', class_='tableHeaderTitle'):
        if 'Related' in td.get_text() and 'Issue' in td.get_text():
            related_section = td.find_parent('tr')
            result["found"] = True
            break

    # 2. Look for JavaScript functions related to Related Issue
    scripts = soup.find_all('script')
    for script in scripts:
        script_text = script.get_text() if script.string else ""

        # Find related issue functions
        if 'Relation' in script_text or 'related' in script_text.lower():
            # Extract function names
            func_matches = re.findall(r'function\s+(\w*[Rr]elat\w*)\s*\(', script_text)
            result["js_functions"].extend(func_matches)

            # Extract API endpoints
            api_matches = re.findall(r'["\']([^"\']*[Rr]elat[^"\']*\.do[^"\']*)["\']', script_text)
            if api_matches:
                result["api_endpoint"] = api_matches[0]

    # 3. Find findRelationIssues API call pattern
    api_pattern = re.search(r'findRelationIssues\.do', html)
    if api_pattern:
        result["api_endpoint"] = "/tody/ims/issue/findRelationIssues.do"

    # 4. Extract related issue data from HTML
    # Look for links containing issueView
    issue_links = soup.find_all('a', href=re.compile(r'issueView.*issueId=\d+'))
    for link in issue_links:
        href = link.get('href', '')
        match = re.search(r'issueId=(\d+)', href)
        if match:
            issue_id = match.group(1)
            title = link.get_text(strip=True)
            result["related_issues"].append({
                "ims_id": issue_id,
                "title": title[:50] if title else ""
            })

    return result


def analyze_patch_list_popup(html: str) -> dict:
    """Analyze Patch List popup trigger in the HTML."""
    result = {
        "found": False,
        "popup_params": {},
        "popup_function": "",
        "api_endpoint": ""
    }

    # 1. Find popupPatchList function call
    # Pattern: popupPatchList('projectCode','siteCode', 'productCode', 'projectName', 'siteName')
    pattern = r"popupPatchList\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
    match = re.search(pattern, html)

    if match:
        result["found"] = True
        result["popup_params"] = {
            "projectCode": match.group(1),
            "siteCode": match.group(2),
            "productCode": match.group(3),
            "projectName": match.group(4),
            "siteName": match.group(5)
        }
        result["popup_function"] = match.group(0)
        result["api_endpoint"] = "/tody/ims/patch/patchList.do"

    # 2. Find Patch List button/link
    soup = BeautifulSoup(html, 'html.parser')
    patch_btn = soup.find('a', onclick=re.compile(r'popupPatchList'))
    if patch_btn:
        result["button_text"] = patch_btn.get_text(strip=True)
        result["button_html"] = str(patch_btn)[:200]

    return result


def fetch_related_issues_api(session: requests.Session, issue_id: str) -> list:
    """Fetch related issues from API endpoint."""
    base_url = "https://ims.tmaxsoft.com"
    api_url = f"{base_url}/tody/ims/issue/findRelationIssues.do"

    try:
        response = session.get(api_url, params={'issueId': issue_id}, timeout=30)
        print(f"[API] findRelationIssues response: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()
                print(f"[API] Found {len(data)} related issues from API")
                return data
            except:
                print(f"[API] Response is not JSON: {response.text[:200]}")
                return []
    except Exception as e:
        print(f"[API] Error: {e}")
        return []


def fetch_patch_list(session: requests.Session, params: dict) -> str:
    """Fetch Patch List popup content."""
    base_url = "https://ims.tmaxsoft.com"
    api_url = f"{base_url}/tody/ims/patch/patchList.do"

    try:
        response = session.get(api_url, params=params, timeout=60)
        print(f"[API] patchList response: {response.status_code}, {len(response.text)} bytes")
        return response.text
    except Exception as e:
        print(f"[API] Error: {e}")
        return ""


def analyze_patch_list_html(html: str) -> dict:
    """Parse Patch List HTML to extract issue IDs."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        "issue_ids": [],
        "table_structure": "",
        "total_patches": 0
    }

    # Find all issue IDs in the patch list
    # Method 1: Look for links with issueView
    links = soup.find_all('a', href=re.compile(r'issueView'))
    for link in links:
        href = link.get('href', '')
        match = re.search(r'issueId=(\d+)', href)
        if match:
            result["issue_ids"].append(match.group(1))

    # Method 2: Look for onclick with popBlankIssueView
    onclick_links = soup.find_all(onclick=re.compile(r'popBlankIssueView'))
    for link in onclick_links:
        onclick = link.get('onclick', '')
        match = re.search(r"popBlankIssueView\s*\(\s*'(\d+)'", onclick)
        if match:
            result["issue_ids"].append(match.group(1))

    # Method 3: Look for 6-digit numbers in table cells
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            for cell in cells:
                text = cell.get_text(strip=True)
                if text.isdigit() and len(text) == 6:
                    result["issue_ids"].append(text)

    # Deduplicate
    result["issue_ids"] = list(set(result["issue_ids"]))
    result["total_patches"] = len(result["issue_ids"])

    # Get table structure
    main_table = soup.find('table', class_=re.compile(r'list|grid|data', re.I))
    if main_table:
        headers = main_table.find_all('th')
        result["table_structure"] = [th.get_text(strip=True) for th in headers]

    return result


def main():
    print("=" * 60)
    print("IMS Related Issues Page Structure Analysis")
    print("=" * 60)

    # Setup session
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    })

    # 1. Login
    print("\n[Step 1] Login to IMS...")
    if not login_to_ims(session, "yijae.shin", "12qwaszx"):
        print("Login failed. Exiting.")
        return

    # 2. Fetch issue detail
    issue_id = "175318"
    print(f"\n[Step 2] Fetching issue {issue_id} detail page...")
    html = fetch_issue_detail(session, issue_id)

    # Save HTML for debugging
    with open("debug_issue_175318.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] Saved HTML to debug_issue_175318.html")

    # 3. Analyze Related Issues section
    print("\n[Step 3] Analyzing Related Issues section...")
    related_result = analyze_related_issues_section(html)
    print(f"  - Found Related Section: {related_result['found']}")
    print(f"  - API Endpoint: {related_result['api_endpoint']}")
    print(f"  - JS Functions: {related_result['js_functions']}")
    print(f"  - Related Issues in HTML: {len(related_result['related_issues'])}")

    # 4. Fetch Related Issues from API
    print("\n[Step 4] Fetching Related Issues from API...")
    api_related = fetch_related_issues_api(session, issue_id)
    if api_related:
        print(f"  - API returned {len(api_related)} related issues:")
        for item in api_related[:5]:  # Show first 5
            print(f"    - {item.get('issueId', 'N/A')}: {item.get('subject', 'N/A')[:40]}")

    # 5. Analyze Patch List popup
    print("\n[Step 5] Analyzing Patch List popup...")
    patch_result = analyze_patch_list_popup(html)
    print(f"  - Found Patch List: {patch_result['found']}")
    if patch_result['found']:
        print(f"  - Popup Parameters: {json.dumps(patch_result['popup_params'], indent=4)}")
        print(f"  - API Endpoint: {patch_result['api_endpoint']}")

        # 6. Fetch Patch List content
        print("\n[Step 6] Fetching Patch List content...")
        patch_html = fetch_patch_list(session, patch_result['popup_params'])

        if patch_html:
            # Save for debugging
            with open("debug_patch_list_175318.html", "w", encoding="utf-8") as f:
                f.write(patch_html)
            print(f"[OK] Saved Patch List HTML to debug_patch_list_175318.html")

            # Analyze patch list
            patch_analysis = analyze_patch_list_html(patch_html)
            print(f"  - Total Issue IDs in Patch List: {patch_analysis['total_patches']}")
            print(f"  - Table Headers: {patch_analysis['table_structure']}")
            print(f"  - Issue IDs: {patch_analysis['issue_ids'][:10]}...")
    else:
        print("  - No Patch List found for this issue")

    # 7. Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"""
Issue: {issue_id}

1. Related Issues API:
   - Endpoint: /tody/ims/issue/findRelationIssues.do
   - Method: GET with ?issueId=XXXXX
   - Returns: JSON array of related issues

2. Patch List Popup:
   - Endpoint: /tody/ims/patch/patchList.do
   - Method: GET with project/site/product params
   - Returns: HTML page with patch table
   - Issue IDs can be extracted from table

3. Total Related Issues:
   - From Related API: {len(api_related)}
   - From Patch List: {patch_analysis['total_patches'] if patch_result['found'] else 'N/A'}
""")

    # Save full analysis result
    full_result = {
        "issue_id": issue_id,
        "related_section": related_result,
        "patch_list": patch_result,
        "api_related_issues": api_related,
        "patch_analysis": patch_analysis if patch_result['found'] else {}
    }

    with open("analysis_related_issues_175318.json", "w", encoding="utf-8") as f:
        json.dump(full_result, f, indent=2, ensure_ascii=False, default=str)
    print("[OK] Full analysis saved to analysis_related_issues_175318.json")


if __name__ == "__main__":
    main()
