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
        # English
        "what is", "what are", "explain", "describe", "define",
        "how to", "how do", "summary", "overview", "meaning",
        "tell me about", "introduction",
        # Korean - 질문 패턴
        "무엇", "뭐야", "뭔가요", "뭐예요", "뭘까",
        "알려줘", "알려주세요", "알려 주세요",
        "설명", "설명해줘", "설명해주세요", "설명해 주세요",
        "어떻게", "어떤", "방법",
        "개요", "소개", "정의",
        "이란", "이란?", "란?", "가요?", "인가요",
        # Korean - 동사 어미
        "해줘", "해주세요", "해 주세요",
        "줘", "주세요", " 주세요",
        # Japanese
        "とは", "説明", "意味", "方法", "について"
    ]

    # Keywords indicating graph traversal is appropriate
    GRAPH_KEYWORDS = [
        # English
        "relationship", "connected", "related", "between", "compare",
        "difference", "all", "list", "which documents", "across",
        "entities", "mentions", "references", "every",
        # Korean
        "관계", "연결", "연관", "연결된",
        "비교", "비교해", "비교해줘", "비교해주세요",
        "차이", "차이점", "다른점", "다른 점",
        "목록", "리스트", "나열", "열거",
        "모든", "모두", "전부", "전체",
        "어떤 문서", "어느 문서",
        "사이", "간의", "와의", "과의",
        # Japanese
        "関係", "比較", "違い", "一覧", "すべて", "全て"
    ]

    # Keywords indicating hybrid approach
    HYBRID_KEYWORDS = [
        # English
        "why", "analyze", "impact", "effect", "comprehensive",
        "detailed", "in-depth", "context", "reason",
        # Korean
        "왜", "이유", "원인",
        "분석", "분석해", "분석해줘", "분석해주세요",
        "영향", "효과", "결과",
        "상세", "상세히", "자세히", "자세하게",
        "맥락", "배경", "근거",
        "종합", "종합적",
        # Japanese
        "なぜ", "分析", "影響", "詳細", "理由"
    ]

    # Korean question patterns (regex)
    KOREAN_VECTOR_PATTERNS = [
        r'.+이란\??$',           # ~이란?
        r'.+란\??$',             # ~란?
        r'.+[이가]\s*뭐',        # ~이/가 뭐
        r'.+[을를]\s*설명',      # ~을/를 설명
        r'.+방법',               # ~방법
        r'.+알려',               # ~알려주세요
    ]

    KOREAN_GRAPH_PATTERNS = [
        r'.+[와과]\s*.+\s*비교',     # A와 B 비교
        r'.+[와과]\s*.+\s*차이',     # A와 B 차이
        r'.+[와과]\s*.+\s*관계',     # A와 B 관계
        r'.+사이.*(관계|차이)',      # ~사이의 관계/차이
        r'모든\s*.+',               # 모든 ~
        r'.+목록',                  # ~목록
        r'.+간의\s*관계',            # ~간의 관계
        r'문서.+관계',              # 문서...관계
        r'관계.*(설명|알려)',        # 관계...설명/알려
    ]

    KOREAN_HYBRID_PATTERNS = [
        r'(이유|원인).*(해결|방법)',   # 이유...해결/방법
        r'(발생|생기).*(이유|원인)',   # 발생...이유/원인
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
        vector_score = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower or kw in query)
        graph_score = sum(1 for kw in self.GRAPH_KEYWORDS if kw in query_lower or kw in query)
        hybrid_score = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower or kw in query)

        # Check for English entity/relationship patterns (graph indicators)
        if re.search(r'between\s+\w+\s+and\s+\w+', query_lower):
            graph_score += 2
        if re.search(r'all\s+(the\s+)?\w+s?\s+(in|from|across)', query_lower):
            graph_score += 2

        # Check Korean patterns
        for pattern in self.KOREAN_VECTOR_PATTERNS:
            if re.search(pattern, query):
                vector_score += 2

        for pattern in self.KOREAN_GRAPH_PATTERNS:
            if re.search(pattern, query):
                graph_score += 3  # Higher weight for graph patterns

        for pattern in self.KOREAN_HYBRID_PATTERNS:
            if re.search(pattern, query):
                hybrid_score += 3  # Higher weight for hybrid

        # Korean question ending patterns for vector (explanations, definitions)
        if re.search(r'(뭐|무엇|어떤|어떻게).*(예요|에요|인가요|일까요|입니까)\??$', query):
            vector_score += 2
        if re.search(r'(설명|알려|가르쳐).*(줘|주세요|주십시오)$', query):
            vector_score += 2

        # Korean installation/usage patterns -> vector
        if re.search(r'(설치|사용|실행|구성|설정).*(방법|절차|순서|과정)', query):
            vector_score += 2

        # Korean error/problem patterns -> vector
        if re.search(r'(에러|오류|문제|장애).*(해결|원인|이유)', query):
            vector_score += 1
            hybrid_score += 1

        # Determine winner
        max_score = max(vector_score, graph_score, hybrid_score)

        if max_score == 0:
            return None  # No clear match, use LLM

        if hybrid_score == max_score and hybrid_score > 0:
            return QueryType.HYBRID
        elif graph_score > vector_score:
            return QueryType.GRAPH
        elif vector_score > 0:
            return QueryType.VECTOR
        else:
            return None

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
    print("=" * 60)

    router = QueryRouter()

    test_queries = [
        # English - Vector
        ("What is GraphRAG?", QueryType.VECTOR),
        ("Explain how Neo4j works", QueryType.VECTOR),
        ("How to install OFCOBOL?", QueryType.VECTOR),
        # English - Graph
        ("What is the relationship between Document and Chunk?", QueryType.GRAPH),
        ("List all error codes in the system", QueryType.GRAPH),
        ("Compare OFCobol and OFAsm installation steps", QueryType.GRAPH),
        # English - Hybrid
        ("Why does this error occur and how is it related to the config?", QueryType.HYBRID),
        # Korean - Vector
        ("OFCobol이란 무엇인가요?", QueryType.VECTOR),
        ("OFCobol 설치 방법을 알려주세요", QueryType.VECTOR),
        ("OFCOBOL 설치 절차가 어떻게 되나요?", QueryType.VECTOR),
        ("에러 코드 설명해주세요", QueryType.VECTOR),
        ("OpenFrame이란?", QueryType.VECTOR),
        ("시스템 구성 방법 알려줘", QueryType.VECTOR),
        # Korean - Graph
        ("문서 간의 관계를 설명해주세요", QueryType.GRAPH),
        ("OFCobol과 OFAsm의 차이점은?", QueryType.GRAPH),
        ("모든 에러 코드 목록", QueryType.GRAPH),
        ("A와 B를 비교해주세요", QueryType.GRAPH),
        # Korean - Hybrid
        ("이 에러가 발생하는 이유와 해결 방법", QueryType.HYBRID),
        ("설치 문제의 원인을 분석해주세요", QueryType.HYBRID),
    ]

    correct = 0
    total = len(test_queries)

    for query, expected in test_queries:
        result = router.classify_query(query)
        features = router.get_query_features(query)
        status = "OK" if result == expected else "MISS"
        if result == expected:
            correct += 1
        print(f"[{status}] '{query[:35]}' -> {result.value} (expected: {expected.value})")

    print("=" * 60)
    print(f"Accuracy: {correct}/{total} ({100*correct/total:.1f}%)")
