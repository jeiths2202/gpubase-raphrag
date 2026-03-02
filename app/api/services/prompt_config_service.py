"""
Prompt Configuration Service

Business logic for managing prompt configurations.
Handles CRUD operations, validation, caching, and file sync.
"""

import logging
from typing import Optional, List
from uuid import UUID
from pathlib import Path

from ..models.prompt_config import (
    PromptSummary, PromptDetail, PromptHistory,
    PromptTestResult, SyncResult, PromptCategory, PromptLanguage
)
from ..infrastructure.postgres.prompt_config_repository import PromptConfigRepository
from .prompt_cache import PromptCache

logger = logging.getLogger(__name__)


class PromptConfigService:
    """
    Service for managing prompt configurations.

    Responsibilities:
    - CRUD operations via repository
    - Validation and business rules
    - Cache management
    - File system synchronization
    """

    PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"
    MAX_CONTENT_LENGTH = 50000  # 50KB limit

    def __init__(self, repository: Optional[PromptConfigRepository] = None):
        """
        Initialize service.

        Args:
            repository: Database repository (optional, uses file-only mode if None)
        """
        self.repository = repository
        self.cache = PromptCache.get_instance()

    async def get_all_prompts(
        self,
        category: Optional[PromptCategory] = None,
        language: Optional[str] = None
    ) -> List[PromptSummary]:
        """
        Get all prompts with optional filtering.

        Args:
            category: Filter by category
            language: Filter by language

        Returns:
            List of PromptSummary
        """
        if self.repository:
            prompts = await self.repository.list_prompts(category, language)
            return [
                PromptSummary(
                    prompt_id=p.prompt_id,
                    name=p.name,
                    category=PromptCategory(p.category),
                    language=PromptLanguage(p.language),
                    is_readonly=p.is_readonly,
                    updated_at=p.updated_at,
                    content_preview=p.content[:100] + "..." if len(p.content) > 100 else p.content
                )
                for p in prompts
            ]
        else:
            # File-only mode: scan directory
            return self._scan_prompt_files(category)

    def _scan_prompt_files(self, category: Optional[PromptCategory] = None) -> List[PromptSummary]:
        """Scan prompt files when no database is available."""
        prompts = []

        # Agent prompts
        if category is None or category == PromptCategory.AGENT:
            for file_path in self.PROMPTS_DIR.glob("*.txt"):
                if file_path.name.startswith("_"):
                    continue
                prompt_id = file_path.stem
                content = file_path.read_text(encoding="utf-8")
                prompts.append(PromptSummary(
                    prompt_id=prompt_id,
                    name=prompt_id.replace("_", " ").title(),
                    category=PromptCategory.AGENT,
                    language=PromptLanguage.EN,
                    is_readonly=False,
                    content_preview=content[:100] + "..." if len(content) > 100 else content
                ))

        # Middleware prompts
        middleware_dir = self.PROMPTS_DIR / "middleware"
        if middleware_dir.exists() and (category is None or category == PromptCategory.MIDDLEWARE):
            for file_path in middleware_dir.glob("*.txt"):
                prompt_id = file_path.stem
                content = file_path.read_text(encoding="utf-8")
                prompts.append(PromptSummary(
                    prompt_id=prompt_id,
                    name=prompt_id.replace("_", " ").title(),
                    category=PromptCategory.MIDDLEWARE,
                    language=PromptLanguage.EN,
                    is_readonly=False,
                    content_preview=content[:100] + "..." if len(content) > 100 else content
                ))

        return prompts

    async def get_prompt(self, prompt_id: str, language: str = "en") -> Optional[PromptDetail]:
        """
        Get full prompt detail.

        Args:
            prompt_id: Prompt identifier
            language: Language code

        Returns:
            PromptDetail or None
        """
        if self.repository:
            prompt = await self.repository.get_prompt(prompt_id, language)
            if not prompt:
                return None

            version_count = await self.repository.count_versions(prompt_id, language)

            return PromptDetail(
                id=prompt.id,
                prompt_id=prompt.prompt_id,
                name=prompt.name,
                description=prompt.description,
                category=PromptCategory(prompt.category),
                language=PromptLanguage(prompt.language),
                content=prompt.content,
                is_readonly=prompt.is_readonly,
                source_file=prompt.source_file,
                created_at=prompt.created_at,
                updated_at=prompt.updated_at,
                updated_by=prompt.updated_by,
                version_count=version_count
            )
        else:
            # File-only mode
            content = self.cache.get(prompt_id, language)
            if not content:
                return None

            from datetime import datetime, timezone
            from uuid import uuid4

            return PromptDetail(
                id=uuid4(),
                prompt_id=prompt_id,
                name=prompt_id.replace("_", " ").title(),
                category=PromptCategory.AGENT,
                language=PromptLanguage(language),
                content=content,
                is_readonly=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                version_count=0
            )

    async def update_prompt(
        self,
        prompt_id: str,
        language: str,
        content: str,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> PromptDetail:
        """
        Update prompt content.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            content: New content
            reason: Change reason
            user_id: User making the change

        Returns:
            Updated PromptDetail

        Raises:
            ValueError: If prompt not found
            PermissionError: If prompt is readonly
        """
        # Check if prompt exists
        prompt = await self.get_prompt(prompt_id, language)
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")

        # Check readonly
        if prompt.is_readonly:
            raise PermissionError(f"Prompt '{prompt_id}' is read-only and cannot be modified")

        # Validate content
        self._validate_content(content)

        if self.repository:
            # Save current version to history
            current_prompt = await self.repository.get_prompt(prompt_id, language)
            if current_prompt:
                await self.repository.save_history(
                    prompt_id=prompt_id,
                    language=language,
                    content=current_prompt.content,
                    reason=reason,
                    user_id=user_id
                )

            # Update prompt
            await self.repository.update_prompt(
                prompt_id=prompt_id,
                language=language,
                content=content,
                user_id=user_id
            )

        # Update cache (hot reload) - always do this
        self.cache.update(prompt_id, language, content)

        logger.info(f"Prompt updated: {prompt_id} ({language}) by user {user_id}")

        return await self.get_prompt(prompt_id, language)

    async def get_prompt_history(
        self,
        prompt_id: str,
        language: str,
        limit: int = 20
    ) -> List[PromptHistory]:
        """
        Get version history for a prompt.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            limit: Maximum entries

        Returns:
            List of PromptHistory
        """
        if not self.repository:
            return []

        history_entries = await self.repository.get_history(prompt_id, language, limit)
        return [
            PromptHistory(
                id=h.id,
                version_number=h.version_number,
                content=h.content,
                change_reason=h.change_reason,
                changed_at=h.changed_at,
                changed_by=h.changed_by
            )
            for h in history_entries
        ]

    async def rollback_prompt(
        self,
        prompt_id: str,
        language: str,
        version_id: UUID,
        user_id: Optional[UUID] = None
    ) -> PromptDetail:
        """
        Rollback prompt to specific version.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            version_id: History entry ID
            user_id: User performing rollback

        Returns:
            Rolled back PromptDetail

        Raises:
            ValueError: If version not found
        """
        if not self.repository:
            raise ValueError("Rollback requires database storage")

        # Get version content
        version = await self.repository.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        # Update with version content
        return await self.update_prompt(
            prompt_id=prompt_id,
            language=language,
            content=version.content,
            reason=f"Rollback to version {version.version_number}",
            user_id=user_id
        )

    async def test_prompt(
        self,
        prompt_id: str,
        language: str,
        test_query: str,
        variables: dict
    ) -> PromptTestResult:
        """
        Test prompt with sample input.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            test_query: Test query
            variables: Template variables

        Returns:
            PromptTestResult
        """
        prompt = await self.get_prompt(prompt_id, language)
        if not prompt:
            return PromptTestResult(
                success=False,
                rendered_prompt="",
                token_count=0,
                error="Prompt not found"
            )

        try:
            # Simple variable substitution
            rendered = prompt.content
            for key, value in variables.items():
                rendered = rendered.replace(f"{{{key}}}", str(value))

            # Estimate token count (rough: 4 chars per token)
            token_count = len(rendered) // 4

            warnings = []
            if token_count > 4000:
                warnings.append(f"Prompt is large ({token_count} tokens). May impact performance.")
            if "{" in rendered and "}" in rendered:
                warnings.append("Unsubstituted variables detected in rendered prompt.")

            return PromptTestResult(
                success=True,
                rendered_prompt=rendered,
                token_count=token_count,
                warnings=warnings
            )
        except Exception as e:
            return PromptTestResult(
                success=False,
                rendered_prompt="",
                token_count=0,
                error=str(e)
            )

    async def sync_from_files(self) -> SyncResult:
        """
        Sync prompts from file system to database.

        Returns:
            SyncResult with sync statistics
        """
        if not self.repository:
            return SyncResult(synced=0, skipped=0, errors=["Database not available"])

        synced = 0
        skipped = 0
        errors = []

        # Sync agent prompts
        for file_path in self.PROMPTS_DIR.glob("*.txt"):
            if file_path.name.startswith("_"):
                continue

            try:
                prompt_id = file_path.stem
                content = file_path.read_text(encoding="utf-8")

                exists = await self.repository.prompt_exists(prompt_id, "en")
                if exists:
                    skipped += 1
                else:
                    await self.repository.create_prompt(
                        prompt_id=prompt_id,
                        category="agent",
                        name=prompt_id.replace("_", " ").title(),
                        content=content,
                        source_file=str(file_path)
                    )
                    synced += 1
                    # Update cache
                    self.cache.update(prompt_id, "en", content)
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

        # Sync middleware prompts
        middleware_dir = self.PROMPTS_DIR / "middleware"
        if middleware_dir.exists():
            for file_path in middleware_dir.glob("*.txt"):
                try:
                    prompt_id = file_path.stem
                    content = file_path.read_text(encoding="utf-8")

                    exists = await self.repository.prompt_exists(prompt_id, "en")
                    if exists:
                        skipped += 1
                    else:
                        await self.repository.create_prompt(
                            prompt_id=prompt_id,
                            category="middleware",
                            name=prompt_id.replace("_", " ").title(),
                            content=content,
                            source_file=str(file_path)
                        )
                        synced += 1
                        # Update cache
                        self.cache.update(prompt_id, "en", content)
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")

        logger.info(f"Prompt sync complete: {synced} synced, {skipped} skipped, {len(errors)} errors")
        return SyncResult(synced=synced, skipped=skipped, errors=errors)

    async def reload_cache(self):
        """Reload all prompts into cache."""
        if self.repository:
            prompts = await self.repository.list_prompts()
            for prompt in prompts:
                self.cache.update(prompt.prompt_id, prompt.language, prompt.content)
            logger.info(f"Prompt cache reloaded: {len(prompts)} prompts from database")
        else:
            # Load from files
            for file_path in self.PROMPTS_DIR.glob("*.txt"):
                if file_path.name.startswith("_"):
                    continue
                prompt_id = file_path.stem
                content = file_path.read_text(encoding="utf-8")
                self.cache.update(prompt_id, "en", content)

            middleware_dir = self.PROMPTS_DIR / "middleware"
            if middleware_dir.exists():
                for file_path in middleware_dir.glob("*.txt"):
                    prompt_id = file_path.stem
                    content = file_path.read_text(encoding="utf-8")
                    self.cache.update(prompt_id, "en", content)

            logger.info(f"Prompt cache reloaded from files: {self.cache.size()} prompts")

        self.cache.set_initialized()

    def _validate_content(self, content: str):
        """Validate prompt content."""
        if not content or not content.strip():
            raise ValueError("Prompt content cannot be empty")

        if len(content) > self.MAX_CONTENT_LENGTH:
            raise ValueError(f"Prompt content exceeds maximum length ({self.MAX_CONTENT_LENGTH} chars)")


# Global service instance
_service_instance: Optional[PromptConfigService] = None


def get_prompt_config_service() -> PromptConfigService:
    """Get the service instance."""
    global _service_instance
    if _service_instance is None:
        # Try to get repository from deps
        try:
            from ..infrastructure.postgres.prompt_config_repository import get_repository
            repo = get_repository()
            _service_instance = PromptConfigService(repo)
        except Exception:
            # File-only mode
            _service_instance = PromptConfigService(None)
    return _service_instance


def init_prompt_config_service(repository: Optional[PromptConfigRepository] = None) -> PromptConfigService:
    """Initialize the service."""
    global _service_instance
    _service_instance = PromptConfigService(repository)
    return _service_instance
