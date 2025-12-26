"""
Notion Connector
Connects to Notion API for pages and databases.
"""
import hashlib
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from .base import BaseConnector, ConnectorDocument, ConnectorResult, ConnectorStatus


class NotionConnector(BaseConnector):
    """
    Connector for Notion integration.
    Uses Notion API v1 for accessing pages and databases.
    """

    API_BASE = "https://api.notion.com/v1"
    OAUTH_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    OAUTH_TOKEN_URL = "https://api.notion.com/v1/oauth/token"

    # OAuth settings (configure in environment)
    CLIENT_ID = ""  # Set from config
    CLIENT_SECRET = ""  # Set from config

    @property
    def resource_type(self) -> str:
        return "notion"

    @property
    def display_name(self) -> str:
        return "Notion"

    @property
    def oauth_scopes(self) -> List[str]:
        return []  # Notion uses integration capabilities, not scopes

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CLIENT_ID = self.config.get("client_id", "")
        self.CLIENT_SECRET = self.config.get("client_secret", "")

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.access_token or self.api_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    # ================== Authentication ==================

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Generate Notion OAuth URL"""
        params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.OAUTH_AUTH_URL}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """Exchange authorization code for tokens"""
        import base64

        try:
            credentials = base64.b64encode(
                f"{self.CLIENT_ID}:{self.CLIENT_SECRET}".encode()
            ).decode()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.OAUTH_TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return ConnectorResult(
                            status=ConnectorStatus.SUCCESS,
                            data={
                                "access_token": data.get("access_token"),
                                "workspace_id": data.get("workspace_id"),
                                "workspace_name": data.get("workspace_name"),
                                "bot_id": data.get("bot_id")
                            }
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

    async def refresh_access_token(self) -> ConnectorResult:
        """Notion access tokens don't expire - return current token"""
        return ConnectorResult(
            status=ConnectorStatus.SUCCESS,
            data={"access_token": self.access_token}
        )

    # ================== Document Operations ==================

    async def list_documents(
        self,
        path: Optional[str] = None,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List all accessible pages and databases"""
        try:
            async with aiohttp.ClientSession() as session:
                # Search for all pages
                has_more = True
                start_cursor = None

                while has_more:
                    payload = {
                        "filter": {"property": "object", "value": "page"},
                        "page_size": 100
                    }
                    if start_cursor:
                        payload["start_cursor"] = start_cursor

                    async with session.post(
                        f"{self.API_BASE}/search",
                        headers=self._get_headers(),
                        json=payload
                    ) as resp:
                        if resp.status != 200:
                            break

                        data = await resp.json()
                        results = data.get("results", [])

                        for page in results:
                            # Filter by modification time
                            last_edited = page.get("last_edited_time")
                            if modified_since and last_edited:
                                edited_dt = datetime.fromisoformat(
                                    last_edited.replace("Z", "+00:00")
                                )
                                if edited_dt <= modified_since:
                                    continue

                            # Extract title
                            title = self._extract_title(page)

                            yield {
                                "external_id": page["id"],
                                "title": title,
                                "type": page["object"],
                                "url": page.get("url"),
                                "created_time": page.get("created_time"),
                                "last_edited_time": last_edited,
                                "parent": page.get("parent", {})
                            }

                        has_more = data.get("has_more", False)
                        start_cursor = data.get("next_cursor")

        except Exception as e:
            print(f"[NotionConnector] List documents error: {e}")

    def _extract_title(self, page: Dict) -> str:
        """Extract title from Notion page"""
        properties = page.get("properties", {})

        # Try common title property names
        for prop_name in ["title", "Title", "Name", "name", "이름", "제목"]:
            if prop_name in properties:
                prop = properties[prop_name]
                if prop.get("type") == "title":
                    title_parts = prop.get("title", [])
                    if title_parts:
                        return "".join(
                            t.get("plain_text", "") for t in title_parts
                        )

        # Fallback to first title-type property
        for prop_name, prop in properties.items():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                if title_parts:
                    return "".join(
                        t.get("plain_text", "") for t in title_parts
                    )

        return "Untitled"

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch full page content"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get page metadata
                async with session.get(
                    f"{self.API_BASE}/pages/{external_id}",
                    headers=self._get_headers()
                ) as resp:
                    if resp.status != 200:
                        return ConnectorResult(
                            status=ConnectorStatus.NOT_FOUND,
                            error="Page not found"
                        )
                    page = await resp.json()

                # Get page blocks (content)
                blocks = await self._fetch_blocks(session, external_id)

                # Convert blocks to text content
                content = self._blocks_to_text(blocks)
                sections = self._blocks_to_sections(blocks)

                title = self._extract_title(page)

                # Calculate content hash
                content_hash = hashlib.md5(content.encode()).hexdigest()

                # Parse dates
                modified_at = None
                if page.get("last_edited_time"):
                    modified_at = datetime.fromisoformat(
                        page["last_edited_time"].replace("Z", "+00:00")
                    )

                doc = ConnectorDocument(
                    external_id=external_id,
                    title=title,
                    content=content,
                    external_url=page.get("url"),
                    path=self._get_page_path(page),
                    mime_type="text/plain",
                    modified_at=modified_at,
                    sections=sections,
                    content_hash=content_hash,
                    metadata={
                        "notion_id": external_id,
                        "parent": page.get("parent", {}),
                        "icon": page.get("icon"),
                        "cover": page.get("cover")
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

    async def _fetch_blocks(
        self,
        session: aiohttp.ClientSession,
        block_id: str
    ) -> List[Dict]:
        """Recursively fetch all blocks of a page"""
        blocks = []

        try:
            has_more = True
            start_cursor = None

            while has_more:
                url = f"{self.API_BASE}/blocks/{block_id}/children"
                params = {"page_size": 100}
                if start_cursor:
                    params["start_cursor"] = start_cursor

                async with session.get(
                    url,
                    headers=self._get_headers(),
                    params=params
                ) as resp:
                    if resp.status != 200:
                        break

                    data = await resp.json()
                    results = data.get("results", [])

                    for block in results:
                        blocks.append(block)

                        # Fetch children if has_children
                        if block.get("has_children"):
                            children = await self._fetch_blocks(
                                session, block["id"]
                            )
                            block["children"] = children

                    has_more = data.get("has_more", False)
                    start_cursor = data.get("next_cursor")

        except Exception as e:
            print(f"[NotionConnector] Fetch blocks error: {e}")

        return blocks

    def _blocks_to_text(self, blocks: List[Dict]) -> str:
        """Convert Notion blocks to plain text"""
        lines = []

        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            # Extract text from rich_text
            rich_text = block_data.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)

            # Handle different block types
            if block_type in ["paragraph", "bulleted_list_item", "numbered_list_item"]:
                if block_type == "bulleted_list_item":
                    lines.append(f"• {text}")
                elif block_type == "numbered_list_item":
                    lines.append(f"1. {text}")
                else:
                    lines.append(text)

            elif block_type.startswith("heading_"):
                level = int(block_type[-1])
                lines.append(f"{'#' * level} {text}")

            elif block_type == "code":
                lang = block_data.get("language", "")
                lines.append(f"```{lang}")
                lines.append(text)
                lines.append("```")

            elif block_type == "quote":
                lines.append(f"> {text}")

            elif block_type == "callout":
                emoji = block_data.get("icon", {}).get("emoji", "💡")
                lines.append(f"{emoji} {text}")

            elif block_type == "table":
                # Handle table
                if "children" in block:
                    for row in block["children"]:
                        cells = row.get("table_row", {}).get("cells", [])
                        cell_texts = [
                            "".join(c.get("plain_text", "") for c in cell)
                            for cell in cells
                        ]
                        lines.append("| " + " | ".join(cell_texts) + " |")

            elif block_type == "divider":
                lines.append("---")

            elif block_type == "toggle":
                lines.append(f"▸ {text}")

            # Process children
            if "children" in block:
                child_text = self._blocks_to_text(block["children"])
                if child_text:
                    # Indent children
                    indented = "\n".join(
                        "  " + line for line in child_text.split("\n")
                    )
                    lines.append(indented)

        return "\n".join(lines)

    def _blocks_to_sections(self, blocks: List[Dict]) -> List[Dict]:
        """Convert blocks to structured sections"""
        sections = []
        current_section = {"title": "", "content": [], "type": "text"}

        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            rich_text = block_data.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)

            # Headings start new sections
            if block_type.startswith("heading_"):
                if current_section["content"]:
                    sections.append(current_section)
                current_section = {
                    "title": text,
                    "content": [],
                    "type": "text",
                    "level": int(block_type[-1])
                }

            elif block_type == "code":
                # Code blocks as separate sections
                if current_section["content"]:
                    sections.append(current_section)
                sections.append({
                    "title": "",
                    "content": [text],
                    "type": "code",
                    "language": block_data.get("language", "")
                })
                current_section = {"title": "", "content": [], "type": "text"}

            elif block_type == "table":
                # Tables as separate sections
                if current_section["content"]:
                    sections.append(current_section)
                table_content = self._extract_table(block)
                sections.append({
                    "title": "",
                    "content": table_content,
                    "type": "table"
                })
                current_section = {"title": "", "content": [], "type": "text"}

            else:
                current_section["content"].append(text)

        if current_section["content"]:
            sections.append(current_section)

        return sections

    def _extract_table(self, block: Dict) -> List[List[str]]:
        """Extract table content"""
        rows = []
        if "children" in block:
            for row in block["children"]:
                cells = row.get("table_row", {}).get("cells", [])
                cell_texts = [
                    "".join(c.get("plain_text", "") for c in cell)
                    for cell in cells
                ]
                rows.append(cell_texts)
        return rows

    def _get_page_path(self, page: Dict) -> str:
        """Get page path from parent info"""
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")

        if parent_type == "workspace":
            return "/"
        elif parent_type == "page_id":
            return f"/page/{parent.get('page_id', '')}"
        elif parent_type == "database_id":
            return f"/database/{parent.get('database_id', '')}"

        return "/"
