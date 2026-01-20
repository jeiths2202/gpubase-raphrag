"""
Deep Query Analysis Module for Hybrid RAG System

Provides comprehensive query understanding through:
1. Intent Classification - What type of question is this?
2. Entity Extraction - What products/concepts are being asked about?
3. Query Decomposition - Break complex queries into retrievable sub-queries
4. Retrieval Strategy - Determine optimal search approach

This replaces simple keyword extraction with semantic query understanding.
"""
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(Enum):
    """Classification of user query intent"""
    DEFINITION = "definition"           # "X란 무엇인가?", "X의 개요"
    COMPARISON = "comparison"           # "A와 B의 차이점", "A vs B"
    TROUBLESHOOTING = "troubleshooting" # "에러 해결", "문제 발생"
    HOW_TO = "how_to"                   # "설정 방법", "사용법"
    FEATURE = "feature"                 # "기능 설명", "지원 여부"
    LIST = "list"                       # "종류", "목록"
    GENERAL = "general"                 # 기타 일반 질문


class EntityType(Enum):
    """Types of entities that can be extracted from queries"""
    PRODUCT = "product"         # OSC, OSI, HiDB, TACF, Base, Batch
    ERROR_CODE = "error_code"   # -5212, ABEND, etc.
    CONCEPT = "concept"         # 리호스트, 마이그레이션, 트랜잭션
    COMMAND = "command"         # oscboot, tjesmgr, etc.
    CONFIG = "config"           # osc.conf, tjes.conf, etc.


@dataclass
class ExtractedEntity:
    """An entity extracted from the query"""
    name: str
    type: EntityType
    doc_filter: Optional[str] = None  # Document filename filter pattern

    def __post_init__(self):
        """Auto-generate doc_filter based on entity type and name"""
        if self.doc_filter is None and self.type == EntityType.PRODUCT:
            # OpenFrame products follow OF_{PRODUCT}_ naming convention
            self.doc_filter = f"OF_{self.name.upper()}"


@dataclass
class QueryAnalysisResult:
    """Complete analysis of a user query"""
    original_query: str
    intent: QueryIntent
    confidence: float
    entities: List[ExtractedEntity] = field(default_factory=list)
    sub_queries: List[str] = field(default_factory=list)
    retrieval_hints: Dict[str, any] = field(default_factory=dict)

    def get_doc_filters(self) -> List[str]:
        """Get document filters for all product entities"""
        return [e.doc_filter for e in self.entities
                if e.doc_filter and e.type == EntityType.PRODUCT]

    def is_multi_entity(self) -> bool:
        """Check if query involves multiple entities (e.g., comparison)"""
        return len([e for e in self.entities if e.type == EntityType.PRODUCT]) > 1


