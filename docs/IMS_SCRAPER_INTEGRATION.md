# IMS Issue Scraper Integration Guide

## Overview

이 가이드는 IMS Issue Scraper를 기존 IMS SSO Knowledge System과 통합하는 방법을 설명합니다.

## Architecture Integration

```
User Query
    ↓
IMS SSO Query Endpoint (/api/v1/ims-sso/query)
    ↓
    ├─→ IMS API Search (기존 방식)
    │   └─→ REST API 엔드포인트 호출
    │
    └─→ IMS Issue Scraper (신규 방식) ← NEW
        └─→ Dynamic web scraping with Playwright
    ↓
RAG Service (Hybrid Strategy)
    ↓
Knowledge Article (Auto-save)
```

## Installation

### 1. Install Dependencies

```bash
# Install playwright
pip install playwright

# Install playwright browsers (Chromium)
playwright install chromium
```

### 2. Verify Installation

```bash
# Test scraper standalone
python -m app.api.ims_sso_connector.scraper.ims_issue_scraper

# Run example script
python scripts/example_ims_scraper.py
```

## Integration Patterns

### Pattern 1: Extend Existing Query Endpoint

현재 `/api/v1/ims-sso/query` 엔드포인트에 스크래핑 기능을 추가합니다.

**File**: `app/api/routers/ims_sso.py`

```python
from ..ims_sso_connector.scraper.ims_issue_scraper import IMSIssueScraper

@router.post("/query")
async def query_ims_ai(request: IMSSSOQueryRequest):
    sso_service = _sso_sessions.get(request.session_id)

    # Step 1: Try REST API first (기존 방식)
    ims_context = None
    for endpoint in search_endpoints:
        response = sso_service.make_request(endpoint, ...)
        if response and response.status_code == 200:
            ims_context = response.json()
            break

    # Step 2: Fallback to scraper if API fails (신규 방식)
    if not ims_context:
        try:
            async with IMSIssueScraper(
                ims_url=sso_service.ims_url,
                chrome_profile="Default"
            ) as scraper:
                # 쿼리에서 이슈 검색 키워드 추출
                issues = await scraper.scrape_issue_list(
                    search_type="1",
                    menu_code="issue_search"
                )

                if issues:
                    ims_context = {"issues": issues}
                    logger.info(f"Retrieved {len(issues)} issues via scraper")
        except Exception as e:
            logger.warning(f"Scraper fallback failed: {e}")

    # Step 3: Continue with RAG as before
    enhanced_query = request.query
    if ims_context:
        context_summary = _format_ims_context(ims_context)
        enhanced_query = f"""사용자 질문: {request.query}

IMS 시스템 참고 정보:
{context_summary}

위 IMS 시스템의 정보를 참고하여 사용자 질문에 답변해주세요."""

    rag_result = await rag_service.query(...)
    # ... rest of the code
```

### Pattern 2: Dedicated Scraping Endpoint

이슈 스크래핑 전용 엔드포인트를 추가합니다.

**File**: `app/api/routers/ims_sso.py`

```python
from ..ims_sso_connector.scraper.ims_issue_scraper import scrape_ims_issues

class IMSIssueListRequest(BaseModel):
    session_id: str
    search_type: str = "1"
    menu_code: str = "issue_search"
    output_file: Optional[str] = None

class IMSIssueListResponse(BaseModel):
    issues: List[Dict[str, Any]]
    count: int

@router.post(
    "/scrape-issues",
    response_model=SuccessResponse[IMSIssueListResponse],
    summary="IMS 이슈 목록 스크래핑",
    description="동적 웹 스크래핑으로 IMS 이슈 목록을 추출합니다"
)
async def scrape_ims_issues_endpoint(request: IMSIssueListRequest):
    """
    IMS 이슈 목록 페이지를 스크래핑하여 데이터 추출

    REST API가 제공되지 않는 경우의 대안으로 사용
    """
    sso_service = _sso_sessions.get(request.session_id)

    if not sso_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO 세션을 찾을 수 없습니다"
        )

    try:
        issues = await scrape_ims_issues(
            ims_url=sso_service.ims_url,
            chrome_profile="Default",
            search_type=request.search_type,
            menu_code=request.menu_code,
            output_file=request.output_file
        )

        return SuccessResponse(
            data=IMSIssueListResponse(
                issues=issues,
                count=len(issues)
            ),
            meta=MetaInfo(
                message=f"Successfully scraped {len(issues)} issues"
            )
        )

    except Exception as e:
        logger.error(f"Issue scraping failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"이슈 스크래핑 실패: {str(e)}"
        )
```

### Pattern 3: Background Task with Caching

