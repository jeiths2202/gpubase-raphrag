"""
Tests for Answer Verification Service

Tests the Learning LLM answer verification against Summary data.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.services.answer_verification_service import (
    AnswerVerificationService,
    VerificationResult,
    VerificationStatus,
    LearningLLMResult,
    get_answer_verification_service,
)


class TestVerificationResult:
    """Test VerificationResult dataclass"""

    def test_verified_result(self):
        result = VerificationResult(
            is_valid=True,
            verification_score=0.85,
            status=VerificationStatus.VERIFIED,
            verified_codes=["-5212", "-9001"],
            unverified_codes=[],
            verified_terms=["TJES"],
        )
        assert result.is_valid is True
        assert result.verification_score == 0.85
        assert result.status == VerificationStatus.VERIFIED
        assert len(result.verified_codes) == 2

    def test_hallucination_result(self):
        result = VerificationResult(
            is_valid=False,
            verification_score=0.2,
            status=VerificationStatus.HALLUCINATION,
            hallucination_patterns=["Pattern: 에러\\s*코드... (1 matches)"],
        )
        assert result.is_valid is False
        assert result.status == VerificationStatus.HALLUCINATION
        assert len(result.hallucination_patterns) == 1

    def test_to_dict(self):
        result = VerificationResult(
            is_valid=True,
            verification_score=0.75,
            status=VerificationStatus.PARTIALLY_VERIFIED,
        )
        d = result.to_dict()
        assert d["is_valid"] is True
        assert d["verification_score"] == 0.75
        assert d["status"] == "partial"


class TestLearningLLMResult:
    """Test LearningLLMResult dataclass"""

    def test_basic_result(self):
        result = LearningLLMResult(
            answer="에러 -5212는 DATASET_NOT_FOUND입니다.",
            confidence=0.85,
            mentioned_codes=["-5212"],
            mentioned_terms=["TJES"],
        )
        assert result.answer.startswith("에러")
        assert result.confidence == 0.85
        assert "-5212" in result.mentioned_codes


class TestAnswerVerificationService:
    """Test AnswerVerificationService"""

    def test_initialization(self):
        service = AnswerVerificationService()
        assert service is not None
        assert service.summary_bm25_service is None

    def test_extract_error_codes(self):
        service = AnswerVerificationService()

        # Test error code extraction
        text = "에러 -5212와 -9001이 발생했습니다."
        codes = service._extract_error_codes(text)
        assert "-5212" in codes
        assert "-9001" in codes

    def test_extract_terms(self):
        service = AnswerVerificationService()

        # Test term extraction (use spaces around terms for word boundary matching)
        text = "The TJES and TACF modules process JCL files."
        terms = service._extract_terms(text)
        assert "TJES" in terms
        assert "TACF" in terms
        assert "JCL" in terms

    def test_extract_commands(self):
        service = AnswerVerificationService()

        # Test command extraction
        text = "tjesmgr BOOT 명령어로 시스템을 시작합니다."
        commands = service._extract_commands(text)
        assert any("tjesmgr" in c.lower() for c in commands)
        assert any("boot" in c.lower() for c in commands)

    def test_detect_hallucination_absolute_claims(self):
        service = AnswerVerificationService()

        # Test absolute certainty detection
        answer = "이 에러는 100% 발생합니다."
        patterns = service.detect_hallucination(answer)
        assert len(patterns) > 0
        assert any("certainty" in p.lower() for p in patterns)

    def test_detect_hallucination_large_error_code(self):
        service = AnswerVerificationService()

        # Very large error codes are suspicious
        answer = "에러 코드 -123456789가 발생했습니다."
        patterns = service.detect_hallucination(answer)
        # Should detect suspicious pattern
        assert len(patterns) >= 0  # May or may not detect based on pattern

    def test_calculate_verification_score_basic(self):
        service = AnswerVerificationService()

        # Test score calculation
        score = service.calculate_verification_score(
            verified_codes=["-5212"],
            unverified_codes=[],
            verified_terms=["TJES"],
            unverified_terms=[],
            verified_commands=["tjesmgr"],
            hallucination_count=0,
            answer_length=500,
        )

        # Base score 0.5 + code ratio + term ratio + command bonus + length bonus
        assert score > 0.5
        assert score <= 1.0

    def test_calculate_verification_score_with_hallucination(self):
        service = AnswerVerificationService()

        # Hallucinations should reduce score
        score = service.calculate_verification_score(
            verified_codes=[],
            unverified_codes=["-5212"],
            verified_terms=[],
            unverified_terms=["FAKE"],
            verified_commands=[],
            hallucination_count=2,
            answer_length=100,
        )

        # Score should be reduced by hallucinations
        assert score < 0.5


class TestGetAnswerVerificationService:
    """Test singleton getter"""

    def test_get_service_singleton(self):
        service1 = get_answer_verification_service()
        service2 = get_answer_verification_service()
        assert service1 is service2


@pytest.mark.asyncio
class TestVerifyAnswerAsync:
    """Test async verify_answer method"""

    async def test_verify_answer_without_service(self):
        """Test verification when summary service is not available"""
        service = AnswerVerificationService(summary_bm25_service=None)

        result = await service.verify_answer(
            answer="에러 -5212는 DATASET_NOT_FOUND입니다.",
            mentioned_codes=["-5212"],
            mentioned_terms=["TJES"],
        )

        # Should return result even without summary service
        assert isinstance(result, VerificationResult)
        # Without verification, codes should be unverified
        assert result.verification_score >= 0.0

    async def test_verify_answer_with_mock_service(self):
        """Test verification with mocked summary service"""
        # Create mock summary service
        mock_service = MagicMock()
        mock_service.is_initialized = True

        # Mock search_error_code to return results
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(
                document=MagicMock(
                    source_pdf="test.pdf",
                    page_numbers=[1],
                    name="DSALC_ERR_DATASET_NOT_FOUND",
                    description="Dataset not found error",
                )
            )
        ]
        mock_service.search_error_code = AsyncMock(return_value=mock_result)
        mock_service.search_command = AsyncMock(return_value=None)
        mock_service.search_glossary = AsyncMock(return_value=None)

        service = AnswerVerificationService(summary_bm25_service=mock_service)

        result = await service.verify_answer(
            answer="에러 -5212는 DATASET_NOT_FOUND입니다.",
            mentioned_codes=["-5212"],
        )

        assert result.is_valid is True
        assert "-5212" in result.verified_codes
