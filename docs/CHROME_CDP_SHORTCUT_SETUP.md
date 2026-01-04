# Chrome CDP 바로가기 설정 가이드

Chrome을 디버깅 모드로 시작하는 바로가기를 만드는 방법입니다.

## 방법 1: 바로가기 직접 생성 (권장)

### Step 1: Chrome 실행 파일 위치 찾기

Chrome 설치 경로 (일반적으로):
```
C:\Program Files\Google\Chrome\Application\chrome.exe
```

또는:
```
C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
```

### Step 2: 바로가기 만들기

1. **바탕화면에서 마우스 우클릭**
   - `새로 만들기` → `바로가기` 선택

2. **항목 위치 입력**
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```

   **중요**: 따옴표와 공백 정확히 지켜야 함!

3. **바로가기 이름 입력**
   ```
   Chrome (Debug Mode)
   ```
   또는
   ```
   Chrome CDP
   ```

4. **완료** 클릭

### Step 3: 바로가기 아이콘 변경 (선택사항)

1. 바로가기 우클릭 → `속성`
2. `바로가기` 탭 → `아이콘 변경` 클릭
3. 다른 아이콘 선택 (디버깅 모드임을 구분하기 위해)

### Step 4: 테스트

1. **기존 Chrome 완전히 종료** (중요!)
   - 모든 Chrome 창 닫기
   - 작업 관리자에서 chrome.exe 프로세스 확인

2. **새 바로가기로 Chrome 실행**

3. **디버깅 포트 확인**
   - Chrome 주소창에 입력:
   ```
   http://localhost:9222/json/version
   ```

   **성공 시 출력**:
   ```json
   {
      "Browser": "Chrome/131.0.6778.109",
      "Protocol-Version": "1.3",
      "User-Agent": "Mozilla/5.0...",
      "V8-Version": "13.1.201.13",
      "WebKit-Version": "537.36",
      "webSocketDebuggerUrl": "ws://localhost:9222/devtools/browser/..."
   }
   ```

---

## 방법 2: 기존 바로가기 수정

### Step 1: 기존 Chrome 바로가기 찾기

일반적인 위치:
- 바탕화면
- 시작 메뉴
- 작업 표시줄 (고정된 경우)

### Step 2: 바로가기 속성 열기

1. 바로가기 **우클릭**
2. `속성` 선택

### Step 3: 대상 수정

**현재 대상** (예시):
```
"C:\Program Files\Google\Chrome\Application\chrome.exe"
```

**수정 후**:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**⚠️ 주의사항**:
- 따옴표 안의 경로는 수정하지 말 것
- 따옴표 **뒤**에 공백 하나 추가 후 `--remote-debugging-port=9222` 추가

### Step 4: 적용 및 확인

1. `적용` → `확인` 클릭
2. 방법 1의 Step 4와 동일하게 테스트

---

## 방법 3: PowerShell 스크립트로 자동 생성

### 스크립트 파일 생성

`create_chrome_cdp_shortcut.ps1`:

```powershell
# Chrome CDP 바로가기 자동 생성 스크립트

# Chrome 실행 파일 경로 탐지
$chromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

$chromeExe = $null
foreach ($path in $chromePaths) {
    if (Test-Path $path) {
        $chromeExe = $path
        break
    }
}

if (-not $chromeExe) {
    Write-Host "Chrome을 찾을 수 없습니다!" -ForegroundColor Red
    exit 1
}

Write-Host "Chrome 경로: $chromeExe" -ForegroundColor Green

