# IMS 스크래핑 방식 - 실용적 대안 분석

**Date**: 2025-12-29
**Status**: 현실적 해결책 제안

## 문제 분석

### 시도한 방법들과 한계

| 방법 | 장점 | 단점 | 결과 |
|------|------|------|------|
| **쿠키 복사** | 간단 | Chrome 실행 중 불가 (Exclusive Lock) | ❌ 실패 |
| **Profile Scraping** | 세션 유지 | Chrome 종료 필수 | ⚠️ 비현실적 |
| **CDP (Debug Mode)** | Chrome 실행 유지 | 디버깅 모드 시작 복잡 | ❌ 자동화 실패 |

### 근본 문제

1. **Chrome의 보안 정책**
   - User Data Directory: 한 번에 하나의 프로세스만
   - Cookie DB: Exclusive lock (실행 중 읽기 불가)
   - CDP: 특수한 시작 방법 필요

2. **Production 요구사항**
   - 사용자가 특별한 조치 없이 사용 가능해야 함
   - Chrome을 일반적인 방법으로 사용하면서 스크래핑 가능해야 함

---

## 실용적 해결책

### ✅ **방법 1: Chrome Extension (권장)**

Chrome Extension으로 쿠키를 추출하여 백엔드로 전송

#### 구조

```
[사용자]
  └─ Chrome (일반 모드, ims.tmaxsoft.com 로그인)
       └─ Chrome Extension 설치
            └─ "Extract IMS Cookies" 버튼 클릭
                 └─ cookies API로 쿠키 추출
                      └─ 백엔드 API로 POST
                           └─ Playwright가 쿠키 사용하여 스크래핑
```

#### 장점
- ✅ Chrome을 종료할 필요 없음
- ✅ 일반 모드로 사용 가능
- ✅ 사용자가 버튼 한 번 클릭으로 완료
- ✅ 보안 정책 준수 (Extension API 사용)

#### 구현

**manifest.json**:
```json
{
  "manifest_version": 3,
  "name": "IMS Cookie Extractor",
  "version": "1.0",
  "permissions": [
    "cookies",
    "tabs"
  ],
  "host_permissions": [
    "https://ims.tmaxsoft.com/*"
  ],
  "action": {
    "default_popup": "popup.html"
  }
}
```

**popup.js**:
```javascript
document.getElementById('extract').addEventListener('click', async () => {
  // Get cookies for ims.tmaxsoft.com
  const cookies = await chrome.cookies.getAll({
    domain: '.tmaxsoft.com'
  });

  // Send to backend
  const response = await fetch('http://localhost:8000/api/v1/ims-sso/upload-cookies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookies })
  });

  if (response.ok) {
    alert('Cookies uploaded! You can now scrape IMS.');
  }
});
```

#### 사용 흐름

1. Chrome Extension 설치 (한 번만)
2. IMS 로그인 (일반적으로)
3. Extension 아이콘 클릭 → "Extract Cookies" 버튼
4. 백엔드로 쿠키 자동 전송
5. 프론트엔드에서 "Scrape IMS" 버튼 클릭
6. Chrome은 계속 실행 상태 유지

---

### ✅ **방법 2: 별도 Chrome 프로필 (IMS 전용)**

IMS 전용 Chrome 프로필 생성

#### 구조

```
[사용자의 메인 Chrome]
  └─ 일반 사용 (계속 실행)

[IMS 전용 Chrome 프로필]
  └─ Profile: "IMS-Scraper"
  └─ IMS 로그인 (한 번만)
  └─ Playwright가 이 프로필 사용 (Chrome 종료 시)
```

#### 장점
- ✅ 메인 Chrome과 독립적
- ✅ IMS 세션 영구 유지
- ✅ 스크래핑 시에만 잠깐 종료

#### 설정

1. **IMS 전용 프로필 생성**
   ```bash
   chrome.exe --profile-directory="IMS-Scraper"
   ```

2. **IMS 로그인 (한 번만)**
   - https://ims.tmaxsoft.com 접속
   - 로그인
   - Chrome 종료

3. **스크래핑 시**
   - IMS 전용 프로필로 Playwright 실행
   - 메인 Chrome은 계속 실행 중

#### 백엔드 구현

```python
# IMS-Scraper 프로필 사용
async with IMSProfileScraper(
    user_data_dir=USER_DATA_DIR,
    profile="IMS-Scraper",  # 전용 프로필
    headless=True
) as scraper:
    issues = await scraper.scrape_issue_list()
```

---

### ✅ **방법 3: 스케줄링 (야간 스크래핑)**

업무 시간 외 자동 스크래핑

#### 구조

```
[낮 시간]
  └─ 사용자가 Chrome으로 작업

[밤 시간 (예: 23:00)]
  └─ 자동 스크립트 실행
       └─ Chrome 종료
       └─ IMS 스크래핑
       └─ 결과 저장
       └─ Chrome 재시작 (선택)
```

#### 장점
- ✅ 사용자 개입 불필요
- ✅ 업무 시간에 방해 안 됨
- ✅ 매일 자동 업데이트

