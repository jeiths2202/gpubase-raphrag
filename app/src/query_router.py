"""
Query Router for GraphRAG Hybrid System
Classifies queries and routes to appropriate RAG strategy
"""
import re
import os
import json
import math
import hashlib
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from langchain_openai import ChatOpenAI
from config import config


class QueryType(Enum):
    """Query classification types"""
    VECTOR = "vector"    # Semantic similarity search
    GRAPH = "graph"      # Relationship/entity traversal
    HYBRID = "hybrid"    # Both approaches combined
    CODE = "code"        # Code generation/analysis (routed to Code LLM)


class EmbeddingClassifier:
    """
    Embedding-based query classifier using prototype vectors

    Uses cosine similarity between query embedding and prototype embeddings
    for each query type to compute classification probabilities.

    Supports caching of prototype embeddings to avoid regeneration on each startup.
    """

    # Cache configuration
    CACHE_VERSION = "1.0"
    DEFAULT_CACHE_DIR = Path(__file__).parent / ".cache"
    CACHE_FILENAME = "prototype_embeddings.json"

    # Prototype queries for each type (multilingual)
    VECTOR_PROTOTYPES = [
        # English - definitions, explanations
        "What is this?",
        "Explain how it works",
        "Describe the process",
        "Tell me about this feature",
        "What does this mean?",
        # Korean - 정의, 설명
        "이것이 무엇인가요?",
        "설명해주세요",
        "이란 무엇인가요",
        "방법을 알려주세요",
        "어떻게 사용하나요?",
        # Japanese - 定義、説明
        "これは何ですか？",
        "説明してください",
        "とは何ですか",
        "方法を教えてください",
    ]

    GRAPH_PROTOTYPES = [
        # English - relationships, comparisons
        "What is the relationship between A and B?",
        "Compare these two options",
        "List all available items",
        "What are the differences?",
        "How are they connected?",
        # Korean - 관계, 비교
        "A와 B의 관계는?",
        "비교해주세요",
        "모든 목록을 보여주세요",
        "차이점이 뭔가요?",
        "어떻게 연결되어 있나요?",
        # Japanese - 関係、比較
        "AとBの関係は？",
        "比較してください",
        "すべてのリストを見せてください",
        "違いは何ですか？",
    ]

    HYBRID_PROTOTYPES = [
        # English - troubleshooting, analysis
        "How to fix this error?",
        "What is the cause and solution?",
        "Analyze the problem in detail",
        "Why does this error occur and how to resolve it?",
        "Troubleshoot this issue",
        # Korean - 문제해결, 분석
        "에러 해결 방법은?",
        "원인과 해결방법을 알려주세요",
        "문제를 상세히 분석해주세요",
        "왜 이 에러가 발생하고 어떻게 해결하나요?",
        "조치 방법을 알려주세요",
        # Japanese - トラブルシューティング、分析
        "エラーの解決方法は？",
        "原因と対処方法を教えてください",
        "問題を詳しく分析してください",
        "なぜこのエラーが発生し、どう解決しますか？",
    ]

    def __init__(self, embedding_service=None, cache_dir: Optional[Path] = None, use_cache: bool = True):
        """
        Initialize the embedding classifier

        Args:
            embedding_service: NeMoEmbeddingService instance (lazy loaded if None)
            cache_dir: Directory for caching prototype embeddings
            use_cache: Whether to use cached embeddings (default: True)
        """
        self._embedding_service = embedding_service
        self._prototypes: Dict[str, np.ndarray] = {}
        self._initialized = False
        self._use_cache = use_cache
        self._cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self._cache_path = self._cache_dir / self.CACHE_FILENAME

    @property
    def embedding_service(self):
        """Lazy load embedding service"""
        if self._embedding_service is None:
            from embeddings import NeMoEmbeddingService
            self._embedding_service = NeMoEmbeddingService()
        return self._embedding_service

    def _get_prototypes_hash(self) -> str:
        """
        Compute hash of prototype queries for cache invalidation

        Returns:
            MD5 hash string of all prototype queries
        """
        all_prototypes = (
            self.VECTOR_PROTOTYPES +
            self.GRAPH_PROTOTYPES +
            self.HYBRID_PROTOTYPES
        )
        content = json.dumps(all_prototypes, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _load_cache(self) -> bool:
        """
        Load prototype embeddings from cache

        Returns:
            True if cache was loaded successfully
        """
        if not self._use_cache:
            return False

        if not self._cache_path.exists():
            return False

        try:
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Validate cache version and hash
            if cache_data.get("version") != self.CACHE_VERSION:
                print("  Cache version mismatch, regenerating...")
                return False

            if cache_data.get("prototypes_hash") != self._get_prototypes_hash():
                print("  Prototype queries changed, regenerating...")
                return False

            # Load prototype vectors
            for query_type in ["vector", "graph", "hybrid"]:
                if query_type not in cache_data.get("prototypes", {}):
                    return False
                self._prototypes[query_type] = np.array(cache_data["prototypes"][query_type])

            print(f"  Loaded prototype embeddings from cache")
            return True

        except Exception as e:
            print(f"  Cache load error: {e}")
            return False

    def _save_cache(self) -> bool:
        """
        Save prototype embeddings to cache

        Returns:
            True if cache was saved successfully
        """
        if not self._use_cache:
            return False

        try:
            # Ensure cache directory exists
            self._cache_dir.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "version": self.CACHE_VERSION,
                "prototypes_hash": self._get_prototypes_hash(),
                "prototypes": {
                    query_type: proto.tolist()
                    for query_type, proto in self._prototypes.items()
                }
            }

            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            print(f"  Saved prototype embeddings to cache")
            return True

        except Exception as e:
            print(f"  Cache save error: {e}")
            return False

    def clear_cache(self) -> bool:
        """
        Clear the prototype embeddings cache

        Returns:
            True if cache was cleared successfully
        """
        try:
            if self._cache_path.exists():
                self._cache_path.unlink()
                print("Cache cleared successfully")
            return True
        except Exception as e:
            print(f"Failed to clear cache: {e}")
            return False

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _softmax(self, scores: List[float], temperature: float = 1.0) -> List[float]:
        """Apply softmax to convert scores to probabilities"""
        # Scale scores by temperature
        scaled = [s / temperature for s in scores]
        # Subtract max for numerical stability
        max_score = max(scaled)
        exp_scores = [math.exp(s - max_score) for s in scaled]
        sum_exp = sum(exp_scores)
        return [e / sum_exp for e in exp_scores]

    def initialize(self, force_regenerate: bool = False) -> bool:
        """
        Initialize prototype embeddings (with caching support)

        Args:
            force_regenerate: If True, regenerate embeddings even if cache exists

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        print("Initializing embedding classifier prototypes...")

        # Try to load from cache first (unless force_regenerate)
        if not force_regenerate and self._load_cache():
            self._initialized = True
            print("Embedding classifier initialized from cache")
            return True

        # Generate new embeddings
        try:
            print("  Generating new prototype embeddings...")

            # Generate embeddings for each prototype set
            for query_type, prototypes in [
                ("vector", self.VECTOR_PROTOTYPES),
                ("graph", self.GRAPH_PROTOTYPES),
                ("hybrid", self.HYBRID_PROTOTYPES)
            ]:
                embeddings = self.embedding_service.embed_batch(prototypes, input_type="query")
                # Compute mean prototype vector
                self._prototypes[query_type] = np.mean(embeddings, axis=0)
                print(f"  {query_type}: {len(prototypes)} prototypes -> {len(self._prototypes[query_type])}d vector")

            # Save to cache
            self._save_cache()

            self._initialized = True
            print("Embedding classifier initialized successfully")
            return True

        except Exception as e:
            print(f"Failed to initialize embedding classifier: {e}")
            return False

    def classify(self, query: str, temperature: float = 0.5) -> Dict[str, float]:
        """
        Classify query using embedding similarity

        Args:
            query: The user's query
            temperature: Softmax temperature (lower = more confident)

        Returns:
            Dictionary with probabilities for each query type
        """
        if not self._initialized:
            if not self.initialize():
                # Return uniform distribution if initialization fails
                return {"vector": 0.33, "graph": 0.33, "hybrid": 0.34}

        try:
            # Generate query embedding
            query_embedding = np.array(
                self.embedding_service.embed_text(query, input_type="query")
            )

            # Compute similarity to each prototype
            similarities = []
            for query_type in ["vector", "graph", "hybrid"]:
                sim = self._cosine_similarity(query_embedding, self._prototypes[query_type])
                similarities.append(sim)

            # Convert to probabilities
            probs = self._softmax(similarities, temperature=temperature)

            return {
                "vector": probs[0],
                "graph": probs[1],
                "hybrid": probs[2]
            }

        except Exception as e:
            print(f"Embedding classification error: {e}")
            return {"vector": 0.33, "graph": 0.33, "hybrid": 0.34}

    def get_classification_details(self, query: str) -> Dict:
        """
        Get detailed classification information

        Args:
            query: The user's query

        Returns:
            Dictionary with similarities, probabilities, and recommended type
        """
        if not self._initialized:
            self.initialize()

        try:
            query_embedding = np.array(
                self.embedding_service.embed_text(query, input_type="query")
            )

            similarities = {}
            for query_type in ["vector", "graph", "hybrid"]:
                similarities[query_type] = self._cosine_similarity(
                    query_embedding, self._prototypes[query_type]
                )

            probs = self.classify(query)
            recommended = max(probs, key=probs.get)

            return {
                "similarities": similarities,
                "probabilities": probs,
                "recommended": recommended,
                "confidence": probs[recommended]
            }

        except Exception as e:
            return {"error": str(e)}


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
        # English - Error related (entity search)
        "error code", "error codes", "err_",
        # Korean
        "관계", "연결", "연관", "연결된",
        "비교", "비교해", "비교해줘", "비교해주세요",
        "차이", "차이점", "다른점", "다른 점",
        "목록", "리스트", "나열", "열거",
        "모든", "모두", "전부", "전체",
        "어떤 문서", "어느 문서",
        "사이", "간의", "와의", "과의",
        # Korean - Error related (entity search)
        "에러 코드", "오류 코드", "에러코드", "오류코드",
        # Japanese
        "関係", "比較", "違い", "一覧", "すべて", "全て",
        # Japanese - Error related
        "エラーコード", "エラー一覧"
    ]

    # Keywords indicating hybrid approach
    HYBRID_KEYWORDS = [
        # English
        "why", "analyze", "impact", "effect", "comprehensive",
        "detailed", "in-depth", "context", "reason",
        # English - Error troubleshooting (needs both semantic + entity search)
        "fix", "resolve", "solution", "troubleshoot", "workaround",
        # Korean
        "왜", "이유", "원인",
        "분석", "분석해", "분석해줘", "분석해주세요",
        "영향", "효과", "결과",
        "상세", "상세히", "자세히", "자세하게",
        "맥락", "배경", "근거",
        "종합", "종합적",
        # Korean - Error troubleshooting (needs both semantic + entity search)
        "해결", "해결방법", "해결 방법", "조치", "조치방법", "조치 방법",
        "대처", "대처방법", "대처 방법", "대응", "대응방법", "대응 방법",
        "처리", "처리방법", "처리 방법", "수정", "수정방법", "수정 방법",
        # Japanese
        "なぜ", "分析", "影響", "詳細", "理由",
        # Japanese - Error troubleshooting (expanded)
        "解決", "解決方法", "解決法", "解決策",
        "対処", "対処方法", "対処法", "対処策",
        "対応", "対応方法", "対応策",
        "修正", "修正方法",
        "処理", "処理方法",
        "回避", "回避方法", "回避策"
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
        r'(에러|오류|error).*(해결|조치|대처|방법)',  # 에러...해결/조치/방법
        r'(해결|조치|대처).*(방법|절차)',  # 해결/조치...방법/절차
    ]

    JAPANESE_HYBRID_PATTERNS = [
        r'(エラー|error).*(解決|対処|対応|方法)',  # エラー...解決/対処/方法
        r'(解決|対処|対応).*(方法|手順)',  # 解決/対処...方法/手順
        r'(原因|理由).*(解決|対処)',  # 原因/理由...解決/対処
        r'(発生|起き).*(原因|理由)',  # 発生...原因/理由
    ]

    # Error code pattern (high priority for hybrid routing)
    # Note: Simple regex greedy matching issue - use _has_error_code() method instead
    ERROR_CODE_PATTERN = r'[A-Z]+-\d+'  # Standard format like OFM-1234

    # Keywords that indicate error codes (substrings)
    ERROR_CODE_KEYWORDS = ['ERR', 'ERROR', 'FAIL', 'EXCEPTION', 'FAULT']

    # Keywords indicating code generation/analysis is appropriate
    CODE_KEYWORDS = [
        # English - code generation
        "write code", "sample code", "code example", "example code",
        "implement", "implementation", "source code", "create a function",
        "write a function", "write function", "write a program", "write a script",
        "code snippet", "coding", "programming",
        # English - function/class creation patterns
        "python function", "java function", "javascript function",
        "function to", "class to", "method to",
        # English - code analysis
        "analyze code", "analyze this code", "explain this code",
        "code review", "syntax", "debug", "refactor",
        # Korean - 코드 생성
        "코드 작성", "코드를 작성", "코드 만들", "코드를 만들",
        "샘플 코드", "샘플코드", "예제 코드", "예제코드",
        "소스 코드", "소스코드", "구현", "구현해",
        "함수 작성", "함수를 작성", "프로그램 작성",
        "스크립트 작성", "코딩", "프로그래밍",
        # Korean - 코드 분석
        "코드 분석", "코드를 분석", "코드 설명", "코드를 설명",
        "구문 분석", "구문을 분석", "문법 분석",
        "디버그", "디버깅", "리팩토링", "리팩터링",
        # Japanese - コード生成
        "コードを書", "コード作成", "サンプルコード",
        "例コード", "ソースコード", "実装", "実装して",
        "関数を作成", "関数を書", "関数作成",
        "プログラム作成", "プログラムを書", "スクリプト作成",
        "コーディング", "プログラミング",
        # Japanese - コード分析
        "コード分析", "コードを分析", "コード説明", "コードを説明",
        "構文分析", "デバッグ", "リファクタリング",
    ]

    # Regex patterns for code-related queries
    CODE_PATTERNS = [
        # English patterns
        r'write\s+(a\s+)?(code|function|program|script)',
        r'(sample|example)\s+code',
        r'implement\s+',
        r'create\s+(a\s+)?(function|class|method)',
        r'(analyze|explain|review)\s+(this\s+)?code',
        # Korean patterns
        r'코드.*(작성|만들|생성)',
        r'(샘플|예제|소스)\s*코드',
        r'(함수|클래스|메서드).*(작성|만들|구현)',
        r'코드.*(분석|설명|리뷰)',
        r'(구문|문법).*(분석|설명)',
        # Japanese patterns
        r'コード.*(作成|書|生成)',
        r'(サンプル|例|ソース)\s*コード',
        r'(関数|クラス|メソッド).*(作成|実装)',
        r'コード.*(分析|説明|レビュー)',
        r'(構文|文法).*(分析|説明)',
    ]

    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        embedding_service=None,
        use_embedding_classifier: bool = True
    ):
        """
        Initialize the query router

        Args:
            llm: Optional LLM for advanced classification
            embedding_service: Optional embedding service for embedding classifier
            use_embedding_classifier: Whether to use embedding-based classification
        """
        self.llm = llm or ChatOpenAI(
            base_url=config.llm.api_url.replace("/chat/completions", ""),
            model=config.llm.model,
            api_key="not-needed",
            temperature=0.1
        )

        # Initialize embedding classifier (lazy initialization)
        self.use_embedding_classifier = use_embedding_classifier
        self._embedding_classifier: Optional[EmbeddingClassifier] = None
        self._embedding_service = embedding_service

        # Weights for hybrid classification
        self.rule_weight = 0.5      # Rule-based score weight
        self.embedding_weight = 0.5  # Embedding-based score weight

    @property
    def embedding_classifier(self) -> EmbeddingClassifier:
        """Lazy load embedding classifier"""
        if self._embedding_classifier is None:
            self._embedding_classifier = EmbeddingClassifier(self._embedding_service)
        return self._embedding_classifier

    def _has_error_code(self, query: str) -> bool:
        """
        Check if query contains an error code pattern

        Detects patterns like:
        - NVSM_ERR_SYSTEM_FWRITE (contains ERR/ERROR/FAIL/EXCEPTION)
        - OFM-1234 (standard error code format)
        - COBOL_COMPILE_ERROR
        """
        # Find uppercase words (potential error codes)
        words = re.findall(r'[A-Z][A-Z0-9_]+', query)

        # Check if any word contains error keywords
        for word in words:
            if any(kw in word for kw in self.ERROR_CODE_KEYWORDS):
                return True

        # Check for standard error code format: ABC-1234
        if re.search(self.ERROR_CODE_PATTERN, query):
            return True

        return False

    # Exclusion patterns for code detection (error codes, not programming)
    CODE_EXCLUSIONS = [
        # English
        "error code", "error codes", "err code", "err codes",
        # Korean
        "에러 코드", "에러코드", "오류 코드", "오류코드",
        # Japanese
        "エラーコード", "エラー コード",
    ]

    def _is_code_query(self, query: str) -> bool:
        """
        Check if query is asking for code generation or analysis

        Detects:
        - Code generation requests (sample code, write function, etc.)
        - Code analysis requests (analyze code, explain syntax, etc.)
        - Programming-related questions

        Excludes:
        - Error code references (에러 코드, error code, エラーコード)

        Returns:
            True if query should be routed to Code LLM
        """
        query_lower = query.lower()

        # Check exclusions first (error codes are NOT code generation requests)
        for exclusion in self.CODE_EXCLUSIONS:
            if exclusion in query_lower or exclusion in query:
                return False

        # Check keyword matches
        for keyword in self.CODE_KEYWORDS:
            if keyword in query_lower or keyword in query:
                return True

        # Check regex patterns
        for pattern in self.CODE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return True

        return False

    def classify_query(self, query: str, method: str = "hybrid") -> QueryType:
        """
        Classify a query to determine the best RAG strategy

        Args:
            query: The user's question
            method: Classification method - "rule", "embedding", "hybrid", or "llm"

        Returns:
            QueryType indicating recommended strategy
        """
        # Check for code queries first (highest priority)
        if self._is_code_query(query):
            return QueryType.CODE

        if method == "rule":
            result = self._rule_based_classify(query)
            return result if result else QueryType.VECTOR

        elif method == "embedding":
            if not self.use_embedding_classifier:
                return self._rule_based_classify(query) or QueryType.VECTOR
            return self._embedding_classify(query)

        elif method == "llm":
            return self._llm_classify(query)

        else:  # hybrid (default)
            return self._hybrid_classify(query)

    def _embedding_classify(self, query: str) -> QueryType:
        """
        Classify using embedding similarity only

        Args:
            query: The user's question

        Returns:
            QueryType based on embedding similarity
        """
        probs = self.embedding_classifier.classify(query)
        max_type = max(probs, key=probs.get)
        return QueryType(max_type)

    def _hybrid_classify(self, query: str) -> QueryType:
        """
        Hybrid classification combining rule-based and embedding-based approaches

        Args:
            query: The user's question

        Returns:
            QueryType based on combined scores
        """
        # Get rule-based scores
        rule_scores = self._get_rule_scores(query)

        # Check for high-confidence rule matches (error codes, etc.)
        max_rule_score = max(rule_scores.values())
        if max_rule_score >= 8:  # High confidence from rules (e.g., error codes)
            max_type = max(rule_scores, key=rule_scores.get)
            return QueryType(max_type)

        # Get embedding-based probabilities
        if self.use_embedding_classifier:
            try:
                emb_probs = self.embedding_classifier.classify(query)
            except Exception:
                emb_probs = {"vector": 0.33, "graph": 0.33, "hybrid": 0.34}
        else:
            emb_probs = {"vector": 0.33, "graph": 0.33, "hybrid": 0.34}

        # Normalize rule scores to probabilities
        rule_sum = sum(rule_scores.values()) or 1
        rule_probs = {k: v / rule_sum for k, v in rule_scores.items()}

        # Combine scores
        combined = {}
        for query_type in ["vector", "graph", "hybrid"]:
            combined[query_type] = (
                rule_probs.get(query_type, 0) * self.rule_weight +
                emb_probs.get(query_type, 0) * self.embedding_weight
            )

        # Return type with highest combined score
        max_type = max(combined, key=combined.get)
        return QueryType(max_type)

    def _get_rule_scores(self, query: str) -> Dict[str, float]:
        """
        Get raw scores from rule-based classification

        Args:
            query: The user's question

        Returns:
            Dictionary with scores for each query type
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
                graph_score += 3

        for pattern in self.KOREAN_HYBRID_PATTERNS:
            if re.search(pattern, query):
                hybrid_score += 3

        for pattern in self.JAPANESE_HYBRID_PATTERNS:
            if re.search(pattern, query):
                hybrid_score += 3

        # Korean question ending patterns for vector
        if re.search(r'(뭐|무엇|어떤|어떻게).*(예요|에요|인가요|일까요|입니까)\??$', query):
            vector_score += 2
        if re.search(r'(설명|알려|가르쳐).*(줘|주세요|주십시오)$', query):
            vector_score += 2

        # Korean installation/usage patterns -> vector
        if re.search(r'(설치|사용|실행|구성|설정).*(방법|절차|순서|과정)', query):
            vector_score += 2

        # Error code detection (high priority)
        has_error_code = self._has_error_code(query)
        has_troubleshoot_keyword = bool(re.search(
            r'(해결|조치|대처|대응|처리|수정|방법|fix|resolve|solution|troubleshoot|'
            r'解決|対処|対応|修正|処理|回避|方法)',
            query_lower
        )) or bool(re.search(
            r'(解決|対処|対応|修正|処理|回避|方法)',
            query
        ))

        if has_error_code:
            if has_troubleshoot_keyword:
                hybrid_score += 10
            else:
                graph_score += 8

        # Korean error/problem patterns (without specific error code)
        if not has_error_code and re.search(r'(에러|오류|문제|장애).*(해결|원인|이유)', query):
            hybrid_score += 2

        return {
            "vector": max(vector_score, 0.1),  # Minimum score to avoid division by zero
            "graph": max(graph_score, 0.1),
            "hybrid": max(hybrid_score, 0.1)
        }

    def _rule_based_classify(self, query: str) -> Optional[QueryType]:
        """
        Rule-based query classification using keyword matching

        Returns None if no clear match, indicating LLM should be used
        """
        scores = self._get_rule_scores(query)

        vector_score = scores["vector"]
        graph_score = scores["graph"]
        hybrid_score = scores["hybrid"]

        # Determine winner (subtract 0.1 minimum to get actual scores)
        max_score = max(vector_score, graph_score, hybrid_score)

        if max_score <= 0.1:
            return None  # No clear match, use LLM

        if hybrid_score == max_score and hybrid_score > 0.1:
            return QueryType.HYBRID
        elif graph_score > vector_score:
            return QueryType.GRAPH
        elif vector_score > 0.1:
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
    import sys

    # Test the query router
    print("Testing Query Router...")
    print("=" * 60)

    # Check if embedding test is requested
    test_embedding = "--embedding" in sys.argv or "-e" in sys.argv
    test_compare = "--compare" in sys.argv or "-c" in sys.argv

    # Initialize router (without embedding classifier for basic test)
    router = QueryRouter(use_embedding_classifier=test_embedding or test_compare)

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
        # Error code patterns - Hybrid (error code + troubleshooting)
        ("NVSM_ERR_SYSTEM_FWRITE 에러의 조치방법에 대해서 알려주세요", QueryType.HYBRID),
        ("OFM-1234 에러 해결 방법", QueryType.HYBRID),
        ("COBOL_COMPILE_ERROR 수정 방법 알려줘", QueryType.HYBRID),
        # Error code patterns - Graph (error code only, no troubleshooting)
        ("NVSM_ERR_SYSTEM_FWRITE 에러가 뭐야?", QueryType.GRAPH),
        ("OFM-1234 에러 설명해줘", QueryType.GRAPH),
        # Japanese - Vector
        ("OpenFrameとは何ですか？", QueryType.VECTOR),
        ("OFCOBOLのインストール方法を教えてください", QueryType.VECTOR),
        ("システムの説明をお願いします", QueryType.VECTOR),
        # Japanese - Graph
        ("OFCOBOLとOFASMの違いは？", QueryType.GRAPH),
        ("すべてのエラーコード一覧", QueryType.GRAPH),
        ("ドキュメント間の関係", QueryType.GRAPH),
        # Japanese - Hybrid (error code + troubleshooting)
        ("NVSM_ERR_SYSTEM_FWRITE エラーの対処方法", QueryType.HYBRID),
        ("OFM-1234 エラーの解決方法を教えてください", QueryType.HYBRID),
        ("COBOL_COMPILE_ERROR の対応方法", QueryType.HYBRID),
        ("エラーが発生する原因と対処法", QueryType.HYBRID),
        # Japanese - Graph (error code only, no troubleshooting)
        ("NVSM_ERR_SYSTEM_FWRITE エラーとは？", QueryType.GRAPH),
    ]

    if test_compare:
        # Compare rule-based vs embedding vs hybrid classification
        print("\n[Comparison Mode: Rule vs Embedding vs Hybrid]")
        print("-" * 80)

        results = {"rule": 0, "embedding": 0, "hybrid": 0}
        total = len(test_queries)

        for query, expected in test_queries:
            rule_result = router.classify_query(query, method="rule")
            emb_result = router.classify_query(query, method="embedding")
            hybrid_result = router.classify_query(query, method="hybrid")

            rule_ok = "✓" if rule_result == expected else "✗"
            emb_ok = "✓" if emb_result == expected else "✗"
            hybrid_ok = "✓" if hybrid_result == expected else "✗"

            if rule_result == expected:
                results["rule"] += 1
            if emb_result == expected:
                results["embedding"] += 1
            if hybrid_result == expected:
                results["hybrid"] += 1

            print(f"Q: {query[:40]}")
            print(f"   Expected: {expected.value}")
            print(f"   Rule: {rule_result.value} {rule_ok} | Emb: {emb_result.value} {emb_ok} | Hybrid: {hybrid_result.value} {hybrid_ok}")
            print()

        print("=" * 80)
        print("Accuracy Summary:")
        for method, correct in results.items():
            print(f"  {method:12}: {correct}/{total} ({100*correct/total:.1f}%)")

    elif test_embedding:
        # Test embedding classifier only
        print("\n[Embedding Classifier Test]")
        print("-" * 60)

        correct = 0
        total = len(test_queries)

        for query, expected in test_queries:
            result = router.classify_query(query, method="embedding")
            details = router.embedding_classifier.get_classification_details(query)
            probs = details.get("probabilities", {})

            status = "OK" if result == expected else "MISS"
            if result == expected:
                correct += 1

            print(f"[{status}] '{query[:35]}'")
            print(f"      -> {result.value} (expected: {expected.value})")
            print(f"      Probs: V:{probs.get('vector', 0):.2f} G:{probs.get('graph', 0):.2f} H:{probs.get('hybrid', 0):.2f}")

        print("=" * 60)
        print(f"Embedding Accuracy: {correct}/{total} ({100*correct/total:.1f}%)")

    else:
        # Standard rule-based test
        print("\n[Rule-based Classification Test]")
        print("-" * 60)

        correct = 0
        total = len(test_queries)

        for query, expected in test_queries:
            result = router.classify_query(query, method="rule")
            status = "OK" if result == expected else "MISS"
            if result == expected:
                correct += 1
            print(f"[{status}] '{query[:35]}' -> {result.value} (expected: {expected.value})")

        print("=" * 60)
        print(f"Rule-based Accuracy: {correct}/{total} ({100*correct/total:.1f}%)")

    print("\nUsage:")
    print("  python query_router.py           # Rule-based test")
    print("  python query_router.py -e        # Embedding classifier test")
    print("  python query_router.py -c        # Compare all methods")
