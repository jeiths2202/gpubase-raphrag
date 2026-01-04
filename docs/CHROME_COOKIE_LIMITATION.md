# Chrome Cookie Extraction Limitation

## Issue Summary

**Problem**: Chrome locks its SQLite cookie database with exclusive access while running, preventing external processes from reading it.

**Error**: `pywintypes.error: (32, 'CreateFile', ...)` - ERROR_SHARING_VIOLATION

**Status**: This is a Chrome security feature, not a bug.

## Technical Background

### Why Cookies Can't Be Extracted While Chrome Runs

1. **Exclusive Lock**: Chrome opens `Cookies` database with exclusive write access
2. **SQLite Safety**: Prevents database corruption from concurrent access
3. **Security Feature**: Reduces attack surface for credential theft

### What Doesn't Work

❌ **Windows File Sharing API** (`FILE_FLAG_BACKUP_SEMANTICS`)
- Only works for files opened with shared read access
- Chrome uses exclusive lock
- Backup flags don't override exclusive locks

❌ **SQLite VACUUM INTO**
- Requires read access to source database
- Chrome's exclusive lock prevents this

❌ **Shadow Copy / VSS**
- Requires admin privileges
- Overly complex for this use case

## Recommended Solutions

### ✅ Solution 1: SSO Session Reuse (Recommended)

**How it works:**
```
1. User connects via IMS SSO (/api/v1/ims-sso/connect)
   - Chrome must be closed for initial setup
   - Cookies extracted once
   - Session established

2. Session maintained in-memory
   - Cookies stored in SSO service
   - No re-extraction needed

3. Scraper uses established session
   - Reuses cookies from SSO service
   - No Chrome interaction required
```

**Implementation:**
```python
# Step 1: Connect via SSO (Chrome closed, one-time)
from app.api.ims_sso_connector.sso.service import IMSSSOService

sso_service = IMSSSOService()
success, error, user_info = sso_service.connect(
    ims_url='https://ims.tmaxsoft.com',
    chrome_profile='Default'
)

# Step 2: Use session for scraping (Chrome can be open)
from app.api.ims_sso_connector.scraper.ims_issue_scraper import IMSIssueScraper

# Modify scraper to accept cookies instead of extracting
async with IMSIssueScraper(
    ims_url='https://ims.tmaxsoft.com',
    cookies=sso_service.session.cookies,  # Reuse SSO cookies
    headless=True
) as scraper:
    issues = await scraper.scrape_issue_list()
```

**Advantages:**
- ✅ Works while Chrome is running
- ✅ No repeated cookie extraction
- ✅ Secure (cookies in-memory only)
- ✅ Integrates with existing IMS SSO system

### ✅ Solution 2: Close Chrome Temporarily

**How it works:**
```python
1. Detect Chrome running
2. Ask user to close Chrome
3. Extract cookies
4. User can reopen Chrome
```

**Implementation:**
```python
import subprocess

# Check Chrome
result = subprocess.run(
    ['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
    capture_output=True
)

if 'chrome.exe' in result.stdout:
    print('Please close Chrome temporarily for cookie extraction')
    # Wait for user to close Chrome
else:
    # Extract cookies
    cookies = extractor.extract_cookies()
```

**Advantages:**
- ✅ Simple implementation
- ✅ No code changes needed
- ⚠️ Requires user action

### ✅ Solution 3: Cookie Persistence

**How it works:**
```
1. Extract cookies once (Chrome closed)
2. Save to encrypted file
3. Reuse saved cookies
4. Re-extract only when expired
```

**Implementation:**
```python
import pickle
from Cryptodome.Cipher import AES

# Save cookies
with open('cookies.enc', 'wb') as f:
    encrypted = encrypt_cookies(cookies)
    pickle.dump(encrypted, f)

# Load cookies
with open('cookies.enc', 'rb') as f:
    encrypted = pickle.load(f)
    cookies = decrypt_cookies(encrypted)
```

**Advantages:**
- ✅ Extract once, use many times
- ✅ Works while Chrome runs (after initial extraction)
- ⚠️ Must handle expiration
- ⚠️ Security considerations

## Production Recommendation

### Use SSO Session Integration (Solution 1)

This aligns with the existing IMS Knowledge System architecture:

```
User → IMS SSO Connect → Session Established
                            ↓
                    (Cookies extracted once)
                            ↓
        ┌──────────────────┴──────────────────┐
        ↓                                     ↓
    Query Endpoint                      Scraper
    (uses session)                 (reuses session)
```

