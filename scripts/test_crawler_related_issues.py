"""
Test existing crawler related issues logic in requests_crawler.py
"""

import sys
import os
import asyncio
import io

# Fix console encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.ims_crawler.infrastructure.adapters.requests_crawler import RequestsBasedCrawler
from app.api.ims_crawler.infrastructure.services.credential_encryption_service import CredentialEncryptionService
from app.api.ims_crawler.domain.entities import UserCredentials


async def test_related_issues():
    print("=" * 60)
    print("Testing Existing Crawler Related Issues Logic")
    print("=" * 60)

    # Initialize services
    encryption_service = CredentialEncryptionService()
    crawler = RequestsBasedCrawler(encryption_service)

    # Create credentials
    username = "yijae.shin"
    password = "12qwaszx"

    encrypted_username, encrypted_password = encryption_service.encrypt_credentials(
        username, password
    )

    credentials = UserCredentials(
        user_id="test_user",
        encrypted_username=encrypted_username,
        encrypted_password=encrypted_password,
        ims_base_url="https://ims.tmaxsoft.com"
    )

    # Authenticate
    print("\n[Step 1] Authenticating...")
    auth_result = await crawler.authenticate(credentials)
    print(f"  Authentication: {'Success' if auth_result else 'Failed'}")

    if not auth_result:
        print("Authentication failed. Exiting.")
        return

    # Test issues
    test_issues = ["267161", "175318", "343803"]

    for issue_id in test_issues:
        print(f"\n{'='*60}")
        print(f"Testing Issue: {issue_id}")
        print("=" * 60)

        # Test crawl_issue_details with fetch_related=True
        print("\n[1] crawl_issue_details(fetch_related=True):")
        try:
            issue = await crawler.crawl_issue_details(
                issue_id,
                credentials,
                fallback_issue=None,
                fetch_related=True
            )
            print(f"  - Title: {issue.title[:50]}...")
            print(f"  - Status: {issue.status}")
            print(f"  - Product: {issue.product}")
            print(f"  - Related Issue IDs: {len(issue.related_issue_ids) if issue.related_issue_ids else 0}")
            if issue.related_issue_ids:
                print(f"  - Sample IDs: {issue.related_issue_ids[:10]}")
        except Exception as e:
            print(f"  - Error: {e}")

        # Test internal methods directly
        print("\n[2] Testing internal methods:")

        # Get issue detail HTML first
        base_url = "https://ims.tmaxsoft.com"
        session = crawler._ensure_session()

        response = session.post(
            f"{base_url}/tody/ims/issue/issueView.do",
            data={'issueId': issue_id, 'menuCode': 'issue_list'},
            timeout=60
        )
        html = response.text

        # Test _fetch_related_issue_ids_sync
        print("\n  [2a] _fetch_related_issue_ids_sync:")
        related_ids = crawler._fetch_related_issue_ids_sync(issue_id, base_url)
        print(f"    - Result: {len(related_ids)} IDs")
        if related_ids:
            print(f"    - IDs: {related_ids}")

        # Test _parse_patch_list_params
        print("\n  [2b] _parse_patch_list_params:")
        patch_params = crawler._parse_patch_list_params(html)
        if patch_params:
            print(f"    - Found params:")
            for k, v in patch_params.items():
                print(f"      - {k}: {v}")
        else:
            print("    - No patch params found")

        # Test _fetch_patch_list_issue_ids_sync
        if patch_params:
            print("\n  [2c] _fetch_patch_list_issue_ids_sync:")
            patch_ids = crawler._fetch_patch_list_issue_ids_sync(patch_params, base_url)
            print(f"    - Result: {len(patch_ids)} IDs")
            if patch_ids:
                print(f"    - Sample IDs: {patch_ids[:10]}...")

    # Cleanup
    await crawler.close()
    print("\n" + "=" * 60)
    print("Test completed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_related_issues())
