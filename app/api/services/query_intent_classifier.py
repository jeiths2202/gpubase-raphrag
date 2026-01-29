"""
Query Intent Classifier for Multi-Product/Multi-Query Support.

Analyzes user queries to determine:
1. Intent type (comparison, relationship, single topic, etc.)
2. Query complexity (single vs multi-step)
3. Best retrieval strategy (vector, graph, hybrid, comparison pipeline)
"""

import re
import logging
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Query intent classification types."""
    SINGLE_TOPIC = "single_topic"        # "What is TJES?"
    COMPARISON = "comparison"             # "Compare TJES and TACF", "BMS vs MFS"
    RELATIONSHIP = "relationship"         # "How do TJES and IMS relate?"
    LISTING = "listing"                   # "List all TJES commands"
    TROUBLESHOOTING = "troubleshooting"   # "Error -5212 solution"
    HOW_TO = "how_to"                     # "How to configure TACF?"
    MIGRATION = "migration"               # "Migrate from CICS to OSC"


class RetrievalStrategy(Enum):
    """Recommended retrieval strategy based on intent."""
    VECTOR = "vector"                     # Semantic similarity search
    GRAPH = "graph"                       # Entity/relationship traversal
    HYBRID = "hybrid"                     # Combined vector + graph
    COMPARISON_PIPELINE = "comparison"    # Multi-product comparison
    MULTI_PRODUCT_SEARCH = "multi_product"  # Search across multiple products


@dataclass
class IntentResult:
    """Result of query intent analysis."""
    intent: QueryIntent
    strategy: RetrievalStrategy
    confidence: float
    products: List[str]          # Detected products
    comparison_aspects: List[str]  # Aspects to compare (for comparison queries)
    is_multi_product: bool
    sub_queries: List[str]       # Decomposed sub-queries (for complex queries)
    reasoning: str               # Explanation of classification


# Comparison patterns (multilingual)
COMPARISON_PATTERNS = [
    # Japanese
    r"(.+)と(.+)の違い",           # "AとBの違い" (difference between A and B)
    r"(.+)と(.+)を比較",           # "AとBを比較" (compare A and B)
    r"(.+)と(.+)の比較",           # "AとBの比較" (comparison of A and B)
    r"(.+)vs\.?\s*(.+)",          # "A vs B"
    r"(.+)と(.+)どちらが",         # "AとBどちらが" (which is A or B)
    # Korean
    r"(.+)[와과]\s*(.+)\s*비교",    # "A와 B 비교"
    r"(.+)[와과]\s*(.+)\s*차이",    # "A와 B 차이"
    r"(.+)\s*vs\.?\s*(.+)",
    # English
    r"compare\s+(.+)\s+(?:and|with|to)\s+(.+)",
    r"difference\s+between\s+(.+)\s+and\s+(.+)",
    r"(.+)\s+versus\s+(.+)",
    r"(.+)\s+vs\.?\s+(.+)",
]

# Relationship patterns
RELATIONSHIP_PATTERNS = [
    r"(.+)と(.+)の関係",           # "AとBの関係" (relationship)
    r"(.+)と(.+)がどう連携",       # How A and B work together
    r"(.+)[와과]\s*(.+)\s*관계",
    r"how\s+(.+)\s+(?:relate|connect|work with)\s+(.+)",
    r"relationship\s+between\s+(.+)\s+and\s+(.+)",
]

# Migration patterns
MIGRATION_PATTERNS = [
    r"(.+)から(.+)へ(?:の)?移行",   # Migration from A to B
    r"(.+)에서\s*(.+)[으로]\s*이전",
    r"migrate\s+from\s+(.+)\s+to\s+(.+)",
    r"migration\s+from\s+(.+)\s+to\s+(.+)",
    r"(.+)を(.+)に置き換え",       # Replace A with B
]

# Listing patterns
LISTING_PATTERNS = [
    r"一覧|リスト|すべて|全て",     # List, all (Japanese)
    r"목록|리스트|모든|전체",       # List, all (Korean)
    r"\blist\b|\ball\b|every",    # English
]

# Troubleshooting patterns
TROUBLESHOOTING_PATTERNS = [
    r"エラー|error|에러|오류",
    r"解決|solution|해결",
    r"原因|cause|원인",
    r"[-−]\d{4,5}",              # Error codes like -5212
    r"ABEND\s+S\d{3}",           # ABEND codes
]

# How-to patterns
HOW_TO_PATTERNS = [
    r"方法|やり方|仕方",           # How to (Japanese)
    r"방법|어떻게",               # How to (Korean)
    r"how\s+to|how\s+do\s+i|how\s+can",
    r"設定|configure|설정",
    r"インストール|install|설치",
]


class QueryIntentClassifier:
    """
    Classifies query intent for optimal retrieval strategy selection.

    Supports:
    - Single topic queries (vector search)
    - Comparison queries (multi-product search)
    - Relationship queries (graph search)
    - Troubleshooting queries (hybrid search)
    - Migration queries (multi-product search)
    """

    def __init__(self):
        """Initialize the classifier with compiled patterns."""
        self.comparison_patterns = [re.compile(p, re.IGNORECASE) for p in COMPARISON_PATTERNS]
        self.relationship_patterns = [re.compile(p, re.IGNORECASE) for p in RELATIONSHIP_PATTERNS]
        self.migration_patterns = [re.compile(p, re.IGNORECASE) for p in MIGRATION_PATTERNS]
        self.listing_pattern = re.compile("|".join(LISTING_PATTERNS), re.IGNORECASE)
        self.troubleshooting_pattern = re.compile("|".join(TROUBLESHOOTING_PATTERNS), re.IGNORECASE)
        self.howto_pattern = re.compile("|".join(HOW_TO_PATTERNS), re.IGNORECASE)

        logger.info("QueryIntentClassifier initialized")

    def classify(self, query: str, detected_products: Optional[List[str]] = None) -> IntentResult:
        """
        Classify query intent and recommend retrieval strategy.

        Args:
            query: User query string
            detected_products: Pre-detected products from MultiProductDetector

        Returns:
            IntentResult with intent, strategy, and metadata
        """
        products = detected_products or []
        is_multi_product = len(products) >= 2

        # Check for comparison intent
        comparison_result = self._check_comparison(query)
        if comparison_result:
            extracted_items, aspects = comparison_result
            # Merge detected products with extracted items
            all_products = list(set(products + extracted_items))
            return IntentResult(
                intent=QueryIntent.COMPARISON,
                strategy=RetrievalStrategy.COMPARISON_PIPELINE,
                confidence=0.9,
                products=all_products,
                comparison_aspects=aspects,
                is_multi_product=True,
                sub_queries=[f"What is {p}?" for p in all_products],
                reasoning=f"Comparison query detected: comparing {', '.join(all_products)}"
            )

        # Check for relationship intent
        relationship_result = self._check_relationship(query)
        if relationship_result:
            extracted_items = relationship_result
            all_products = list(set(products + extracted_items))
            return IntentResult(
                intent=QueryIntent.RELATIONSHIP,
                strategy=RetrievalStrategy.GRAPH,
                confidence=0.85,
                products=all_products,
                comparison_aspects=[],
                is_multi_product=len(all_products) >= 2,
                sub_queries=[],
                reasoning=f"Relationship query detected between: {', '.join(all_products)}"
            )

        # Check for migration intent
        migration_result = self._check_migration(query)
        if migration_result:
            source, target = migration_result
            all_products = list(set(products + [source, target]))
            return IntentResult(
                intent=QueryIntent.MIGRATION,
                strategy=RetrievalStrategy.MULTI_PRODUCT_SEARCH,
                confidence=0.9,
                products=all_products,
                comparison_aspects=["migration_steps", "compatibility", "differences"],
                is_multi_product=True,
                sub_queries=[
                    f"What is {source}?",
                    f"What is {target}?",
                    f"Migration considerations from {source} to {target}"
                ],
                reasoning=f"Migration query: {source} → {target}"
            )

        # Check for troubleshooting intent
        if self.troubleshooting_pattern.search(query):
            return IntentResult(
                intent=QueryIntent.TROUBLESHOOTING,
                strategy=RetrievalStrategy.HYBRID,
                confidence=0.85,
                products=products,
                comparison_aspects=[],
                is_multi_product=is_multi_product,
                sub_queries=[],
                reasoning="Troubleshooting query detected (error/solution keywords)"
            )

        # Check for listing intent
        if self.listing_pattern.search(query):
            return IntentResult(
                intent=QueryIntent.LISTING,
                strategy=RetrievalStrategy.GRAPH if is_multi_product else RetrievalStrategy.VECTOR,
                confidence=0.8,
                products=products,
                comparison_aspects=[],
                is_multi_product=is_multi_product,
                sub_queries=[],
                reasoning="Listing query detected (list/all keywords)"
            )

        # Check for how-to intent
        if self.howto_pattern.search(query):
            return IntentResult(
                intent=QueryIntent.HOW_TO,
                strategy=RetrievalStrategy.HYBRID if is_multi_product else RetrievalStrategy.VECTOR,
                confidence=0.8,
                products=products,
                comparison_aspects=[],
                is_multi_product=is_multi_product,
                sub_queries=[],
                reasoning="How-to query detected"
            )

        # Default: Single topic
        strategy = RetrievalStrategy.MULTI_PRODUCT_SEARCH if is_multi_product else RetrievalStrategy.VECTOR
        return IntentResult(
            intent=QueryIntent.SINGLE_TOPIC,
            strategy=strategy,
            confidence=0.7,
            products=products,
            comparison_aspects=[],
            is_multi_product=is_multi_product,
            sub_queries=[],
            reasoning="Default classification: single topic query"
        )

    def _check_comparison(self, query: str) -> Optional[Tuple[List[str], List[str]]]:
        """
        Check if query is a comparison and extract compared items.

        Returns:
            Tuple of (compared_items, comparison_aspects) or None
        """
        for pattern in self.comparison_patterns:
            match = pattern.search(query)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    item1 = groups[0].strip()
                    item2 = groups[1].strip()
                    # Extract comparison aspects from query
                    aspects = self._extract_comparison_aspects(query)
                    return ([item1, item2], aspects)
        return None

    def _check_relationship(self, query: str) -> Optional[List[str]]:
        """Check if query asks about relationships between entities."""
        for pattern in self.relationship_patterns:
            match = pattern.search(query)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    return [groups[0].strip(), groups[1].strip()]
        return None

    def _check_migration(self, query: str) -> Optional[Tuple[str, str]]:
        """Check if query is about migration from one product to another."""
        for pattern in self.migration_patterns:
            match = pattern.search(query)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    return (groups[0].strip(), groups[1].strip())
        return None

    def _extract_comparison_aspects(self, query: str) -> List[str]:
        """Extract what aspects should be compared."""
        aspects = []

        aspect_keywords = {
            "機能|기능|feature|function": "features",
            "性能|성능|performance": "performance",
            "設定|설정|config": "configuration",
            "コマンド|명령|command": "commands",
            "使い方|사용법|usage": "usage",
            "インストール|설치|install": "installation",
            "違い|차이|difference": "differences",
        }

        for pattern, aspect in aspect_keywords.items():
            if re.search(pattern, query, re.IGNORECASE):
                aspects.append(aspect)

        # Default aspects if none found
        if not aspects:
            aspects = ["features", "differences"]

        return aspects


# Singleton instance
_classifier_instance: Optional[QueryIntentClassifier] = None


def get_query_intent_classifier() -> QueryIntentClassifier:
    """Get or create singleton QueryIntentClassifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = QueryIntentClassifier()
    return _classifier_instance