#### Windows 작업 스케줄러 설정

```powershell
# 스케줄러 등록
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\path\to\scrape_ims_nightly.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 11:00PM
Register-ScheduledTask -TaskName "IMS Nightly Scraping" -Action $action -Trigger $trigger
```

---

## 추천 방식 비교

| 방식 | 복잡도 | 사용자 편의성 | Production 적합 |
|------|--------|---------------|-----------------|
| **Chrome Extension** | 중간 | ⭐⭐⭐⭐⭐ | ✅ 최고 |
| **별도 프로필** | 낮음 | ⭐⭐⭐ | ✅ 좋음 |
| **스케줄링** | 낮음 | ⭐⭐⭐⭐ | ✅ 좋음 |
| CDP (현재) | 높음 | ⭐ | ⚠️ 복잡 |

---

## 최종 권장사항

### 🥇 **1순위: 별도 Chrome 프로필 (즉시 사용 가능)**

**이유**:
- ✅ 구현 완료 (백엔드 API, 스크래퍼, 테스트 스크립트 모두 준비됨)
- ✅ 메인 Chrome과 독립적 (업무 방해 없음)
- ✅ 5분 설정 (setup_ims_profile.bat 실행만 하면 됨)
- ✅ Production 즉시 적용 가능

**적용 시나리오**:
- 지금 바로 사용 필요
- 메인 Chrome 종료 불가
- 추가 개발 시간 없음
- 안정적인 솔루션 필요

**현재 구현 상태**:
- ✅ 백엔드 API: `/api/v1/ims-sso/scrape-with-profile`
- ✅ 스크래퍼: `IMSProfileScraper` (app/api/ims_sso_connector/scraper/)
- ✅ 설정 스크립트: `setup_ims_profile.bat`
- ✅ 테스트 스크립트: `test_profile_quick.py`
- ✅ 상세 가이드: `docs/IMS_SEPARATE_PROFILE_GUIDE.md`

**즉시 시작**:
```bash
# 1. 프로필 설정 (한 번만)
setup_ims_profile.bat
# → IMS 로그인 → Chrome 창 종료

# 2. 테스트
python test_profile_quick.py

# 3. 사용
# POST /api/v1/ims-sso/scrape-with-profile
```

---

### 🥈 **2순위: Chrome Extension (장기적 최적 솔루션)**

**이유**:
- 사용자 경험 최고
- Chrome 종료 완전히 불필요
- 버튼 클릭 한 번으로 완료
- Production 환경에 가장 적합

**적용 시나리오**:
- 사용자가 자주 스크래핑하는 경우
- UI에서 "Scrape Now" 기능 제공
- 실시간성이 중요한 경우

**개발 필요**:
- Extension 개발 (manifest.json, popup.js, popup.html)
- 백엔드 `/upload-cookies` 엔드포인트 추가
- Chrome Web Store 배포

---

### 🥉 **3순위: 야간 스케줄링**

**이유**:
- 완전 자동화
- 사용자 개입 불필요
- 백그라운드 작업

**적용 시나리오**:
- 일일 데이터 업데이트
- 사용자가 실시간 스크래핑 불필요
- 대량 데이터 수집

---

## 다음 단계

### ✅ **즉시 시작: 별도 Chrome 프로필 (권장)**

```bash
# 1. 프로필 설정 (5분)
setup_ims_profile.bat
# → 열린 Chrome 창에서 https://ims.tmaxsoft.com 로그인
# → Chrome 창 종료 (메인 Chrome은 계속 실행)

# 2. 테스트 (30초)
python test_profile_quick.py
# → IMS 이슈 목록 스크래핑 확인

# 3. 프론트엔드 통합
POST /api/v1/ims-sso/scrape-with-profile
{
  "profile": "IMS-Scraper",
  "search_type": "1",
  "menu_code": "issue_search"
}
```

**상세 가이드**: `docs/IMS_SEPARATE_PROFILE_GUIDE.md`

---

### 선택지 2: Chrome Extension 개발 (향후)

```bash
# Extension 디렉토리 생성
mkdir chrome-extension-ims
cd chrome-extension-ims

# 파일 생성
# - manifest.json
# - popup.html
# - popup.js
# - icon.png

# Chrome에 로드
# chrome://extensions → Developer mode → Load unpacked
```

---

### 선택지 3: 야간 스케줄링 설정 (자동화)

```python
# scrape_ims_nightly.py 작성
# Windows Task Scheduler 등록
# 매일 23:00 자동 실행
```

---

## 결론

**즉시 사용 가능한 해결책**:

1. **지금 바로**: 별도 Chrome 프로필 (IMS-Scraper) ✅
   - ✅ 모든 구현 완료 (API, 스크래퍼, 테스트, 가이드)
   - ✅ 5분 설정으로 즉시 사용
   - ✅ 메인 Chrome 방해 없음
   - ✅ Production 적용 가능

2. **장기적**: Chrome Extension 개발 (선택 사항)
   - 최고의 사용자 경험
   - Production 환경 최적화
   - 추가 개발 필요

**다음 액션**:
```bash
setup_ims_profile.bat
```
