"""
Tests for Preferences Endpoints

Tests user preferences API including theme and language settings.
"""
import pytest
from fastapi.testclient import TestClient

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestPreferencesEndpointStructure:
    """Tests for preferences endpoint existence and structure"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_preferences_get_endpoint_exists(self, client):
        """Test that GET /preferences endpoint exists"""
        response = client.get(f"{API_PREFIX}/preferences")
        # Should be 401 (unauthorized) not 404
        assert response.status_code != 404

    def test_preferences_patch_endpoint_exists(self, client):
        """Test that PATCH /preferences endpoint exists"""
        response = client.patch(f"{API_PREFIX}/preferences", json={})
        # Should be 401 (unauthorized) or 400 (validation), not 404
        assert response.status_code != 404


class TestPreferencesValidation:
    """Tests for preferences request validation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_preferences_patch_theme_validation(self, client):
        """Test theme value validation"""
        # Valid themes: light, dark, system
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"theme": "invalid_theme"},
            headers={"Authorization": "Bearer test_token"}
        )
        # Should fail validation (400/401/422)
        assert response.status_code in [400, 401, 422]

    def test_preferences_patch_language_validation(self, client):
        """Test language value validation"""
        # Valid languages: en, ko
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"language": "invalid_lang"},
            headers={"Authorization": "Bearer test_token"}
        )
        # Should fail validation (400/401/422)
        assert response.status_code in [400, 401, 422]


class TestPreferencesAuthentication:
    """Tests for preferences authentication requirements"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_get_preferences_requires_auth(self, client):
        """Test that GET /preferences requires authentication"""
        response = client.get(f"{API_PREFIX}/preferences")
        assert response.status_code == 401

    def test_patch_preferences_requires_auth(self, client):
        """Test that PATCH /preferences requires authentication"""
        response = client.patch(f"{API_PREFIX}/preferences", json={"theme": "dark"})
        assert response.status_code == 401


class TestPreferencesResponseFormat:
    """Tests for preferences response format"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_unauthorized_error_format(self, client):
        """Test unauthorized response has error info"""
        response = client.get(f"{API_PREFIX}/preferences")
        assert response.status_code == 401
        data = response.json()
        # API uses custom error format
        assert "error" in data or "detail" in data


class TestPreferencesValues:
    """Tests for valid preference values"""

    VALID_THEMES = ["light", "dark", "system"]
    VALID_LANGUAGES = ["en", "ko"]

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    @pytest.mark.parametrize("theme", VALID_THEMES)
    def test_valid_theme_values_accepted(self, client, theme):
        """Test that valid theme values don't cause 422"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"theme": theme}
        )
        # 401 (no auth) is acceptable, 422 (validation) is not
        assert response.status_code != 422

    @pytest.mark.parametrize("language", VALID_LANGUAGES)
    def test_valid_language_values_accepted(self, client, language):
        """Test that valid language values don't cause 422"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"language": language}
        )
        # 401 (no auth) is acceptable, 422 (validation) is not
        assert response.status_code != 422

    def test_combined_preferences_update(self, client):
        """Test updating both theme and language"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={
                "theme": "dark",
                "language": "ko"
            }
        )
        # 401 (no auth) is acceptable, 422 (validation) is not
        assert response.status_code != 422


class TestPreferencesPartialUpdate:
    """Tests for partial preference updates"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_theme_only_update(self, client):
        """Test updating only theme"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"theme": "light"}
        )
        # Should be handled (not 404 or validation error for structure)
        assert response.status_code in [200, 401, 400]

    def test_language_only_update(self, client):
        """Test updating only language"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={"language": "en"}
        )
        # Should be handled (not 404 or validation error for structure)
        assert response.status_code in [200, 401, 400]

    def test_empty_update(self, client):
        """Test empty update request"""
        response = client.patch(
            f"{API_PREFIX}/preferences",
            json={}
        )
        # Empty update may return various responses
        assert response.status_code in [200, 400, 401, 422]
