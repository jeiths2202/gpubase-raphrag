"""
Intent Classification System
Analyzes user prompts to determine intent (e.g., search vs list_all).
Uses hybrid approach: rules first, LLM if ambiguous.
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Types of user intent"""
    SEARCH = "search"           # Keyword-based search
    LIST_ALL = "list_all"       # List all items (e.g., all crawled issues)
    DETAIL = "detail"           # Get details of specific item
    ANALYZE = "analyze"         # Analyze/summarize content
    CREATE = "create"           # Create new item
    UPDATE = "update"           # Update existing item
    DELETE = "delete"           # Delete item
    UNKNOWN = "unknown"         # Could not determine intent


@dataclass
class IntentResult:
    """Result of intent classification"""
    intent: IntentType
    confidence: float           # 0.0 to 1.0
    extracted_params: Dict      # Extracted parameters (e.g., product name for list_all)
    method: str                 # "rules" or "llm"


# Intent keywords by language (Korean, Japanese, English)
INTENT_KEYWORDS = {
    IntentType.LIST_ALL: {
        "patterns": [
            # Korean
            r"모두|전부|모든|리스트업|리스트|목록|전체|다\s*보여",
            r"리스팅|나열|리스팅해|보여줘|뭐가\s*있",
            # Japanese
            r"全部|すべて|一覧|リスト|リストアップ|リスティング",
            r"全て|ぜんぶ|全件|全体",
            # English
            r"list\s*all|show\s*all|all\s*of|every|all\s*issues?",
            r"get\s*all|fetch\s*all|retrieve\s*all|listing|enumerate",
        ],
        "negative_patterns": [
            # These indicate search, not list_all
            r"찾아|검색|search|find|look\s*for|探す|検索",
        ]
    },
    IntentType.SEARCH: {
        "patterns": [
            # Korean
            r"찾아|검색|찾기|검색해|찾는|검색하|조회|관련",
            r"어디|뭐가|무엇|어떤",
            # Japanese
            r"探す|探して|検索|検索して|見つけ|調べ|関連",
            r"何が|どこ",
            # English
            r"search|find|look\s*for|query|locate|where|lookup",
            r"related|about|regarding|concerning",
        ],
        "negative_patterns": []
    },
    IntentType.DETAIL: {
        "patterns": [
            # Korean
            r"자세히|상세|세부|내용|디테일",
            r"알려줘|설명해|분석해",
            # Japanese
            r"詳しく|詳細|内容|ディテール",
            r"教えて|説明して",
            # English
            r"detail|details|describe|explain|tell\s*me\s*about",
            r"more\s*info|information",
        ],
        "negative_patterns": []
    },
    IntentType.ANALYZE: {
        "patterns": [
            # Korean
            r"분석|통계|요약|정리|패턴|트렌드",
            r"얼마나|몇\s*개|비율",
            # Japanese
            r"分析|統計|要約|整理|パターン|トレンド",
            r"いくつ|何件|割合",
            # English
            r"analyze|analysis|statistics|summarize|summary",
            r"how\s*many|count|trend|pattern|ratio",
        ],
        "negative_patterns": []
    },
}

# Product/keyword extraction patterns
PRODUCT_EXTRACTION_PATTERNS = [
    # Korean: "X 이슈", "X의 이슈", "X 관련"
    r"([a-zA-Z0-9_-]+)\s*(?:이슈|버그|오류|문제|티켓)",
    r"([a-zA-Z0-9_-]+)\s*의?\s*(?:이슈|버그|오류|문제|티켓)",
    r"([a-zA-Z0-9_-]+)\s*관련",
    # Japanese: "X の issue", "X issue"
    r"([a-zA-Z0-9_-]+)\s*の?\s*(?:イシュー|バグ|エラー|問題)",
    # English: "X issues", "issues for X", "issues about X"
    r"([a-zA-Z0-9_-]+)\s+issues?",
    r"issues?\s+(?:for|about|in|of)\s+([a-zA-Z0-9_-]+)",
]

