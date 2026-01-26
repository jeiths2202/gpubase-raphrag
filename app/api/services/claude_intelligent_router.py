"""
Claude AI Intelligent Router

Uses Claude AI for intelligent query routing and response generation.
Combines project context understanding with query analysis for optimal
RAG strategy selection.
"""
import re
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Literal

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """RAG routing strategies"""
    VECTOR = "vector"      # Semantic similarity search
    GRAPH = "graph"        # Knowledge graph traversal
    HYBRID = "hybrid"      # Combined approach
    CODE = "code"          # Code generation/analysis


@dataclass
class QueryAnalysis:
    """Result of query analysis by Claude"""
    intent: str                           # User's intent
    strategy: RoutingStrategy             # Recommended strategy
    confidence: float                     # Confidence score (0-1)
    reasoning: str                        # Explanation
    error_codes: List[str] = field(default_factory=list)  # Detected error codes
    keywords: List[str] = field(default_factory=list)     # Key search terms
    requires_planning: bool = False       # Complex query needing multi-step
    plan: List[str] = field(default_factory=list)         # Execution plan if complex
    language: str = "auto"                # Detected language


@dataclass
class RoutingResult:
    """Complete routing decision"""
    analysis: QueryAnalysis
    search_params: Dict[str, Any]         # Parameters for search
    post_process_hints: List[str] = field(default_factory=list)  # Hints for response


# Project context for Claude (knowledge base summary)
PROJECT_CONTEXT = """
# HybridRAG Knowledge Management System

## Available Document Types
1. **Technical Manuals**: OpenFrame, OFCOBOL, OFASM, Tibero installation/configuration guides
2. **Error Reference Guides**: Error codes with causes and solutions (JP/KO/EN)
3. **API Documentation**: System APIs and integration guides
4. **Configuration Guides**: System setup and tuning

## Error Code Patterns in Knowledge Base
- OpenFrame: OFM-XXXX, OFCOBOL-XXXX, OFASM-XXXX
- Tibero: TBR-XXXX, TIBERO-XXXX
- DSALC errors: DSALC_ERR_* (-5200 ~ -5299)
- System errors: NVSM_ERR_*, OSC_ERR_*

## Search Strategy Guidelines
- **VECTOR**: Definitions, explanations, how-to guides, general questions
- **GRAPH**: Relationships, comparisons, entity listings, error code lookups
- **HYBRID**: Troubleshooting (error + solution), complex analysis, cross-document queries
"""

# Claude routing prompt template
ROUTING_PROMPT_TEMPLATE = """You are an intelligent query router for a HybridRAG Knowledge Management System.
Analyze the user's query and determine the optimal search strategy.

{project_context}

## User Query
```
{query}
```

## Your Task
Analyze the query and provide routing decision in JSON format:

```json
{{
  "intent": "Brief description of user's intent",
  "strategy": "VECTOR" | "GRAPH" | "HYBRID",
  "confidence": 0.0-1.0,
  "reasoning": "Why this strategy is best",
  "error_codes": ["extracted error codes if any"],
  "keywords": ["key search terms to extract"],
  "requires_planning": false,
  "plan": ["step 1", "step 2"] // only if requires_planning is true
}}
```

## Strategy Selection Rules
1. **VECTOR** - Use for:
   - "What is X?", "Explain Y", "How to do Z"
   - Simple factual questions
   - Definitions and explanations

2. **GRAPH** - Use for:
   - "Compare A and B", "Relationship between X and Y"
   - "List all errors", "Show all configurations"
   - Error code lookups without troubleshooting

3. **HYBRID** - Use for:
   - Error troubleshooting: "Error X - cause and solution"
   - Complex analysis requiring both semantic and relational search
   - Questions combining "what" + "why" + "how to fix"

## Error Code Detection
If you detect error codes like:
- Numeric: -5212, -1234
- Named: DSALC_ERR_*, OFM-1234, TIBERO-5678
Extract them to "error_codes" array for keyword filtering.

Respond ONLY with the JSON object, no additional text."""


