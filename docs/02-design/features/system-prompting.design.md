# System Prompting Feature - Design Document

## Feature Overview

**Feature Name**: System Prompting Admin UI
**Version**: v1.0
**Created**: 2026-01-31
**Status**: Design
**Plan Reference**: `docs/01-plan/features/system-prompting.plan.md`

---

## 1. Architecture Overview

### 1.1 System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Admin Dashboard                                 │
│  ┌──────────┐ ┌──────────┐ ┌───────────────┐ ┌────────────┐                │
│  │  Users   │ │ Scoring  │ │   Prompts     │ │Enhancement │                │
│  │   Tab    │ │   Tab    │ │    Tab ★      │ │    Tab     │                │
│  └──────────┘ └──────────┘ └───────────────┘ └────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    /api/v1/admin/prompts                                │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │ │
│  │  │ GET /       │ │ GET /{id}   │ │ PUT /{id}   │ │ POST /sync  │       │ │
│  │  │ List All    │ │ Get Detail  │ │ Update      │ │ File→DB    │       │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    PromptConfigService                                  │ │
│  │  - get_all_prompts()      - update_prompt()     - rollback_prompt()    │ │
│  │  - get_prompt()           - validate_prompt()   - reload_cache()       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    PromptCache (Singleton)                              │ │
│  │  - In-memory cache for runtime access                                   │ │
│  │  - Hot-reload without restart                                           │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌─────────────────────────────────┐  ┌─────────────────────────────────────┐
│        File System              │  │           PostgreSQL                 │
│  ┌───────────────────────────┐  │  │  ┌─────────────────────────────────┐│
│  │ app/api/agents/prompts/   │  │  │  │      prompt_configs            ││
│  │   ├── rag_agent.txt       │  │  │  │  - id, prompt_id, category     ││
│  │   ├── code_agent.txt      │  │  │  │  - content, language           ││
│  │   ├── vision_agent.txt    │  │  │  │  - is_readonly, source_file   ││
│  │   └── middleware/         │  │  │  └─────────────────────────────────┘│
│  │       ├── rag_system.txt  │  │  │  ┌─────────────────────────────────┐│
│  │       └── ...             │  │  │  │      prompt_history            ││
│  └───────────────────────────┘  │  │  │  - prompt_id, version_number   ││
│  (Read-only source of truth)    │  │  │  - content, changed_by/at      ││
└─────────────────────────────────┘  │  └─────────────────────────────────┘│
                                     └─────────────────────────────────────┘
```

### 1.2 Data Flow

```
1. Server Startup:
   File System → PromptConfigService.init() → PromptCache (memory)
                                            ↘ PostgreSQL (sync if needed)

2. Admin Views Prompts:
   Frontend → GET /admin/prompts → PromptConfigService → PromptCache → Response

3. Admin Updates Prompt:
   Frontend → PUT /admin/prompts/{id} → PromptConfigService
                                        ├→ PostgreSQL (persist)
                                        ├→ prompt_history (version)
                                        └→ PromptCache.update() (hot reload)

4. Agent Uses Prompt:
   RAGAgent/CodeAgent → PromptCache.get(prompt_id) → Prompt Content
```

---

## 2. Database Schema

### 2.1 prompt_configs Table

```sql
CREATE TABLE prompt_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification
    prompt_id VARCHAR(100) NOT NULL,        -- 'rag_agent', 'code_agent', etc.
    language VARCHAR(10) DEFAULT 'en',      -- 'en', 'ko', 'ja'

    -- Classification
    category VARCHAR(50) NOT NULL,          -- 'agent', 'middleware', 'system', 'persona', 'domain'
    name VARCHAR(200) NOT NULL,             -- Human-readable name
    description TEXT,

    -- Content
    content TEXT NOT NULL,

    -- Protection
    is_readonly BOOLEAN DEFAULT FALSE,      -- TRUE for master_constraint

    -- Source tracking
    source_file VARCHAR(255),               -- Original file path

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),

    -- Constraints
    CONSTRAINT unique_prompt_language UNIQUE (prompt_id, language)
);

