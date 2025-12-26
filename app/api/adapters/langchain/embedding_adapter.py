"""
LangChain Embedding Adapter
Implements EmbeddingPort using LangChain's OpenAI Embeddings.
"""
from typing import Optional, List
import logging

from ...ports.embedding_port import (
    EmbeddingPort,
    EmbeddingConfig,
    EmbeddingResult,
    BatchEmbeddingResult
)

logger = logging.getLogger(__name__)


class LangChainEmbeddingAdapter(EmbeddingPort):
    """
    Embedding adapter using LangChain's OpenAI Embeddings.

    This adapter wraps LangChain's embedding integration to provide
    a clean interface that conforms to our EmbeddingPort specification.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: Optional[str] = None,
        default_config: Optional[EmbeddingConfig] = None
    ):
        self.api_key = api_key
        self.model = model
        self._dimensions = dimensions
        self.base_url = base_url
        self.default_config = default_config or EmbeddingConfig(
            model=model,
            dimensions=dimensions
        )
        self._client = None

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions"""
        return self._dimensions

    def _get_client(self, config: EmbeddingConfig):
        """Get or create LangChain OpenAI Embeddings client"""
        try:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                api_key=self.api_key,
                model=config.model,
                dimensions=config.dimensions,
                base_url=self.base_url,
                timeout=config.timeout,
                **config.extra_params
            )
        except ImportError:
            raise ImportError("langchain_openai is required for LangChainEmbeddingAdapter")

    async def embed_text(
        self,
        text: str,
        config: Optional[EmbeddingConfig] = None
    ) -> EmbeddingResult:
        """Generate embedding for single text"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            embedding = await client.aembed_query(text)

            # Estimate token count
            token_count = len(text) // 4

            return EmbeddingResult(
                text=text,
                embedding=embedding,
                token_count=token_count
            )

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def embed_texts(
        self,
        texts: List[str],
        config: Optional[EmbeddingConfig] = None
    ) -> BatchEmbeddingResult:
        """Generate embeddings for multiple texts"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            embeddings = await client.aembed_documents(texts)

            results = []
            total_tokens = 0

            for text, embedding in zip(texts, embeddings):
                token_count = len(text) // 4
                total_tokens += token_count

                results.append(EmbeddingResult(
                    text=text,
                    embedding=embedding,
                    token_count=token_count
                ))

            return BatchEmbeddingResult(
                embeddings=results,
                total_tokens=total_tokens,
                model=cfg.model
            )

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise

    async def embed_query(
        self,
        query: str,
        config: Optional[EmbeddingConfig] = None
    ) -> EmbeddingResult:
        """Generate embedding for a search query"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            embedding = await client.aembed_query(query)

            return EmbeddingResult(
                text=query,
                embedding=embedding,
                token_count=len(query) // 4
            )

        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            raise

    async def embed_documents(
        self,
        documents: List[str],
        config: Optional[EmbeddingConfig] = None
    ) -> BatchEmbeddingResult:
        """Generate embeddings for documents"""
        return await self.embed_texts(documents, config)

    async def get_available_models(self) -> List[str]:
        """Return available OpenAI embedding models"""
        return [
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002"
        ]

    async def health_check(self) -> bool:
        """Check if embedding service is accessible"""
        try:
            result = await self.embed_text("health check")
            return len(result.embedding) > 0
        except Exception:
            return False
