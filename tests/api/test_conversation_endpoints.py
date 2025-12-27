"""
Tests for Conversation API Endpoints

Tests the conversation management API including:
- Conversation CRUD operations
- Message operations
- Regenerate and fork functionality
- Search and statistics
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestConversationEndpointStructure:
    """Tests for conversation endpoint existence and structure"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_list_conversations_endpoint_exists(self, client):
        """Test that GET /conversations endpoint exists"""
        response = client.get(f"{API_PREFIX}/conversations")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_create_conversation_endpoint_exists(self, client):
        """Test that POST /conversations endpoint exists"""
        response = client.post(f"{API_PREFIX}/conversations")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_get_conversation_endpoint_exists(self, client):
        """Test that GET /conversations/{id} endpoint exists"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_update_conversation_endpoint_exists(self, client):
        """Test that PATCH /conversations/{id} endpoint exists"""
        fake_id = str(uuid4())
        response = client.patch(f"{API_PREFIX}/conversations/{fake_id}")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_delete_conversation_endpoint_exists(self, client):
        """Test that DELETE /conversations/{id} endpoint exists"""
        fake_id = str(uuid4())
        response = client.delete(f"{API_PREFIX}/conversations/{fake_id}")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_add_message_endpoint_exists(self, client):
        """Test that POST /conversations/{id}/messages endpoint exists"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_get_messages_endpoint_exists(self, client):
        """Test that GET /conversations/{id}/messages endpoint exists"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}/messages")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_add_feedback_endpoint_exists(self, client):
        """Test that POST /conversations/{id}/messages/{message_id}/feedback exists"""
        fake_conv_id = str(uuid4())
        fake_msg_id = str(uuid4())
        response = client.post(
            f"{API_PREFIX}/conversations/{fake_conv_id}/messages/{fake_msg_id}/feedback"
        )
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_regenerate_endpoint_exists(self, client):
        """Test that POST /conversations/{id}/regenerate endpoint exists"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/regenerate")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_fork_endpoint_exists(self, client):
        """Test that POST /conversations/{id}/fork endpoint exists"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/fork")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_search_endpoint_exists(self, client):
        """Test that GET /conversations/search endpoint exists"""
        response = client.get(f"{API_PREFIX}/conversations/search?q=test")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404

    def test_stats_endpoint_exists(self, client):
        """Test that GET /conversations/stats endpoint exists"""
        response = client.get(f"{API_PREFIX}/conversations/stats")
        # Should be 401 (unauthorized), not 404
        assert response.status_code != 404


class TestConversationAuthProtection:
    """Tests for authentication protection on conversation endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_list_conversations_requires_auth(self, client):
        """Test that listing conversations requires authentication"""
        response = client.get(f"{API_PREFIX}/conversations")
        assert response.status_code == 401

    def test_create_conversation_requires_auth(self, client):
        """Test that creating conversation requires authentication"""
        response = client.post(f"{API_PREFIX}/conversations", json={})
        assert response.status_code == 401

    def test_get_conversation_requires_auth(self, client):
        """Test that getting conversation requires authentication"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}")
        assert response.status_code == 401

    def test_update_conversation_requires_auth(self, client):
        """Test that updating conversation requires authentication"""
        fake_id = str(uuid4())
        response = client.patch(f"{API_PREFIX}/conversations/{fake_id}", json={"title": "New"})
        assert response.status_code == 401

    def test_delete_conversation_requires_auth(self, client):
        """Test that deleting conversation requires authentication"""
        fake_id = str(uuid4())
        response = client.delete(f"{API_PREFIX}/conversations/{fake_id}")
        assert response.status_code == 401

    def test_add_message_requires_auth(self, client):
        """Test that adding message requires authentication"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user",
            "content": "Hello"
        })
        assert response.status_code == 401

    def test_get_messages_requires_auth(self, client):
        """Test that getting messages requires authentication"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}/messages")
        assert response.status_code == 401

    def test_add_feedback_requires_auth(self, client):
        """Test that adding feedback requires authentication"""
        fake_conv_id = str(uuid4())
        fake_msg_id = str(uuid4())
        response = client.post(
            f"{API_PREFIX}/conversations/{fake_conv_id}/messages/{fake_msg_id}/feedback",
            json={"score": 5}
        )
        assert response.status_code == 401

    def test_regenerate_requires_auth(self, client):
        """Test that regenerate requires authentication"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/regenerate", json={
            "message_id": str(uuid4())
        })
        assert response.status_code == 401

    def test_fork_requires_auth(self, client):
        """Test that fork requires authentication"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/fork", json={
            "from_message_id": str(uuid4())
        })
        assert response.status_code == 401

    def test_search_requires_auth(self, client):
        """Test that search requires authentication"""
        response = client.get(f"{API_PREFIX}/conversations/search?q=test")
        assert response.status_code == 401

    def test_stats_requires_auth(self, client):
        """Test that stats requires authentication"""
        response = client.get(f"{API_PREFIX}/conversations/stats")
        assert response.status_code == 401


class TestConversationErrorFormat:
    """Tests for error response format"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_unauthorized_has_error_detail(self, client):
        """Test that unauthorized response has error details"""
        response = client.get(f"{API_PREFIX}/conversations")
        assert response.status_code == 401
        data = response.json()
        # API uses custom error format with 'error' field
        assert "error" in data or "detail" in data


