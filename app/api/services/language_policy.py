"""
Language Policy Service

Provides language enforcement for LLM responses and role-based language restrictions.
Ensures RAG responses match the user's selected UI language.
"""
from enum import Enum
from typing import Optional, Tuple
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class LanguageRestrictionLevel(str, Enum):
    """Language restriction levels"""
    NONE = "none"           # No restrictions, allow any language
    PREFERRED = "preferred" # Suggest language but allow override
    ENFORCED = "enforced"   # Must use specified languages only


class LanguagePolicy(BaseModel):
    """Language restriction policy for a role"""
    allowed_languages: list[str] = Field(
        default=["en", "ko", "ja"],
        description="Languages allowed for this role"
    )
    default_language: str = Field(
        default="en",
        description="Default language if none specified"
    )
    restriction_level: LanguageRestrictionLevel = Field(
        default=LanguageRestrictionLevel.NONE,
        description="How strictly to enforce language"
    )
    allow_auto_detect: bool = Field(
        default=True,
        description="Allow automatic language detection"
    )


# Default policies by role
ROLE_LANGUAGE_POLICIES = {
    "admin": LanguagePolicy(
        allowed_languages=["en", "ko", "ja"],
        restriction_level=LanguageRestrictionLevel.NONE,
    ),
    "leader": LanguagePolicy(
        allowed_languages=["en", "ko", "ja"],
        restriction_level=LanguageRestrictionLevel.NONE,
    ),
    "senior": LanguagePolicy(
        allowed_languages=["en", "ko", "ja"],
        restriction_level=LanguageRestrictionLevel.PREFERRED,
    ),
    "user": LanguagePolicy(
        allowed_languages=["en", "ko"],
        default_language="ko",
        restriction_level=LanguageRestrictionLevel.PREFERRED,
    ),
    "guest": LanguagePolicy(
        allowed_languages=["en"],
        default_language="en",
        restriction_level=LanguageRestrictionLevel.ENFORCED,
    ),
}


# Language enforcement instructions for LLM prompts
LANGUAGE_INSTRUCTIONS = {
    "en": {
        "instruction": "You MUST respond in English only. Do not use any other language in your response.",
        "reminder": "Remember: English only.",
        "system_prefix": "[Response Language: English]"
    },
    "ko": {
        "instruction": "반드시 한국어로만 응답하세요. 다른 언어를 사용하지 마세요.",
        "reminder": "중요: 한국어로만 답변하세요.",
        "system_prefix": "[응답 언어: 한국어]"
    },
    "ja": {
        "instruction": "必ず日本語のみで回答してください。他の言語は使用しないでください。",
        "reminder": "重要：日本語のみで回答してください。",
        "system_prefix": "[回答言語：日本語]"
    },
}


# Auto-detection language (let LLM choose based on query)
AUTO_LANGUAGE_INSTRUCTION = """
Detect the language of the user's question and respond in the same language.
- If the question is in Korean (한국어), respond in Korean.
- If the question is in Japanese (日本語), respond in Japanese.
- Otherwise, respond in English.
"""


class LanguagePolicyService:
    """
    Service for language policy enforcement and validation.

    Provides:
    - Language validation based on user role
    - LLM prompt injection for language enforcement
    - Role-based language restrictions
    """

    def __init__(self):
        self._policies = ROLE_LANGUAGE_POLICIES.copy()

    def get_language_instruction(self, language: str) -> str:
        """
        Get the language enforcement instruction for LLM prompt.

        Args:
            language: Target language code (en, ko, ja, auto)

        Returns:
            Language instruction string to inject into prompt
        """
        if language == "auto":
            return AUTO_LANGUAGE_INSTRUCTION

        lang_info = LANGUAGE_INSTRUCTIONS.get(language.lower())
        if lang_info:
            return lang_info["instruction"]

        # Default to English
        return LANGUAGE_INSTRUCTIONS["en"]["instruction"]

    def inject_language_constraint(
        self,
        prompt: str,
        language: str,
        position: str = "prefix"
    ) -> str:
        """
        Inject language constraint into a prompt.

        Args:
            prompt: Original prompt
            language: Target language (en, ko, ja, auto)
            position: Where to inject - "prefix", "suffix", or "both"

        Returns:
            Modified prompt with language constraint
        """
        instruction = self.get_language_instruction(language)

        if position == "prefix":
            return f"{instruction}\n\n{prompt}"
        elif position == "suffix":
            return f"{prompt}\n\n{instruction}"
        elif position == "both":
            reminder = LANGUAGE_INSTRUCTIONS.get(language, {}).get(
                "reminder", instruction
            )
            return f"{instruction}\n\n{prompt}\n\n{reminder}"
        else:
            return f"{instruction}\n\n{prompt}"

    def get_system_prefix(self, language: str) -> str:
        """
        Get system prefix for language (for logging/debugging).

        Args:
            language: Target language code

        Returns:
            System prefix string
        """
        lang_info = LANGUAGE_INSTRUCTIONS.get(language.lower())
        if lang_info:
            return lang_info["system_prefix"]
        return f"[Response Language: {language.upper()}]"

    def validate_language(
        self,
        requested_language: str,
        user_role: str
    ) -> Tuple[str, bool]:
        """
        Validate and potentially adjust language based on user's role policy.

        Args:
            requested_language: Language requested by user
            user_role: User's role (admin, leader, senior, user, guest)

        Returns:
            Tuple of (final_language, was_modified)
            - final_language: The language to use
            - was_modified: True if the language was changed from request
        """
        policy = self._policies.get(user_role, self._policies["user"])

        # Auto detection always allowed if policy permits
        if requested_language == "auto" and policy.allow_auto_detect:
            return (requested_language, False)

        # Check if requested language is allowed
        if requested_language in policy.allowed_languages:
            return (requested_language, False)

        # Handle based on restriction level
        if policy.restriction_level == LanguageRestrictionLevel.ENFORCED:
            logger.warning(
                f"Language '{requested_language}' enforced to '{policy.default_language}' "
                f"for role '{user_role}'"
            )
            return (policy.default_language, True)

        if policy.restriction_level == LanguageRestrictionLevel.PREFERRED:
            # Log warning but allow
            logger.info(
                f"User requested non-preferred language: {requested_language} "
                f"(role: {user_role}, preferred: {policy.allowed_languages})"
            )
            return (requested_language, False)

        # NONE restriction level - allow anything
        return (requested_language, False)

    def get_user_allowed_languages(self, user_role: str) -> list[str]:
        """
        Get list of languages allowed for user's role.

        Args:
            user_role: User's role

        Returns:
            List of allowed language codes
        """
        policy = self._policies.get(user_role, self._policies["user"])
        return policy.allowed_languages.copy()

    def get_policy_for_role(self, user_role: str) -> LanguagePolicy:
        """
        Get the full language policy for a role.

        Args:
            user_role: User's role

        Returns:
            LanguagePolicy for the role
        """
        return self._policies.get(user_role, self._policies["user"])

    def update_role_policy(self, role: str, policy: LanguagePolicy) -> None:
        """
        Update language policy for a role (admin function).

        Args:
            role: Role to update
            policy: New policy
        """
        self._policies[role] = policy
        logger.info(f"Updated language policy for role '{role}'")


# Singleton instance
_language_policy_service: Optional[LanguagePolicyService] = None


def get_language_policy_service() -> LanguagePolicyService:
    """Get singleton language policy service instance"""
    global _language_policy_service
    if _language_policy_service is None:
        _language_policy_service = LanguagePolicyService()
    return _language_policy_service