# 바로가기 생성
$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [System.Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$Desktop\Chrome (Debug Mode).lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $chromeExe
$Shortcut.Arguments = "--remote-debugging-port=9222"
$Shortcut.Description = "Chrome with CDP debugging port 9222"
$Shortcut.IconLocation = $chromeExe
$Shortcut.Save()

Write-Host "바로가기 생성 완료: $ShortcutPath" -ForegroundColor Green
Write-Host ""
Write-Host "사용 방법:"
Write-Host "1. 기존 Chrome 완전히 종료"
Write-Host "2. 바탕화면의 'Chrome (Debug Mode)' 아이콘 더블클릭"
Write-Host "3. http://localhost:9222/json/version 접속하여 확인"
```

### 실행 방법

```powershell
# PowerShell 관리자 권한으로 실행
powershell -ExecutionPolicy Bypass -File create_chrome_cdp_shortcut.ps1
```

---

## 자동 시작 설정 (선택사항)

### Windows 시작 시 자동 실행

1. **시작 프로그램 폴더 열기**
   - `Win + R` → `shell:startup` 입력

2. **바로가기 복사**
   - 생성한 "Chrome (Debug Mode)" 바로가기를 시작 프로그램 폴더에 복사

3. **확인**
   - Windows 재시작 시 Chrome이 디버깅 모드로 자동 실행됨

---

## 트러블슈팅

### 문제 1: "포트가 이미 사용 중입니다"

**원인**: 다른 Chrome 프로세스가 이미 실행 중

**해결**:
```powershell
# 모든 Chrome 프로세스 종료
taskkill /F /IM chrome.exe

# 확인
tasklist | findstr chrome
```

### 문제 2: localhost:9222 접속 안 됨

**원인**: 디버깅 모드로 시작되지 않음

**확인**:
```powershell
# Chrome 프로세스 확인 (--remote-debugging-port 인자 포함되어 있는지)
Get-Process chrome | Select-Object CommandLine
```

**해결**:
1. Chrome 완전 종료
2. 바로가기로만 실행 (직접 실행 X)

### 문제 3: "chrome.exe를 찾을 수 없습니다"

**원인**: Chrome 설치 경로가 다름

**확인**:
```powershell
# Chrome 설치 경로 찾기
Get-ChildItem -Path "C:\Program Files" -Filter chrome.exe -Recurse -ErrorAction SilentlyContinue
Get-ChildItem -Path "C:\Program Files (x86)" -Filter chrome.exe -Recurse -ErrorAction SilentlyContinue
```

---

## 보안 고려사항

### ⚠️ 주의사항

디버깅 포트가 활성화되면 **로컬 네트워크에서 Chrome을 제어**할 수 있습니다.

**권장 사항**:
1. **로컬호스트만 허용** (기본값)
   ```
   --remote-debugging-port=9222
   ```

2. **외부 접근 차단**
   - 방화벽에서 포트 9222 외부 접근 차단

3. **필요시에만 사용**
   - 일반 브라우징: 일반 Chrome 사용
   - IMS 스크래핑: CDP Chrome 사용

---

## Production 배포

### 서버 환경에서 설정

**Windows Server**:
```powershell
# Chrome 서비스로 등록
sc.exe create "ChromeCDP" binPath= "C:\Program Files\Google\Chrome\Application\chrome.exe --remote-debugging-port=9222 --headless" start= auto
```

**Docker (Linux)**:
```dockerfile
# Dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    chromium-browser

CMD ["chromium-browser", "--remote-debugging-port=9222", "--no-sandbox", "--headless"]
```

---

## 테스트

### 바로가기 생성 후 테스트

```bash
# 1. Chrome CDP 바로가기로 Chrome 실행

# 2. Playwright CDP 연결 테스트
python -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        print(f'Connected! Contexts: {len(browser.contexts)}')
        await browser.close()

asyncio.run(test())
"
```

**성공 시 출력**:
```
Connected! Contexts: 1
```

---

## 다음 단계

바로가기 생성 완료 후:

1. ✅ CDP 바로가기로 Chrome 실행
2. ✅ http://localhost:9222/json/version 접속 확인
3. ✅ IMS CDP Scraper 테스트 실행

```bash
python test_cdp_scraper.py
```