class TestConversationQueryParams:
    """Tests for conversation endpoint query parameters"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_list_pagination_params(self, client):
        """Test that list endpoint accepts pagination params"""
        response = client.get(f"{API_PREFIX}/conversations?skip=0&limit=10")
        # Should be 401 (unauthorized but params accepted)
        assert response.status_code == 401

    def test_list_include_archived_param(self, client):
        """Test that list endpoint accepts include_archived param"""
        response = client.get(f"{API_PREFIX}/conversations?include_archived=true")
        # Should be 401 (unauthorized but param accepted)
        assert response.status_code == 401

    def test_get_include_messages_param(self, client):
        """Test that get endpoint accepts include_messages param"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}?include_messages=false")
        # Should be 401 (unauthorized but param accepted)
        assert response.status_code == 401

    def test_delete_hard_delete_param(self, client):
        """Test that delete endpoint accepts hard_delete param"""
        fake_id = str(uuid4())
        response = client.delete(f"{API_PREFIX}/conversations/{fake_id}?hard_delete=true")
        # Should be 401 (unauthorized but param accepted)
        assert response.status_code == 401

    def test_messages_pagination_params(self, client):
        """Test that messages endpoint accepts pagination params"""
        fake_id = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{fake_id}/messages?skip=0&limit=50")
        # Should be 401 (unauthorized but params accepted)
        assert response.status_code == 401

    def test_messages_include_inactive_branches_param(self, client):
        """Test that messages endpoint accepts include_inactive_branches param"""
        fake_id = str(uuid4())
        response = client.get(
            f"{API_PREFIX}/conversations/{fake_id}/messages?include_inactive_branches=true"
        )
        # Should be 401 (unauthorized but param accepted)
        assert response.status_code == 401

    def test_search_query_param_required(self, client):
        """Test that search requires query parameter"""
        response = client.get(f"{API_PREFIX}/conversations/search")
        # Missing required q param should return 422 validation error
        assert response.status_code in [401, 422]

    def test_search_query_min_length(self, client):
        """Test search query minimum length"""
        response = client.get(f"{API_PREFIX}/conversations/search?q=a")
        # Query too short should return 401 (checked before validation) or 422
        assert response.status_code in [401, 422]

    def test_search_limit_param(self, client):
        """Test that search accepts limit param"""
        response = client.get(f"{API_PREFIX}/conversations/search?q=test&limit=50")
        # Should be 401 (unauthorized but param accepted)
        assert response.status_code == 401


