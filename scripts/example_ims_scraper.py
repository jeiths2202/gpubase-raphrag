#!/usr/bin/env python3
"""
IMS Issue Scraper - Example Usage

이 스크립트는 IMS 이슈 목록 페이지를 스크래핑하는 방법을 보여줍니다.
Chrome에 이미 로그인된 세션을 재사용하여 IMS 시스템의 데이터를 추출합니다.

Usage:
    python scripts/example_ims_scraper.py
    python scripts/example_ims_scraper.py --url https://ims.tmaxsoft.com --profile Default
    python scripts/example_ims_scraper.py --output issues.json
"""
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.ims_sso_connector.scraper.ims_issue_scraper import IMSIssueScraper, scrape_ims_issues


async def example_basic_usage():
    """
    기본 사용법: Context manager를 사용한 스크래핑
    """
    print("=" * 60)
    print("Example 1: Basic Usage with Context Manager")
    print("=" * 60)

    async with IMSIssueScraper(
        ims_url="https://ims.tmaxsoft.com",
        chrome_profile="Default",
        headless=True  # 백그라운드 실행 (디버깅 시 False로 변경)
    ) as scraper:
        issues = await scraper.scrape_issue_list(
            search_type="1",
            menu_code="issue_search"
        )

        print(f"\n✅ Extracted {len(issues)} issues")

        # 첫 3개 미리보기
        if issues:
            print("\n📋 First 3 issues:")
            for i, issue in enumerate(issues[:3], 1):
                print(f"\n{i}. {json.dumps(issue, ensure_ascii=False, indent=2)}")

        return issues


async def example_convenience_function():
    """
    편의 함수 사용: 간편하게 스크래핑하고 파일로 저장
    """
    print("\n" + "=" * 60)
    print("Example 2: Using Convenience Function")
    print("=" * 60)

    issues = await scrape_ims_issues(
        ims_url="https://ims.tmaxsoft.com",
        chrome_profile="Default",
        output_file="ims_issues.json"
    )

    print(f"\n✅ Scraped and saved {len(issues)} issues to ims_issues.json")
    return issues


async def example_custom_selector():
    """
    커스텀 셀렉터 사용: 특정 요소가 로드될 때까지 대기
    """
    print("\n" + "=" * 60)
    print("Example 3: Custom Selector and Wait Time")
    print("=" * 60)

    async with IMSIssueScraper(
        ims_url="https://ims.tmaxsoft.com",
        headless=False  # 브라우저 UI 표시 (디버깅용)
    ) as scraper:
        issues = await scraper.scrape_issue_list(
            search_type="1",
            menu_code="issue_search",
            wait_for_selector="table.issue-list tbody tr",  # 이슈 테이블 행 대기
            max_wait_time=15000  # 최대 15초 대기
        )

        print(f"\n✅ Extracted {len(issues)} issues with custom selector")
        return issues


async def example_issue_detail():
    """
    이슈 상세 정보 조회
    """
    print("\n" + "=" * 60)
    print("Example 4: Getting Issue Details")
    print("=" * 60)

    async with IMSIssueScraper(ims_url="https://ims.tmaxsoft.com") as scraper:
        # 먼저 이슈 목록 가져오기
        issues = await scraper.scrape_issue_list()

        if issues:
            # 첫 번째 이슈의 상세 정보 조회
            first_issue_id = issues[0].get('id')
            if first_issue_id:
                detail = await scraper.get_issue_detail(first_issue_id)
                print(f"\n📄 Issue Detail for {first_issue_id}:")
                print(json.dumps(detail, ensure_ascii=False, indent=2))
                return detail

        print("⚠️ No issues found or issue ID not available")


async def example_error_handling():
    """
    에러 처리 예제
    """
    print("\n" + "=" * 60)
    print("Example 5: Error Handling")
    print("=" * 60)

    try:
        async with IMSIssueScraper(
            ims_url="https://ims.tmaxsoft.com",
            chrome_profile="InvalidProfile"  # 존재하지 않는 프로필
        ) as scraper:
            issues = await scraper.scrape_issue_list()
    except Exception as e:
        print(f"\n❌ Expected error caught: {e}")
        print("✅ Error handling works correctly")

        # 올바른 프로필로 재시도
        print("\n🔄 Retrying with correct profile...")
        async with IMSIssueScraper(
            ims_url="https://ims.tmaxsoft.com",
            chrome_profile="Default"
        ) as scraper:
            issues = await scraper.scrape_issue_list()
            print(f"✅ Successfully scraped {len(issues)} issues after retry")
            return issues


async def main():
    """
    모든 예제 실행
    """
    print("""
╔════════════════════════════════════════════════════════╗
║       IMS Issue Scraper - Example Usage               ║
╚════════════════════════════════════════════════════════╝

이 스크립트는 다양한 IMS 스크래핑 사용법을 보여줍니다.

Prerequisites:
✅ Chrome browser installed
✅ Logged into IMS system in Chrome
✅ Playwright installed: pip install playwright
✅ Playwright browsers installed: playwright install chromium
    """)

    # 예제 선택
    if len(sys.argv) > 1:
        example_num = sys.argv[1]
        if example_num == "1":
            await example_basic_usage()
        elif example_num == "2":
            await example_convenience_function()
        elif example_num == "3":
            await example_custom_selector()
        elif example_num == "4":
            await example_issue_detail()
        elif example_num == "5":
            await example_error_handling()
        else:
            print(f"❌ Unknown example: {example_num}")
            print("Available examples: 1, 2, 3, 4, 5")
    else:
        # 모든 예제 실행 (1, 2만 - 빠른 예제)
        try:
            print("\n🚀 Running quick examples (1, 2)...")
            print("To run specific example: python scripts/example_ims_scraper.py <1|2|3|4|5>\n")

            await example_basic_usage()
            await example_convenience_function()

            print("\n" + "=" * 60)
            print("✅ All quick examples completed!")
            print("=" * 60)
            print("""
To run individual examples:
  python scripts/example_ims_scraper.py 1  # Basic usage
  python scripts/example_ims_scraper.py 2  # Convenience function
  python scripts/example_ims_scraper.py 3  # Custom selector (visible browser)
  python scripts/example_ims_scraper.py 4  # Issue details
  python scripts/example_ims_scraper.py 5  # Error handling
            """)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("\nTroubleshooting:")
            print("1. Make sure you're logged into IMS in Chrome")
            print("2. Verify Chrome profile name (Default, Profile 1, etc.)")
            print("3. Check if Playwright is installed: pip install playwright")
            print("4. Install Playwright browsers: playwright install chromium")
            print("5. Check network connectivity to IMS system")


if __name__ == "__main__":
    asyncio.run(main())
