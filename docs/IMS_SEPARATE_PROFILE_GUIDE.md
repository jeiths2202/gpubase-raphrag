# IMS Separate Profile Setup Guide

**Date**: 2025-12-29
**Method**: Dedicated Chrome Profile for IMS Scraping
**Status**: Production Ready ✅

## 개요

메인 Chrome을 종료하지 않고 IMS를 스크래핑하는 방법입니다.

### 핵심 개념

```
[메인 Chrome] (계속 실행)
  └─ Profile: Default
  └─ 일반 업무용

[IMS 전용 Chrome] (스크래핑 시에만 종료)
  └─ Profile: IMS-Scraper
  └─ IMS 로그인 세션 유지
```

## 장점

- ✅ **메인 Chrome 방해 없음**: 일반 Chrome 계속 사용 가능
- ✅ **세션 영구 유지**: IMS 로그인 한 번이면 계속 사용
- ✅ **구현 완료**: 백엔드 API 이미 준비됨
- ✅ **5분 설정**: 빠른 초기 설정
- ✅ **Production 가능**: 실제 운영 환경에서 사용 가능

## 설정 방법

### 방법 1: 배치 파일 사용 (권장)

```bash
# 1. 설정 스크립트 실행
setup_ims_profile.bat

# 2. 열린 Chrome 창에서 IMS 로그인
#    (https://ims.tmaxsoft.com)

# 3. 로그인 후 해당 Chrome 창만 종료
#    (메인 Chrome은 계속 실행)

# 4. 테스트
python test_profile_quick.py
```

### 방법 2: 수동 설정

1. **IMS-Scraper 프로필 생성**
   ```bash
   # 명령 프롬프트에서 실행
   "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
     --profile-directory="IMS-Scraper" ^
     https://ims.tmaxsoft.com
   ```

2. **IMS 로그인**
   - 열린 Chrome 창에서 https://ims.tmaxsoft.com 로그인
   - 로그인 성공 확인

3. **Chrome 창 종료**
   - IMS-Scraper 프로필 Chrome 창만 종료
   - 메인 Chrome은 계속 실행 유지

4. **프로필 확인**
   ```bash
   # 프로필 디렉토리 존재 확인
   dir "%LOCALAPPDATA%\Google\Chrome\User Data\IMS-Scraper"
   ```

## 사용 방법

### Python Script

```python
from app.api.ims_sso_connector.scraper.ims_profile_scraper import scrape_ims_issues_with_profile

# IMS-Scraper 프로필 사용
issues = await scrape_ims_issues_with_profile(
    ims_url="https://ims.tmaxsoft.com",
    profile="IMS-Scraper",  # 전용 프로필
    search_type="1",
    menu_code="issue_search"
)

print(f"Found {len(issues)} issues")
```

### REST API

```bash
# POST /api/v1/ims-sso/scrape-with-profile
curl -X POST http://localhost:8000/api/v1/ims-sso/scrape-with-profile \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "IMS-Scraper",
    "search_type": "1",
    "menu_code": "issue_search"
  }'
```

### API Response

```json
{
  "success": true,
  "data": {
    "total_count": 127,
    "issues": [
      {
        "index": 1,
        "id": "IMS-2024-001",
        "title": "Issue title here",
        "status": "Open",
        "assignee": "John Doe",
        "created_date": "2024-12-15",
        "cells": ["...", "...", "..."]
      }
    ],
    "profile_used": "IMS-Scraper",
    "scrape_timestamp": "2025-12-29T10:30:45"
  }
}
```

## 워크플로우

### 일반 사용

```
1. [한 번만] setup_ims_profile.bat 실행 → IMS 로그인 → 종료
2. [스크래핑 시] API 호출 또는 Python 스크립트 실행
3. [완료 후] 메인 Chrome 계속 사용
```

### 세션 갱신 필요 시

```
1. setup_ims_profile.bat 재실행
2. IMS 다시 로그인
3. Chrome 창 종료
```

## 문제 해결

### "Chrome is running" 에러

**증상**:
```
RuntimeError: Chrome is running. Close Chrome or use a separate profile.
```

**원인**: IMS-Scraper 프로필 Chrome 창이 아직 열려있음

