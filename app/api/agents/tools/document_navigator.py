"""
Document Navigator Tool
Provides document/section navigation for Agent-Driven RAG pre-search confirmation.

This tool enables the agent to:
1. Get document candidates based on query
2. Get section hierarchy within documents
3. Search by keywords across document map
4. Perform scoped searches within selected documents/sections
"""
import logging
from typing import Dict, Any, Optional, List

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class DocumentNavigatorTool(BaseTool):
    """
    Document Navigation Tool for Agent-Driven RAG.

    Features:
    - Query-based document candidate retrieval
    - Section hierarchy navigation
    - Keyword-based document search
    - Scoped search within selected scope
    """

    def __init__(self):
        super().__init__(
            name="document_navigator",
            description="""Document navigation tool for pre-search scope selection.
Use this to help users select specific documents or sections before searching.
Actions:
- get_candidates: Get document/section candidates matching a query
- get_document_map: Get full document hierarchy
- search_by_keyword: Search documents by keyword
- search_scoped: Search within selected documents/sections

Returns document and section information for user scope selection."""
        )
        self._doc_map_service = None
        self._agent_work_service = None
        self._rag_service = None

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: get_candidates, get_document_map, search_by_keyword, or search_scoped",
                    "enum": ["get_candidates", "get_document_map", "search_by_keyword", "search_scoped"]
                },
                "query": {
                    "type": "string",
                    "description": "Search query (required for get_candidates and search_scoped)"
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword for search_by_keyword action"
                },
                "pdf_id": {
                    "type": "string",
                    "description": "Optional document ID to filter"
                },
                "scope_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document IDs for scoped search"
                },
                "scope_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of section paths for scoped search"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5
                }
            },
            "required": ["action"]
        }

    async def _get_doc_map_service(self):
        """Lazy load DocumentMapService."""
        if self._doc_map_service is None:
            try:
                from ...services.document_map_service import get_document_map_service
                self._doc_map_service = get_document_map_service()
            except Exception as e:
                logger.error(f"Failed to get DocumentMapService: {e}")
        return self._doc_map_service

    async def _get_agent_work_service(self):
        """Lazy load AgentWorkService."""
        if self._agent_work_service is None:
            try:
                from ...services.agent_work_service import get_agent_work_service
                self._agent_work_service = get_agent_work_service()
            except Exception as e:
                logger.error(f"Failed to get AgentWorkService: {e}")
        return self._agent_work_service

    async def _get_rag_service(self):
        """Lazy load RAG service."""
        if self._rag_service is None:
            try:
                from ...core.deps import get_rag_service
                self._rag_service = get_rag_service()
            except Exception as e:
                logger.error(f"Failed to get RAGService: {e}")
        return self._rag_service

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Execute document navigation action."""
        action = kwargs.get("action")

        if not action:
            return self.create_error_result("Missing required parameter: action")

        try:
            if action == "get_candidates":
                return await self._get_candidates(context, **kwargs)
            elif action == "get_document_map":
                return await self._get_document_map(context, **kwargs)
            elif action == "search_by_keyword":
                return await self._search_by_keyword(context, **kwargs)
            elif action == "search_scoped":
                return await self._search_scoped(context, **kwargs)
            else:
                return self.create_error_result(f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"DocumentNavigator execution failed: {e}")
            return self.create_error_result(str(e))

    async def _get_candidates(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Get document/section candidates for a query."""
        query = kwargs.get("query")
        if not query:
            return self.create_error_result("Query is required for get_candidates")

        top_k = kwargs.get("top_k", 5)

        doc_map_service = await self._get_doc_map_service()
        if not doc_map_service:
            return self.create_error_result("DocumentMapService not available")

        candidates = await doc_map_service.get_document_candidates(
            query=query,
            top_k=top_k,
            min_score=0.1
        )

        # Get suggested scope from history if user_id available
        suggested_scope = None
        user_id = context.user_id if hasattr(context, 'user_id') else None
        if user_id:
            agent_work_service = await self._get_agent_work_service()
            if agent_work_service:
                suggested = await agent_work_service.get_suggested_scope(user_id, query)
                if suggested:
                    suggested_scope = suggested.to_dict()

        # Format results
        result = {
            "candidates": [],
            "suggested_scope": suggested_scope,
            "query": query,
            "total_candidates": len(candidates)
        }

        for doc in candidates:
            doc_result = {
                "pdf_id": doc.pdf_id,
                "document_name": doc.document_name,
                "document_type": doc.document_type,
                "total_pages": doc.total_pages,
                "relevance_score": doc.relevance_score,
                "sections": []
            }

            for section in doc.sections[:5]:  # Limit sections
                doc_result["sections"].append({
                    "section_path": section.section_path,
                    "section_title": section.section_title,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "relevance_score": section.relevance_score
                })

            result["candidates"].append(doc_result)

        return self.create_success_result(
            result,
            metadata={"action": "get_candidates", "query": query}
        )

    async def _get_document_map(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Get document map for navigation."""
        pdf_id = kwargs.get("pdf_id")

        doc_map_service = await self._get_doc_map_service()
        if not doc_map_service:
            return self.create_error_result("DocumentMapService not available")

        doc_map = await doc_map_service.get_document_map(pdf_id)

        return self.create_success_result(
            doc_map,
            metadata={"action": "get_document_map", "pdf_id": pdf_id}
        )

    async def _search_by_keyword(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Search documents by keyword."""
        keyword = kwargs.get("keyword")
        if not keyword:
            return self.create_error_result("Keyword is required for search_by_keyword")

        doc_map_service = await self._get_doc_map_service()
        if not doc_map_service:
            return self.create_error_result("DocumentMapService not available")

        results = await doc_map_service.search_by_keyword(
            keyword=keyword,
            include_sections=True
        )

        return self.create_success_result(
            {"documents": results, "keyword": keyword},
            metadata={"action": "search_by_keyword", "keyword": keyword}
        )

    async def _search_scoped(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Search within selected scope."""
        query = kwargs.get("query")
        if not query:
            return self.create_error_result("Query is required for search_scoped")

        scope_documents = kwargs.get("scope_documents", [])
        scope_sections = kwargs.get("scope_sections", [])
        top_k = kwargs.get("top_k", 5)

        if not scope_documents and not scope_sections:
            return self.create_error_result(
                "At least one of scope_documents or scope_sections is required"
            )

        rag_service = await self._get_rag_service()
        if not rag_service:
            return self.create_error_result("RAG service not available")

        # Use RAG service's scoped search
        user_id = context.user_id if hasattr(context, 'user_id') else None
        result = await rag_service.search_with_scope(
            question=query,
            scope_documents=scope_documents,
            scope_sections=scope_sections,
            top_k=top_k,
            user_id=user_id
        )

        # Track in search history if user_id available
        if user_id:
            agent_work_service = await self._get_agent_work_service()
            if agent_work_service:
                from ...services.agent_work_service import SearchScope
                scope = SearchScope(
                    documents=scope_documents,
                    sections=scope_sections
                )
                await agent_work_service.add_search_history(
                    user_id=user_id,
                    query=query,
                    selected_scope=scope,
                    result_count=len(result.get("sources", [])),
                    was_successful=bool(result.get("sources"))
                )

        return self.create_success_result(
            {
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "scope_used": {
                    "documents": scope_documents,
                    "sections": scope_sections
                }
            },
            metadata={
                "action": "search_scoped",
                "query": query,
                "scope_documents": scope_documents,
                "scope_sections": scope_sections
            }
        )


class ScopeSuggestionTool(BaseTool):
    """
    Tool for getting scope suggestions based on query and history.

    This tool analyzes user history and current query to suggest
    appropriate search scope for better RAG results.
    """

    def __init__(self):
        super().__init__(
            name="scope_suggestion",
            description="""Get search scope suggestions based on query and user history.
Use this to recommend documents/sections the user should select for their query.
Returns suggested scope and explanation."""
        )
        self._agent_work_service = None
        self._doc_map_service = None

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to get suggestions for"
                },
                "user_id": {
                    "type": "string",
                    "description": "User ID for history-based suggestions"
                }
            },
            "required": ["query"]
        }

    async def _get_services(self):
        """Lazy load services."""
        if self._agent_work_service is None:
            try:
                from ...services.agent_work_service import get_agent_work_service
                self._agent_work_service = get_agent_work_service()
            except Exception as e:
                logger.error(f"Failed to get AgentWorkService: {e}")

        if self._doc_map_service is None:
            try:
                from ...services.document_map_service import get_document_map_service
                self._doc_map_service = get_document_map_service()
            except Exception as e:
                logger.error(f"Failed to get DocumentMapService: {e}")

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """Get scope suggestions for query."""
        query = kwargs.get("query")
        if not query:
            return self.create_error_result("Query is required")

        user_id = kwargs.get("user_id") or (
            context.user_id if hasattr(context, 'user_id') else None
        )

        await self._get_services()

        suggestions = {
            "query": query,
            "from_history": None,
            "from_keywords": [],
            "recommendation": None
        }

        # Check history-based suggestions
        if user_id and self._agent_work_service:
            suggested = await self._agent_work_service.get_suggested_scope(user_id, query)
            if suggested:
                suggestions["from_history"] = suggested.to_dict()

        # Get keyword-based suggestions
        if self._doc_map_service:
            candidates = await self._doc_map_service.get_document_candidates(
                query=query,
                top_k=3,
                min_score=0.3
            )

            for doc in candidates:
                suggestion = {
                    "pdf_id": doc.pdf_id,
                    "document_name": doc.document_name,
                    "relevance_score": doc.relevance_score,
                    "top_sections": [
                        {
                            "section_path": s.section_path,
                            "section_title": s.section_title,
                            "relevance_score": s.relevance_score
                        }
                        for s in doc.sections[:3]
                    ]
                }
                suggestions["from_keywords"].append(suggestion)

        # Generate recommendation
        if suggestions["from_history"]:
            suggestions["recommendation"] = "history_based"
            suggestions["explanation"] = "이전에 비슷한 검색을 수행한 기록이 있습니다. 같은 범위를 사용할 수 있습니다."
        elif suggestions["from_keywords"]:
            suggestions["recommendation"] = "keyword_based"
            suggestions["explanation"] = "쿼리 키워드를 기반으로 관련 문서를 추천합니다."
        else:
            suggestions["recommendation"] = "none"
            suggestions["explanation"] = "특별한 추천 범위가 없습니다. 전체 검색을 권장합니다."

        return self.create_success_result(
            suggestions,
            metadata={"query": query, "user_id": user_id}
        )
