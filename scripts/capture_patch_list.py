#!/usr/bin/env python3
"""
Patch List API Discovery Script

This script attempts to discover the Patch List API endpoint by:
1. Logging into IMS
2. Trying common URL patterns for patch list
3. Capturing the response

Based on the popupPatchList() function call pattern:
popupPatchList('2023002899','00840', '138', 'GBSC 일본 손보재팬', '(주)티맥스소프트')

Parameters:
1. '2023002899' - Project code
2. '00840' - Site code
3. '138' - Product code (OpenFrame OSC)
4. 'GBSC 일본 손보재팬' - Project/Site name
5. '(주)티맥스소프트' - Company name
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

IMS_BASE_URL = "https://ims.tmaxsoft.com"
IMS_USERNAME = os.getenv("IMS_USERNAME", "")
IMS_PASSWORD = os.getenv("IMS_PASSWORD", "")

# Potential Patch List API endpoints to try
PATCH_LIST_ENDPOINTS = [
    "/tody/ims/patch/patchList.do",
    "/tody/ims/patch/patchSearchList.do",
    "/tody/ims/patch/findPatchList.do",
    "/tody/ims/patch/patchInstallList.do",
    "/tody/ims/issue/findPatchIssues.do",
]


def login_to_ims(session: requests.Session) -> bool:
    """Login to IMS and return success status."""
    login_url = f"{IMS_BASE_URL}/tody/auth/login.do"

    login_data = {
        "userId": IMS_USERNAME,
        "userPasswd": IMS_PASSWORD,
        "menuCode": "main"
    }

    try:
        response = session.post(login_url, data=login_data, allow_redirects=True)

        # Check if login was successful by looking for user info in the response
        if "logout" in response.text.lower() or "로그아웃" in response.text:
            print("✓ Login successful")
            return True
        else:
            print("✗ Login failed")
            return False
    except Exception as e:
        print(f"✗ Login error: {e}")
        return False


def try_patch_list_api(session: requests.Session, endpoint: str, params: dict) -> dict:
    """Try a patch list API endpoint and return the response."""
    url = f"{IMS_BASE_URL}{endpoint}"

    try:
        # Try GET first
        response = session.get(url, params=params, timeout=30)

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')

            if 'json' in content_type:
                return {
                    "endpoint": endpoint,
                    "method": "GET",
                    "status": response.status_code,
                    "content_type": content_type,
                    "data": response.json(),
                    "success": True
                }
            elif 'html' in content_type:
                # Parse HTML for table data
                soup = BeautifulSoup(response.text, 'html.parser')
                tables = soup.find_all('table')

                return {
                    "endpoint": endpoint,
                    "method": "GET",
                    "status": response.status_code,
                    "content_type": content_type,
                    "tables_found": len(tables),
                    "html_preview": response.text[:500],
                    "success": True
                }
            else:
                return {
                    "endpoint": endpoint,
                    "method": "GET",
                    "status": response.status_code,
                    "content_type": content_type,
                    "preview": response.text[:200],
                    "success": True
                }
        else:
            return {
                "endpoint": endpoint,
                "method": "GET",
                "status": response.status_code,
                "success": False
            }

    except Exception as e:
        return {
            "endpoint": endpoint,
            "error": str(e),
            "success": False
        }


def main():
    """Main discovery function."""
    if not IMS_USERNAME or not IMS_PASSWORD:
        print("Error: IMS_USERNAME and IMS_PASSWORD environment variables are required")
        print("Set them in .env file or as environment variables")
        return

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # Login first
    if not login_to_ims(session):
        return

    # Sample parameters based on the popupPatchList() function
    test_params = {
        "projectCode": "2023002899",
        "siteCode": "00840",
        "productCode": "138",
        "projectName": "GBSC 일본 손보재팬",
        "companyName": "(주)티맥스소프트"
    }

    print("\n" + "="*60)
    print("Testing Patch List API Endpoints")
    print("="*60)

    results = []

    for endpoint in PATCH_LIST_ENDPOINTS:
        print(f"\nTrying: {endpoint}")
        result = try_patch_list_api(session, endpoint, test_params)
        results.append(result)

        if result.get("success"):
            print(f"  ✓ Status: {result.get('status')}")
            print(f"  Content-Type: {result.get('content_type', 'N/A')}")
            if result.get('tables_found'):
                print(f"  Tables found: {result.get('tables_found')}")
        else:
            print(f"  ✗ Status: {result.get('status', 'Error')}")
            if result.get('error'):
                print(f"  Error: {result.get('error')}")

    # Save results
    output_file = "patch_list_api_discovery.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n\nResults saved to: {output_file}")

    # Show successful endpoints
    successful = [r for r in results if r.get('success')]
    if successful:
        print("\n" + "="*60)
        print("Successful endpoints:")
        for r in successful:
            print(f"  - {r['endpoint']} ({r.get('status')})")


if __name__ == "__main__":
    main()
