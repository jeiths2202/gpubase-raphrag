"""
Vision LLM Factory

Factory for creating Vision LLM adapters based on configuration.
Supports multiple providers: OpenAI, Anthropic, and local models.
"""

import logging
from typing import Any, Dict, Optional

from app.api.ports.vision_llm_port import VisionLLMPort

logger = logging.getLogger(__name__)


class VisionLLMFactory:
    """
    Factory for creating Vision LLM adapters.

    Supports:
    - OpenAI (GPT-4V, GPT-4o)
    - Anthropic (Claude 3 Vision)
    - Local models (placeholder for future)

    Usage:
        # From settings
        factory = VisionLLMFactory()
        vision_llm = factory.create_from_settings(settings.vision)

        # Direct creation
        vision_llm = factory.create_openai(api_key="...", model="gpt-4o")
    """

    # Supported providers
    PROVIDERS = ["openai", "anthropic", "local"]

    # Default models per provider
    DEFAULT_MODELS = {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "local": "llava-v1.6",
    }

    def __init__(self):
        """Initialize factory."""
        self._instances: Dict[str, VisionLLMPort] = {}

    def create(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> VisionLLMPort:
        """
        Create a Vision LLM adapter.

        Args:
            provider: Provider name (openai, anthropic, local)
            api_key: API key for the provider
            model: Model name (optional, uses default)
            **kwargs: Additional provider-specific options

        Returns:
            VisionLLMPort instance
        """
        provider = provider.lower()

        if provider not in self.PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}. Use one of {self.PROVIDERS}")

        model = model or self.DEFAULT_MODELS.get(provider)

        if provider == "openai":
            return self.create_openai(api_key, model, **kwargs)
        elif provider == "anthropic":
            return self.create_anthropic(api_key, model, **kwargs)
        elif provider == "local":
            return self.create_local(model, **kwargs)
        else:
            raise ValueError(f"Provider {provider} not implemented")

    def create_openai(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> VisionLLMPort:
        """
        Create OpenAI Vision adapter.

        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4o, gpt-4o-mini, gpt-4-turbo)
            base_url: Optional custom base URL
            max_retries: Maximum retry attempts
            timeout: Request timeout

        Returns:
            OpenAIVisionAdapter
        """
        from app.api.adapters.vision.openai_vision_adapter import OpenAIVisionAdapter

        return OpenAIVisionAdapter(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )

    def create_anthropic(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_retries: int = 3,
        timeout: int = 60,
    ) -> VisionLLMPort:
        """
        Create Anthropic Vision adapter.

        Args:
            api_key: Anthropic API key
            model: Model name (claude-3-5-sonnet, claude-3-opus, claude-3-haiku)
            max_retries: Maximum retry attempts
            timeout: Request timeout

        Returns:
            AnthropicVisionAdapter
        """
        from app.api.adapters.vision.anthropic_vision_adapter import AnthropicVisionAdapter

        return AnthropicVisionAdapter(
            api_key=api_key,
            model=model,
            max_retries=max_retries,
            timeout=timeout,
        )

    def create_local(
        self,
        model: str = "llava-v1.6",
        base_url: str = "http://localhost:8080",
        **kwargs
    ) -> VisionLLMPort:
        """
        Create local Vision LLM adapter.

        Placeholder for local models like LLaVA, Yi-VL.

        Args:
            model: Model name
            base_url: Local server URL

        Returns:
            LocalVisionAdapter (not implemented yet)
        """
        raise NotImplementedError(
            "Local Vision LLM adapter not implemented. "
            "Use OpenAI or Anthropic providers."
        )

    def create_from_settings(self, settings: Any) -> VisionLLMPort:
        """
        Create Vision LLM from settings object.

        Args:
            settings: VisionSettings object with provider, model, api_key

        Returns:
            VisionLLMPort instance
        """
        return self.create(
            provider=settings.provider,
            api_key=settings.api_key,
            model=settings.model,
            timeout=getattr(settings, 'timeout', 60),
        )

    def create_with_fallback(
        self,
        primary_settings: Any,
        fallback_settings: Optional[Any] = None,
    ) -> tuple:
        """
        Create primary and fallback Vision LLMs.

        Args:
            primary_settings: Settings for primary LLM
            fallback_settings: Settings for fallback LLM (optional)

        Returns:
            Tuple of (primary_llm, fallback_llm or None)
        """
        primary = self.create_from_settings(primary_settings)

        fallback = None
        if fallback_settings:
            try:
                fallback = self.create(
                    provider=fallback_settings.fallback_provider,
                    api_key=fallback_settings.fallback_api_key,
                    model=fallback_settings.fallback_model,
                )
            except Exception as e:
                logger.warning(f"Failed to create fallback Vision LLM: {e}")

        return primary, fallback

    def get_or_create(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> VisionLLMPort:
        """
        Get cached instance or create new one.

        Useful for reusing adapters across requests.

        Args:
            provider: Provider name
            api_key: API key
            model: Model name

        Returns:
            Cached or new VisionLLMPort instance
        """
        cache_key = f"{provider}:{model or 'default'}"

        if cache_key not in self._instances:
            self._instances[cache_key] = self.create(
                provider=provider,
                api_key=api_key,
                model=model,
                **kwargs
            )

        return self._instances[cache_key]

    def clear_cache(self) -> None:
        """Clear cached instances."""
        self._instances.clear()

    @staticmethod
    def get_supported_providers() -> Dict[str, Dict[str, Any]]:
        """Get information about supported providers."""
        return {
            "openai": {
                "name": "OpenAI",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                "default_model": "gpt-4o",
                "requires_api_key": True,
                "supports_streaming": True,
            },
            "anthropic": {
                "name": "Anthropic",
                "models": [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-opus-20240229",
                    "claude-3-haiku-20240307"
                ],
                "default_model": "claude-3-5-sonnet-20241022",
                "requires_api_key": True,
                "supports_streaming": True,
            },
            "local": {
                "name": "Local (LLaVA/Yi-VL)",
                "models": ["llava-v1.6", "yi-vl-6b"],
                "default_model": "llava-v1.6",
                "requires_api_key": False,
                "supports_streaming": False,
                "status": "not_implemented",
            },
        }


# Singleton factory instance
_factory: Optional[VisionLLMFactory] = None


def get_vision_llm_factory() -> VisionLLMFactory:
    """Get global Vision LLM factory instance."""
    global _factory
    if _factory is None:
        _factory = VisionLLMFactory()
    return _factory


def create_vision_llm(
    provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> VisionLLMPort:
    """
    Convenience function to create Vision LLM.

    Args:
        provider: Provider name
        api_key: API key
        model: Model name

    Returns:
        VisionLLMPort instance
    """
    return get_vision_llm_factory().create(
        provider=provider,
        api_key=api_key,
        model=model,
        **kwargs
    )
