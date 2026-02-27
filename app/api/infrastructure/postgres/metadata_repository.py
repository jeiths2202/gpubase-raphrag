"""
PostgreSQL Metadata Repository
Stores configuration metadata (glossary, document mappings, error codes, synonyms, visual keywords).
Replaces hardcoded values with database-driven configuration.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MetadataRepository:
    """
    Repository for storing metadata configuration in PostgreSQL.
    Tables: domain_glossary, document_mappings, error_code_ranges, synonyms, visual_keywords
    """

    def __init__(self, pool):
        """Initialize with asyncpg connection pool."""
        self._pool = pool
        self._initialized = False

    async def _ensure_tables(self):
        """Create all metadata tables if they don't exist."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            # 1. domain_glossary - 도메인 용어 사전
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_glossary (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    term VARCHAR(100) NOT NULL UNIQUE,
                    full_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(50) DEFAULT 'system',
                    translations JSONB DEFAULT '{}',
                    equivalent_to VARCHAR(255),
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_glossary_term
                ON domain_glossary(term)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_glossary_category
                ON domain_glossary(category)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_glossary_active
                ON domain_glossary(active) WHERE active = TRUE
            """)

            # 2. document_mappings - 키워드-문서 매핑
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_mappings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    keyword VARCHAR(100) NOT NULL,
                    document_pattern VARCHAR(255) NOT NULL,
                    category VARCHAR(50) DEFAULT 'product',
                    priority INT DEFAULT 100,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(keyword, document_pattern)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_mapping_keyword
                ON document_mappings(keyword)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_mapping_active
                ON document_mappings(active) WHERE active = TRUE
            """)

            # 3. error_code_ranges - 에러 코드 범위
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS error_code_ranges (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    module VARCHAR(50) NOT NULL,
                    range_start INT NOT NULL,
                    range_end INT NOT NULL,
                    file_path VARCHAR(255) NOT NULL,
                    category VARCHAR(50),
                    description TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(module, range_start, range_end)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_range_module
                ON error_code_ranges(module)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_range_start
                ON error_code_ranges(range_start)
            """)

            # 4. synonyms - 동의어
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS synonyms (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    base_term VARCHAR(255) NOT NULL,
                    synonym VARCHAR(255) NOT NULL,
                    language VARCHAR(10) NOT NULL,
                    domain VARCHAR(50) DEFAULT 'general',
                    confidence FLOAT DEFAULT 1.0,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(base_term, synonym, language)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_synonyms_base_term
                ON synonyms(base_term)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_synonyms_language
                ON synonyms(language)
            """)

            # 5. visual_keywords - 시각 키워드
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS visual_keywords (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    keyword VARCHAR(100) NOT NULL,
                    language VARCHAR(10) NOT NULL,
                    category VARCHAR(50) DEFAULT 'diagram',
                    weight FLOAT DEFAULT 1.0,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(keyword, language)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_visual_kw_language
                ON visual_keywords(language)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_visual_kw_category
                ON visual_keywords(category)
            """)

            logger.info("Metadata tables initialized (5 tables)")
            self._initialized = True

    # ==================== domain_glossary ====================

    async def get_glossary_terms(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all glossary terms."""
        await self._ensure_tables()

        where = "WHERE active = TRUE" if active_only else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, term, full_name, description, category,
                       translations, equivalent_to, active, created_at, updated_at
                FROM domain_glossary
                {where}
                ORDER BY term
            """)
            return [dict(row) for row in rows]

    async def get_glossary_term(self, term: str) -> Optional[Dict[str, Any]]:
        """Get a single glossary term."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, term, full_name, description, category,
                       translations, equivalent_to, active, created_at, updated_at
                FROM domain_glossary
                WHERE term = $1 AND active = TRUE
            """, term.upper())
            return dict(row) if row else None

    async def add_glossary_term(
        self,
        term: str,
        full_name: str,
        description: str = None,
        category: str = "system",
        translations: Dict[str, str] = None,
        equivalent_to: str = None
    ) -> str:
        """Add a new glossary term. Returns the term."""
        await self._ensure_tables()
        import json

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO domain_glossary
                (term, full_name, description, category, translations, equivalent_to)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (term) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    translations = EXCLUDED.translations,
                    equivalent_to = EXCLUDED.equivalent_to,
                    updated_at = NOW()
            """, term.upper(), full_name, description, category,
                json.dumps(translations or {}), equivalent_to)
        return term.upper()

    async def update_glossary_term(self, term: str, **kwargs) -> bool:
        """Update a glossary term."""
        await self._ensure_tables()
        import json

        updates = ["updated_at = NOW()"]
        params = [term.upper()]
        param_idx = 2

        for key, value in kwargs.items():
            if key in ('full_name', 'description', 'category', 'equivalent_to'):
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
                param_idx += 1
            elif key == 'translations':
                updates.append(f"translations = ${param_idx}::jsonb")
                params.append(json.dumps(value or {}))
                param_idx += 1
            elif key == 'active':
                updates.append(f"active = ${param_idx}")
                params.append(value)
                param_idx += 1

        query = f"UPDATE domain_glossary SET {', '.join(updates)} WHERE term = $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    # ==================== document_mappings ====================

    async def get_document_mappings(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all document mappings."""
        await self._ensure_tables()

        where = "WHERE active = TRUE" if active_only else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, keyword, document_pattern, category, priority,
                       active, created_at, updated_at
                FROM document_mappings
                {where}
                ORDER BY priority, keyword
            """)
            return [dict(row) for row in rows]

    async def get_document_pattern(self, keyword: str) -> Optional[str]:
        """Get document pattern for a keyword."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT document_pattern
                FROM document_mappings
                WHERE keyword = $1 AND active = TRUE
                ORDER BY priority
                LIMIT 1
            """, keyword.upper())
            return row['document_pattern'] if row else None

    async def add_document_mapping(
        self,
        keyword: str,
        document_pattern: str,
        category: str = "product",
        priority: int = 100
    ) -> str:
        """Add a new document mapping."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO document_mappings
                (keyword, document_pattern, category, priority)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (keyword, document_pattern) DO UPDATE SET
                    category = EXCLUDED.category,
                    priority = EXCLUDED.priority,
                    updated_at = NOW()
            """, keyword.upper(), document_pattern, category, priority)
        return keyword.upper()

    # ==================== error_code_ranges ====================

    async def get_error_ranges(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all error code ranges."""
        await self._ensure_tables()

        where = "WHERE active = TRUE" if active_only else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, module, range_start, range_end, file_path,
                       category, description, active, created_at, updated_at
                FROM error_code_ranges
                {where}
                ORDER BY module, range_start
            """)
            return [dict(row) for row in rows]

    async def find_error_range(self, error_code: int) -> Optional[Dict[str, Any]]:
        """Find error range that contains the given error code."""
        await self._ensure_tables()

        # 에러 코드는 절대값으로 검색
        abs_code = abs(error_code)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, module, range_start, range_end, file_path,
                       category, description
                FROM error_code_ranges
                WHERE range_start <= $1 AND range_end >= $1 AND active = TRUE
                LIMIT 1
            """, abs_code)
            return dict(row) if row else None

    async def add_error_range(
        self,
        module: str,
        range_start: int,
        range_end: int,
        file_path: str,
        category: str = None,
        description: str = None
    ) -> str:
        """Add a new error code range."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO error_code_ranges
                (module, range_start, range_end, file_path, category, description)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (module, range_start, range_end) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    updated_at = NOW()
            """, module.upper(), range_start, range_end, file_path, category, description)
        return f"{module.upper()}:{range_start}-{range_end}"

    # ==================== synonyms ====================

    async def get_synonyms(
        self,
        language: str = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get synonyms, optionally filtered by language."""
        await self._ensure_tables()

        conditions = []
        params = []
        param_idx = 1

        if active_only:
            conditions.append("active = TRUE")
        if language:
            conditions.append(f"language = ${param_idx}")
            params.append(language)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, base_term, synonym, language, domain,
                       confidence, active, created_at
                FROM synonyms
                {where}
                ORDER BY base_term, language
            """, *params)
            return [dict(row) for row in rows]

    async def get_synonyms_for_term(
        self,
        base_term: str,
        language: str = None
    ) -> List[str]:
        """Get synonyms for a specific term."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            if language:
                rows = await conn.fetch("""
                    SELECT synonym
                    FROM synonyms
                    WHERE base_term = $1 AND language = $2 AND active = TRUE
                    ORDER BY confidence DESC
                """, base_term.upper(), language)
            else:
                rows = await conn.fetch("""
                    SELECT synonym
                    FROM synonyms
                    WHERE base_term = $1 AND active = TRUE
                    ORDER BY confidence DESC
                """, base_term.upper())
            return [row['synonym'] for row in rows]

    async def add_synonym(
        self,
        base_term: str,
        synonym: str,
        language: str,
        domain: str = "general",
        confidence: float = 1.0
    ) -> str:
        """Add a new synonym."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO synonyms
                (base_term, synonym, language, domain, confidence)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (base_term, synonym, language) DO UPDATE SET
                    domain = EXCLUDED.domain,
                    confidence = EXCLUDED.confidence
            """, base_term.upper(), synonym, language, domain, confidence)
        return f"{base_term.upper()}:{synonym}:{language}"

    # ==================== visual_keywords ====================

    async def get_visual_keywords(
        self,
        language: str = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get visual keywords, optionally filtered by language."""
        await self._ensure_tables()

        conditions = []
        params = []
        param_idx = 1

        if active_only:
            conditions.append("active = TRUE")
        if language:
            conditions.append(f"language = ${param_idx}")
            params.append(language)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, keyword, language, category, weight, active, created_at
                FROM visual_keywords
                {where}
                ORDER BY weight DESC, keyword
            """, *params)
            return [dict(row) for row in rows]

    async def add_visual_keyword(
        self,
        keyword: str,
        language: str,
        category: str = "diagram",
        weight: float = 1.0
    ) -> str:
        """Add a new visual keyword."""
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO visual_keywords
                (keyword, language, category, weight)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (keyword, language) DO UPDATE SET
                    category = EXCLUDED.category,
                    weight = EXCLUDED.weight
            """, keyword, language, category, weight)
        return f"{keyword}:{language}"

    # ==================== Bulk Operations ====================

    async def bulk_insert_glossary(self, terms: List[Dict[str, Any]]) -> int:
        """Bulk insert glossary terms."""
        await self._ensure_tables()
        import json

        count = 0
        async with self._pool.acquire() as conn:
            for term_data in terms:
                await conn.execute("""
                    INSERT INTO domain_glossary
                    (term, full_name, description, category, translations, equivalent_to)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    ON CONFLICT (term) DO NOTHING
                """,
                    term_data['term'].upper(),
                    term_data['full_name'],
                    term_data.get('description'),
                    term_data.get('category', 'system'),
                    json.dumps(term_data.get('translations', {})),
                    term_data.get('equivalent_to')
                )
                count += 1
        return count

    async def bulk_insert_mappings(self, mappings: List[Dict[str, Any]]) -> int:
        """Bulk insert document mappings."""
        await self._ensure_tables()

        count = 0
        async with self._pool.acquire() as conn:
            for mapping in mappings:
                await conn.execute("""
                    INSERT INTO document_mappings
                    (keyword, document_pattern, category, priority)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (keyword, document_pattern) DO NOTHING
                """,
                    mapping['keyword'].upper(),
                    mapping['document_pattern'],
                    mapping.get('category', 'product'),
                    mapping.get('priority', 100)
                )
                count += 1
        return count

    async def bulk_insert_error_ranges(self, ranges: List[Dict[str, Any]]) -> int:
        """Bulk insert error code ranges."""
        await self._ensure_tables()

        count = 0
        async with self._pool.acquire() as conn:
            for r in ranges:
                await conn.execute("""
                    INSERT INTO error_code_ranges
                    (module, range_start, range_end, file_path, category, description)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (module, range_start, range_end) DO NOTHING
                """,
                    r['module'].upper(),
                    r['range_start'],
                    r['range_end'],
                    r['file_path'],
                    r.get('category'),
                    r.get('description')
                )
                count += 1
        return count

    async def bulk_insert_synonyms(self, synonyms: List[Dict[str, Any]]) -> int:
        """Bulk insert synonyms."""
        await self._ensure_tables()

        count = 0
        async with self._pool.acquire() as conn:
            for s in synonyms:
                await conn.execute("""
                    INSERT INTO synonyms
                    (base_term, synonym, language, domain, confidence)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (base_term, synonym, language) DO NOTHING
                """,
                    s['base_term'].upper(),
                    s['synonym'],
                    s['language'],
                    s.get('domain', 'general'),
                    s.get('confidence', 1.0)
                )
                count += 1
        return count

    async def bulk_insert_visual_keywords(self, keywords: List[Dict[str, Any]]) -> int:
        """Bulk insert visual keywords."""
        await self._ensure_tables()

        count = 0
        async with self._pool.acquire() as conn:
            for kw in keywords:
                await conn.execute("""
                    INSERT INTO visual_keywords
                    (keyword, language, category, weight)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (keyword, language) DO NOTHING
                """,
                    kw['keyword'],
                    kw['language'],
                    kw.get('category', 'diagram'),
                    kw.get('weight', 1.0)
                )
                count += 1
        return count


# Singleton instance
_metadata_repository: Optional[MetadataRepository] = None


async def get_metadata_repository() -> MetadataRepository:
    """Get or create metadata repository singleton."""
    global _metadata_repository

    if _metadata_repository is None:
        import asyncpg
        from ...core.config import api_settings

        dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        _metadata_repository = MetadataRepository(pool)
        await _metadata_repository._ensure_tables()
        logger.info("Metadata repository initialized (5 tables)")

    return _metadata_repository
