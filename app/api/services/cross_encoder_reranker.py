"""
Cross-Encoder Re-ranker Service

Neural re-ranking using cross-encoder models for improved RAG retrieval quality.

Features:
- Uses query-document pair scoring (not just embedding similarity)
- Supports NVIDIA NIM reranker API
- Supports LLM-based re-ranking using Mistral NeMo 12B (CODE_LLM)
- Falls back to local cross-encoder models if NIM unavailable
- Configurable top-k re-ranking

Priority: NIM Reranker → LLM Reranker (Mistral) → Local CrossEncoder → Fallback

Usage:
    reranker = get_cross_encoder_reranker()
    reranked = await reranker.rerank(query, documents, top_k=5)
"""

import os
import re
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result from re-ranking a single document."""
    document: Dict[str, Any]
    score: float
    original_rank: int


class CrossEncoderReranker:
    """
    Cross-Encoder based re-ranker for improved RAG retrieval.

    Supports multiple re-ranking backends:
    1. NIM Reranker API (dedicated reranker model)
    2. LLM-based reranking (Mistral NeMo 12B - CODE_LLM)
    3. Local CrossEncoder (sentence-transformers)
    4. Fallback (original scores)
    """

    def __init__(
        self,
        nim_api_url: Optional[str] = None,
        llm_api_url: Optional[str] = None,
        model_name: str = "nvidia/nv-rerankqa-mistral-4b-v3",
        max_documents: int = 20,
        batch_size: int = 10,
    ):
        """
        Initialize the cross-encoder re-ranker.

        Args:
            nim_api_url: URL for NIM re-ranker API (optional)
            llm_api_url: URL for LLM API for LLM-based reranking (optional)
            model_name: Model name for re-ranking
            max_documents: Maximum documents to re-rank (for performance)
            batch_size: Batch size for API calls
        """
        self._nim_api_url = nim_api_url or os.getenv("NIM_RERANKER_URL")
        self._llm_api_url = llm_api_url or os.getenv("CODE_LLM_API_URL")
        self._llm_model = os.getenv("CODE_LLM_MODEL", "mistralai/Mistral-Nemo-Instruct-2407")
        self._model_name = model_name
        self._max_documents = max_documents
        self._batch_size = batch_size
        self._http_client = None
        self._local_model = None

        # Check for local cross-encoder model availability
        try:
            from sentence_transformers import CrossEncoder
            self._cross_encoder_available = True
            logger.info("[CrossEncoderReranker] sentence-transformers CrossEncoder available")
        except ImportError:
            self._cross_encoder_available = False
            logger.info("[CrossEncoderReranker] sentence-transformers not available")

        # Log available backends
        backends = []
        if self._nim_api_url:
            backends.append("NIM Reranker")
        if self._llm_api_url:
            backends.append(f"LLM ({self._llm_model})")
        if self._cross_encoder_available:
            backends.append("Local CrossEncoder")
        backends.append("Fallback")
        logger.info(f"[CrossEncoderReranker] Available backends: {' → '.join(backends)}")

    async def _get_http_client(self):
        """Get or create HTTP client for NIM API calls."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        content_key: str = "content",
    ) -> List[RerankResult]:
        """
        Re-rank documents using cross-encoder scoring.

        Args:
            query: The search query
            documents: List of documents to re-rank (each with 'content' key)
            top_k: Number of top documents to return
            content_key: Key in document dict containing text content

        Returns:
            List of RerankResult with re-ranked documents
        """
        if not documents:
            return []

        # Limit documents for performance
        docs_to_rerank = documents[:self._max_documents]

        logger.info(f"[CrossEncoderReranker] Re-ranking {len(docs_to_rerank)} documents for query: '{query[:50]}...'")
        print(f"[CrossEncoderReranker] Re-ranking {len(docs_to_rerank)} documents", flush=True)

        # Try NIM Reranker API first (fastest, most accurate)
        if self._nim_api_url:
            try:
                scores = await self._rerank_with_nim(query, docs_to_rerank, content_key)
                if scores:
                    print(f"[CrossEncoderReranker] Used NIM Reranker API", flush=True)
                    return self._create_results(docs_to_rerank, scores, top_k)
            except Exception as e:
                logger.warning(f"[CrossEncoderReranker] NIM API failed: {e}, trying LLM reranker")

        # Try LLM-based reranking (Mistral NeMo 12B)
        if self._llm_api_url:
            try:
                scores = await self._rerank_with_llm(query, docs_to_rerank, content_key)
                if scores:
                    print(f"[CrossEncoderReranker] Used LLM reranker ({self._llm_model})", flush=True)
                    return self._create_results(docs_to_rerank, scores, top_k)
            except Exception as e:
                logger.warning(f"[CrossEncoderReranker] LLM reranker failed: {e}, trying local model")

        # Try local cross-encoder
        if self._cross_encoder_available:
            try:
                scores = await self._rerank_with_local_model(query, docs_to_rerank, content_key)
                if scores:
                    print(f"[CrossEncoderReranker] Used local CrossEncoder", flush=True)
                    return self._create_results(docs_to_rerank, scores, top_k)
            except Exception as e:
                logger.warning(f"[CrossEncoderReranker] Local model failed: {e}, using fallback")

        # Fallback: use original scores
        logger.info("[CrossEncoderReranker] Using original scores as fallback")
        print(f"[CrossEncoderReranker] Used fallback (original scores)", flush=True)
        return self._fallback_rerank(docs_to_rerank, top_k)

    async def _rerank_with_nim(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        content_key: str,
    ) -> Optional[List[float]]:
        """
        Re-rank using NVIDIA NIM re-ranker API.

        Args:
            query: Search query
            documents: Documents to re-rank
            content_key: Key for content in documents

        Returns:
            List of scores or None if failed
        """
        client = await self._get_http_client()

        # Prepare passages for NIM API
        passages = []
        for doc in documents:
            content = doc.get(content_key, "")
            # Truncate long content
            if len(content) > 2000:
                content = content[:2000] + "..."
            passages.append({"text": content})

        payload = {
            "model": self._model_name,
            "query": {"text": query},
            "passages": passages,
        }

        try:
            response = await client.post(
                f"{self._nim_api_url}/v1/ranking",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            result = response.json()

            # Extract scores from NIM response
            rankings = result.get("rankings", [])
            scores = [0.0] * len(documents)
            for ranking in rankings:
                idx = ranking.get("index", 0)
                score = ranking.get("logit", 0.0)
                if 0 <= idx < len(scores):
                    scores[idx] = score

            logger.info(f"[CrossEncoderReranker] NIM API returned {len(rankings)} rankings")
            return scores

        except Exception as e:
            logger.error(f"[CrossEncoderReranker] NIM API error: {e}")
            return None

    async def _rerank_with_llm(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        content_key: str,
    ) -> Optional[List[float]]:
        """
        Re-rank using LLM-based scoring (Mistral NeMo 12B).

        Uses the LLM to score relevance of each document to the query.
        Processes in batches for efficiency.

        Args:
            query: Search query
            documents: Documents to re-rank
            content_key: Key for content in documents

        Returns:
            List of scores (0-10 scale normalized to 0-1) or None if failed
        """
        client = await self._get_http_client()

        scores = []
        batch_size = 5  # Process 5 documents per LLM call for efficiency

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            # Build prompt for batch scoring
            docs_text = ""
            for j, doc in enumerate(batch):
                content = doc.get(content_key, "")
                # Truncate long content
                if len(content) > 500:
                    content = content[:500] + "..."
                title = doc.get("section_title", doc.get("title", f"Document {i+j+1}"))
                docs_text += f"\n[Doc {j+1}] {title}\n{content}\n"

            prompt = f"""Rate the relevance of each document to the query on a scale of 0-10.
Only output JSON array with scores, nothing else.

Query: {query}

Documents:{docs_text}

Output format: [score1, score2, ...]
Example: [8, 3, 6, 2, 7]

Scores:"""

            try:
                response = await client.post(
                    self._llm_api_url,
                    json={
                        "model": self._llm_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 100,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30.0,
                )
                response.raise_for_status()

                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Parse scores from response
                # Try to extract JSON array from response
                match = re.search(r'\[[\d\s,\.]+\]', content)
                if match:
                    batch_scores = json.loads(match.group())
                    # Normalize to 0-1 scale
                    batch_scores = [min(max(float(s) / 10.0, 0.0), 1.0) for s in batch_scores]

                    # Pad if fewer scores than documents
                    while len(batch_scores) < len(batch):
                        batch_scores.append(0.5)

                    scores.extend(batch_scores[:len(batch)])
                else:
                    # Fallback: assign middle scores
                    logger.warning(f"[CrossEncoderReranker] Could not parse LLM scores: {content[:100]}")
                    scores.extend([0.5] * len(batch))

            except Exception as e:
                logger.error(f"[CrossEncoderReranker] LLM batch scoring error: {e}")
                scores.extend([0.5] * len(batch))

        logger.info(f"[CrossEncoderReranker] LLM scored {len(scores)} documents, avg: {sum(scores)/len(scores):.2f}")
        return scores if len(scores) == len(documents) else None

    async def _rerank_with_local_model(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        content_key: str,
    ) -> Optional[List[float]]:
        """
        Re-rank using local sentence-transformers CrossEncoder.

        Args:
            query: Search query
            documents: Documents to re-rank
            content_key: Key for content in documents

        Returns:
            List of scores or None if failed
        """
        from sentence_transformers import CrossEncoder

        # Lazy load model (use a small multilingual model)
        if self._local_model is None:
            model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            logger.info(f"[CrossEncoderReranker] Loading local model: {model_name}")
            self._local_model = CrossEncoder(model_name)

        # Prepare query-document pairs
        pairs = []
        for doc in documents:
            content = doc.get(content_key, "")
            # Truncate long content
            if len(content) > 1000:
                content = content[:1000] + "..."
            pairs.append([query, content])

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: self._local_model.predict(pairs).tolist()
        )

        logger.info(f"[CrossEncoderReranker] Local model scored {len(scores)} documents")
        return scores

    def _create_results(
        self,
        documents: List[Dict[str, Any]],
        scores: List[float],
        top_k: int,
    ) -> List[RerankResult]:
        """
        Create sorted RerankResult list from scores.

        Args:
            documents: Original documents
            scores: Re-ranker scores
            top_k: Number of results to return

        Returns:
            Sorted list of RerankResult
        """
        # Create (index, score) pairs
        indexed_scores = list(enumerate(scores))

        # Sort by score descending
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        # Create results
        results = []
        for rank, (original_idx, score) in enumerate(indexed_scores[:top_k]):
            results.append(RerankResult(
                document=documents[original_idx],
                score=score,
                original_rank=original_idx,
            ))

        logger.info(f"[CrossEncoderReranker] Top {top_k} results: "
                   f"ranks {[r.original_rank for r in results]}, "
                   f"scores {[f'{r.score:.3f}' for r in results]}")

        return results

    def _fallback_rerank(
        self,
        documents: List[Dict[str, Any]],
        top_k: int,
    ) -> List[RerankResult]:
        """
        Fallback: use original similarity scores.

        Args:
            documents: Original documents
            top_k: Number of results to return

        Returns:
            List of RerankResult using original scores
        """
        results = []
        for idx, doc in enumerate(documents[:top_k]):
            score = doc.get("similarity", doc.get("score", 0.0))
            results.append(RerankResult(
                document=doc,
                score=float(score),
                original_rank=idx,
            ))

        return results

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
_reranker: Optional[CrossEncoderReranker] = None


def get_cross_encoder_reranker() -> CrossEncoderReranker:
    """Get singleton CrossEncoderReranker instance."""
    global _reranker
    if _reranker is None:
        nim_url = os.getenv("NIM_RERANKER_URL")
        _reranker = CrossEncoderReranker(nim_api_url=nim_url)
    return _reranker