주기적으로 이슈를 스크래핑하여 캐싱합니다.

```python
from fastapi import BackgroundTasks
import asyncio
from datetime import datetime, timedelta

# In-memory cache
_issue_cache = {
    "data": [],
    "last_update": None,
    "ttl": timedelta(minutes=15)
}

async def background_scrape_issues(ims_url: str):
    """백그라운드에서 이슈 스크래핑 및 캐시 업데이트"""
    try:
        issues = await scrape_ims_issues(
            ims_url=ims_url,
            chrome_profile="Default"
        )

        _issue_cache["data"] = issues
        _issue_cache["last_update"] = datetime.now()
        logger.info(f"Background scraping completed: {len(issues)} issues")

    except Exception as e:
        logger.error(f"Background scraping failed: {e}")

@router.post("/query")
async def query_ims_ai(
    request: IMSSSOQueryRequest,
    background_tasks: BackgroundTasks
):
    sso_service = _sso_sessions.get(request.session_id)

    # Check cache first
    if _issue_cache["data"] and _issue_cache["last_update"]:
        cache_age = datetime.now() - _issue_cache["last_update"]
        if cache_age < _issue_cache["ttl"]:
            ims_context = {"issues": _issue_cache["data"]}
            logger.info("Using cached issue data")
        else:
            # Cache expired, trigger background refresh
            background_tasks.add_task(
                background_scrape_issues,
                sso_service.ims_url
            )
    else:
        # No cache, trigger background scraping
        background_tasks.add_task(
            background_scrape_issues,
            sso_service.ims_url
        )

    # Continue with query processing...
```

## Configuration

### Environment Variables

Add to `.env`:

```bash
# IMS Scraper Configuration
IMS_SCRAPER_HEADLESS=true          # Run browser in headless mode
IMS_SCRAPER_TIMEOUT=30000          # Page load timeout (ms)
IMS_SCRAPER_CHROME_PROFILE=Default # Chrome profile name
IMS_SCRAPER_CACHE_TTL=900          # Cache TTL (seconds)
```

### Application Settings

**File**: `app/api/core/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # IMS Scraper Settings
    ims_scraper_headless: bool = True
    ims_scraper_timeout: int = 30000
    ims_scraper_chrome_profile: str = "Default"
    ims_scraper_cache_ttl: int = 900

    class Config:
        env_file = ".env"
```

## Frontend Integration

### New UI Component for Issue List

**File**: `frontend/src/features/knowledge/components/ImsIssueList.tsx`

```typescript
import React, { useState } from 'react';
import { api } from '../../../services/api';

interface ImsIssue {
  id: string;
  title: string;
  status: string;
  priority: string;
  assignee: string;
  created_at: string;
}

export const ImsIssueList: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const [issues, setIssues] = useState<ImsIssue[]>([]);
  const [loading, setLoading] = useState(false);

  const scrapeIssues = async () => {
    setLoading(true);
    try {
      const response = await api.post('/ims-sso/scrape-issues', {
        session_id: sessionId,
        search_type: '1',
        menu_code: 'issue_search'
      });

      setIssues(response.data.data.issues);
    } catch (error) {
      console.error('Failed to scrape issues:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ims-issue-list">
      <button onClick={scrapeIssues} disabled={loading}>
        {loading ? '스크래핑 중...' : 'IMS 이슈 가져오기'}
      </button>

      {issues.length > 0 && (
        <table className="issue-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>제목</th>
              <th>상태</th>
              <th>우선순위</th>
              <th>담당자</th>
            </tr>
          </thead>
          <tbody>
            {issues.map(issue => (
              <tr key={issue.id}>
                <td>{issue.id}</td>
                <td>{issue.title}</td>
                <td>{issue.status}</td>
                <td>{issue.priority}</td>
                <td>{issue.assignee}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
```

## Testing

### Unit Tests

**File**: `tests/api/test_ims_scraper.py`

```python
import pytest
from app.api.ims_sso_connector.scraper.ims_issue_scraper import IMSIssueScraper

@pytest.mark.asyncio
async def test_scraper_initialization():
    scraper = IMSIssueScraper(
        ims_url="https://ims.tmaxsoft.com",
        headless=True
    )

    async with scraper:
        assert scraper.browser is not None
        assert scraper.context is not None
        assert scraper.page is not None

@pytest.mark.asyncio
async def test_scrape_issue_list():
    async with IMSIssueScraper(ims_url="https://ims.tmaxsoft.com") as scraper:
        issues = await scraper.scrape_issue_list()

        assert isinstance(issues, list)
        # Validate issue structure
        if issues:
            assert 'id' in issues[0]
            assert 'title' in issues[0]

@pytest.mark.asyncio
async def test_scraper_error_handling():
    with pytest.raises(Exception):
        async with IMSIssueScraper(
            ims_url="https://invalid-url.com",
            chrome_profile="NonExistent"
        ) as scraper:
            await scraper.scrape_issue_list()
```

