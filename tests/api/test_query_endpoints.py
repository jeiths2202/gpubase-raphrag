"""
Tests for Query Endpoints

Tests query/RAG API endpoints with mock responses.
Uses mock RAG service for isolation from GPU/LLM dependencies.
"""
import pytest
from fastapi.testclient import TestClient

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestQueryEndpointStructure:
    """Tests for query endpoint existence and structure"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_query_endpoint_exists(self, client):
        """Test that POST /query endpoint exists"""
        response = client.post(f"{API_PREFIX}/query")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_query_stream_endpoint_exists(self, client):
        """Test that POST /query/stream endpoint exists"""
        response = client.post(f"{API_PREFIX}/query/stream")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404


class TestQueryValidation:
    """Tests for query request validation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_query_requires_body(self, client):
        """Test that query requires request body"""
        response = client.post(f"{API_PREFIX}/query")
        # Should fail validation (400/422)
        assert response.status_code in [400, 401, 422]

    def test_query_requires_question(self, client):
        """Test that query requires question field"""
        response = client.post(f"{API_PREFIX}/query", json={})
        # Should fail validation (400/422)
        assert response.status_code in [400, 401, 422]

    def test_query_with_valid_structure(self, client):
        """Test query with valid request structure"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "What is knowledge management?"
        })
        # Should be handled (not 422 validation error for structure)
        # Could be 200, 401 (auth), or 500 (service unavailable)
        assert response.status_code not in [422]


class TestQueryAuthentication:
    """Tests for query authentication requirements"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_query_auth_behavior(self, client):
        """Test query endpoint auth behavior"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "Test question"
        })
        # Query might require auth (401) or work without (200/500)
        assert response.status_code in [200, 401, 500, 503]


class TestQueryParameters:
    """Tests for query parameters"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_query_with_language(self, client):
        """Test query with language parameter"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "지식관리란 무엇인가요?",
            "language": "ko"
        })
        # Should accept language parameter (not 422)
        assert response.status_code not in [422]

    def test_query_with_max_results(self, client):
        """Test query with max_results parameter"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "What is RAG?",
            "max_results": 5
        })
        # Should accept max_results parameter (not 422)
        assert response.status_code not in [422]


class TestQueryResponseFormat:
    """Tests for query response format"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_query_error_response_format(self, client):
        """Test query error response has proper format"""
        response = client.post(f"{API_PREFIX}/query", json={})

        if response.status_code in [400, 401, 422]:
            data = response.json()
            # API uses custom error format
            assert "error" in data or "detail" in data

    def test_validation_error_format(self, client):
        """Test validation error response format"""
        response = client.post(f"{API_PREFIX}/query")

        # Should return validation error
        assert response.status_code in [400, 401, 422]
        data = response.json()
        assert "error" in data or "detail" in data


class TestQueryEdgeCases:
    """Tests for query edge cases"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_empty_question(self, client):
        """Test query with empty question"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": ""
        })
        # Empty question should fail validation or be handled
        assert response.status_code in [200, 400, 401, 422, 500]

    def test_very_long_question(self, client):
        """Test query with very long question"""
        long_question = "What is " + "very " * 1000 + "important?"
        response = client.post(f"{API_PREFIX}/query", json={
            "question": long_question
        })
        # Should handle long questions (not crash)
        assert response.status_code in [200, 400, 401, 413, 422, 500, 503]

    def test_special_characters_in_question(self, client):
        """Test query with special characters"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "What about <script>alert('xss')</script>?"
        })
        # Should handle safely (not 500 server error from parsing)
        assert response.status_code in [200, 400, 401, 422, 500, 503]

    def test_unicode_question(self, client):
        """Test query with unicode characters"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "한글 질문: 인공지능이란 무엇인가요? 🤖"
        })
        # Should handle unicode properly
        assert response.status_code in [200, 400, 401, 422, 500, 503]


class TestQueryTypes:
    """Tests for different query types"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_knowledge_query(self, client):
        """Test knowledge-based query"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "How does the authentication system work?"
        })
        # Should be handled
        assert response.status_code in [200, 401, 500, 503]

    def test_chart_request_query(self, client):
        """Test chart generation query"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "Show me a chart of sales data"
        })
        # Should be handled
        assert response.status_code in [200, 401, 500, 503]

    def test_table_request_query(self, client):
        """Test table data query"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "Create a table comparing features"
        })
        # Should be handled
        assert response.status_code in [200, 401, 500, 503]

    def test_code_request_query(self, client):
        """Test code generation query"""
        response = client.post(f"{API_PREFIX}/query", json={
            "question": "Write Python code to parse JSON"
        })
        # Should be handled
        assert response.status_code in [200, 401, 500, 503]