**해결**:
```bash
# Windows: IMS-Scraper 프로세스 확인
tasklist | findstr chrome.exe

# 해당 Chrome 창만 종료 (메인 Chrome 아님)
# 또는 수동으로 IMS-Scraper 창 닫기
```

### 로그인 세션 없음

**증상**: 로그인 페이지로 리다이렉트

**원인**:
- IMS-Scraper 프로필에 로그인 기록 없음
- 세션 만료

**해결**:
```bash
# 1. 재설정
setup_ims_profile.bat

# 2. IMS 로그인

# 3. Chrome 창 종료

# 4. 재시도
python test_profile_quick.py
```

### 프로필 디렉토리 없음

**증상**:
```
FileNotFoundError: Profile directory not found
```

**원인**: IMS-Scraper 프로필이 생성되지 않음

**해결**:
```bash
# 수동으로 프로필 생성
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --profile-directory="IMS-Scraper"
```

## 고급 사용

### 여러 IMS 인스턴스

```python
# Production IMS
issues_prod = await scrape_ims_issues_with_profile(
    ims_url="https://ims.tmaxsoft.com",
    profile="IMS-Scraper-Prod"
)

# Development IMS
issues_dev = await scrape_ims_issues_with_profile(
    ims_url="https://ims-dev.tmaxsoft.com",
    profile="IMS-Scraper-Dev"
)
```

### 커스텀 User Data Directory

```python
issues = await scrape_ims_issues_with_profile(
    ims_url="https://ims.tmaxsoft.com",
    user_data_dir=r"D:\CustomChrome\UserData",
    profile="IMS-Scraper"
)
```

### Headless 모드

```python
# GUI 없이 백그라운드 실행
issues = await scrape_ims_issues_with_profile(
    profile="IMS-Scraper",
    headless=True  # 화면 없음
)
```

## 보안 고려사항

### Cookie/Session 보안

- ✅ Cookie는 Chrome 프로필에만 저장
- ✅ 파일 시스템 레벨 암호화 (Windows DPAPI)
- ✅ 프로세스 간 격리 (Profile 분리)

### 권장 사항

1. **IMS-Scraper 프로필 전용 사용**
   - 일반 브라우징 금지
   - IMS 로그인 용도로만 사용

2. **정기적인 세션 갱신**
   - 월 1회 재로그인 권장
   - 보안 정책에 따라 조정

3. **접근 제어**
   - User Data Directory 권한 관리
   - 백업 시 암호화 필수

## 비교: 다른 방법들

| 방법 | 메인 Chrome | 설정 복잡도 | Production 적합 |
|------|-------------|-------------|-----------------|
| **Separate Profile** | ✅ 계속 실행 | 낮음 (5분) | ✅ 적합 |
| Cookie Copy | ❌ 종료 필요 | 중간 | ❌ 불가 (Exclusive Lock) |
| CDP | ✅ 계속 실행 | 높음 (자동화 실패) | ⚠️ 수동 시작 필요 |
| Chrome Extension | ✅ 계속 실행 | 높음 (개발 필요) | ✅ 최적 |

## 성능 특성

| 항목 | 값 |
|------|-----|
| 초기 설정 시간 | ~5분 |
| 스크래핑 시간 (100개 이슈) | ~10-15초 |
| 메모리 사용 | ~200-300MB (Chrome instance) |
| 디스크 공간 | ~100MB (Profile) |

## 다음 단계

### 즉시 사용 가능

```bash
# 1. 설정
setup_ims_profile.bat

# 2. 테스트
python test_profile_quick.py

# 3. 프론트엔드 통합
# POST /api/v1/ims-sso/scrape-with-profile
```

### 향후 개선 (선택)

1. **Chrome Extension 개발**: 최고의 UX
2. **스케줄링 추가**: 자동 주기적 스크래핑
3. **Multi-Instance**: 여러 IMS 서버 지원

## 참고 문서

- `docs/IMS_PROFILE_SCRAPING.md` - 상세 API 문서
- `docs/IMS_SCRAPING_ALTERNATIVES.md` - 대안 방법 비교
- `app/api/ims_sso_connector/scraper/ims_profile_scraper.py` - 구현 코드
- `app/api/routers/ims_sso.py` - API 엔드포인트 (line 180-220)
