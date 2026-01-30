# IMS Profile Scraping - Chrome 세션 재사용 방식

**Date**: 2025-12-29
**Status**: ✅ PRODUCTION READY

## 개요

Chrome 프로필의 로그인 세션을 직접 사용하여 IMS를 스크래핑합니다.
쿠키 복사, 디버깅 모드, SSO 연결 모두 불필요한 **가장 간단한 방식**입니다.

## 핵심 원리

```
[사용자]
  └─ Chrome (https://ims.tmaxsoft.com 로그인됨)
       └─ Chrome 종료
            └─ Playwright가 동일 프로필로 Chrome 기동
                 └─ ims.tmaxsoft.com 접근
                      └─ 세션 자동 인식 ✓
```

### Playwright `launch_persistent_context()` 사용

```python
from playwright.async_api import async_playwright

USER_DATA_DIR = r"C:\Users\USERNAME\AppData\Local\Google\Chrome\User Data"

async with async_playwright() as p:
    context = await p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR + "/Default",
        channel="chrome",
        headless=False
    )

    page = await context.new_page()
    await page.goto("https://ims.tmaxsoft.com")

    # 로그인 상태 자동 유지 ✓
    await page.wait_for_selector("text=Knowledge")
```

## 장점

### ✅ Production Ready
- 디버깅 모드 불필요
- 쿠키 복사 불필요
- SSO 연결 불필요
- 별도 인프라 불필요

### ✅ 간단함
- Chrome 로그인 → 종료 → API 호출
- 3단계로 완료

### ✅ 안정적
- Chrome의 실제 세션 사용
- 쿠키 만료 걱정 없음
- 자동 로그인 유지

## 제약사항

### ⚠️ Chrome 종료 필요

**문제**: Chrome이 실행 중이면 User Data Directory가 잠김
**해결**: Chrome을 완전히 종료한 상태에서 API 호출

### 사용 흐름

```yaml
Step 1: Chrome 로그인
  - 사용자가 Chrome에서 https://ims.tmaxsoft.com 로그인
  - 정상적으로 사용

Step 2: 스크래핑 필요 시
  - Chrome 완전 종료
  - API 호출: POST /api/v1/ims-sso/scrape-with-profile
  - Playwright가 Chrome 프로필로 스크래핑

Step 3: 스크래핑 완료 후
  - Chrome 재시작 가능
  - 다음 스크래핑 시 Step 2 반복
```

## API 사용법

### 1. 백엔드 API 엔드포인트

**Endpoint**: `POST /api/v1/ims-sso/scrape-with-profile`

**Request**:
```json
{
  "ims_url": "https://ims.tmaxsoft.com",
  "user_data_dir": null,
  "profile": "Default",
  "search_type": "1",
  "menu_code": "issue_search",
  "headless": true
}
```

