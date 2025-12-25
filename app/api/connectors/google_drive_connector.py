"""
Google Drive Connector
Connects to Google Drive API for documents and files.
"""
import hashlib
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from .base import BaseConnector, ConnectorDocument, ConnectorResult, ConnectorStatus


class GoogleDriveConnector(BaseConnector):
    """
    Connector for Google Drive integration.
    Supports Google Docs, Sheets, and uploaded files.
    """

    API_BASE = "https://www.googleapis.com/drive/v3"
    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

    # Supported MIME types
    SUPPORTED_MIMES = {
        "application/vnd.google-apps.document": "Google Doc",
        "application/vnd.google-apps.spreadsheet": "Google Sheet",
        "application/pdf": "PDF",
        "text/plain": "Text",
        "text/markdown": "Markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word"
    }

    CLIENT_ID = ""
    CLIENT_SECRET = ""

    @property
    def resource_type(self) -> str:
        return "google_drive"

    @property
    def display_name(self) -> str:
        return "Google Drive"

    @property
    def oauth_scopes(self) -> List[str]:
        return [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/documents.readonly"
        ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CLIENT_ID = self.config.get("client_id", "")
        self.CLIENT_SECRET = self.config.get("client_secret", "")

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }

    # ================== Authentication ==================

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Google OAuth URL"""
        import urllib.parse

        scopes = " ".join(self.oauth_scopes)
        params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        query = urllib.parse.urlencode(params)
        return f"{self.OAUTH_AUTH_URL}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """Exchange authorization code for tokens"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.OAUTH_TOKEN_URL,
                    data={
                        "client_id": self.CLIENT_ID,
                        "client_secret": self.CLIENT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri
                    }
                ) as resp:
                    data = await resp.json()

                    if "error" in data:
                        return ConnectorResult(
                            status=ConnectorStatus.ERROR,
                            error=data.get("error_description", data["error"])
                        )

                    return ConnectorResult(
                        status=ConnectorStatus.SUCCESS,
                        data={
                            "access_token": data.get("access_token"),
                            "refresh_token": data.get("refresh_token"),
                            "expires_in": data.get("expires_in"),
                            "token_type": data.get("token_type")
                        }
                    )
        except Exception as e:
            return ConnectorResult(
                status=ConnectorStatus.ERROR,
                error=str(e)
            )

    async def refresh_access_token(self) -> ConnectorResult:
        """Refresh the access token"""
        if not self.refresh_token:
            return ConnectorResult(
                status=ConnectorStatus.AUTH_EXPIRED,
                error="No refresh token available"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.OAUTH_TOKEN_URL,
                    data={
                        "client_id": self.CLIENT_ID,
                        "client_secret": self.CLIENT_SECRET,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token"
                    }
                ) as resp:
                    data = await resp.json()

                    if "error" in data:
                        return ConnectorResult(
                            status=ConnectorStatus.AUTH_EXPIRED,
                            error=data.get("error_description", data["error"])
                        )

                    return ConnectorResult(
                        status=ConnectorStatus.SUCCESS,
                        data={
                            "access_token": data.get("access_token"),
                            "expires_in": data.get("expires_in")
                        }
                    )
        except Exception as e:
            return ConnectorResult(
                status=ConnectorStatus.ERROR,
                error=str(e)
            )

    # ================== Document Operations ==================

    async def list_documents(
        self,
        path: Optional[str] = None,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List documents from Google Drive"""
        try:
            async with aiohttp.ClientSession() as session:
                page_token = None

                while True:
                    # Build query
                    query_parts = ["trashed = false"]

                    # Filter by folder if path specified
                    if path:
                        query_parts.append(f"'{path}' in parents")

                    # Filter by supported MIME types
                    mime_filters = [
                        f"mimeType = '{mime}'"
                        for mime in self.SUPPORTED_MIMES.keys()
                    ]
                    query_parts.append(f"({' or '.join(mime_filters)})")

                    # Filter by modification time
                    if modified_since:
                        iso_time = modified_since.isoformat() + "Z"
                        query_parts.append(f"modifiedTime > '{iso_time}'")

                    params = {
                        "q": " and ".join(query_parts),
                        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,size,webViewLink,parents)",
                        "pageSize": 100,
                        "orderBy": "modifiedTime desc"
                    }
                    if page_token:
                        params["pageToken"] = page_token

                    async with session.get(
                        f"{self.API_BASE}/files",
                        headers=self._get_headers(),
                        params=params
                    ) as resp:
                        if resp.status != 200:
                            break

                        data = await resp.json()
                        files = data.get("files", [])

                        for file in files:
                            yield {
                                "external_id": file["id"],
                                "title": file["name"],
                                "mime_type": file["mimeType"],
                                "url": file.get("webViewLink"),
                                "size": file.get("size"),
                                "modified_time": file.get("modifiedTime"),
                                "created_time": file.get("createdTime"),
                                "parents": file.get("parents", [])
                            }

                        page_token = data.get("nextPageToken")
                        if not page_token:
                            break

        except Exception as e:
            print(f"[GoogleDriveConnector] List documents error: {e}")

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch document content from Google Drive"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get file metadata
                async with session.get(
                    f"{self.API_BASE}/files/{external_id}",
                    headers=self._get_headers(),
                    params={"fields": "id,name,mimeType,modifiedTime,webViewLink,size"}
                ) as resp:
                    if resp.status == 404:
                        return ConnectorResult(
                            status=ConnectorStatus.NOT_FOUND,
                            error="File not found"
                        )
                    if resp.status != 200:
                        return ConnectorResult(
                            status=ConnectorStatus.ERROR,
                            error=f"API error: {resp.status}"
                        )

                    file_meta = await resp.json()

                # Get content based on MIME type
                mime_type = file_meta.get("mimeType", "")
                content = ""
                sections = []

                if mime_type == "application/vnd.google-apps.document":
                    # Export Google Doc as plain text
                    content, sections = await self._export_google_doc(
                        session, external_id
                    )
                elif mime_type == "application/vnd.google-apps.spreadsheet":
                    # Export Google Sheet as CSV
                    content = await self._export_sheet(session, external_id)
                    sections = [{"title": "", "content": content, "type": "table"}]
                else:
                    # Download file content
                    content = await self._download_file(session, external_id)

                if not content:
                    return ConnectorResult(
                        status=ConnectorStatus.ERROR,
                        error="Failed to extract content"
                    )

                # Parse modification time
                modified_at = None
                if file_meta.get("modifiedTime"):
                    modified_at = datetime.fromisoformat(
                        file_meta["modifiedTime"].replace("Z", "+00:00")
                    )

                content_hash = hashlib.md5(content.encode()).hexdigest()

                doc = ConnectorDocument(
                    external_id=external_id,
                    title=file_meta.get("name", "Untitled"),
                    content=content,
                    external_url=file_meta.get("webViewLink"),
                    mime_type=mime_type,
                    modified_at=modified_at,
                    sections=sections,
                    content_hash=content_hash,
                    metadata={
                        "drive_id": external_id,
                        "original_mime_type": mime_type,
                        "size": file_meta.get("size")
                    }
                )

                return ConnectorResult(
                    status=ConnectorStatus.SUCCESS,
                    data=doc
                )

        except Exception as e:
            return ConnectorResult(
                status=ConnectorStatus.ERROR,
                error=str(e)
            )

    async def _export_google_doc(
        self,
        session: aiohttp.ClientSession,
        file_id: str
    ) -> tuple:
        """Export Google Doc as plain text with sections"""
        try:
            async with session.get(
                f"{self.API_BASE}/files/{file_id}/export",
                headers=self._get_headers(),
                params={"mimeType": "text/plain"}
            ) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    # Simple section parsing
                    sections = self._parse_text_sections(content)
                    return content, sections
        except Exception as e:
            print(f"[GoogleDriveConnector] Export doc error: {e}")

        return "", []

    async def _export_sheet(
        self,
        session: aiohttp.ClientSession,
        file_id: str
    ) -> str:
        """Export Google Sheet as CSV"""
        try:
            async with session.get(
                f"{self.API_BASE}/files/{file_id}/export",
                headers=self._get_headers(),
                params={"mimeType": "text/csv"}
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception as e:
            print(f"[GoogleDriveConnector] Export sheet error: {e}")

        return ""

    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        file_id: str
    ) -> str:
        """Download file content"""
        try:
            async with session.get(
                f"{self.API_BASE}/files/{file_id}",
                headers=self._get_headers(),
                params={"alt": "media"}
            ) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    # Try to decode as text
                    try:
                        return content.decode("utf-8")
                    except UnicodeDecodeError:
                        return content.decode("latin-1")
        except Exception as e:
            print(f"[GoogleDriveConnector] Download file error: {e}")

        return ""

    def _parse_text_sections(self, content: str) -> List[Dict]:
        """Parse plain text into sections"""
        import re

        sections = []
        current_section = {"title": "", "content": [], "type": "text"}

        lines = content.split("\n")

        for line in lines:
            # Detect headings (lines with title-like formatting)
            if line.strip() and len(line.strip()) < 100:
                # Check if it looks like a heading
                if line.isupper() or re.match(r'^[0-9]+\.\s+', line):
                    if current_section["content"]:
                        current_section["content"] = "\n".join(current_section["content"])
                        sections.append(current_section)
                    current_section = {
                        "title": line.strip(),
                        "content": [],
                        "type": "text"
                    }
                    continue

            current_section["content"].append(line)

        if current_section["content"]:
            current_section["content"] = "\n".join(current_section["content"])
            sections.append(current_section)

        return sections