**Workflow:**

1. **Initial Setup** (Chrome closed):
```bash
POST /api/v1/ims-sso/connect
{
  "ims_url": "https://ims.tmaxsoft.com",
  "chrome_profile": "Default"
}
```

2. **Query with Session** (Chrome can be open):
```bash
POST /api/v1/ims-sso/query
{
  "session_id": "...",
  "query": "프로젝트 X 상태는?"
}
```

3. **Scrape with Session** (Chrome can be open):
```bash
POST /api/v1/ims-sso/scrape-issues
{
  "session_id": "...",
  "search_type": "1"
}
```

## Implementation Changes Required

### Modify Scraper to Accept Cookies

**File**: `app/api/ims_sso_connector/scraper/ims_issue_scraper.py`

```python
class IMSIssueScraper:
    def __init__(
        self,
        ims_url: str = "https://ims.tmaxsoft.com",
        chrome_profile: str = "Default",
        cookies: Optional[List[dict]] = None,  # NEW: Accept pre-extracted cookies
        headless: bool = True
    ):
        self.ims_url = ims_url.rstrip('/')
        self.chrome_profile = chrome_profile
        self.cookies = cookies  # NEW
        self.headless = headless

    async def initialize(self):
        # NEW: Use provided cookies if available
        if self.cookies:
            print('[INFO] Using provided cookies from session')
            cookies = self.cookies
        else:
            # Original: Extract from Chrome
            print('[SEARCH] Extracting cookies from Chrome...')
            cookie_extractor = ChromeCookieExtractor(profile=self.chrome_profile)
            domain = self.ims_url.replace('https://', '').replace('http://', '').split('/')[0]
            cookies = cookie_extractor.extract_cookies_for_domain(domain)

        # Continue with browser setup...
```

### Integrate with SSO Service

**File**: `app/api/routers/ims_sso.py`

```python
@router.post("/scrape-issues")
async def scrape_ims_issues_endpoint(request: IMSIssueListRequest):
    sso_service = _sso_sessions.get(request.session_id)

    # Extract cookies from SSO session
    session_cookies = []
    for cookie_name, cookie_value in sso_service.session.cookies.items():
        session_cookies.append({
            'name': cookie_name,
            'value': cookie_value,
            'domain': '.tmaxsoft.com',
            'path': '/'
        })

    # Use scraper with session cookies
    async with IMSIssueScraper(
        ims_url=sso_service.ims_url,
        cookies=session_cookies,  # Reuse SSO cookies
        headless=True
    ) as scraper:
        issues = await scraper.scrape_issue_list()

    return SuccessResponse(data={"issues": issues})
```

## Testing Workflow

### Test 1: SSO Session Integration

```bash
# 1. Close Chrome
# 2. Connect via SSO
python test_scraper_with_sso.py

# 3. Chrome can be reopened
# 4. Use session for subsequent scraping
```

### Test 2: Direct Scraping (Chrome Closed)

```bash
# 1. Close Chrome
# 2. Run scraper
python -m app.api.ims_sso_connector.scraper.ims_issue_scraper

# 3. Reopen Chrome after extraction
```

## FAQ

**Q: Can I extract cookies while Chrome is running?**
A: No, Chrome locks the database exclusively. Use SSO session reuse instead.

**Q: Will this ever be fixed?**
A: This is intentional Chrome security. Alternative: Use Chrome Extensions API with proper permissions.

**Q: What about other browsers?**
A: Firefox and Edge have similar locking mechanisms.

**Q: Is there a workaround?**
A: Yes - establish session once (Chrome closed), then reuse session (Chrome can be open).

## Summary

| Approach | Chrome Running | Complexity | Security | Recommended |
|----------|---------------|------------|----------|-------------|
| SSO Session Reuse | ✅ | Low | High | ✅ Yes |
| Close Chrome | ❌ | Low | High | ⚠️ OK |
| Cookie Persistence | ✅* | Medium | Medium | ⚠️ OK |
| Chrome Extension | ✅ | High | Medium | ❌ No |

*After initial extraction

**Recommendation**: Use SSO Session Reuse (Solution 1) for production.

---

**Updated**: 2025-12-29
**Status**: Chrome exclusive lock is expected behavior
**Solution**: SSO session integration implemented