class ClaudeIntelligentRouter:
    """
    Claude AI-based intelligent query router.

    Uses Claude to analyze queries and determine optimal RAG strategy.
    Supports complex query planning and error code detection.
    """

    def __init__(
        self,
        llm_service=None,
        project_context: str = PROJECT_CONTEXT,
        fallback_strategy: RoutingStrategy = RoutingStrategy.HYBRID
    ):
        """
        Initialize the intelligent router.

        Args:
            llm_service: LLM service for Claude calls
            project_context: Project-specific context for routing
            fallback_strategy: Strategy to use if routing fails
        """
        self._llm_service = llm_service
        self.project_context = project_context
        self.fallback_strategy = fallback_strategy

        # Compile error code patterns
        self._error_patterns = [
            r'[A-Z]+[-_]ERR[-_][A-Z_]+',  # DSALC_ERR_DATASET_NOT_FOUND
            r'[A-Z]+-\d{3,5}',             # OFM-1234
            r'-\d{4,5}',                   # -5212
            r'[A-Z]+_\d{4,5}',             # ERROR_5212
        ]

    @property
    def llm_service(self):
        """Lazy load LLM service"""
        if self._llm_service is None:
            try:
                from ..adapters.langchain.llm_adapter import get_llm_service
                self._llm_service = get_llm_service()
            except Exception as e:
                logger.warning(f"Failed to load LLM service: {e}")
        return self._llm_service

    def _extract_error_codes(self, query: str) -> List[str]:
        """Extract error codes from query using regex patterns"""
        error_codes = []
        for pattern in self._error_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            error_codes.extend(matches)
        return list(set(error_codes))

    def _detect_language(self, query: str) -> str:
        """Detect query language"""
        korean = len(re.findall(r'[\uac00-\ud7af]', query))
        japanese = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', query))

        if korean > japanese and korean > len(query) * 0.1:
            return "ko"
        elif japanese > korean and japanese > len(query) * 0.1:
            return "ja"
        return "en"

    def _rule_based_fallback(self, query: str) -> QueryAnalysis:
        """Rule-based fallback when Claude is unavailable"""
        error_codes = self._extract_error_codes(query)
        language = self._detect_language(query)

        # Determine strategy based on patterns
        query_lower = query.lower()

        # Check for troubleshooting keywords
        troubleshoot_keywords = [
            'fix', 'resolve', 'solution', 'troubleshoot', 'workaround',
            '해결', '조치', '대처', '수정', '방법',
            '解決', '対処', '対応', '修正'
        ]
        has_troubleshoot = any(kw in query_lower or kw in query for kw in troubleshoot_keywords)

        # Check for comparison/relationship keywords
        graph_keywords = [
            'compare', 'relationship', 'between', 'list all', 'difference',
            '비교', '관계', '차이', '목록', '모든',
            '比較', '関係', '違い', '一覧'
        ]
        has_graph = any(kw in query_lower or kw in query for kw in graph_keywords)

        # Determine strategy
        if error_codes and has_troubleshoot:
            strategy = RoutingStrategy.HYBRID
            intent = "Error troubleshooting"
            reasoning = "Query contains error code with troubleshooting intent"
        elif error_codes:
            strategy = RoutingStrategy.GRAPH
            intent = "Error code lookup"
            reasoning = "Query contains error code for lookup"
        elif has_graph:
            strategy = RoutingStrategy.GRAPH
            intent = "Relationship/comparison query"
            reasoning = "Query asks about relationships or comparisons"
        elif has_troubleshoot:
            strategy = RoutingStrategy.HYBRID
            intent = "Problem solving"
            reasoning = "Query asks for solutions without specific error code"
        else:
            strategy = RoutingStrategy.VECTOR
            intent = "Information retrieval"
            reasoning = "General information query"

        return QueryAnalysis(
            intent=intent,
            strategy=strategy,
            confidence=0.7,
            reasoning=reasoning,
            error_codes=error_codes,
            keywords=error_codes,  # Use error codes as keywords
            requires_planning=False,
            language=language
        )

    async def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze query using Claude AI.

        Args:
            query: User's query

        Returns:
            QueryAnalysis with routing decision
        """
        # Try Claude-based analysis
        if self.llm_service:
            try:
                prompt = ROUTING_PROMPT_TEMPLATE.format(
                    project_context=self.project_context,
                    query=query
                )

                response = await self.llm_service.generate(prompt)

                # Parse JSON response
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = json.loads(json_match.group())

                    return QueryAnalysis(
                        intent=result.get("intent", "Unknown"),
                        strategy=RoutingStrategy(result.get("strategy", "hybrid").lower()),
                        confidence=result.get("confidence", 0.8),
                        reasoning=result.get("reasoning", ""),
                        error_codes=result.get("error_codes", []),
                        keywords=result.get("keywords", []),
                        requires_planning=result.get("requires_planning", False),
                        plan=result.get("plan", []),
                        language=self._detect_language(query)
                    )

            except Exception as e:
                logger.warning(f"Claude analysis failed, using fallback: {e}")

        # Fallback to rule-based
        return self._rule_based_fallback(query)

    async def route(self, query: str) -> RoutingResult:
        """
        Route query to optimal strategy.

        Args:
            query: User's query

        Returns:
            RoutingResult with analysis and search parameters
        """
        analysis = await self.analyze_query(query)

        # Build search parameters based on strategy
        search_params = {
            "strategy": analysis.strategy.value,
            "query": query,
        }

        # Add keyword filter for error codes
        if analysis.error_codes:
            search_params["keyword_filter"] = analysis.error_codes[0]
            search_params["error_codes"] = analysis.error_codes

        # Add language hint
        search_params["language"] = analysis.language

        # Post-process hints based on strategy
        hints = []
        if analysis.strategy == RoutingStrategy.HYBRID:
            hints.append("Include both cause and solution in response")
        if analysis.error_codes:
            hints.append(f"Focus on error codes: {', '.join(analysis.error_codes)}")
        if analysis.requires_planning:
            hints.append("Execute multi-step plan")

        return RoutingResult(
            analysis=analysis,
            search_params=search_params,
            post_process_hints=hints
        )

    def explain_routing(self, query: str) -> Dict[str, Any]:
        """
        Get detailed explanation of routing decision (sync version).

        Args:
            query: User's query

        Returns:
            Dictionary with routing explanation
        """
        analysis = self._rule_based_fallback(query)

        return {
            "query": query,
            "detected_language": analysis.language,
            "error_codes_found": analysis.error_codes,
            "recommended_strategy": analysis.strategy.value,
            "confidence": analysis.confidence,
            "reasoning": analysis.reasoning,
            "intent": analysis.intent
        }


# Factory function
def create_intelligent_router(
    llm_service=None,
    custom_context: str = None
) -> ClaudeIntelligentRouter:
    """
    Create an intelligent router instance.

    Args:
        llm_service: Optional LLM service
        custom_context: Optional custom project context

    Returns:
        ClaudeIntelligentRouter instance
    """
    return ClaudeIntelligentRouter(
        llm_service=llm_service,
        project_context=custom_context or PROJECT_CONTEXT
    )


# Test function
if __name__ == "__main__":
    import asyncio

    async def test_router():
        router = ClaudeIntelligentRouter()

        test_queries = [
            # Vector queries
            "OpenFrame이란 무엇인가요?",
            "OFCOBOL 설치 방법을 알려주세요",

            # Graph queries
            "모든 에러 코드 목록을 보여주세요",
            "OFCobol과 OFAsm의 차이점은?",

            # Hybrid queries (error troubleshooting)
            "-5212에러의 원인에 대해서 알려줘",
            "DSALC_ERR_DATASET_NOT_FOUND 해결 방법",
            "OFM-1234 에러가 발생했습니다. 어떻게 해결하나요?",
        ]

        print("=" * 60)
        print("Claude Intelligent Router Test")
        print("=" * 60)

        for query in test_queries:
            result = await router.route(query)
            print(f"\nQuery: {query}")
            print(f"  Strategy: {result.analysis.strategy.value}")
            print(f"  Intent: {result.analysis.intent}")
            print(f"  Error Codes: {result.analysis.error_codes}")
            print(f"  Confidence: {result.analysis.confidence:.2f}")
            print(f"  Reasoning: {result.analysis.reasoning}")

    asyncio.run(test_router())
