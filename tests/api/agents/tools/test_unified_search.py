"""
Tests for Unified Search Tool.

Tests:
- Query validation (LLM corruption recovery)
- Error code extraction patterns
- RRF (Reciprocal Rank Fusion) score calculation
- Structure enrichment (tables, images)
- End-to-end hybrid search
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.api.agents.tools.unified_search import UnifiedSearchTool
from app.api.agents.tools.adaptive_search import _validate_query, _extract_error_codes
from app.api.agents.types import AgentContext


class TestQueryValidation:
    """Test query validation and LLM corruption recovery."""

    def test_identical_query_no_corruption(self):
        """Query identical to original should not be flagged as corrupted."""
        query = "TIBERO-1234 에러 해결 방법"
        original = "TIBERO-1234 에러 해결 방법"
        validated, was_corrupted = _validate_query(query, original)
        assert validated == query
        assert was_corrupted is False

    def test_japanese_corruption_detection(self):
        """Detect Japanese to Chinese character substitution."""
        # LLM sometimes substitutes Japanese characters with Chinese
        query = "图面機成"  # Corrupted (Chinese)
        original = "画面構成"  # Original (Japanese)
        validated, was_corrupted = _validate_query(query, original)
        assert validated == original
        assert was_corrupted is True

    def test_korean_preserved(self):
        """Korean text should be preserved without corruption detection."""
        query = "사용자 인증 방법"
        original = "사용자 인증 방법"
        validated, was_corrupted = _validate_query(query, original)
        assert validated == query
        assert was_corrupted is False

    def test_truncation_detection(self):
        """Detect when query is significantly truncated."""
        query = "에러"
        original = "TIBERO-1234 에러 코드 발생 시 해결 방법을 알려주세요"
        validated, was_corrupted = _validate_query(query, original)
        assert validated == original
        assert was_corrupted is True

    def test_empty_query_uses_original(self):
        """Empty query should use original."""
        query = ""
        original = "검색 쿼리"
        validated, was_corrupted = _validate_query(query, original)
        assert validated == original
        assert was_corrupted is False

    def test_both_empty_returns_empty(self):
        """Both empty should return empty without corruption."""
        validated, was_corrupted = _validate_query("", "")
        assert validated == ""
        assert was_corrupted is False


class TestErrorCodeExtraction:
    """Test error code pattern detection."""

    def test_named_error_code(self):
        """Detect named error codes like DSALC_ERR_*."""
        query = "DSALC_ERR_DATASET_NOT_FOUND 오류가 발생했습니다"
        codes = _extract_error_codes(query)
        assert "DSALC_ERR_DATASET_NOT_FOUND" in codes

    def test_standard_format_error_code(self):
        """Detect standard format like TIBERO-1234."""
        query = "TIBERO-5212 에러 해결 방법"
        codes = _extract_error_codes(query)
        assert "TIBERO-5212" in codes

    def test_numeric_error_with_context(self):
        """Detect numeric codes when error context is present."""
        query = "에러 코드 -5212가 발생했습니다"
        codes = _extract_error_codes(query)
        assert "-5212" in codes

    def test_numeric_error_without_context(self):
        """Numeric codes without error context should not be extracted."""
        query = "값이 -5212입니다"  # No error context
        codes = _extract_error_codes(query)
        assert "-5212" not in codes

    def test_multiple_error_codes(self):
        """Detect multiple error codes in same query."""
        query = "OFM-1234 또는 TIBERO-5678 에러 발생 시 조치 방법"
        codes = _extract_error_codes(query)
        assert "OFM-1234" in codes
        assert "TIBERO-5678" in codes

    def test_japanese_error_context(self):
        """Detect error codes with Japanese context."""
        query = "エラーコード -5212 の対処方法"
        codes = _extract_error_codes(query)
        assert "-5212" in codes

    def test_no_error_codes(self):
        """Return empty list when no error codes present."""
        query = "시스템 구성 방법을 알려주세요"
        codes = _extract_error_codes(query)
        assert codes == []


class TestRRFFusion:
    """Test Reciprocal Rank Fusion score calculation."""

    @pytest.fixture
    def unified_tool(self):
        return UnifiedSearchTool()

    def test_rrf_basic_calculation(self, unified_tool):
        """Test basic RRF score calculation."""
        neo4j_results = [
            {"chunk_id": "chunk1", "content": "Test content 1", "rank": 1},
            {"chunk_id": "chunk2", "content": "Test content 2", "rank": 2},
        ]
        postgres_results = [
            {"chunk_id": "chunk2", "content": "Test content 2", "rank": 1},
            {"chunk_id": "chunk3", "content": "Test content 3", "rank": 2},
        ]

        fused = unified_tool._rrf_fusion(neo4j_results, postgres_results, [], k=60)

        # chunk2 should have highest score (appears in both)
        assert len(fused) == 3
        chunk2 = next(c for c in fused if c["chunk_id"] == "chunk2")
        chunk1 = next(c for c in fused if c["chunk_id"] == "chunk1")
        assert chunk2["rrf_score"] > chunk1["rrf_score"]

    def test_rrf_error_boost(self, unified_tool):
        """Test error code boosting in RRF."""
        neo4j_results = [
            {"chunk_id": "chunk1", "content": "Normal content", "rank": 1},
            {"chunk_id": "chunk2", "content": "Content with TIBERO-5212 error", "rank": 2},
        ]

        fused = unified_tool._rrf_fusion(neo4j_results, [], ["TIBERO-5212"], k=60)

        chunk_with_error = next(c for c in fused if c["chunk_id"] == "chunk2")
        chunk_normal = next(c for c in fused if c["chunk_id"] == "chunk1")

        # Error-boosted chunk should have higher score despite lower rank
        assert chunk_with_error["error_boosted"] is True
        # Boosted chunk2 (rank 2 * 1.5) should beat normal chunk1 (rank 1)
        # RRF score for rank 1: 1/(60+1) = 0.0164
        # RRF score for rank 2 with boost: 1/(60+2) * 1.5 = 0.0242
        assert chunk_with_error["rrf_score"] > chunk_normal["rrf_score"]

    def test_rrf_empty_inputs(self, unified_tool):
        """Test RRF with empty inputs."""
        fused = unified_tool._rrf_fusion([], [], [])
        assert fused == []

    def test_rrf_only_neo4j(self, unified_tool):
        """Test RRF with only Neo4j results."""
        neo4j_results = [
            {"chunk_id": "chunk1", "content": "Test", "rank": 1},
        ]
        fused = unified_tool._rrf_fusion(neo4j_results, [], [], k=60)
        assert len(fused) == 1
        assert fused[0]["neo4j_rank"] == 1
        assert fused[0]["postgres_rank"] == 999


class TestMarkdownTableFix:
    """Test markdown table separator fixing."""

    @pytest.fixture
    def unified_tool(self):
        return UnifiedSearchTool()

    def test_add_missing_separator(self, unified_tool):
        """Add separator when missing."""
        content = """| Header 1 | Header 2 |
