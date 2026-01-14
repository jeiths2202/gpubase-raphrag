"""
Planner Middleware and Tools for Deep Agents
Planner (태스크 분해/계획) 기능을 Deep Agents에서 사용할 수 있도록 제공

복잡한 작업을 작은 단계로 분해하고 실행 계획을 수립하는 기능 제공
"""
import os
import logging
from typing import List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# 의존성 체크
try:
    from langchain_core.tools import tool
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def _get_sync_db_connection():
    """동기식 PostgreSQL 연결 생성"""
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError("psycopg2 is not installed")

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kms"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


class PlannerToolsProvider:
    """
    Planner 도구 제공자

    태스크 분해, 컨텍스트 수집, 유사 작업 검색 등의 도구를 Deep Agent에 전달합니다.
    """

    def _search_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """Knowledge base 검색 (동기)"""
        try:
            from ..tools import VectorSearchTool
            from ..types import AgentContext

            vector_tool = VectorSearchTool()
            context = AgentContext()

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            vector_tool.execute(context, query=query, top_k=top_k)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(
                        vector_tool.execute(context, query=query, top_k=top_k)
                    )
            except RuntimeError:
                result = asyncio.run(
                    vector_tool.execute(context, query=query, top_k=top_k)
                )

            if result.get("success"):
                output = result.get("output", {})
                if isinstance(output, dict):
                    results = output.get("results", [])
                    if results:
                        formatted = []
                        for r in results[:top_k]:
                            content = r.get('content', '')[:400]
                            source = r.get('source', 'Unknown')
                            formatted.append(f"[{source}]\n{content}\n")
                        return "\n".join(formatted)
                return str(output)
            return "No results found"

        except Exception as e:
            logger.error(f"[PlannerTools] Knowledge search error: {e}")
            return f"Search error: {str(e)}"

    def _search_graph(self, query: str, query_type: str = "entity", top_k: int = 5) -> str:
        """Graph database 검색 (동기)"""
        try:
            from ..tools import GraphQueryTool
            from ..types import AgentContext

            graph_tool = GraphQueryTool()
            context = AgentContext()

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            graph_tool.execute(context, query=query, query_type=query_type, top_k=top_k)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(
                        graph_tool.execute(context, query=query, query_type=query_type, top_k=top_k)
                    )
            except RuntimeError:
                result = asyncio.run(
                    graph_tool.execute(context, query=query, query_type=query_type, top_k=top_k)
                )

            if result.get("success"):
                output = result.get("output", {})
                if isinstance(output, dict):
                    results = output.get("results", [])
                    if results:
                        formatted = []
                        for r in results[:top_k]:
                            content = r.get('content', '')[:300]
                            entities = r.get('entities', [])
                            formatted.append(f"Content: {content}")
                            if entities:
                                formatted.append(f"Entities: {', '.join(str(e) for e in entities[:5])}")
                            formatted.append("")
                        return "\n".join(formatted)
                return str(output)
            return "No graph results found"

        except Exception as e:
            logger.error(f"[PlannerTools] Graph search error: {e}")
            return f"Graph search error: {str(e)}"

    def _search_ims_issues(self, query: str, limit: int = 10) -> str:
        """IMS 이슈 검색 (동기)"""
        if not PSYCOPG2_AVAILABLE:
            return "IMS search not available (psycopg2 not installed)"

        conn = None
        try:
            conn = _get_sync_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            search_pattern = f"%{query}%"
            sql = """
                SELECT ims_id, title, status, product, created_at
                FROM ims_issues
                WHERE title ILIKE %s OR description ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
            """

            cursor.execute(sql, (search_pattern, search_pattern, limit))
            rows = cursor.fetchall()

            if not rows:
                return f"No IMS issues found for: {query}"

            formatted = [f"Found {len(rows)} IMS issues:"]
            for row in rows:
                formatted.append(f"- [{row['ims_id']}] {row['title'][:60]} ({row['status']})")

            return "\n".join(formatted)

        except Exception as e:
            logger.error(f"[PlannerTools] IMS search error: {e}")
            return f"IMS search error: {str(e)}"
        finally:
            if conn:
                conn.close()

    def get_tools(self) -> List[Callable]:
        """Planner 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[PlannerTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def gather_context(query: str, top_k: int = 5) -> str:
            """Search the knowledge base to gather context for planning.

            Use this tool to find relevant documentation, examples, or background
            information before creating a plan.

            Args:
                query: Search query for relevant context
                top_k: Number of results to return (default: 5)

            Returns:
                Relevant context from knowledge base
            """
            try:
                result = provider._search_knowledge_base(query, top_k)
                return f"=== Knowledge Base Context ===\n{result}"
            except Exception as e:
                logger.error(f"[PlannerTools] gather_context error: {e}")
                return f"Context gathering error: {str(e)}"

        @tool
        def explore_relationships(query: str, query_type: str = "entity") -> str:
            """Explore entity relationships in the knowledge graph.

            Use this to understand connections between concepts, components,
            or systems that may be relevant to planning.

            Args:
                query: Query about entities or relationships
                query_type: Type of query - "entity", "relation", or "path"

            Returns:
                Related entities and relationships from knowledge graph
            """
            try:
                result = provider._search_graph(query, query_type)
                return f"=== Knowledge Graph Results ===\n{result}"
            except Exception as e:
                logger.error(f"[PlannerTools] explore_relationships error: {e}")
                return f"Graph exploration error: {str(e)}"

        @tool
        def search_similar_tasks(query: str, limit: int = 10) -> str:
            """Search IMS for similar tasks or issues.

            Use this to find how similar tasks were handled in the past,
            identify potential blockers, or learn from previous solutions.

            Args:
                query: Description of the task or problem
                limit: Maximum number of results (default: 10)

            Returns:
                List of similar IMS issues and their status
            """
            try:
                result = provider._search_ims_issues(query, limit)
                return f"=== Similar IMS Issues ===\n{result}"
            except Exception as e:
                logger.error(f"[PlannerTools] search_similar_tasks error: {e}")
                return f"IMS search error: {str(e)}"

        return [gather_context, explore_relationships, search_similar_tasks]


def get_planner_tools() -> List[Callable]:
    """
    Planner 도구 목록 반환 (간편 함수)

    Returns:
        List of Planner tools for use with create_deep_agent
    """
    provider = PlannerToolsProvider()
    return provider.get_tools()


# Planner 시스템 프롬프트
PLANNER_SYSTEM_PROMPT = """
## Task Planning and Decomposition Guidelines

