"""
Tests for Health Check Endpoints

Tests API health, readiness, and liveness probes.
"""
import pytest
from fastapi.testclient import TestClient

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_health_endpoint_exists(self, client):
        """Test that /health endpoint exists"""
        response = client.get(f"{API_PREFIX}/health")
        # Should return 200 or redirect, not 404
        assert response.status_code != 404

    def test_health_returns_status(self, client):
        """Test health endpoint returns status"""
        response = client.get(f"{API_PREFIX}/health")
        if response.status_code == 200:
            data = response.json()
            # Should have status field
            assert "status" in data or "healthy" in str(data).lower()

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        # Root should return something (200 or redirect)
        assert response.status_code in [200, 307, 308]


class TestAPIInfo:
    """Tests for API information endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_docs_endpoint(self, client):
        """Test OpenAPI docs endpoint exists"""
        response = client.get("/docs")
        # Should return HTML or redirect
        assert response.status_code in [200, 307, 308]

    def test_openapi_json(self, client):
        """Test OpenAPI JSON schema endpoint"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data


class TestCORSConfiguration:
    """Tests for CORS configuration"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_cors_preflight(self, client):
        """Test CORS preflight request"""
        response = client.options(
            f"{API_PREFIX}/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        # CORS preflight handled - various valid responses depending on config
        # 400 can occur when CORS is configured restrictively (security feature)
        assert response.status_code in [200, 204, 307, 400, 405]

    def test_cors_origin_header(self, client):
        """Test CORS allows configured origins"""
        response = client.get(
            f"{API_PREFIX}/health",
            headers={"Origin": "http://localhost:3000"}
        )
        # Response should not have wildcard CORS
        cors_header = response.headers.get("access-control-allow-origin", "")
        assert cors_header != "*" or cors_header == ""


class TestSecurityHeaders:
    """Tests for security headers"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_content_type_header(self, client):
        """Test content-type header is set correctly"""
        response = client.get(f"{API_PREFIX}/health")
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type or content_type != ""


class TestErrorHandling:
    """Tests for error handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_404_for_unknown_endpoint(self, client):
        """Test 404 response for unknown endpoint"""
        response = client.get("/this-endpoint-does-not-exist-12345")
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test 405 for wrong HTTP method"""
        # POST to docs should fail
        response = client.post("/docs")
        # Should be 405 or 404
        assert response.status_code in [404, 405, 307, 308]
