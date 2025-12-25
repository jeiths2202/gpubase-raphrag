"""
OneNote Connector
Connects to Microsoft Graph API for OneNote notebooks.
"""
import hashlib
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from .base import BaseConnector, ConnectorDocument, ConnectorResult, ConnectorStatus


class OneNoteConnector(BaseConnector):
    """
    Connector for Microsoft OneNote integration.
    Uses Microsoft Graph API to access notebooks, sections, and pages.
    """

    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    OAUTH_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    OAUTH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    CLIENT_ID = ""
    CLIENT_SECRET = ""

    @property
    def resource_type(self) -> str:
        return "onenote"

    @property
    def display_name(self) -> str:
        return "OneNote"

    @property
    def oauth_scopes(self) -> List[str]:
        return [
            "Notes.Read",
            "Notes.Read.All",
            "User.Read",
            "offline_access"
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
        """Generate Microsoft OAuth URL"""
        import urllib.parse

        scopes = " ".join(self.oauth_scopes)
        params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
            "response_mode": "query"
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
                        "redirect_uri": redirect_uri,
                        "scope": " ".join(self.oauth_scopes)
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
                            "expires_in": data.get("expires_in")
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
                        "grant_type": "refresh_token",
                        "scope": " ".join(self.oauth_scopes)
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
                            "refresh_token": data.get("refresh_token", self.refresh_token),
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
        """List pages from all OneNote notebooks"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get all notebooks
                notebooks = await self._list_notebooks(session)

                for notebook in notebooks:
                    notebook_id = notebook["id"]
                    notebook_name = notebook["displayName"]

                    # Get sections in notebook
                    sections = await self._list_sections(session, notebook_id)

                    for section in sections:
                        section_id = section["id"]
                        section_name = section["displayName"]

                        # Get pages in section
                        async for page in self._list_pages(
                            session, section_id, modified_since
                        ):
                            yield {
                                "external_id": page["id"],
                                "title": page["title"],
                                "path": f"{notebook_name}/{section_name}",
                                "url": page.get("links", {}).get("oneNoteWebUrl", {}).get("href"),
                                "created_time": page.get("createdDateTime"),
                                "modified_time": page.get("lastModifiedDateTime"),
                                "notebook": notebook_name,
                                "section": section_name
                            }

        except Exception as e:
            print(f"[OneNoteConnector] List documents error: {e}")

    async def _list_notebooks(
        self,
        session: aiohttp.ClientSession
    ) -> List[Dict]:
        """List user's notebooks"""
        notebooks = []

        try:
            async with session.get(
                f"{self.GRAPH_API_BASE}/me/onenote/notebooks",
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    notebooks = data.get("value", [])
        except Exception as e:
            print(f"[OneNoteConnector] List notebooks error: {e}")

        return notebooks

    async def _list_sections(
        self,
        session: aiohttp.ClientSession,
        notebook_id: str
    ) -> List[Dict]:
        """List sections in a notebook"""
        sections = []

        try:
            async with session.get(
                f"{self.GRAPH_API_BASE}/me/onenote/notebooks/{notebook_id}/sections",
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sections = data.get("value", [])
        except Exception as e:
            print(f"[OneNoteConnector] List sections error: {e}")

        return sections

    async def _list_pages(
        self,
        session: aiohttp.ClientSession,
        section_id: str,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict, None]:
        """List pages in a section"""
        try:
            params = {"$orderby": "lastModifiedDateTime desc"}

            if modified_since:
                iso_time = modified_since.isoformat() + "Z"
                params["$filter"] = f"lastModifiedDateTime gt {iso_time}"

            async with session.get(
                f"{self.GRAPH_API_BASE}/me/onenote/sections/{section_id}/pages",
                headers=self._get_headers(),
                params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for page in data.get("value", []):
                        yield page
        except Exception as e:
            print(f"[OneNoteConnector] List pages error: {e}")

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch OneNote page content"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get page metadata
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/onenote/pages/{external_id}",
                    headers=self._get_headers()
                ) as resp:
                    if resp.status == 404:
                        return ConnectorResult(
                            status=ConnectorStatus.NOT_FOUND,
                            error="Page not found"
                        )
                    if resp.status != 200:
                        return ConnectorResult(
                            status=ConnectorStatus.ERROR,
                            error=f"API error: {resp.status}"
                        )

                    page_meta = await resp.json()

                # Get page content (HTML)
                async with session.get(
                    f"{self.GRAPH_API_BASE}/me/onenote/pages/{external_id}/content",
                    headers=self._get_headers()
                ) as resp:
                    if resp.status != 200:
                        return ConnectorResult(
                            status=ConnectorStatus.ERROR,
                            error="Failed to get page content"
                        )

                    html_content = await resp.text()

                # Convert HTML to plain text
                content = self._html_to_text(html_content)
                sections = self._parse_onenote_sections(html_content)

                # Parse dates
                modified_at = None
                if page_meta.get("lastModifiedDateTime"):
                    modified_at = datetime.fromisoformat(
                        page_meta["lastModifiedDateTime"].replace("Z", "+00:00")
                    )

                content_hash = hashlib.md5(content.encode()).hexdigest()

                # Get web URL
                web_url = page_meta.get("links", {}).get("oneNoteWebUrl", {}).get("href")

                doc = ConnectorDocument(
                    external_id=external_id,
                    title=page_meta.get("title", "Untitled"),
                    content=content,
                    external_url=web_url,
                    path=page_meta.get("parentSection", {}).get("displayName", ""),
                    mime_type="text/html",
                    modified_at=modified_at,
                    sections=sections,
                    content_hash=content_hash,
                    metadata={
                        "onenote_id": external_id,
                        "parent_section_id": page_meta.get("parentSection", {}).get("id"),
                        "created_by": page_meta.get("createdByAppId")
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

    def _parse_onenote_sections(self, html: str) -> List[Dict]:
        """Parse OneNote HTML into sections"""
        import re

        sections = []
        current_section = {"title": "", "content": [], "type": "text"}

        # Remove OneNote specific elements
        html = re.sub(r'<head>.*?</head>', '', html, flags=re.DOTALL)

        # Extract content from body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
        if body_match:
            body = body_match.group(1)
        else:
            body = html

        # Split by OneNote divs (typically sections)
        divs = re.findall(r'<div[^>]*data-id="[^"]*"[^>]*>(.*?)</div>', body, re.DOTALL)

        for div_content in divs:
            # Check for headings
            heading_match = re.search(r'<h([1-6])[^>]*>(.*?)</h\1>', div_content)

            if heading_match:
                if current_section["content"]:
                    current_section["content"] = "\n".join(current_section["content"])
                    sections.append(current_section)

                title = re.sub(r'<[^>]+>', '', heading_match.group(2))
                current_section = {
                    "title": title.strip(),
                    "content": [],
                    "type": "text",
                    "level": int(heading_match.group(1))
                }
            else:
                text = self._html_to_text(div_content)
                if text.strip():
                    current_section["content"].append(text)

        if current_section["content"]:
            current_section["content"] = "\n".join(current_section["content"])
            sections.append(current_section)

        return sections
