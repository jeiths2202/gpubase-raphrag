"""
Base Prompt Infrastructure
Template system and registry for managing prompts.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Type, TypeVar
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='PromptTemplate')


class Language(str, Enum):
    """Supported languages for prompts"""
    KOREAN = "ko"
    ENGLISH = "en"
    JAPANESE = "ja"
    AUTO = "auto"


class PromptRole(str, Enum):
    """Message role in conversation"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class PromptConfig:
    """Configuration for prompt behavior"""
    language: Language = Language.AUTO
    max_context_length: int = 8000
    include_sources: bool = True
    response_format: str = "text"  # text, json, markdown
    temperature_hint: float = 0.7


@dataclass
class PromptMessage:
    """A single message in a prompt"""
    role: PromptRole
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role.value, "content": self.content}


class PromptTemplate(ABC):
    """
    Abstract base class for all prompt templates.

    Prompts are first-class citizens that:
    1. Have explicit input/output contracts
    2. Support multiple languages
    3. Are versioned and testable
    4. Can be validated before use

    Example:
        class AnswerPrompt(PromptTemplate):
            def __init__(self):
                super().__init__(
                    name="answer_generation",
                    version="1.0",
                    description="Generate answer from context"
                )

            def format(self, context: str, question: str, language: str) -> List[PromptMessage]:
                system = self.get_system_prompt(language)
                user = self.get_user_prompt(context, question, language)
                return [
                    PromptMessage(PromptRole.SYSTEM, system),
                    PromptMessage(PromptRole.USER, user)
                ]
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0",
        description: str = "",
        default_config: Optional[PromptConfig] = None
    ):
        self.name = name
        self.version = version
        self.description = description
        self.default_config = default_config or PromptConfig()

        # Template validation
        self._validate()

    @abstractmethod
    def format(self, **kwargs) -> List[PromptMessage]:
        """
        Format the prompt with given parameters.

        Returns:
            List of PromptMessage objects
        """
        pass

    @abstractmethod
    def get_required_params(self) -> List[str]:
        """
        Return list of required parameter names.

        Returns:
            List of parameter names
        """
        pass

    def format_string(self, **kwargs) -> str:
        """
        Format and return as a single string (for simple cases).

        Returns:
            Formatted prompt string
        """
        messages = self.format(**kwargs)
        return "\n\n".join(m.content for m in messages)

    def _validate(self) -> None:
        """Validate template configuration"""
        if not self.name:
            raise ValueError("Prompt template must have a name")

    def validate_params(self, **kwargs) -> List[str]:
        """
        Validate that all required parameters are provided.

        Returns:
            List of missing parameter names
        """
        required = set(self.get_required_params())
        provided = set(kwargs.keys())
        return list(required - provided)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', version='{self.version}')>"


class MultiLanguagePromptTemplate(PromptTemplate):
    """
    Prompt template with multi-language support.

    Subclasses define templates for each language and the base class
    handles language selection and fallback.
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0",
        description: str = "",
        default_language: Language = Language.KOREAN
    ):
        self.default_language = default_language
        self._templates: Dict[Language, Dict[str, str]] = {}
        super().__init__(name, version, description)

    def register_template(
        self,
        language: Language,
        system_template: str,
        user_template: str
    ) -> None:
        """Register templates for a language"""
        self._templates[language] = {
            "system": system_template,
            "user": user_template
        }

    def get_template(self, language: Language) -> Dict[str, str]:
        """Get template for language with fallback"""
        if language in self._templates:
            return self._templates[language]

        # Fallback to default language
        if self.default_language in self._templates:
            return self._templates[self.default_language]

        # Fallback to English
        if Language.ENGLISH in self._templates:
            return self._templates[Language.ENGLISH]

        raise ValueError(f"No template found for language: {language}")

    def detect_language(self, text: str) -> Language:
        """Detect language from text"""
        # Simple heuristic based on character ranges
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
        japanese_chars = sum(1 for c in text if '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')

        total = len(text)
        if total == 0:
            return self.default_language

        if korean_chars / total > 0.3:
            return Language.KOREAN
        elif japanese_chars / total > 0.3:
            return Language.JAPANESE
        else:
            return Language.ENGLISH


class PromptRegistry:
    """
    Central registry for all prompt templates.

    Provides:
    1. Single source of truth for prompts
    2. Version management
    3. Easy testing and validation
    4. Runtime prompt switching

    Usage:
        # Register prompts
        registry = PromptRegistry()
        registry.register(AnswerGenerationPrompt())
        registry.register(ConceptExtractionPrompt())

        # Get prompt
        prompt = registry.get("answer_generation")
        messages = prompt.format(context=ctx, question=q, language="ko")
    """

    _instance: Optional["PromptRegistry"] = None

    def __init__(self):
        self._prompts: Dict[str, PromptTemplate] = {}
        self._aliases: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> "PromptRegistry":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)"""
        cls._instance = None

    def register(self, prompt: PromptTemplate, alias: Optional[str] = None) -> None:
        """
        Register a prompt template.

        Args:
            prompt: Prompt template to register
            alias: Optional alias name
        """
        key = f"{prompt.name}:{prompt.version}"
        self._prompts[key] = prompt
        self._prompts[prompt.name] = prompt  # Latest version

        if alias:
            self._aliases[alias] = prompt.name

        logger.debug(f"Registered prompt: {key}")

    def get(self, name: str, version: Optional[str] = None) -> PromptTemplate:
        """
        Get a prompt template by name.

        Args:
            name: Prompt name or alias
            version: Optional specific version

        Returns:
            PromptTemplate instance

        Raises:
            KeyError: If prompt not found
        """
        # Check aliases
        if name in self._aliases:
            name = self._aliases[name]

        # Get specific version or latest
        key = f"{name}:{version}" if version else name

        if key not in self._prompts:
            raise KeyError(f"Prompt not found: {key}")

        return self._prompts[key]

    def list_prompts(self) -> List[Dict[str, str]]:
        """List all registered prompts"""
        seen = set()
        result = []

        for key, prompt in self._prompts.items():
            if prompt.name not in seen:
                seen.add(prompt.name)
                result.append({
                    "name": prompt.name,
                    "version": prompt.version,
                    "description": prompt.description
                })

        return result

    def validate_all(self) -> Dict[str, List[str]]:
        """Validate all prompts, return any issues"""
        issues = {}

        for name, prompt in self._prompts.items():
            try:
                prompt._validate()
            except Exception as e:
                issues[name] = [str(e)]

        return issues


# Global registry access
def get_prompt_registry() -> PromptRegistry:
    """Get the global prompt registry"""
    return PromptRegistry.get_instance()
