# IMS Knowledge System - Complete Guide

## Overview

The IMS Knowledge System enables seamless integration between your company's IMS (Information Management System) and the AI-powered Knowledge Management System. Users can leverage existing Chrome SSO sessions to query IMS data and automatically generate knowledge articles.

## Architecture

```
User (Chrome Browser)
    ↓ (Already logged into IMS)
Chrome Cookie Extractor
    ↓ (Extract session cookies)
IMS SSO Service
    ↓ (Authenticated session)
IMS System APIs ←→ RAG Service
    ↓              ↓
Knowledge Article Service
    ↓
Knowledge Database
```

## Features

### ✅ Implemented Features

1. **Chrome SSO Integration**
   - Extract cookies from Chrome while browser is running
   - Works with Windows File Sharing API for locked database access
   - Cross-platform support (Windows, macOS, Linux)
   - Automatic cookie decryption (AES-256)

2. **IMS System Connection**
   - Automatic session validation
   - Multiple endpoint fallback for compatibility
   - Connection status monitoring
   - Session management (connect/disconnect/status)

3. **AI-Powered Knowledge Generation**
   - Hybrid RAG strategy (vector + graph search)
   - IMS data context integration
   - Automatic language detection
   - Multi-source synthesis (IMS + Knowledge Base)

4. **Automatic Knowledge Storage**
   - Auto-save as Knowledge Article
   - IMS source attribution
   - Tagged for easy retrieval
   - Multi-language support (ko/ja/en)

## API Endpoints

### 1. Connect to IMS System

**Endpoint:** `POST /api/v1/ims-sso/connect`

**Request:**
```json
{
  "ims_url": "https://ims.tmaxsoft.com",
  "chrome_profile": "Default",
  "validation_endpoint": "/api/v1/me"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "ims_url": "https://ims.tmaxsoft.com",
    "user_info": {
      "authenticated": true,
      "username": "john.doe"
    }
  }
}
```

**How it works:**
1. Extracts cookies from Chrome for `ims.tmaxsoft.com`
2. Creates authenticated `requests.Session`
3. Validates connection by calling IMS API
4. Returns session ID for subsequent requests

---

### 2. Check Connection Status

**Endpoint:** `GET /api/v1/ims-sso/status/{session_id}`

**Response:**
```json
{
  "status": "success",
  "data": {
    "is_connected": true,
    "ims_url": "https://ims.tmaxsoft.com",
    "user_info": { ... }
  }
}
```

---

### 3. Query AI with IMS Context

**Endpoint:** `POST /api/v1/ims-sso/query`

