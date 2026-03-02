"""
IMS Related Issues - Find issue with actual related issues
"""

import requests
from bs4 import BeautifulSoup
import re
import json


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
    print(f"[OK] Login successful")
    return True


def fetch_related_issues_api(session: requests.Session, issue_id: str) -> list:
    """Fetch related issues from API endpoint."""
    base_url = "https://ims.tmaxsoft.com"
    api_url = f"{base_url}/tody/ims/issue/findRelationIssues.do"
    try:
        response = session.get(api_url, params={'issueId': issue_id}, timeout=30)
        if response.status_code == 200:
            try:
                return response.json()
            except:
                return []
    except:
        return []
    return []


def main():
    print("=" * 60)
    print("Finding issues with Related Issues")
    print("=" * 60)

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })

    if not login_to_ims(session, "yijae.shin", "12qwaszx"):
        print("Login failed.")
        return

    # Test several issues to find one with related issues
    test_issues = [
        "343803",  # Recent OpenFrame issue
        "267161",  # Another issue
        "175318",  # Original issue
        "300675",  # From patch list
        "344422",  # From patch list
        "335092",  # From patch list
    ]

    for issue_id in test_issues:
        related = fetch_related_issues_api(session, issue_id)
        print(f"Issue {issue_id}: {len(related)} related issues")
        if related:
            print(f"  Sample: {json.dumps(related[:2], indent=2, ensure_ascii=False)}")

            # Save full response
            with open(f"debug_related_api_{issue_id}.txt", "w", encoding="utf-8") as f:
                f.write(json.dumps(related, indent=2, ensure_ascii=False))
            print(f"  [OK] Saved to debug_related_api_{issue_id}.txt")


if __name__ == "__main__":
    main()
