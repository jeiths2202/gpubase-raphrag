"""
Document Read Tool
Reads content from uploaded documents.
"""
from typing import Dict, Any, Optional
import logging

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class DocumentReadTool(BaseTool):
    """
    Tool for reading document content.
    Accesses documents uploaded to the session or knowledge base.
    """

    def __init__(self):
        super().__init__(
            name="document_read",
            description="""Read content from an uploaded document.
Use this tool to retrieve the full text or specific sections of a document
that was uploaded by the user or exists in the knowledge base."""
        )

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the document to read"
                },
                "chunk_index": {
                    "type": "integer",
                    "description": "Specific chunk index to read (optional, returns all if not specified)"
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 5000
                }
            },
            "required": ["document_id"]
        }

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        document_id = kwargs.get("document_id", "")
        chunk_index = kwargs.get("chunk_index")
        max_length = kwargs.get("max_length", 5000)

        if not document_id:
            return self.create_error_result("document_id parameter is required")

        try:
            from ...services.document_service import get_document_service

            doc_service = get_document_service()

            # Get document
            doc = await doc_service.get_document(document_id)

            if doc is None:
                return self.create_error_result(f"Document not found: {document_id}")

            # Get content
            if chunk_index is not None:
                chunks = doc.get("chunks", [])
                if 0 <= chunk_index < len(chunks):
                    content = chunks[chunk_index].get("content", "")
                else:
                    return self.create_error_result(
                        f"Chunk index {chunk_index} out of range (0-{len(chunks)-1})"
                    )
            else:
                content = doc.get("content", "")

            # Truncate if needed
            if len(content) > max_length:
                content = content[:max_length] + "...[truncated]"

            output = {
                "document_id": document_id,
                "title": doc.get("title", "Untitled"),
                "content": content,
                "content_length": len(content),
                "total_chunks": len(doc.get("chunks", [])),
                "metadata": {
                    "source": doc.get("source", ""),
                    "mime_type": doc.get("mime_type", ""),
                    "created_at": doc.get("created_at", "")
                }
            }

            return self.create_success_result(
                output,
                metadata={"document_id": document_id}
            )

        except ImportError:
            logger.warning("Document service not available")
            return self.create_error_result("Document service not available")
        except Exception as e:
            logger.error(f"Document read error: {e}")
            return self.create_error_result(f"Failed to read document: {str(e)}")


class WebFetchTool(BaseTool):
    """
    Tool for fetching web content.
    Retrieves and extracts text from web pages.
    """

    def __init__(self):
        super().__init__(
            name="web_fetch",
            description="""Fetch and extract content from a web page.
Use this tool to retrieve information from URLs provided by the user
or to look up external documentation."""
        )

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch"
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "Whether to extract plain text (default: true)",
                    "default": True
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 10000
                }
            },
            "required": ["url"]
        }

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        url = kwargs.get("url", "")
        extract_text = kwargs.get("extract_text", True)
        max_length = kwargs.get("max_length", 10000)

        if not url:
            return self.create_error_result("url parameter is required")

        # Validate URL
        if not url.startswith(("http://", "https://")):
            return self.create_error_result("URL must start with http:// or https://")

        try:
            import aiohttp
            from bs4 import BeautifulSoup

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        return self.create_error_result(
                            f"HTTP error: {response.status}"
                        )

                    html = await response.text()
                    content_type = response.headers.get("content-type", "")

            # Extract text if HTML
            if extract_text and "text/html" in content_type:
                soup = BeautifulSoup(html, "html.parser")

                # Remove script and style elements
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                # Get text
                text = soup.get_text(separator="\n", strip=True)

                # Clean up whitespace
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                content = "\n".join(lines)
            else:
                content = html

            # Truncate if needed
            if len(content) > max_length:
                content = content[:max_length] + "...[truncated]"

            # Extract title
            title = ""
            if "text/html" in content_type:
                soup = BeautifulSoup(html, "html.parser")
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)

            output = {
                "url": url,
                "title": title,
                "content": content,
                "content_length": len(content),
                "content_type": content_type
            }

            return self.create_success_result(
                output,
                metadata={"url": url, "extracted": extract_text}
            )

        except ImportError as e:
            logger.warning(f"Required library not available: {e}")
            return self.create_error_result(
                "Web fetch not available (missing aiohttp or beautifulsoup4)"
            )
        except Exception as e:
            logger.error(f"Web fetch error: {e}")
            return self.create_error_result(f"Failed to fetch URL: {str(e)}")
