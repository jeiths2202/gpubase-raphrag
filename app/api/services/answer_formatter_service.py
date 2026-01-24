"""
Answer Formatter Service for Read-Only Formatting

This service formats structured answers to improve readability
WITHOUT adding new content. It ensures:
- READ-ONLY: No new facts or information added
- REORDERING: Blocks can be reordered for better flow
- TRANSITIONS: Predefined transition phrases can be added
- GUARDRAILS: Input block count == Output block count

핵심 원칙:
1. 새로운 내용 추가 절대 금지
2. 블록 순서 최적화만 허용
3. 사전 정의된 연결어만 허용
"""
import logging
from typing import List, Dict, Any, Optional
from functools import lru_cache

from ..agents.types import (
    BlockType,
    AnswerBlock,
    StructuredAnswer,
)

logger = logging.getLogger(__name__)


class AnswerFormatterService:
    """
    Read-only formatter for structured answers.

    Allowed Operations:
    - Reorder blocks for better flow
    - Add predefined transition phrases between blocks
    - Adjust heading levels for consistency

    Forbidden Operations:
    - Add new facts or information
    - Modify original content text
    - Remove source citations
    """

    # Predefined transition phrases by language
    TRANSITION_PHRASES = {
        "ko": {
            "addition": "또한,",
            "contrast": "반면에,",
            "conclusion": "결론적으로,",
            "example": "예를 들어,",
            "result": "따라서,",
        },
        "en": {
            "addition": "Additionally,",
            "contrast": "However,",
            "conclusion": "In conclusion,",
            "example": "For example,",
            "result": "Therefore,",
        },
        "ja": {
            "addition": "また、",
            "contrast": "一方で、",
            "conclusion": "結論として、",
            "example": "例えば、",
            "result": "従って、",
        },
    }

    # Block type ordering priority (lower = earlier)
    BLOCK_ORDER_PRIORITY = {
        BlockType.HEADING: 1,
        BlockType.TEXT: 2,
        BlockType.LIST: 3,
        BlockType.CODE: 4,
        BlockType.TABLE: 5,
        BlockType.QUOTE: 6,
        BlockType.IMAGE: 7,
        BlockType.SOURCE_CITATION: 10,  # Always last
        BlockType.NO_ANSWER: 0,  # Always first if present
    }

    def __init__(self):
        """Initialize the Answer Formatter Service"""
        pass

    async def format(
        self,
        answer: StructuredAnswer,
        style: str = "default",
        add_transitions: bool = False
    ) -> StructuredAnswer:
        """
        Format a structured answer for better readability.

        Args:
            answer: Original StructuredAnswer
            style: Formatting style (default, compact, detailed)
            add_transitions: Whether to add transition phrases

        Returns:
            Formatted StructuredAnswer
        """
        # Validate input
        if not answer.blocks:
            return answer

        original_block_count = len(answer.blocks)

        # Step 1: Separate citation blocks from content blocks
        content_blocks = []
        citation_blocks = []

        for block in answer.blocks:
            if block.type == BlockType.SOURCE_CITATION:
                citation_blocks.append(block)
            else:
                content_blocks.append(block)

        # Step 2: Optimize content block order
        if style == "default":
            content_blocks = self._optimize_block_order(content_blocks)

        # Step 3: Add transitions (optional)
        if add_transitions and answer.language:
            content_blocks = self._add_transitions(
                content_blocks,
                answer.language
            )

        # Step 4: Adjust heading levels for consistency
        content_blocks = self._normalize_headings(content_blocks)

        # Step 5: Recombine blocks (content first, then citations)
        formatted_blocks = content_blocks + citation_blocks

        # Guardrail: Validate block count
        # Note: Transitions may add text to existing blocks, not new blocks
        self._validate_no_new_content(
            original_blocks=answer.blocks,
            formatted_blocks=formatted_blocks,
            original_count=original_block_count
        )

        return StructuredAnswer(
            blocks=formatted_blocks,
            confidence=answer.confidence,
            language=answer.language,
            metadata={
                **(answer.metadata or {}),
                "formatted": True,
                "style": style,
            }
        )

    def _optimize_block_order(
        self,
        blocks: List[AnswerBlock]
    ) -> List[AnswerBlock]:
        """
        Optimize block order for better reading flow.

        Strategy:
        - Group related blocks (heading + content)
        - Keep logical sequence
        - Move code blocks after explanatory text
        """
        if len(blocks) <= 1:
            return blocks

        # Group blocks by section (heading + following content)
        sections: List[List[AnswerBlock]] = []
        current_section: List[AnswerBlock] = []

        for block in blocks:
            if block.type == BlockType.HEADING and current_section:
                sections.append(current_section)
                current_section = [block]
            else:
                current_section.append(block)

        if current_section:
            sections.append(current_section)

        # Flatten sections back to blocks
        optimized = []
        for section in sections:
            optimized.extend(section)

        return optimized

    def _add_transitions(
        self,
        blocks: List[AnswerBlock],
        language: str
    ) -> List[AnswerBlock]:
        """
        Add transition phrases between blocks.

        Only modifies TEXT blocks by prepending transition phrases.
        Does not add new blocks.
        """
        if len(blocks) <= 1:
            return blocks

        lang_key = language if language in self.TRANSITION_PHRASES else "ko"
        phrases = self.TRANSITION_PHRASES[lang_key]

        result = []
        prev_block_type = None

        for i, block in enumerate(blocks):
            # Only add transitions to TEXT blocks that follow other content
            if (
                block.type == BlockType.TEXT and
                i > 0 and
                prev_block_type in [BlockType.TEXT, BlockType.LIST, BlockType.CODE]
            ):
                # Clone block with transition phrase
                new_content = f"{phrases['addition']} {block.content}"
                result.append(AnswerBlock(
                    type=block.type,
                    content=new_content,
                    # Copy other fields
                    items=block.items,
                    ordered=block.ordered,
                    language=block.language,
                    headers=block.headers,
                    rows=block.rows,
                    level=block.level,
                    url=block.url,
                    caption=block.caption,
                    doc_name=block.doc_name,
                    page=block.page,
                    chunk_id=block.chunk_id,
                    score=block.score,
                ))
            else:
                result.append(block)

            prev_block_type = block.type

        return result

    def _normalize_headings(
        self,
        blocks: List[AnswerBlock]
    ) -> List[AnswerBlock]:
        """
        Normalize heading levels for consistency.

        Ensures:
        - First heading is level 2
        - Subsequent headings don't skip levels
        """
        result = []
        min_level = 4
        heading_found = False

        # Find minimum heading level
        for block in blocks:
            if block.type == BlockType.HEADING:
                level = block.level or 2
                min_level = min(min_level, level)
                heading_found = True

        if not heading_found:
            return blocks

        # Normalize levels (shift to start at 2)
        level_shift = 2 - min_level

        for block in blocks:
            if block.type == BlockType.HEADING:
                current_level = block.level or 2
                new_level = max(1, min(4, current_level + level_shift))

                result.append(AnswerBlock(
                    type=BlockType.HEADING,
                    content=block.content,
                    level=new_level,
                ))
            else:
                result.append(block)

        return result

    def _validate_no_new_content(
        self,
        original_blocks: List[AnswerBlock],
        formatted_blocks: List[AnswerBlock],
        original_count: int
    ) -> None:
        """
        Validate that no new content blocks were added.

        Raises ValueError if content was added.
        """
        # Count non-citation blocks
        original_content_count = sum(
            1 for b in original_blocks
            if b.type != BlockType.SOURCE_CITATION
        )
        formatted_content_count = sum(
            1 for b in formatted_blocks
            if b.type != BlockType.SOURCE_CITATION
        )

        if formatted_content_count > original_content_count:
            logger.error(
                f"[AnswerFormatter] Guardrail violation: "
                f"Content blocks increased from {original_content_count} to {formatted_content_count}"
            )
            raise ValueError(
                "Formatter added new content blocks, which is forbidden"
            )

    def format_for_display(
        self,
        answer: StructuredAnswer,
        max_content_length: int = 2000
    ) -> StructuredAnswer:
        """
        Format answer for UI display with length constraints.

        Args:
            answer: Structured answer to format
            max_content_length: Maximum total content length

        Returns:
            Display-formatted answer
        """
        if not answer.blocks:
            return answer

        total_length = 0
        truncated_blocks = []

        for block in answer.blocks:
            # Citation blocks are always included
            if block.type == BlockType.SOURCE_CITATION:
                truncated_blocks.append(block)
                continue

            # Calculate block content length
            content_len = len(block.content or "")
            if block.items:
                content_len += sum(len(item) for item in block.items)

            # Check if we have room
            if total_length + content_len <= max_content_length:
                truncated_blocks.append(block)
                total_length += content_len
            else:
                # Truncate this block if needed
                remaining = max_content_length - total_length
                if remaining > 100 and block.content:
                    truncated_content = block.content[:remaining-3] + "..."
                    truncated_blocks.append(AnswerBlock(
                        type=block.type,
                        content=truncated_content,
                        level=block.level,
                        language=block.language,
                    ))
                break

        return StructuredAnswer(
            blocks=truncated_blocks,
            confidence=answer.confidence,
            language=answer.language,
            metadata={
                **(answer.metadata or {}),
                "truncated": total_length > max_content_length,
            }
        )


# Singleton instance
_answer_formatter_instance: Optional[AnswerFormatterService] = None


@lru_cache()
def get_answer_formatter_service() -> AnswerFormatterService:
    """Get cached Answer Formatter Service instance"""
    global _answer_formatter_instance
    if _answer_formatter_instance is None:
        _answer_formatter_instance = AnswerFormatterService()
    return _answer_formatter_instance
