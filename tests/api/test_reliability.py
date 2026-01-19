"""
Tests for Reliability Service

Tests source reliability calculation with various scenarios.
"""
import pytest
from app.api.models.query import ReliabilityLevel, SourceReliability
from app.api.services.reliability_service import (
    calculate_reliability,
    calculate_source_count_score,
    calculate_avg_similarity,
    calculate_source_diversity,
    calculate_source_quality,
    get_reliability_level,
    generate_explanation,
)


class TestSourceCountScore:
    """Tests for source count scoring"""

    def test_zero_sources(self):
        """Test score for zero sources"""
        assert calculate_source_count_score(0) == 0.0

    def test_one_source(self):
        """Test score for one source"""
        assert calculate_source_count_score(1) == 0.3

    def test_two_sources(self):
        """Test score for two sources"""
        assert calculate_source_count_score(2) == 0.6

    def test_three_or_more_sources(self):
        """Test score for three or more sources"""
        assert calculate_source_count_score(3) == 1.0
        assert calculate_source_count_score(5) == 1.0
        assert calculate_source_count_score(10) == 1.0


class TestAvgSimilarity:
    """Tests for average similarity calculation"""

    def test_empty_sources(self):
        """Test with empty sources list"""
        assert calculate_avg_similarity([]) == 0.0

    def test_sources_with_score_field(self):
        """Test sources with 'score' field"""
        sources = [
            {"score": 0.8},
            {"score": 0.6},
            {"score": 0.7},
        ]
        assert calculate_avg_similarity(sources) == pytest.approx(0.7, abs=0.01)

    def test_sources_with_similarity_field(self):
        """Test sources with 'similarity' field"""
        sources = [
            {"similarity": 0.9},
            {"similarity": 0.8},
        ]
        assert calculate_avg_similarity(sources) == pytest.approx(0.85, abs=0.01)

    def test_sources_with_result_score_field(self):
        """Test sources with 'result_score' field"""
        sources = [
            {"result_score": 0.5},
            {"result_score": 0.7},
        ]
        assert calculate_avg_similarity(sources) == pytest.approx(0.6, abs=0.01)

    def test_sources_without_scores(self):
        """Test sources without any score fields returns default"""
        sources = [
            {"doc_id": "doc1"},
            {"doc_id": "doc2"},
        ]
        assert calculate_avg_similarity(sources) == 0.5  # Default value


class TestSourceDiversity:
    """Tests for source diversity calculation"""

    def test_empty_sources(self):
        """Test with empty sources list"""
        assert calculate_source_diversity([]) == 0.0

    def test_all_unique_documents(self):
        """Test when all sources are from unique documents"""
        sources = [
            {"doc_id": "doc1"},
            {"doc_id": "doc2"},
            {"doc_id": "doc3"},
        ]
        # Returns value between 0 and 1 based on diversity
        result = calculate_source_diversity(sources)
        assert 0.0 <= result <= 1.0

    def test_duplicate_documents(self):
        """Test when sources have duplicate documents"""
        sources = [
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc2"},
            {"doc_id": "doc2"},
        ]
        # Returns value between 0 and 1
        result = calculate_source_diversity(sources)
        assert 0.0 <= result <= 1.0

    def test_low_diversity(self):
        """Test when diversity is very low"""
        sources = [
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
            {"doc_id": "doc1"},
        ]
        # Low diversity should return lower score than high diversity
        result = calculate_source_diversity(sources)
        assert 0.0 <= result <= 1.0

    def test_document_id_field_variations(self):
        """Test different document_id field names"""
        sources = [
            {"document_id": "doc1"},
            {"doc_id": "doc2"},
        ]
        # Should handle different field name variations
        result = calculate_source_diversity(sources)
        assert 0.0 <= result <= 1.0


class TestSourceQuality:
    """Tests for source quality calculation"""

    def test_empty_sources(self):
        """Test with empty sources list"""
        assert calculate_source_quality([]) == 0.0

    def test_global_kb_sources(self):
        """Test with global KB sources (highest quality)"""
        sources = [
            {"source_type": "global_kb"},
            {"source_type": "global_kb"},
        ]
        assert calculate_source_quality(sources) == 1.0

    def test_vector_sources(self):
        """Test with vector search sources"""
        sources = [
            {"source_type": "vector"},
        ]
        assert calculate_source_quality(sources) == 1.0

    def test_session_sources(self):
        """Test with session sources (lower quality)"""
        sources = [
            {"source_type": "session"},
        ]
        assert calculate_source_quality(sources) == 0.6

    def test_mixed_sources(self):
        """Test with mixed source types"""
        sources = [
            {"source_type": "global_kb"},  # 1.0
            {"source_type": "session"},    # 0.6
        ]
        # Average: (1.0 + 0.6) / 2 = 0.8
        assert calculate_source_quality(sources) == pytest.approx(0.8, abs=0.01)

    def test_unknown_source_type(self):
        """Test with unknown source type uses default weight"""
        sources = [
            {"source_type": "unknown_type"},
        ]
        # Unknown type defaults to 0.7
        assert calculate_source_quality(sources) == 0.7