-- Indexes
CREATE INDEX idx_prompt_configs_category ON prompt_configs(category);
CREATE INDEX idx_prompt_configs_prompt_id ON prompt_configs(prompt_id);
```

### 2.2 prompt_history Table

```sql
CREATE TABLE prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Reference
    prompt_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'en',
    version_number INTEGER NOT NULL,

    -- Snapshot
    content TEXT NOT NULL,

    -- Audit
    change_reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changed_by UUID REFERENCES users(id),

    -- Constraints
    CONSTRAINT unique_prompt_version UNIQUE (prompt_id, language, version_number)
);

-- Indexes
CREATE INDEX idx_prompt_history_lookup ON prompt_history(prompt_id, language);
CREATE INDEX idx_prompt_history_changed_at ON prompt_history(changed_at DESC);
```

### 2.3 Initial Data (Seed)

```sql
-- Agent prompts
INSERT INTO prompt_configs (prompt_id, language, category, name, source_file, content)
VALUES
    ('rag_agent', 'en', 'agent', 'RAG Agent System Prompt', 'app/api/agents/prompts/rag_agent.txt', '...'),
    ('code_agent', 'en', 'agent', 'Code Agent System Prompt', 'app/api/agents/prompts/code_agent.txt', '...'),
    ('vision_agent', 'en', 'agent', 'Vision Agent System Prompt', 'app/api/agents/prompts/vision_agent.txt', '...'),
    ('ims_agent', 'en', 'agent', 'IMS Agent System Prompt', 'app/api/agents/prompts/ims_agent.txt', '...'),
    ('opencode_agent', 'en', 'agent', 'OpenCode Agent System Prompt', 'app/api/agents/prompts/opencode_agent.txt', '...'),
    ('planner_agent', 'en', 'agent', 'Planner Agent System Prompt', 'app/api/agents/prompts/planner_agent.txt', '...'),
    ('enhancement_analyst_agent', 'en', 'agent', 'Enhancement Analyst Agent', 'app/api/agents/prompts/enhancement_analyst_agent.txt', '...'),
    ('enhancement_architect_agent', 'en', 'agent', 'Enhancement Architect Agent', 'app/api/agents/prompts/enhancement_architect_agent.txt', '...'),
    ('enhancement_coder_agent', 'en', 'agent', 'Enhancement Coder Agent', 'app/api/agents/prompts/enhancement_coder_agent.txt', '...'),
    ('enhancement_qa_agent', 'en', 'agent', 'Enhancement QA Agent', 'app/api/agents/prompts/enhancement_qa_agent.txt', '...');

-- Middleware prompts
INSERT INTO prompt_configs (prompt_id, language, category, name, source_file, content)
VALUES
    ('rag_system', 'en', 'middleware', 'RAG System Guidelines', 'app/api/agents/prompts/middleware/rag_system.txt', '...'),
    ('code_system', 'en', 'middleware', 'Code System Guidelines', 'app/api/agents/prompts/middleware/code_system.txt', '...'),
    ('ims_system', 'en', 'middleware', 'IMS System Guidelines', 'app/api/agents/prompts/middleware/ims_system.txt', '...');

-- Master constraint (readonly)
INSERT INTO prompt_configs (prompt_id, language, category, name, is_readonly, content)
VALUES
    ('master_constraint', 'en', 'system', 'Master System Constraint', TRUE, '...');
```

---

## 3. Backend API Design

### 3.1 Pydantic Models

**File**: `app/api/models/prompt_config.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class PromptCategory(str, Enum):
    """Prompt categories"""
    AGENT = "agent"
    MIDDLEWARE = "middleware"
    SYSTEM = "system"
    PERSONA = "persona"
    DOMAIN = "domain"


class PromptLanguage(str, Enum):
    """Supported languages"""
    EN = "en"
    KO = "ko"
    JA = "ja"


class PromptSummary(BaseModel):
    """Prompt list item"""
    prompt_id: str
    name: str
    category: PromptCategory
    language: PromptLanguage = PromptLanguage.EN
    is_readonly: bool = False
    updated_at: Optional[datetime] = None
    content_preview: str = Field(
        default="",
        description="First 100 chars of content"
    )


class PromptDetail(BaseModel):
    """Full prompt detail"""
    id: UUID
    prompt_id: str
    name: str
    description: Optional[str] = None
    category: PromptCategory
    language: PromptLanguage = PromptLanguage.EN
    content: str
    is_readonly: bool = False
    source_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[UUID] = None
    version_count: int = 0


