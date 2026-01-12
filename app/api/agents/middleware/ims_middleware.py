"""
IMS Middleware and Tools for Deep Agents
IMS (Issue Management System) 검색 기능을 Deep Agents에서 사용할 수 있도록 제공

Deep Agents에서:
1. Tools: create_deep_agent의 tools 파라미터로 전달
2. Middleware: langchain.agents.middleware.types.AgentMiddleware 상속하여 동작 커스터마이즈

이 모듈은 IMS 검색 도구를 LangChain 호환 형태로 제공합니다.
"""
import os
import asyncio
import logging
from typing import List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# 의존성 체크
try:
    from langchain_core.tools import tool
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False


def _run_async(coro):
    """Run async coroutine in sync context"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If we're already in an async context, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class IMSToolsProvider:
    """
    IMS 도구 제공자

    IMS 검색 도구를 생성하여 Deep Agent에 전달합니다.

    사용 예시:
    ```python
    from deepagents import create_deep_agent
    from app.api.agents.middleware import IMSToolsProvider

    ims_provider = IMSToolsProvider()
    tools = ims_provider.get_tools()

    agent = create_deep_agent(
        model=my_llm,
        tools=tools,
    )
    ```
    """

    def __init__(self):
        self._db_pool = None

    async def _get_db_pool(self):
        """DB Pool 초기화"""
        if self._db_pool is None:
            try:
                from ...ims_crawler.infrastructure.dependencies import get_db_pool
                self._db_pool = await get_db_pool()
                logger.info("[IMSTools] DB pool connected")
            except Exception as e:
                logger.warning(f"[IMSTools] Failed to connect DB pool: {e}")
        return self._db_pool

    async def _search_issues(
        self,
        query: str,
        status: str = "all",
        priority: str = "all",
        product: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """Search issues in local database"""
        try:
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
                ims_id = row["ims_id"]
                formatted_issues.append({
                    "id": ims_id,
                    "url": f"https://ims.tmaxsoft.com/tody/ims/issue/issueView.do?issueId={ims_id}&menuCode=issue_search",
                    "title": row["title"] or "",
                    "status": row["status"] or "",
                    "priority": row["priority"] or "",
                    "product": row["product"] or "",
                    "description": (row["description"] or "")[:300],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else ""
                })

            return formatted_issues

        except Exception as e:
            logger.error(f"[IMSTools] Search error: {e}")
            return []

    async def _get_issue_detail(self, issue_id: str) -> Optional[dict]:
        """Get detailed information for a specific issue by ID"""
        try:
            from ...ims_crawler.infrastructure.dependencies import get_db_pool

            sql = """
                SELECT
                    ims_id, title, description, status, priority,
                    product, created_at, issue_details, action_log_text
                FROM ims_issues
                WHERE ims_id = $1
                LIMIT 1
            """

            pool = await get_db_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, issue_id)

            if not row:
                return None

            return {
                "id": row["ims_id"],
                "url": f"https://ims.tmaxsoft.com/tody/ims/issue/issueView.do?issueId={row['ims_id']}&menuCode=issue_search",
                "title": row["title"] or "",
                "description": row["description"] or "",
                "status": row["status"] or "",
                "priority": row["priority"] or "",
                "product": row["product"] or "",
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                "issue_details": row["issue_details"] or "",
                "action_log": row["action_log_text"] or "",
            }

        except Exception as e:
            logger.error(f"[IMSTools] Get detail error: {e}")
            return None

    def get_tools(self) -> List[Callable]:
        """IMS 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[IMSTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def ims_search(query: str, status: str = "all", priority: str = "all", product: str = "", limit: int = 10) -> str:
            """Search the Issue Management System (IMS) for issues.

            Use this tool to find bug reports, feature requests, or technical issues.
            Can filter by status, priority, product, and other criteria.

            Args:
                query: Search query for issues (required). Search in title and description.
                status: Filter by status - one of: open, closed, in_progress, all (default: all)
                priority: Filter by priority - one of: critical, high, medium, low, all (default: all)
                product: Filter by product name (optional)
                limit: Maximum number of issues to return (default: 10, max: 50)

            Returns:
                List of matching issues with id, title, status, priority, product, description, url
            """
            try:
                limit = min(max(1, limit), 50)
                product_filter = product if product else None

                results = _run_async(provider._search_issues(
                    query=query,
                    status=status,
                    priority=priority,
                    product=product_filter,
                    limit=limit
                ))

                if not results:
                    return f"IMS에서 '{query}'에 대한 검색 결과가 없습니다."

                # Format output
                output_lines = [f"IMS 검색 결과 ({len(results)}건):"]
                output_lines.append("=" * 60)

                for i, issue in enumerate(results, 1):
                    output_lines.append(f"\n[{i}] {issue['title']}")
                    output_lines.append(f"    ID: {issue['id']}")
                    output_lines.append(f"    상태: {issue['status']} | 우선순위: {issue['priority']}")
                    output_lines.append(f"    제품: {issue['product']}")
                    output_lines.append(f"    URL: {issue['url']}")
                    if issue['description']:
                        desc = issue['description'][:200] + "..." if len(issue['description']) > 200 else issue['description']
                        output_lines.append(f"    설명: {desc}")

                return "\n".join(output_lines)

            except Exception as e:
                logger.error(f"[IMSTools] ims_search error: {e}")
                return f"IMS 검색 중 오류가 발생했습니다: {str(e)}"

        @tool
        def ims_get_detail(issue_id: str) -> str:
            """Get detailed information for a specific IMS issue.

            Use this tool to get full details of an issue including description,
            action logs, and issue details.

            Args:
                issue_id: The IMS issue ID (e.g., "IMS-12345")

            Returns:
                Detailed issue information including description, status, action logs
            """
            try:
                result = _run_async(provider._get_issue_detail(issue_id))

                if not result:
                    return f"IMS ID '{issue_id}'에 해당하는 이슈를 찾을 수 없습니다."

                # Format output
                output_lines = [
                    f"IMS 이슈 상세 정보",
                    "=" * 60,
                    f"ID: {result['id']}",
                    f"제목: {result['title']}",
                    f"상태: {result['status']}",
                    f"우선순위: {result['priority']}",
                    f"제품: {result['product']}",
                    f"생성일: {result['created_at']}",
                    f"URL: {result['url']}",
                    "",
                    "설명:",
                    "-" * 40,
                    result['description'] or "(설명 없음)",
                ]

                if result['issue_details']:
                    output_lines.extend([
                        "",
                        "이슈 상세:",
                        "-" * 40,
                        result['issue_details']
                    ])

                if result['action_log']:
                    output_lines.extend([
                        "",
                        "액션 로그:",
                        "-" * 40,
                        result['action_log'][:2000] + "..." if len(result['action_log']) > 2000 else result['action_log']
                    ])

                return "\n".join(output_lines)

            except Exception as e:
                logger.error(f"[IMSTools] ims_get_detail error: {e}")
                return f"IMS 이슈 조회 중 오류가 발생했습니다: {str(e)}"

        return [ims_search, ims_get_detail]


# Convenience function
def get_ims_tools() -> List[Callable]:
    """
    IMS 도구 목록 반환 (간편 함수)

    Returns:
        List of IMS tools for use with create_deep_agent
    """
    provider = IMSToolsProvider()
    return provider.get_tools()


# IMS 시스템 프롬프트 (create_deep_agent의 system_prompt에 추가)
IMS_SYSTEM_PROMPT = """
## IMS (Issue Management System) Search Guidelines

You have access to the IMS issue tracking system.

### Available Tools:

1. **ims_search**: Search for issues in IMS
   - Use to find bug reports, feature requests, or technical issues
   - Can filter by status (open, closed, in_progress), priority (critical, high, medium, low), and product
   - Returns list of matching issues with ID, title, status, priority, URL

2. **ims_get_detail**: Get detailed information for a specific issue
   - Use when you need full details including description, action logs
   - Requires the issue ID (e.g., "IMS-12345")

### Important Rules:

1. **Search First**: When user asks about IMS issues, ALWAYS use ims_search first.
2. **Provide URLs**: Always include the IMS URL so users can access the issue directly.
3. **Be Specific**: Use filters (status, priority, product) when the user provides specific criteria.
4. **Get Details**: If user asks for detailed information about a specific issue, use ims_get_detail.
"""
