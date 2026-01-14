# Security Code Review Report

**Review Date**: 2026-01-14
**Branch**: `feature/cpu-local-llm-stable`
**Reviewer**: Claude Code (Automated Security Analysis)
**Scope**: 95 modified files across backend and frontend
**Last Updated**: 2026-01-14 (Critical vulnerabilities fixed)

---

## Executive Summary

| Severity | Count | Status |
|----------|-------|--------|
| **Critical** | 3 | ✅ **FIXED** |
| **High** | 9 | Address Before Production |
| **Medium** | 3 | Plan Remediation |
| **Total** | 15 | - |

### Critical Vulnerabilities - All Fixed ✅

| # | Vulnerability | Status | Commit |
|---|--------------|--------|--------|
| 1 | Command Injection (Bash Tool) | ✅ Fixed | Whitelist + shell=False |
| 2 | OAuth CSRF (State Validation) | ✅ Fixed | Server-side state storage |
| 3 | Weak Token Encryption | ✅ Fixed | Fernet (AES-128-CBC) |

This security review identified **15 high-confidence vulnerabilities** across the following categories:
- Authentication/Authorization: 6 issues
- Injection: 3 issues
- Data Exposure: 6 issues
- Input Validation: 3 issues (1 critical overlap)

---

## Critical Vulnerabilities

### 1. Command Injection in Bash Tool ✅ FIXED

| Field | Value |
|-------|-------|
| **Confidence** | 10/10 |
| **Severity** | Critical |
| **File** | `app/api/agents/tools/bash.py` |
| **CWE** | CWE-78: OS Command Injection |
| **Status** | ✅ **FIXED** |

**Original Issue**:
The BashTool used shell execution with a blocklist approach that could be bypassed.

**Fix Applied**:
1. ✅ Changed from blocklist to whitelist approach (ALLOWED_COMMANDS set)
2. ✅ Changed to use subprocess without shell (prevents shell metacharacter attacks)
3. ✅ Added argument validation with BLOCKED_ARG_PATTERNS
4. ✅ Added special validation for git commands (read-only only)
5. ✅ Added path traversal protection

---

### 2. Missing OAuth State Parameter Validation (CSRF) ✅ FIXED

| Field | Value |
|-------|-------|
| **Confidence** | 10/10 |
| **Severity** | Critical |
| **File** | `kms-portal-ui/src/pages/OAuthCallbackPage.tsx` |
| **CWE** | CWE-352: Cross-Site Request Forgery |
| **Status** | ✅ **FIXED** |

**Original Issue**:
The OAuth callback extracted connection ID from state but never validated the random portion.

**Fix Applied**:
1. ✅ Backend: Added `_oauth_states` dictionary to store state tokens server-side
2. ✅ Backend: Added `_generate_oauth_state()` with cryptographically secure random token
3. ✅ Backend: Added `validate_oauth_state()` method with expiration (10 min)
4. ✅ Backend: Router now requires and validates state parameter
5. ✅ Frontend: OAuthCallbackPage now passes state to backend for validation
6. ✅ Frontend: Added state parameter requirement check

**Key Changes**:
- State tokens are now stored server-side with timestamps
- State tokens are single-use (deleted after validation)
- State tokens expire after 10 minutes
- Full state validation prevents CSRF attacks

---

### 3. Weak Token "Encryption" (Base64 Only) ✅ FIXED

| Field | Value |
|-------|-------|
| **Confidence** | 10/10 |
| **Severity** | Critical |
| **File** | `app/api/services/external_document_service.py` |
| **CWE** | CWE-327: Use of Broken Crypto Algorithm |
| **Status** | ✅ **FIXED** |

**Original Issue**:
OAuth tokens were "encrypted" using only Base64 encoding, providing zero security.

**Fix Applied**:
1. ✅ Implemented Fernet encryption (AES-128-CBC with HMAC authentication)
2. ✅ Added PBKDF2 key derivation with 100,000 iterations
3. ✅ Uses ENCRYPTION_MASTER_KEY and ENCRYPTION_SALT from environment
4. ✅ Added migration path for legacy base64-encoded tokens
5. ✅ Added cryptography>=41.0.0 to requirements

