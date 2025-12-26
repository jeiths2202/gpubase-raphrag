"""
User Preferences API Router
사용자 개인 설정 관리 API (테마, 언어 등)
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from ..models.base import SuccessResponse, MetaInfo
from ..models.preferences import (
    UserPreferencesResponse,
    UserPreferencesUpdate,
    SupportedPreferences,
    PreferencesUpdateResponse,
    ThemeType,
    LanguageCode,
)
from ..core.deps import get_current_user

router = APIRouter(prefix="/preferences", tags=["Preferences"])


# In-memory storage for user preferences (temporary until database integration)
_user_preferences: dict[str, dict] = {}


def get_user_preferences(user_id: str) -> UserPreferencesResponse:
    """Get user preferences from storage"""
    if user_id in _user_preferences:
        return UserPreferencesResponse(**_user_preferences[user_id])
    # Return defaults for new users
    return UserPreferencesResponse()


def save_user_preferences(user_id: str, preferences: dict) -> None:
    """Save user preferences to storage"""
    if user_id not in _user_preferences:
        _user_preferences[user_id] = {}
    _user_preferences[user_id].update(preferences)


@router.get(
    "",
    response_model=SuccessResponse[UserPreferencesResponse],
    summary="사용자 설정 조회",
    description="현재 로그인한 사용자의 개인 설정(테마, 언어 등)을 조회합니다."
)
async def get_preferences(
    current_user: dict = Depends(get_current_user)
):
    """Get current user's preferences"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    user_id = current_user.get("id", current_user.get("username", "anonymous"))

    preferences = get_user_preferences(user_id)

    return SuccessResponse(
        data=preferences,
        meta=MetaInfo(request_id=request_id)
    )


@router.patch(
    "",
    response_model=SuccessResponse[PreferencesUpdateResponse],
    summary="사용자 설정 업데이트",
    description="사용자의 개인 설정을 업데이트합니다. 변경할 항목만 전송하면 됩니다."
)
async def update_preferences(
    request: UserPreferencesUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update current user's preferences (partial update)"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    user_id = current_user.get("id", current_user.get("username", "anonymous"))

    # Get current preferences
    current_prefs = get_user_preferences(user_id)

    # Collect fields to update
    updated_fields = []
    update_data = {}

    # Process each field if provided
    request_dict = request.model_dump(exclude_unset=True)

    for field, value in request_dict.items():
        if value is not None:
            updated_fields.append(field)
            # Convert enum to string value for storage
            if isinstance(value, (ThemeType, LanguageCode)):
                update_data[field] = value.value
            else:
                update_data[field] = value

    if not updated_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_UPDATES", "message": "업데이트할 항목이 없습니다."}
        )

    # Save updated preferences
    save_user_preferences(user_id, update_data)

    # Get updated preferences
    updated_prefs = get_user_preferences(user_id)

    return SuccessResponse(
        data=PreferencesUpdateResponse(
            message="설정이 업데이트되었습니다.",
            updated_fields=updated_fields,
            preferences=updated_prefs
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/supported",
    response_model=SuccessResponse[SupportedPreferences],
    summary="지원 옵션 조회",
    description="테마, 언어 등 지원되는 설정 옵션 목록을 조회합니다. 인증 불필요."
)
async def get_supported_preferences():
    """Get supported preference options (no auth required)"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    return SuccessResponse(
        data=SupportedPreferences(),
        meta=MetaInfo(request_id=request_id)
    )
