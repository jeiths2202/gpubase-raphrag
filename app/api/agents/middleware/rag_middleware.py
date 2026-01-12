"""
RAG Middleware and Tools for Deep Agents
기존 RAG 기능을 Deep Agents에서 사용할 수 있도록 제공

Deep Agents에서는:
1. Tools: create_deep_agent의 tools 파라미터로 전달
2. Middleware: langchain.agents.middleware.types.AgentMiddleware 상속하여 동작 커스터마이즈

이 모듈은 두 가지를 모두 제공합니다:
- RAG 도구 (vector_search, document_read 등)
- RAG 미들웨어 (시스템 프롬프트 수정, before/after 훅)
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
    from langchain.agents.middleware.types import AgentMiddleware
    MIDDLEWARE_AVAILABLE = True
except ImportError:
    MIDDLEWARE_AVAILABLE = False
    # Fallback
    class AgentMiddleware:
        name: str = "fallback"


class RAGToolsProvider:
    """
    RAG 도구 제공자

    지식베이스 검색 도구를 생성하여 Deep Agent에 전달합니다.

    사용 예시:
    ```python
    from deepagents import create_deep_agent
    from app.api.agents.middleware import RAGToolsProvider

    rag_provider = RAGToolsProvider()
    tools = rag_provider.get_tools()

    agent = create_deep_agent(
        model=my_llm,
        tools=tools,
    )
    ```
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        embedding_url: Optional[str] = None,
        index_name: str = "document_embeddings"
    ):
        self.neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = neo4j_user or os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = neo4j_password or os.getenv("NEO4J_PASSWORD", "")
        self.embedding_url = embedding_url or os.getenv("EMBEDDING_URL", "http://localhost:12801/v1")
        self.index_name = index_name
        self._vector_store = None

    def _get_vector_store(self):
        """Vector Store 초기화"""
        if self._vector_store is None:
            try:
                from langchain_community.vectorstores import Neo4jVector
                from langchain_openai import OpenAIEmbeddings

                embeddings = OpenAIEmbeddings(
                    model="nvidia/nv-embedqa-mistral-7b-v2",
                    openai_api_base=self.embedding_url,
                    openai_api_key="not-needed",
                )

                self._vector_store = Neo4jVector.from_existing_index(
                    embedding=embeddings,
                    url=self.neo4j_uri,
                    username=self.neo4j_user,
                    password=self.neo4j_password,
                    index_name=self.index_name,
                )
                logger.info(f"[RAGTools] Vector store connected: {self.neo4j_uri}")
            except Exception as e:
                logger.warning(f"[RAGTools] Failed to connect vector store: {e}")
        return self._vector_store

    def get_tools(self) -> List[Callable]:
        """RAG 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[RAGTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def vector_search(query: str, top_k: int = 5) -> str:
            """Search the knowledge base for relevant documents using semantic similarity.

            Use this tool to find documents related to a question or topic.
            Results include similarity scores and source information.

            Args:
                query: The search query or keywords
                top_k: Number of results to return (default: 5, max: 20)

            Returns:
                Relevant document contents with sources
            """
            try:
                top_k = min(max(1, top_k), 20)
                store = provider._get_vector_store()

                if store is None:
                    return "[Error] Cannot connect to knowledge base. Please try again later."

                results = store.similarity_search_with_score(query, k=top_k)

                if not results:
                    return "No relevant documents found."

                output_parts = []
                for i, (doc, score) in enumerate(results, 1):
                    source = doc.metadata.get("source", "unknown")
                    title = doc.metadata.get("title", "")
                    content = doc.page_content[:500]
                    if len(doc.page_content) > 500:
                        content += "..."

                    part = f"[{i}] (similarity: {score:.2f})\n"
                    part += f"Source: {source}\n"
                    if title:
                        part += f"Title: {title}\n"
                    part += content

                    output_parts.append(part)

                return "\n\n---\n\n".join(output_parts)

            except Exception as e:
                logger.error(f"[RAGTools] vector_search error: {e}")
                return f"Search error: {str(e)}"

        @tool
        def document_read(doc_id: str) -> str:
            """Read the full content of a specific document.

            Use this to get complete document content after finding it with vector_search.

            Args:
                doc_id: Document ID or source path

            Returns:
                Full document content
            """
            try:
                from neo4j import GraphDatabase

                driver = GraphDatabase.driver(
                    provider.neo4j_uri,
                    auth=(provider.neo4j_user, provider.neo4j_password)
                )

                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (d:Document)
                        WHERE d.source = $doc_id OR d.id = $doc_id
                        RETURN d.content as content, d.source as source, d.title as title
                        LIMIT 1
                        """,
                        doc_id=doc_id
                    )
                    record = result.single()

                    if record:
                        return f"Source: {record['source']}\nTitle: {record.get('title', 'N/A')}\n\n{record['content']}"
                    else:
                        return f"Document not found: {doc_id}"

            except Exception as e:
                logger.error(f"[RAGTools] document_read error: {e}")
                return f"Document read error: {str(e)}"

        return [vector_search, document_read]


