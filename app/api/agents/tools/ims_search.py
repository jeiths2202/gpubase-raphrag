"""
IMS Search Tool
Searches the IMS (Issue Management System) for issues.
"""
from typing import Dict, Any, Optional, List
import logging

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class IMSSearchTool(BaseTool):
    """
    Tool for searching IMS issues.
    Wraps the existing IMS crawler search functionality.
    """

    def __init__(self):
        super().__init__(
            name="ims_search",
            description="""Search the Issue Management System (IMS) for issues.
Use this tool to find bug reports, feature requests, or technical issues.
Can filter by status, priority, product, and other criteria."""
        )

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for issues"
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status (open, closed, in_progress)",
                    "enum": ["open", "closed", "in_progress", "all"],
                    "default": "all"
                },
                "priority": {
                    "type": "string",
                    "description": "Filter by priority (critical, high, medium, low)",
                    "enum": ["critical", "high", "medium", "low", "all"],
                    "default": "all"
                },
                "product": {
                    "type": "string",
                    "description": "Filter by product name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of issues to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        query = kwargs.get("query", "")
        status = kwargs.get("status", "all")
        priority = kwargs.get("priority", "all")
        product = kwargs.get("product")
        limit = kwargs.get("limit", 10)

        if not query:
            return self.create_error_result("Query parameter is required")

        try:
            # Try to use the IMS search service
            from ...ims_crawler.application.use_cases.search_issues import SearchIssuesUseCase

            # Build filters
            filters = {}
            if status != "all":
                filters["status"] = status
            if priority != "all":
                filters["priority"] = priority
            if product:
                filters["product"] = product

            # Execute search
            use_case = SearchIssuesUseCase()
            results = await use_case.execute(
                query=query,
                filters=filters,
                limit=limit
            )

            # Format results
            formatted_issues = []
            for issue in results.get("issues", [])[:limit]:
                formatted_issues.append({
                    "id": issue.get("issue_id", ""),
                    "title": issue.get("title", ""),
                    "status": issue.get("status", ""),
                    "priority": issue.get("priority", ""),
                    "product": issue.get("product", ""),
                    "description": issue.get("description", "")[:300],
                    "created_at": issue.get("created_at", ""),
                    "related_issues": issue.get("related_issue_ids", [])[:5]
                })

            output = {
                "query": query,
                "filters": filters,
                "total_count": results.get("total_count", len(formatted_issues)),
                "issues": formatted_issues
            }

            return self.create_success_result(
                output,
                metadata={
                    "source": "ims",
                    "filters_applied": filters
                }
            )

        except ImportError:
            # IMS module not available, return mock data
            logger.warning("IMS module not available, returning mock data")
            return self.create_success_result(
                {
                    "query": query,
                    "note": "IMS search service not available",
                    "issues": []
                },
                metadata={"source": "mock"}
            )
        except Exception as e:
            logger.error(f"IMS search error: {e}")
            return self.create_error_result(f"IMS search failed: {str(e)}")
