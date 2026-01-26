#!/usr/bin/env python3
"""
IMS DWR GET API Call Test

IMS uses GET-based DWR endpoint: /tody/dwr/exec/{Service}.{method}
"""
import sys
import io
import re
import time
import random
import xml.etree.ElementTree as ET
import requests
from urllib.parse import urlencode

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

IMS_URL = "https://ims.tmaxsoft.com"
USERNAME = "yijae.shin"
PASSWORD = "12qwaszx"


class IMSDwrClient:
    """Client for IMS DWR GET-based API calls."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.call_id = 0

    def login(self, username: str, password: str) -> bool:
        """Login to IMS."""
        print(f"[1] Logging in as {username}...")

        login_url = f"{self.base_url}/tody/auth/login.do"
        self.session.get(login_url)

        login_data = {"id": username, "password": password}
        response = self.session.post(login_url, data=login_data, allow_redirects=True)

        if "/login" in response.url or "/auth/login" in response.url:
            print("[ERROR] Login failed")
            return False

        print(f"[OK] Login successful")
        print(f"    JSESSIONID: {self.session.cookies.get('JSESSIONID', 'N/A')[:40]}...")
        return True

    def call_dwr(self, service_name: str, method_name: str, params: list = None) -> dict:
        """
        Call DWR service using GET method.

        IMS DWR Format:
        GET /tody/dwr/exec/{Service}.{method}?callCount=1&c0-scriptName={Service}&c0-methodName={method}&c0-id={id}&c0-param0=string:{value}&xml=true
        """
        self.call_id += 1
        call_id = f"{random.randint(1000, 9999)}_{int(time.time() * 1000)}"

        # Build query parameters
        query_params = {
            'callCount': '1',
            'c0-scriptName': service_name,
            'c0-methodName': method_name,
            'c0-id': call_id,
            'xml': 'true'
        }

        # Add parameters
        if params:
            for i, param in enumerate(params):
                if param is None:
                    query_params[f'c0-param{i}'] = 'null:null'
                elif isinstance(param, str):
                    query_params[f'c0-param{i}'] = f'string:{param}'
                elif isinstance(param, int):
                    query_params[f'c0-param{i}'] = f'number:{param}'
                elif isinstance(param, bool):
                    query_params[f'c0-param{i}'] = f'boolean:{str(param).lower()}'
                else:
                    query_params[f'c0-param{i}'] = f'string:{str(param)}'

        # Build URL
        url = f"{self.base_url}/tody/dwr/exec/{service_name}.{method_name}"

        # Set referer header (important for DWR)
        headers = {
            'Referer': f'{self.base_url}/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search'
        }

        # Make request
        response = self.session.get(url, params=query_params, headers=headers)

        # Parse response
        return self._parse_response(response.text, response.status_code)

    def _parse_response(self, text: str, status_code: int) -> dict:
        """Parse DWR XML/JavaScript response."""
        if status_code != 200:
            return {'error': f'HTTP {status_code}', 'raw': text[:500]}

        # Check if XML response
        if text.strip().startswith('<?xml') or text.strip().startswith('<'):
            return self._parse_xml_response(text)

        # JavaScript response
        if 'dwr.engine' in text:
            return self._parse_js_response(text)

        return {'raw': text[:1000]}

    def _parse_xml_response(self, text: str) -> dict:
        """Parse XML DWR response."""
        try:
            root = ET.fromstring(text)
            result = {'success': True, 'data': [], 'xml': text[:500]}

            # Find all reply elements
            for reply in root.findall('.//reply'):
                data = self._xml_to_dict(reply)
                result['data'].append(data)

            return result
        except ET.ParseError as e:
            return {'error': f'XML parse error: {e}', 'raw': text[:500]}

    def _xml_to_dict(self, element) -> dict:
        """Convert XML element to dictionary."""
        result = {}
        for child in element:
            if len(child) > 0:
                result[child.tag] = self._xml_to_dict(child)
            else:
                result[child.tag] = child.text
        return result

    def _parse_js_response(self, text: str) -> dict:
        """Parse JavaScript DWR response."""
        match = re.search(r'dwr\.engine\._remoteHandleCallback\([^,]+,[^,]+,(.+)\);', text)
        if match:
            return {'success': True, 'data': match.group(1)[:500]}

        if 'Exception' in text or 'Error' in text:
            return {'error': text[:500]}

        return {'raw': text[:500]}


def main():
    print("=" * 70)
    print("IMS DWR GET-based API Test")
    print("=" * 70)

    client = IMSDwrClient(IMS_URL)

    if not client.login(USERNAME, PASSWORD):
        return

    print("\n" + "=" * 70)
    print("## DWR API Calls (GET method)")
    print("=" * 70)

    # Test 1: ProductDwr.findVersions
    print("\n### Test 1: ProductDwr.findVersions('129')")
    result = client.call_dwr("ProductDwr", "findVersions", ["129"])
    print(f"    Result: {result}")

    # Test 2: ProductDwr.findModules
    print("\n### Test 2: ProductDwr.findModules('129')")
    result = client.call_dwr("ProductDwr", "findModules", ["129"])
    print(f"    Result: {result}")

    # Test 3: IssueCategoryDwr.findCategories
    print("\n### Test 3: IssueCategoryDwr.findCategories()")
    result = client.call_dwr("IssueCategoryDwr", "findCategories", [])
    print(f"    Result: {result}")

    # Test 4: UserDwr.findUsersByName
    print("\n### Test 4: UserDwr.findUsersByName('shin')")
    result = client.call_dwr("UserDwr", "findUsersByName", ["shin"])
    print(f"    Result: {result}")

    # Show final format
    print("\n" + "=" * 70)
    print("## Confirmed API Format")
    print("=" * 70)
    print(f"""
IMS DWR uses GET-based API calls:

URL Format:
  GET {IMS_URL}/tody/dwr/exec/{{ServiceName}}.{{methodName}}

Query Parameters:
  - callCount=1
  - c0-scriptName={{ServiceName}}
  - c0-methodName={{methodName}}
  - c0-id={{unique_id}}
  - c0-param0=string:{{value}}
  - xml=true

Required Headers:
  - Cookie: JSESSIONID={{session_id}}
  - Referer: {IMS_URL}/tody/ims/...

Example:
  GET {IMS_URL}/tody/dwr/exec/ProductDwr.findVersions?callCount=1&c0-scriptName=ProductDwr&c0-methodName=findVersions&c0-id=1234&c0-param0=string:129&xml=true
""")


if __name__ == "__main__":
    main()
