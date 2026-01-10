"""
IMS Search Tool
Searches the IMS (Issue Management System) for issues.
Supports DB search with crawl fallback when no results found.
"""
from typing import Dict, Any, Optional, List, Callable, Awaitable
from uuid import UUID, uuid4
import logging
import asyncio

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)

# Status message callbacks type
StatusCallback = Callable[[str], Awaitable[None]]


class IMSSearchTool(BaseTool):
    """
    Tool for searching IMS issues.
    First searches local DB, then triggers crawl if no results found.
    """

    def __init__(self):
        super().__init__(
            name="ims_search",
            description="""Search the Issue Management System (IMS) for issues.
Use this tool to find bug reports, feature requests, or technical issues.
Can filter by status, priority, product, and other criteria.
If no results found in local DB, will automatically crawl IMS for data."""
        )
        self._status_callback: Optional[StatusCallback] = None

    def set_status_callback(self, callback: StatusCallback):
        """Set callback for status messages during search/crawl"""
        self._status_callback = callback

    async def _emit_status(self, message: str):
        """Emit status message if callback is set"""
        if self._status_callback:
            await self._status_callback(message)

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
                },
                "force_crawl": {
                    "type": "boolean",
                    "description": "Force crawl even if DB has results",
                    "default": False
                }
            },
            "required": ["query"]
        }

    async def _search_db(
        self,
        query: str,
        status: str,
        priority: str,
        product: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search issues in local database"""
        from ...ims_crawler.infrastructure.dependencies import get_db_pool

        # Build SQL filters
        where_clauses = []
        params = []
        param_idx = 1

        if status != "all":
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if priority != "all":
            where_clauses.append(f"priority = ${param_idx}")
            params.append(priority)
            param_idx += 1

        if product:
            where_clauses.append(f"product ILIKE ${param_idx}")
            params.append(f"%{product}%")
            param_idx += 1

        # Search in title and description
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

        return formatted_issues

    async def _crawl_and_search(
        self,
        query: str,
        user_id: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Trigger IMS crawl for the query and return results"""
        from ...ims_crawler.infrastructure.dependencies import get_crawl_jobs_use_case

        try:
            # Parse user_id to UUID
            try:
                uid = UUID(user_id) if user_id else uuid4()
            except (ValueError, TypeError):
                uid = uuid4()

            # Get crawl jobs use case
            crawl_use_case = await get_crawl_jobs_use_case()

            # Create crawl job
            job, is_cached = await crawl_use_case.create_crawl_job(
                user_id=uid,
                search_query=query,
                max_results=limit * 2,  # Get more to filter later
                download_attachments=False,  # Skip attachments for faster crawl
                crawl_related=False,
                force_refresh=False  # Use cache if available
            )

            if is_cached:
                logger.info(f"Using cached crawl results for query: {query}")
            else:
                # Execute the crawl job
                logger.info(f"Starting new crawl for query: {query}")
                async for progress in crawl_use_case.execute_crawl_job(job.id):
                    event_type = progress.get("event", "")
                    if event_type == "issue_saved":
                        # Progress update - issue saved
                        pass
                    elif event_type == "job_completed":
                        logger.info(f"Crawl completed: {progress}")
                        break
                    elif event_type == "job_failed":
                        logger.error(f"Crawl failed: {progress}")
                        break

            # After crawl, search DB again for results
            return await self._search_db(query, "all", "all", None, limit)

        except Exception as e:
            logger.error(f"Crawl error: {e}")
            return []

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
        force_crawl = kwargs.get("force_crawl", False)

        if not query:
            return self.create_error_result("Query parameter is required")

        try:
            # Build filters for metadata
            filters = {}
            if status != "all":
                filters["status"] = status
            if priority != "all":
                filters["priority"] = priority
            if product:
                filters["product"] = product

            # Step 1: Search local DB first
            formatted_issues = await self._search_db(query, status, priority, product, limit)

            source = "database"
            crawl_triggered = False

            # Step 2: If no results and not forcing crawl skip, trigger crawl
            if len(formatted_issues) == 0 or force_crawl:
                # Emit status key for crawling (frontend will translate using i18n)
                await self._emit_status("crawling")

                logger.info(f"No DB results for '{query}', triggering crawl...")

                # Get user_id from context
                user_id = context.user_id or str(uuid4())

                # Perform crawl
                crawled_issues = await self._crawl_and_search(query, user_id, limit)

                if crawled_issues:
                    formatted_issues = crawled_issues
                    source = "crawl"
                    crawl_triggered = True

                    # Emit ready status key
                    await self._emit_status("ready")
            else:
                # DB has results, emit ready status key
                await self._emit_status("ready")

            output = {
                "query": query,
                "filters": filters,
                "total_count": len(formatted_issues),
                "issues": formatted_issues,
                "source": source,
                "crawl_triggered": crawl_triggered
            }

            return self.create_success_result(
                output,
                metadata={
                    "source": source,
                    "filters_applied": filters,
                    "crawl_triggered": crawl_triggered
                }
            )

        except ImportError as e:
            logger.warning(f"IMS module not available: {e}")
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