**Parameters**:
- `ims_url`: IMS 시스템 URL (기본값: https://ims.tmaxsoft.com)
- `user_data_dir`: Chrome User Data 디렉토리 (null이면 자동 탐지)
- `profile`: Chrome 프로필 이름 (기본값: "Default")
- `search_type`: 검색 타입 (기본값: "1")
- `menu_code`: 메뉴 코드 (기본값: "issue_search")
- `headless`: 헤드리스 모드 (기본값: true)

**Response**:
```json
{
  "status": "success",
  "data": {
    "issues": [
      {
        "index": 1,
        "id": "ISSUE-001",
        "title": "Example Issue",
        "status": "Open",
        "assignee": "John Doe",
        "created_date": "2025-12-29",
        "cells": ["ISSUE-001", "Example Issue", "Open", ...]
      }
    ],
    "count": 15,
    "scraping_method": "chrome_profile",
    "profile_used": "Default"
  },
  "meta": {
    "message": "Successfully scraped 15 issues from IMS using Chrome profile",
    "extra": {
      "ims_url": "https://ims.tmaxsoft.com",
      "profile": "Default",
      "search_type": "1",
      "chrome_required": "must_be_closed",
      "session_reuse": true
    }
  }
}
```

### 2. 프론트엔드 통합

**기존 ContentTab.tsx 수정**:

```typescript
// IMS Knowledge Service 메뉴에서 스크래핑 버튼 추가
const scrapeIMS = async () => {
  setScrapingIMS(true);
  setScrapingError(null);

  try {
    const response = await api.post('/ims-sso/scrape-with-profile', {
      ims_url: 'https://ims.tmaxsoft.com',
      profile: 'Default',
      search_type: '1',
      headless: true
    });

    const { issues, count } = response.data.data;

    setScrapedIssues(issues);
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'assistant',
      content: `Successfully scraped ${count} issues from IMS`,
      timestamp: new Date()
    }]);

  } catch (error: any) {
    const errorMessage = error.response?.data?.detail ||
                        'Scraping failed';

    if (error.response?.status === 409) {
      // Chrome 실행 중 오류
      setScrapingError(
        'Chrome이 실행 중입니다. Chrome을 종료한 후 다시 시도해주세요.'
      );
    } else {
      setScrapingError(errorMessage);
    }
  } finally {
    setScrapingIMS(false);
  }
};
```

**UI 추가**:
```tsx
<button onClick={scrapeIMS} disabled={scrapingIMS}>
  {scrapingIMS ? 'Scraping...' : 'Scrape IMS Issues'}
</button>

{scrapingError && (
  <div className="error">
    {scrapingError}
  </div>
)}
```

## Python 직접 사용

```python
import asyncio
from app.api.ims_sso_connector.scraper.ims_profile_scraper import (
    scrape_ims_issues_with_profile
)

async def main():
    # Chrome을 종료한 상태에서 실행
    issues = await scrape_ims_issues_with_profile(
        ims_url="https://ims.tmaxsoft.com",
        user_data_dir=r"C:\Users\USERNAME\AppData\Local\Google\Chrome\User Data",
        profile="Default",
        search_type="1",
        headless=True
    )

    print(f"Found {len(issues)} issues")
    for issue in issues:
        print(issue)

asyncio.run(main())
```

## 테스트

### 테스트 스크립트 실행

```bash
# Chrome 종료 필수!
python test_profile_scraper.py
```

**예상 출력**:
```
======================================================================
IMS Profile Scraper Test
======================================================================

⚠️  Prerequisites:
1. Login to https://ims.tmaxsoft.com in Chrome
2. Close ALL Chrome windows completely
3. Run this test

Chrome User Data: C:\Users\yijae.shin\AppData\Local\Google\Chrome\User Data
Profile: Default

Starting scrape...

[INFO] Initializing Chrome with profile context...
[INFO] User Data Dir: C:\Users\yijae.shin\AppData\Local\Google\Chrome\User Data
[INFO] Profile: Default
[OK] Chrome launched with persistent context
[OK] Scraper initialized
[INFO] Navigating to: https://ims.tmaxsoft.com/tody/ims/issue/issueSearchList.do?searchType=1&menuCode=issue_search
[OK] Page loaded
[OK] Issue list loaded
[INFO] Extracting issue data...
[OK] Extracted 15 issues

======================================================================
✓ SUCCESS: 15 issues found
======================================================================
```

## 에러 처리

### 1. Chrome 실행 중 오류

**Error**: `HTTP 409 Conflict`
**Message**: "Chrome이 실행 중입니다. Chrome을 완전히 종료한 후 다시 시도해주세요."

**해결**:
1. 모든 Chrome 창 닫기
2. 작업 관리자에서 chrome.exe 프로세스 확인
3. 완전히 종료된 후 재시도

### 2. 프로필 찾을 수 없음

**Error**: `HTTP 404 Not Found`
**Message**: "Chrome 프로필을 찾을 수 없습니다"

**해결**:
1. Chrome User Data 경로 확인:
   - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data`
   - macOS: `~/Library/Application Support/Google/Chrome`
   - Linux: `~/.config/google-chrome`
2. 프로필 이름 확인 (Default, Profile 1, etc.)
3. Chrome 설치 확인

### 3. 로그인 페이지로 리다이렉트

**Symptom**: 스크래핑 시 로그인 화면 표시

**해결**:
1. Chrome에서 https://ims.tmaxsoft.com 로그인
2. 로그인 상태 확인
3. Chrome 종료
4. 스크래핑 재시도

## Production 배포 고려사항

### 1. 별도 Chrome 프로필 생성 (권장)

사용자의 메인 Chrome과 분리하기 위해:

```bash
# Windows
chrome.exe --profile-directory="IMS-Scraper"

# 첫 실행 시 IMS 로그인
# 이후 해당 프로필로 스크래핑
```

**API 호출 시**:
```json
{
  "profile": "IMS-Scraper"
}
```

### 2. Headless 모드 사용

Production에서는 `headless: true` 설정:
```json
{
  "headless": true
}
```

### 3. 스크래핑 스케줄링

Chrome 종료 시간대를 고려한 스케줄:

```python
# 예: 업무 시간 외 스크래핑
schedule.every().day.at("23:00").do(scrape_ims_task)
```

### 4. 에러 알림

Chrome 실행 중 오류 시 사용자 알림:

```typescript
if (error.response?.status === 409) {
  alert('Chrome을 종료한 후 다시 시도해주세요.');
}
```

## 비교: 3가지 방식

| 방식 | 장점 | 단점 | Production |
|------|------|------|-----------|
| **Profile Scraping** | ✅ 간단<br>✅ 안정적<br>✅ 쿠키 복사 불필요 | ⚠️ Chrome 종료 필요 | ✅ **권장** |
| SSO Session Cookies | ✅ Chrome 재실행 가능 | ❌ 초기 연결 시 Chrome 종료 필요<br>❌ 세션 관리 복잡 | ⚠️ 대안 |
| CDP Debugging | ✅ Chrome 실행 유지 | ❌ 디버깅 모드 필요<br>❌ Production 부적합 | ❌ 비권장 |

## 결론

**Chrome Profile Scraping**이 가장 **간단하고 안정적**인 방식입니다.

✅ **사용 흐름**:
1. Chrome 로그인 (일회성)
2. 스크래핑 시 Chrome 종료
3. API 호출
4. Chrome 재시작

✅ **Production Ready**:
- 디버깅 모드 불필요
- 별도 인프라 불필요
- 쿠키 관리 불필요

⚠️ **유일한 제약**: Chrome 종료 필요 (일반적으로 문제되지 않음)

---

**구현 완료**: 2025-12-29
**Status**: PRODUCTION READY ✅
