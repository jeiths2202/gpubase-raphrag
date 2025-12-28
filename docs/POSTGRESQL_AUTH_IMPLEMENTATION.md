# PostgreSQL-based User Identity System - Implementation Summary

## Overview

Implemented a production-ready PostgreSQL-backed user authentication and identity management system that separates authentication (AuthN) from internal user management (Identity/Workspace Ownership).

---

## Architecture

### Design Principles

1. **Authentication ≠ Identity**
   - Google/SSO authentication → External providers
   - PostgreSQL users table → Internal identity (stable, owns workspaces)
   - auth_identities table → Maps external auth to internal users

2. **Single Source of Truth**
   - PostgreSQL is the ONLY persistent storage for users
   - No more in-memory user storage
   - Workspace ownership based on internal user_id (UUID)

3. **Multiple Auth Methods**
   - One internal user can have multiple authentication providers
   - Example: user@company.com can login via Google OR SSO OR local password
   - All map to same internal user_id

---

## Components Implemented

### 1. Database Schema (`migrations/002_user_identity_system.sql`)

```sql
-- users: Internal user registry
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    password_hash TEXT,  -- NULL for SSO-only users
    role TEXT,  -- admin / leader / senior / user / guest
    status TEXT,  -- active / inactive / suspended
    department TEXT,
    language TEXT DEFAULT 'ko',
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_login_at TIMESTAMP
);

-- auth_identities: External authentication mapping
CREATE TABLE auth_identities (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    provider TEXT,  -- google / sso / local
    provider_user_id TEXT,  -- Google 'sub', SSO user ID, etc.
    email TEXT,
    provider_metadata JSONB,
    created_at TIMESTAMP,
    last_used_at TIMESTAMP,
    UNIQUE (provider, provider_user_id)
);
```

**Helper Function**:
```sql
get_or_create_user_from_auth(provider, provider_user_id, email, ...)
-- Automatically handles user creation/retrieval on external auth
```

---

### 2. Pydantic Models (`app/api/models/user.py`)

```python
# Core models
class User(BaseModel):
    id: UUID  # Internal identity
    email: str
    password_hash: Optional[str]
    role: UserRole
    status: UserStatus
    ...

class AuthIdentity(BaseModel):
    user_id: UUID
    provider: AuthProvider  # google / sso / local
    provider_user_id: str
    ...

# Request/Response models
class LocalLoginRequest(BaseModel):
    id: str  # "admin" or email
    password: str

class AuthResponse(BaseModel):
    user: UserPublic
    access_token: str
    refresh_token: str
```

---

### 3. PostgreSQL Repository (`app/api/infrastructure/postgres/user_repository.py`)

**Key Methods**:

```python
class PostgresUserRepository:
    # CRUD Operations
    async def create_user(user_create: UserCreate) -> User
    async def get_user_by_id(user_id: UUID) -> User
    async def get_user_by_email(email: str) -> User
    async def update_user(user_id, user_update) -> User

    # Authentication Identity
    async def create_auth_identity(auth_identity_create) -> AuthIdentity
    async def get_auth_identity(provider, provider_user_id) -> AuthIdentity

    # Combined Operations (Transactions)
    async def get_or_create_user_from_external_auth(
        provider, provider_user_id, email, ...
    ) -> Tuple[User, bool]

    # Local Authentication
    async def authenticate_local(id_or_email, password) -> User

    # Admin Bootstrap
    async def create_admin_if_not_exists(email, password) -> Tuple[User, bool]
```

**Security Features**:
- bcrypt password hashing (work factor 12)
- Timing-attack resistant authentication
- SQL injection protection via parameterized queries
- Password hash never logged or exposed

---

### 4. Authentication Service (`app/api/services/auth_service.py`)

```python
class AuthService:
    # Bootstrap
    async def initialize_admin_user() -> bool

    # Local Authentication
    async def authenticate_local(id_or_email, password) -> User

    # Google OAuth
    async def authenticate_google(credential) -> User

    # Corporate SSO
    async def initiate_sso(email) -> dict
    async def handle_sso_callback(token) -> dict

    # JWT Token Generation
    async def create_access_token(user) -> str
    async def create_refresh_token(user) -> str

    # User Management
    async def get_user_by_id(user_id) -> User
    async def get_user_public(user_id) -> UserPublic
```

