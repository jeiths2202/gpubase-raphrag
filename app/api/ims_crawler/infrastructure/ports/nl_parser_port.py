"""
NL Parser Port - Interface for natural language query parsing

Uses NVIDIA NIM LLM to convert natural language to IMS search syntax.
"""

from abc import ABC, abstractmethod

from ...domain.value_objects import SearchIntent


class NLParserPort(ABC):
    """
    Abstract interface for natural language query parsing.

    Implementations use LLMs (NVIDIA NIM) to understand user intent
    and convert to IMS-compatible search queries.
    """

    @abstractmethod
    async def parse_query(
        self,
        natural_language_query: str,
        language: str = "en"
    ) -> SearchIntent:
        """
        Parse natural language query into structured search intent.

        Args:
            natural_language_query: User's search query in natural language
            language: Query language (en, ko, ja)

        Returns:
            SearchIntent value object with parsed filters and intent

        Example:
            Input: "Show me critical bugs assigned to John from last week"
            Output: SearchIntent(
                intent_type=COMPLEX_QUERY,
                priority_filters=["critical"],
                issue_type_filters=["bug"],
                assignee_filters=["John"],
                date_from="2024-01-01",
                ...
            )

        Raises:
            ParserError: If parsing fails
        """
        pass

    @abstractmethod
    async def convert_to_ims_syntax(self, intent: SearchIntent) -> str:
        """
        Convert SearchIntent to IMS native search syntax.

        Args:
            intent: Parsed search intent

        Returns:
            IMS-compatible search query string

        Example:
            Input: SearchIntent(priority_filters=["critical"], status_filters=["open"])
            Output: "priority=critical AND status=open"

        Raises:
            ParserError: If conversion fails
        """
        pass

    @abstractmethod
    async def extract_keywords(self, text: str) -> list[str]:
        """
        Extract key terms from text for search optimization.

        Args:
            text: Input text (issue title, description, etc.)

        Returns:
            List of extracted keywords

        Raises:
            ParserError: If extraction fails
        """
        pass
