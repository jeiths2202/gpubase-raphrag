"""
IMS Related Issues - Detailed Analysis
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import sys
import io

# Fix console encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def login_to_ims(session: requests.Session, username: str, password: str) -> bool:
    """Login to IMS system."""
    base_url = "https://ims.tmaxsoft.com"
    login_url = f"{base_url}/tody/auth/login.do"
    session.get(login_url, timeout=30)
    response = session.post(
        login_url,
        data={'id': username, 'password': password},
        allow_redirects=True,
        timeout=30
    )
    if '/login' in response.url or '/auth/login' in response.url:
        return False
    print("[OK] Login successful")
    return True


def fetch_related_issues_api(session: requests.Session, issue_id: str) -> dict:
    """Fetch related issues from API endpoint."""
    base_url = "https://ims.tmaxsoft.com"
    api_url = f"{base_url}/tody/ims/issue/findRelationIssues.do"

    result = {
        "status": None,
        "content_type": None,
        "is_json": False,
        "data": None,
        "raw": None
    }

    try:
        response = session.get(api_url, params={'issueId': issue_id}, timeout=30)
        result["status"] = response.status_code
        result["content_type"] = response.headers.get('Content-Type', '')
        result["raw"] = response.text[:500]

        if response.status_code == 200:
            try:
                result["data"] = response.json()
                result["is_json"] = True
            except:
                result["is_json"] = False
    except Exception as e:
        result["error"] = str(e)

    return result


def fetch_issue_detail_and_analyze(session: requests.Session, issue_id: str) -> dict:
    """Fetch issue detail and analyze Related Issue section."""
    base_url = "https://ims.tmaxsoft.com"
    detail_url = f"{base_url}/tody/ims/issue/issueView.do"

    response = session.post(
        detail_url,
        data={'issueId': issue_id, 'menuCode': 'issue_list'},
        headers={'Referer': f"{base_url}/tody/ims/issue/issueSearchList.do"},
        timeout=60
    )

    html = response.text

    # Find Related Issue section HTML
    result = {
        "html_size": len(html),
        "related_section_found": False,
        "related_section_html": "",
        "relation_types": [],
        "js_api_calls": []
    }

    # Look for Related Issue div
    match = re.search(r'id=["\']RelationIssuesDiv["\'][^>]*>(.*?)</div>\s*<!--', html, re.DOTALL | re.I)
    if match:
        result["related_section_found"] = True
        result["related_section_html"] = match.group(1)[:1000]

    # Find relation search types (R, C, P)
    type_matches = re.findall(r'relationSearchType.*?value=["\'](\w+)["\']', html)
    result["relation_types"] = list(set(type_matches))

    # Find API calls
    api_matches = re.findall(r'url\s*=\s*["\']([^"\']*Relation[^"\']*)["\']', html)
    result["js_api_calls"] = list(set(api_matches))

    return html, result


def main():
    print("=" * 60)
    print("IMS Related Issues - Detailed Analysis")
    print("=" * 60)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })

    if not login_to_ims(session, "yijae.shin", "12qwaszx"):
        print("Login failed.")
        return

    # Test issues
    test_issues = ["267161", "343803", "175318"]

    for issue_id in test_issues:
        print(f"\n{'='*60}")
        print(f"Analyzing Issue: {issue_id}")
        print("=" * 60)

        # 1. Fetch and analyze issue detail page
        print("\n[1] Issue Detail Page Analysis:")
        html, detail_result = fetch_issue_detail_and_analyze(session, issue_id)
        print(f"  - HTML Size: {detail_result['html_size']} bytes")
        print(f"  - Related Section Found: {detail_result['related_section_found']}")
        print(f"  - Relation Types: {detail_result['relation_types']}")
        print(f"  - JS API Calls: {detail_result['js_api_calls']}")

        # Save HTML
        with open(f"debug_issue_{issue_id}.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  - Saved to debug_issue_{issue_id}.html")

        # 2. Test Related Issues API
        print("\n[2] Related Issues API (findRelationIssues.do):")
        api_result = fetch_related_issues_api(session, issue_id)
        print(f"  - Status: {api_result['status']}")
        print(f"  - Content-Type: {api_result['content_type']}")
        print(f"  - Is JSON: {api_result['is_json']}")

        if api_result['is_json'] and api_result['data']:
            data = api_result['data']
            if isinstance(data, list):
                print(f"  - Count: {len(data)}")
                if data:
                    print(f"  - Fields: {list(data[0].keys()) if data else []}")
                    # Save to file
                    with open(f"debug_related_api_{issue_id}.json", "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"  - Saved to debug_related_api_{issue_id}.json")
        else:
            print(f"  - Raw response (first 200 chars):")
            print(f"    {api_result.get('raw', '')[:200]}")


if __name__ == "__main__":
    main()