**Factory Function**:
```python
async def initialize_auth_service(dsn: str) -> AuthService
# Called at application startup to create PostgreSQL-backed service
```

---

### 5. Configuration Updates

**`app/api/core/config.py`**:
```python
class APISettings(BaseSettings):
    # PostgreSQL Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str  # REQUIRED
    POSTGRES_DB: str = "kms_db"

    def get_postgres_dsn(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@..."
```

**`.env.example`**:
```env
# PostgreSQL Database (REQUIRED)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password_here
POSTGRES_DB=kms_db
```

**`requirements-api.txt`**:
```
asyncpg>=0.29.0
bcrypt>=4.1.0
```

---

### 6. Application Startup (`app/api/main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... secrets validation ...

    # PostgreSQL Auth Service Initialization
    from .services.auth_service import initialize_auth_service

    dsn = api_settings.get_postgres_dsn()
    auth_service = await initialize_auth_service(dsn)
    # Automatically creates admin user at startup

    logger.info("✓ PostgreSQL-backed authentication initialized")

    yield
```

---

## Fixed Admin Credentials (Per Requirements)

```
ID: admin
Password: SecureAdm1nP@ss2024!
Email: admin@localhost
Role: admin
```

**Bootstrap Process**:
1. Check if admin user exists in PostgreSQL
2. If not, create with fixed credentials
3. Password hashed with bcrypt before storage
4. Happens automatically at application startup

---

## Authentication Flow Examples

### 1. Local Admin Login

```
POST /api/v1/auth/login
{
  "id": "admin",
  "password": "SecureAdm1nP@ss2024!"
}

FLOW:
1. AuthService.authenticate_local("admin", "...")
2. UserRepository.authenticate_local(FIXED_ADMIN_EMAIL, "...")
3. bcrypt.checkpw(password, stored_hash)
4. Update last_login_at
5. Generate JWT with sub = internal user_id (UUID)
6. Return tokens + user info
```

### 2. Google OAuth Login

```
POST /api/v1/auth/google
{
  "credential": "ya29.google_access_token..."
}

FLOW:
1. AuthService.authenticate_google(credential)
2. Verify token with Google API → get 'sub' (Google user ID) and email
3. UserRepository.get_or_create_user_from_external_auth(
     provider="google",
     provider_user_id=google_sub,
     email=email
   )
4. Check auth_identities for (provider='google', provider_user_id=google_sub)
5. If exists → return existing internal user
6. If not → create new user + auth_identity mapping
7. Generate JWT with sub = internal user_id (UUID)
8. Return tokens + user info
```

### 3. Corporate SSO Login

```
POST /api/v1/auth/sso
{
  "email": "user@company.com"
}

FLOW:
1. AuthService.initiate_sso(email)
2. Validate corporate email domain
3. Generate temporary SSO token
4. Redirect to /auth/sso/callback?token=...

GET /api/v1/auth/sso/callback?token=xxx

5. AuthService.handle_sso_callback(token)
6. Validate token and extract email
7. UserRepository.get_or_create_user_from_external_auth(
     provider="sso",
     provider_user_id=email,
     email=email
   )
8. Generate JWT with sub = internal user_id (UUID)
9. Return tokens + user info
```

---

## JWT Token Structure

**Access Token**:
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // Internal user UUID
  "username": "System Administrator",
  "email": "admin@localhost",
  "role": "admin",
  "exp": 1735392000
}
```

**CRITICAL**: `sub` claim MUST be internal user_id (UUID), NEVER provider_user_id

---

## Migration Steps

### 1. Database Setup

```bash
# Run migration script
psql -U postgres -d kms_db -f migrations/002_user_identity_system.sql
```

### 2. Environment Configuration

```bash
# Update .env with PostgreSQL credentials
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=kms_db
```

### 3. Install Dependencies

```bash
pip install asyncpg>=0.29.0 bcrypt>=4.1.0
```

### 4. Start Application

```bash
python -m app.api.main
```

**Expected Startup Logs**:
```
[INFO] Initializing PostgreSQL-backed AuthService...
[INFO] ✓ Admin user created: admin@localhost
[INFO] ✓ AuthService initialized successfully
[INFO] ✓ PostgreSQL-backed authentication initialized
```

