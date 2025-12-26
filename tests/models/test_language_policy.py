"""
Tests for Language Policy Models

Tests Pydantic validation for language policy models.
"""
import pytest
from pydantic import ValidationError


class TestLanguageRestrictionLevel:
    """Tests for LanguageRestrictionLevel enum"""

    def test_all_levels_defined(self):
        """Test all expected restriction levels are defined"""
        from app.api.models.language_policy import LanguageRestrictionLevel

        expected = ["none", "preferred", "enforced"]
        actual = [level.value for level in LanguageRestrictionLevel]

        for level in expected:
            assert level in actual

    def test_level_values(self):
        """Test restriction level enum values"""
        from app.api.models.language_policy import LanguageRestrictionLevel

        assert LanguageRestrictionLevel.NONE.value == "none"
        assert LanguageRestrictionLevel.PREFERRED.value == "preferred"
        assert LanguageRestrictionLevel.ENFORCED.value == "enforced"


class TestLanguagePolicy:
    """Tests for LanguagePolicy model"""

    def test_default_values(self):
        """Test default language policy values"""
        from app.api.models.language_policy import LanguagePolicy, LanguageRestrictionLevel

        policy = LanguagePolicy()

        assert policy.allowed_languages == ["en", "ko", "ja"]
        assert policy.default_language == "en"
        assert policy.restriction_level == LanguageRestrictionLevel.NONE
        assert policy.allow_auto_detect is True

    def test_custom_policy(self):
        """Test creating custom language policy"""
        from app.api.models.language_policy import LanguagePolicy, LanguageRestrictionLevel

        policy = LanguagePolicy(
            allowed_languages=["en", "ko"],
            default_language="ko",
            restriction_level=LanguageRestrictionLevel.PREFERRED,
            allow_auto_detect=False
        )

        assert policy.allowed_languages == ["en", "ko"]
        assert policy.default_language == "ko"
        assert policy.restriction_level == LanguageRestrictionLevel.PREFERRED
        assert policy.allow_auto_detect is False

    def test_enforced_policy(self):
        """Test enforced language policy"""
        from app.api.models.language_policy import LanguagePolicy, LanguageRestrictionLevel

        policy = LanguagePolicy(
            allowed_languages=["en"],
            default_language="en",
            restriction_level=LanguageRestrictionLevel.ENFORCED,
            allow_auto_detect=False
        )

        assert len(policy.allowed_languages) == 1
        assert policy.allowed_languages[0] == "en"
        assert policy.restriction_level == LanguageRestrictionLevel.ENFORCED


class TestLanguagePolicyResponse:
    """Tests for LanguagePolicyResponse model"""

    def test_basic_response(self):
        """Test basic language policy response"""
        from app.api.models.language_policy import LanguagePolicyResponse, LanguageRestrictionLevel

        response = LanguagePolicyResponse(
            allowed_languages=["en", "ko", "ja"],
            default_language="en",
            restriction_level=LanguageRestrictionLevel.NONE,
            allow_auto_detect=True
        )

        assert response.allowed_languages == ["en", "ko", "ja"]
        assert response.default_language == "en"
        assert response.current_language is None

    def test_response_with_current_language(self):
        """Test response with current language set"""
        from app.api.models.language_policy import LanguagePolicyResponse, LanguageRestrictionLevel

        response = LanguagePolicyResponse(
            allowed_languages=["en", "ko", "ja"],
            default_language="en",
            restriction_level=LanguageRestrictionLevel.PREFERRED,
            allow_auto_detect=True,
            current_language="ko"
        )

        assert response.current_language == "ko"


class TestLanguageValidationRequest:
    """Tests for LanguageValidationRequest model"""

    def test_valid_request(self):
        """Test valid language validation request"""
        from app.api.models.language_policy import LanguageValidationRequest

        request = LanguageValidationRequest(language="en")
        assert request.language == "en"

        request = LanguageValidationRequest(language="ko")
        assert request.language == "ko"

        request = LanguageValidationRequest(language="ja")
        assert request.language == "ja"

    def test_language_min_length(self):
        """Test language minimum length validation"""
        from app.api.models.language_policy import LanguageValidationRequest

        with pytest.raises(ValidationError):
            LanguageValidationRequest(language="a")  # Too short

    def test_language_max_length(self):
        """Test language maximum length validation"""
        from app.api.models.language_policy import LanguageValidationRequest

        with pytest.raises(ValidationError):
            LanguageValidationRequest(language="toolong")  # Too long


class TestLanguageValidationResponse:
    """Tests for LanguageValidationResponse model"""

    def test_valid_response(self):
        """Test valid language validation response"""
        from app.api.models.language_policy import LanguageValidationResponse

        response = LanguageValidationResponse(
            valid=True,
            requested_language="en",
            effective_language="en",
            was_modified=False
        )

        assert response.valid is True
        assert response.was_modified is False
        assert response.message is None

    def test_modified_response(self):
        """Test modified language validation response"""
        from app.api.models.language_policy import LanguageValidationResponse

        response = LanguageValidationResponse(
            valid=False,
            requested_language="ja",
            effective_language="en",
            was_modified=True,
            message="Japanese not allowed for guest role"
        )

        assert response.valid is False
        assert response.was_modified is True
        assert response.requested_language == "ja"
        assert response.effective_language == "en"
        assert "Japanese" in response.message
