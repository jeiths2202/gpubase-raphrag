"""
Language Policy Models

Pydantic models for language restriction policies and role-based language management.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LanguageRestrictionLevel(str, Enum):
    """Language restriction levels"""
    NONE = "none"           # No restrictions, allow any language
    PREFERRED = "preferred" # Suggest language but allow override
    ENFORCED = "enforced"   # Must use specified languages only


class LanguagePolicy(BaseModel):
    """Language restriction policy configuration"""
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
        description="How strictly to enforce language restriction"
    )
    allow_auto_detect: bool = Field(
        default=True,
        description="Allow automatic language detection"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "allowed_languages": ["en", "ko", "ja"],
                "default_language": "en",
                "restriction_level": "preferred",
                "allow_auto_detect": True
            }
        }


class LanguagePolicyResponse(BaseModel):
    """Response model for language policy info"""
    allowed_languages: list[str] = Field(
        description="Languages allowed for current user"
    )
    default_language: str = Field(
        description="Default language for current user"
    )
    restriction_level: LanguageRestrictionLevel = Field(
        description="Restriction level for current user"
    )
    allow_auto_detect: bool = Field(
        description="Whether auto-detect is allowed"
    )
    current_language: Optional[str] = Field(
        default=None,
        description="User's current language preference"
    )


class LanguageValidationRequest(BaseModel):
    """Request to validate a language selection"""
    language: str = Field(
        min_length=2,
        max_length=5,
        description="Language code to validate (e.g., 'en', 'ko', 'ja')"
    )


class LanguageValidationResponse(BaseModel):
    """Response for language validation"""
    valid: bool = Field(
        description="Whether the language is allowed"
    )
    requested_language: str = Field(
        description="The language that was requested"
    )
    effective_language: str = Field(
        description="The language that will be used"
    )
    was_modified: bool = Field(
        description="Whether the language was modified from request"
    )
    message: Optional[str] = Field(
        default=None,
        description="Additional message about the validation"
    )
