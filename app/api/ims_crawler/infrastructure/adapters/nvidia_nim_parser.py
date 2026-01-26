"""
NVIDIA NIM Natural Language Parser - Converts NL queries to IMS search syntax

Uses NVIDIA NIM (Nemotron or Mistral) to parse natural language queries
and convert them to structured SearchIntent objects.
"""

import json
from typing import List
from ...domain.value_objects import SearchIntent, SearchIntentType
from ..ports.nl_parser_port import NLParserPort
from ....ports.llm_port import LLMPort, LLMMessage, LLMRole, LLMConfig


class NvidiaNIMParser(NLParserPort):
    """
    NVIDIA NIM-based natural language parser.

    Uses prompt engineering to extract structured search intent from NL queries.
    Supports English, Korean, and Japanese.
    """

    def __init__(self, llm: LLMPort):
        """
        Initialize parser with LLM adapter.

        Args:
            llm: LLM adapter (NVIDIA NIM via langchain)
        """
        self.llm = llm

    async def parse_query(
        self,
        natural_language_query: str,
        language: str = "en"
    ) -> SearchIntent:
        """
        Parse natural language query into structured search intent.

        Args:
            natural_language_query: User's search query
            language: Query language (en, ko, ja)

        Returns:
            SearchIntent value object

        Example:
            >>> parser = NvidiaNIMParser(llm)
            >>> intent = await parser.parse_query("Show me critical bugs from last week")
            >>> intent.intent_type
            'complex_query'
            >>> intent.priority_filters
            ['critical']
        """
        system_prompt = self._build_system_prompt(language)
        user_prompt = self._build_user_prompt(natural_language_query)

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt)
        ]

        config = LLMConfig(
            temperature=0.1,  # Low temperature for consistent parsing
            max_tokens=1024,
            model="meta/llama-3.1-70b-instruct"  # NVIDIA NIM model
        )

        response = await self.llm.generate(messages, config)

        # Parse JSON response
        try:
            parsed = json.loads(response.content)
            return self._json_to_search_intent(parsed, natural_language_query)
        except json.JSONDecodeError:
            # Fallback to keyword search if parsing fails
            return SearchIntent(
                intent_type=SearchIntentType.KEYWORD_SEARCH,
                keywords=natural_language_query.split(),
                status_filters=[],
                priority_filters=[],
                assignee_filters=[],
                project_filters=[],
                raw_query=natural_language_query,
                confidence_score=0.5
            )

    async def convert_to_ims_syntax(self, intent: SearchIntent) -> str:
        """
        Convert SearchIntent to IMS native search syntax.

        Args:
            intent: Parsed search intent

        Returns:
            IMS-compatible search query string

        Example:
            >>> syntax = await parser.convert_to_ims_syntax(intent)
            >>> syntax
            'priority=critical AND status=open'
        """
        parts = []

        # Keywords
        if intent.keywords:
            keyword_str = " OR ".join(f'text~"{kw}"' for kw in intent.keywords)
            parts.append(f"({keyword_str})")

        # Status filters
        if intent.status_filters:
            status_str = " OR ".join(f'status="{s}"' for s in intent.status_filters)
            parts.append(f"({status_str})")

        # Priority filters
        if intent.priority_filters:
            priority_str = " OR ".join(f'priority="{p}"' for p in intent.priority_filters)
            parts.append(f"({priority_str})")

        # Assignee filters
        if intent.assignee_filters:
            assignee_str = " OR ".join(f'assignee="{a}"' for a in intent.assignee_filters)
            parts.append(f"({assignee_str})")

        # Project filters
        if intent.project_filters:
            project_str = " OR ".join(f'project="{p}"' for p in intent.project_filters)
            parts.append(f"({project_str})")

        # Date range
        if intent.date_from:
            parts.append(f'created >= "{intent.date_from}"')
        if intent.date_to:
            parts.append(f'created <= "{intent.date_to}"')

        return " AND ".join(parts) if parts else "text~*"

    async def extract_keywords(self, text: str) -> List[str]:
        """
        Extract key terms from text.

        Args:
            text: Input text

        Returns:
            List of extracted keywords
        """
        # Simple implementation - split and remove common words
        stop_words = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "or"}
        words = text.lower().split()
        return [w for w in words if w not in stop_words and len(w) > 2]

    def _build_system_prompt(self, language: str) -> str:
        """Build system prompt for NL parsing"""
        return f"""You are an expert IMS (Issue Management System) query parser.

Your task is to convert natural language queries into structured JSON format.

Supported languages: English, Korean, Japanese
Current language: {language}

Output JSON schema:
{{
  "intent_type": "keyword_search|status_filter|priority_filter|date_range|assignee_filter|project_filter|complex_query|semantic_search",
  "keywords": ["word1", "word2"],
  "status_filters": ["open", "resolved", "closed"],
  "priority_filters": ["critical", "high", "medium", "low"],
  "assignee_filters": ["username"],
  "project_filters": ["project_key"],
  "date_from": "YYYY-MM-DD",
  "date_to": "YYYY-MM-DD",
  "semantic_query": "semantic search text",
  "confidence_score": 0.0-1.0
}}

Rules:
1. Extract ALL relevant filters from the query
2. Use "complex_query" for queries with multiple filters
3. Use "semantic_search" for conceptual/meaning-based queries
4. Set confidence_score based on query clarity (0.0-1.0)
5. Return ONLY valid JSON, no additional text

Examples:

Query: "Show me critical bugs from last week"
{{
  "intent_type": "complex_query",
  "keywords": ["bugs"],
  "status_filters": [],
  "priority_filters": ["critical"],
  "date_from": "2026-01-27",
  "date_to": "2026-01-04",
  "confidence_score": 0.9
}}

Query: "Find issues assigned to John"
{{
  "intent_type": "assignee_filter",
  "assignee_filters": ["John"],
  "confidence_score": 0.95
}}"""

    def _build_user_prompt(self, query: str) -> str:
        """Build user prompt with query"""
        return f'Parse this query:\n"{query}"\n\nReturn structured JSON:'

    def _json_to_search_intent(self, parsed: dict, raw_query: str) -> SearchIntent:
        """Convert parsed JSON to SearchIntent"""
        return SearchIntent(
            intent_type=SearchIntentType(parsed.get("intent_type", "keyword_search")),
            keywords=parsed.get("keywords", []),
            status_filters=parsed.get("status_filters", []),
            priority_filters=parsed.get("priority_filters", []),
            assignee_filters=parsed.get("assignee_filters", []),
            project_filters=parsed.get("project_filters", []),
            date_from=parsed.get("date_from"),
            date_to=parsed.get("date_to"),
            semantic_query=parsed.get("semantic_query"),
            include_related=True,
            include_attachments=True,
            max_results=100,
            raw_query=raw_query,
            parsed_ims_syntax=None,  # Will be set by convert_to_ims_syntax
            confidence_score=parsed.get("confidence_score", 0.7)
        )
