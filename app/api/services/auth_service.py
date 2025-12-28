"""
PostgreSQL-backed Authentication Service

PURPOSE:
- Replace in-memory authentication with persistent PostgreSQL storage
- Separate Authentication (Google/SSO) from Internal User Management
- Support local admin login with fixed credentials

DESIGN:
1. Authentication providers (Google/SSO/Local) → resolve to internal user_id
2. JWT 'sub' claim = internal user_id (UUID)
3. Workspace ownership based on internal user_id
"""
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from jose import jwt

from ..core.config import api_settings
from ..models.user import (
    User,
    UserPublic,
    UserUpdate,
    UserCreate,
    UserStatus,
    UserRole,
    AuthProvider,
    LocalLoginRequest,
)
from ..infrastructure.postgres.user_repository import PostgresUserRepository

logger = logging.getLogger(__name__)


# ============================================================================
# FIXED ADMIN CREDENTIALS (As Per Requirements)
# ============================================================================
FIXED_ADMIN_ID = "admin"
FIXED_ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"
FIXED_ADMIN_EMAIL = "admin@example.com"  # Valid email format for Pydantic validation


class AuthService:
    """
    PostgreSQL-backed Authentication Service.

    Features:
    - Local authentication (admin with fixed credentials)
    - Google OAuth integration
    - Corporate SSO integration
    - JWT token generation
    - User identity management via PostgreSQL

    SECURITY NOTE:
    - Admin password is FIXED per requirements
    - All users stored in PostgreSQL
    - bcrypt password hashing
    - JWT tokens include internal user_id as 'sub'
    """

    def __init__(self, user_repository: PostgresUserRepository):
        """
        Initialize auth service with user repository.

        Args:
            user_repository: PostgreSQL user repository
        """
        self.user_repo = user_repository
        self._sso_tokens: Dict[str, Dict[str, Any]] = {}  # In-memory SSO token cache
        self._verification_codes: Dict[str, Dict[str, Any]] = {}  # In-memory verification code storage

    # ==================== Bootstrap ====================

    async def initialize_admin_user(self) -> bool:
        """
        Initialize fixed admin user at application startup.

        Creates admin with FIXED credentials:
        - ID: admin
        - Password: SecureAdm1nP@ss2024!
        - Email: admin@localhost

        Returns:
            True if admin was created, False if already exists
        """
        try:
            user, created = await self.user_repo.create_admin_if_not_exists(
                email=FIXED_ADMIN_EMAIL,
                password=FIXED_ADMIN_PASSWORD,
                display_name="System Administrator"
            )

            if created:
                logger.info(f"✓ Admin user created: {FIXED_ADMIN_EMAIL}")
                return True
            else:
                logger.info(f"Admin user already exists: {FIXED_ADMIN_EMAIL}")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize admin user: {e}")
            raise

    # ==================== Local Authentication ====================

    async def authenticate(
        self,
        username: str,
        password: str
    ) -> Optional[User]:
        """
        General authentication method (wrapper for authenticate_local).

        This method exists for compatibility with the auth router.

        Args:
            username: User ID or email
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        return await self.authenticate_local(username, password)

    async def authenticate_local(
        self,
        id_or_email: str,
        password: str
    ) -> Optional[User]:
        """
        Authenticate with local username/password.

        Supports:
        - Fixed admin credentials (ID: admin)
        - Email-based login for other users

        Args:
            id_or_email: User ID or email
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        logger.debug(f"authenticate_local called with id_or_email={id_or_email}")

        # Special handling for fixed admin ID
        if id_or_email == FIXED_ADMIN_ID:
            logger.debug(f"Special admin ID detected, using email: {FIXED_ADMIN_EMAIL}")
            # Try admin email
            user = await self.user_repo.authenticate_local(
                FIXED_ADMIN_EMAIL,
                password
            )
            if user:
                logger.info(f"✓ Admin login successful: {user.id}")
                return user
            else:
                logger.warning(f"✗ Admin authentication failed for email: {FIXED_ADMIN_EMAIL}")

        # Standard email-based authentication
        logger.debug(f"Attempting standard email-based authentication for: {id_or_email}")
        user = await self.user_repo.authenticate_local(id_or_email, password)

        if user:
            logger.info(f"✓ Local login successful: {user.email}")
        else:
            logger.warning(f"✗ Local login failed: {id_or_email}")

        return user

    # ==================== Google OAuth ====================

    async def authenticate_google(self, credential: str) -> Optional[User]:
        """
        Authenticate with Google OAuth access token.

        FLOW:
        1. Verify token with Google API
        2. Extract Google user ID (sub) and email
        3. Resolve to internal user via auth_identities
        4. Create new user if first-time login

        Args:
            credential: Google OAuth access token

        Returns:
            Internal User object (with internal UUID)
        """
        import httpx

        try:
            # Verify access token with Google
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {credential}"}
                )

                if response.status_code != 200:
                    logger.warning(f"Google token verification failed: {response.status_code}")
                    return None

                userinfo = response.json()

                # Extract Google user info
                google_sub = userinfo.get("sub")  # Google's unique user ID
                email = userinfo.get("email")
                name = userinfo.get("name", email.split("@")[0] if email else "Google User")
                picture = userinfo.get("picture")

                if not google_sub or not email:
                    logger.warning("Missing required fields in Google response")
                    return None

                logger.info(f"✓ Google OAuth verified: {email}")

                # Get or create internal user
                user, created = await self.user_repo.get_or_create_user_from_external_auth(
                    provider=AuthProvider.GOOGLE,
                    provider_user_id=google_sub,
                    email=email,
                    display_name=name,
                    provider_metadata={"picture": picture}
                )

                if created:
                    logger.info(f"✓ New user created from Google: {email}")
                else:
                    logger.info(f"✓ Existing user authenticated via Google: {email}")

                return user

        except Exception as e:
            logger.error(f"Google authentication error: {e}")
            return None

    # ==================== Corporate SSO ====================

    async def initiate_sso(self, email: str) -> Dict[str, Any]:
        """
        Initiate corporate SSO flow.

        TODO: Implement actual SAML/OIDC integration
        For now, generates temporary token for mock SSO flow
        """
        import uuid

        # Validate corporate email domain
        if not api_settings.is_corp_email(email):
            return {
                "error": "INVALID_DOMAIN",
                "message": "Email domain not authorized for SSO"
            }

        # Generate SSO token
        token = uuid.uuid4().hex

        # Store token with email (valid for 5 minutes)
        self._sso_tokens[token] = {
            "email": email,
            "created_at": datetime.utcnow()
        }

        # Clean up old tokens
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)
        self._sso_tokens = {
            k: v for k, v in self._sso_tokens.items()
            if v["created_at"] > cutoff_time
        }

        logger.info(f"✓ SSO initiated for: {email}")

        return {
            "success": True,
            "sso_url": f"/auth/sso/callback?token={token}",
            "message": "SSO 인증 페이지로 이동합니다."
        }

    async def handle_sso_callback(self, token: str) -> Dict[str, Any]:
        """
        Handle SSO callback and authenticate user.

        FLOW:
        1. Validate SSO token
        2. Extract email from token data
        3. Get or create internal user via auth_identities
        4. Return internal user

        Returns:
            {"success": True, "user": User} or error dict
        """
        # Validate token
        if token not in self._sso_tokens:
            logger.warning(f"Invalid SSO token: {token}")
            return {
                "error": "INVALID_TOKEN",
                "message": "유효하지 않은 SSO 토큰입니다."
            }

        token_data = self._sso_tokens[token]

        # Check expiration
        if datetime.utcnow() - token_data["created_at"] > timedelta(minutes=5):
            del self._sso_tokens[token]
            logger.warning(f"Expired SSO token: {token}")
            return {
                "error": "TOKEN_EXPIRED",
                "message": "SSO 토큰이 만료되었습니다."
            }

        email = token_data["email"]

        # Clean up used token
        del self._sso_tokens[token]

        # Get or create internal user
        user, created = await self.user_repo.get_or_create_user_from_external_auth(
            provider=AuthProvider.SSO,
            provider_user_id=email,  # Use email as provider user ID for SSO
            email=email,
            display_name=email.split("@")[0]
        )

        if created:
            logger.info(f"✓ New user created from SSO: {email}")
        else:
            logger.info(f"✓ Existing user authenticated via SSO: {email}")

        return {
            "success": True,
            "user": user
        }

    # ==================== JWT Token Generation ====================

    async def create_access_token(self, user: User) -> str:
        """
        Create JWT access token.

        CRITICAL: 'sub' claim MUST be internal user.id (UUID)
        NEVER use provider_user_id for JWT sub
        """
        expire = datetime.utcnow() + timedelta(
            minutes=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

        payload = {
            "sub": str(user.id),  # Internal user UUID
            "username": user.display_name or user.email,
            "email": user.email,
            "role": user.role.value,
            "exp": expire
        }

        token = jwt.encode(
            payload,
            api_settings.JWT_SECRET_KEY,
            algorithm=api_settings.JWT_ALGORITHM
        )

        return token

    async def create_refresh_token(self, user: User) -> str:
        """Create JWT refresh token."""
        expire = datetime.utcnow() + timedelta(
            days=api_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

        payload = {
            "sub": str(user.id),  # Internal user UUID
            "type": "refresh",
            "exp": expire
        }

        token = jwt.encode(
            payload,
            api_settings.JWT_SECRET_KEY,
            algorithm=api_settings.JWT_ALGORITHM
        )

        return token

    async def verify_refresh_token(self, token: str) -> Optional[User]:
        """
        Verify refresh token and return user.

        Returns:
            User if token valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                api_settings.JWT_SECRET_KEY,
                algorithms=[api_settings.JWT_ALGORITHM]
            )

            user_id = payload.get("sub")
            token_type = payload.get("type")

            if not user_id or token_type != "refresh":
                return None

            # Get user from database
            user = await self.user_repo.get_user_by_id(UUID(user_id))
            return user

        except Exception as e:
            logger.warning(f"Refresh token verification failed: {e}")
            return None

    # ==================== User Management ====================

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by internal UUID."""
        return await self.user_repo.get_user_by_id(user_id)

    async def get_user_public(self, user_id: UUID) -> Optional[UserPublic]:
        """
        Get public user information (safe for API responses).

        SECURITY: Excludes password_hash and internal sensitive data
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        return UserPublic(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            department=user.department,
            language=user.language,
            created_at=user.created_at,
            last_login_at=user.last_login_at
        )

    # ==================== User Registration ====================

    def _generate_verification_code(self) -> str:
        """Generate a 6-digit verification code"""
        return str(random.randint(100000, 999999))

    async def _send_verification_email(self, email: str, code: str) -> None:
        """
        Send verification code via email.

        Methods (in priority order):
        1. Linux sendmail (production)
        2. SMTP server (fallback)
        3. Console log (development)
        """
        import subprocess
        import shutil
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        # Email content
        subject = "KMS Email Verification Code"
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">Email Verification</h1>
            </div>
            <div style="padding: 30px; background: #f9fafb; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px; color: #374151;">Your verification code is:</p>
                <div style="background: white; border: 2px solid #6366f1; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                    <h2 style="font-size: 32px; letter-spacing: 8px; color: #6366f1; margin: 0;">{code}</h2>
                </div>
                <p style="font-size: 14px; color: #6b7280;">This code will expire in 5 minutes.</p>
                <p style="font-size: 14px; color: #6b7280;">If you didn't request this code, please ignore this email.</p>
            </div>
        </body>
        </html>
        """

        body_text = f"""
KMS Email Verification

Your verification code is: {code}

This code will expire in 5 minutes.
If you didn't request this code, please ignore this email.
        """

        # Log for development
        logger.info(f"📧 ========================================")
        logger.info(f"📧 SENDING EMAIL TO: {email}")
        logger.info(f"📧 Verification Code: {code}")
        logger.info(f"📧 ========================================")

        if not api_settings.SMTP_ENABLED:
            logger.info("📧 SMTP_ENABLED=false, email not sent (development mode)")
            return

        # Method 1: Try Linux sendmail
        if api_settings.USE_SENDMAIL and shutil.which(api_settings.SENDMAIL_PATH):
            try:
                # Construct email message for sendmail
                message = f"""From: {api_settings.SMTP_FROM_NAME} <{api_settings.SMTP_FROM_EMAIL}>
To: {email}
Subject: {subject}
Content-Type: text/html; charset=utf-8

{body_html}
"""
                # Call sendmail
                process = subprocess.run(
                    [api_settings.SENDMAIL_PATH, "-t", "-oi"],
                    input=message.encode('utf-8'),
                    capture_output=True,
                    timeout=10
                )

                if process.returncode == 0:
                    logger.info(f"✅ Email sent via sendmail to {email}")
                    return
                else:
                    logger.warning(f"⚠️ Sendmail failed: {process.stderr.decode()}")

            except Exception as e:
                logger.warning(f"⚠️ Sendmail error: {e}")

        # Method 2: Try SMTP
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{api_settings.SMTP_FROM_NAME} <{api_settings.SMTP_FROM_EMAIL}>"
            msg['To'] = email

            # Attach both text and HTML versions
            part1 = MIMEText(body_text, 'plain', 'utf-8')
            part2 = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(part1)
            msg.attach(part2)

            # Send via SMTP
            with smtplib.SMTP(api_settings.SMTP_HOST, api_settings.SMTP_PORT, timeout=10) as smtp:
                if api_settings.SMTP_USE_TLS:
                    smtp.starttls()

                if api_settings.SMTP_USERNAME and api_settings.SMTP_PASSWORD:
                    smtp.login(api_settings.SMTP_USERNAME, api_settings.SMTP_PASSWORD)

                smtp.send_message(msg)
                logger.info(f"✅ Email sent via SMTP to {email}")
                return

        except Exception as e:
            logger.error(f"❌ SMTP email failed: {e}")
            logger.info(f"📧 Email not sent, but code logged above for development")

    async def register_user(
        self,
        user_id: str,
        email: str,
        password: str
    ) -> Dict[str, Any]:
        """
        Register a new user and send verification code.

        Args:
            user_id: User ID for login
            email: User email address
            password: Plain text password (will be hashed)

        Returns:
            Success dict or error dict
        """
        # Check if email already exists
        existing_user = await self.user_repo.get_user_by_email(email)
        if existing_user:
            return {
                "error": "EMAIL_ALREADY_EXISTS",
                "message": "이미 등록된 이메일입니다."
            }

        # Create user
        try:
            user_create = UserCreate(
                email=email,
                display_name=user_id,  # Use user_id as display_name
                password=password,
                role=UserRole.USER,
                status=UserStatus.PENDING  # User needs email verification before activation
            )

            user = await self.user_repo.create_user(user_create)

            # Generate and store verification code
            verification_code = self._generate_verification_code()
            self._verification_codes[email] = {
                "code": verification_code,
                "created_at": datetime.utcnow(),
                "user_id": str(user.id)
            }

            # Send verification email
            await self._send_verification_email(email, verification_code)

            # Clean up old verification codes
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            self._verification_codes = {
                k: v for k, v in self._verification_codes.items()
                if v["created_at"] > cutoff_time
            }

            logger.info(f"✓ New user registered: {email}")

            return {
                "user_id": user_id,
                "email": email,
                "message": "회원가입이 완료되었습니다."
            }

        except Exception as e:
            logger.error(f"User registration error: {e}")
            return {
                "error": "REGISTRATION_FAILED",
                "message": "회원가입에 실패했습니다."
            }

    async def verify_email(
        self,
        email: str,
        code: str
    ) -> Dict[str, Any]:
        """
        Verify email with code and activate user in PostgreSQL.

        Args:
            email: User email
            code: Verification code sent via email

        Returns:
            Success dict with user object or error dict
        """
        # Get user by email
        user = await self.user_repo.get_user_by_email(email)

        if not user:
            return {
                "error": "USER_NOT_FOUND",
                "message": "사용자를 찾을 수 없습니다."
            }

        # Check if verification code exists
        if email not in self._verification_codes:
            return {
                "error": "CODE_NOT_FOUND",
                "message": "인증 코드가 존재하지 않습니다. 회원가입을 다시 진행해주세요."
            }

        stored_code_data = self._verification_codes[email]

        # Check if code matches
        if stored_code_data["code"] != code:
            return {
                "error": "INVALID_CODE",
                "message": "인증 코드가 일치하지 않습니다."
            }

        # Check if code is expired (5 minutes)
        if datetime.utcnow() - stored_code_data["created_at"] > timedelta(minutes=5):
            del self._verification_codes[email]
            return {
                "error": "CODE_EXPIRED",
                "message": "인증 코드가 만료되었습니다. 회원가입을 다시 진행해주세요."
            }

        # Update user status to ACTIVE in PostgreSQL
        try:
            user_update = UserUpdate(status=UserStatus.ACTIVE)
            updated_user = await self.user_repo.update_user(user.id, user_update)

            if not updated_user:
                return {
                    "error": "UPDATE_FAILED",
                    "message": "사용자 상태 업데이트에 실패했습니다."
                }

            # Remove verification code after successful verification
            del self._verification_codes[email]

            logger.info(f"✓ Email verified and user activated in DB: {email}")

            return {
                "user": updated_user
            }

        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return {
                "error": "VERIFICATION_FAILED",
                "message": "이메일 인증에 실패했습니다."
            }


# ==================== Factory Function ====================

_auth_service_instance: Optional[AuthService] = None


async def get_auth_service() -> AuthService:
    """
    Get AuthService instance (singleton).

    This will be replaced with proper dependency injection
    when PostgreSQL connection pool is initialized.
    """
    global _auth_service_instance

    if _auth_service_instance is None:
        # For now, create with in-memory fallback
        # This will be replaced with actual PostgreSQL connection
        logger.warning("AuthService using in-memory mode - PostgreSQL not initialized")

        # TODO: Initialize with actual PostgreSQL connection pool
        # dsn = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        # user_repo = await PostgresUserRepository.create(dsn)
        # _auth_service_instance = AuthService(user_repo)

        # For now, return None to maintain backward compatibility
        raise RuntimeError(
            "PostgreSQL AuthService not initialized. "
            "Call initialize_auth_service() at application startup."
        )

    return _auth_service_instance


async def initialize_auth_service(dsn: str) -> AuthService:
    """
    Initialize AuthService with PostgreSQL connection.

    Call this at application startup.

    Args:
        dsn: PostgreSQL connection string

    Returns:
        Initialized AuthService
    """
    global _auth_service_instance

    logger.info("Initializing PostgreSQL-backed AuthService...")

    # Create user repository with connection pool
    user_repo = await PostgresUserRepository.create(dsn)

    # Create auth service
    _auth_service_instance = AuthService(user_repo)

    # Bootstrap admin user
    await _auth_service_instance.initialize_admin_user()

    logger.info("✓ AuthService initialized successfully")

    return _auth_service_instance