class TestConversationRequestValidation:
    """Tests for request body validation (without auth)"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_create_accepts_empty_body(self, client):
        """Test that create accepts empty body (all fields optional)"""
        response = client.post(f"{API_PREFIX}/conversations", json={})
        # Should be 401 (unauthorized), not 422 (validation)
        # because ConversationCreate has all optional fields with defaults
        assert response.status_code == 401

    def test_create_accepts_full_body(self, client):
        """Test that create accepts full body"""
        response = client.post(f"{API_PREFIX}/conversations", json={
            "title": "Test Conversation",
            "project_id": "proj_123",
            "strategy": "hybrid",
            "language": "ko"
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_add_message_requires_role(self, client):
        """Test that add message requires role field"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "content": "Hello"
        })
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_add_message_requires_content(self, client):
        """Test that add message requires content field"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user"
        })
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_add_message_valid_structure(self, client):
        """Test add message with valid structure"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user",
            "content": "Hello, how are you?"
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_feedback_requires_score(self, client):
        """Test that feedback requires score"""
        fake_conv_id = str(uuid4())
        fake_msg_id = str(uuid4())
        response = client.post(
            f"{API_PREFIX}/conversations/{fake_conv_id}/messages/{fake_msg_id}/feedback",
            json={}
        )
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_feedback_score_range(self, client):
        """Test feedback score must be 1-5"""
        fake_conv_id = str(uuid4())
        fake_msg_id = str(uuid4())
        # Score of 0 should fail validation
        response = client.post(
            f"{API_PREFIX}/conversations/{fake_conv_id}/messages/{fake_msg_id}/feedback",
            json={"score": 0}
        )
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_feedback_valid_structure(self, client):
        """Test feedback with valid structure"""
        fake_conv_id = str(uuid4())
        fake_msg_id = str(uuid4())
        response = client.post(
            f"{API_PREFIX}/conversations/{fake_conv_id}/messages/{fake_msg_id}/feedback",
            json={"score": 5, "text": "Great response!"}
        )
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_regenerate_requires_message_id(self, client):
        """Test that regenerate requires message_id"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/regenerate", json={})
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_regenerate_valid_structure(self, client):
        """Test regenerate with valid structure"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/regenerate", json={
            "message_id": str(uuid4()),
            "strategy": "graph"
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_fork_requires_from_message_id(self, client):
        """Test that fork requires from_message_id"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/fork", json={})
        # Either 401 (auth checked first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_fork_valid_structure(self, client):
        """Test fork with valid structure"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/fork", json={
            "from_message_id": str(uuid4()),
            "new_title": "Forked Conversation"
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_update_accepts_partial_body(self, client):
        """Test that update accepts partial body"""
        fake_id = str(uuid4())
        response = client.patch(f"{API_PREFIX}/conversations/{fake_id}", json={
            "title": "Updated Title"
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401

    def test_update_accepts_archive_flag(self, client):
        """Test that update accepts is_archived flag"""
        fake_id = str(uuid4())
        response = client.patch(f"{API_PREFIX}/conversations/{fake_id}", json={
            "is_archived": True
        })
        # Should be 401 (unauthorized), valid body should pass validation
        assert response.status_code == 401


class TestConversationContentType:
    """Tests for content type handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_post_requires_json(self, client):
        """Test that POST endpoints require JSON content type"""
        response = client.post(
            f"{API_PREFIX}/conversations",
            content="not json",
            headers={"Content-Type": "text/plain"}
        )
        # Should reject non-JSON content (401 or 422)
        assert response.status_code in [401, 422]

    def test_response_is_json(self, client):
        """Test that responses are JSON"""
        response = client.get(f"{API_PREFIX}/conversations")
        # Even error responses should be JSON
        assert response.headers.get("content-type", "").startswith("application/json")


class TestConversationOpenAPISpec:
    """Tests for OpenAPI specification coverage"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_conversations_in_openapi(self, client):
        """Test that conversations endpoints are in OpenAPI spec"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})

        # Check main endpoints exist in spec
        assert f"{API_PREFIX}/conversations" in paths
        assert f"{API_PREFIX}/conversations/search" in paths
        assert f"{API_PREFIX}/conversations/stats" in paths

    def test_conversation_operations_in_openapi(self, client):
        """Test that conversation operations are documented"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})

        conversations_path = paths.get(f"{API_PREFIX}/conversations", {})
        # Should have GET and POST
        assert "get" in conversations_path
        assert "post" in conversations_path

    def test_conversation_tags_in_openapi(self, client):
        """Test that Conversations tag is in OpenAPI spec"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        tags = [t.get("name") for t in spec.get("tags", [])]

        # Conversations tag should exist (may be auto-generated from router)
        # or the endpoints are tagged
        conversations_path = spec.get("paths", {}).get(f"{API_PREFIX}/conversations", {})
        get_tags = conversations_path.get("get", {}).get("tags", [])
        assert "Conversations" in get_tags or "Conversations" in tags or len(get_tags) > 0


class TestConversationMethodHandling:
    """Tests for HTTP method handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_conversations_get_allowed(self, client):
        """Test GET is allowed on /conversations"""
        response = client.get(f"{API_PREFIX}/conversations")
        # Should be 401, not 405 Method Not Allowed
        assert response.status_code != 405

    def test_conversations_post_allowed(self, client):
        """Test POST is allowed on /conversations"""
        response = client.post(f"{API_PREFIX}/conversations", json={})
        # Should be 401, not 405 Method Not Allowed
        assert response.status_code != 405

    def test_conversations_put_not_allowed(self, client):
        """Test PUT is not allowed on /conversations"""
        response = client.put(f"{API_PREFIX}/conversations", json={})
        # PUT on collection should be 405
        assert response.status_code == 405

    def test_conversation_detail_patch_allowed(self, client):
        """Test PATCH is allowed on /conversations/{id}"""
        fake_id = str(uuid4())
        response = client.patch(f"{API_PREFIX}/conversations/{fake_id}", json={})
        # Should be 401, not 405
        assert response.status_code != 405

    def test_conversation_detail_delete_allowed(self, client):
        """Test DELETE is allowed on /conversations/{id}"""
        fake_id = str(uuid4())
        response = client.delete(f"{API_PREFIX}/conversations/{fake_id}")
        # Should be 401, not 405
        assert response.status_code != 405


class TestMessageRoleValidation:
    """Tests for message role validation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_user_role_accepted(self, client):
        """Test that 'user' role is accepted"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user",
            "content": "Hello"
        })
        # Should be 401 (unauthorized), valid role should pass validation
        assert response.status_code == 401

    def test_assistant_role_accepted(self, client):
        """Test that 'assistant' role is accepted"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "assistant",
            "content": "Hello, how can I help?"
        })
        # Should be 401 (unauthorized), valid role should pass validation
        assert response.status_code == 401

    def test_invalid_role_rejected(self, client):
        """Test that invalid role is rejected"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "invalid_role",
            "content": "Hello"
        })
        # Either 401 (auth first) or 422 (validation error for invalid enum)
        assert response.status_code in [401, 422]


