"""
Tests for External Connectors (GitHub, Google Drive, OneNote)
Tests OAuth SSO implementation and basic connector functionality.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientSession

# Add app to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.api.connectors.base import ConnectorStatus, ConnectorResult, ConnectorDocument
from app.api.connectors.github_connector import GitHubConnector
from app.api.connectors.google_drive_connector import GoogleDriveConnector
from app.api.connectors.onenote_connector import OneNoteConnector


class TestGitHubConnector:
    """Tests for GitHub OAuth SSO Connector"""

    def test_init_with_env_vars(self):
        """Test connector initializes with environment variables"""
        with patch.dict(os.environ, {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_client_secret"
        }):
            connector = GitHubConnector()
            assert connector.CLIENT_ID == "test_client_id"
            assert connector.CLIENT_SECRET == "test_client_secret"

    def test_init_with_config(self):
        """Test connector initializes with config dict"""
        connector = GitHubConnector(config={
            "client_id": "config_client_id",
            "client_secret": "config_client_secret"
        })
        assert connector.CLIENT_ID == "config_client_id"
        assert connector.CLIENT_SECRET == "config_client_secret"

    def test_resource_type(self):
        """Test resource type property"""
        connector = GitHubConnector()
        assert connector.resource_type == "github"

    def test_display_name(self):
        """Test display name property"""
        connector = GitHubConnector()
        assert connector.display_name == "GitHub"

    def test_oauth_scopes(self):
        """Test OAuth scopes"""
        connector = GitHubConnector()
        scopes = connector.oauth_scopes
        assert "repo" in scopes
        assert "read:user" in scopes

    def test_get_oauth_url(self):
        """Test OAuth URL generation"""
        with patch.dict(os.environ, {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_secret"
        }):
            connector = GitHubConnector()
            url = connector.get_oauth_url(
                redirect_uri="http://localhost:3000/callback",
                state="test_state"
            )

            assert "https://github.com/login/oauth/authorize" in url
            assert "client_id=test_client_id" in url
            assert "redirect_uri=http://localhost:3000/callback" in url
            assert "state=test_state" in url
            assert "scope=repo" in url

    def test_get_headers(self):
        """Test API headers generation"""
        connector = GitHubConnector(access_token="test_token")
        headers = connector._get_headers()

        assert headers["Authorization"] == "Bearer test_token"
        assert "application/vnd.github" in headers["Accept"]
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    @pytest.mark.asyncio
    async def test_validate_connection_no_token(self):
        """Test validate_connection fails without token"""
        connector = GitHubConnector()
        result = await connector.validate_connection()

        assert result.status == ConnectorStatus.ERROR
        assert "No access token" in result.error

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        """Test successful OAuth code exchange"""
        mock_response_token = AsyncMock()
        mock_response_token.status = 200
        mock_response_token.json = AsyncMock(return_value={
            "access_token": "test_access_token",
            "token_type": "bearer",
            "scope": "repo,read:user"
        })

        mock_response_user = AsyncMock()
        mock_response_user.status = 200
        mock_response_user.json = AsyncMock(return_value={
            "login": "testuser",
            "name": "Test User",
            "id": 12345,
            "avatar_url": "https://avatars.githubusercontent.com/u/12345"
        })

        with patch.dict(os.environ, {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_secret"
        }):
            connector = GitHubConnector()

            with patch("aiohttp.ClientSession") as mock_session:
                mock_session_instance = MagicMock()
                mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
                mock_session_instance.__aexit__ = AsyncMock(return_value=None)

                # Mock both POST (token) and GET (user info) calls
                mock_post = MagicMock()
                mock_post.__aenter__ = AsyncMock(return_value=mock_response_token)
                mock_post.__aexit__ = AsyncMock(return_value=None)
                mock_session_instance.post = MagicMock(return_value=mock_post)

                mock_get = MagicMock()
                mock_get.__aenter__ = AsyncMock(return_value=mock_response_user)
                mock_get.__aexit__ = AsyncMock(return_value=None)
                mock_session_instance.get = MagicMock(return_value=mock_get)

                mock_session.return_value = mock_session_instance

                result = await connector.exchange_code(
                    code="test_code",
                    redirect_uri="http://localhost:3000/callback"
                )

                assert result.status == ConnectorStatus.SUCCESS
                assert result.data["access_token"] == "test_access_token"
                assert result.data["user_login"] == "testuser"
                assert result.data["user_name"] == "Test User"
                assert result.data["user_id"] == 12345


class TestGoogleDriveConnector:
    """Tests for Google Drive OAuth SSO Connector"""

    def test_init_with_env_vars(self):
        """Test connector initializes with environment variables"""
        with patch.dict(os.environ, {
            "GOOGLE_DRIVE_CLIENT_ID": "test_client_id",
            "GOOGLE_DRIVE_CLIENT_SECRET": "test_client_secret"
        }):
            connector = GoogleDriveConnector()
            assert connector.CLIENT_ID == "test_client_id"
            assert connector.CLIENT_SECRET == "test_client_secret"

    def test_init_with_config(self):
        """Test connector initializes with config dict"""
        connector = GoogleDriveConnector(config={
            "client_id": "config_client_id",
            "client_secret": "config_client_secret"
        })
        assert connector.CLIENT_ID == "config_client_id"
        assert connector.CLIENT_SECRET == "config_client_secret"

    def test_resource_type(self):
        """Test resource type property"""
        connector = GoogleDriveConnector()
        assert connector.resource_type == "google_drive"

    def test_display_name(self):
        """Test display name property"""
        connector = GoogleDriveConnector()
        assert connector.display_name == "Google Drive"

    def test_oauth_scopes(self):
        """Test OAuth scopes include user info"""
        connector = GoogleDriveConnector()
        scopes = connector.oauth_scopes
        assert "https://www.googleapis.com/auth/drive.readonly" in scopes
        assert "https://www.googleapis.com/auth/userinfo.profile" in scopes
        assert "https://www.googleapis.com/auth/userinfo.email" in scopes

    def test_get_oauth_url(self):
        """Test OAuth URL generation"""
        with patch.dict(os.environ, {
            "GOOGLE_DRIVE_CLIENT_ID": "test_client_id",
            "GOOGLE_DRIVE_CLIENT_SECRET": "test_secret"
        }):
            connector = GoogleDriveConnector()
            url = connector.get_oauth_url(
                redirect_uri="http://localhost:3000/callback",
                state="test_state"
            )

            assert "https://accounts.google.com/o/oauth2/v2/auth" in url
            assert "client_id=test_client_id" in url
            assert "redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fcallback" in url
            assert "state=test_state" in url
            assert "access_type=offline" in url
            assert "prompt=consent" in url

    def test_get_headers(self):
        """Test API headers generation"""
        connector = GoogleDriveConnector(access_token="test_token")
        headers = connector._get_headers()

        assert headers["Authorization"] == "Bearer test_token"
        assert headers["Accept"] == "application/json"

    def test_supported_mime_types(self):
        """Test supported MIME types"""
        connector = GoogleDriveConnector()

        assert "application/vnd.google-apps.document" in connector.SUPPORTED_MIMES
        assert "application/vnd.google-apps.spreadsheet" in connector.SUPPORTED_MIMES
        assert "application/pdf" in connector.SUPPORTED_MIMES

    @pytest.mark.asyncio
    async def test_validate_connection_no_token(self):
        """Test validate_connection fails without token"""
        connector = GoogleDriveConnector()
        result = await connector.validate_connection()

        assert result.status == ConnectorStatus.ERROR
        assert "No access token" in result.error


class TestOneNoteConnector:
    """Tests for OneNote OAuth SSO Connector (Microsoft Graph API)"""

    def test_init_with_env_vars(self):
        """Test connector initializes with environment variables"""
        with patch.dict(os.environ, {
            "MICROSOFT_CLIENT_ID": "test_client_id",
            "MICROSOFT_CLIENT_SECRET": "test_client_secret"
        }):
            connector = OneNoteConnector()
            assert connector.CLIENT_ID == "test_client_id"
            assert connector.CLIENT_SECRET == "test_client_secret"

    def test_init_with_config(self):
        """Test connector initializes with config dict"""
        connector = OneNoteConnector(config={
            "client_id": "config_client_id",
            "client_secret": "config_client_secret"
        })
        assert connector.CLIENT_ID == "config_client_id"
        assert connector.CLIENT_SECRET == "config_client_secret"

    def test_resource_type(self):
        """Test resource type property"""
        connector = OneNoteConnector()
        assert connector.resource_type == "onenote"

    def test_display_name(self):
        """Test display name property"""
        connector = OneNoteConnector()
        assert connector.display_name == "OneNote"

    def test_oauth_scopes(self):
        """Test OAuth scopes for Microsoft Graph"""
        connector = OneNoteConnector()
        scopes = connector.oauth_scopes

        assert "Notes.Read" in scopes
        assert "Notes.Read.All" in scopes
        assert "User.Read" in scopes
        assert "offline_access" in scopes

    def test_get_oauth_url(self):
        """Test OAuth URL generation for Microsoft"""
        with patch.dict(os.environ, {
            "MICROSOFT_CLIENT_ID": "test_client_id",
            "MICROSOFT_CLIENT_SECRET": "test_secret"
        }):
            connector = OneNoteConnector()
            url = connector.get_oauth_url(
                redirect_uri="http://localhost:3000/callback",
                state="test_state"
            )

            assert "https://login.microsoftonline.com/common/oauth2/v2.0/authorize" in url
            assert "client_id=test_client_id" in url
            assert "state=test_state" in url
            assert "response_type=code" in url
            assert "response_mode=query" in url

    def test_get_headers(self):
        """Test API headers generation"""
        connector = OneNoteConnector(access_token="test_token")
        headers = connector._get_headers()

        assert headers["Authorization"] == "Bearer test_token"
        assert headers["Accept"] == "application/json"

    def test_graph_api_base_url(self):
        """Test Microsoft Graph API base URL"""
        connector = OneNoteConnector()
        assert connector.GRAPH_API_BASE == "https://graph.microsoft.com/v1.0"

    def test_oauth_token_url(self):
        """Test OAuth token URL"""
        connector = OneNoteConnector()
        assert "login.microsoftonline.com" in connector.OAUTH_TOKEN_URL
        assert "oauth2/v2.0/token" in connector.OAUTH_TOKEN_URL

    @pytest.mark.asyncio
    async def test_validate_connection_no_token(self):
        """Test validate_connection fails without token"""
        connector = OneNoteConnector()
        result = await connector.validate_connection()

        assert result.status == ConnectorStatus.ERROR
        assert "No access token" in result.error


class TestConnectorTimeout:
    """Tests for connector timeout configuration"""

    def test_default_timeout(self):
        """Test default timeout is set"""
        connector = GitHubConnector()
        # Should have a timeout value (either from config or default)
        assert connector._timeout_seconds > 0

    def test_client_timeout_object(self):
        """Test _get_client_timeout returns aiohttp.ClientTimeout"""
        connector = GitHubConnector()
        timeout = connector._get_client_timeout()

        # Should return ClientTimeout object
        assert timeout is not None
        assert timeout.total == connector._timeout_seconds


class TestConnectorCommonFunctionality:
    """Tests for common connector functionality from BaseConnector"""

    def test_html_to_text(self):
        """Test HTML to text conversion"""
        connector = GitHubConnector()

        html = "<h1>Title</h1><p>Paragraph text</p><ul><li>Item 1</li></ul>"
        text = connector._html_to_text(html)

        assert "Title" in text
        assert "Paragraph text" in text
        assert "Item 1" in text

    def test_normalize_content_string(self):
        """Test normalize_content with string input"""
        connector = GitHubConnector()

        result = connector.normalize_content("plain text", "text/plain")
        assert result == "plain text"

    def test_normalize_content_html(self):
        """Test normalize_content with HTML input"""
        connector = GitHubConnector()

        result = connector.normalize_content("<p>Hello</p>", "text/html")
        assert "Hello" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