You are a strategic planning assistant that excels at breaking down complex tasks.

### Available Tools:

1. **gather_context**: Search knowledge base for relevant background information
   - Use before planning to understand the domain
   - Find documentation, examples, best practices

2. **explore_relationships**: Query knowledge graph for entity relationships
   - Identify connections between concepts
   - Understand system dependencies

3. **search_similar_tasks**: Find similar IMS issues and how they were resolved
   - Learn from past solutions
   - Identify potential blockers

### Planning Process:

1. **Understand**: Gather context about the task
2. **Analyze**: Identify key components and relationships
3. **Decompose**: Break into smaller, actionable steps
4. **Order**: Arrange steps by dependencies
5. **Assign**: Recommend agent type for each step

### Output Format:

## Task: [Main objective]

### Context
[Summary of relevant background gathered from tools]

### Plan

1. **Step 1**: [Description]
   - Agent: [rag/ims/vision/code]
   - Dependencies: [None/Step X]
   - Complexity: [Low/Medium/High]
   - Details: [Specific actions to take]

2. **Step 2**: [Description]
   ...

### Risks and Considerations
[Potential blockers, alternatives, or important notes]

### Success Criteria
[How to measure if the task is complete]

### Important Rules:

1. **Be Thorough**: Search all available sources before planning
2. **Be Specific**: Each step should be actionable
3. **Consider Dependencies**: Identify what must happen first
4. **Learn from History**: Check IMS for similar past issues
5. **Assign Appropriately**: Match steps to the right agent type
"""
