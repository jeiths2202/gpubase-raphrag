"""
Answer Composer

Composes the final user-facing response from verified multi-agent results.
Strips all internal reasoning and chain-of-thought.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from .types import (
    ComposedAnswer, VerificationResult, ExecutionPlan
)

logger = logging.getLogger(__name__)


class AnswerComposer(BaseAgent):
    """
    Composes final answers from verified agent results.

    Responsibilities:
    - Strip all internal reasoning (Chain-of-Thought)
    - Format sources with citations
    - Apply user language preference
    - Generate next action suggestions
    """

    def __init__(
        self,
        llm_adapter=None,
        name: str = "AnswerComposer",
        description: str = "Composes final user-facing answers from verified results"
    ):
        """
        Initialize the Answer Composer.

        Args:
            llm_adapter: LLM adapter for composition
            name: Agent name
            description: Agent description
        """
        super().__init__(
            name=name,
            agent_type=AgentType.PLANNER,
            description=description,
            tools=[],
        )
        self._llm_adapter = llm_adapter
        self._system_prompt = self._load_composer_prompt()

    @property
    def llm_adapter(self):
        """Lazy load LLM adapter"""
        if self._llm_adapter is None:
            from ..registry import get_llm_adapter
            self._llm_adapter = get_llm_adapter()
        return self._llm_adapter

    def _load_composer_prompt(self) -> str:
        """Load the composer system prompt"""
        prompt_file = Path(__file__).parent / "prompts" / "composer.txt"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Fallback prompt if file not found"""
        return """You are an Answer Composer. Create clear, user-facing responses.
NEVER expose internal reasoning or chain-of-thought.
Always cite sources. Match user's language."""

    async def compose(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult],
        verification: VerificationResult,
        context: Optional[AgentContext] = None
    ) -> ComposedAnswer:
        """
        Compose the final answer from verified results.

        Args:
            plan: The execution plan used
            task_results: Results from each task (task_id -> AgentResult)
            verification: Verification result
            context: Agent context with preferences

        Returns:
            ComposedAnswer ready for user
        """
        # Collect and deduplicate sources
        all_sources = self._collect_sources(task_results)

        # Determine target language
        language = self._determine_language(plan, context)

        # Build composition prompt
        composition_prompt = self._build_composition_prompt(
            plan, task_results, verification, language
        )

        try:
            # Use LLM for composition
            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": composition_prompt}
            ]

            response = await self.llm_adapter.generate(messages)
            composed_json = self._parse_composition_response(response.get("content", ""))

            # Build ComposedAnswer
            answer = ComposedAnswer(
                content=self._clean_content(composed_json.get("content", "")),
                language=composed_json.get("language", language),
                sources=self._format_sources(
                    composed_json.get("sources", []),
                    all_sources
                ),
                confidence=verification.overall_score,
                next_actions=composed_json.get("next_actions", [])
            )

            logger.info(
                f"[AnswerComposer] Composed answer: {len(answer.content)} chars, "
                f"{len(answer.sources)} sources, {len(answer.next_actions)} actions"
            )

            return answer

        except Exception as e:
            logger.error(f"[AnswerComposer] Composition failed: {e}")
            # Fall back to simple aggregation
            return self._fallback_composition(task_results, all_sources, language)

    def _collect_sources(
        self,
        task_results: Dict[str, AgentResult]
    ) -> List[Dict[str, Any]]:
        """Collect and deduplicate sources from all results"""
        all_sources = []
        seen_refs = set()

        for task_id, result in task_results.items():
            for source in result.sources:
                # Create unique reference key
                ref = source.get("reference") or source.get("doc_id") or source.get("title", "")
                if ref and ref not in seen_refs:
                    seen_refs.add(ref)
                    all_sources.append({
                        **source,
                        "from_task": task_id
                    })

        return all_sources

    def _determine_language(
        self,
        plan: ExecutionPlan,
        context: Optional[AgentContext]
    ) -> str:
        """Determine target language for the answer"""
        # Check context first
        if context and context.language != "auto":
            return context.language

        # Detect from original task
        task = plan.original_task
        if self._is_korean(task):
            return "ko"
        elif self._is_japanese(task):
            return "ja"

        return "en"

    def _is_korean(self, text: str) -> bool:
        """Check if text contains Korean characters"""
        return bool(re.search(r'[\uAC00-\uD7AF]', text))

    def _is_japanese(self, text: str) -> bool:
        """Check if text contains Japanese characters"""
        return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text))

    def _build_composition_prompt(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult],
        verification: VerificationResult,
        language: str
    ) -> str:
        """Build the prompt for LLM composition"""
        parts = [
            f"## Original Request\n{plan.original_task}",
            f"\n## Target Language: {language}",
            "\n## Agent Results"
        ]

        # Add each result
        for task in plan.decomposed_tasks:
            result = task_results.get(task.task_id)
            if result and result.success:
                # Truncate long answers for prompt
                answer_preview = result.answer[:2000] if result.answer else ""
                parts.append(f"\n### {task.description}")
                parts.append(f"Agent: {result.agent_type.value}")
                parts.append(f"Answer:\n{answer_preview}")

                if result.sources:
                    source_list = ", ".join(
                        s.get("title", s.get("doc_name", "Unknown"))[:50]
                        for s in result.sources[:5]
                    )
                    parts.append(f"Sources: {source_list}")

        # Add verification summary
        parts.append(f"\n## Quality Score: {verification.overall_score:.0%}")

        parts.append("""
## Instructions
Compose a clear, coherent answer that:
1. Directly addresses the original request
2. Cites sources naturally
3. Uses the target language
4. NEVER exposes internal reasoning
5. Suggests 2-4 relevant next actions

Return JSON with: content, language, sources, next_actions
""")

        return "\n".join(parts)

    def _parse_composition_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM composition response"""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        # Try to find JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # If no valid JSON, treat as plain text response
        return {
            "content": content,
            "language": "auto",
            "sources": [],
            "next_actions": []
        }

    def _clean_content(self, content: str) -> str:
        """Clean the composed content, removing any internal reasoning"""
        if not content:
            return content

        # Remove think tags
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)

        # Remove internal reasoning patterns
        patterns = [
            r"Based on (?:my|the) analysis.*?\.",
            r"The (?:RAG|IMS|Code|Vision) agent.*?\.",
            r"According to (?:my|the) reasoning.*?\.",
            r"Let me (?:check|analyze|look).*?\.",
            r"I (?:see|found|notice) that.*?\.",
            r"With confidence score.*?\.",
        ]

        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)

        # Clean up whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def _format_sources(
        self,
        llm_sources: List[Dict[str, Any]],
        all_sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format and merge sources"""
        formatted = []

        # Use LLM-suggested sources if available
        if llm_sources:
            for src in llm_sources:
                formatted.append({
                    "title": src.get("title", "Unknown"),
                    "type": src.get("type", "document"),
                    "reference": src.get("reference", ""),
                    "url": src.get("url")
                })
        # Otherwise use collected sources
        elif all_sources:
            for src in all_sources[:10]:  # Limit to 10
                formatted.append({
                    "title": src.get("title") or src.get("doc_name", "Unknown"),
                    "type": src.get("type", "document"),
                    "reference": src.get("reference") or src.get("doc_id", ""),
                    "url": src.get("url")
                })

        return formatted

    def _fallback_composition(
        self,
        task_results: Dict[str, AgentResult],
        all_sources: List[Dict[str, Any]],
        language: str
    ) -> ComposedAnswer:
        """Simple fallback composition without LLM"""
        # Concatenate successful results
        content_parts = []
        for task_id, result in task_results.items():
            if result.success and result.answer:
                # Clean and add
                cleaned = self._clean_content(result.answer)
                if cleaned:
                    content_parts.append(cleaned)

        content = "\n\n".join(content_parts) if content_parts else "결과를 찾을 수 없습니다."

        return ComposedAnswer(
            content=content,
            language=language,
            sources=self._format_sources([], all_sources),
            confidence=0.6,
            next_actions=[]
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute is not the primary interface - use compose() instead"""
        return AgentResult(
            answer="Answer Composer should be called via compose() method",
            agent_type=AgentType.PLANNER,
            steps=0,
            execution_time=0.0,
            success=False,
            error="Use compose() method instead of execute()"
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream is not the primary interface"""
        yield AgentStreamChunk(
            chunk_type="error",
            content="Answer Composer should be called via compose() method"
        )


# Singleton instance
_answer_composer: Optional[AnswerComposer] = None


def get_answer_composer(llm_adapter=None) -> AnswerComposer:
    """Get or create the Answer Composer instance"""
    global _answer_composer
    if _answer_composer is None:
        _answer_composer = AnswerComposer(llm_adapter=llm_adapter)
    elif llm_adapter and _answer_composer._llm_adapter is None:
        _answer_composer._llm_adapter = llm_adapter
    return _answer_composer
