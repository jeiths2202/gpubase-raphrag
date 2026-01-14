"""
RAG Tools for Deep Agents
기존 RAG 도구를 LangChain tool 형식으로 래핑

비즈니스 로직은 기존 VectorSearchTool, GraphQueryTool을 그대로 사용
"""
import logging
from typing import List, Optional, Any, Callable
import asyncio

logger = logging.getLogger(__name__)

# LangChain 의존성 체크
try:
    from langchain_core.tools import tool, StructuredTool
    from pydantic import BaseModel, Field
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False
    logger.warning("langchain_core.tools not available")


class VectorSearchInput(BaseModel):
    """Vector search input schema"""
    query: str = Field(description="The search query (natural language)")
    top_k: int = Field(default=5, description="Number of results to return")


class GraphQueryInput(BaseModel):
    """Graph query input schema"""
    query: str = Field(description="The query about entities or relationships")
    query_type: str = Field(default="entity", description="Type: entity, relation, or path")
    top_k: int = Field(default=5, description="Number of results to return")


class ImageSearchInput(BaseModel):
    """Image search input schema"""
    query: str = Field(description="Text query to search for relevant images")
    top_k: int = Field(default=3, description="Number of images to return")
    document_id: Optional[str] = Field(default=None, description="Optional document ID to filter images")