class RAGMiddleware(AgentMiddleware):
    """
    RAG 미들웨어

    Deep Agent의 동작을 커스터마이즈합니다:
    - 시스템 프롬프트에 RAG 사용 지침 추가
    - 응답 전/후 처리

    사용 예시:
    ```python
    from deepagents import create_deep_agent
    from app.api.agents.middleware import RAGToolsProvider, RAGMiddleware

    rag_tools = RAGToolsProvider().get_tools()

    agent = create_deep_agent(
        model=my_llm,
        tools=rag_tools,
        middleware=[RAGMiddleware()],
    )
    ```
    """

    name: str = "rag_middleware"

    def __init__(
        self,
        require_search_first: bool = True,
        language: str = "en"
    ):
        """
        RAG 미들웨어 초기화

        Args:
            require_search_first: 검색 우선 규칙 적용 여부
            language: 응답 언어 (en, ko, ja)
        """
        self.require_search_first = require_search_first
        self.language = language

    def before_model(self, state, config):
        """모델 호출 전 처리"""
        # 필요시 state 수정
        return state

    def after_model(self, state, config):
        """모델 호출 후 처리"""
        # 응답 후처리 (예: 검색 없이 답변했는지 확인)
        return state


# Convenience function
def get_rag_tools(
    neo4j_uri: Optional[str] = None,
    neo4j_password: Optional[str] = None
) -> List[Callable]:
    """
    RAG 도구 목록 반환 (간편 함수)

    Args:
        neo4j_uri: Neo4j URI
        neo4j_password: Neo4j password

    Returns:
        List of RAG tools for use with create_deep_agent
    """
    provider = RAGToolsProvider(
        neo4j_uri=neo4j_uri,
        neo4j_password=neo4j_password
    )
    return provider.get_tools()


# RAG 시스템 프롬프트 (create_deep_agent의 system_prompt에 추가)
RAG_SYSTEM_PROMPT = """
## Knowledge Base Search Guidelines

You have access to the HybridRAG KMS knowledge base.

### Available Tools:

1. **vector_search**: Semantic similarity search
   - Use to find documents related to a question
   - Returns relevant excerpts with sources

2. **document_read**: Full document retrieval
   - Use to read complete document content
   - Requires document ID or source path

### Important Rules:

1. **Search First**: Before answering, ALWAYS use vector_search to find relevant information.

2. **Cite Sources**: When using search results, mention the source.
   Example: "According to document 'xyz.pdf'..."

3. **Admit Limitations**: If no relevant results, say so honestly.
   "I couldn't find relevant information in the knowledge base."

4. **No General Knowledge**: Only use information from search results.
   Don't answer from general knowledge if search returns nothing.

5. **Multiple Searches**: For complex questions, perform multiple searches to gather comprehensive information.
"""