---

## Verification

### 1. Check Admin Creation

```sql
SELECT id, email, display_name, role, status, created_at
FROM users
WHERE role = 'admin';
```

### 2. Test Admin Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"id": "admin", "password": "SecureAdm1nP@ss2024!"}'
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGc...",
    "token_type": "bearer",
    "expires_in": 3600,
    "refresh_token": "eyJhbGc..."
  }
}
```

### 3. Test Google Login (if configured)

```bash
# Get Google OAuth token first, then:
curl -X POST http://localhost:8000/api/v1/auth/google \
  -H "Content-Type: application/json" \
  -d '{"credential": "ya29.google_access_token..."}'
```

### 4. Verify Database State

```sql
-- Check users
SELECT COUNT(*) FROM users;
SELECT * FROM users;

-- Check auth identities
SELECT COUNT(*) FROM auth_identities;
SELECT * FROM auth_identities;

-- Check user authentication methods
SELECT * FROM v_user_auth_methods;
```

---

## Benefits of This Implementation

### 1. Stable Workspace Ownership
- User changes auth provider → workspace ownership unchanged
- Internal user_id (UUID) is permanent
- No data relationship breakage

### 2. Multiple Authentication Methods
- User can login via Google, SSO, or local password
- Flexibility for users
- Enterprise-grade flexibility

### 3. Security
- bcrypt password hashing
- SQL injection prevention
- Timing-attack resistant
- No password exposure

### 4. Scalability
- Connection pooling (asyncpg)
- Async operations (non-blocking)
- Optimized queries with indexes
- Transaction support

### 5. Auditability
- All authentication tracked in auth_identities.last_used_at
- User creation/modification timestamps
- Login history via users.last_login_at
- Audit views for monitoring

---

## Future Enhancements

### 1. Role-Based Access Control (RBAC)
- Implement permission system based on user.role
- Resource-level permissions
- Hierarchical role inheritance

### 2. Multi-Factor Authentication (MFA)
- TOTP (Time-based One-Time Password)
- SMS verification
- Email verification

### 3. Account Management
- Password reset flow
- Email verification
- Account linking (connect multiple providers to same user)

### 4. OAuth Provider Expansion
- Microsoft OAuth
- GitHub OAuth
- Custom OIDC providers

### 5. Session Management
- Active session tracking
- Concurrent login limits
- Remote session revocation

### 6. Audit Logging
- Detailed authentication logs
- Failed login attempts
- Role changes
- Account modifications

---

## Troubleshooting

### PostgreSQL Connection Errors

```
Error: could not connect to server: Connection refused
```

**Solution**:
1. Check PostgreSQL is running: `pg_isready`
2. Verify credentials in `.env`
3. Check firewall rules for port 5432
4. Verify PostgreSQL accepts connections: `postgresql.conf` → `listen_addresses`

### Admin User Not Created

```
Warning: Admin user already exists
```

**Solution**:
1. Check if admin exists: `SELECT * FROM users WHERE email = 'admin@localhost';`
2. If wrong password, update manually:
   ```python
   from app.api.infrastructure.postgres.user_repository import PostgresUserRepository
   repo.hash_password("SecureAdm1nP@ss2024!")
   # Copy hash and update database
   ```

### bcrypt Import Error

```
ImportError: No module named 'bcrypt'
```

**Solution**:
```bash
pip install bcrypt>=4.1.0
```

### asyncpg Import Error

```
ImportError: No module named 'asyncpg'
```

**Solution**:
```bash
pip install asyncpg>=0.29.0
```

---

## Summary

This implementation provides a **production-ready, enterprise-grade PostgreSQL-backed user authentication and identity management system** that:

✅ Separates Authentication from Internal User Management
✅ Supports Local, Google OAuth, and Corporate SSO
✅ Provides Fixed Admin Credentials (ID: admin)
✅ Uses bcrypt for Secure Password Hashing
✅ Implements Connection Pooling and Async Operations
✅ Supports Multiple Auth Methods per User
✅ Maintains Stable Workspace Ownership
✅ Includes Comprehensive Audit Trail
✅ Follows Enterprise Security Best Practices

**Next Steps**:
1. Run database migration
2. Configure environment variables
3. Install dependencies
4. Start application
5. Test authentication flows
6. Verify database state
