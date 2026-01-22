"""Reranking tool using BM25 + Semantic scoring."""
import math
import re
import httpx
from collections import Counter

from .base import Tool
from config import config


class RerankTool(Tool):
    """Rerank search results using BM25 + Semantic + Source quality."""

    name = "rerank"
    description = """Rerank and filter search results based on relevance to user query.
Use this tool AFTER collecting results from multiple search tools.

Applies:
1. BM25 scoring (keyword matching)
2. Semantic similarity scoring
3. Source quality boost (clear sources ranked higher)

Returns top 5 most relevant results."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The original user query",
            },
            "results": {
                "type": "array",
                "description": "Array of search results to rerank. Each result should have 'content' and optionally 'title', 'source_type', 'url', 'score'",
                "items": {
                    "type": "object",
                },
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query", "results"],
    }

    def __init__(self):
        self._embedding_cache = {}

    async def execute(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
    ) -> dict:
        """Rerank results using hybrid scoring."""
        if not results:
            return {"query": query, "results": [], "total": 0}

        # Deduplicate by content
        seen_content = set()
        unique_results = []
        for r in results:
            content = r.get("content", "")[:200]
            if content and content not in seen_content:
                seen_content.add(content)
                unique_results.append(r)

        # Calculate scores
        scored_results = []
        query_embedding = await self._get_embedding(query)

        for result in unique_results:
            content = result.get("content", "")
            title = result.get("title", "")

            # 1. BM25 score
            bm25_score = self._calculate_bm25(query, content + " " + title)

            # 2. Semantic score
            semantic_score = await self._calculate_semantic(query_embedding, content)

            # 3. Source quality boost
            source_boost = self._calculate_source_boost(result)

            # Combined score (weighted)
            final_score = (
                0.3 * bm25_score +
                0.5 * semantic_score +
                0.2 * source_boost
            )

            scored_results.append({
                **result,
                "bm25_score": round(bm25_score, 4),
                "semantic_score": round(semantic_score, 4),
                "source_boost": round(source_boost, 4),
                "final_score": round(final_score, 4),
            })

        # Sort by final score
        scored_results.sort(key=lambda x: x["final_score"], reverse=True)

        # Return top_k
        top_results = scored_results[:top_k]

        return {
            "query": query,
            "results": top_results,
            "total": len(top_results),
            "original_count": len(results),
            "deduplicated_count": len(unique_results),
        }

    def _calculate_bm25(self, query: str, document: str, k1: float = 1.5, b: float = 0.75) -> float:
        """Calculate BM25 score."""
        # Tokenize
        query_terms = self._tokenize(query)
        doc_terms = self._tokenize(document)

        if not query_terms or not doc_terms:
            return 0.0

        # Document frequency
        doc_len = len(doc_terms)
        avg_doc_len = 500  # Assume average
        term_freq = Counter(doc_terms)

        score = 0.0
        for term in query_terms:
            if term in term_freq:
                tf = term_freq[term]
                # Simplified IDF (assume term appears in 10% of docs)
                idf = math.log((10 - 1 + 0.5) / (1 + 0.5))
                # BM25 formula
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)

        # Normalize to 0-1
        return min(score / (len(query_terms) * 2), 1.0)

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization."""
        # Lowercase and split on non-alphanumeric
        text = text.lower()
        # Handle Korean, Japanese, English
        tokens = re.findall(r'[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]+', text)
        return tokens

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{config.embedding_api_url}/embeddings",
                    json={
                        "input": text[:512],
                        "model": config.embedding_model,
                        "input_type": "query",
                    },
                )
                response.raise_for_status()
                data = response.json()
                embedding = data["data"][0]["embedding"]
                self._embedding_cache[text] = embedding
                return embedding
        except Exception:
            return []

    async def _calculate_semantic(self, query_embedding: list[float], content: str) -> float:
        """Calculate semantic similarity."""
        if not query_embedding:
            return 0.0

        content_embedding = await self._get_embedding(content[:512])
        if not content_embedding:
            return 0.0

        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(query_embedding, content_embedding))
        norm_a = math.sqrt(sum(a * a for a in query_embedding))
        norm_b = math.sqrt(sum(b * b for b in content_embedding))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = dot_product / (norm_a * norm_b)
        return max(0.0, similarity)  # Ensure non-negative

    def _calculate_source_boost(self, result: dict) -> float:
        """Calculate source quality boost."""
        boost = 0.5  # Base score

        # Has clear title
        if result.get("title") and len(result.get("title", "")) > 5:
            boost += 0.1

        # Has document ID (from our database)
        if result.get("doc_id"):
            boost += 0.2

        # Source type boost
        source_type = result.get("source_type", "")
        if source_type == "document":
            boost += 0.15  # Internal documents
        elif source_type == "web":
            boost += 0.05  # Web pages (less trusted)

        # Has URL (verifiable source)
        if result.get("url"):
            boost += 0.05

        # High original score
        if result.get("score", 0) > 0.7:
            boost += 0.1

        return min(boost, 1.0)

    async def close(self):
        """Clear cache."""
        self._embedding_cache.clear()