**Key Changes**:
```python
# Derives Fernet key using PBKDF2
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=cls._ENCRYPTION_SALT,
    iterations=100_000,  # OWASP recommended
)
```

**Security Properties**:
- AES-128-CBC encryption
- HMAC authentication (tamper detection)
- Secure key derivation with salt
- Tokens without encryption are rejected (not stored)

---

## High Severity Vulnerabilities

### 4. Server-Side Request Forgery (SSRF)

| Field | Value |
|-------|-------|
| **Confidence** | 10/10 |
| **Severity** | High |
| **File** | `app/api/services/web_content_service.py:379-401` |
| **CWE** | CWE-918: Server-Side Request Forgery |

**Description**:
The `fetch_url()` method accepts arbitrary URLs without validating for internal addresses or cloud metadata endpoints.

**Exploit Scenario**:
```bash
# Access cloud metadata
POST /api/v1/agents/fetch-url
{"url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}

# Scan internal network
POST /api/v1/agents/fetch-url
{"url": "http://192.168.1.1:9000/api/v1/admin/users"}
```

**Recommendation**:
```python
BLOCKED_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
]

def validate_url(url: str) -> bool:
    hostname = urlparse(url).hostname
    resolved_ip = socket.gethostbyname(hostname)
    return not any(ip_address(resolved_ip) in net for net in BLOCKED_NETWORKS)
```

---

### 5. Sensitive Credentials in localStorage

| Field | Value |
|-------|-------|
| **Confidence** | 9/10 |
| **Severity** | High |
| **File** | `kms-portal-ui/src/store/externalConnectorsStore.ts:1202-1223` |
| **CWE** | CWE-922: Insecure Storage of Sensitive Information |

**Description**:
OAuth tokens (accessToken, refreshToken) are persisted to localStorage, accessible via XSS.

**Recommendation**:
- Store tokens server-side only
- Use HttpOnly cookies for session management
- If client storage required, use sessionStorage with encryption

---

### 6. Unsalted SHA256 Password Hashing

| Field | Value |
|-------|-------|
| **Confidence** | 9/10 |
| **Severity** | High |
| **File** | `app/api/core/deps.py:1094, 1116, 1147` |
| **CWE** | CWE-916: Use of Password Hash With Insufficient Salt |

**Description**:
Passwords are hashed with plain SHA256 without salt, vulnerable to rainbow table attacks.

**Recommendation**:
```python
import bcrypt

# Hashing
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# Verification
bcrypt.checkpw(password.encode(), stored_hash.encode())
```

---

### 7. SQL Injection via String Interpolation

| Field | Value |
|-------|-------|
| **Confidence** | 9/10 |
| **Severity** | High |
| **File** | `app/api/agents/tools/ims_search.py:197, 285` |
| **CWE** | CWE-89: SQL Injection |

**Description**:
LIMIT clause uses f-string interpolation instead of parameterized query.

**Vulnerable Code**:
```python
sql = f"""
    SELECT ... FROM ims_issues
    WHERE {where_clause}
    LIMIT {limit}  # String interpolation
"""
```

**Recommendation**:
```python
sql = "SELECT ... FROM ims_issues WHERE ... LIMIT $N"
params.append(int(limit))
```

---

### 8. Missing Authorization on Connection Endpoints

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | High |
| **File** | `app/api/routers/external_connection.py:146-182` |
| **CWE** | CWE-862: Missing Authorization |

**Description**:
Endpoints access connections by ID without verifying user ownership.

**Recommendation**:
```python
@router.get("/{connection_id}")
async def get_connection(connection_id: str, user=Depends(get_current_user)):
    connection = service.get_connection(connection_id)
    if connection.user_id != user.id:
        raise HTTPException(403, "Access denied")
```

---

### 9. OAuth Code Exchange Without Ownership Verification

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | High |
| **File** | `app/api/routers/external_connection.py:211-248` |
| **CWE** | CWE-306: Missing Authentication |

**Description**:
OAuth callback doesn't verify that the user completing the flow is the same user who initiated it.

