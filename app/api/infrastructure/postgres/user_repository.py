"""
PostgreSQL User Repository Implementation

Production-ready PostgreSQL implementation for user and authentication identity management.

Features:
- Async operations using asyncpg
- Connection pooling
- Secure password hashing with bcrypt
- Transaction support for user creation with auth identity
- Protection against timing attacks during authentication
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import asyncpg
from asyncpg import Pool, Connection
import bcrypt

from ...models.user import (
    User,
    UserCreate,
    UserUpdate,
    UserRole,
    UserStatus,
    AuthProvider,
    AuthIdentity,
    AuthIdentityCreate,
)

logger = logging.getLogger(__name__)


class PostgresUserRepository:
    """
    PostgreSQL implementation of User Repository.

    DESIGN PRINCIPLES:
    1. Authentication resolves to internal user_id
    2. Authorization uses internal user role
    3. Workspace ownership based on internal user_id
    4. Multiple auth providers can map to single user

    SECURITY:
    - bcrypt for password hashing (work factor 12)
    - Timing-attack protection during authentication
    - Input validation for SQL injection prevention
    - No password exposure in logs or responses
    """

    def __init__(self, pool: Pool):
        """
        Initialize PostgreSQL user repository.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    @classmethod
    async def create(
        cls,
        dsn: str,
        *,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs
    ) -> "PostgresUserRepository":
        """
        Factory method to create repository with connection pool.

        Args:
            dsn: PostgreSQL connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            **kwargs
        )
        return cls(pool)

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()

    # ==================== Password Hashing ====================

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash password using bcrypt with work factor 12.

        SECURITY: bcrypt is designed to be slow to prevent brute force attacks.
        Work factor 12 = 2^12 iterations (~300ms per hash)
        """
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify password against bcrypt hash.

        SECURITY: Timing-attack resistant comparison
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.warning(f"Password verification failed: {e}")
            return False

    # ==================== User CRUD Operations ====================

    async def create_user(
        self,
        user_create: UserCreate,
        *,
        conn: Optional[Connection] = None
    ) -> User:
        """
        Create new user in database.

        Args:
            user_create: User creation data
            conn: Optional existing connection (for transactions)

        Returns:
            Created user

        Raises:
            asyncpg.UniqueViolationError: If email already exists
        """
        # Hash password if provided (local auth)
        password_hash = None
        if user_create.password:
            password_hash = self.hash_password(user_create.password)

        query = """
            INSERT INTO users (
                email, display_name, password_hash, role, status, department, language
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING
                id, email, display_name, password_hash, role, status,
                department, language, created_at, updated_at, last_login_at
        """

        if conn:
            row = await conn.fetchrow(
                query,
                user_create.email,
                user_create.display_name,
                password_hash,
                user_create.role.value,
                user_create.status.value,
                user_create.department,
                user_create.language
            )
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    user_create.email,
                    user_create.display_name,
                    password_hash,
                    user_create.role.value,
                    user_create.status.value,
                    user_create.department,
                    user_create.language
                )

        return User(**dict(row))

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by internal UUID."""
        query = """
            SELECT
                id, email, display_name, password_hash, role, status,
                department, language, created_at, updated_at, last_login_at
            FROM users
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

        if row:
            return User(**dict(row))
        return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        query = """
            SELECT
                id, email, display_name, password_hash, role, status,
                department, language, created_at, updated_at, last_login_at
            FROM users
            WHERE email = $1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, email)

        if row:
            return User(**dict(row))
        return None

    async def update_user(
        self,
        user_id: UUID,
        user_update: UserUpdate
    ) -> Optional[User]:
        """
        Update user information.

        Only non-None fields in user_update are updated.
        """
        updates = []
        values = []
        param_idx = 1

        if user_update.display_name is not None:
            updates.append(f"display_name = ${param_idx}")
            values.append(user_update.display_name)
            param_idx += 1

        if user_update.role is not None:
            updates.append(f"role = ${param_idx}")
            values.append(user_update.role.value)
            param_idx += 1

        if user_update.status is not None:
            updates.append(f"status = ${param_idx}")
            values.append(user_update.status.value)
            param_idx += 1

        if user_update.department is not None:
            updates.append(f"department = ${param_idx}")
            values.append(user_update.department)
            param_idx += 1

        if user_update.language is not None:
            updates.append(f"language = ${param_idx}")
            values.append(user_update.language)
            param_idx += 1

        if not updates:
            # No updates, return existing user
            return await self.get_user_by_id(user_id)

        # Add user_id as last parameter
        values.append(user_id)

        query = f"""
            UPDATE users
            SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING
                id, email, display_name, password_hash, role, status,
                department, language, created_at, updated_at, last_login_at
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)

        if row:
            return User(**dict(row))
        return None

    async def update_last_login(self, user_id: UUID) -> None:
        """Update user's last login timestamp."""
        query = """
            UPDATE users
            SET last_login_at = NOW()
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            await conn.execute(query, user_id)

    async def list_users(
        self,
        *,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Tuple[List[User], int]:
        """
        List users with optional filtering and pagination.

        Returns:
            (users, total_count)
        """
        where_clauses = []
        values = []
        param_idx = 1

        if role is not None:
            where_clauses.append(f"role = ${param_idx}")
            values.append(role.value)
            param_idx += 1

        if status is not None:
            where_clauses.append(f"status = ${param_idx}")
            values.append(status.value)
            param_idx += 1

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        count_query = f"SELECT COUNT(*) FROM users WHERE {where_sql}"

        data_query = f"""
            SELECT
                id, email, display_name, password_hash, role, status,
                department, language, created_at, updated_at, last_login_at
            FROM users
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, *values)
            rows = await conn.fetch(data_query, *values, limit, offset)

        users = [User(**dict(row)) for row in rows]
        return users, total

    # ==================== Authentication Identity Operations ====================

    async def create_auth_identity(
        self,
        auth_identity_create: AuthIdentityCreate,
        *,
        conn: Optional[Connection] = None
    ) -> AuthIdentity:
        """
        Create authentication identity mapping.

        Args:
            auth_identity_create: Auth identity data
            conn: Optional existing connection (for transactions)

        Raises:
            asyncpg.UniqueViolationError: If (provider, provider_user_id) already exists
        """
        query = """
            INSERT INTO auth_identities (
                user_id, provider, provider_user_id, email, provider_metadata
            )
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, user_id, provider, provider_user_id, email,
                      provider_metadata, created_at, last_used_at
        """

        metadata_json = None
        if auth_identity_create.provider_metadata:
            import json
            metadata_json = json.dumps(auth_identity_create.provider_metadata)

        if conn:
            row = await conn.fetchrow(
                query,
                auth_identity_create.user_id,
                auth_identity_create.provider.value,
                auth_identity_create.provider_user_id,
                auth_identity_create.email,
                metadata_json
            )
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    auth_identity_create.user_id,
                    auth_identity_create.provider.value,
                    auth_identity_create.provider_user_id,
                    auth_identity_create.email,
                    metadata_json
                )

        row_dict = dict(row)
        # BUGFIX: Parse provider_metadata if it's a JSON string (asyncpg JSONB handling)
        if row_dict.get('provider_metadata') and isinstance(row_dict['provider_metadata'], str):
            import json
            row_dict['provider_metadata'] = json.loads(row_dict['provider_metadata'])
        return AuthIdentity(**row_dict)

    async def get_auth_identity(
        self,
        provider: AuthProvider,
        provider_user_id: str
    ) -> Optional[AuthIdentity]:
        """
        Get authentication identity by provider and provider_user_id.

        This is the CRITICAL method for external authentication resolution.
        """
        query = """
            SELECT id, user_id, provider, provider_user_id, email,
                   provider_metadata, created_at, last_used_at
            FROM auth_identities
            WHERE provider = $1 AND provider_user_id = $2
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, provider.value, provider_user_id)

        if row:
            row_dict = dict(row)
            # BUGFIX: Parse provider_metadata if it's a JSON string (asyncpg JSONB handling)
            if row_dict.get('provider_metadata') and isinstance(row_dict['provider_metadata'], str):
                import json
                row_dict['provider_metadata'] = json.loads(row_dict['provider_metadata'])
            return AuthIdentity(**row_dict)
        return None

    async def update_auth_identity_last_used(
        self,
        provider: AuthProvider,
        provider_user_id: str
    ) -> None:
        """Update last_used_at timestamp for auth identity."""
        query = """
            UPDATE auth_identities
            SET last_used_at = NOW()
            WHERE provider = $1 AND provider_user_id = $2
        """

        async with self._pool.acquire() as conn:
            await conn.execute(query, provider.value, provider_user_id)

    async def get_user_auth_identities(self, user_id: UUID) -> List[AuthIdentity]:
        """Get all authentication identities for a user."""
        query = """
            SELECT id, user_id, provider, provider_user_id, email,
                   provider_metadata, created_at, last_used_at
            FROM auth_identities
            WHERE user_id = $1
            ORDER BY created_at DESC
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)

        return [AuthIdentity(**dict(row)) for row in rows]

    # ==================== Combined Operations (Transactions) ====================

    async def get_or_create_user_from_external_auth(
        self,
        provider: AuthProvider,
        provider_user_id: str,
        email: str,
        display_name: Optional[str] = None,
        provider_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[User, bool]:
        """
        Get existing user or create new user from external authentication.

        This is the PRIMARY method for Google/SSO authentication flow.

        Returns:
            (user, created) - user object and whether it was newly created

        FLOW:
        1. Check if auth_identity exists for (provider, provider_user_id)
        2. If exists: Update last_used_at, return existing user
        3. If not exists: Create new user + auth_identity in transaction
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Step 1: Check existing auth_identity
                auth_identity = await self.get_auth_identity(provider, provider_user_id)

                if auth_identity:
                    # Existing user found
                    await self.update_auth_identity_last_used(provider, provider_user_id)
                    await self.update_last_login(auth_identity.user_id)

                    user = await self.get_user_by_id(auth_identity.user_id)
                    return user, False

                # Step 2: Create new user
                user_create = UserCreate(
                    email=email,
                    display_name=display_name or email.split('@')[0],
                    role=UserRole.USER,  # Default role for external auth users
                    status=UserStatus.ACTIVE,
                    password=None  # No password for SSO/OAuth users
                )

                try:
                    user = await self.create_user(user_create, conn=conn)
                except asyncpg.UniqueViolationError:
                    # Email already exists, get existing user
                    user = await self.get_user_by_email(email)

                # Step 3: Create auth_identity mapping
                auth_identity_create = AuthIdentityCreate(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                    provider_metadata=provider_metadata
                )

                await self.create_auth_identity(auth_identity_create, conn=conn)

                return user, True

    # ==================== Local Authentication ====================

    async def authenticate_local(
        self,
        id_or_email: str,
        password: str
    ) -> Optional[User]:
        """
        Authenticate user with ID/email and password.

        Args:
            id_or_email: User ID or email
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise

        SECURITY:
        - Timing-attack resistant
        - Password hash never logged or exposed
        - Status check after authentication
        """
        logger.debug(f"[REPO] authenticate_local called with id_or_email={id_or_email}")

        # Try to find user by email first, then by username if email not found
        user = await self.get_user_by_email(id_or_email)

        if not user:
            logger.debug(f"[REPO] User not found for email: {id_or_email}")
            # User not found or has no password (SSO-only user)
            # Still compute a fake hash to prevent timing attacks
            self.verify_password(password, "$2b$12$fake.hash.for.timing.protection")
            return None

        if not user.password_hash:
            logger.debug(f"[REPO] User {user.id} has no password_hash (SSO-only user)")
            # Still compute a fake hash to prevent timing attacks
            self.verify_password(password, "$2b$12$fake.hash.for.timing.protection")
            return None

        logger.debug(f"[REPO] User found: {user.id}, verifying password...")

        # Verify password
        password_valid = self.verify_password(password, user.password_hash)
        logger.debug(f"[REPO] Password verification result: {password_valid}")

        if not password_valid:
            return None

        # Check user status
        if user.status != UserStatus.ACTIVE:
            logger.warning(f"Authentication attempt for inactive user: {user.id}")
            return None

        logger.debug(f"[REPO] Authentication successful, updating last_login")

        # Update last login
        await self.update_last_login(user.id)

        return user

    # ==================== Admin Operations ====================

    async def create_admin_if_not_exists(
        self,
        email: str,
        password: str,
        display_name: str = "System Administrator"
    ) -> Tuple[User, bool]:
        """
        Create admin user if it doesn't exist.

        This is called at application startup for bootstrap.

        Returns:
            (user, created) - admin user and whether it was newly created
        """
        # Check if admin already exists
        existing_user = await self.get_user_by_email(email)

        if existing_user:
            return existing_user, False

        # Create admin user
        user_create = UserCreate(
            email=email,
            display_name=display_name,
            password=password,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            language="ko"
        )

        user = await self.create_user(user_create)
        logger.info(f"Admin user created: {email}")

        return user, True
