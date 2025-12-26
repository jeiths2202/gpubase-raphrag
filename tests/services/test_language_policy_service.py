"""
Tests for Language Policy Service

Tests language policy enforcement and validation logic.
"""
import pytest


class TestLanguagePolicyServiceInit:
    """Tests for LanguagePolicyService initialization"""

    def test_get_language_policy_service(self):
        """Test singleton service retrieval"""
        from app.api.services.language_policy import get_language_policy_service

        service1 = get_language_policy_service()
        service2 = get_language_policy_service()

        assert service1 is service2

    def test_default_policies_exist(self):
        """Test that default policies exist for all roles"""
        from app.api.services.language_policy import ROLE_LANGUAGE_POLICIES

        expected_roles = ["admin", "leader", "senior", "user", "guest"]

        for role in expected_roles:
            assert role in ROLE_LANGUAGE_POLICIES


class TestLanguageInstructions:
    """Tests for language instruction generation"""

    def test_get_english_instruction(self):
        """Test English language instruction"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        instruction = service.get_language_instruction("en")

        assert "English" in instruction
        assert "MUST" in instruction or "only" in instruction.lower()

    def test_get_korean_instruction(self):
        """Test Korean language instruction"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        instruction = service.get_language_instruction("ko")

        assert "한국어" in instruction

    def test_get_japanese_instruction(self):
        """Test Japanese language instruction"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        instruction = service.get_language_instruction("ja")

        assert "日本語" in instruction

    def test_get_auto_instruction(self):
        """Test auto-detect language instruction"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        instruction = service.get_language_instruction("auto")

        assert "detect" in instruction.lower() or "Detect" in instruction

    def test_unknown_language_defaults_to_english(self):
        """Test unknown language falls back to English"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        instruction = service.get_language_instruction("fr")

        assert "English" in instruction


class TestInjectLanguageConstraint:
    """Tests for prompt injection with language constraints"""

    def test_inject_prefix(self):
        """Test prefix injection"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        original_prompt = "Answer this question:"
        result = service.inject_language_constraint(original_prompt, "ko", "prefix")

        assert "한국어" in result
        assert result.index("한국어") < result.index("Answer")

    def test_inject_suffix(self):
        """Test suffix injection"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        original_prompt = "Answer this question:"
        result = service.inject_language_constraint(original_prompt, "ja", "suffix")

        assert "日本語" in result
        assert result.index("Answer") < result.index("日本語")

    def test_inject_both(self):
        """Test both prefix and suffix injection"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        original_prompt = "Answer this question:"
        result = service.inject_language_constraint(original_prompt, "en", "both")

        # Should contain English instruction at both ends
        assert result.count("English") >= 1 or result.count("english") >= 1


class TestGetSystemPrefix:
    """Tests for system prefix generation"""

    def test_english_prefix(self):
        """Test English system prefix"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        prefix = service.get_system_prefix("en")

        assert "English" in prefix

    def test_korean_prefix(self):
        """Test Korean system prefix"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        prefix = service.get_system_prefix("ko")

        assert "한국어" in prefix

    def test_japanese_prefix(self):
        """Test Japanese system prefix"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        prefix = service.get_system_prefix("ja")

        assert "日本語" in prefix


class TestValidateLanguage:
    """Tests for language validation based on role"""

    def test_admin_allows_all_languages(self):
        """Test admin role allows all languages"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()

        for lang in ["en", "ko", "ja"]:
            result, modified = service.validate_language(lang, "admin")
            assert result == lang
            assert modified is False

    def test_guest_restricts_to_english(self):
        """Test guest role restricts to English only"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()

        # English should be allowed
        result, modified = service.validate_language("en", "guest")
        assert result == "en"
        assert modified is False

        # Japanese should be restricted
        result, modified = service.validate_language("ja", "guest")
        assert result == "en"  # Falls back to default
        assert modified is True

        # Korean should be restricted
        result, modified = service.validate_language("ko", "guest")
        assert result == "en"  # Falls back to default
        assert modified is True

    def test_user_role_preferred_languages(self):
        """Test user role with preferred languages"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()

        # English and Korean allowed for user
        result_en, _ = service.validate_language("en", "user")
        result_ko, _ = service.validate_language("ko", "user")

        assert result_en == "en"
        assert result_ko == "ko"

    def test_auto_detect_allowed(self):
        """Test auto-detect is allowed when policy permits"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()

        result, modified = service.validate_language("auto", "admin")
        assert result == "auto"
        assert modified is False

    def test_unknown_role_uses_user_policy(self):
        """Test unknown role falls back to user policy"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()

        result, _ = service.validate_language("en", "unknown_role")
        assert result == "en"


class TestGetUserAllowedLanguages:
    """Tests for getting allowed languages by role"""

    def test_admin_all_languages(self):
        """Test admin gets all languages"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        allowed = service.get_user_allowed_languages("admin")

        assert "en" in allowed
        assert "ko" in allowed
        assert "ja" in allowed

    def test_guest_english_only(self):
        """Test guest only gets English"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        allowed = service.get_user_allowed_languages("guest")

        assert "en" in allowed
        assert "ko" not in allowed
        assert "ja" not in allowed

    def test_returned_list_is_copy(self):
        """Test returned list is a copy (immutable)"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        allowed1 = service.get_user_allowed_languages("admin")
        allowed1.append("fr")

        allowed2 = service.get_user_allowed_languages("admin")
        assert "fr" not in allowed2


class TestGetPolicyForRole:
    """Tests for getting full policy by role"""

    def test_get_admin_policy(self):
        """Test getting admin policy"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        policy = service.get_policy_for_role("admin")

        assert policy.restriction_level.value == "none"
        assert len(policy.allowed_languages) == 3

    def test_get_guest_policy(self):
        """Test getting guest policy"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        policy = service.get_policy_for_role("guest")

        assert policy.restriction_level.value == "enforced"
        assert len(policy.allowed_languages) == 1
        assert policy.default_language == "en"

    def test_unknown_role_returns_user_policy(self):
        """Test unknown role returns user policy"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        policy = service.get_policy_for_role("unknown")
        user_policy = service.get_policy_for_role("user")

        assert policy.allowed_languages == user_policy.allowed_languages


class TestRolePolicyHierarchy:
    """Tests for role-based policy hierarchy"""

    def test_admin_has_most_permissions(self):
        """Test admin has most language permissions"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        admin_policy = service.get_policy_for_role("admin")

        for role in ["leader", "senior", "user", "guest"]:
            role_policy = service.get_policy_for_role(role)
            assert len(admin_policy.allowed_languages) >= len(role_policy.allowed_languages)

    def test_guest_has_fewest_permissions(self):
        """Test guest has fewest language permissions"""
        from app.api.services.language_policy import get_language_policy_service

        service = get_language_policy_service()
        guest_policy = service.get_policy_for_role("guest")

        for role in ["admin", "leader", "senior", "user"]:
            role_policy = service.get_policy_for_role(role)
            assert len(guest_policy.allowed_languages) <= len(role_policy.allowed_languages)