class QueryAnalyzer:
    """
    Deep Query Analyzer for understanding user intent and extracting entities.

    This analyzer provides semantic understanding of queries to enable
    more targeted retrieval strategies.
    """

    # OpenFrame product names (auto-detected, no hardcoding of specific behaviors)
    KNOWN_PRODUCTS = {
        "OSC", "OSI", "HIDB", "TACF", "BASE", "BATCH", "TJES",
        "GW", "MANAGER", "COBOL", "PLI", "ASM"
    }

    # Intent detection patterns (language-agnostic where possible)
    INTENT_PATTERNS = {
        QueryIntent.COMPARISON: [
            r'비교|차이|다른\s*점|vs\.?|versus|比較|違い|差',
            r'(\w+)[와과]\s*(\w+)\s*(비교|차이|다른)',
            r'(\w+)\s*(と|versus|vs\.?)\s*(\w+)',
        ],
        QueryIntent.DEFINITION: [
            r'(이?란|무엇|뭐|개요|소개|정의|とは|概要|紹介|what\s+is)',
            r'(설명해|알려|説明|教えて|explain|describe)',
        ],
        QueryIntent.TROUBLESHOOTING: [
            r'(에러|오류|문제|해결|안\s*됨|실패|エラー|失敗|error|fail|issue)',
            r'(-\d{4}|ABEND|CRASH)',  # Error codes
        ],
        QueryIntent.HOW_TO: [
            r'(방법|어떻게|설정|구성|설치|사용법|方法|設定|インストール|how\s+to|configure|install|setup)',
        ],
        QueryIntent.FEATURE: [
            r'(기능|지원|가능|できる|サポート|feature|support|capability)',
        ],
        QueryIntent.LIST: [
            r'(종류|목록|리스트|어떤|一覧|種類|list|types|what\s+are)',
        ],
    }

    # Error code patterns
    ERROR_PATTERNS = [
        r'-\d{4,5}',           # Numeric error codes like -5212
        r'[A-Z]{2,4}\d{3,4}',  # Alphanumeric codes like OSC0001
        r'ABEND\s*[A-Z0-9]*',  # ABEND codes
    ]

    def __init__(self):
        """Initialize the query analyzer"""
        # Compile regex patterns for performance
        self._compiled_intent_patterns = {
            intent: [re.compile(p, re.IGNORECASE) for p in patterns]
            for intent, patterns in self.INTENT_PATTERNS.items()
        }
        self._compiled_error_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.ERROR_PATTERNS
        ]

    def analyze(self, query: str) -> QueryAnalysisResult:
        """
        Perform deep analysis of a user query.

        Args:
            query: The user's natural language query

        Returns:
            QueryAnalysisResult with intent, entities, and retrieval hints
        """
        # Normalize query
        normalized = self._normalize_query(query)

        # Step 1: Classify intent
        intent, confidence = self._classify_intent(normalized)

        # Step 2: Extract entities
        entities = self._extract_entities(normalized)

        # Step 3: Generate sub-queries based on intent
        sub_queries = self._generate_sub_queries(normalized, intent, entities)

        # Step 4: Generate retrieval hints
        retrieval_hints = self._generate_retrieval_hints(intent, entities)

        return QueryAnalysisResult(
            original_query=query,
            intent=intent,
            confidence=confidence,
            entities=entities,
            sub_queries=sub_queries,
            retrieval_hints=retrieval_hints
        )

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent processing"""
        # Remove extra whitespace
        normalized = ' '.join(query.split())
        return normalized

    def _classify_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """
        Classify the intent of the query.

        Returns:
            Tuple of (QueryIntent, confidence score)
        """
        scores = {intent: 0.0 for intent in QueryIntent}

        for intent, patterns in self._compiled_intent_patterns.items():
            for pattern in patterns:
                if pattern.search(query):
                    scores[intent] += 1.0

        # Find highest scoring intent
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]

        if max_score == 0:
            return QueryIntent.GENERAL, 0.5

        # Normalize confidence
        total = sum(scores.values())
        confidence = max_score / total if total > 0 else 0.5

        return max_intent, min(confidence, 1.0)

    def _extract_entities(self, query: str) -> List[ExtractedEntity]:
        """
        Extract entities (products, error codes, concepts) from the query.
        """
        entities = []
        query_upper = query.upper()

        # Extract product names
        for product in self.KNOWN_PRODUCTS:
            # Check for product mention
            # Use flexible pattern that works with Korean/Japanese particles
            # Korean particles: 와/과/의/을/를/은/는/이/가/란/에/로/라/도
            # Japanese particles: と/の/を/は/が/で
            pattern = rf'(?:^|[\s,、\(\[])({product})(?:[\s,、와과의을를은는이가란에로라도とのをはがで\)\]?]|$)'
            if re.search(pattern, query_upper):
                entities.append(ExtractedEntity(
                    name=product,
                    type=EntityType.PRODUCT
                ))

        # Extract error codes
        for pattern in self._compiled_error_patterns:
            matches = pattern.findall(query)
            for match in matches:
                entities.append(ExtractedEntity(
                    name=match,
                    type=EntityType.ERROR_CODE,
                    doc_filter="Error"  # Search in error reference guides
                ))

        # Extract OpenFrame-style identifiers (e.g., OPENFRAME, OF_*)
        of_pattern = re.compile(r'\bOF[_/]?(\w+)\b', re.IGNORECASE)
        for match in of_pattern.finditer(query):
            product_name = match.group(1).upper()
            if product_name in self.KNOWN_PRODUCTS:
                # Already captured above
                continue
            entities.append(ExtractedEntity(
                name=product_name,
                type=EntityType.PRODUCT
            ))

        return entities

    def _generate_sub_queries(
        self,
        query: str,
        intent: QueryIntent,
        entities: List[ExtractedEntity]
    ) -> List[str]:
        """
        Generate optimized sub-queries based on intent and entities.

        For comparison queries, generates separate definition queries for each entity.
        For troubleshooting, generates error-focused queries.
        """
        sub_queries = []
        product_entities = [e for e in entities if e.type == EntityType.PRODUCT]

        if intent == QueryIntent.COMPARISON and len(product_entities) >= 2:
            # For comparison: get definition of each product
            for entity in product_entities:
                # Generate definition-focused sub-queries
                sub_queries.append(f"{entity.name} 概要 特徴 紹介")  # Japanese
                sub_queries.append(f"{entity.name} 시스템 개요 특징")  # Korean

        elif intent == QueryIntent.DEFINITION and product_entities:
            for entity in product_entities:
                sub_queries.append(f"OpenFrame/{entity.name} 概要 基本概念 紹介")
                sub_queries.append(f"{entity.name}システム 構造 構成要素")

        elif intent == QueryIntent.TROUBLESHOOTING:
            error_entities = [e for e in entities if e.type == EntityType.ERROR_CODE]
            for error in error_entities:
                sub_queries.append(f"{error.name} エラー 原因 対処")
                sub_queries.append(f"{error.name} 에러 해결 방법")

        elif intent == QueryIntent.HOW_TO:
            for entity in product_entities:
                sub_queries.append(f"{entity.name} 設定 方法 手順")
                sub_queries.append(f"{entity.name} 설정 방법 가이드")

        # If no specific sub-queries, use the original query
        if not sub_queries:
            sub_queries.append(query)

        return sub_queries

    def _generate_retrieval_hints(
        self,
        intent: QueryIntent,
        entities: List[ExtractedEntity]
    ) -> Dict[str, any]:
        """
        Generate hints for the retrieval system based on query analysis.
        """
        hints = {
            "intent": intent.value,
            "use_doc_filter": False,
            "doc_filters": [],
            "prioritize_intro_sections": False,
            "search_error_guides": False,
            "merge_strategy": "score",  # or "interleave" for comparison
        }

        product_entities = [e for e in entities if e.type == EntityType.PRODUCT]

        # For comparison queries with multiple products
        if intent == QueryIntent.COMPARISON and len(product_entities) >= 2:
            hints["use_doc_filter"] = True
            hints["doc_filters"] = [e.doc_filter for e in product_entities if e.doc_filter]
            hints["prioritize_intro_sections"] = True
            hints["merge_strategy"] = "interleave"

        # For definition queries
        elif intent == QueryIntent.DEFINITION and product_entities:
            hints["use_doc_filter"] = True
            hints["doc_filters"] = [e.doc_filter for e in product_entities if e.doc_filter]
            hints["prioritize_intro_sections"] = True

        # For troubleshooting
        elif intent == QueryIntent.TROUBLESHOOTING:
            hints["search_error_guides"] = True
            hints["doc_filters"] = ["Error", "Troubleshoot"]

        return hints


# Singleton instance
_analyzer: Optional[QueryAnalyzer] = None


def get_query_analyzer() -> QueryAnalyzer:
    """Get or create QueryAnalyzer singleton"""
    global _analyzer
    if _analyzer is None:
        _analyzer = QueryAnalyzer()
    return _analyzer
