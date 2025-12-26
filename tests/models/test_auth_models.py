"""
Tests for Authentication Models

Tests Pydantic validation and business logic for auth models.
"""
import pytest
from pydantic import ValidationError


class TestUserRole:
    """Tests for UserRole enum"""

    def test_all_roles_defined(self):
        """Test that all expected roles are defined"""
        from app.api.models.auth import UserRole

        expected_roles = ["admin", "leader", "senior", "user", "guest"]
        actual_roles = [role.value for role in UserRole]

        for role in expected_roles:
            assert role in actual_roles

    def test_role_values(self):
        """Test role enum values"""
        from app.api.models.auth import UserRole

        assert UserRole.ADMIN.value == "admin"
        assert UserRole.LEADER.value == "leader"
        assert UserRole.SENIOR.value == "senior"
        assert UserRole.USER.value == "user"
        assert UserRole.GUEST.value == "guest"

    def test_role_from_string(self):
        """Test creating role from string"""
        from app.api.models.auth import UserRole

        assert UserRole("admin") == UserRole.ADMIN
        assert UserRole("user") == UserRole.USER


class TestRoleHierarchy:
    """Tests for role hierarchy and permissions"""

    def test_hierarchy_order(self):
        """Test role hierarchy ordering"""
        from app.api.models.auth import ROLE_HIERARCHY, UserRole

        assert ROLE_HIERARCHY[UserRole.ADMIN] > ROLE_HIERARCHY[UserRole.LEADER]
        assert ROLE_HIERARCHY[UserRole.LEADER] > ROLE_HIERARCHY[UserRole.SENIOR]
        assert ROLE_HIERARCHY[UserRole.SENIOR] > ROLE_HIERARCHY[UserRole.USER]
        assert ROLE_HIERARCHY[UserRole.USER] > ROLE_HIERARCHY[UserRole.GUEST]

    def test_has_permission_same_level(self):
        """Test permission check with same level"""
        from app.api.models.auth import has_permission, UserRole

        assert has_permission(UserRole.USER.value, UserRole.USER.value)
        assert has_permission(UserRole.ADMIN.value, UserRole.ADMIN.value)

    def test_has_permission_higher_level(self):
        """Test permission check with higher level"""
        from app.api.models.auth import has_permission, UserRole

        # Admin has permission for all roles
        assert has_permission(UserRole.ADMIN.value, UserRole.GUEST.value)
        assert has_permission(UserRole.ADMIN.value, UserRole.USER.value)
        assert has_permission(UserRole.ADMIN.value, UserRole.SENIOR.value)

        # Senior has permission for user level
        assert has_permission(UserRole.SENIOR.value, UserRole.USER.value)

    def test_has_permission_lower_level(self):
        """Test permission check with lower level"""
        from app.api.models.auth import has_permission, UserRole

        # Guest cannot access user-level features
        assert not has_permission(UserRole.GUEST.value, UserRole.USER.value)

        # User cannot access senior-level features
        assert not has_permission(UserRole.USER.value, UserRole.SENIOR.value)

    def test_has_permission_invalid_role(self):
        """Test permission check with invalid role"""
        from app.api.models.auth import has_permission

        assert not has_permission("invalid_role", "user")
        assert not has_permission("user", "invalid_role")

    def test_can_review_function(self):
        """Test can_review function"""
        from app.api.models.auth import can_review, UserRole

        # Senior and above can review
        assert can_review(UserRole.ADMIN.value)
        assert can_review(UserRole.LEADER.value)
        assert can_review(UserRole.SENIOR.value)

        # User and guest cannot review
        assert not can_review(UserRole.USER.value)
        assert not can_review(UserRole.GUEST.value)


class TestLoginRequest:
    """Tests for LoginRequest model"""

    def test_valid_login_request(self):
        """Test valid login request"""
        from app.api.models.auth import LoginRequest

        request = LoginRequest(username="testuser", password="password123")
        assert request.username == "testuser"
        assert request.password == "password123"

    def test_username_required(self):
        """Test that username is required"""
        from app.api.models.auth import LoginRequest

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(password="password123")

        error = exc_info.value
        assert any("username" in str(e) for e in error.errors())

    def test_password_required(self):
        """Test that password is required"""
        from app.api.models.auth import LoginRequest

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="testuser")

        error = exc_info.value
        assert any("password" in str(e) for e in error.errors())

    def test_username_max_length(self):
        """Test username max length validation"""
        from app.api.models.auth import LoginRequest

        long_username = "a" * 101  # Over 100 char limit
        with pytest.raises(ValidationError):
            LoginRequest(username=long_username, password="password123")


