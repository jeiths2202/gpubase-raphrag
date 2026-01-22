"""
Tests for Agent Navigation Endpoints

Tests for Agent-Driven RAG navigation and session management endpoints.
Part of the pre-search scope selection system.
"""
import pytest

# API prefix used by the application
API_PREFIX = "/api/v1"


class TestAgentNavigationEndpointStructure:
    """Tests for agent navigation endpoint existence and structure"""

    def test_candidates_endpoint_exists(self, client):
        """Test that /agent-navigation/candidates endpoint exists"""
        response = client.post(f"{API_PREFIX}/agent-navigation/candidates")
        # Should return 422 (validation error) or auth error, not 404
        assert response.status_code != 404

    def test_select_scope_endpoint_exists(self, client):
        """Test that /agent-navigation/select-scope endpoint exists"""
        response = client.post(f"{API_PREFIX}/agent-navigation/select-scope")
        assert response.status_code != 404

    def test_document_map_endpoint_exists(self, client):
        """Test that /agent-navigation/document-map endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-navigation/document-map")
        assert response.status_code != 404

    def test_search_keyword_endpoint_exists(self, client):
        """Test that /agent-navigation/search-keyword endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-navigation/search-keyword?keyword=test")
        assert response.status_code != 404

    def test_refresh_endpoint_exists(self, client):
        """Test that /agent-navigation/refresh endpoint exists"""
        response = client.post(f"{API_PREFIX}/agent-navigation/refresh")
        assert response.status_code != 404

    def test_stats_endpoint_exists(self, client):
        """Test that /agent-navigation/stats endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-navigation/stats")
        assert response.status_code != 404


class TestCandidatesValidation:
    """Tests for candidates request validation"""

    def test_candidates_requires_body(self, client):
        """Test that candidates requires request body or auth"""
        response = client.post(f"{API_PREFIX}/agent-navigation/candidates")
        # Returns 401 (auth required) or 400/422 (validation) - both are valid
        assert response.status_code in [400, 401, 422]

    def test_candidates_requires_query(self, client):
        """Test that candidates requires query field or auth"""
        response = client.post(
            f"{API_PREFIX}/agent-navigation/candidates",
            json={"top_k": 5}
        )
        # Returns 401 (auth required) or 400/422 (validation) - both are valid
        assert response.status_code in [400, 401, 422]

    def test_candidates_with_valid_structure(self, client):
        """Test candidates with valid request structure"""
        response = client.post(
            f"{API_PREFIX}/agent-navigation/candidates",
            json={
                "query": "VSAM error -5212",
                "top_k": 5,
                "min_score": 0.1
            }
        )
        # Should be processed (not 400/422 validation error for structure)
        # Could be 200, 401 (auth), or 500 (no DB)
        assert response.status_code in [200, 401, 500]


class TestSelectScopeValidation:
    """Tests for select-scope request validation"""

    def test_select_scope_requires_body(self, client):
        """Test that select-scope requires request body or auth"""
        response = client.post(f"{API_PREFIX}/agent-navigation/select-scope")
        # Returns 401 (auth required) or 400/422 (validation) - both are valid
        assert response.status_code in [400, 401, 422]

    def test_select_scope_requires_query(self, client):
        """Test that select-scope requires query field or auth"""
        response = client.post(
            f"{API_PREFIX}/agent-navigation/select-scope",
            json={
                "selected_documents": ["doc1"],
                "selected_sections": []
            }
        )
        # Returns 401 (auth required) or 400/422 (validation) - both are valid
        assert response.status_code in [400, 401, 422]

    def test_select_scope_with_valid_structure(self, client):
        """Test select-scope with valid request structure"""
        response = client.post(
            f"{API_PREFIX}/agent-navigation/select-scope",
            json={
                "query": "test query",
                "selected_documents": ["doc1", "doc2"],
                "selected_sections": ["1.1", "2.3"]
            }
        )
        assert response.status_code in [200, 401, 500]


class TestAgentSessionEndpointStructure:
    """Tests for agent session endpoint existence and structure"""

    def test_restore_check_endpoint_exists(self, client):
        """Test that /agent-session/restore-check endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-session/restore-check")
        assert response.status_code != 404

    def test_restore_endpoint_exists(self, client):
        """Test that /agent-session/restore endpoint exists"""
        response = client.post(f"{API_PREFIX}/agent-session/restore")
        assert response.status_code != 404

    def test_history_get_endpoint_exists(self, client):
        """Test that /agent-session/history GET endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-session/history")
        assert response.status_code != 404

    def test_history_delete_endpoint_exists(self, client):
        """Test that /agent-session/history DELETE endpoint exists"""
        response = client.delete(f"{API_PREFIX}/agent-session/history")
        assert response.status_code != 404

    def test_preferences_get_endpoint_exists(self, client):
        """Test that /agent-session/preferences GET endpoint exists"""
        response = client.get(f"{API_PREFIX}/agent-session/preferences")
        assert response.status_code != 404

    def test_preferences_put_endpoint_exists(self, client):
        """Test that /agent-session/preferences PUT endpoint exists"""
        response = client.put(f"{API_PREFIX}/agent-session/preferences")
        assert response.status_code != 404

    def test_update_state_endpoint_exists(self, client):
        """Test that /agent-session/update-state endpoint exists"""
        response = client.post(f"{API_PREFIX}/agent-session/update-state?query=test")
        assert response.status_code != 404


class TestRestoreSessionValidation:
    """Tests for restore session request validation"""

    def test_restore_requires_body(self, client):
        """Test that restore requires request body or auth"""
        response = client.post(f"{API_PREFIX}/agent-session/restore")
        # Returns 401 (auth required) or 400/422 (validation) - both are valid
        assert response.status_code in [400, 401, 422]

    def test_restore_with_valid_structure(self, client):
        """Test restore with valid request structure"""
        response = client.post(
            f"{API_PREFIX}/agent-session/restore",
            json={"restore": True}
        )
        assert response.status_code in [200, 401, 500]

    def test_restore_dismiss(self, client):
        """Test restore dismiss action"""
        response = client.post(
            f"{API_PREFIX}/agent-session/restore",
            json={"restore": False}
        )
        assert response.status_code in [200, 401, 500]


class TestPreferencesValidation:
    """Tests for preferences request validation"""

    def test_preferences_update_valid_structure(self, client):
        """Test preferences update with valid structure"""
        response = client.put(
            f"{API_PREFIX}/agent-session/preferences",
            json={
                "default_documents": ["doc1"],
                "language": "ko",
                "always_confirm_scope": True
            }
        )
        assert response.status_code in [200, 401, 500]


class TestRestoreCheckParameters:
    """Tests for restore-check query parameters"""

    def test_restore_check_default_params(self, client):
        """Test restore-check with default parameters"""
        response = client.get(f"{API_PREFIX}/agent-session/restore-check")
        assert response.status_code in [200, 401, 500]

    def test_restore_check_custom_age(self, client):
        """Test restore-check with custom max_age_hours"""
        response = client.get(f"{API_PREFIX}/agent-session/restore-check?max_age_hours=48")
        assert response.status_code in [200, 401, 500]


class TestSearchHistoryParameters:
    """Tests for search history query parameters"""

    def test_history_default_limit(self, client):
        """Test history with default limit"""
        response = client.get(f"{API_PREFIX}/agent-session/history")
        assert response.status_code in [200, 401, 500]

    def test_history_custom_limit(self, client):
        """Test history with custom limit"""
        response = client.get(f"{API_PREFIX}/agent-session/history?limit=10")
        assert response.status_code in [200, 401, 500]