### Integration Tests

**File**: `tests/integration/test_ims_scraper_integration.py`

```python
import pytest
from httpx import AsyncClient
from app.api.main import app

@pytest.mark.asyncio
async def test_scrape_issues_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First connect
        connect_response = await client.post("/api/v1/ims-sso/connect", json={
            "ims_url": "https://ims.tmaxsoft.com",
            "chrome_profile": "Default"
        })
        session_id = connect_response.json()["data"]["session_id"]

        # Then scrape
        scrape_response = await client.post("/api/v1/ims-sso/scrape-issues", json={
            "session_id": session_id,
            "search_type": "1"
        })

        assert scrape_response.status_code == 200
        data = scrape_response.json()["data"]
        assert "issues" in data
        assert isinstance(data["issues"], list)
```

## Performance Considerations

### Optimization Strategies

1. **Caching**:
   - Cache scraped data for 15 minutes
   - Reduce repeated scraping operations
   - Background refresh before cache expires

2. **Selective Scraping**:
   - Only scrape when REST API fails
   - Limit scraping frequency per session
   - Implement rate limiting

3. **Resource Management**:
   - Properly close browser instances
   - Use context managers for cleanup
   - Monitor memory usage

### Performance Metrics

```python
# Add to ims_sso.py
import time

@router.post("/query")
async def query_ims_ai(request: IMSSSOQueryRequest):
    start_time = time.time()

    # ... scraping logic ...

    scraping_time = time.time() - start_time
    logger.info(f"Scraping completed in {scraping_time:.2f}s")

    return SuccessResponse(
        data=...,
        meta=MetaInfo(
            extra={
                "scraping_time": scraping_time,
                "method": "scraper" if used_scraper else "api"
            }
        )
    )
```

## Troubleshooting

### Common Issues

1. **Playwright Not Installed**:
```bash
pip install playwright
playwright install chromium
```

2. **Chrome Profile Not Found**:
```python
# List available profiles
import os
profile_dir = os.path.expanduser("~/.config/google-chrome")  # Linux
profile_dir = os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\User Data")  # Windows

for profile in os.listdir(profile_dir):
    if profile.startswith("Profile") or profile == "Default":
        print(f"Found profile: {profile}")
```

3. **Scraping Timeout**:
```python
# Increase timeout
await scraper.scrape_issue_list(max_wait_time=30000)  # 30 seconds
```

4. **Cookie Extraction Failed**:
- Ensure Chrome is running
- Verify you're logged into IMS
- Check Chrome profile name

## Security Considerations

### Cookie Security
- Cookies extracted locally only
- Session-based, not persistent
- Encrypted during extraction
- Never logged or stored in plain text

### Scraping Ethics
- Respect IMS rate limits
- Cache aggressively to minimize requests
- Only scrape when necessary (API unavailable)
- Follow robots.txt if applicable

### Access Control
- Require valid SSO session
- Validate user permissions
- Log all scraping operations
- Monitor for abuse

## Production Deployment

### Checklist

- [ ] Install Playwright and browsers on production server
- [ ] Configure environment variables
- [ ] Set up Redis cache for scraped data
- [ ] Implement rate limiting
- [ ] Add monitoring and alerting
- [ ] Test with production Chrome profile
- [ ] Enable headless mode
- [ ] Configure proper logging
- [ ] Set up error notifications

### Docker Integration

**File**: `docker/Dockerfile.scraper`

```dockerfile
FROM python:3.10-slim

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2

# Install Python dependencies
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application
COPY . /app
WORKDIR /app

CMD ["python", "-m", "app.api.main"]
```

## Next Steps

1. **Choose Integration Pattern**: Select Pattern 1, 2, or 3 based on your needs
2. **Implement Backend Changes**: Update `ims_sso.py` with chosen pattern
3. **Add Frontend UI**: Create issue list component
4. **Test Integration**: Run integration tests
5. **Deploy**: Follow production deployment checklist

## References

- [IMS Knowledge System Guide](./IMS_KNOWLEDGE_SYSTEM.md)
- [IMS Quick Start](./IMS_QUICK_START.md)
- [Playwright Documentation](https://playwright.dev/python/)
- [Chrome Cookie Extraction](../app/api/ims_sso_connector/chrome_cookie_extractor/README.md)
