"""
Settings API Router
설정 관리 API
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException

from ..models.base import SuccessResponse, MetaInfo
from ..models.settings import (
    SystemSettings,
    SettingsUpdate,
    SettingsUpdateResponse,
)
from ..core.deps import get_current_user, get_admin_user, get_settings_service

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get(
    "",
    response_model=SuccessResponse[SystemSettings],
    summary="현재 설정 조회",
    description="시스템 현재 설정을 조회합니다."
)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    settings_service = Depends(get_settings_service)
):
    """Get current system settings"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await settings_service.get_settings()

    return SuccessResponse(
        data=SystemSettings(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.patch(
    "",
    response_model=SuccessResponse[SettingsUpdateResponse],
    summary="설정 업데이트",
    description="시스템 설정을 업데이트합니다. 관리자 권한이 필요합니다."
)
async def update_settings(
    request: SettingsUpdate,
    current_user: dict = Depends(get_admin_user),
    settings_service = Depends(get_settings_service)
):
    """Update system settings (admin only)"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Collect fields to update
    updated_fields = []
    update_data = {}

    if request.rag is not None:
        rag_dict = request.rag.model_dump(exclude_unset=True)
        for key, value in rag_dict.items():
            updated_fields.append(f"rag.{key}")
            update_data[f"rag.{key}"] = value

    if request.llm is not None:
        llm_dict = request.llm.model_dump(exclude_unset=True)
        for key, value in llm_dict.items():
            updated_fields.append(f"llm.{key}")
            update_data[f"llm.{key}"] = value

    if request.ui is not None:
        ui_dict = request.ui.model_dump(exclude_unset=True)
        for key, value in ui_dict.items():
            updated_fields.append(f"ui.{key}")
            update_data[f"ui.{key}"] = value

    if not updated_fields:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_UPDATES", "message": "업데이트할 항목이 없습니다."}
        )

    # Apply updates
    await settings_service.update_settings(update_data)

    return SuccessResponse(
        data=SettingsUpdateResponse(
            message="설정이 업데이트되었습니다.",
            updated_fields=updated_fields
        ),
        meta=MetaInfo(request_id=request_id)
    )
