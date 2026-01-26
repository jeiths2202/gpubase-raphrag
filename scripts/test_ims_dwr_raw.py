#!/usr/bin/env python3
"""
IMS DWR Raw HTTP Call Test

Direct HTTP calls to DWR without Playwright.
"""
import sys
import io
import re
import json
import requests
from urllib.parse import urljoin

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# IMS Credentials
IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


class IMSDwrClient:
    """Client for making DWR calls to IMS."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.script_session_id = None
        self.batch_id = 0

    def login(self, username: str, password: str) -> bool:
        """Login to IMS and get session."""
        print(f"[1] Logging in as {username}...")

        # Get login page first (to get any CSRF tokens)
        login_url = f"{self.base_url}/tody/auth/login.do"
        self.session.get(login_url)

        # Submit login form
        login_data = {
            "id": username,
            "password": password
        }

        response = self.session.post(login_url, data=login_data, allow_redirects=True)

        # Check if login was successful
        if "/login" in response.url or "/auth/login" in response.url:
            print("[ERROR] Login failed")
            return False

        print(f"[OK] Login successful")
        print(f"    Session ID: {self.session.cookies.get('JSESSIONID', 'N/A')[:30]}...")

        # Initialize DWR by loading a page
        self._init_dwr_session()

        return True

    def _init_dwr_session(self):
        """Initialize DWR session by loading engine.js."""
        # Load DWR engine to get script session ID
        engine_url = f"{self.base_url}/tody/dwr/engine.js"
        response = self.session.get(engine_url)

        # Extract default session token format
        # DWR uses a generated script session ID
        import time
        import random
        self.script_session_id = f"{int(time.time() * 1000)}_{random.randint(100, 999)}"
        print(f"    DWR Session: {self.script_session_id}")

    def call_dwr(self, service_name: str, method_name: str, params: list = None) -> dict:
        """
        Make a DWR call.

        Args:
            service_name: DWR service name (e.g., 'ProductDwr')
            method_name: Method to call (e.g., 'findVersions')
            params: List of parameters

        Returns:
            Parsed response data
        """
        self.batch_id += 1

        # Build DWR request body
        lines = [
            "callCount=1",
            "windowName=",
            f"c0-scriptName={service_name}",
            f"c0-methodName={method_name}",
            "c0-id=0",
        ]

        # Add parameters
        if params:
            for i, param in enumerate(params):
                if isinstance(param, str):
                    lines.append(f"c0-param{i}=string:{param}")
                elif isinstance(param, int):
                    lines.append(f"c0-param{i}=number:{param}")
                elif isinstance(param, bool):
                    lines.append(f"c0-param{i}=boolean:{str(param).lower()}")
                elif param is None:
                    lines.append(f"c0-param{i}=null:null")
                else:
                    lines.append(f"c0-param{i}=string:{str(param)}")

        lines.extend([
            f"batchId={self.batch_id}",
            "instanceId=0",
            "page=/tody/ims/issue/issueSearchList.do",
            f"scriptSessionId={self.script_session_id}"
        ])

        body = "\n".join(lines)

        # Make request
        url = f"{self.base_url}/tody/dwr/call/plaincall/{service_name}.{method_name}.dwr"

        headers = {
            "Content-Type": "text/plain",
            "Accept": "*/*",
        }

        response = self.session.post(url, data=body, headers=headers)

        # Parse DWR response
        return self._parse_dwr_response(response.text)

    def _parse_dwr_response(self, text: str) -> dict:
        """Parse DWR JavaScript response into Python object."""
        # DWR response format:
        # //#DWR-INSERT
        # //#DWR-REPLY
        # dwr.engine._remoteHandleCallback('0','0',[...data...]);

        # Find the callback data
        match = re.search(r'dwr\.engine\._remoteHandleCallback\([^,]+,[^,]+,(.+)\);', text)
        if not match:
            # Check for error
            if 'dwr.engine._remoteHandleException' in text:
                error_match = re.search(r'message:"([^"]+)"', text)
                return {"error": error_match.group(1) if error_match else "DWR Error"}
            return {"raw": text[:500]}

        data_str = match.group(1)

        # Convert JavaScript to Python
        try:
            # Handle DWR object references (s0, s1, etc.)
            # This is simplified - complex objects need more parsing
            data_str = self._convert_js_to_python(data_str)
            return {"data": data_str, "success": True}
        except Exception as e:
            return {"raw": data_str[:500], "parse_error": str(e)}

    def _convert_js_to_python(self, js_str: str) -> str:
        """Convert JavaScript literals to Python-parseable format."""
        # Replace JavaScript object notation with more details
        # This is a simplified version - full parsing would need more work

        # Find array of objects
        if js_str.startswith('['):
            # Extract items between [ and ]
            return js_str
        elif js_str.startswith('{'):
            return js_str
        else:
            return js_str


def main():
    print("=" * 70)
    print("IMS DWR Raw HTTP Call Test")
    print("=" * 70)

    client = IMSDwrClient(IMS_URL)

    if not client.login(USERNAME, PASSWORD):
        return

    print("\n" + "=" * 70)
    print("## DWR API Calls")
    print("=" * 70)

    # Test 1: Get product versions
    print("\n### Test 1: ProductDwr.findVersions('129')")
    result = client.call_dwr("ProductDwr", "findVersions", ["129"])
    if result.get('success'):
        print(f"    Response preview:")
        data = result.get('data', '')[:500]
        print(f"    {data}...")
    else:
        print(f"    Error: {result}")

    # Test 2: Get issue categories
    print("\n### Test 2: IssueCategoryDwr.findCategories()")
    result = client.call_dwr("IssueCategoryDwr", "findCategories", [])
    if result.get('success'):
        print(f"    Response preview:")
        data = result.get('data', '')[:500]
        print(f"    {data}...")
    else:
        print(f"    Error: {result}")

    # Test 3: Search users
    print("\n### Test 3: UserDwr.findUsersByName('shin')")
    result = client.call_dwr("UserDwr", "findUsersByName", ["shin"])
    if result.get('success'):
        print(f"    Response preview:")
        data = result.get('data', '')[:500]
        print(f"    {data}...")
    else:
        print(f"    Error: {result}")

    # Test 4: Get modules for a product
    print("\n### Test 4: ProductDwr.findModules('129')")
    result = client.call_dwr("ProductDwr", "findModules", ["129"])
    if result.get('success'):
        print(f"    Response preview:")
        data = result.get('data', '')[:500]
        print(f"    {data}...")
    else:
        print(f"    Error: {result}")

    # Show request format
    print("\n" + "=" * 70)
    print("## DWR Request Format Example")
    print("=" * 70)
    print("""
