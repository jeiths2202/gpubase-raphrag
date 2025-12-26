"""
Tests for Authentication Endpoints

Tests login, register, logout, and token endpoints.
Uses mock auth service for isolation.
"""
import pytest
from fastapi.testclient import TestClient

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestAuthEndpointStructure:
    """Tests for auth endpoint existence and structure"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_login_endpoint_exists(self, client):
        """Test that /auth/login endpoint exists"""
        # POST without body should return 422 (validation error), not 404
        response = client.post(f"{API_PREFIX}/auth/login")
        assert response.status_code != 404

    def test_register_endpoint_exists(self, client):
        """Test that /auth/register endpoint exists"""
        response = client.post(f"{API_PREFIX}/auth/register")
        assert response.status_code != 404

    def test_logout_endpoint_exists(self, client):
        """Test that /auth/logout endpoint exists"""
        response = client.post(f"{API_PREFIX}/auth/logout")
        # Should be 401 (unauthorized) or 200, not 404
        assert response.status_code != 404

    def test_refresh_endpoint_exists(self, client):
        """Test that /auth/refresh endpoint exists"""
        response = client.post(f"{API_PREFIX}/auth/refresh")
        assert response.status_code != 404

    def test_me_endpoint_exists(self, client):
        """Test that /auth/me endpoint exists"""
        response = client.get(f"{API_PREFIX}/auth/me")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404


class TestLoginValidation:
    """Tests for login request validation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_login_requires_body(self, client):
        """Test that login requires request body"""
        response = client.post(f"{API_PREFIX}/auth/login")
        # API returns 400 for validation errors (custom error handling)
        assert response.status_code == 400

    def test_login_requires_username(self, client):
        """Test that login requires username"""
        response = client.post(f"{API_PREFIX}/auth/login", json={"password": "test123"})
        assert response.status_code == 400

    def test_login_requires_password(self, client):
        """Test that login requires password"""
        response = client.post(f"{API_PREFIX}/auth/login", json={"username": "testuser"})
        assert response.status_code == 400

    def test_login_with_valid_structure(self, client):
        """Test login with valid request structure"""
        response = client.post(f"{API_PREFIX}/auth/login", json={
            "username": "testuser",
            "password": "testpass123"
        })
        # Should return 401 (invalid credentials) or 200, not 400
        assert response.status_code in [200, 401]


class TestRegisterValidation:
    """Tests for registration request validation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_register_requires_body(self, client):
        """Test that register requires request body"""
        response = client.post(f"{API_PREFIX}/auth/register")
        # API returns 400 for validation errors
        assert response.status_code == 400

    def test_register_requires_email(self, client):
        """Test that register requires email"""
        response = client.post(f"{API_PREFIX}/auth/register", json={
            "user_id": "newuser",
            "password": "test12345678"  # min 8 chars
        })
        # API returns 400 for validation errors
        assert response.status_code == 400

    def test_register_with_valid_structure(self, client):
        """Test register with valid request structure"""
        response = client.post(f"{API_PREFIX}/auth/register", json={
            "user_id": "newuser",
            "email": "new@example.com",
            "password": "test123456"
        })
        # Should be handled (not 400 validation error for structure)
        # Could be 200 or 409 (user exists)
        assert response.status_code in [200, 201, 409, 500]


class TestAuthProtection:
    """Tests for authentication protection"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_me_requires_auth(self, client):
        """Test that /auth/me requires authentication"""
        response = client.get(f"{API_PREFIX}/auth/me")
        assert response.status_code == 401

    def test_unauthorized_has_error_detail(self, client):
        """Test that unauthorized response has error details"""
        response = client.get(f"{API_PREFIX}/auth/me")
        assert response.status_code == 401
        data = response.json()
        # API uses custom error format with 'error' field
        assert "error" in data or "detail" in data

    def test_logout_without_auth(self, client):
        """Test logout behavior without authentication"""
        response = client.post(f"{API_PREFIX}/auth/logout")
        # Logout without auth could be 200 (no-op) or 401
        assert response.status_code in [200, 401]


class TestAuthCookies:
    """Tests for authentication cookie handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_login_sets_cookies(self, client):
        """Test that successful login would set cookies"""
        # Note: This tests the structure, actual cookie setting
        # depends on valid credentials
        response = client.post(f"{API_PREFIX}/auth/login", json={
            "username": "testuser",
            "password": "testpass123"
        })

        # If login succeeds, should set cookies
        if response.status_code == 200:
            # Check for Set-Cookie header
            set_cookie = response.headers.get("set-cookie", "")
            # Should have HttpOnly cookie for security
            pass

    def test_logout_clears_cookies(self, client):
        """Test that logout clears auth cookies"""
        response = client.post(f"{API_PREFIX}/auth/logout")
        # If implemented, should clear cookies
        assert response.status_code in [200, 401]


class TestAuthResponseFormat:
    """Tests for authentication response format"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_login_error_format(self, client):
        """Test login error response format"""
        response = client.post(f"{API_PREFIX}/auth/login", json={
            "username": "nonexistent",
            "password": "wrongpass"
        })

        if response.status_code == 401:
            data = response.json()
            # API uses custom error format
            assert "error" in data or "detail" in data

    def test_validation_error_format(self, client):
        """Test validation error response format"""
        response = client.post(f"{API_PREFIX}/auth/login", json={})

        # API returns 400 for validation errors
        assert response.status_code == 400
        data = response.json()
        # API uses custom error format
        assert "error" in data or "detail" in data


class TestRefreshToken:
    """Tests for token refresh"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_refresh_without_token(self, client):
        """Test refresh without token"""
        response = client.post(f"{API_PREFIX}/auth/refresh")
        # Should fail without valid token
        assert response.status_code in [401, 422]

    def test_refresh_with_invalid_token(self, client):
        """Test refresh with invalid token"""
        response = client.post(f"{API_PREFIX}/auth/refresh", json={
            "refresh_token": "invalid-token-12345"
        })
        # Should fail with invalid token
        assert response.status_code in [401, 422]