| Data 1 | Data 2 |"""
        fixed = unified_tool._fix_markdown_table_separators(content)
        assert "| --- |" in fixed

    def test_preserve_existing_separator(self, unified_tool):
        """Don't add separator when already present."""
        content = """| Header 1 | Header 2 |
| --- | --- |
| Data 1 | Data 2 |"""
        fixed = unified_tool._fix_markdown_table_separators(content)
        # Should only have one separator line
        assert fixed.count("---") == 2  # Two columns

    def test_consolidate_scattered_rows(self, unified_tool):
        """Remove empty lines within table."""
        content = """| Header 1 | Header 2 |

| Data 1 | Data 2 |

| Data 3 | Data 4 |"""
        fixed = unified_tool._fix_markdown_table_separators(content)
        lines = [l for l in fixed.split('\n') if l.strip()]
        # Should have header + separator + 2 data rows = 4 lines
        table_lines = [l for l in lines if l.strip().startswith('|')]
        assert len(table_lines) == 4


class TestUnifiedSearchExecution:
    """Test unified search execution."""

    @pytest.fixture
    def unified_tool(self):
        return UnifiedSearchTool()

    @pytest.fixture
    def context(self):
        return AgentContext(
            user_id="test_user",
            session_id="test_session",
            max_steps=5,
            metadata={"original_query": "TIBERO-5212 에러 해결"}
        )

    @pytest.mark.asyncio
    async def test_empty_query_error(self, unified_tool, context):
        """Empty query should return error."""
        result = await unified_tool.execute(context, query="")
        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_query_validation_applied(self, unified_tool, context):
        """Query validation should fix corrupted queries."""
        # Set up context with original query
        context.metadata["original_query"] = "화면構成"

        with patch.object(unified_tool, '_neo4j_vector_search', new_callable=AsyncMock) as mock_neo4j:
            with patch.object(unified_tool, '_postgres_keyword_search', new_callable=AsyncMock) as mock_pg:
                mock_neo4j.return_value = []
                mock_pg.return_value = []

                # Pass corrupted query
                result = await unified_tool.execute(context, query="图面機成")

                # The tool should use corrected query for search
                # (check via metadata if query was corrected)
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_hybrid_mode_calls_both_sources(self, unified_tool, context):
        """Hybrid mode should call both Neo4j and PostgreSQL."""
        with patch.object(unified_tool, '_neo4j_vector_search', new_callable=AsyncMock) as mock_neo4j:
            with patch.object(unified_tool, '_postgres_keyword_search', new_callable=AsyncMock) as mock_pg:
                mock_neo4j.return_value = [
                    {"chunk_id": "neo1", "content": "Test", "rank": 1, "doc_id": "doc1"}
                ]
                mock_pg.return_value = [
                    {"chunk_id": "pg1", "content": "Test", "rank": 1, "pdf_id": "doc1"}
                ]

                result = await unified_tool.execute(
                    context,
                    query="test query",
                    search_mode="hybrid"
                )

                mock_neo4j.assert_called_once()
                mock_pg.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_only_mode(self, unified_tool, context):
        """Vector only mode should only call Neo4j."""
        with patch.object(unified_tool, '_neo4j_vector_search', new_callable=AsyncMock) as mock_neo4j:
            with patch.object(unified_tool, '_postgres_keyword_search', new_callable=AsyncMock) as mock_pg:
                mock_neo4j.return_value = [
                    {"chunk_id": "neo1", "content": "Test", "rank": 1, "doc_id": "doc1"}
                ]

                result = await unified_tool.execute(
                    context,
                    query="test query",
                    search_mode="vector_only"
                )

                mock_neo4j.assert_called_once()
                mock_pg.assert_not_called()

    @pytest.mark.asyncio
    async def test_keyword_only_mode(self, unified_tool, context):
        """Keyword only mode should only call PostgreSQL."""
        with patch.object(unified_tool, '_neo4j_vector_search', new_callable=AsyncMock) as mock_neo4j:
            with patch.object(unified_tool, '_postgres_keyword_search', new_callable=AsyncMock) as mock_pg:
                mock_pg.return_value = [
                    {"chunk_id": "pg1", "content": "Test", "rank": 1, "pdf_id": "doc1"}
                ]

                result = await unified_tool.execute(
                    context,
                    query="test query",
                    search_mode="keyword_only"
                )

                mock_neo4j.assert_not_called()
                mock_pg.assert_called_once()