# Issue ID extraction patterns
ISSUE_ID_PATTERNS = [
    # Korean: "151592이슈", "이슈 151592", "151592번 이슈"
    r"(\d{4,8})\s*(?:이슈|번\s*이슈|번\s*이슈)",
    r"이슈\s*(\d{4,8})",
    r"#(\d{4,8})",
    # Japanese: "イシュー 151592", "151592 イシュー"
    r"(\d{4,8})\s*(?:イシュー|番)",
    r"イシュー\s*(\d{4,8})",
    # English: "issue 151592", "#151592", "issue #151592"
    r"issue\s*#?(\d{4,8})",
    r"#(\d{4,8})",
    # Generic: just a 5-8 digit number in context of detail/summary request
    r"(\d{5,8})",
]

# Patterns to detect user-specific filtering requests
USER_SPECIFIC_PATTERNS = [
    # Korean: "내가 검색한", "나의 id로", "내 검색", "나의 이슈"
    r"내가\s*검색",
    r"나의?\s*(?:id|아이디|검색|이슈|결과)",
    r"내\s*(?:검색|이슈|결과)",
    r"제가\s*(?:검색|조회|찾은)",
    # Japanese: "私の", "自分の"
    r"私の",
    r"自分の",
    r"自分が",
    # English: "my searches", "my issues", "I searched", "searched by me"
    r"my\s+(?:search|issue|result|data)",
    r"i\s+(?:searched|found|crawled)",
    r"(?:searched|crawled|found)\s+by\s+me",
]


