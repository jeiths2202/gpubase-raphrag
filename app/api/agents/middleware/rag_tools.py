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


class AdaptiveSearchInput(BaseModel):
    """Adaptive chunk search input schema for structure-preserving PDF search"""
    query: str = Field(description="The search query (natural language)")
    top_k: int = Field(default=5, description="Number of results to return")
    expand_relations: bool = Field(
        default=True,
        description="Whether to include related chunks (previous/next, parent/children)"
    )
    pdf_id: Optional[str] = Field(default=None, description="Optional PDF ID to filter results")
    section_filter: Optional[str] = Field(
        default=None,
        description="Optional section path prefix to filter results (e.g., '1.2' for section 1.2.x)"
    )


class RAGToolsProvider:
    """
    RAG 도구 제공자

    기존 VectorSearchTool, GraphQueryTool, ImageSearchTool, AdaptiveSearchTool을 LangChain tool로 래핑
    """

    def __init__(self, rag_service=None, multimodal_service=None, adaptive_service=None):
        """
        Args:
            rag_service: 기존 RAGService 인스턴스 (None이면 lazy load)
            multimodal_service: MultimodalRAGService 인스턴스 (None이면 lazy load)
            adaptive_service: AdaptiveEmbeddingService 인스턴스 (None이면 lazy load)
        """
        self._rag_service = rag_service
        self._multimodal_service = multimodal_service
        self._adaptive_service = adaptive_service
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

    @property
    def adaptive_service(self):
        """AdaptiveEmbeddingService lazy load"""
        if self._adaptive_service is None:
            try:
                from ...services.pdf_adaptive_embedding_service import PDFAdaptiveEmbeddingService
                from ...infrastructure.postgres.adaptive_chunk_repository import (
                    PostgresAdaptiveChunkRepository,
                    PostgresPDFStructureRepository,
                    PostgresCoverageRepository,
                )
                logger.debug("Adaptive service will be initialized on first use")
            except Exception as e:
                logger.warning(f"Failed to import adaptive service: {e}")
        return self._adaptive_service

    def set_adaptive_service(self, service):
        """Set adaptive embedding service instance"""
        self._adaptive_service = service

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

        # Adaptive Search Tool (for structure-preserving PDF search)
        adaptive_tool = self._create_adaptive_search_tool()
        if adaptive_tool:
            tools.append(adaptive_tool)

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

    def _create_adaptive_search_tool(self):
        """
        Adaptive Search LangChain tool 생성

        구조 보존 PDF 검색 도구: pgvector + 관계 확장
        """
        provider = self

        def adaptive_search(
            query: str,
            top_k: int = 5,
            expand_relations: bool = True,
            pdf_id: Optional[str] = None,
            section_filter: Optional[str] = None
        ) -> str:
            """
            Search PDFs with structure-preserving adaptive embeddings.

            Use this tool when searching through PDF documents that have been
            processed with adaptive embedding. It preserves document structure
            (sections, tables, images) and can expand results to include
            related context (previous/next chunks, parent/child sections).

            This is particularly useful for:
            - Technical manuals with hierarchical sections
            - Documents with tables and figures
            - When you need context from surrounding content
            """
            if provider._adaptive_service is None:
                return "Adaptive search is not available. Service not configured."

            try:
                # 1. Generate embedding for query
                from ...services.multimodal_embedding import TextEmbeddingService
                embedding_service = TextEmbeddingService()

                loop = asyncio.get_event_loop()

                async def do_search():
                    # Get query embedding
                    embeddings = await embedding_service.embed_texts([query])
                    if not embeddings or not embeddings[0]:
                        return "Failed to generate query embedding."

                    query_embedding = embeddings[0]

                    # Search adaptive chunks
                    results = await provider._adaptive_service.search_chunks(
                        query_embedding=query_embedding,
                        limit=top_k,
                        pdf_id=pdf_id,
                        section_path_prefix=section_filter,
                        min_similarity=0.3,
                    )

                    if not results:
                        return "No relevant content found for the query."

                    # Format results
                    output_parts = [f"Found {len(results)} relevant chunk(s):\n"]

                    for i, result in enumerate(results, 1):
                        chunk_info = (
                            f"{i}. [{result.get('chunk_type', 'TEXT')}] "
                            f"Similarity: {result.get('similarity', 0):.2%}\n"
                            f"   PDF: {result.get('pdf_id', 'Unknown')}\n"
                            f"   Pages: {result.get('page_start', '?')}-{result.get('page_end', '?')}\n"
                        )

                        if result.get('section_title'):
                            chunk_info += f"   Section: {result['section_title']}\n"
                        if result.get('section_path'):
                            chunk_info += f"   Path: {result['section_path']}\n"

                        # Content preview (truncate if too long)
                        content = result.get('content', '')
                        if len(content) > 500:
                            content = content[:500] + "..."
                        chunk_info += f"   Content: {content}\n"

                        # Related chunks info (if expand_relations)
                        if expand_relations:
                            relations = result.get('relations', {})
                            if isinstance(relations, str):
                                import json
                                try:
                                    relations = json.loads(relations)
                                except:
                                    relations = {}

                            related = []
                            if relations.get('previous'):
                                related.append(f"prev: {relations['previous'][:16]}...")
                            if relations.get('next'):
                                related.append(f"next: {relations['next'][:16]}...")
                            if relations.get('parent'):
                                related.append(f"parent: {relations['parent'][:16]}...")
                            if relations.get('children'):
                                related.append(f"children: {len(relations['children'])} items")

                            if related:
                                chunk_info += f"   Related: {', '.join(related)}\n"

                        output_parts.append(chunk_info)

                    return "\n".join(output_parts)

                # Execute async search
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, do_search())
                        result = future.result()
                else:
                    result = loop.run_until_complete(do_search())

                return result

            except Exception as e:
                logger.error(f"Adaptive search error: {e}")
                return f"Adaptive search error: {str(e)}"

        return StructuredTool.from_function(
            func=adaptive_search,
            name="adaptive_search",
            description=(
                "Search PDFs with structure-preserving adaptive embeddings. "
                "Use this for PDF documents processed with adaptive embedding. "
                "Preserves document structure (sections, tables, images) and can "
                "expand results to include related context. Best for technical "
                "manuals, structured documents, and when you need surrounding context."
            ),
            args_schema=AdaptiveSearchInput,
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


def create_adaptive_search_tool(adaptive_service=None) -> Optional[Any]:
    """Adaptive search tool 팩토리 함수 (구조 보존 PDF 검색)"""
    provider = RAGToolsProvider(adaptive_service=adaptive_service)
    return provider._create_adaptive_search_tool()


def get_rag_tools(
    rag_service=None,
    multimodal_service=None,
    adaptive_service=None,
    context=None
) -> List[Any]:
    """
    모든 RAG 도구 반환 (이미지 검색, 적응형 검색 포함)

    Args:
        rag_service: RAG service for vector/graph search
        multimodal_service: Service for image search
        adaptive_service: Service for adaptive PDF search
        context: Agent context

    Returns:
        List of LangChain tools
    """
    provider = RAGToolsProvider(rag_service, multimodal_service, adaptive_service)
    if context:
        provider.set_context(context)
    return provider.get_tools()