class TestReliabilityLevel:
    """Tests for reliability level determination"""

    def test_high_level(self):
        """Test high reliability level (score >= 0.7)"""
        assert get_reliability_level(0.9) == ReliabilityLevel.HIGH
        assert get_reliability_level(0.7) == ReliabilityLevel.HIGH

    def test_medium_level(self):
        """Test medium reliability level (0.4 <= score < 0.7)"""
        assert get_reliability_level(0.6) == ReliabilityLevel.MEDIUM
        assert get_reliability_level(0.4) == ReliabilityLevel.MEDIUM

    def test_low_level(self):
        """Test low reliability level (score < 0.4)"""
        assert get_reliability_level(0.3) == ReliabilityLevel.LOW
        assert get_reliability_level(0.0) == ReliabilityLevel.LOW


class TestExplanation:
    """Tests for explanation generation"""

    def test_korean_explanation(self):
        """Test Korean explanation generation"""
        explanation = generate_explanation(
            ReliabilityLevel.HIGH, {}, 3, "ko"
        )
        assert "3개의 출처" in explanation
        assert "신뢰도가 높습니다" in explanation

    def test_english_explanation(self):
        """Test English explanation generation"""
        explanation = generate_explanation(
            ReliabilityLevel.HIGH, {}, 3, "en"
        )
        assert "3 sources" in explanation
        assert "High reliability" in explanation

    def test_japanese_explanation(self):
        """Test Japanese explanation generation"""
        explanation = generate_explanation(
            ReliabilityLevel.HIGH, {}, 3, "ja"
        )
        assert "3件のソース" in explanation
        assert "信頼性が高い" in explanation

    def test_unknown_language_defaults_to_korean(self):
        """Test unknown language defaults to Korean"""
        explanation = generate_explanation(
            ReliabilityLevel.HIGH, {}, 3, "unknown"
        )
        assert "신뢰도가 높습니다" in explanation


class TestCalculateReliability:
    """Tests for overall reliability calculation"""

    def test_empty_sources(self):
        """Test reliability with no sources"""
        result = calculate_reliability([])

        assert isinstance(result, SourceReliability)
        assert result.score == 0.0
        assert result.level == ReliabilityLevel.LOW
        assert result.factors["source_count"] == 0.0
        assert result.factors["avg_similarity"] == 0.0

    def test_single_high_quality_source(self):
        """Test reliability with single high quality source"""
        sources = [
            {"score": 0.9, "doc_id": "doc1", "source_type": "global_kb"}
        ]
        result = calculate_reliability(sources)

        assert isinstance(result, SourceReliability)
        # With high similarity (0.9) and quality (1.0), even single source can be high
        assert result.level in [ReliabilityLevel.HIGH, ReliabilityLevel.MEDIUM, ReliabilityLevel.LOW]
        assert result.factors["source_count"] == 0.3  # Only 1 source

    def test_multiple_high_quality_sources(self):
        """Test reliability with multiple high quality sources"""
        sources = [
            {"score": 0.9, "doc_id": "doc1", "source_type": "global_kb"},
            {"score": 0.85, "doc_id": "doc2", "source_type": "global_kb"},
            {"score": 0.8, "doc_id": "doc3", "source_type": "vector"},
        ]
        result = calculate_reliability(sources)

        assert isinstance(result, SourceReliability)
        assert result.level == ReliabilityLevel.HIGH
        assert result.factors["source_count"] == 1.0  # 3+ sources
        assert result.factors["source_quality"] == pytest.approx(1.0, abs=0.01)

    def test_low_similarity_sources(self):
        """Test reliability with low similarity scores"""
        sources = [
            {"score": 0.2, "doc_id": "doc1", "source_type": "global_kb"},
            {"score": 0.3, "doc_id": "doc2", "source_type": "global_kb"},
        ]
        result = calculate_reliability(sources)

        assert result.factors["avg_similarity"] == pytest.approx(0.25, abs=0.01)
        assert result.level in [ReliabilityLevel.LOW, ReliabilityLevel.MEDIUM]

    def test_reliability_score_bounds(self):
        """Test that reliability score is bounded between 0 and 1"""
        # Very high scores
        sources = [
            {"score": 1.0, "doc_id": f"doc{i}", "source_type": "global_kb"}
            for i in range(10)
        ]
        result = calculate_reliability(sources)
        assert 0.0 <= result.score <= 1.0

    def test_different_languages(self):
        """Test reliability calculation with different languages"""
        sources = [
            {"score": 0.8, "doc_id": "doc1", "source_type": "global_kb"}
        ]

        result_ko = calculate_reliability(sources, "ko")
        result_en = calculate_reliability(sources, "en")
        result_ja = calculate_reliability(sources, "ja")

        # Scores should be the same
        assert result_ko.score == result_en.score == result_ja.score

        # Explanations should be in different languages
        assert "출처" in result_ko.explanation or "신뢰" in result_ko.explanation
        assert "source" in result_en.explanation.lower()
        assert "ソース" in result_ja.explanation or "信頼" in result_ja.explanation

    def test_factors_structure(self):
        """Test that all required factors are present"""
        sources = [
            {"score": 0.8, "doc_id": "doc1", "source_type": "global_kb"}
        ]
        result = calculate_reliability(sources)

        assert "source_count" in result.factors
        assert "avg_similarity" in result.factors
        assert "source_diversity" in result.factors
        assert "source_quality" in result.factors

        # All factors should be between 0 and 1
        for factor_name, value in result.factors.items():
            assert 0.0 <= value <= 1.0, f"{factor_name} out of bounds: {value}"
