"""
Confluence Connector
Connects to Atlassian Confluence API for pages and spaces.
"""
import hashlib
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from .base import BaseConnector, ConnectorDocument, ConnectorResult, ConnectorStatus


class ConfluenceConnector(BaseConnector):
    """
    Connector for Atlassian Confluence integration.
    Uses Confluence Cloud REST API with API token authentication.
    """

    @property
    def resource_type(self) -> str:
        return "confluence"

    @property
    def display_name(self) -> str:
        return "Confluence"

    @property
    def oauth_scopes(self) -> List[str]:
        return []  # Uses API token, not OAuth

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Confluence config
        self.base_url = self.config.get("base_url", "")  # e.g., "https://your-domain.atlassian.net/wiki"
        self.user_email = self.config.get("user_email", "")

    def _get_api_base(self) -> str:
        """Get Confluence API base URL"""
        return f"{self.base_url}/rest/api"

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers with Basic auth"""
        import base64

        if self.api_token and self.user_email:
            credentials = base64.b64encode(
                f"{self.user_email}:{self.api_token}".encode()
            ).decode()
            return {
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        return {"Accept": "application/json"}

    # ================== Authentication ==================

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Confluence uses API token, not OAuth"""
        raise NotImplementedError("Confluence uses API token authentication")

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """Not used for Confluence"""
        raise NotImplementedError("Confluence uses API token authentication")

    async def refresh_access_token(self) -> ConnectorResult:
        """API tokens don't expire"""
        return ConnectorResult(
            status=ConnectorStatus.SUCCESS,
            data={"api_token": self.api_token}
        )

    async def validate_connection(self) -> ConnectorResult:
        """Validate Confluence connection with API token"""
        if not self.api_token or not self.user_email or not self.base_url:
            return ConnectorResult(
                status=ConnectorStatus.ERROR,
                error="Missing required configuration (base_url, user_email, api_token)"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._get_api_base()}/space",
                    headers=self._get_headers(),
                    params={"limit": 1}
                ) as resp:
                    if resp.status == 200:
                        return ConnectorResult(
                            status=ConnectorStatus.SUCCESS,
                            message="Connection validated"
                        )
                    elif resp.status == 401:
                        return ConnectorResult(
                            status=ConnectorStatus.AUTH_EXPIRED,
                            error="Invalid API token"
                        )
                    else:
                        error = await resp.text()
                        return ConnectorResult(
                            status=ConnectorStatus.ERROR,
                            error=error
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
        """List pages from Confluence spaces"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get spaces
                spaces = await self._list_spaces(session)

                for space in spaces:
                    space_key = space["key"]
                    space_name = space["name"]

                    # Filter by path (space key) if specified
                    if path and space_key != path:
                        continue

                    # Get pages in space
                    async for page in self._list_pages(
                        session, space_key, modified_since
                    ):
                        yield {
                            "external_id": page["id"],
                            "title": page["title"],
                            "path": f"{space_name}",
                            "space_key": space_key,
                            "url": f"{self.base_url}{page['_links']['webui']}",
                            "type": page["type"],
                            "status": page.get("status"),
                            "version": page.get("version", {}).get("number"),
                            "modified_time": page.get("version", {}).get("when")
                        }

        except Exception as e:
            print(f"[ConfluenceConnector] List documents error: {e}")

    async def _list_spaces(
        self,
        session: aiohttp.ClientSession
    ) -> List[Dict]:
        """List accessible spaces"""
        spaces = []

        try:
            start = 0
            limit = 50

            while True:
                async with session.get(
                    f"{self._get_api_base()}/space",
                    headers=self._get_headers(),
                    params={
                        "start": start,
                        "limit": limit,
                        "type": "global",
                        "status": "current"
                    }
                ) as resp:
                    if resp.status != 200:
                        break

                    data = await resp.json()
                    results = data.get("results", [])
                    spaces.extend(results)

                    if len(results) < limit:
                        break
                    start += limit

        except Exception as e:
            print(f"[ConfluenceConnector] List spaces error: {e}")

        return spaces

    async def _list_pages(
        self,
        session: aiohttp.ClientSession,
        space_key: str,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict, None]:
        """List pages in a space"""
        try:
            start = 0
            limit = 50

            while True:
                params = {
                    "spaceKey": space_key,
                    "start": start,
                    "limit": limit,
                    "expand": "version",
                    "status": "current"
                }

                async with session.get(
                    f"{self._get_api_base()}/content",
                    headers=self._get_headers(),
                    params=params
                ) as resp:
                    if resp.status != 200:
                        break

                    data = await resp.json()
                    results = data.get("results", [])

                    for page in results:
                        # Filter by modification time
                        if modified_since:
                            version_when = page.get("version", {}).get("when")
                            if version_when:
                                page_modified = datetime.fromisoformat(
                                    version_when.replace("Z", "+00:00")
                                )
                                if page_modified <= modified_since:
                                    continue

                        yield page

                    if len(results) < limit:
                        break
                    start += limit

        except Exception as e:
            print(f"[ConfluenceConnector] List pages error: {e}")

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch Confluence page content"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._get_api_base()}/content/{external_id}",
                    headers=self._get_headers(),
                    params={
                        "expand": "body.storage,version,space,ancestors"
                    }
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

                    page = await resp.json()

                # Extract content from storage format (HTML)
                body = page.get("body", {}).get("storage", {}).get("value", "")
                content = self._html_to_text(body)
                sections = self._parse_confluence_sections(body)

                # Parse modification time
                modified_at = None
                version_when = page.get("version", {}).get("when")
                if version_when:
                    modified_at = datetime.fromisoformat(
                        version_when.replace("Z", "+00:00")
                    )

                # Build path from ancestors
                ancestors = page.get("ancestors", [])
                path_parts = [a["title"] for a in ancestors]
                path = " / ".join(path_parts) if path_parts else page.get("space", {}).get("name", "")

                content_hash = hashlib.md5(content.encode()).hexdigest()

                doc = ConnectorDocument(
                    external_id=external_id,
                    title=page.get("title", "Untitled"),
                    content=content,
                    external_url=f"{self.base_url}{page['_links']['webui']}",
                    path=path,
                    mime_type="text/html",
                    modified_at=modified_at,
                    sections=sections,
                    content_hash=content_hash,
                    metadata={
                        "confluence_id": external_id,
                        "space_key": page.get("space", {}).get("key"),
                        "space_name": page.get("space", {}).get("name"),
                        "version": page.get("version", {}).get("number"),
                        "type": page.get("type"),
                        "author": page.get("version", {}).get("by", {}).get("displayName")
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

    def _parse_confluence_sections(self, html: str) -> List[Dict]:
        """Parse Confluence storage format HTML into sections"""
        import re

        sections = []
        current_section = {"title": "", "content": [], "type": "text"}

        # Handle Confluence-specific elements
        # Extract structured content

        # Find headings
        heading_pattern = r'<h([1-6])[^>]*>(.*?)</h\1>'
        parts = re.split(heading_pattern, html)

        i = 0
        while i < len(parts):
            if i + 2 < len(parts) and parts[i+1].isdigit():
                # Found a heading
                if current_section["content"]:
                    current_section["content"] = self._html_to_text(
                        "\n".join(current_section["content"])
                    )
                    sections.append(current_section)

                level = int(parts[i+1])
                title = self._html_to_text(parts[i+2])
                current_section = {
                    "title": title.strip(),
                    "content": [],
                    "type": "text",
                    "level": level
                }
                i += 3
            else:
                # Regular content
                content = parts[i]
                if content.strip():
                    # Check for code blocks
                    code_blocks = re.findall(
                        r'<ac:structured-macro ac:name="code"[^>]*>.*?<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?</ac:structured-macro>',
                        content, re.DOTALL
                    )
                    if code_blocks:
                        for code in code_blocks:
                            sections.append({
                                "title": "",
                                "content": code,
                                "type": "code"
                            })
                        # Remove code blocks from content
                        content = re.sub(
                            r'<ac:structured-macro ac:name="code"[^>]*>.*?</ac:structured-macro>',
                            '', content, flags=re.DOTALL
                        )

                    # Check for tables
                    tables = re.findall(r'<table[^>]*>.*?</table>', content, re.DOTALL)
                    if tables:
                        for table in tables:
                            table_content = self._parse_confluence_table(table)
                            sections.append({
                                "title": "",
                                "content": table_content,
                                "type": "table"
                            })
                        content = re.sub(r'<table[^>]*>.*?</table>', '', content, flags=re.DOTALL)

                    if content.strip():
                        current_section["content"].append(content)
                i += 1

        if current_section["content"]:
            current_section["content"] = self._html_to_text(
                "\n".join(current_section["content"])
            )
            sections.append(current_section)

        return sections

    def _parse_confluence_table(self, table_html: str) -> List[List[str]]:
        """Parse HTML table into rows"""
        import re

        rows = []
        row_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

        for row in row_matches:
            cells = []
            cell_matches = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
            for cell in cell_matches:
                cell_text = self._html_to_text(cell)
                cells.append(cell_text.strip())
            if cells:
                rows.append(cells)

        return rows
