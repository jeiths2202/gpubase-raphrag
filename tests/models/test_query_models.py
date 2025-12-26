"""
Tests for Query Models

Tests Pydantic validation for query request/response models.
"""
import pytest
from pydantic import ValidationError


class TestStrategyType:
    """Tests for StrategyType enum"""

    def test_all_strategies_defined(self):
        """Test all expected strategies are defined"""
        from app.api.models.query import StrategyType

        expected = ["auto", "vector", "graph", "hybrid", "code"]
        actual = [s.value for s in StrategyType]

        for strategy in expected:
            assert strategy in actual

    def test_strategy_values(self):
        """Test strategy enum values"""
        from app.api.models.query import StrategyType

        assert StrategyType.AUTO.value == "auto"
        assert StrategyType.VECTOR.value == "vector"
        assert StrategyType.GRAPH.value == "graph"
        assert StrategyType.HYBRID.value == "hybrid"
        assert StrategyType.CODE.value == "code"


class TestLanguageType:
    """Tests for LanguageType enum"""

    def test_all_languages_defined(self):
        """Test all expected languages are defined"""
        from app.api.models.query import LanguageType

        expected = ["auto", "ko", "ja", "en"]
        actual = [l.value for l in LanguageType]

        for lang in expected:
            assert lang in actual


class TestQueryOptions:
    """Tests for QueryOptions model"""

    def test_default_options(self):
        """Test default query options"""
        from app.api.models.query import QueryOptions

        options = QueryOptions()
        assert options.top_k == 5
        assert options.include_sources is True
        assert options.use_session_docs is True
        assert options.session_weight == 2.0
        assert options.use_external_resources is True

    def test_top_k_range(self):
        """Test top_k range validation"""
        from app.api.models.query import QueryOptions

        # Valid range
        options = QueryOptions(top_k=10)
        assert options.top_k == 10

        # Min boundary
        options = QueryOptions(top_k=1)
        assert options.top_k == 1

        # Max boundary
        options = QueryOptions(top_k=20)
        assert options.top_k == 20

        # Below min
        with pytest.raises(ValidationError):
            QueryOptions(top_k=0)

        # Above max
        with pytest.raises(ValidationError):
            QueryOptions(top_k=21)

    def test_session_weight_range(self):
        """Test session_weight range validation"""
        from app.api.models.query import QueryOptions

        # Valid range
        options = QueryOptions(session_weight=3.0)
        assert options.session_weight == 3.0

        # Boundaries
        options = QueryOptions(session_weight=1.0)
        assert options.session_weight == 1.0

        options = QueryOptions(session_weight=5.0)
        assert options.session_weight == 5.0

        # Out of range
        with pytest.raises(ValidationError):
            QueryOptions(session_weight=0.5)

        with pytest.raises(ValidationError):
            QueryOptions(session_weight=5.5)

    def test_external_weight_range(self):
        """Test external_weight range validation"""
        from app.api.models.query import QueryOptions

        # Valid
        options = QueryOptions(external_weight=2.5)
        assert options.external_weight == 2.5

        # Out of range
        with pytest.raises(ValidationError):
            QueryOptions(external_weight=0.5)


class TestQueryRequest:
    """Tests for QueryRequest model"""

    def test_valid_query_request(self):
        """Test valid query request"""
        from app.api.models.query import QueryRequest, StrategyType, LanguageType

        request = QueryRequest(question="What is RAG?")
        assert request.question == "What is RAG?"
        assert request.strategy == StrategyType.AUTO  # Default
        assert request.language == LanguageType.AUTO  # Default

    def test_question_required(self):
        """Test that question is required"""
        from app.api.models.query import QueryRequest

        with pytest.raises(ValidationError) as exc_info:
            QueryRequest()

        error = exc_info.value
        assert any("question" in str(e) for e in error.errors())

    def test_question_min_length(self):
        """Test question minimum length"""
        from app.api.models.query import QueryRequest

        with pytest.raises(ValidationError):
            QueryRequest(question="")

    def test_question_max_length(self):
        """Test question maximum length"""
        from app.api.models.query import QueryRequest

        long_question = "a" * 2001  # Over 2000 char limit
        with pytest.raises(ValidationError):
            QueryRequest(question=long_question)

        # Just at limit should work
        valid_question = "a" * 2000
        request = QueryRequest(question=valid_question)
        assert len(request.question) == 2000

    def test_query_with_strategy(self):
        """Test query with explicit strategy"""
        from app.api.models.query import QueryRequest, StrategyType

        request = QueryRequest(
            question="Show code examples",
            strategy=StrategyType.CODE
        )
        assert request.strategy == StrategyType.CODE

    def test_query_with_language(self):
        """Test query with explicit language"""
        from app.api.models.query import QueryRequest, LanguageType

        request = QueryRequest(
            question="한글 질문입니다",
            language=LanguageType.KO
        )
        assert request.language == LanguageType.KO

    def test_query_with_options(self):
        """Test query with custom options"""
        from app.api.models.query import QueryRequest, QueryOptions

        options = QueryOptions(top_k=10, include_sources=False)
        request = QueryRequest(question="Test", options=options)
        assert request.options.top_k == 10
        assert request.options.include_sources is False