class PromptUpdateRequest(BaseModel):
    """Request to update prompt"""
    content: str = Field(..., min_length=1, max_length=50000)
    reason: Optional[str] = Field(None, max_length=500)


class PromptHistory(BaseModel):
    """Version history item"""
    id: UUID
    version_number: int
    content: str
    change_reason: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[UUID] = None


class PromptTestRequest(BaseModel):
    """Request to test prompt"""
    test_query: str = Field(..., min_length=1, max_length=1000)
    variables: dict = Field(default_factory=dict)


class PromptTestResult(BaseModel):
    """Test result"""
    success: bool
    rendered_prompt: str
    token_count: int
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class SyncResult(BaseModel):
    """File sync result"""
    synced: int
    skipped: int
    errors: List[str] = Field(default_factory=list)
```

### 3.2 Router Endpoints

**File**: `app/api/routers/admin_prompts.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from uuid import UUID

from ..core.deps import get_current_user
from ..models.prompt_config import (
    PromptSummary, PromptDetail, PromptUpdateRequest,
    PromptHistory, PromptTestRequest, PromptTestResult,
    SyncResult, PromptCategory
)
from ..services.prompt_config_service import (
    get_prompt_config_service, PromptConfigService
)

router = APIRouter(
    prefix="/admin/prompts",
    tags=["Admin - Prompt Configuration"],
)


