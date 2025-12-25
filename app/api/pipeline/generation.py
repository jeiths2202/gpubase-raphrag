"""
Generation Stage
Handles LLM-based response generation for RAG pipeline.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Protocol, AsyncIterator
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


# ==================== Ports (Interfaces) ====================

class LLMPort(Protocol):
    """Port for LLM service"""

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """Generate response from messages"""
        ...


class StreamingLLMPort(Protocol):
    """Port for streaming LLM service"""

    async def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> AsyncIterator[str]:
        """Stream response tokens"""
        ...


class PromptTemplatePort(Protocol):
    """Port for prompt templates"""

    def format(self, **kwargs) -> List[Dict[str, str]]:
        """Format prompt with parameters"""
        ...


# ==================== Enums ====================

class GenerationMode(str, Enum):
    """Generation mode"""
    STANDARD = "standard"
    STREAMING = "streaming"
    BATCH = "batch"


class ResponseFormat(str, Enum):
    """Response format"""
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


# ==================== Configuration ====================

@dataclass
class GenerationConfig:
    """Configuration for generation stage"""
    mode: GenerationMode = GenerationMode.STANDARD
    temperature: float = 0.7
    max_tokens: int = 2048
    response_format: ResponseFormat = ResponseFormat.TEXT
    language: str = "auto"
    include_sources: bool = True
    max_context_length: int = 8000
    timeout_seconds: float = 60.0


# ==================== Result ====================

@dataclass
class GenerationResult:
    """Result from generation stage"""
    answer: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ==================== Stage Implementation ====================

class GenerationStage:
    """
    Generation stage of the RAG pipeline.

    Responsibilities:
    1. Build prompts from context and question
    2. Call LLM for response generation
    3. Handle streaming and batch modes
    4. Format and validate responses

    This stage is completely independent of:
    - Embedding logic
    - Retrieval logic
    - Storage concerns

    Example:
        stage = GenerationStage(llm, prompt_template, config)

        result = await stage.generate(
            question="What is RAG?",
            context="RAG stands for Retrieval-Augmented Generation..."
        )

        print(result.answer)
    """

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None,
        config: Optional[GenerationConfig] = None,
        streaming_llm: Optional[StreamingLLMPort] = None
    ):
        self.llm = llm
        self.prompt_template = prompt_template
        self.config = config or GenerationConfig()
        self.streaming_llm = streaming_llm

        self._default_system_prompt = self._get_default_system_prompt()

    async def generate(
        self,
        question: str,
        context: str = "",
        system_prompt: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> GenerationResult:
        """
        Generate a response.

        Args:
            question: User question
            context: Retrieved context
            system_prompt: Optional custom system prompt
            additional_params: Additional template parameters

        Returns:
            GenerationResult with answer and metadata
        """
        start_time = time.time()

        # Prepare context
        prepared_context = self._prepare_context(context)

        # Build messages
        messages = self._build_messages(
            question=question,
            context=prepared_context,
            system_prompt=system_prompt,
            additional_params=additional_params or {}
        )

        # Generate response
        try:
            response = await self.llm.generate(
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

        duration = (time.time() - start_time) * 1000

        # Parse response
        answer = self._parse_response(response)

        return GenerationResult(
            answer=answer,
            duration_ms=duration,
            metadata={
                "question": question,
                "context_length": len(prepared_context),
                "language": self.config.language
            }
        )

    async def stream_generate(
        self,
        question: str,
        context: str = "",
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Stream generate a response.

        Yields:
            Response tokens as they arrive
        """
        if not self.streaming_llm:
            # Fallback to non-streaming
            result = await self.generate(question, context, system_prompt)
            yield result.answer
            return

        # Prepare context
        prepared_context = self._prepare_context(context)

        # Build messages
        messages = self._build_messages(
            question=question,
            context=prepared_context,
            system_prompt=system_prompt,
            additional_params={}
        )

        # Stream response
        async for token in self.streaming_llm.stream(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        ):
            yield token

    def _prepare_context(self, context: str) -> str:
        """Prepare and truncate context"""
        if len(context) > self.config.max_context_length:
            context = context[:self.config.max_context_length] + "..."
        return context

    def _build_messages(
        self,
        question: str,
        context: str,
        system_prompt: Optional[str],
        additional_params: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Build messages for LLM"""
        if self.prompt_template:
            # Use provided template
            messages = self.prompt_template.format(
                question=question,
                context=context,
                **additional_params
            )
            # Convert to dict if needed
            if messages and hasattr(messages[0], "to_dict"):
                messages = [m.to_dict() for m in messages]
            return messages

        # Build default messages
        system = system_prompt or self._default_system_prompt
        user_content = self._build_user_message(question, context)

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content}
        ]

    def _build_user_message(self, question: str, context: str) -> str:
        """Build user message from question and context"""
        if context:
            return f"""Context:
{context}

Question: {question}

Please answer based on the provided context."""
        else:
            return question

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt based on language"""
        lang = self.config.language

        if lang == "ko":
            return """당신은 문서 기반 질의응답 전문가입니다.
주어진 컨텍스트를 바탕으로 정확하고 도움이 되는 답변을 제공하세요.

지침:
- 컨텍스트에 있는 정보만 사용하세요
- 불확실한 경우 명확히 밝히세요
- 답변은 명확하고 구조적으로 작성하세요"""

        elif lang == "ja":
            return """あなたは文書ベースのQ&A専門家です。
与えられたコンテキストに基づいて、正確で役立つ回答を提供してください。

ガイドライン:
- コンテキストの情報のみを使用
- 不確かな場合は明確に述べる
- 回答は明確に構成する"""

        else:  # Default to English
            return """You are a document-based Q&A expert.
Provide accurate and helpful answers based on the given context.

Guidelines:
- Only use information from the context
- Clearly state when uncertain
- Structure your answer clearly"""

    def _parse_response(self, response: Any) -> str:
        """Parse LLM response to string"""
        if isinstance(response, dict):
            return response.get("content", str(response))
        return str(response)

    def with_template(
        self,
        prompt_template: PromptTemplatePort
    ) -> "GenerationStage":
        """Create new stage with different prompt template"""
        return GenerationStage(
            self.llm,
            prompt_template,
            self.config,
            self.streaming_llm
        )

    def with_config(self, **kwargs) -> "GenerationStage":
        """Create new stage with modified config"""
        new_config = GenerationConfig(
            mode=kwargs.get("mode", self.config.mode),
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            response_format=kwargs.get("response_format", self.config.response_format),
            language=kwargs.get("language", self.config.language),
            include_sources=kwargs.get("include_sources", self.config.include_sources),
            max_context_length=kwargs.get("max_context_length", self.config.max_context_length)
        )
        return GenerationStage(
            self.llm,
            self.prompt_template,
            new_config,
            self.streaming_llm
        )


# ==================== Specialized Stages ====================

class AnalysisGenerationStage(GenerationStage):
    """Generation stage optimized for analysis"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationConfig(
            temperature=0.5,
            max_tokens=4096,
            max_context_length=12000
        )
        super().__init__(llm, prompt_template, config)

        self._default_system_prompt = """You are an expert analyst.
Provide systematic and comprehensive analysis.

Structure your response:
1. Key concepts identification
2. Related elements analysis
3. Relationships explanation
4. Conclusions and implications"""


class CodeGenerationStage(GenerationStage):
    """Generation stage optimized for code"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationConfig(
            temperature=0.3,
            max_tokens=4096,
            response_format=ResponseFormat.MARKDOWN
        )
        super().__init__(llm, prompt_template, config)

        self._default_system_prompt = """You are an expert programmer.
Provide working code examples with clear explanations.
Follow best practices and mention edge cases.
Use markdown code blocks with language specification."""


class ConversationalGenerationStage(GenerationStage):
    """Generation stage for conversational responses"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationConfig(
            temperature=0.7,
            max_tokens=1024
        )
        super().__init__(llm, prompt_template, config)

        self._default_system_prompt = """You are a helpful assistant.
Provide clear, conversational responses.
Be friendly and informative."""
