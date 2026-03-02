#!/usr/bin/env python3
"""
Debug script to capture Patch List HTML structure.

Usage:
    python scripts/debug_patch_list.py

Requires IMS_USERNAME and IMS_PASSWORD in .env file.
"""

import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

load_dotenv()

IMS_BASE_URL = "https://ims.tmaxsoft.com"


def login_to_ims(session: requests.Session) -> bool:
    """Login to IMS."""
    login_url = f"{IMS_BASE_URL}/tody/auth/login.do"

    username = os.getenv("IMS_USERNAME", "")
    password = os.getenv("IMS_PASSWORD", "")

    if not username or not password:
        print("Error: IMS_USERNAME and IMS_PASSWORD required in .env")
        return False

    response = session.post(login_url, data={
        "userId": username,
        "userPasswd": password,
        "menuCode": "main"
    }, allow_redirects=True)

    if "logout" in response.text.lower() or "로그아웃" in response.text:
        print("✓ Login successful")
        return True
    print("✗ Login failed")
    return False


def fetch_patch_list(session: requests.Session):
    """Fetch Patch List page and analyze structure."""

    # Test URL from user
    url = f"{IMS_BASE_URL}/tody/ims/patch/patchList.do"
    params = {
        "projectCode": "2023003150",
        "siteCode": "00840",
        "productCode": "128",
        "projectName": "GBSC 일본 우오이치",
        "siteName": "(주)티맥스소프트"
    }

    print(f"\nFetching: {url}")
    print(f"Params: {params}")

    response = session.get(url, params=params, timeout=60)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

    # Save full HTML
    output_file = "debug_patch_list.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response.text)
    print(f"\n✓ Full HTML saved to: {output_file}")

    # Parse and analyze
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find tables
    tables = soup.find_all('table')
    print(f"\nFound {len(tables)} tables")

    # Look for Issue No patterns
    issue_patterns = soup.find_all(string=lambda s: s and 'Issue' in str(s))
    print(f"Found {len(issue_patterns)} elements containing 'Issue'")

    # Look for links that might contain issue IDs
    links = soup.find_all('a', href=True)
    issue_links = [a for a in links if 'issueView' in a.get('href', '')]
    print(f"Found {len(issue_links)} issueView links")

    if issue_links:
        print("\nSample issue links:")
        for link in issue_links[:5]:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            print(f"  - {text}: {href}")

    # Look for table with Issue No header
    for i, table in enumerate(tables):
        headers = table.find_all('th')
        header_texts = [th.get_text(strip=True) for th in headers]
        if any('Issue' in h for h in header_texts):
            print(f"\nTable {i} has Issue-related headers:")
            print(f"  Headers: {header_texts}")

            # Get rows
            rows = table.find_all('tr')
            print(f"  Rows: {len(rows)}")

            # Show first few data rows
            for row in rows[1:4]:  # Skip header, show 3 rows
                cells = row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True)[:30] for c in cells]
                print(f"  Row: {cell_texts}")


def main():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    if not login_to_ims(session):
        return

    fetch_patch_list(session)


if __name__ == "__main__":
    main()
