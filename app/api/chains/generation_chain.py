"""
Generation Chain
Chain for LLM-based text generation with context.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Protocol, Union
import logging

from .base import Chain, ChainStep, ChainConfig, ChainResult

logger = logging.getLogger(__name__)


# ==================== Protocols for Dependencies ====================

class LLMPort(Protocol):
    """Protocol for LLM service"""
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str: ...


class PromptTemplatePort(Protocol):
    """Protocol for prompt templates"""
    def format(self, **kwargs) -> List[Dict[str, str]]: ...


# ==================== Data Classes ====================

@dataclass
class GenerationChainConfig(ChainConfig):
    """Configuration for generation chain"""
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    language: str = "auto"
    response_format: str = "text"  # text, json, markdown


@dataclass
class GenerationInput:
    """Input for generation chain"""
    question: str
    context: str = ""
    system_prompt: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationOutput:
    """Output from generation chain"""
    answer: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== Chain Steps ====================

class PrepareContextStep(ChainStep[GenerationInput, Dict[str, Any]]):
    """Step to prepare and format context"""

    def __init__(self, max_context_length: int = 8000):
        super().__init__("prepare_context")
        self.max_context_length = max_context_length

    async def execute(
        self,
        input: GenerationInput,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare context for generation"""
        # Truncate context if needed
        formatted_context = input.context
        if len(formatted_context) > self.max_context_length:
            formatted_context = formatted_context[:self.max_context_length] + "..."

        return {
            "question": input.question,
            "context": formatted_context,
            "system_prompt": input.system_prompt,
            "additional_context": input.additional_context
        }


class BuildMessagesStep(ChainStep[Dict[str, Any], Dict[str, Any]]):
    """Step to build LLM messages"""

    def __init__(
        self,
        prompt_template: Optional[PromptTemplatePort] = None,
        default_system: str = "You are a helpful assistant."
    ):
        super().__init__("build_messages")
        self.prompt_template = prompt_template
        self.default_system = default_system

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build messages for LLM"""
        if self.prompt_template:
            # Use template if provided
            messages = self.prompt_template.format(
                context=input["context"],
                question=input["question"],
                **input.get("additional_context", {})
            )
            # Convert PromptMessage to dict if needed
            if messages and hasattr(messages[0], "to_dict"):
                messages = [m.to_dict() for m in messages]
        else:
            # Build default messages
            system_prompt = input.get("system_prompt") or self.default_system
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_user_message(input)}
            ]

        return {
            **input,
            "messages": messages
        }

    def _build_user_message(self, input: Dict[str, Any]) -> str:
        """Build user message from context and question"""
        if input.get("context"):
            return f"""Context:
{input['context']}

Question: {input['question']}

Answer based on the context provided:"""
        else:
            return input["question"]


class GenerateStep(ChainStep[Dict[str, Any], Dict[str, Any]]):
    """Step to generate response using LLM"""

    def __init__(self, llm: LLMPort, config: GenerationChainConfig):
        super().__init__("generate")
        self.llm = llm
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate response"""
        messages = input["messages"]

        response = await self.llm.generate(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )

        return {
            **input,
            "raw_response": response
        }


class FormatResponseStep(ChainStep[Dict[str, Any], GenerationOutput]):
    """Step to format the final response"""

    def __init__(self, config: GenerationChainConfig):
        super().__init__("format_response")
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> GenerationOutput:
        """Format the generation output"""
        raw_response = input["raw_response"]

        # Handle different response formats
        if isinstance(raw_response, dict):
            answer = raw_response.get("content", str(raw_response))
            metadata = {
                k: v for k, v in raw_response.items()
                if k != "content"
            }
        else:
            answer = str(raw_response)
            metadata = {}

        return GenerationOutput(
            answer=answer,
            metadata={
                **metadata,
                "question": input["question"],
                "had_context": bool(input.get("context"))
            }
        )


# ==================== Generation Chain ====================

class GenerationChain(Chain[GenerationInput, GenerationOutput]):
    """
    Chain for LLM text generation.

    Supports:
    - Context preparation and truncation
    - Custom prompt templates
    - Configurable temperature and tokens
    - Response formatting

    Example:
        chain = GenerationChain(llm, prompt_template)

        result = await chain.run(GenerationInput(
            question="What is RAG?",
            context="RAG is Retrieval-Augmented Generation..."
        ))

        if result.is_success:
            print(result.output.answer)
    """

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None,
        config: Optional[GenerationChainConfig] = None,
        default_system_prompt: str = "You are a helpful assistant that answers questions based on the provided context."
    ):
        self._config = config or GenerationChainConfig()
        super().__init__("generation", self._config)

        self.llm = llm
        self.prompt_template = prompt_template
        self.default_system_prompt = default_system_prompt

        self._steps = self._build_steps()

    def _build_steps(self) -> List[ChainStep]:
        """Build chain steps"""
        return [
            PrepareContextStep(max_context_length=8000),
            BuildMessagesStep(
                prompt_template=self.prompt_template,
                default_system=self.default_system_prompt
            ),
            GenerateStep(self.llm, self._config),
            FormatResponseStep(self._config)
        ]

    def get_steps(self) -> List[ChainStep]:
        return self._steps

    def with_template(
        self,
        prompt_template: PromptTemplatePort
    ) -> "GenerationChain":
        """Create new chain with different prompt template"""
        return GenerationChain(
            self.llm,
            prompt_template,
            self._config,
            self.default_system_prompt
        )

    def with_system_prompt(self, system_prompt: str) -> "GenerationChain":
        """Create new chain with different system prompt"""
        return GenerationChain(
            self.llm,
            self.prompt_template,
            self._config,
            system_prompt
        )


# ==================== Specialized Chains ====================

class AnalysisChain(GenerationChain):
    """Chain specialized for deep analysis"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationChainConfig(
            temperature=0.5,  # Lower for analysis
            max_tokens=4096   # Higher for detailed analysis
        )
        super().__init__(
            llm,
            prompt_template,
            config,
            default_system_prompt="""You are an expert analyst.
Provide systematic and comprehensive analysis for complex questions.
Structure your response with:
1. Key concepts identification
2. Related elements analysis
3. Relationships explanation
4. Conclusions and implications"""
        )


class CodeGenerationChain(GenerationChain):
    """Chain specialized for code generation"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationChainConfig(
            temperature=0.3,  # Lower for code accuracy
            max_tokens=4096,
            response_format="markdown"
        )
        super().__init__(
            llm,
            prompt_template,
            config,
            default_system_prompt="""You are an expert programmer.
Provide working code examples with clear explanations.
Follow best practices and mention edge cases."""
        )


class SummarizationChain(GenerationChain):
    """Chain specialized for summarization"""

    def __init__(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ):
        config = GenerationChainConfig(
            temperature=0.3,
            max_tokens=1024
        )
        super().__init__(
            llm,
            prompt_template,
            config,
            default_system_prompt="""You are a summarization expert.
Create concise, accurate summaries that preserve key information.
Use clear language and maintain factual accuracy."""
        )
