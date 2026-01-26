"""
LLM Port Interface
Abstract interface for Language Model operations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncGenerator
from enum import Enum


class LLMRole(str, Enum):
    """Message role in conversation"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMMessage:
    """Message for LLM conversation"""
    role: LLMRole
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """LLM configuration"""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: List[str] = field(default_factory=list)
    timeout: int = 60

    # Provider-specific settings
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMTokenUsage:
    """Token usage statistics"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM response"""
    content: str
    model: str
    usage: LLMTokenUsage = field(default_factory=LLMTokenUsage)
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMStreamChunk:
    """Streaming response chunk"""
    content: str
    is_final: bool = False
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMPort(ABC):
    """
    Abstract interface for Language Model operations.

    All LLM implementations must implement this interface.
    This allows swapping between different providers (OpenAI, Anthropic, etc.)
    without changing the application logic.
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: List of messages in the conversation
            config: Optional configuration override

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Generate a streaming response from the LLM.

        Args:
            messages: List of messages in the conversation
            config: Optional configuration override

        Yields:
            LLMStreamChunk for each piece of the response
        """
        pass

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        pass

    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """
        Get list of available models.

        Returns:
            List of model identifiers
        """
        pass

    async def generate_with_functions(
        self,
        messages: List[LLMMessage],
        functions: List[Dict[str, Any]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Generate response with function calling support.

        Args:
            messages: List of messages
            functions: List of function definitions
            config: Optional configuration

        Returns:
            LLMResponse with potential function calls
        """
        raise NotImplementedError("Function calling not supported by this provider")

    async def embed_for_completion(
        self,
        prompt: str,
        suffix: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Generate completion for a prompt (for code completion, etc.)

        Args:
            prompt: Text before cursor
            suffix: Text after cursor
            config: Optional configuration

        Returns:
            LLMResponse with completion
        """
        raise NotImplementedError("Completion mode not supported by this provider")

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the LLM service is healthy.

        Returns:
            True if service is healthy
        """
        pass