class RAGToolsProvider:
    """
    RAG 도구 제공자

    기존 VectorSearchTool, GraphQueryTool, ImageSearchTool을 LangChain tool로 래핑
    """

    def __init__(self, rag_service=None, multimodal_service=None):
        """
        Args:
            rag_service: 기존 RAGService 인스턴스 (None이면 lazy load)
            multimodal_service: MultimodalRAGService 인스턴스 (None이면 lazy load)
        """
        self._rag_service = rag_service
        self._multimodal_service = multimodal_service
        self._context = None

    @property
    def rag_service(self):
        """RAG Service lazy load"""
        if self._rag_service is None:
            try:
                from ..tools import VectorSearchTool
                self._vector_tool = VectorSearchTool()
                self._rag_service = self._vector_tool.rag_service
            except Exception as e:
                logger.warning(f"Failed to load RAG service: {e}")
        return self._rag_service

    @property
    def multimodal_service(self):
        """MultimodalRAGService lazy load"""
        if self._multimodal_service is None:
            try:
                from ...services.multimodal_rag_service import MultimodalRAGService
                from ...infrastructure.postgres.image_embedding_repository import PostgresImageEmbeddingRepository
                # Note: In production, this should be injected via DI
                logger.debug("Multimodal service will be lazy loaded on first use")
            except Exception as e:
                logger.warning(f"Failed to import multimodal service: {e}")
        return self._multimodal_service

    def set_multimodal_service(self, service):
        """Set multimodal service instance"""
        self._multimodal_service = service

    def set_context(self, context):
        """AgentContext 설정"""
        self._context = context

    def get_tools(self) -> List[Any]:
        """LangChain tool 형식의 RAG 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("LangChain tools not available")
            return []

        tools = []

        # Vector Search Tool
        vector_tool = self._create_vector_search_tool()
        if vector_tool:
            tools.append(vector_tool)

        # Graph Query Tool
        graph_tool = self._create_graph_query_tool()
        if graph_tool:
            tools.append(graph_tool)

        # Image Search Tool (for multimodal RAG)
        image_tool = self._create_image_search_tool()
        if image_tool:
            tools.append(image_tool)

        return tools

    def _create_vector_search_tool(self):
        """Vector Search LangChain tool 생성"""
        from ..tools import VectorSearchTool
        from ..types import AgentContext

        vector_tool = VectorSearchTool()
        provider = self

        def vector_search(query: str, top_k: int = 5) -> str:
            """Search the knowledge base using semantic similarity."""
            context = provider._context or AgentContext()

            # 동기 래퍼로 비동기 함수 실행
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 이미 이벤트 루프가 실행 중이면 새 스레드에서 실행
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
                return result.get("output", "No results found")
            else:
                return f"Search error: {result.get('error', 'Unknown error')}"

        return StructuredTool.from_function(
            func=vector_search,
            name="vector_search",
            description="Search the knowledge base using semantic similarity. Use this to find documents related to a query.",
            args_schema=VectorSearchInput,
        )

    def _create_graph_query_tool(self):
        """Graph Query LangChain tool 생성"""
        from ..tools import GraphQueryTool
        from ..types import AgentContext

        graph_tool = GraphQueryTool()
        provider = self

        def graph_query(query: str, query_type: str = "entity", top_k: int = 5) -> str:
            """Query the knowledge graph to find entities and relationships."""
            context = provider._context or AgentContext()

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
                return result.get("output", "No results found")
            else:
                return f"Graph query error: {result.get('error', 'Unknown error')}"

        return StructuredTool.from_function(
            func=graph_query,
            name="graph_query",
            description="Query the knowledge graph to find entities and relationships between concepts.",
            args_schema=GraphQueryInput,
        )

    def _create_image_search_tool(self):
        """Image Search LangChain tool 생성"""
        provider = self

        def image_search(query: str, top_k: int = 3, document_id: Optional[str] = None) -> str:
            """Search for relevant images in the knowledge base using semantic similarity.

            Use this tool when the user asks about diagrams, figures, charts, images,
            or visual content from documents.
            """
            if provider._multimodal_service is None:
                return "Image search is not available. Multimodal service not configured."

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            provider._multimodal_service.search_images(
                                query=query,
                                limit=top_k,
                                document_id=document_id,
                                include_data=False,  # Don't include binary in tool response
                            )
                        )
                        results = future.result()
                else:
                    results = loop.run_until_complete(
                        provider._multimodal_service.search_images(
                            query=query,
                            limit=top_k,
                            document_id=document_id,
                            include_data=False,
                        )
                    )
            except RuntimeError:
                results = asyncio.run(
                    provider._multimodal_service.search_images(
                        query=query,
                        limit=top_k,
                        document_id=document_id,
                        include_data=False,
                    )
                )

            if not results:
                return "No relevant images found for the query."

            # Format results for LLM consumption
            output_parts = [f"Found {len(results)} relevant image(s):\n"]
            for i, img in enumerate(results, 1):
                output_parts.append(
                    f"{i}. Image ID: {img['image_id']}\n"
                    f"   Document: {img['document_id']}\n"
                    f"   Page: {img.get('page_number', 'N/A')}\n"
                    f"   Description: {img.get('description', 'No description')}\n"
                    f"   Similarity: {img['similarity']:.2f}\n"
                )

            return "\n".join(output_parts)

        return StructuredTool.from_function(
            func=image_search,
            name="image_search",
            description="Search for relevant images, diagrams, figures, or charts in the document knowledge base. Use this when questions involve visual content.",
            args_schema=ImageSearchInput,
        )


def create_vector_search_tool(rag_service=None) -> Optional[Any]:
    """Vector search tool 팩토리 함수"""
    provider = RAGToolsProvider(rag_service)
    return provider._create_vector_search_tool()


def create_graph_query_tool(rag_service=None) -> Optional[Any]:
    """Graph query tool 팩토리 함수"""
    provider = RAGToolsProvider(rag_service)
    return provider._create_graph_query_tool()


def create_image_search_tool(multimodal_service=None) -> Optional[Any]:
    """Image search tool 팩토리 함수"""
    provider = RAGToolsProvider(multimodal_service=multimodal_service)
    return provider._create_image_search_tool()


def get_rag_tools(rag_service=None, multimodal_service=None, context=None) -> List[Any]:
    """모든 RAG 도구 반환 (이미지 검색 포함)"""
    provider = RAGToolsProvider(rag_service, multimodal_service)
    if context:
        provider.set_context(context)
    return provider.get_tools()
