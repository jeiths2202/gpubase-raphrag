"""
Unit tests for MetadataConfigService and MetadataRepository.
Tests Redis caching behavior, fallback logic, and database operations.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta


class MockCacheService:
    """Mock cache service for testing."""

    def __init__(self):
        self.cache = {}

    async def get(self, key: str):
        return self.cache.get(key)

    async def set(self, key: str, value, ttl=None):
        self.cache[key] = value
        return True

    async def delete(self, key: str):
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    async def exists(self, key: str):
        return key in self.cache

    async def clear_pattern(self, pattern: str):
        # Simple pattern matching for tests
        prefix = pattern.replace("*", "")
        keys_to_delete = [k for k in self.cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del self.cache[key]
        return len(keys_to_delete)

    async def get_ttl(self, key: str):
        return 300 if key in self.cache else None


class TestMetadataConfigService:
    """Tests for MetadataConfigService."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        repo = MagicMock()
        repo.get_glossary_terms = AsyncMock(return_value=[
            {"term": "TJES", "full_name": "Tmax Job Entry Subsystem", "category": "system"},
            {"term": "TACF", "full_name": "Tmax Access Control Facility", "category": "system"},
        ])
        repo.get_glossary_term = AsyncMock(return_value={
            "term": "TJES", "full_name": "Tmax Job Entry Subsystem", "category": "system"
        })
        repo.get_document_mappings = AsyncMock(return_value=[
            {"keyword": "ADRDSSU", "document_pattern": "Utility", "priority": 20},
            {"keyword": "HIDB", "document_pattern": "HiDB", "priority": 10},
        ])
        repo.get_document_pattern = AsyncMock(return_value="Utility")
        repo.find_error_range = AsyncMock(return_value={
            "module": "BASE", "range_start": 5000, "range_end": 5999, "file_path": "BASE-5000.md"
        })
        repo.get_error_ranges = AsyncMock(return_value=[
            {"module": "BASE", "range_start": 5000, "range_end": 5999, "file_path": "BASE-5000.md"},
        ])
        repo.get_synonyms = AsyncMock(return_value=[
            {"base_term": "DATASET", "synonym": "データセット", "language": "ja"},
        ])
        repo.get_synonyms_for_term = AsyncMock(return_value=["データセット"])
        repo.get_visual_keywords = AsyncMock(return_value=[
            {"keyword": "図", "language": "ja", "weight": 1.0},
            {"keyword": "プロセス図", "language": "ja", "weight": 1.2},
        ])
        return repo

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache service."""
        return MockCacheService()

    @pytest.fixture
    def service(self, mock_repository, mock_cache):
        """Create service with mock repository and cache."""
        from app.api.services.metadata_config_service import MetadataConfigService
        svc = MetadataConfigService(mock_repository)
        svc._cache = mock_cache  # Inject mock cache
        return svc

    @pytest.mark.asyncio
    async def test_get_glossary_term(self, service, mock_repository):
        """Test getting a single glossary term."""
        result = await service.get_glossary_term("TJES")
        assert result is not None
        assert result["term"] == "TJES"
        mock_repository.get_glossary_term.assert_called_once_with("TJES")

    @pytest.mark.asyncio
    async def test_get_glossary_term_fallback(self, service, mock_repository):
        """Test fallback when DB lookup fails."""
        mock_repository.get_glossary_term.side_effect = Exception("DB error")
        result = await service.get_glossary_term("TJES")
        assert result is not None
        assert result["full_name"] == "Tmax Job Entry Subsystem"

    @pytest.mark.asyncio
    async def test_get_all_glossary_terms_caching(self, service, mock_repository, mock_cache):
        """Test that glossary terms are cached in Redis."""
        # First call - should hit DB
        result1 = await service.get_all_glossary_terms()
        assert len(result1) == 2
        assert mock_repository.get_glossary_terms.call_count == 1

        # Verify data is in cache
        cache_key = f"{service.CACHE_PREFIX}glossary_all"
        assert cache_key in mock_cache.cache

        # Second call - should use cache
        result2 = await service.get_all_glossary_terms()
        assert len(result2) == 2
        assert mock_repository.get_glossary_terms.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_get_document_pattern(self, service, mock_repository):
        """Test getting document pattern for keyword."""
        result = await service.get_document_pattern("ADRDSSU")
        assert result == "Utility"
        mock_repository.get_document_pattern.assert_called_once_with("ADRDSSU")

    @pytest.mark.asyncio
    async def test_get_document_pattern_fallback(self, service, mock_repository):
        """Test fallback when DB lookup fails."""
        mock_repository.get_document_pattern.side_effect = Exception("DB error")
        result = await service.get_document_pattern("HIDB")
        assert result == "HiDB"  # From fallback

    @pytest.mark.asyncio
    async def test_get_error_file(self, service, mock_repository):
        """Test getting error file for error code."""
        result = await service.get_error_file(-5212)
        assert result == "BASE-5000.md"
        mock_repository.find_error_range.assert_called_once_with(-5212)

    @pytest.mark.asyncio
    async def test_is_visual_keyword(self, service, mock_repository):
        """Test visual keyword detection."""
        is_visual, weight = await service.is_visual_keyword("プロセス図を見せて")
        assert is_visual is True
        assert weight == 1.2  # プロセス図 has weight 1.2

    @pytest.mark.asyncio
    async def test_is_visual_keyword_not_found(self, service, mock_repository):
        """Test when no visual keyword found."""
        mock_repository.get_visual_keywords.return_value = []
        is_visual, weight = await service.is_visual_keyword("普通のテキスト")
        assert is_visual is False
        assert weight == 0.0

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, service, mock_repository, mock_cache):
        """Test Redis cache invalidation."""
        # Load data into cache
        await service.get_all_glossary_terms()
        cache_key = f"{service.CACHE_PREFIX}glossary_all"
        assert cache_key in mock_cache.cache

        # Invalidate specific cache
        await service.invalidate("glossary")
        assert cache_key not in mock_cache.cache

    @pytest.mark.asyncio
    async def test_cache_refresh(self, service, mock_repository, mock_cache):
        """Test cache refresh clears and reloads."""
        # Load data into cache
        await service.get_all_glossary_terms()
        assert len(mock_cache.cache) > 0

        # Refresh cache
        await service.refresh_cache()

        # Cache should be repopulated
        mock_repository.get_glossary_terms.assert_called()
        mock_repository.get_document_mappings.assert_called()
        mock_repository.get_error_ranges.assert_called()

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, service, mock_cache):
        """Test cache statistics for Redis."""
        # Load some data
        await service.get_all_glossary_terms()

        stats = await service.get_cache_stats()
        assert stats["cache_type"] == "MockCacheService"
        assert stats["cache_prefix"] == "metadata:"
        assert stats["ttl_seconds"] == 300
        assert "keys_status" in stats


class TestMetadataRepository:
    """Tests for MetadataRepository."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="INSERT 1")
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=1)

        # Context manager for pool.acquire()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        return pool

    @pytest.fixture
    def repository(self, mock_pool):
        """Create repository with mock pool."""
        from app.api.infrastructure.postgres.metadata_repository import MetadataRepository
        repo = MetadataRepository(mock_pool)
        repo._initialized = True  # Skip table creation
        return repo

    @pytest.mark.asyncio
    async def test_get_glossary_terms(self, repository, mock_pool):
        """Test getting glossary terms."""
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetch.return_value = [
            {"id": "1", "term": "TJES", "full_name": "Tmax Job Entry Subsystem",
             "description": None, "category": "system", "translations": {},
             "equivalent_to": "JES2", "active": True,
             "created_at": None, "updated_at": None}
        ]

        result = await repository.get_glossary_terms()
        assert len(result) == 1
        assert result[0]["term"] == "TJES"

    @pytest.mark.asyncio
    async def test_add_glossary_term(self, repository, mock_pool):
        """Test adding glossary term."""
        result = await repository.add_glossary_term(
            term="NEWTERM",
            full_name="New Term Full Name",
            description="A new term",
            category="system"
        )
        assert result == "NEWTERM"

    @pytest.mark.asyncio
    async def test_find_error_range(self, repository, mock_pool):
        """Test finding error range."""
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            "id": "1", "module": "BASE", "range_start": 5000, "range_end": 5999,
            "file_path": "BASE-5000.md", "category": "allocation", "description": None
        }

        result = await repository.find_error_range(-5212)
        assert result is not None
        assert result["module"] == "BASE"
        assert result["file_path"] == "BASE-5000.md"

    @pytest.mark.asyncio
    async def test_bulk_insert_glossary(self, repository, mock_pool):
        """Test bulk insert of glossary terms."""
        terms = [
            {"term": "TERM1", "full_name": "Term One"},
            {"term": "TERM2", "full_name": "Term Two"},
        ]
        count = await repository.bulk_insert_glossary(terms)
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_visual_keywords(self, repository, mock_pool):
        """Test getting visual keywords."""
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetch.return_value = [
            {"id": "1", "keyword": "図", "language": "ja",
             "category": "diagram", "weight": 1.0, "active": True, "created_at": None}
        ]

        result = await repository.get_visual_keywords(language="ja")
        assert len(result) == 1
        assert result[0]["keyword"] == "図"


# Integration test placeholder
class TestMetadataIntegration:
    """Integration tests (require actual database)."""

    @pytest.mark.skip(reason="Requires actual database connection")
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow with actual database."""
        from app.api.services.metadata_config_service import get_metadata_config_service

        service = await get_metadata_config_service()

        # Test glossary
        glossary = await service.get_all_glossary_terms()
        assert len(glossary) > 0

        # Test document mapping
        pattern = await service.get_document_pattern("ADRDSSU")
        assert pattern == "Utility"

        # Test error code
        error_file = await service.get_error_file(-5212)
        assert error_file is not None

        # Test visual keywords
        is_visual, weight = await service.is_visual_keyword("プロセス図を見せて")
        assert is_visual is True
