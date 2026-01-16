"""
Tests for Query Expansion Service
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.api.services.query_expansion_service import (
    QueryExpansionService,
    get_query_expansion_service,
    ExpandedQuery
)


class TestQueryExpansionService:
    """Test suite for QueryExpansionService"""

    @pytest.fixture
    def service(self):
        """Create a fresh service instance for each test"""
        return QueryExpansionService()

    # ==========================================================================
    # Japanese Query Expansion Tests
    # ==========================================================================

    def test_expand_japanese_procedure(self, service):
        """Test expansion of Japanese procedure terms"""
        result = service.expand("MFS処理手順", "ja")

        assert result.original == "MFS処理手順"
        assert "処理順序" in result.all_terms
        assert "処理フロー" in result.all_terms
        assert "手順" in result.all_terms

    def test_expand_japanese_order(self, service):
        """Test expansion of Japanese order/sequence terms"""
        result = service.expand("処理順序", "ja")

        assert "処理手順" in result.all_terms
        assert "フロー" in result.all_terms

    def test_expand_japanese_error(self, service):
        """Test expansion of Japanese error terms"""
        result = service.expand("エラー対処", "ja")

        assert "障害" in result.all_terms
        assert "問題" in result.all_terms

    def test_expand_japanese_structure(self, service):
        """Test expansion of Japanese structure terms"""
        result = service.expand("MFS構造", "ja")

        assert "構成" in result.all_terms
        assert "仕組み" in result.all_terms

    # ==========================================================================
    # Korean Query Expansion Tests
    # ==========================================================================

    def test_expand_korean_procedure(self, service):
        """Test expansion of Korean procedure terms"""
        result = service.expand("처리절차", "ko")

        assert "처리순서" in result.all_terms
        assert "처리흐름" in result.all_terms
        assert "절차" in result.all_terms

    def test_expand_korean_error(self, service):
        """Test expansion of Korean error terms"""
        result = service.expand("오류처리", "ko")

        assert "에러" in result.all_terms
        assert "문제" in result.all_terms

    # ==========================================================================
    # English Query Expansion Tests
    # ==========================================================================

    def test_expand_english_procedure(self, service):
        """Test expansion of English procedure terms"""
        result = service.expand("processing procedure", "en")

        assert "process" in result.all_terms
        assert "steps" in result.all_terms
        assert "flow" in result.all_terms

    def test_expand_english_error(self, service):
        """Test expansion of English error terms"""
        result = service.expand("error handling", "en")

        assert "issue" in result.all_terms
        assert "problem" in result.all_terms

    # ==========================================================================
    # Technical Term Expansion Tests
    # ==========================================================================

    def test_expand_mfs_technical(self, service):
        """Test expansion of MFS technical term"""
        result = service.expand("MFS定義", "ja")

        assert "Message Format Service" in result.all_terms
        assert "MFSメッセージフォーマット" in result.all_terms

    def test_expand_ims_technical(self, service):
        """Test expansion of IMS technical term"""
        result = service.expand("IMS設定", "ja")

        assert "Information Management System" in result.all_terms

    def test_expand_mid_technical(self, service):
        """Test expansion of MID technical term"""
        result = service.expand("MID定義", "ja")

        assert "Message Input Descriptor" in result.all_terms

    # ==========================================================================
    # Language Detection Tests
    # ==========================================================================

    def test_detect_japanese(self, service):
        """Test Japanese language detection"""
        result = service.expand("処理手順", "auto")
        assert result.language == "ja"

    def test_detect_korean(self, service):
        """Test Korean language detection"""
        result = service.expand("처리절차", "auto")
        assert result.language == "ko"

    def test_detect_english(self, service):
        """Test English language detection"""
        result = service.expand("processing procedure", "auto")
        assert result.language == "en"

    # ==========================================================================
    # Expanded Query Generation Tests
    # ==========================================================================

    def test_get_expanded_query(self, service):
        """Test expanded query generation"""
        result = service.expand("MFS処理手順", "ja")

        expanded_query = result.get_expanded_query()
        # Should contain original query
        assert "MFS処理手順" in expanded_query
        # Should contain some expanded terms
        assert len(expanded_query) > len("MFS処理手順")

    def test_get_expanded_query_no_expansion(self, service):
        """Test expanded query when no synonyms found"""
        result = service.expand("xyz123abc", "en")

        expanded_query = result.get_expanded_query()
        # Should return original when no expansions
        assert expanded_query == "xyz123abc"

    # ==========================================================================
    # Edge Cases
    # ==========================================================================

    def test_empty_query(self, service):
        """Test with empty query"""
        result = service.expand("", "ja")

        assert result.original == ""
        assert "" in result.all_terms

    def test_no_duplicate_terms(self, service):
        """Test that expanded terms have no duplicates"""
        result = service.expand("処理手順と処理順序", "ja")

        # Check no duplicates in expanded_terms
        assert len(result.expanded_terms) == len(set(result.expanded_terms))

    # ==========================================================================
    # Singleton Tests
    # ==========================================================================

    def test_singleton(self):
        """Test that get_query_expansion_service returns singleton"""
        service1 = get_query_expansion_service()
        service2 = get_query_expansion_service()

        assert service1 is service2


class TestExpandedQuery:
    """Test suite for ExpandedQuery dataclass"""

    def test_expanded_query_creation(self):
        """Test ExpandedQuery creation"""
        result = ExpandedQuery(
            original="test",
            expanded_terms=["term1", "term2"],
            all_terms={"test", "term1", "term2"},
            language="en"
        )

        assert result.original == "test"
        assert result.expanded_terms == ["term1", "term2"]
        assert len(result.all_terms) == 3

    def test_get_expanded_query_with_terms(self):
        """Test get_expanded_query with expanded terms"""
        result = ExpandedQuery(
            original="query",
            expanded_terms=["a", "b", "c", "d"],
            all_terms={"query", "a", "b", "c", "d"},
            language="en"
        )

        expanded = result.get_expanded_query()
        # Should include original + top 3 terms
        assert "query" in expanded
        assert "a" in expanded
        assert "b" in expanded
        assert "c" in expanded


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
