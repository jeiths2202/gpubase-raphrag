"""
User Preferences Models
Theme and Language preference management for KMS Platform
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum


class ThemeType(str, Enum):
    """Supported theme types"""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class LanguageCode(str, Enum):
    """Supported language codes"""
    EN = "en"
    KO = "ko"
    JA = "ja"


class UserPreferencesResponse(BaseModel):
    """Response model for user preferences"""
    theme: ThemeType = Field(default=ThemeType.DARK, description="User's theme preference")
    language: LanguageCode = Field(default=LanguageCode.EN, description="User's language preference")
    timezone: str = Field(default="UTC", description="User's timezone")
    notifications_enabled: bool = Field(default=True, description="Enable notifications")
    email_notifications: bool = Field(default=True, description="Enable email notifications")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "theme": "dark",
                "language": "ko",
                "timezone": "Asia/Seoul",
                "notifications_enabled": True,
                "email_notifications": True
            }
        })


class UserPreferencesUpdate(BaseModel):
    """Request model for updating user preferences (partial update)"""
    theme: Optional[ThemeType] = Field(default=None, description="Theme preference")
    language: Optional[LanguageCode] = Field(default=None, description="Language preference")
    timezone: Optional[str] = Field(default=None, description="Timezone preference")
    notifications_enabled: Optional[bool] = Field(default=None, description="Enable notifications")
    email_notifications: Optional[bool] = Field(default=None, description="Enable email notifications")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "theme": "light",
                "language": "ko"
            }
        })


class SupportedLanguage(BaseModel):
    """Model for supported language information"""
    code: str = Field(..., description="Language code (e.g., 'en', 'ko')")
    name: str = Field(..., description="Language name in English")
    native_name: str = Field(..., description="Language name in native language")


class SupportedPreferences(BaseModel):
    """Response model for supported preference options"""
    themes: list[str] = Field(
        default=["light", "dark", "system"],
        description="Available theme options"
    )
    languages: list[SupportedLanguage] = Field(
        default_factory=lambda: [
            SupportedLanguage(code="en", name="English", native_name="English"),
            SupportedLanguage(code="ko", name="Korean", native_name="한국어"),
            SupportedLanguage(code="ja", name="Japanese", native_name="日本語")
        ],
        description="Available languages"
    )
    timezones: list[str] = Field(
        default_factory=lambda: [
            "UTC",
            "Asia/Seoul",
            "Asia/Tokyo",
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Paris"
        ],
        description="Available timezones"
    )


class PreferencesUpdateResponse(BaseModel):
    """Response after updating preferences"""
    message: str = Field(default="Preferences updated successfully")
    updated_fields: list[str] = Field(default_factory=list, description="List of updated fields")
    preferences: UserPreferencesResponse = Field(..., description="Updated preferences")