class TestRegisterRequest:
    """Tests for RegisterRequest model"""

    def test_valid_register_request(self):
        """Test valid registration request"""
        from app.api.models.auth import RegisterRequest

        request = RegisterRequest(
            user_id="newuser123",
            email="user@example.com",
            password="securepass123"
        )
        assert request.user_id == "newuser123"
        assert request.email == "user@example.com"
        assert request.password == "securepass123"

    def test_user_id_min_length(self):
        """Test user_id minimum length"""
        from app.api.models.auth import RegisterRequest

        with pytest.raises(ValidationError):
            RegisterRequest(
                user_id="ab",  # Less than 3 chars
                email="user@example.com",
                password="securepass123"
            )

    def test_user_id_pattern(self):
        """Test user_id pattern validation"""
        from app.api.models.auth import RegisterRequest

        # Invalid characters
        with pytest.raises(ValidationError):
            RegisterRequest(
                user_id="user@name",
                email="user@example.com",
                password="securepass123"
            )

    def test_valid_user_id_patterns(self):
        """Test valid user_id patterns"""
        from app.api.models.auth import RegisterRequest

        # Valid patterns: alphanumeric and underscore
        valid_ids = ["user123", "user_name", "User_123", "ABC"]
        for user_id in valid_ids:
            request = RegisterRequest(
                user_id=user_id,
                email="user@example.com",
                password="securepass123"
            )
            assert request.user_id == user_id

    def test_email_validation(self):
        """Test email format validation"""
        from app.api.models.auth import RegisterRequest

        with pytest.raises(ValidationError):
            RegisterRequest(
                user_id="newuser",
                email="invalid-email",
                password="securepass123"
            )

    def test_password_min_length(self):
        """Test password minimum length"""
        from app.api.models.auth import RegisterRequest

        with pytest.raises(ValidationError):
            RegisterRequest(
                user_id="newuser",
                email="user@example.com",
                password="short"  # Less than 8 chars
            )


class TestVerifyEmailRequest:
    """Tests for VerifyEmailRequest model"""

    def test_valid_verify_email_request(self):
        """Test valid email verification request"""
        from app.api.models.auth import VerifyEmailRequest

        request = VerifyEmailRequest(
            email="user@example.com",
            code="123456"
        )
        assert request.email == "user@example.com"
        assert request.code == "123456"

    def test_code_length_validation(self):
        """Test verification code length"""
        from app.api.models.auth import VerifyEmailRequest

        # Code too short
        with pytest.raises(ValidationError):
            VerifyEmailRequest(email="user@example.com", code="12345")

        # Code too long
        with pytest.raises(ValidationError):
            VerifyEmailRequest(email="user@example.com", code="1234567")


class TestUserInfo:
    """Tests for UserInfo model"""

    def test_basic_user_info(self):
        """Test basic user info creation"""
        from app.api.models.auth import UserInfo, UserRole

        user = UserInfo(
            id="user_001",
            username="testuser"
        )
        assert user.id == "user_001"
        assert user.username == "testuser"
        assert user.role == UserRole.USER  # Default role
        assert user.is_active is True  # Default active

    def test_user_info_can_review(self):
        """Test UserInfo can_review method"""
        from app.api.models.auth import UserInfo, UserRole

        # Senior can review
        senior = UserInfo(id="1", username="senior", role=UserRole.SENIOR)
        assert senior.can_review() is True

        # User cannot review
        user = UserInfo(id="2", username="user", role=UserRole.USER)
        assert user.can_review() is False

    def test_user_info_is_reviewer(self):
        """Test UserInfo is_reviewer method"""
        from app.api.models.auth import UserInfo, UserRole

        admin = UserInfo(id="1", username="admin", role=UserRole.ADMIN)
        assert admin.is_reviewer() is True

        leader = UserInfo(id="2", username="leader", role=UserRole.LEADER)
        assert leader.is_reviewer() is True

        senior = UserInfo(id="3", username="senior", role=UserRole.SENIOR)
        assert senior.is_reviewer() is True

        user = UserInfo(id="4", username="user", role=UserRole.USER)
        assert user.is_reviewer() is False

        guest = UserInfo(id="5", username="guest", role=UserRole.GUEST)
        assert guest.is_reviewer() is False


class TestTokenResponse:
    """Tests for TokenResponse model"""

    def test_token_response(self):
        """Test token response creation"""
        from app.api.models.auth import TokenResponse

        response = TokenResponse(
            access_token="access_token_value",
            expires_in=3600,
            refresh_token="refresh_token_value"
        )
        assert response.access_token == "access_token_value"
        assert response.token_type == "bearer"  # Default
        assert response.expires_in == 3600
        assert response.refresh_token == "refresh_token_value"