class IntentClassifier:
    """
    Classifies user intent using hybrid approach.
    1. First try rule-based classification
    2. If confidence is low, fall back to LLM
    """

    def __init__(self, llm_adapter=None):
        """
        Initialize classifier.

        Args:
            llm_adapter: Optional LLM adapter for ambiguous cases
        """
        self.llm_adapter = llm_adapter
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency"""
        self._compiled_patterns = {}
        for intent_type, keywords in INTENT_KEYWORDS.items():
            self._compiled_patterns[intent_type] = {
                "patterns": [
                    re.compile(p, re.IGNORECASE | re.UNICODE)
                    for p in keywords["patterns"]
                ],
                "negative_patterns": [
                    re.compile(p, re.IGNORECASE | re.UNICODE)
                    for p in keywords.get("negative_patterns", [])
                ]
            }

        self._product_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE)
            for p in PRODUCT_EXTRACTION_PATTERNS
        ]

        self._user_specific_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE)
            for p in USER_SPECIFIC_PATTERNS
        ]

        self._issue_id_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE)
            for p in ISSUE_ID_PATTERNS
        ]

    def _is_user_specific(self, task: str) -> bool:
        """Check if user wants user-specific filtering"""
        for pattern in self._user_specific_patterns:
            if pattern.search(task):
                return True
        return False

    def _extract_issue_id(self, task: str) -> Optional[str]:
        """Extract specific issue ID from task"""
        for pattern in self._issue_id_patterns:
            match = pattern.search(task)
            if match:
                issue_id = match.group(1)
                # Validate it looks like an IMS issue ID (5-8 digits)
                if len(issue_id) >= 5 and len(issue_id) <= 8:
                    return issue_id
        return None

    def _extract_product(self, task: str) -> Optional[str]:
        """Extract product/keyword from task"""
        for pattern in self._product_patterns:
            match = pattern.search(task)
            if match:
                # Get the first capturing group
                product = match.group(1)
                # Filter out common words that aren't products
                if product.lower() not in {"all", "the", "a", "an", "my", "our"}:
                    return product
        return None

    def _score_intent(self, task: str, intent_type: IntentType) -> Tuple[int, int]:
        """
        Score how well task matches an intent type.

        Returns:
            (positive_matches, negative_matches)
        """
        compiled = self._compiled_patterns.get(intent_type, {})
        positive = 0
        negative = 0

        for pattern in compiled.get("patterns", []):
            if pattern.search(task):
                positive += 1

        for pattern in compiled.get("negative_patterns", []):
            if pattern.search(task):
                negative += 1

        return positive, negative

    async def classify(self, task: str, agent_type: str = None) -> IntentResult:
        """
        Classify the intent of a task.

        Args:
            task: User's task/query
            agent_type: Optional agent type for context-specific classification

        Returns:
            IntentResult with intent type, confidence, and extracted params
        """
        import sys

        task_lower = task.lower()

        # Extract product/keyword
        product = self._extract_product(task)
        extracted_params = {}
        if product:
            extracted_params["product"] = product

        # Extract specific issue ID
        issue_id = self._extract_issue_id(task)
        if issue_id:
            extracted_params["issue_id"] = issue_id
            logger.info(f"[Intent] Extracted issue_id: {issue_id}")

        # Check if user wants user-specific filtering
        user_specific = self._is_user_specific(task)
        extracted_params["user_specific"] = user_specific

        # Score each intent type
        scores: Dict[IntentType, float] = {}

        for intent_type in [IntentType.LIST_ALL, IntentType.SEARCH,
                           IntentType.DETAIL, IntentType.ANALYZE]:
            positive, negative = self._score_intent(task, intent_type)
            # Negative patterns reduce score
            score = max(0, positive - negative * 2)
            scores[intent_type] = score

            if score > 0:
                logger.info(f"[Intent] {intent_type.value}: +{positive} -{negative} = {score}")

        # If issue_id is present and DETAIL or ANALYZE has any score, boost it
        if issue_id:
            if scores[IntentType.DETAIL] > 0 or scores[IntentType.ANALYZE] > 0:
                # Boost DETAIL/ANALYZE when specific issue ID is mentioned
                scores[IntentType.DETAIL] += 2
                scores[IntentType.ANALYZE] += 1
                logger.info(f"[Intent] Boosted DETAIL/ANALYZE due to issue_id")
            elif scores[IntentType.LIST_ALL] == 0 and scores[IntentType.SEARCH] == 0:
                # If no other intent matches, default to DETAIL for issue ID queries
                scores[IntentType.DETAIL] = 1
                logger.info(f"[Intent] Defaulting to DETAIL for issue_id query")

        # Find best match
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # Calculate confidence based on score difference
        total_score = sum(scores.values())
        if total_score > 0:
            confidence = best_score / total_score
        else:
            confidence = 0.0

        # If no clear winner or low confidence, and LLM available, use LLM
        if confidence < 0.6 and self.llm_adapter:
            logger.info(f"[Intent] Low confidence ({confidence:.2f}), using LLM")
            return await self._classify_with_llm(task, extracted_params)

        # If no matches at all, default to SEARCH for IMS agent
        if best_score == 0:
            if agent_type == "ims":
                best_intent = IntentType.SEARCH
                confidence = 0.5  # Default confidence
            else:
                best_intent = IntentType.UNKNOWN
                confidence = 0.0

        logger.info(f"[Intent] Result: {best_intent.value} (confidence={confidence:.2f})")

        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            extracted_params=extracted_params,
            method="rules"
        )

    async def _classify_with_llm(
        self,
        task: str,
        extracted_params: Dict
    ) -> IntentResult:
        """Use LLM for ambiguous cases"""
        try:
            prompt = f"""Classify the intent of this user request into one of these categories:
- search: The user wants to search/find specific items matching criteria
- list_all: The user wants to see all items (e.g., all issues for a product)
- detail: The user wants detailed information about a specific item
- analyze: The user wants analysis, statistics, or summary

User request: "{task}"

Respond with only the category name (search, list_all, detail, or analyze):"""

            response = await self.llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])

            classification = response.get("content", "").strip().lower()

            intent_map = {
                "search": IntentType.SEARCH,
                "list_all": IntentType.LIST_ALL,
                "detail": IntentType.DETAIL,
                "analyze": IntentType.ANALYZE,
            }

            intent = intent_map.get(classification, IntentType.SEARCH)

            return IntentResult(
                intent=intent,
                confidence=0.8,  # LLM generally reliable
                extracted_params=extracted_params,
                method="llm"
            )

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            # Fall back to search
            return IntentResult(
                intent=IntentType.SEARCH,
                confidence=0.5,
                extracted_params=extracted_params,
                method="rules_fallback"
            )


# Singleton instance
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier(llm_adapter=None) -> IntentClassifier:
    """Get or create the intent classifier instance"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier(llm_adapter)
    elif llm_adapter and _classifier_instance.llm_adapter is None:
        _classifier_instance.llm_adapter = llm_adapter
    return _classifier_instance
