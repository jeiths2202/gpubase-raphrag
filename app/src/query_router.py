"""
Query Router for GraphRAG Hybrid System
Classifies queries and routes to appropriate RAG strategy
"""
import re
from enum import Enum
from typing import Dict, Optional
from langchain_openai import ChatOpenAI
from config import config


class QueryType(Enum):
    """Query classification types"""
    VECTOR = "vector"    # Semantic similarity search
    GRAPH = "graph"      # Relationship/entity traversal
    HYBRID = "hybrid"    # Both approaches combined


class QueryRouter:
    """
    Routes queries to appropriate RAG strategy based on query characteristics

    - VECTOR: Simple factual questions, explanations, summaries
    - GRAPH: Questions about relationships, comparisons, cross-document queries
    - HYBRID: Complex questions requiring both semantic and relational context
    """

    # Keywords indicating vector search is appropriate
    VECTOR_KEYWORDS = [
        "what is", "what are", "explain", "describe", "define",
        "how to", "how do", "summary", "overview", "meaning",
        "뭐야", "뭔가요", "설명", "무엇", "어떻게",
        "とは", "説明", "意味", "方法"
    ]

    # Keywords indicating graph traversal is appropriate
    GRAPH_KEYWORDS = [
        "relationship", "connected", "related", "between", "compare",
        "difference", "all", "list", "which documents", "across",
        "entities", "mentions", "references",
        "관계", "연결", "비교", "차이", "목록", "모든",
        "関係", "比較", "違い", "一覧", "すべて"
    ]

    # Keywords indicating hybrid approach
    HYBRID_KEYWORDS = [
        "why", "analyze", "impact", "effect", "comprehensive",
        "detailed", "in-depth", "context",
        "왜", "분석", "영향", "상세", "맥락",
        "なぜ", "分析", "影響", "詳細"
    ]

    def __init__(self, llm: Optional[ChatOpenAI] = None):
        """
        Initialize the query router

        Args:
            llm: Optional LLM for advanced classification
        """
        self.llm = llm or ChatOpenAI(
            base_url=config.llm.api_url.replace("/chat/completions", ""),
            model=config.llm.model,
            api_key="not-needed",
            temperature=0.1
        )

    def classify_query(self, query: str) -> QueryType:
        """
        Classify a query to determine the best RAG strategy

        Args:
            query: The user's question

        Returns:
            QueryType indicating recommended strategy
        """
        # First try rule-based classification (fast)
        rule_result = self._rule_based_classify(query)
        if rule_result is not None:
            return rule_result

        # Fall back to LLM-based classification (more accurate)
        return self._llm_classify(query)

    def _rule_based_classify(self, query: str) -> Optional[QueryType]:
        """
        Rule-based query classification using keyword matching

        Returns None if no clear match, indicating LLM should be used
        """
        query_lower = query.lower()

        # Count keyword matches for each type
        vector_score = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
        graph_score = sum(1 for kw in self.GRAPH_KEYWORDS if kw in query_lower)
        hybrid_score = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower)

        # Check for entity/relationship patterns (graph indicators)
        if re.search(r'between\s+\w+\s+and\s+\w+', query_lower):
            graph_score += 2
        if re.search(r'all\s+(the\s+)?\w+s?\s+(in|from|across)', query_lower):
            graph_score += 2

        # Determine winner
        max_score = max(vector_score, graph_score, hybrid_score)

        if max_score == 0:
            return None  # No clear match, use LLM

        if hybrid_score == max_score:
            return QueryType.HYBRID
        elif graph_score > vector_score:
            return QueryType.GRAPH
        else:
            return QueryType.VECTOR

    def _llm_classify(self, query: str) -> QueryType:
        """
        LLM-based query classification for complex cases
        """
        prompt = f"""Classify this query for a RAG system. Choose the most appropriate strategy:

Query: {query}

Classification options:
- VECTOR: Simple factual questions, explanations, definitions, summaries
  Examples: "What is X?", "Explain how Y works", "Describe Z"

- GRAPH: Questions about relationships, comparisons, cross-document queries, listing entities
  Examples: "What is the relationship between X and Y?", "Compare A and B", "List all errors"

- HYBRID: Complex questions requiring both semantic understanding and relationship context
  Examples: "Why does X affect Y?", "Analyze the impact of Z", "Detailed context of W"

Respond with only one word: VECTOR, GRAPH, or HYBRID"""

        try:
            response = self.llm.invoke(prompt)
            result = response.content.strip().upper()

            # Clean up response (remove thinking tokens if present)
            if "</think>" in result:
                result = result.split("</think>")[-1].strip()

            # Parse result
            if "GRAPH" in result:
                return QueryType.GRAPH
            elif "HYBRID" in result:
                return QueryType.HYBRID
            else:
                return QueryType.VECTOR

        except Exception as e:
            print(f"LLM classification error: {e}")
            return QueryType.VECTOR  # Default to vector search

    def get_query_features(self, query: str) -> Dict:
        """
        Extract features from a query for logging/analysis

        Args:
            query: The user's question

        Returns:
            Dictionary of query features
        """
        query_lower = query.lower()

        # Detect language
        korean_count = len(re.findall(r'[\uac00-\ud7af]', query))
        japanese_count = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', query))

        if korean_count > japanese_count and korean_count > len(query) * 0.1:
            language = "ko"
        elif japanese_count > korean_count and japanese_count > len(query) * 0.1:
            language = "ja"
        else:
            language = "en"

        # Check for error code patterns
        has_error_code = bool(re.search(r'[A-Z_]+ERR[A-Z_]*|[A-Z]+-\d+', query))

        return {
            "length": len(query),
            "word_count": len(query.split()),
            "language": language,
            "has_error_code": has_error_code,
            "is_question": query.strip().endswith("?") or any(
                query_lower.startswith(w) for w in ["what", "how", "why", "which", "when", "where"]
            )
        }


def get_query_router(llm: Optional[ChatOpenAI] = None) -> QueryRouter:
    """Get a configured query router instance"""
    return QueryRouter(llm)


if __name__ == "__main__":
    # Test the query router
    print("Testing Query Router...")

    router = QueryRouter()

    test_queries = [
        ("What is GraphRAG?", QueryType.VECTOR),
        ("Explain how Neo4j works", QueryType.VECTOR),
        ("What is the relationship between Document and Chunk?", QueryType.GRAPH),
        ("List all error codes in the system", QueryType.GRAPH),
        ("Compare OFCobol and OFAsm installation steps", QueryType.GRAPH),
        ("Why does this error occur and how is it related to the config?", QueryType.HYBRID),
        ("OFCobol이란 무엇인가요?", QueryType.VECTOR),
        ("문서 간의 관계를 설명해주세요", QueryType.GRAPH),
    ]

    for query, expected in test_queries:
        result = router.classify_query(query)
        features = router.get_query_features(query)
        status = "OK" if result == expected else "MISMATCH"
        print(f"[{status}] '{query[:40]}...' -> {result.value} (expected: {expected.value})")
        print(f"       Features: {features}")
