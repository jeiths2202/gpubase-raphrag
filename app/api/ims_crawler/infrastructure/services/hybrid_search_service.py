"""
Hybrid Search Service

Combines BM25 keyword search with semantic embedding search
for optimal multilingual (Korean/Japanese/English) performance.
"""
import re
from typing import List, Dict, Tuple
import numpy as np

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, util


class HybridSearchService:
    """
    Production-ready hybrid search combining BM25 + Semantic.

    Features:
    - Character N-grams for CJK languages (Korean, Japanese)
    - Balanced BM25 (30%) + Semantic (70%) scoring
    - Multilingual support with paraphrase-multilingual-MiniLM-L12-v2
    """

    def __init__(
        self,
        bm25_weight: float = 0.3,
        semantic_weight: float = 0.7,
        semantic_model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'
    ):
        """
        Initialize hybrid search service.

        Args:
            bm25_weight: Weight for BM25 score (default: 0.3)
            semantic_weight: Weight for semantic score (default: 0.7)
            semantic_model_name: Sentence transformer model name
        """
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight
        self.semantic_model = SentenceTransformer(semantic_model_name)

        # Cached index state
        self.documents: List[Dict] = []
        self.contents: List[str] = []
        self.bm25: BM25Okapi = None
        self.embeddings = None

    def _tokenize(self, text: str) -> List[str]:
        """
        CJK-optimized tokenization with character bi-grams.

        For Korean/Japanese text, generates character bi-grams
        to enable partial matching. English text uses whitespace only.

        Args:
            text: Input text to tokenize

        Returns:
            List of tokens including bi-grams for CJK characters
        """
        text = text.lower()
        tokens = text.split()

        ngrams = []
        for token in tokens:
            if re.match(r'^[a-z0-9]+$', token):
                # English/numbers: use original token only
                ngrams.append(token)
            else:
                # CJK characters: generate bi-grams + original
                for i in range(len(token) - 1):
                    ngrams.append(token[i:i+2])
                ngrams.append(token)

        return tokens + ngrams

    def index_documents(self, documents: List[Dict], show_progress: bool = False):
        """
        Index documents for hybrid search.

        Args:
            documents: List of document dicts with 'content' or 'description' field
            show_progress: Show progress bar during embedding generation
        """
        if not documents:
            return

        self.documents = documents

        # Extract text content
        self.contents = []
        for doc in documents:
            content = doc.get('content') or doc.get('description', '')
            self.contents.append(content)

        # BM25 indexing with CJK tokenization
        tokenized_contents = [self._tokenize(content) for content in self.contents]
        self.bm25 = BM25Okapi(tokenized_contents)

        # Semantic embedding generation
        self.embeddings = self.semantic_model.encode(
            self.contents,
            convert_to_tensor=True,
            show_progress_bar=show_progress
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.0,
        return_scores: bool = False
    ) -> List[Tuple]:
        """
        Perform hybrid search with BM25 + Semantic scoring.

        Args:
            query: Search query (Korean/Japanese/English)
            top_k: Number of top results to return
            threshold: Minimum hybrid score (0.0-1.0)
            return_scores: Include score breakdown in results

        Returns:
            List of (document, score) or (document, score, breakdown) tuples
        """
        if not self.documents or self.bm25 is None or self.embeddings is None:
            return []

        # BM25 keyword scores
        tokenized_query = self._tokenize(query)
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_scores_norm = bm25_scores / (bm25_scores.max() + 1e-8)

        # Semantic similarity scores
        query_embedding = self.semantic_model.encode(query, convert_to_tensor=True)
        semantic_scores = util.cos_sim(query_embedding, self.embeddings)[0].cpu().numpy()

        # Hybrid scoring: weighted combination
        hybrid_scores = (
            self.bm25_weight * bm25_scores_norm +
            self.semantic_weight * semantic_scores
        )

        # Top-k selection
        top_indices = np.argsort(hybrid_scores)[::-1][:top_k]

        # Collect results
        results = []
        for idx in top_indices:
            score = float(hybrid_scores[idx])
            if score >= threshold:
                if return_scores:
                    breakdown = {
                        'bm25': float(bm25_scores_norm[idx]),
                        'semantic': float(semantic_scores[idx]),
                        'hybrid': score
                    }
                    results.append((self.documents[idx], score, breakdown))
                else:
                    results.append((self.documents[idx], score))

        return results

    def search_with_scores(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Tuple[Dict, float, Dict]]:
        """
        Convenience method for search with score breakdown.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of (document, score, breakdown) tuples
        """
        return self.search(query, top_k=top_k, return_scores=True)
