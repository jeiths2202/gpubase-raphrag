"""
Image Search Tool
Searches for images in the multimodal RAG knowledge base.
"""
from typing import Dict, Any, Optional, List
import logging
import asyncio

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class ImageSearchTool(BaseTool):
    """
    Tool for searching images in the multimodal RAG system.
    Uses MultimodalRAGService for vector similarity search on image embeddings.
    """

    def __init__(self, multimodal_service=None):
        super().__init__(
            name="image_search",
            description="""Search for images, diagrams, charts, or figures in the knowledge base.
Use this tool when the user asks about visual content, flowcharts, architecture diagrams,
screenshots, or any image-related information from documents.
Returns matching images with their descriptions and similarity scores."""
        )
        self._multimodal_service = multimodal_service

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query describing the image content"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 3)",
                    "default": 3
                },
                "document_id": {
                    "type": "string",
                    "description": "Optional: filter by specific document ID",
                    "default": None
                }
            },
            "required": ["query"]
        }

    async def _get_multimodal_service(self):
        """Lazy load multimodal service (async)"""
        if self._multimodal_service is None:
            try:
                from ...core.deps import get_multimodal_rag_service
                self._multimodal_service = await get_multimodal_rag_service()
            except Exception as e:
                logger.warning(f"Failed to load multimodal service: {e}")
        return self._multimodal_service

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Execute image search"""
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 3)
        document_id = kwargs.get("document_id")

        if not query:
            return ToolResult(
                success=False,
                output="Query is required for image search",
                error="Missing query parameter"
            )

        try:
            service = await self._get_multimodal_service()
            if service is None:
                return ToolResult(
                    success=False,
                    output="Image search service is not available",
                    error="MultimodalRAGService not initialized"
                )

            # Perform search
            results = await service.search_images(
                query=query,
                limit=top_k,
                document_id=document_id,
                include_data=False  # Don't include binary data in tool output
            )

            if not results:
                return ToolResult(
                    success=True,
                    output=f"No images found matching '{query}'",
                    data={"images": [], "count": 0}
                )

            # Format results for agent consumption
            formatted_results = []
            for img in results:
                formatted_results.append({
                    "image_id": img.get("image_id"),
                    "document_id": img.get("document_id"),
                    "page_number": img.get("page_number"),
                    "description": img.get("description", "No description"),
                    "similarity": round(img.get("similarity", 0), 3)
                })

            # Create human-readable output
            output_lines = [f"Found {len(formatted_results)} image(s) for '{query}':\n"]
            for i, img in enumerate(formatted_results, 1):
                output_lines.append(
                    f"{i}. {img['description'][:100]}..."
                    f"\n   Page: {img['page_number']}, "
                    f"Similarity: {img['similarity']:.1%}"
                )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "images": formatted_results,
                    "count": len(formatted_results),
                    "query": query
                }
            )

        except Exception as e:
            logger.error(f"Image search error: {e}")
            return ToolResult(
                success=False,
                output=f"Image search failed: {str(e)}",
                error=str(e)
            )
