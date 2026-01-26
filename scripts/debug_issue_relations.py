#!/usr/bin/env python3
"""Debug IMS issue relations using requests."""

import re
import requests

IMS_BASE_URL = "https://ims.tmaxsoft.com"
TEST_ISSUE_ID = "267161"

def main():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # 1. Login - get page first for cookies
    print("1. Logging in...")
    login_url = f"{IMS_BASE_URL}/tody/auth/login.do"
    session.get(login_url, timeout=30)

    # Submit with correct field names (id, password)
    login_response = session.post(login_url, data={
        "id": "yijae.shin",
        "password": "12qwaszx"
    }, allow_redirects=True)

    if "logout" in login_response.text.lower() or "로그아웃" in login_response.text:
        print("   Login successful")
    else:
        print("   Login may have failed, continuing anyway...")

    # 2. Fetch issue detail page
    print(f"\n2. Fetching issue {TEST_ISSUE_ID} detail page...")
    detail_url = f"{IMS_BASE_URL}/tody/ims/issue/issueView.do"
    detail_response = session.post(detail_url, data={
        'issueId': TEST_ISSUE_ID,
        'menuCode': 'issue_search'
    })

    html = detail_response.text
    with open("debug_issue_343803.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Saved HTML ({len(html)} bytes)")

    # 3. Fetch Related Issue API
    print(f"\n3. Fetching Related Issue API for {TEST_ISSUE_ID}...")
    related_url = f"{IMS_BASE_URL}/tody/ims/issue/findRelationIssues.do?issueId={TEST_ISSUE_ID}"
    related_response = session.get(related_url)
    related_text = related_response.text

    with open("debug_related_api_343803.txt", "w", encoding="utf-8") as f:
        f.write(related_text)
    print(f"   Response length: {len(related_text)}")

    # Parse issue IDs from Related API
    related_ids = re.findall(r'"issueId"\s*:\s*"?(\d+)"?', related_text)
    related_ids = list(set(related_ids))
    print(f"   Related Issue IDs: {related_ids}")

    if TEST_ISSUE_ID in related_ids:
        print(f"   *** SELF-REFERENCE in Related API: {TEST_ISSUE_ID} ***")
    else:
        print(f"   No self-reference in Related API")

    # 4. Check Patch List
    print(f"\n4. Checking Patch List...")
    patch_match = re.search(
        r"popupPatchList\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)",
        html
    )

    if patch_match:
        params = {
            'projectCode': patch_match.group(1),
            'siteCode': patch_match.group(2),
            'productCode': patch_match.group(3),
            'projectName': patch_match.group(4),
            'siteName': patch_match.group(5)
        }
        print(f"   Params: projectCode={params['projectCode']}, siteCode={params['siteCode']}, productCode={params['productCode']}")

        patch_url = f"{IMS_BASE_URL}/tody/ims/patch/patchList.do"
        patch_response = session.get(patch_url, params=params)
        patch_html = patch_response.text

        with open("debug_patch_list_343803.html", "w", encoding="utf-8") as f:
            f.write(patch_html)
        print(f"   Saved Patch List HTML ({len(patch_html)} bytes)")

        # Parse issue IDs from Patch List
        patch_ids = re.findall(r'>(\d{6})<', patch_html)
        patch_ids = list(set(patch_ids))
        print(f"   Patch List Issue IDs ({len(patch_ids)}): {patch_ids[:20]}")

        if TEST_ISSUE_ID in patch_ids:
            print(f"   *** SELF-REFERENCE in Patch List: {TEST_ISSUE_ID} ***")
        else:
            print(f"   No self-reference in Patch List")
    else:
        print("   Patch List params not found in HTML")

    # 5. Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Issue ID: {TEST_ISSUE_ID}")
    print(f"Related Issue API IDs: {related_ids}")
    if patch_match:
        print(f"Patch List IDs count: {len(patch_ids)}")

    # Check what our crawler would produce
    all_ids = related_ids + (patch_ids if patch_match else [])
    seen = set()
    unique_ids = []
    for id in all_ids:
        if id not in seen and id != TEST_ISSUE_ID:
            seen.add(id)
            unique_ids.append(id)

    print(f"\nAfter dedup (excluding self): {len(unique_ids)} IDs")
    print(f"Sample: {unique_ids[:10]}")


if __name__ == "__main__":
    main()
