"""
Local RAG Adapter
Wraps LocalRAGService to match RAGService interface for web UI compatibility.
"""
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

logger = logging.getLogger(__name__)


class LocalRAGAdapter:
    """
    Adapter that wraps LocalRAGService to provide RAGService-compatible interface.
    Used when Neo4j is not available.
    """

    _instance: Optional['LocalRAGAdapter'] = None
    _initialized: bool = False

    def __init__(self):
        self._local_rag = None
        self._pool = None

    @classmethod
    def get_instance(cls) -> 'LocalRAGAdapter':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_initialized(self):
        """Ensure local RAG service is initialized"""
        if self._local_rag is None:
            import asyncpg
            from ..core.config import api_settings
            from ..infrastructure.postgres.text_chunk_repository import PostgresTextChunkRepository
            from .local_rag_service import LocalRAGService

            logger.info("Initializing Local RAG Service (PostgreSQL + Ollama)...")

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            chunk_repo = PostgresTextChunkRepository(self._pool)
            self._local_rag = LocalRAGService(text_chunk_repository=chunk_repo)

            self._initialized = True
            logger.info("Local RAG Service initialized successfully")

    async def query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        session_id: Optional[str] = None,
        use_session_docs: bool = True,
        session_weight: float = 2.0,
        user_id: Optional[str] = None,
        use_external_resources: bool = True,
        external_weight: float = 2.5
    ) -> Dict[str, Any]:
        """
        Execute RAG query using local PostgreSQL + Ollama.

        Provides same interface as RAGService.query() for compatibility.
        """
        await self._ensure_initialized()

        try:
            # Search local knowledge base
            results = await self._local_rag.search(
                query=question,
                limit=top_k,
                min_similarity=0.2
            )

            if not results:
                return {
                    "answer": "No relevant information found in the knowledge base.",
                    "sources": [],
                    "strategy": "vector",
                    "language": language,
                    "success": False
                }

            # Build context from results
            context_parts = []
            sources = []

            # Fetch document names for all document IDs
            doc_names = await self._get_document_names(
                list(set(r.get("document_id", "") for r in results if r.get("document_id")))
            )

            for i, result in enumerate(results):
                content = result.get("content", "")
                doc_id = result.get("document_id", "")
                context_parts.append(f"[{i+1}] {content[:1000]}")

                sources.append({
                    "doc_id": doc_id,
                    "doc_name": doc_names.get(doc_id, doc_id),  # Use actual doc name
                    "chunk_id": result.get("chunk_id", ""),
                    "chunk_index": result.get("chunk_index", 0),
                    "content": content[:500],
                    "score": result.get("similarity", 0.0),
                    "source_type": "local_postgres",
                    "entities": [],
                    "page_number": result.get("page_number")  # Include page number
                })

            context = "\n\n".join(context_parts)

            # Generate answer using Ollama LLM
            answer = await self._generate_answer(question, context, language)

            return {
                "answer": answer,
                "sources": sources,
                "strategy": "vector",
                "language": language,
                "success": True
            }

        except Exception as e:
            logger.error(f"Local RAG query failed: {e}")
            return {
                "answer": f"Error processing query: {str(e)}",
                "sources": [],
                "strategy": "vector",
                "language": language,
                "success": False,
                "error": str(e)
            }

    async def _generate_answer(
        self,
        question: str,
        context: str,
        language: str = "auto"
    ) -> str:
        """Generate answer using Ollama LLM."""
        import aiohttp

        # Language-specific prompts
        if language == "ko":
            prompt = f"""다음 컨텍스트를 기반으로 질문에 답변하세요. 컨텍스트에 없는 정보는 답변하지 마세요.

컨텍스트:
{context}

질문: {question}

답변:"""
        elif language == "ja":
            prompt = f"""以下のコンテキストに基づいて質問に答えてください。コンテキストにない情報は答えないでください。

コンテキスト:
{context}

質問: {question}

回答:"""
        else:
            prompt = f"""Answer the question based on the following context. Do not answer with information not in the context.

Context:
{context}

Question: {question}

Answer:"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "qwen2.5:3b",
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 1024
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("response", "").strip()
                    else:
                        logger.warning(f"Ollama generate failed: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")

        # Fallback: return context summary
        return f"Based on the knowledge base:\n\n{context[:1500]}"

    async def _get_document_names(self, document_ids: List[str]) -> Dict[str, str]:
        """
        Fetch document names from the documents table.

        Args:
            document_ids: List of document IDs to look up

        Returns:
            Dict mapping document_id to document name (original_name)
        """
        if not document_ids or not self._pool:
            return {}

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, original_name FROM documents
                    WHERE id = ANY($1)
                """, document_ids)

                return {row['id']: row['original_name'] for row in rows}
        except Exception as e:
            logger.warning(f"Failed to fetch document names: {e}")
            return {}

    async def classify_query(self, question: str) -> Dict[str, Any]:
        """Classify query type (simplified for local RAG)."""
        return {
            "query_type": "vector",
            "confidence": 0.9,
            "features": {}
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG service statistics."""
        return {
            "mode": "local",
            "embedding_model": "nomic-embed-text",
            "llm_model": "qwen2.5:3b",
            "storage": "postgresql"
        }


# Singleton accessor
_local_rag_adapter = None


async def get_local_rag_adapter() -> LocalRAGAdapter:
    """Get or create the local RAG adapter singleton."""
    global _local_rag_adapter
    if _local_rag_adapter is None:
        _local_rag_adapter = LocalRAGAdapter.get_instance()
        await _local_rag_adapter._ensure_initialized()
    return _local_rag_adapter