URL: POST https://ims.tmaxsoft.com/tody/dwr/call/plaincall/ProductDwr.findVersions.dwr

Headers:
    Content-Type: text/plain
    Cookie: JSESSIONID=xxx

Body:
    callCount=1
    windowName=
    c0-scriptName=ProductDwr
    c0-methodName=findVersions
    c0-id=0
    c0-param0=string:129
    batchId=1
    instanceId=0
    page=/tody/ims/issue/issueSearchList.do
    scriptSessionId=1234567890_123

Response (JavaScript format):
    //#DWR-INSERT
    //#DWR-REPLY
    dwr.engine._remoteHandleCallback('1','0',[{versionCode:"07300000",versionName:"7.3",...}]);
""")

    print("\n" + "=" * 70)
    print("## Available DWR Services Summary")
    print("=" * 70)
    print("""
1. ProductDwr
   - findVersions(productCode) -> 제품별 버전 목록
   - findModules(productCode) -> 제품별 모듈 목록
   - findSubVersions(productCode, mainVersion) -> 하위 버전
   - findSimpleModules(productCode) -> 간단 모듈 목록

2. IssueCategoryDwr
   - findCategories() -> 이슈 카테고리 목록
   - findCategory(categoryId) -> 카테고리 상세

3. UserDwr
   - findUsersByName(searchText) -> 사용자 검색
   - findUser(userId) -> 사용자 상세
   - findModuleManagers(p0, p1, p2) -> 모듈 담당자

Note: Full Issue CRUD APIs are likely via form submission, not DWR.
""")


if __name__ == "__main__":
    main()