class TestSourceInfo:
    """Tests for SourceInfo model"""

    def test_basic_source_info(self):
        """Test basic source info creation"""
        from app.api.models.query import SourceInfo

        source = SourceInfo(
            doc_id="doc_001",
            doc_name="test.pdf",
            chunk_id="chunk_001",
            chunk_index=0,
            content="Sample content",
            score=0.85,
            source_type="vector"
        )
        assert source.doc_id == "doc_001"
        assert source.score == 0.85
        assert source.is_session_doc is False  # Default
        assert source.is_external_resource is False  # Default

    def test_score_range(self):
        """Test score range validation"""
        from app.api.models.query import SourceInfo

        # Valid scores
        source = SourceInfo(
            doc_id="1", doc_name="a", chunk_id="c1",
            chunk_index=0, content="x", score=0.0, source_type="v"
        )
        assert source.score == 0.0

        source = SourceInfo(
            doc_id="1", doc_name="a", chunk_id="c1",
            chunk_index=0, content="x", score=1.0, source_type="v"
        )
        assert source.score == 1.0

        # Invalid scores
        with pytest.raises(ValidationError):
            SourceInfo(
                doc_id="1", doc_name="a", chunk_id="c1",
                chunk_index=0, content="x", score=-0.1, source_type="v"
            )

        with pytest.raises(ValidationError):
            SourceInfo(
                doc_id="1", doc_name="a", chunk_id="c1",
                chunk_index=0, content="x", score=1.1, source_type="v"
            )

    def test_session_doc_source(self):
        """Test session document source"""
        from app.api.models.query import SourceInfo

        source = SourceInfo(
            doc_id="doc_001",
            doc_name="uploaded.pdf",
            chunk_id="chunk_001",
            chunk_index=0,
            content="Session content",
            score=0.9,
            source_type="session",
            is_session_doc=True,
            page_number=5
        )
        assert source.is_session_doc is True
        assert source.page_number == 5

    def test_external_resource_source(self):
        """Test external resource source"""
        from app.api.models.query import SourceInfo

        source = SourceInfo(
            doc_id="doc_001",
            doc_name="Notion Page",
            chunk_id="chunk_001",
            chunk_index=0,
            content="External content",
            score=0.88,
            source_type="external_notion",
            is_external_resource=True,
            source_url="https://notion.so/page",
            external_source="notion"
        )
        assert source.is_external_resource is True
        assert source.external_source == "notion"


class TestQueryAnalysis:
    """Tests for QueryAnalysis model"""

    def test_basic_analysis(self):
        """Test basic query analysis"""
        from app.api.models.query import QueryAnalysis

        analysis = QueryAnalysis(
            detected_language="ko",
            query_type="factual"
        )
        assert analysis.detected_language == "ko"
        assert analysis.is_comprehensive is False  # Default
        assert analysis.used_session_docs is False  # Default

    def test_comprehensive_analysis(self):
        """Test comprehensive query analysis"""
        from app.api.models.query import QueryAnalysis

        analysis = QueryAnalysis(
            detected_language="en",
            query_type="comprehensive",
            is_comprehensive=True,
            is_deep_analysis=True,
            used_session_docs=True,
            session_doc_count=3
        )
        assert analysis.is_comprehensive is True
        assert analysis.session_doc_count == 3


class TestQueryResponse:
    """Tests for QueryResponse model"""

    def test_basic_response(self):
        """Test basic query response"""
        from app.api.models.query import QueryResponse, StrategyType, LanguageType

        response = QueryResponse(
            answer="This is the answer",
            strategy=StrategyType.HYBRID,
            language=LanguageType.EN,
            confidence=0.92
        )
        assert response.answer == "This is the answer"
        assert response.confidence == 0.92
        assert response.sources == []  # Default empty

    def test_confidence_range(self):
        """Test confidence range validation"""
        from app.api.models.query import QueryResponse, StrategyType, LanguageType

        # Valid
        response = QueryResponse(
            answer="a", strategy=StrategyType.AUTO,
            language=LanguageType.AUTO, confidence=0.5
        )
        assert response.confidence == 0.5

        # Invalid
        with pytest.raises(ValidationError):
            QueryResponse(
                answer="a", strategy=StrategyType.AUTO,
                language=LanguageType.AUTO, confidence=1.5
            )


class TestClassificationModels:
    """Tests for classification models"""

    def test_classification_result(self):
        """Test ClassificationResult model"""
        from app.api.models.query import ClassificationResult, StrategyType

        result = ClassificationResult(
            strategy=StrategyType.VECTOR,
            confidence=0.85,
            probabilities={
                "vector": 0.85,
                "graph": 0.10,
                "hybrid": 0.05
            }
        )
        assert result.strategy == StrategyType.VECTOR
        assert result.probabilities["vector"] == 0.85

    def test_classification_features(self):
        """Test ClassificationFeatures model"""
        from app.api.models.query import ClassificationFeatures

        features = ClassificationFeatures(
            language="ko",
            has_error_code=True,
            is_code_query=True
        )
        assert features.language == "ko"
        assert features.has_error_code is True
        assert features.is_code_query is True
        assert features.is_comprehensive is False  # Default
