"""
IMS Search Tool
Searches the IMS (Issue Management System) for issues.
Supports DB search with crawl fallback when no results found.
Checks for IMS credentials before crawling.
"""
from typing import Dict, Any, Optional, List, Callable, Awaitable
from uuid import UUID, uuid4
import logging
import asyncio

from .base import BaseTool
from ..types import ToolResult, AgentContext
from ..intent import IntentType

logger = logging.getLogger(__name__)

# Status message callbacks type
StatusCallback = Callable[[str], Awaitable[None]]


class IMSSearchTool(BaseTool):
    """
    Tool for searching IMS issues.
    First searches local DB, then triggers crawl if no results found.
    Checks for IMS credentials before crawling - prompts user if not found.
    """

    def __init__(self):
        super().__init__(
            name="ims_search",
            description="""Search the Issue Management System (IMS) for issues.
Use this tool to find bug reports, feature requests, or technical issues.
Can filter by status, priority, product, and other criteria.
If no results found in local DB, will automatically crawl IMS for data.
Requires IMS credentials for crawling."""
        )
        self._status_callback: Optional[StatusCallback] = None

    def set_status_callback(self, callback: StatusCallback):
        """Set callback for status messages during search/crawl"""
        self._status_callback = callback

    async def _emit_status(self, message: str):
        """Emit status message if callback is set"""
        if self._status_callback:
            await self._status_callback(message)

    async def _check_credentials(self, user_id: str) -> bool:
        """
        Check if user has IMS credentials stored.

        Args:
            user_id: User's UUID string

        Returns:
            True if credentials exist, False otherwise
        """
        from ...ims_crawler.infrastructure.dependencies import get_manage_credentials_use_case

        try:
            uid = UUID(user_id) if user_id else None
            if not uid:
                return False

            credentials_use_case = await get_manage_credentials_use_case()
            credentials = await credentials_use_case.get_credentials(uid)

            return credentials is not None
        except Exception as e:
            logger.warning(f"Error checking credentials: {e}")
            return False

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

    async def _list_all_issues(
        self,
        user_id: str,
        status: str,
        priority: str,
        limit: int,
        keyword: Optional[str] = None,
        user_specific: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all issues matching the keyword.
        Used for 'list_all' intent - returns matching issues from DB only.
        Filters by keyword in title/description (NOT by product field).

        Args:
            user_id: User ID (only used if user_specific=True)
            status: Status filter
            priority: Priority filter
            limit: Maximum results
            keyword: Search keyword for title/description
            user_specific: If True, filter by user_id (e.g., "내가 검색한")
        """
        from ...ims_crawler.infrastructure.dependencies import get_db_pool

        # Build SQL filters
        where_clauses = []
        params = []
        param_idx = 1

        # Only filter by user_id if user explicitly requested it
        if user_specific and user_id:
            where_clauses.append(f"user_id = ${param_idx}")
            params.append(UUID(user_id) if user_id else uuid4())
            param_idx += 1

        if status != "all":
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if priority != "all":
            where_clauses.append(f"priority = ${param_idx}")
            params.append(priority)
            param_idx += 1

        # Keyword filter in title, description, issue_details, and action_log_text fields
        if keyword:
            search_pattern = f"%{keyword}%"
            where_clauses.append(
                f"(title ILIKE ${param_idx} OR description ILIKE ${param_idx + 1} "
                f"OR issue_details ILIKE ${param_idx + 2} OR action_log_text ILIKE ${param_idx + 3})"
            )
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
            param_idx += 4

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

        print(f"[IMS_SEARCH] list_all SQL: {sql}", flush=True)
        print(f"[IMS_SEARCH] list_all params: {params}", flush=True)

        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

            print(f"[IMS_SEARCH] list_all DB returned {len(rows)} rows", flush=True)

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

            print(f"[IMS_SEARCH] list_all found {len(formatted_issues)} issues for user {user_id}", flush=True)
            return formatted_issues
        except Exception as e:
            logger.error(f"[IMS_SEARCH] list_all error: {e}")
            return []

    async def _crawl_and_search(
        self,
        query: str,
        user_id: str,
        limit: int,
        force_refresh: bool = False
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
            # For list_all intent, use force_refresh=True to get all fresh data
            job, is_cached = await crawl_use_case.create_crawl_job(
                user_id=uid,
                search_query=query,
                max_results=limit * 2,  # Get more to filter later
                download_attachments=False,  # Skip attachments for faster crawl
                crawl_related=False,
                force_refresh=force_refresh
            )
            print(f"[IMS_SEARCH] crawl job created: is_cached={is_cached}, force_refresh={force_refresh}", flush=True)

            if is_cached:
                print(f"[IMS_SEARCH] Using cached crawl results for query: {query}", flush=True)
            else:
                # Execute the crawl job
                print(f"[IMS_SEARCH] Starting new crawl for query: {query}", flush=True)
                issues_found = 0
                issues_crawled = 0
                async for progress in crawl_use_case.execute_crawl_job(job.id):
                    event_type = progress.get("event", "")
                    if event_type == "search_completed":
                        issues_found = progress.get("total_issues", 0)
                        print(f"[IMS_SEARCH] Search found {issues_found} issues from IMS", flush=True)
                    elif event_type == "crawl_fetch_completed":
                        issues_crawled = progress.get("fetched_count", 0)
                        print(f"[IMS_SEARCH] Crawl fetched {issues_crawled} issue details", flush=True)
                    elif event_type == "job_completed":
                        saved = progress.get("issues_crawled", 0)
                        print(f"[IMS_SEARCH] Crawl completed: found={issues_found}, crawled={issues_crawled}, saved={saved}", flush=True)
                        break
                    elif event_type == "job_failed":
                        print(f"[IMS_SEARCH] Crawl failed: {progress.get('error', 'unknown')}", flush=True)
                        break

            # After crawl, search DB again for results
            return await self._search_db(query, "all", "all", None, limit)

        except Exception as e:
            logger.error(f"Crawl error: {e}")
            return []

    def _get_message(self, key: str, language: str, **kwargs) -> str:
        """Get localized message based on language"""
        messages = {
            "no_crawled_issues": {
                "ko": "크롤링된 이슈가 없습니다.",
                "ja": "クロールされたイシューがありません。",
                "en": "No crawled issues found."
            },
            "no_crawled_issues_product": {
                "ko": "'{product}' 관련 크롤링된 이슈가 없습니다.",
                "ja": "'{product}' に関連するクロールされたイシューがありません。",
                "en": "No crawled issues found for '{product}'."
            },
            "found_issues": {
                "ko": "총 {count}개의 크롤링된 이슈를 찾았습니다.",
                "ja": "合計 {count} 件のクロールされたイシューが見つかりました。",
                "en": "Found {count} crawled issue(s)."
            },
            "login_required": {
                "ko": "크롤링된 이슈를 조회하려면 로그인이 필요합니다.",
                "ja": "クロールされたイシューを表示するにはログインが必要です。",
                "en": "Login required to list crawled issues."
            }
        }

        # Normalize language code
        lang = language.lower() if language else "en"
        if lang.startswith("ko"):
            lang = "ko"
        elif lang.startswith("ja"):
            lang = "ja"
        else:
            lang = "en"

        template = messages.get(key, {}).get(lang, messages.get(key, {}).get("en", key))
        return template.format(**kwargs)

    async def _execute_list_all(
        self,
        context: AgentContext,
        status: str,
        priority: str,
        limit: int,
        keyword: Optional[str] = None,
        user_specific: bool = False
    ) -> ToolResult:
        """
        Execute list_all intent - ALWAYS crawl first, then list all matching issues.
        Filters by keyword in title/description (NOT by product field).
        Only filters by user_id if user explicitly requested it.
        """
        user_id = context.user_id or ""
        language = context.language or "en"

        try:
            # ALWAYS crawl first to get fresh data from IMS
            if keyword:
                # Check credentials before crawling
                has_credentials = await self._check_credentials(user_id)
                print(f"[IMS_SEARCH] list_all: checking credentials for crawl, has_credentials={has_credentials}", flush=True)

                if not has_credentials:
                    # No credentials - emit status to prompt user
                    await self._emit_status("credentials_required")
                    return self.create_success_result(
                        {
                            "intent": "list_all",
                            "query": keyword,
                            "total_count": 0,
                            "issues": [],
                            "source": "database",
                            "credentials_required": True,
                            "message": "IMS login required. Please provide your IMS credentials."
                        },
                        metadata={"credentials_required": True}
                    )

                # Emit crawling status to show in chat
                await self._emit_status("crawling")
                print(f"[IMS_SEARCH] list_all: starting crawl for keyword={keyword}", flush=True)

                # Perform crawl to get fresh data (force_refresh=True for list_all)
                await self._crawl_and_search(keyword, user_id, limit, force_refresh=True)
                print(f"[IMS_SEARCH] list_all: crawl completed for keyword={keyword}", flush=True)

            # After crawl, list issues from DB
            formatted_issues = await self._list_all_issues(
                user_id=user_id,
                status=status,
                priority=priority,
                limit=limit,
                keyword=keyword,
                user_specific=user_specific
            )

            # Emit ready status
            await self._emit_status("ready")

            # Build filters for output
            filters = {}
            if keyword:
                filters["keyword"] = keyword
            if status != "all":
                filters["status"] = status
            if priority != "all":
                filters["priority"] = priority
            if user_specific:
                filters["user_specific"] = True

            # Determine source - crawl if keyword was provided (crawl was triggered)
            source = "crawl" if keyword else "database"

            if len(formatted_issues) == 0:
                # No crawled issues found for keyword
                if keyword:
                    message = self._get_message("no_crawled_issues_product", language, product=keyword)
                else:
                    message = self._get_message("no_crawled_issues", language)

                output = {
                    "intent": "list_all",
                    "query": keyword or "",
                    "filters": filters,
                    "total_count": 0,
                    "issues": [],
                    "source": source,
                    "crawl_triggered": bool(keyword),
                    "message": message
                }
            else:
                message = self._get_message("found_issues", language, count=len(formatted_issues))
                output = {
                    "intent": "list_all",
                    "query": keyword or "",
                    "filters": filters,
                    "total_count": len(formatted_issues),
                    "issues": formatted_issues,
                    "source": source,
                    "crawl_triggered": bool(keyword),
                    "message": message
                }

            return self.create_success_result(
                output,
                metadata={
                    "intent": "list_all",
                    "source": source,
                    "keyword": keyword,
                    "crawl_triggered": bool(keyword),
                    "filters_applied": filters
                }
            )

        except Exception as e:
            logger.error(f"[IMS_SEARCH] list_all error: {e}")
            return self.create_error_result(f"Failed to list issues: {str(e)}")

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        query = kwargs.get("query") or ""
        status = kwargs.get("status") or "all"
        priority = kwargs.get("priority") or "all"
        product = kwargs.get("product")  # Can be None
        limit = kwargs.get("limit") or 10  # Default to 10 if None
        force_crawl = kwargs.get("force_crawl") or False

        # Get intent from context (set by orchestrator)
        intent = context.intent
        intent_type = intent.intent if intent else IntentType.SEARCH

        # Extract product from intent if not provided in kwargs
        if not product and intent and intent.extracted_params.get("product"):
            product = intent.extracted_params["product"]
            print(f"[IMS_SEARCH] Extracted product from intent: {product}", flush=True)

        print(f"[IMS_SEARCH] Intent: {intent_type.value}, query: {query}", flush=True)

        # Handle list_all intent - list all matching issues (with keyword filter, high limit)
        if intent_type == IntentType.LIST_ALL:
            # For list_all, return all matching results (no arbitrary limit unless user specifies)
            # Use very high limit to effectively return all matches
            list_all_limit = 10000  # Effectively unlimited

            # Check if user wants user-specific filtering (e.g., "내가 검색한", "my issues")
            user_specific = intent.extracted_params.get("user_specific", False) if intent else False

            # For list_all, ignore status/priority filters - return ALL matching issues
            print(f"[IMS_SEARCH] Executing list_all with keyword={query}, limit={list_all_limit}, user_specific={user_specific}", flush=True)
            return await self._execute_list_all(context, "all", "all", list_all_limit, keyword=query, user_specific=user_specific)

        # For search intent, require query
        if not query:
            return self.create_error_result("Query parameter is required for search")

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
                logger.info(f"No DB results for '{query}', checking credentials for crawl...")

                # Get user_id from context
                user_id = context.user_id or ""
                logger.info(f"[IMS_SEARCH] context.user_id={context.user_id}, using user_id={user_id}")

                # Check if user has IMS credentials before crawling
                has_credentials = await self._check_credentials(user_id)
                logger.info(f"[IMS_SEARCH] has_credentials={has_credentials} for user_id={user_id}")

                if not has_credentials:
                    # No credentials - emit status to prompt user
                    logger.info(f"No IMS credentials found for user {user_id}, requesting login")
                    await self._emit_status("credentials_required")

                    # Return result indicating credentials are needed
                    output = {
                        "query": query,
                        "filters": filters,
                        "total_count": 0,
                        "issues": [],
                        "source": "database",
                        "crawl_triggered": False,
                        "credentials_required": True,
                        "message": "IMS login required. Please provide your IMS credentials to search."
                    }

                    return self.create_success_result(
                        output,
                        metadata={
                            "source": "database",
                            "credentials_required": True
                        }
                    )

                # Has credentials - proceed with crawl
                # Emit status key for crawling (frontend will translate using i18n)
                await self._emit_status("crawling")

                logger.info(f"Starting IMS crawl for '{query}'...")

                # Perform crawl
                crawled_issues = await self._crawl_and_search(query, user_id, limit)

                if crawled_issues:
                    formatted_issues = crawled_issues
                    source = "crawl"
                    crawl_triggered = True

                    # Emit ready status key
                    await self._emit_status("ready")
                else:
                    # Crawl returned no results
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