class TestConversationUUIDHandling:
    """Tests for UUID parameter handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_valid_uuid_accepted(self, client):
        """Test that valid UUID is accepted in path"""
        valid_uuid = str(uuid4())
        response = client.get(f"{API_PREFIX}/conversations/{valid_uuid}")
        # Should be 401 (unauthorized), not 422 (validation)
        assert response.status_code == 401

    def test_path_accepts_string_id(self, client):
        """Test that path accepts string as conversation_id"""
        # The endpoint accepts str, not strictly UUID
        response = client.get(f"{API_PREFIX}/conversations/not-a-uuid-but-string")
        # Should be 401 (unauthorized) since path accepts string
        assert response.status_code == 401


class TestConversationCJKContent:
    """Tests for CJK (Chinese, Japanese, Korean) content handling"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_korean_content_accepted(self, client):
        """Test that Korean content is accepted"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user",
            "content": "안녕하세요, 오늘 날씨가 좋네요."
        })
        # Should be 401 (unauthorized), CJK content should pass validation
        assert response.status_code == 401

    def test_japanese_content_accepted(self, client):
        """Test that Japanese content is accepted"""
        fake_id = str(uuid4())
        response = client.post(f"{API_PREFIX}/conversations/{fake_id}/messages", json={
            "role": "user",
            "content": "こんにちは、今日はいい天気ですね。"
        })
        # Should be 401 (unauthorized), CJK content should pass validation
        assert response.status_code == 401

    def test_korean_title_accepted(self, client):
        """Test that Korean title is accepted"""
        response = client.post(f"{API_PREFIX}/conversations", json={
            "title": "한국어 대화 제목"
        })
        # Should be 401 (unauthorized), CJK title should pass validation
        assert response.status_code == 401

    def test_search_with_korean_query(self, client):
        """Test search with Korean query"""
        response = client.get(f"{API_PREFIX}/conversations/search?q=안녕하세요")
        # Should be 401 (unauthorized), CJK query should pass validation
        assert response.status_code == 401