class TestToolRegistration:
    """Test that UnifiedSearchTool is properly registered."""

    def test_import_unified_search(self):
        """UnifiedSearchTool should be importable."""
        from app.api.agents.tools import UnifiedSearchTool
        tool = UnifiedSearchTool()
        assert tool.name == "unified_search"

    def test_registry_has_unified_search(self):
        """ToolRegistry should include unified_search."""
        from app.api.agents.registry import ToolRegistry
        registry = ToolRegistry.get_instance()
        tool = registry.get("unified_search")
        assert tool is not None
        assert tool.name == "unified_search"

    def test_rag_agent_tools_include_unified_search(self):
        """RAG agent should have unified_search in its tools."""
        from app.api.agents.registry import ToolRegistry
        from app.api.agents.types import AgentType
        registry = ToolRegistry.get_instance()
        tools = registry.get_tools_for_agent(AgentType.RAG)
        tool_names = [t.name for t in tools]
        assert "unified_search" in tool_names

    def test_get_tool_by_name(self):
        """get_tool_by_name should return UnifiedSearchTool."""
        from app.api.agents.tools import get_tool_by_name
        tool = get_tool_by_name("unified_search")
        assert tool.name == "unified_search"


class TestLangChainWrapper:
    """Test LangChain tool wrapper for Deep Agents."""

    def test_unified_search_langchain_tool_created(self):
        """LangChain tool should be created successfully."""
        try:
            from app.api.agents.middleware.rag_tools import RAGToolsProvider
            provider = RAGToolsProvider()
            lc_tool = provider._create_unified_search_tool()

            assert lc_tool is not None
            assert lc_tool.name == "unified_search"
            assert "PRIMARY" in lc_tool.description
        except ImportError:
            pytest.skip("LangChain not available")

    def test_get_rag_tools_includes_unified_search(self):
        """get_rag_tools should include unified_search."""
        try:
            from app.api.agents.middleware.rag_tools import get_rag_tools
            tools = get_rag_tools()
            tool_names = [t.name for t in tools]
            assert "unified_search" in tool_names
        except ImportError:
            pytest.skip("LangChain not available")
