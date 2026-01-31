"""
Prompt Cache Service

Singleton in-memory cache for runtime prompt access.
Provides O(1) access to prompts without database queries.
Supports hot-reload without server restart.
"""

import logging
from typing import Optional, Dict, List
from threading import Lock
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Singleton cache for runtime prompt access.

    Usage:
        cache = PromptCache.get_instance()
        content = cache.get("rag_agent", "en")
        cache.update("rag_agent", "en", new_content)
    """

    _instance: Optional["PromptCache"] = None
    _lock = Lock()

    # Default prompts directory
    PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"

    def __init__(self):
        self._cache: Dict[str, str] = {}  # key: "{prompt_id}:{language}"
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "PromptCache":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def _make_key(self, prompt_id: str, language: str = "en") -> str:
        """Create cache key from prompt_id and language."""
        return f"{prompt_id}:{language}"

    def get(self, prompt_id: str, language: str = "en") -> Optional[str]:
        """
        Get prompt content from cache.

        Falls back to English if requested language not found.
        Falls back to file system if not in cache.
        """
        key = self._make_key(prompt_id, language)
        content = self._cache.get(key)

        # Fallback to English if not found
        if content is None and language != "en":
            key = self._make_key(prompt_id, "en")
            content = self._cache.get(key)

        # Fallback to file system
        if content is None:
            content = self._load_from_file(prompt_id)
            if content:
                self._cache[self._make_key(prompt_id, "en")] = content

        return content

    def _load_from_file(self, prompt_id: str) -> Optional[str]:
        """Load prompt from file system (fallback)."""
        # Try direct file
        file_path = self.PROMPTS_DIR / f"{prompt_id}.txt"
        if file_path.exists():
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to load prompt file {file_path}: {e}")

        # Try middleware subdirectory
        middleware_path = self.PROMPTS_DIR / "middleware" / f"{prompt_id}.txt"
        if middleware_path.exists():
            try:
                return middleware_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to load middleware prompt {middleware_path}: {e}")

        return None

    def update(self, prompt_id: str, language: str, content: str):
        """
        Update prompt in cache (hot reload).

        This is called when a prompt is saved via Admin UI.
        """
        key = self._make_key(prompt_id, language)
        self._cache[key] = content
        logger.debug(f"Prompt cache updated: {key} ({len(content)} chars)")

    def set(self, prompt_id: str, language: str, content: str):
        """Alias for update()."""
        self.update(prompt_id, language, content)

    def remove(self, prompt_id: str, language: str = "en"):
        """Remove prompt from cache."""
        key = self._make_key(prompt_id, language)
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Prompt removed from cache: {key}")

    def clear(self):
        """Clear all cached prompts."""
        self._cache.clear()
        self._initialized = False
        logger.info("Prompt cache cleared")

    def is_initialized(self) -> bool:
        """Check if cache has been initialized."""
        return self._initialized

    def set_initialized(self):
        """Mark cache as initialized."""
        self._initialized = True

    def get_all_keys(self) -> List[str]:
        """Get all cached prompt keys."""
        return list(self._cache.keys())

    def size(self) -> int:
        """Get number of cached prompts."""
        return len(self._cache)

    def bulk_update(self, prompts: Dict[str, Dict[str, str]]):
        """
        Bulk update prompts.

        Args:
            prompts: Dict of {prompt_id: {language: content}}
        """
        for prompt_id, lang_contents in prompts.items():
            for language, content in lang_contents.items():
                self.update(prompt_id, language, content)

        self._initialized = True
        logger.info(f"Bulk loaded {len(prompts)} prompts into cache")


# Convenience function
def get_prompt_cache() -> PromptCache:
    """Get the prompt cache singleton."""
    return PromptCache.get_instance()
