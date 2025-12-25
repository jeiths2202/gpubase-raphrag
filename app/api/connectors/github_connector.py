"""
GitHub Connector
Connects to GitHub API for repository documentation.
"""
import base64
import hashlib
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from .base import BaseConnector, ConnectorDocument, ConnectorResult, ConnectorStatus


class GitHubConnector(BaseConnector):
    """
    Connector for GitHub integration.
    Fetches documentation files from repositories.
    """

    API_BASE = "https://api.github.com"
    OAUTH_AUTH_URL = "https://github.com/login/oauth/authorize"
    OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"

    # Supported documentation file extensions
    DOC_EXTENSIONS = {".md", ".txt", ".rst", ".adoc", ".markdown", ".mdx"}

    CLIENT_ID = ""
    CLIENT_SECRET = ""

    @property
    def resource_type(self) -> str:
        return "github"

    @property
    def display_name(self) -> str:
        return "GitHub"

    @property
    def oauth_scopes(self) -> List[str]:
        return ["repo", "read:user"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CLIENT_ID = self.config.get("client_id", "")
        self.CLIENT_SECRET = self.config.get("client_secret", "")

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {
            "Authorization": f"Bearer {self.access_token or self.api_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    # ================== Authentication ==================

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Generate GitHub OAuth URL"""
        scopes = " ".join(self.oauth_scopes)
        params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.OAUTH_AUTH_URL}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """Exchange authorization code for tokens"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.OAUTH_TOKEN_URL,
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self.CLIENT_ID,
                        "client_secret": self.CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": redirect_uri
                    }
                ) as resp:
                    if resp.status == 200:
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
                                "token_type": data.get("token_type"),
                                "scope": data.get("scope")
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
        """GitHub OAuth tokens don't expire - return current token"""
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
        """List documentation files from all accessible repositories"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get user's repositories
                repos = await self._list_repositories(session)

                for repo in repos:
                    repo_full_name = repo["full_name"]

                    # Skip if not modified since the given time
                    if modified_since:
                        pushed_at = repo.get("pushed_at")
                        if pushed_at:
                            pushed_dt = datetime.fromisoformat(
                                pushed_at.replace("Z", "+00:00")
                            )
                            if pushed_dt <= modified_since:
                                continue

                    # Get documentation files from repository
                    async for doc in self._list_repo_docs(
                        session, repo_full_name, path
                    ):
                        yield doc

        except Exception as e:
            print(f"[GitHubConnector] List documents error: {e}")

    async def _list_repositories(
        self,
        session: aiohttp.ClientSession
    ) -> List[Dict]:
        """List user's accessible repositories"""
        repos = []

        try:
            page = 1
            while True:
                async with session.get(
                    f"{self.API_BASE}/user/repos",
                    headers=self._get_headers(),
                    params={"per_page": 100, "page": page, "sort": "updated"}
                ) as resp:
                    if resp.status != 200:
                        break

                    data = await resp.json()
                    if not data:
                        break

                    repos.extend(data)
                    page += 1

                    # Limit to 500 repos
                    if len(repos) >= 500:
                        break

        except Exception as e:
            print(f"[GitHubConnector] List repos error: {e}")

        return repos

    async def _list_repo_docs(
        self,
        session: aiohttp.ClientSession,
        repo_full_name: str,
        path: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List documentation files in a repository"""
        try:
            # Get repository tree
            async with session.get(
                f"{self.API_BASE}/repos/{repo_full_name}/git/trees/HEAD",
                headers=self._get_headers(),
                params={"recursive": "1"}
            ) as resp:
                if resp.status != 200:
                    return

                data = await resp.json()
                tree = data.get("tree", [])

                for item in tree:
                    if item["type"] != "blob":
                        continue

                    file_path = item["path"]

                    # Filter by path if specified
                    if path and not file_path.startswith(path):
                        continue

                    # Check if it's a documentation file
                    ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
                    if ext not in self.DOC_EXTENSIONS:
                        continue

                    yield {
                        "external_id": f"{repo_full_name}:{file_path}",
                        "title": file_path.rsplit("/", 1)[-1],
                        "path": file_path,
                        "url": f"https://github.com/{repo_full_name}/blob/HEAD/{file_path}",
                        "sha": item["sha"],
                        "size": item.get("size", 0),
                        "repo": repo_full_name
                    }

        except Exception as e:
            print(f"[GitHubConnector] List repo docs error: {e}")

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch file content from GitHub"""
        try:
            # Parse external_id: "owner/repo:path/to/file.md"
            if ":" not in external_id:
                return ConnectorResult(
                    status=ConnectorStatus.ERROR,
                    error="Invalid external ID format"
                )

            repo_full_name, file_path = external_id.split(":", 1)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.API_BASE}/repos/{repo_full_name}/contents/{file_path}",
                    headers=self._get_headers()
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

                    data = await resp.json()

                    # Decode content
                    content_b64 = data.get("content", "")
                    content = base64.b64decode(content_b64).decode("utf-8")

                    # Calculate content hash
                    content_hash = hashlib.md5(content.encode()).hexdigest()

                    # Parse sections from markdown
                    sections = self._parse_markdown_sections(content)

                    doc = ConnectorDocument(
                        external_id=external_id,
                        title=file_path.rsplit("/", 1)[-1],
                        content=content,
                        external_url=data.get("html_url"),
                        path=file_path,
                        mime_type="text/markdown",
                        sections=sections,
                        content_hash=content_hash,
                        etag=data.get("sha"),
                        metadata={
                            "repo": repo_full_name,
                            "sha": data.get("sha"),
                            "size": data.get("size"),
                            "download_url": data.get("download_url")
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

    def _parse_markdown_sections(self, content: str) -> List[Dict]:
        """Parse markdown into sections by headings"""
        import re

        sections = []
        current_section = {"title": "", "content": [], "type": "text", "level": 0}

        lines = content.split("\n")

        for line in lines:
            # Check for heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if heading_match:
                # Save current section
                if current_section["content"]:
                    current_section["content"] = "\n".join(current_section["content"])
                    sections.append(current_section)

                # Start new section
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                current_section = {
                    "title": title,
                    "content": [],
                    "type": "text",
                    "level": level
                }

            elif line.startswith("```"):
                # Code block - handle as separate section
                if current_section["content"]:
                    current_section["content"] = "\n".join(current_section["content"])
                    sections.append(current_section)
                    current_section = {"title": "", "content": [], "type": "text", "level": 0}

                # Find matching end
                lang = line[3:].strip()
                code_lines = [line]
                idx = lines.index(line) + 1
                while idx < len(lines) and not lines[idx].startswith("```"):
                    code_lines.append(lines[idx])
                    idx += 1
                if idx < len(lines):
                    code_lines.append(lines[idx])

                sections.append({
                    "title": "",
                    "content": "\n".join(code_lines),
                    "type": "code",
                    "language": lang
                })

            else:
                current_section["content"].append(line)

        # Add final section
        if current_section["content"]:
            current_section["content"] = "\n".join(current_section["content"])
            sections.append(current_section)

        return sections