# Admin auth dependency
async def require_admin(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@router.get(
    "",
    response_model=List[PromptSummary],
    summary="List all prompts",
    description="Returns all prompts grouped by category"
)
async def list_prompts(
    category: Optional[PromptCategory] = None,
    language: Optional[str] = None,
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
) -> List[PromptSummary]:
    """List all prompts with optional filtering."""
    return await service.get_all_prompts(category=category, language=language)


@router.get(
    "/{prompt_id}",
    response_model=PromptDetail,
    summary="Get prompt detail"
)
async def get_prompt(
    prompt_id: str,
    language: str = "en",
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
) -> PromptDetail:
    """Get full prompt detail including content."""
    prompt = await service.get_prompt(prompt_id, language)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.put(
    "/{prompt_id}",
    response_model=PromptDetail,
    summary="Update prompt"
)
async def update_prompt(
    prompt_id: str,
    request: PromptUpdateRequest,
    language: str = "en",
    service: PromptConfigService = Depends(get_prompt_config_service),
    admin = Depends(require_admin),
) -> PromptDetail:
    """Update prompt content. Creates new version in history."""
    try:
        user_id = admin.get('id')
        return await service.update_prompt(
            prompt_id=prompt_id,
            language=language,
            content=request.content,
            reason=request.reason,
            user_id=user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/{prompt_id}/history",
    response_model=List[PromptHistory],
    summary="Get version history"
)
async def get_prompt_history(
    prompt_id: str,
    language: str = "en",
    limit: int = 20,
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
) -> List[PromptHistory]:
    """Get version history for a prompt."""
    return await service.get_prompt_history(prompt_id, language, limit)


@router.post(
    "/{prompt_id}/rollback/{version_id}",
    response_model=PromptDetail,
    summary="Rollback to version"
)
async def rollback_prompt(
    prompt_id: str,
    version_id: UUID,
    language: str = "en",
    service: PromptConfigService = Depends(get_prompt_config_service),
    admin = Depends(require_admin),
) -> PromptDetail:
    """Rollback prompt to a specific version."""
    try:
        user_id = admin.get('id')
        return await service.rollback_prompt(
            prompt_id=prompt_id,
            language=language,
            version_id=version_id,
            user_id=user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{prompt_id}/test",
    response_model=PromptTestResult,
    summary="Test prompt"
)
async def test_prompt(
    prompt_id: str,
    request: PromptTestRequest,
    language: str = "en",
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
) -> PromptTestResult:
    """Test prompt rendering with sample variables."""
    return await service.test_prompt(
        prompt_id=prompt_id,
        language=language,
        test_query=request.test_query,
        variables=request.variables
    )


@router.post(
    "/sync",
    response_model=SyncResult,
    summary="Sync from files"
)
async def sync_prompts(
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
) -> SyncResult:
    """Sync prompts from file system to database."""
    return await service.sync_from_files()


@router.post(
    "/reload",
    summary="Reload cache"
)
async def reload_cache(
    service: PromptConfigService = Depends(get_prompt_config_service),
    _admin = Depends(require_admin),
):
    """Force reload prompts into runtime cache."""
    await service.reload_cache()
    return {"status": "ok", "message": "Cache reloaded"}
```

### 3.3 Service Layer

**File**: `app/api/services/prompt_config_service.py`

```python
import logging
from typing import Optional, List, Dict
from uuid import UUID
from pathlib import Path

from ..models.prompt_config import (
    PromptSummary, PromptDetail, PromptHistory,
    PromptTestResult, SyncResult, PromptCategory
)
from ..infrastructure.postgres.prompt_config_repository import PromptConfigRepository
from .prompt_cache import PromptCache

logger = logging.getLogger(__name__)


class PromptConfigService:
    """Service for managing prompt configurations."""

    PROMPTS_DIR = Path("app/api/agents/prompts")
    MASTER_CONSTRAINT_FILE = Path("app/api/agents/master_system_constraint.py")

    def __init__(self, repository: PromptConfigRepository):
        self.repository = repository
        self.cache = PromptCache.get_instance()

    async def get_all_prompts(
        self,
        category: Optional[PromptCategory] = None,
        language: Optional[str] = None
    ) -> List[PromptSummary]:
        """Get all prompts with optional filtering."""
        prompts = await self.repository.list_prompts(category, language)
        return [
            PromptSummary(
                prompt_id=p.prompt_id,
                name=p.name,
                category=p.category,
                language=p.language,
                is_readonly=p.is_readonly,
                updated_at=p.updated_at,
                content_preview=p.content[:100] + "..." if len(p.content) > 100 else p.content
            )
            for p in prompts
        ]

    async def get_prompt(self, prompt_id: str, language: str = "en") -> Optional[PromptDetail]:
        """Get full prompt detail."""
        prompt = await self.repository.get_prompt(prompt_id, language)
        if not prompt:
            return None

        version_count = await self.repository.count_versions(prompt_id, language)

        return PromptDetail(
            id=prompt.id,
            prompt_id=prompt.prompt_id,
            name=prompt.name,
            description=prompt.description,
            category=prompt.category,
            language=prompt.language,
            content=prompt.content,
            is_readonly=prompt.is_readonly,
            source_file=prompt.source_file,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
            updated_by=prompt.updated_by,
            version_count=version_count
        )

    async def update_prompt(
        self,
        prompt_id: str,
        language: str,
        content: str,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> PromptDetail:
        """Update prompt content."""
        # Check if readonly
        prompt = await self.repository.get_prompt(prompt_id, language)
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if prompt.is_readonly:
            raise PermissionError(f"Prompt '{prompt_id}' is read-only and cannot be modified")

        # Validate content
        self._validate_content(content)

        # Save current version to history
        await self.repository.save_history(
            prompt_id=prompt_id,
            language=language,
            content=prompt.content,
            reason=reason,
            user_id=user_id
        )

        # Update prompt
        updated = await self.repository.update_prompt(
            prompt_id=prompt_id,
            language=language,
            content=content,
            user_id=user_id
        )

        # Update cache (hot reload)
        self.cache.update(prompt_id, language, content)

        logger.info(f"Prompt updated: {prompt_id} ({language}) by user {user_id}")

        return await self.get_prompt(prompt_id, language)

    async def get_prompt_history(
        self,
        prompt_id: str,
        language: str,
        limit: int = 20
    ) -> List[PromptHistory]:
        """Get version history."""
        return await self.repository.get_history(prompt_id, language, limit)

    async def rollback_prompt(
        self,
        prompt_id: str,
        language: str,
        version_id: UUID,
        user_id: Optional[UUID] = None
    ) -> PromptDetail:
        """Rollback to specific version."""
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
        """Test prompt with sample input."""
        prompt = await self.repository.get_prompt(prompt_id, language)
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
        """Sync prompts from file system to database."""
        synced = 0
        skipped = 0
        errors = []

        # Sync agent prompts
        for file_path in self.PROMPTS_DIR.glob("*.txt"):
            try:
                prompt_id = file_path.stem
                content = file_path.read_text(encoding="utf-8")

                existing = await self.repository.get_prompt(prompt_id, "en")
                if existing:
                    skipped += 1
                else:
                    await self.repository.create_prompt(
                        prompt_id=prompt_id,
                        category="agent",
                        name=f"{prompt_id.replace('_', ' ').title()}",
                        content=content,
                        source_file=str(file_path)
                    )
                    synced += 1
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

        # Sync middleware prompts
        middleware_dir = self.PROMPTS_DIR / "middleware"
        if middleware_dir.exists():
            for file_path in middleware_dir.glob("*.txt"):
                try:
                    prompt_id = file_path.stem
                    content = file_path.read_text(encoding="utf-8")

                    existing = await self.repository.get_prompt(prompt_id, "en")
                    if existing:
                        skipped += 1
                    else:
                        await self.repository.create_prompt(
                            prompt_id=prompt_id,
                            category="middleware",
                            name=f"{prompt_id.replace('_', ' ').title()}",
                            content=content,
                            source_file=str(file_path)
                        )
                        synced += 1
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")

        # Reload cache
        await self.reload_cache()

        return SyncResult(synced=synced, skipped=skipped, errors=errors)

    async def reload_cache(self):
        """Reload all prompts into cache."""
        prompts = await self.repository.list_prompts()
        for prompt in prompts:
            self.cache.update(prompt.prompt_id, prompt.language, prompt.content)
        logger.info(f"Prompt cache reloaded: {len(prompts)} prompts")

    def _validate_content(self, content: str):
        """Validate prompt content."""
        if not content or not content.strip():
            raise ValueError("Prompt content cannot be empty")

        if len(content) > 50000:
            raise ValueError("Prompt content exceeds maximum length (50KB)")


# Dependency injection
_service_instance: Optional[PromptConfigService] = None

def get_prompt_config_service() -> PromptConfigService:
    global _service_instance
    if _service_instance is None:
        from ..infrastructure.postgres.prompt_config_repository import get_repository
        _service_instance = PromptConfigService(get_repository())
    return _service_instance
```

### 3.4 PromptCache (Runtime Cache)

**File**: `app/api/services/prompt_cache.py`

```python
import logging
from typing import Optional, Dict
from threading import Lock

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Singleton cache for runtime prompt access.

    Provides O(1) access to prompts without database queries.
    Supports hot-reload without server restart.
    """

    _instance: Optional["PromptCache"] = None
    _lock = Lock()

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

    def _make_key(self, prompt_id: str, language: str = "en") -> str:
        return f"{prompt_id}:{language}"

    def get(self, prompt_id: str, language: str = "en") -> Optional[str]:
        """Get prompt content from cache."""
        key = self._make_key(prompt_id, language)
        content = self._cache.get(key)

        # Fallback to English if not found
        if content is None and language != "en":
            key = self._make_key(prompt_id, "en")
            content = self._cache.get(key)

        return content

    def update(self, prompt_id: str, language: str, content: str):
        """Update prompt in cache (hot reload)."""
        key = self._make_key(prompt_id, language)
        self._cache[key] = content
        logger.debug(f"Prompt cache updated: {key}")

    def remove(self, prompt_id: str, language: str = "en"):
        """Remove prompt from cache."""
        key = self._make_key(prompt_id, language)
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        """Clear all cached prompts."""
        self._cache.clear()
        self._initialized = False

    def is_initialized(self) -> bool:
        return self._initialized

    def set_initialized(self):
        self._initialized = True

    def get_all_keys(self) -> list:
        """Get all cached prompt keys."""
        return list(self._cache.keys())
```

---

## 4. Frontend Design

### 4.1 Component Structure

```
kms-portal-ui/src/components/admin/prompts/
├── index.tsx                 # PromptTab main component
├── PromptList.tsx            # Left sidebar with prompt list
├── PromptEditor.tsx          # Monaco editor for content
├── PromptHistory.tsx         # Version history panel
├── PromptMetadata.tsx        # Name, category, description
└── PromptActions.tsx         # Save, Reset, Test buttons
```

### 4.2 Main Component (PromptTab)

**File**: `kms-portal-ui/src/components/admin/prompts/index.tsx`

```tsx
import React, { useState, useEffect } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { promptsApi, PromptSummary, PromptDetail } from '../../../api/prompts.api';
import { PromptList } from './PromptList';
import { PromptEditor } from './PromptEditor';
import { PromptHistory } from './PromptHistory';
import './PromptTab.css';

export const PromptTab: React.FC = () => {
  const { t } = useTranslation();
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [editedContent, setEditedContent] = useState('');

  // Load prompts on mount
  useEffect(() => {
    loadPrompts();
  }, []);

  const loadPrompts = async () => {
    try {
      setLoading(true);
      const data = await promptsApi.listPrompts();
      setPrompts(data);
    } catch (err) {
      setError(t('prompts.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPrompt = async (promptId: string) => {
    try {
      const detail = await promptsApi.getPrompt(promptId);
      setSelectedPrompt(detail);
      setEditedContent(detail.content);
      setHasChanges(false);
    } catch (err) {
      setError(t('prompts.errors.loadDetailFailed'));
    }
  };

  const handleContentChange = (content: string) => {
    setEditedContent(content);
    setHasChanges(content !== selectedPrompt?.content);
  };

  const handleSave = async () => {
    if (!selectedPrompt) return;

    try {
      const updated = await promptsApi.updatePrompt(selectedPrompt.prompt_id, {
        content: editedContent,
        reason: 'Updated via Admin UI'
      });
      setSelectedPrompt(updated);
      setHasChanges(false);
    } catch (err) {
      setError(t('prompts.errors.saveFailed'));
    }
  };

  const handleReset = () => {
    if (selectedPrompt) {
      setEditedContent(selectedPrompt.content);
      setHasChanges(false);
    }
  };

  const handleRollback = async (versionId: string) => {
    if (!selectedPrompt) return;

    try {
      const updated = await promptsApi.rollbackPrompt(
        selectedPrompt.prompt_id,
        versionId
      );
      setSelectedPrompt(updated);
      setEditedContent(updated.content);
      setHasChanges(false);
      setShowHistory(false);
    } catch (err) {
      setError(t('prompts.errors.rollbackFailed'));
    }
  };

  if (loading) {
    return <div className="prompt-tab-loading">{t('common.loading')}</div>;
  }

  return (
    <div className="prompt-tab">
      {error && (
        <div className="prompt-tab-error">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="prompt-tab-content">
        {/* Left: Prompt List */}
        <PromptList
          prompts={prompts}
          selectedId={selectedPrompt?.prompt_id}
          onSelect={handleSelectPrompt}
        />

        {/* Right: Editor + Actions */}
        <div className="prompt-tab-editor">
          {selectedPrompt ? (
            <>
              {/* Metadata Header */}
              <div className="prompt-metadata">
                <h2>{selectedPrompt.name}</h2>
                <div className="prompt-metadata-badges">
                  <span className="badge category">{selectedPrompt.category}</span>
                  <span className="badge language">{selectedPrompt.language}</span>
                  {selectedPrompt.is_readonly && (
                    <span className="badge readonly">Read-only</span>
                  )}
                </div>
                {selectedPrompt.description && (
                  <p className="prompt-description">{selectedPrompt.description}</p>
                )}
              </div>

              {/* Monaco Editor */}
              <PromptEditor
                content={editedContent}
                onChange={handleContentChange}
                readonly={selectedPrompt.is_readonly}
              />

              {/* Actions */}
              <div className="prompt-actions">
                <button
                  onClick={handleSave}
                  disabled={!hasChanges || selectedPrompt.is_readonly}
                  className="btn-primary"
                >
                  {t('common.save')}
                </button>
                <button
                  onClick={handleReset}
                  disabled={!hasChanges}
                  className="btn-secondary"
                >
                  {t('common.reset')}
                </button>
                <button
                  onClick={() => setShowHistory(!showHistory)}
                  className="btn-tertiary"
                >
                  {t('prompts.history')} ({selectedPrompt.version_count})
                </button>
              </div>

              {/* History Panel */}
              {showHistory && (
                <PromptHistory
                  promptId={selectedPrompt.prompt_id}
                  onRollback={handleRollback}
                  onClose={() => setShowHistory(false)}
                />
              )}
            </>
          ) : (
            <div className="prompt-tab-placeholder">
              {t('prompts.selectPrompt')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
```

### 4.3 API Client

**File**: `kms-portal-ui/src/api/prompts.api.ts`

```typescript
import { client } from './client';

export interface PromptSummary {
  prompt_id: string;
  name: string;
  category: 'agent' | 'middleware' | 'system' | 'persona' | 'domain';
  language: string;
  is_readonly: boolean;
  updated_at: string | null;
  content_preview: string;
}

export interface PromptDetail {
  id: string;
  prompt_id: string;
  name: string;
  description: string | null;
  category: string;
  language: string;
  content: string;
  is_readonly: boolean;
  source_file: string | null;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
  version_count: number;
}

export interface PromptHistory {
  id: string;
  version_number: number;
  content: string;
  change_reason: string | null;
  changed_at: string;
  changed_by: string | null;
}

export interface PromptUpdateRequest {
  content: string;
  reason?: string;
}

export const promptsApi = {
  listPrompts: async (category?: string, language?: string): Promise<PromptSummary[]> => {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (language) params.append('language', language);

    const response = await client.get(`/api/v1/admin/prompts?${params}`);
    return response.data;
  },

  getPrompt: async (promptId: string, language = 'en'): Promise<PromptDetail> => {
    const response = await client.get(
      `/api/v1/admin/prompts/${promptId}?language=${language}`
    );
    return response.data;
  },

  updatePrompt: async (
    promptId: string,
    request: PromptUpdateRequest,
    language = 'en'
  ): Promise<PromptDetail> => {
    const response = await client.put(
      `/api/v1/admin/prompts/${promptId}?language=${language}`,
      request
    );
    return response.data;
  },

  getHistory: async (
    promptId: string,
    language = 'en',
    limit = 20
  ): Promise<PromptHistory[]> => {
    const response = await client.get(
      `/api/v1/admin/prompts/${promptId}/history?language=${language}&limit=${limit}`
    );
    return response.data;
  },

  rollbackPrompt: async (
    promptId: string,
    versionId: string,
    language = 'en'
  ): Promise<PromptDetail> => {
    const response = await client.post(
      `/api/v1/admin/prompts/${promptId}/rollback/${versionId}?language=${language}`
    );
    return response.data;
  },

  syncFromFiles: async (): Promise<{ synced: number; skipped: number; errors: string[] }> => {
    const response = await client.post('/api/v1/admin/prompts/sync');
    return response.data;
  },

  reloadCache: async (): Promise<void> => {
    await client.post('/api/v1/admin/prompts/reload');
  },
};
```

### 4.4 Translations

**File**: `kms-portal-ui/src/i18n/locales/en/common.json` (additions)

```json
{
  "prompts": {
    "title": "System Prompts",
    "selectPrompt": "Select a prompt to edit",
    "history": "History",
    "categories": {
      "agent": "Agent Prompts",
      "middleware": "Middleware",
      "system": "System",
      "persona": "Persona",
      "domain": "Domain"
    },
    "actions": {
      "save": "Save Changes",
      "reset": "Reset",
      "rollback": "Rollback",
      "sync": "Sync from Files",
      "reload": "Reload Cache"
    },
    "errors": {
      "loadFailed": "Failed to load prompts",
      "loadDetailFailed": "Failed to load prompt details",
      "saveFailed": "Failed to save prompt",
      "rollbackFailed": "Failed to rollback prompt"
    },
    "readonly": "This prompt is read-only and cannot be modified",
    "unsavedChanges": "You have unsaved changes"
  }
}
```

---

## 5. Integration Points

### 5.1 Agent Prompt Loading (Modified)

**File**: `app/api/agents/adapters/deep_agent_adapter.py` (changes)

```python
# BEFORE:
def _load_agent_prompt(agent_type: str) -> str:
    prompt_path = PROMPTS_DIR / f"{agent_type}_agent.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""

# AFTER:
from ..services.prompt_cache import PromptCache

def _load_agent_prompt(agent_type: str, language: str = "en") -> str:
    """Load agent prompt from cache (with file fallback)."""
    cache = PromptCache.get_instance()

    # Try cache first
    prompt_id = f"{agent_type}_agent"
    content = cache.get(prompt_id, language)

    if content:
        return content

    # Fallback to file (for backward compatibility)
    prompt_path = PROMPTS_DIR / f"{agent_type}_agent.txt"
    if prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        # Update cache
        cache.update(prompt_id, language, content)
        return content

    return ""
```

### 5.2 Server Startup (Initialization)

**File**: `app/api/main.py` (additions)

```python
from app.api.services.prompt_config_service import get_prompt_config_service

@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...

    # Initialize prompt cache
    try:
        service = get_prompt_config_service()
        await service.reload_cache()
        logger.info("Prompt cache initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize prompt cache: {e}")
```

### 5.3 Admin Dashboard Tab (Modified)

**File**: `kms-portal-ui/src/pages/AdminDashboardPage.tsx` (additions)

```tsx
import { PromptTab } from '../components/admin/prompts';

// In tab definitions:
const tabs = [
  { id: 'users', label: t('admin.tabs.users'), component: <UsersTab /> },
  { id: 'scoring', label: t('admin.tabs.scoring'), component: <ScoringTab /> },
  { id: 'prompts', label: t('admin.tabs.prompts'), component: <PromptTab /> },  // NEW
  { id: 'enhancements', label: t('admin.tabs.enhancements'), component: <EnhancementsTab /> },
];
```

---

## 6. Migration Script

**File**: `scripts/migrations/001_create_prompt_tables.sql`

```sql
-- Create prompt_configs table
CREATE TABLE IF NOT EXISTS prompt_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'en',
    category VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    content TEXT NOT NULL,
    is_readonly BOOLEAN DEFAULT FALSE,
    source_file VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),
    CONSTRAINT unique_prompt_language UNIQUE (prompt_id, language)
);

CREATE INDEX IF NOT EXISTS idx_prompt_configs_category ON prompt_configs(category);
CREATE INDEX IF NOT EXISTS idx_prompt_configs_prompt_id ON prompt_configs(prompt_id);

-- Create prompt_history table
CREATE TABLE IF NOT EXISTS prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'en',
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    change_reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changed_by UUID REFERENCES users(id),
    CONSTRAINT unique_prompt_version UNIQUE (prompt_id, language, version_number)
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_lookup ON prompt_history(prompt_id, language);
CREATE INDEX IF NOT EXISTS idx_prompt_history_changed_at ON prompt_history(changed_at DESC);
```

---

## 7. Implementation Checklist

### Phase 1: Backend (Priority: Must)
- [ ] Create DB migration script
- [ ] Create `app/api/models/prompt_config.py`
- [ ] Create `app/api/infrastructure/postgres/prompt_config_repository.py`
- [ ] Create `app/api/services/prompt_cache.py`
- [ ] Create `app/api/services/prompt_config_service.py`
- [ ] Create `app/api/routers/admin_prompts.py`
- [ ] Register router in `main.py`
- [ ] Add startup initialization

### Phase 2: Frontend (Priority: Must)
- [ ] Create `kms-portal-ui/src/api/prompts.api.ts`
- [ ] Create `PromptTab` component
- [ ] Create `PromptList` component
- [ ] Create `PromptEditor` component (Monaco)
- [ ] Create `PromptHistory` component
- [ ] Add translations (en, ko, ja)
- [ ] Add tab to Admin Dashboard

### Phase 3: Integration (Priority: Must)
- [ ] Modify `deep_agent_adapter.py` to use cache
- [ ] Modify `rag_agent.py` to use cache
- [ ] Test hot reload functionality
- [ ] Verify readonly protection for master_constraint

### Phase 4: Testing
- [ ] Unit tests for service
- [ ] API endpoint tests
- [ ] Frontend component tests
- [ ] E2E test for prompt editing flow

---

## 8. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Master Constraint modification | `is_readonly=TRUE` flag, backend validation |
| SQL Injection | Parameterized queries in repository |
| XSS in prompt content | Content stored as-is, not rendered as HTML |
| Unauthorized access | Admin role check in all endpoints |
| History tampering | History is append-only, no delete endpoint |

---

## 9. Performance Considerations

| Aspect | Approach |
|--------|----------|
| Prompt loading | In-memory cache (PromptCache singleton) |
| Cache invalidation | Update cache on save, no TTL needed |
| Large prompts | 50KB limit, lazy loading in UI |
| History queries | Index on (prompt_id, language), limit results |

---

## 10. Approval

| Role | Name | Date | Status |
|------|------|------|--------|
| Feature Owner | - | - | Pending |
| Tech Lead | - | - | Pending |
| QA | - | - | Pending |

---

**Next Step**: `/pdca do system-prompting` 으로 구현 시작
