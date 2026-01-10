"""
Vector Search Tool
Searches the vector embedding store using the existing RAGService.
"""
from typing import Dict, Any, Optional, List
import logging

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


class VectorSearchTool(BaseTool):
    """
    Tool for searching vector embeddings.
    Wraps the existing RAGService with strategy="vector".
    """

    def __init__(self, rag_service=None):
        super().__init__(
            name="vector_search",
            description="""Search the knowledge base using semantic similarity.
Use this tool to find documents, articles, or information related to a query.
Returns the most relevant text chunks with their sources."""
        )
        self._rag_service = rag_service

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (natural language)"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5
                },
                "language": {
                    "type": "string",
                    "description": "Language filter (en, ko, ja, or auto)",
                    "default": "auto"
                }
            },
            "required": ["query"]
        }

    @property
    def rag_service(self):
        """Lazy load RAG service"""
        if self._rag_service is None:
            from ...services.rag_service import RAGService
            self._rag_service = RAGService.get_instance()
        return self._rag_service

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 5)
        language = kwargs.get("language", context.language)

        if not query:
            return self.create_error_result("Query parameter is required")

        try:
            result = await self.rag_service.query(
                question=query,
                strategy="vector",
                language=language,
                top_k=top_k,
                session_id=context.session_id,
                user_id=context.user_id
            )

            # Format results
            sources = result.get("sources", [])
            formatted_sources = []
            for i, source in enumerate(sources[:top_k], 1):
                formatted_sources.append({
                    "rank": i,
                    "content": source.get("content", "")[:500],  # Truncate
                    "source": source.get("source", "Unknown"),
                    "score": source.get("score", 0.0)
                })

            output = {
                "query": query,
                "results_count": len(formatted_sources),
                "results": formatted_sources
            }

            return self.create_success_result(
                output,
                metadata={
                    "strategy": "vector",
                    "language": result.get("language", language),
                    "confidence": result.get("confidence", 0.0)
                }
            )

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return self.create_error_result(f"Search failed: {str(e)}")


class GraphQueryTool(BaseTool):
    """
    Tool for querying the knowledge graph.
    Uses Neo4j graph database for entity and relationship queries.
    """

    def __init__(self, rag_service=None):
        super().__init__(
            name="graph_query",
            description="""Query the knowledge graph to find entities and relationships.
Use this for questions about connections between concepts, entities, or
for exploring structured knowledge relationships."""
        )
        self._rag_service = rag_service

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query about entities or relationships"
                },
                "query_type": {
                    "type": "string",
                    "description": "Type of graph query: entity, relation, or path",
                    "enum": ["entity", "relation", "path"],
                    "default": "entity"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    @property
    def rag_service(self):
        """Lazy load RAG service"""
        if self._rag_service is None:
            from ...services.rag_service import RAGService
            self._rag_service = RAGService.get_instance()
        return self._rag_service

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        query = kwargs.get("query", "")
        query_type = kwargs.get("query_type", "entity")
        top_k = kwargs.get("top_k", 5)

        if not query:
            return self.create_error_result("Query parameter is required")

        try:
            result = await self.rag_service.query(
                question=query,
                strategy="graph",
                language=context.language,
                top_k=top_k,
                session_id=context.session_id,
                user_id=context.user_id
            )

            # Format graph results
            sources = result.get("sources", [])
            formatted_results = []
            for source in sources[:top_k]:
                formatted_results.append({
                    "content": source.get("content", "")[:500],
                    "entities": source.get("entities", []),
                    "relations": source.get("relations", []),
                    "source": source.get("source", "")
                })

            output = {
                "query": query,
                "query_type": query_type,
                "results_count": len(formatted_results),
                "results": formatted_results
            }

            return self.create_success_result(
                output,
                metadata={"strategy": "graph", "query_type": query_type}
            )

        except Exception as e:
            logger.error(f"Graph query error: {e}")
            return self.create_error_result(f"Graph query failed: {str(e)}")
