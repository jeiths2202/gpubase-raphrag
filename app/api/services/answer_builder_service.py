"""
Answer Builder Service for ChatGPT-style Structured Output

This service builds structured answers from RAG search results using
rule-based extraction. It ensures:
- Retrieval = Truth: Only use content from search results
- LLM = Formatter Only: No free generation, only structuring
- Hallucination = Structurally Prevented: Blocks are extracted, not generated

핵심 원칙:
1. 검색 결과에서 직접 추출만 허용
2. LLM은 포맷팅 전용 (선택적)
3. 구조적으로 할루시네이션 차단

Enhanced with RAG Accuracy Pipeline:
- Faithfulness checking (ISSUP-style)
- Relevance grading integration
- Partial match handling

Created as part of PDCA: rag-accuracy-improvement
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache

from ..agents.types import (
    BlockType,
    AnswerBlock,
    StructuredAnswer,
)
from ..core.config import api_settings
from ..models.rag_accuracy import SupportLevel, QueryAnalysis
from ..services.faithfulness_checker_service import get_faithfulness_checker_service
from ..services.partial_match_handler import get_partial_match_handler

logger = logging.getLogger(__name__)


class AnswerBuilderService:
    """
    Rule-based Answer Builder that extracts structured answers from search results.

    Key Design:
    - Extractive QA: Only extract from source documents
    - No LLM Free Generation: Content comes from search results
    - Intent-based Structuring: Different intents get different block structures

    Enhanced with RAG Accuracy:
    - Faithfulness checking before answer generation
    - Partial match handling for low-confidence results
    - Support level classification (FULLY_SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED)
    """

    # Minimum confidence threshold for including sources
    # Note: RRF scores typically range 0.01-0.05, not 0.0-1.0
    MIN_CONFIDENCE = 0.01

    # Maximum sources to include in citations
    MAX_CITATIONS = 5

    # Faithfulness threshold for answer acceptance
    FAITHFULNESS_THRESHOLD = 0.5

    # Intent patterns for classification
    INTENT_PATTERNS = {
        "definition": [
            r"(?:무엇|뭐|what|what's)\s*(?:인가요|입니까|인지|야|is|are)",
            r"(?:정의|definition|define|설명|explain)",
            r"이란\??$",
            r"とは\??$",
        ],
        "troubleshooting": [
            r"(?:에러|오류|error|exception|failed|실패)",
            r"(?:해결|fix|resolve|solution|solve)",
            r"(?:문제|problem|issue|bug)",
            r"(?:안됨|안되|doesn't work|not working)",
        ],
        "howto": [
            r"(?:어떻게|how|how to|방법)",
            r"(?:하는 방법|하려면|하려고)",
            r"(?:설정|configure|setup|install)",
            r"(?:사용법|usage|guide)",
        ],
        "comparison": [
            r"(?:차이|difference|compare|vs|versus)",
            r"(?:비교|비해|보다)",
        ],
        "list": [
            r"(?:종류|types|list|나열)",
            r"(?:모든|all|every)",
            r"(?:목록|리스트)",
        ],
    }

    def __init__(self):
        """Initialize the Answer Builder Service"""
        self.min_confidence = getattr(
            api_settings,
            'STRUCTURED_ANSWER_MIN_CONFIDENCE',
            self.MIN_CONFIDENCE
        )
        self.faithfulness_checker = get_faithfulness_checker_service()
        self.partial_match_handler = get_partial_match_handler()

    def classify_intent(self, query: str) -> str:
        """
        Classify query intent for block structure determination.

        Args:
            query: User query string

        Returns:
            Intent type: definition, troubleshooting, howto, comparison, list, general
        """
        query_lower = query.lower()

        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    return intent

        return "general"

    async def build_answer(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        intent: Optional[str] = None,
        language: str = "auto",
        multi_product_results: Optional[List[Dict[str, Any]]] = None,
        query_analysis: Optional[QueryAnalysis] = None,
        check_faithfulness: bool = True
    ) -> StructuredAnswer:
        """
        Build a structured answer from search results.

        Args:
            query: User's original query
            search_results: List of search result dictionaries
            intent: Query intent (auto-classified if not provided)
            language: Response language
            multi_product_results: Optional multi-product aggregated results for platform comparison
            query_analysis: Optional QueryAnalysis from RAG accuracy pipeline
            check_faithfulness: Whether to perform faithfulness checking

        Returns:
            StructuredAnswer with content blocks
        """
        # Classify intent if not provided
        if not intent:
            intent = self.classify_intent(query)

        logger.info(f"[AnswerBuilder] Building answer for intent: {intent}")

        # Filter by confidence
        relevant = [
            r for r in search_results
            if self._get_score(r) >= self.min_confidence
        ]

        # No relevant results found
        if not relevant and not multi_product_results:
            # Use partial match handler if query_analysis is available
            if query_analysis:
                partial_response = self.partial_match_handler.build_partial_response(
                    query_analysis=query_analysis,
                    graded_results=[],
                    support_level=SupportLevel.NOT_SUPPORTED,
                )
                return StructuredAnswer(
                    blocks=[
                        AnswerBlock(
                            type=BlockType.NO_ANSWER,
                            content=partial_response
                        )
                    ],
                    confidence=0.0,
                    language=language,
                    metadata={
                        "intent": intent,
                        "support_level": SupportLevel.NOT_SUPPORTED.value,
                        "faithfulness_checked": False,
                    }
                )
            return self._no_answer_response(query, language)

        # Build blocks based on intent
        blocks: List[AnswerBlock] = []

        # Add product_version blocks if multi-product results are available
        if multi_product_results:
            product_blocks = self._build_product_version_blocks(multi_product_results)
            blocks.extend(product_blocks)
            logger.info(f"[AnswerBuilder] Added {len(product_blocks)} product_version blocks")

        if intent == "definition":
            blocks.extend(self._build_definition_blocks(query, relevant, language))
        elif intent == "troubleshooting":
            blocks.extend(self._build_troubleshooting_blocks(query, relevant, language))
        elif intent == "howto":
            blocks.extend(self._build_howto_blocks(query, relevant, language))
        elif intent == "comparison":
            blocks.extend(self._build_comparison_blocks(query, relevant, language))
        elif intent == "list":
            blocks.extend(self._build_list_blocks(query, relevant, language))
        else:
            # Only add general blocks if no product version blocks were added
            if not multi_product_results:
                blocks.extend(self._build_general_blocks(query, relevant, language))

        # Add source citations
        citation_blocks = self._build_citation_blocks(relevant[:self.MAX_CITATIONS])
        blocks.extend(citation_blocks)

        # Calculate overall confidence
        confidence = self._calculate_confidence(relevant) if relevant else 0.8

        # Faithfulness checking (if enabled and context available)
        support_level = SupportLevel.FULLY_SUPPORTED
        faithfulness_confidence = 1.0

        if check_faithfulness and relevant:
            # Build context from search results
            context = "\n\n".join([
                self._get_content(r) for r in relevant[:5]
            ])

            # Build answer text from blocks for checking
            answer_text = self._blocks_to_text(blocks)

            if answer_text and context:
                faithfulness_result = self.faithfulness_checker.check_faithfulness(
                    answer=answer_text,
                    context=context
                )
                support_level = faithfulness_result.support_level
                faithfulness_confidence = faithfulness_result.confidence

                logger.info(
                    f"[AnswerBuilder] Faithfulness check: "
                    f"support_level={support_level.value}, "
                    f"confidence={faithfulness_confidence:.2f}"
                )

                # Add warning block if partially supported
                if support_level == SupportLevel.PARTIALLY_SUPPORTED:
                    blocks.insert(0, AnswerBlock(
                        type=BlockType.WARNING,
                        content=self._get_partial_support_warning(language)
                    ))

        return StructuredAnswer(
            blocks=blocks,
            confidence=confidence * faithfulness_confidence,
            language=language,
            metadata={
                "intent": intent,
                "source_count": len(relevant),
                "total_results": len(search_results),
                "multi_product": bool(multi_product_results),
                "support_level": support_level.value,
                "faithfulness_confidence": faithfulness_confidence,
            }
        )

    def _get_score(self, result: Dict[str, Any]) -> float:
        """Extract score from a search result safely"""
        score = result.get("score") or result.get("similarity") or 0.0
        try:
            return float(score)
        except (ValueError, TypeError):
            return 0.0

    def _get_content(self, result: Dict[str, Any]) -> str:
        """Extract content from a search result"""
        return result.get("content") or result.get("text") or ""

    def _get_doc_name(self, result: Dict[str, Any]) -> str:
        """Extract document name from a search result"""
        return (
            result.get("doc_name") or
            result.get("document_name") or
            result.get("source") or
            result.get("doc_id") or
            "Unknown"
        )

    def _extract_sentences(self, text: str, max_sentences: int = 3) -> str:
        """Extract first N sentences from text"""
        # Split by sentence-ending punctuation
        sentences = re.split(r'(?<=[.!?。])\s+', text.strip())
        return " ".join(sentences[:max_sentences])

    def _extract_code_blocks(self, text: str) -> List[Tuple[str, str]]:
        """Extract code blocks from text content"""
        code_blocks = []

        # Markdown code blocks
        pattern = r'```(\w*)\n?(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        for lang, code in matches:
            code_blocks.append((lang or "text", code.strip()))

        # Inline code patterns (config files, commands)
        inline_pattern = r'`([^`]+)`'
        inline_matches = re.findall(inline_pattern, text)
        for code in inline_matches:
            if len(code) > 20:  # Only include longer snippets
                code_blocks.append(("", code.strip()))

        return code_blocks

    def _extract_list_items(self, text: str) -> List[str]:
        """Extract list items from text content"""
        items = []

        # Numbered lists (1. 2. 3. or 1) 2) 3))
        numbered = re.findall(r'(?:^|\n)\s*(?:\d+[.)]\s+)(.+?)(?=\n|$)', text)
        items.extend(numbered)

        # Bullet lists (- * •)
        bullets = re.findall(r'(?:^|\n)\s*[-*•]\s+(.+?)(?=\n|$)', text)
        items.extend(bullets)

        return items

    def _no_answer_response(self, query: str, language: str) -> StructuredAnswer:
        """Generate a no-answer response"""
        messages = {
            "ko": f"'{query}'에 대한 관련 정보를 찾지 못했습니다. 다른 키워드로 검색해 보세요.",
            "ja": f"'{query}'に関する情報が見つかりませんでした。別のキーワードで検索してみてください。",
            "en": f"No relevant information found for '{query}'. Try searching with different keywords.",
        }

        lang_key = language if language in messages else "ko"

        return StructuredAnswer(
            blocks=[
                AnswerBlock(
                    type=BlockType.NO_ANSWER,
                    content=messages[lang_key]
                )
            ],
            confidence=0.0,
            language=language,
            metadata={"intent": "no_answer"}
        )

    def _build_product_version_blocks(
        self,
        multi_product_results: List[Dict[str, Any]]
    ) -> List[AnswerBlock]:
        """
        Build product_version blocks from multi-product aggregated results.

        Args:
            multi_product_results: List of multi-product result dictionaries
                Each item has: name, doc_type, variants, has_differences, available_platforms

        Returns:
            List of AnswerBlock with type='product_version'
        """
        blocks = []

        for mpr in multi_product_results:
            name = mpr.get("name", "Unknown")
            doc_type = mpr.get("doc_type", "commands")
            variants = mpr.get("variants", [])
            has_differences = mpr.get("has_differences", False)
            available_platforms = mpr.get("available_platforms", [])

            if not variants:
                continue

            # Create a product_version block
            block = AnswerBlock(
                type=BlockType.PRODUCT_VERSION,
                name=name,
                doc_type=doc_type,
                variants=variants,
                has_differences=has_differences,
                available_platforms=available_platforms
            )
            blocks.append(block)
            logger.debug(f"[AnswerBuilder] Created product_version block for '{name}' with {len(variants)} variants")

        return blocks

    def _build_definition_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for definition-type queries"""
        blocks = []

        # Extract main definition from top result
        if results:
            top_content = self._get_content(results[0])
            definition = self._extract_sentences(top_content, max_sentences=2)

            if definition:
                blocks.append(AnswerBlock(
                    type=BlockType.TEXT,
                    content=definition
                ))

        # Add additional context from other results
        additional_info = []
        for result in results[1:3]:
            content = self._get_content(result)
            snippet = self._extract_sentences(content, max_sentences=1)
            if snippet and snippet not in additional_info:
                additional_info.append(snippet)

        if additional_info:
            blocks.append(AnswerBlock(
                type=BlockType.HEADING,
                content="추가 정보" if language in ["ko", "auto"] else "Additional Information",
                level=3
            ))
            for info in additional_info:
                blocks.append(AnswerBlock(
                    type=BlockType.TEXT,
                    content=info
                ))

        return blocks

    def _build_troubleshooting_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for troubleshooting-type queries"""
        blocks = []

        # Error/Problem heading
        blocks.append(AnswerBlock(
            type=BlockType.HEADING,
            content="문제 분석" if language in ["ko", "auto"] else "Problem Analysis",
            level=2
        ))

        # Extract problem description from top result
        if results:
            top_content = self._get_content(results[0])
            problem_desc = self._extract_sentences(top_content, max_sentences=2)
            if problem_desc:
                blocks.append(AnswerBlock(
                    type=BlockType.TEXT,
                    content=problem_desc
                ))

        # Look for solution steps
        solution_steps = []
        code_examples = []

        for result in results:
            content = self._get_content(result)

            # Extract list items (potential solution steps)
            items = self._extract_list_items(content)
            for item in items:
                if item not in solution_steps:
                    solution_steps.append(item)

            # Extract code blocks
            codes = self._extract_code_blocks(content)
            code_examples.extend(codes)

        # Add solution steps
        if solution_steps:
            blocks.append(AnswerBlock(
                type=BlockType.HEADING,
                content="해결 방법" if language in ["ko", "auto"] else "Solution",
                level=3
            ))
            blocks.append(AnswerBlock(
                type=BlockType.LIST,
                items=solution_steps[:5],  # Limit to 5 steps
                ordered=True
            ))

        # Add code examples
        if code_examples:
            blocks.append(AnswerBlock(
                type=BlockType.HEADING,
                content="코드 예제" if language in ["ko", "auto"] else "Code Example",
                level=3
            ))
            for lang, code in code_examples[:2]:  # Limit to 2 code blocks
                blocks.append(AnswerBlock(
                    type=BlockType.CODE,
                    content=code,
                    language=lang
                ))

        return blocks

    def _build_howto_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for how-to type queries"""
        blocks = []

        # Introduction
        if results:
            intro = self._extract_sentences(self._get_content(results[0]), max_sentences=1)
            if intro:
                blocks.append(AnswerBlock(
                    type=BlockType.TEXT,
                    content=intro
                ))

        # Extract steps from all results
        all_steps = []
        code_examples = []

        for result in results:
            content = self._get_content(result)
            steps = self._extract_list_items(content)
            all_steps.extend([s for s in steps if s not in all_steps])

            codes = self._extract_code_blocks(content)
            code_examples.extend(codes)

        # Add steps
        if all_steps:
            blocks.append(AnswerBlock(
                type=BlockType.HEADING,
                content="단계별 가이드" if language in ["ko", "auto"] else "Step-by-Step Guide",
                level=2
            ))
            blocks.append(AnswerBlock(
                type=BlockType.LIST,
                items=all_steps[:7],
                ordered=True
            ))

        # Add code examples
        if code_examples:
            for lang, code in code_examples[:2]:
                blocks.append(AnswerBlock(
                    type=BlockType.CODE,
                    content=code,
                    language=lang
                ))

        return blocks

    def _build_comparison_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for comparison-type queries"""
        blocks = []

        # Introduction
        blocks.append(AnswerBlock(
            type=BlockType.HEADING,
            content="비교 분석" if language in ["ko", "auto"] else "Comparison Analysis",
            level=2
        ))

        # Extract comparison points
        comparison_points = []
        for result in results[:3]:
            content = self._get_content(result)
            snippet = self._extract_sentences(content, max_sentences=2)
            if snippet:
                comparison_points.append(snippet)

        # Add as text blocks (could be enhanced to table format)
        for point in comparison_points:
            blocks.append(AnswerBlock(
                type=BlockType.TEXT,
                content=point
            ))

        return blocks

    def _build_list_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for list-type queries"""
        blocks = []

        # Collect all list items
        all_items = []
        for result in results:
            content = self._get_content(result)
            items = self._extract_list_items(content)
            all_items.extend([i for i in items if i not in all_items])

        if all_items:
            blocks.append(AnswerBlock(
                type=BlockType.LIST,
                items=all_items[:10],  # Limit to 10 items
                ordered=False
            ))
        else:
            # Fallback to text extraction
            for result in results[:3]:
                content = self._get_content(result)
                snippet = self._extract_sentences(content, max_sentences=2)
                if snippet:
                    blocks.append(AnswerBlock(
                        type=BlockType.TEXT,
                        content=snippet
                    ))

        return blocks

    def _build_general_blocks(
        self,
        query: str,
        results: List[Dict],
        language: str
    ) -> List[AnswerBlock]:
        """Build blocks for general queries"""
        blocks = []

        # Extract main content from top results
        for i, result in enumerate(results[:3]):
            content = self._get_content(result)

            if i == 0:
                # Main answer from top result
                main_text = self._extract_sentences(content, max_sentences=3)
                if main_text:
                    blocks.append(AnswerBlock(
                        type=BlockType.TEXT,
                        content=main_text
                    ))
            else:
                # Additional context
                additional = self._extract_sentences(content, max_sentences=2)
                if additional:
                    blocks.append(AnswerBlock(
                        type=BlockType.TEXT,
                        content=additional
                    ))

        # Check for code blocks in results
        for result in results[:3]:
            content = self._get_content(result)
            codes = self._extract_code_blocks(content)
            for lang, code in codes[:1]:
                blocks.append(AnswerBlock(
                    type=BlockType.CODE,
                    content=code,
                    language=lang
                ))

        return blocks

    def _build_citation_blocks(
        self,
        results: List[Dict]
    ) -> List[AnswerBlock]:
        """Build source citation blocks from search results"""
        citations = []

        for result in results:
            citations.append(AnswerBlock(
                type=BlockType.SOURCE_CITATION,
                doc_name=self._get_doc_name(result),
                page=result.get("page_number"),
                chunk_id=result.get("chunk_id"),
                score=self._get_score(result)
            ))

        return citations

    def _calculate_confidence(self, results: List[Dict]) -> float:
        """Calculate overall answer confidence from search results"""
        if not results:
            return 0.0

        # Average of top 3 scores, weighted by position
        weights = [0.5, 0.3, 0.2]
        total_weight = 0.0
        weighted_sum = 0.0

        for i, result in enumerate(results[:3]):
            weight = weights[i] if i < len(weights) else 0.1
            score = self._get_score(result)
            weighted_sum += score * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _blocks_to_text(self, blocks: List[AnswerBlock]) -> str:
        """Convert answer blocks to plain text for faithfulness checking"""
        text_parts = []
        for block in blocks:
            if block.type == BlockType.TEXT:
                text_parts.append(block.content or "")
            elif block.type == BlockType.LIST:
                if block.items:
                    text_parts.append("\n".join(block.items))
            elif block.type == BlockType.CODE:
                text_parts.append(block.content or "")
            elif block.type == BlockType.HEADING:
                text_parts.append(block.content or "")
        return "\n".join(text_parts)

    def _get_partial_support_warning(self, language: str) -> str:
        """Get warning message for partially supported answers"""
        warnings = {
            "ko": "⚠️ 이 답변은 검색 결과에서 부분적으로만 지원됩니다. 추가 확인이 필요할 수 있습니다.",
            "ja": "⚠️ この回答は検索結果によって部分的にのみサポートされています。追加の確認が必要な場合があります。",
            "en": "⚠️ This answer is only partially supported by the search results. Additional verification may be needed.",
        }
        lang_key = language if language in warnings else "ko"
        return warnings[lang_key]


# Singleton instance
_answer_builder_instance: Optional[AnswerBuilderService] = None


@lru_cache()
def get_answer_builder_service() -> AnswerBuilderService:
    """Get cached Answer Builder Service instance"""
    global _answer_builder_instance
    if _answer_builder_instance is None:
        _answer_builder_instance = AnswerBuilderService()
    return _answer_builder_instance