---

### 10. Sensitive Tokens Logged

| Field | Value |
|-------|-------|
| **Confidence** | 9/10 |
| **Severity** | High |
| **File** | `app/api/connectors/onenote_connector.py:50, 76` |
| **CWE** | CWE-532: Information Exposure Through Log Files |

**Description**:
Client ID and OAuth metadata are logged via print statements.

**Recommendation**:
- Remove all print statements with sensitive data
- Use structured logging with log level filtering

---

### 11. Stored XSS via Markdown Links

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | High |
| **File** | `kms-portal-ui/src/components/AgentChat/MessageContent.tsx:74-77` |
| **CWE** | CWE-79: Cross-site Scripting |

**Description**:
Markdown link renderer doesn't sanitize `href` for `javascript:` URIs.

**Recommendation**:
```tsx
import rehypeSanitize from 'rehype-sanitize';

<ReactMarkdown rehypePlugins={[rehypeSanitize]}>
```

---

### 12. Decrypted Tokens Logged

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | High |
| **File** | `app/api/services/external_document_service.py:414-416` |
| **CWE** | CWE-532: Information Exposure Through Log Files |

---

## Medium Severity Vulnerabilities

### 13. Verification Codes Logged

| Field | Value |
|-------|-------|
| **Confidence** | 9/10 |
| **Severity** | Medium |
| **File** | `app/api/core/deps.py:1225-1229` |

---

### 14. Database Credentials in DSN String

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | Medium |
| **File** | `app/api/core/deps.py:1511-1512` |

**Recommendation**:
```python
self._pool = await asyncpg.create_pool(
    host=settings.POSTGRES_HOST,
    password=settings.POSTGRES_PASSWORD,  # Not in string
    ...
)
```

---

### 15. HTTP Header Injection in Content-Disposition

| Field | Value |
|-------|-------|
| **Confidence** | 8/10 |
| **Severity** | Medium |
| **File** | `app/api/routers/images.py:219-221` |

**Recommendation**:
```python
safe_filename = re.sub(r'[^\w\-.]', '_', image_id)
```

---

## Remediation Priority Matrix

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| **P0** | Command Injection (Bash Tool) | High | Critical |
| **P0** | Weak Token Encryption | Medium | Critical |
| **P0** | OAuth CSRF | Medium | Critical |
| **P1** | SSRF in URL Fetch | Medium | High |
| **P1** | Unsalted Password Hashing | Low | High |
| **P1** | localStorage Token Storage | Medium | High |
| **P2** | SQL Injection (LIMIT) | Low | High |
| **P2** | Missing Authorization | Medium | High |
| **P2** | Log Data Exposure | Low | Medium |

---

## Immediate Actions Required

### ✅ Completed (Critical)
1. ~~**Disable or sandbox Bash Tool**~~ ✅ Fixed with whitelist + shell=False
2. ~~**Implement proper AES/Fernet encryption**~~ ✅ Fixed with PBKDF2 + Fernet
3. ~~**Add OAuth state validation**~~ ✅ Fixed with server-side storage

### Remaining (High Priority)
4. **Add SSRF protection** with IP blocklist
5. **Replace SHA256 with bcrypt** for password hashing
6. **Remove credentials from localStorage** - use server-side storage

---

## Appendix: Files Reviewed

### Backend (Python)
- `app/api/agents/tools/bash.py`
- `app/api/agents/tools/ims_search.py`
- `app/api/services/external_document_service.py`
- `app/api/services/web_content_service.py`
- `app/api/routers/external_connection.py`
- `app/api/routers/images.py`
- `app/api/connectors/*.py` (5 connectors)
- `app/api/core/deps.py`
- `app/api/core/config.py`

### Frontend (TypeScript)
- `kms-portal-ui/src/pages/OAuthCallbackPage.tsx`
- `kms-portal-ui/src/store/externalConnectorsStore.ts`
- `kms-portal-ui/src/components/AgentChat/MessageContent.tsx`
- `kms-portal-ui/src/components/AgentChat/hooks/useUrlAttachment.ts`

---

*Report generated by Claude Code Security Analysis*
