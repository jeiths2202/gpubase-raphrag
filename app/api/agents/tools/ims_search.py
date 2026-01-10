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
            # Use direct database search (no user filtering for agent access)
            from ...ims_crawler.infrastructure.dependencies import get_db_pool

            # Build SQL filters
            filters = {}
            where_clauses = []
            params = []
            param_idx = 1

            if status != "all":
                filters["status"] = status
                where_clauses.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if priority != "all":
                filters["priority"] = priority
                where_clauses.append(f"priority = ${param_idx}")
                params.append(priority)
                param_idx += 1

            if product:
                filters["product"] = product
                where_clauses.append(f"product ILIKE ${param_idx}")
                params.append(f"%{product}%")
                param_idx += 1

            # Build the query - search in title and description
            # Use full-text search for better keyword matching
            search_pattern = f"%{query}%"
            where_clauses.append(f"(title ILIKE ${param_idx} OR description ILIKE ${param_idx + 1})")
            params.extend([search_pattern, search_pattern])

            where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

            sql = f"""
                SELECT
                    ims_id, title, description, status, priority,
                    product, created_at
                FROM ims_issues
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit}
            """

            pool = await get_db_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

            # Format results
            formatted_issues = []
            for row in rows:
                formatted_issues.append({
                    "id": row["ims_id"],
                    "title": row["title"] or "",
                    "status": row["status"] or "",
                    "priority": row["priority"] or "",
                    "product": row["product"] or "",
                    "description": (row["description"] or "")[:300],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else ""
                })

            output = {
                "query": query,
                "filters": filters,
                "total_count": len(formatted_issues),
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