**Request:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "프로젝트 X의 최신 상태는?"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "response": "IMS 시스템의 정보를 바탕으로 답변드립니다...",
    "knowledge_id": "ka_abc123def456"
  },
  "meta": {
    "message": "IMS 시스템과 AI를 통해 지식이 생성되었습니다",
    "extra": {
      "ims_context_used": true,
      "sources_count": 3,
      "strategy": "hybrid"
    }
  }
}
```

**Processing Flow:**
1. **IMS Data Retrieval** (tries multiple endpoints):
   - `/api/v1/search?q={query}`
   - `/api/search?q={query}`
   - `/search?q={query}`
   - `/api/v1/knowledge/search?q={query}`
   - `/api/knowledge?q={query}`

2. **Context Enhancement:**
   - If IMS data found: Adds IMS context to query
   - Formats data for AI comprehension
   - Limits to top 5 results for efficiency

3. **AI Response Generation:**
   - Uses Hybrid RAG strategy (vector + graph)
   - Auto-detects language
   - Synthesizes IMS data + Knowledge Base

4. **Knowledge Article Creation:**
   - Auto-saves as Knowledge Article
   - Tags: `["IMS", "AI생성", "SSO"]`
   - Category: `technical`
   - Includes IMS source attribution

---

### 4. Disconnect Session

**Endpoint:** `POST /api/v1/ims-sso/disconnect/{session_id}`

**Response:**
```json
{
  "status": "success",
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## Frontend Usage

### UI Flow

1. Navigate to: `http://localhost:3000/knowledge`
2. Click sidebar: **"IMS 지식 서비스"**
3. Enter IMS URL: `https://ims.tmaxsoft.com`
4. Click: **"SSO로 연결"**
5. Wait for connection confirmation
6. Enter question in chat interface
7. View AI-generated response with IMS context
8. Knowledge automatically saved

### Component Structure

```typescript
// ContentTab.tsx
const ContentTab: React.FC = () => {
  // Connection State
  const [imsUrl, setImsUrl] = useState('https://ims.tmaxsoft.com');
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Chat State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  // Knowledge State
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);

  // Connect to IMS
  const connectToIMS = async () => {
    const response = await api.post('/ims-sso/connect', {
      ims_url: imsUrl,
      chrome_profile: 'Default',
      validation_endpoint: '/api/v1/me'
    });
    setSessionId(response.data.data.session_id);
    setIsConnected(true);
  };

  // Send query
  const sendMessage = async () => {
    const response = await api.post('/ims-sso/query', {
      session_id: sessionId,
      query: inputMessage
    });
    // Handle response...
  };
};
```

## Configuration

### Chrome Profile Detection

By default, uses `"Default"` Chrome profile. For other profiles:

```json
{
  "chrome_profile": "Profile 1"  // or "Profile 2", etc.
}
```

Profile locations:
- **Windows**: `%LOCALAPPDATA%\Google\Chrome\User Data\{Profile}`
- **macOS**: `~/Library/Application Support/Google/Chrome/{Profile}`
- **Linux**: `~/.config/google-chrome/{Profile}`

### IMS Endpoint Configuration

The system tries common IMS endpoints automatically. To add custom endpoints, modify:

```python
# app/api/routers/ims_sso.py (line 272)
search_endpoints = [
    "/api/v1/search",
    "/api/search",
    "/your/custom/endpoint"  # Add here
]
```

## Security Considerations

### Cookie Extraction

1. **Chrome Running Detection:**
   - Detects if Chrome is running
   - Uses Windows File Sharing API for safe access
   - No need to close Chrome

2. **Encryption:**
   - Cookies are AES-256 encrypted by Chrome
   - Automatic decryption using OS keychain
   - Windows: DPAPI, macOS: Keychain, Linux: Secret Service

3. **Session Management:**
   - Sessions stored in-memory (currently)
   - **Production:** Move to Redis/Database
   - Session timeout recommended

### Authentication Flow

```
Chrome Browser (User logged in)
    ↓ (Secure cookie extraction)
Backend Server (Encrypted cookies)
    ↓ (Decryption with OS key)
IMS System (Validated session)
    ↓ (Authenticated requests)
Knowledge Generation
```

## Error Handling

### Common Errors

1. **Connection Failed:**
```json
{
  "detail": "Cookie extraction failed: Chrome profile 'Profile X' not found"
}
```
**Solution:** Verify Chrome profile name

2. **Session Expired:**
```json
{
  "detail": "SSO 세션이 만료되었습니다. 다시 연결해주세요."
}
```
**Solution:** Reconnect to IMS system

3. **IMS Search Failed:**
```
IMS system search failed (continuing with RAG): Connection timeout
```
**Effect:** Falls back to RAG-only mode (still generates response)

## Performance Optimization

### Caching Strategy

**Session Cookies:**
- Cached after first extraction
- Reused for all requests in session
- Auto-refresh on expiration

**IMS Data:**
- No persistent cache (always fresh)
- 5-second timeout per endpoint
- Fail-fast on errors

### Concurrent Requests

- Multiple sessions supported
- Each session isolated
- No cross-session interference

## Production Deployment

### Required Changes

1. **Session Storage:**
```python
# Replace in-memory dict with Redis
import redis
redis_client = redis.Redis(host='localhost', port=6379)

# Store session
redis_client.setex(
    f"ims_sso:{session_id}",
    3600,  # 1 hour TTL
    pickle.dumps(sso_service)
)
```

2. **Environment Variables:**
```bash
IMS_DEFAULT_URL=https://ims.company.com
IMS_SESSION_TTL=3600
CHROME_PROFILE_PATH=/custom/path
```

3. **Monitoring:**
```python
# Add metrics
from prometheus_client import Counter, Histogram

ims_connections = Counter('ims_sso_connections_total', 'IMS SSO connections')
ims_query_duration = Histogram('ims_query_duration_seconds', 'IMS query duration')
```

## Testing

### Manual Testing

1. **Test Connection:**
```bash
curl -X POST http://localhost:8000/api/v1/ims-sso/connect \
  -H "Content-Type: application/json" \
  -d '{
    "ims_url": "https://ims.tmaxsoft.com",
    "chrome_profile": "Default"
  }'
```

2. **Test Query:**
```bash
curl -X POST http://localhost:8000/api/v1/ims-sso/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "YOUR_SESSION_ID",
    "query": "테스트 질문"
  }'
```

### Integration Tests

```python
# tests/test_ims_sso.py
async def test_ims_connection():
    response = await client.post("/api/v1/ims-sso/connect", json={
        "ims_url": "https://test-ims.com",
        "chrome_profile": "Default"
    })
    assert response.status_code == 200
    assert "session_id" in response.json()["data"]

async def test_ims_query():
    # Connect first
    connect_response = await client.post("/api/v1/ims-sso/connect", ...)
    session_id = connect_response.json()["data"]["session_id"]

    # Query
    query_response = await client.post("/api/v1/ims-sso/query", json={
        "session_id": session_id,
        "query": "테스트"
    })
    assert query_response.status_code == 200
    assert "response" in query_response.json()["data"]
```

## Troubleshooting

### Chrome Cookie Extraction Issues

**Problem:** `CookieDBLockedError` on Windows
**Solution:**
```python
# Install pywin32
pip install pywin32

# Verify installation
python -c "import win32file; print('OK')"
```

**Problem:** Profile not found
**Solution:**
```bash
# List Chrome profiles
ls -la ~/Library/Application\ Support/Google/Chrome/  # macOS
dir %LOCALAPPDATA%\Google\Chrome\User Data  # Windows
```

### IMS Connection Issues

**Problem:** All endpoints return 404
**Solution:** Verify IMS system URLs with your admin

**Problem:** Authentication fails with 401
**Solution:**
1. Verify Chrome is logged into IMS
2. Check cookie expiration
3. Try reconnecting

## Roadmap

### Planned Features

- [ ] Redis session storage
- [ ] Configurable IMS endpoints per organization
- [ ] Batch query support
- [ ] Knowledge article review workflow
- [ ] Usage analytics dashboard
- [ ] Multi-IMS system support
- [ ] Automated knowledge refresh

## Support

For issues or questions:
- **GitHub Issues:** https://github.com/your-repo/issues
- **Internal Wiki:** Link to your company wiki
- **Contact:** your-team@company.com
