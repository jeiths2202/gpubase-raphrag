"""
IMS Credentials Router - FULLY IMPLEMENTED

Endpoints for storing, validating, and managing encrypted IMS credentials.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional

from ....core.deps import get_current_user
from ...application.use_cases import ManageCredentialsUseCase
from ...infrastructure.dependencies import get_manage_credentials_use_case


router = APIRouter(prefix="/ims-credentials", tags=["IMS Crawler"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CredentialsCreateRequest(BaseModel):
    """Request model for creating/updating credentials"""
    ims_url: str = Field(default="https://ims.tmaxsoft.com", description="IMS base URL")
    username: str = Field(..., min_length=1, description="IMS username")
    password: str = Field(..., min_length=1, description="IMS password")


class CredentialsResponse(BaseModel):
    """Response model for credentials (no sensitive data)"""
    id: str
    user_id: str
    ims_url: str
    is_validated: bool
    last_validated_at: Optional[str] = None
    validation_error: Optional[str] = None
    created_at: str
    updated_at: str


class ValidationResponse(BaseModel):
    """Response model for credential validation"""
    is_valid: bool
    message: str
    validated_at: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=CredentialsResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_credentials(
    request: CredentialsCreateRequest,
    current_user: dict = Depends(get_current_user),
    use_case: ManageCredentialsUseCase = Depends(get_manage_credentials_use_case)
):
    """
    Create or update IMS credentials for the current user.

    Credentials are encrypted using AES-256-GCM before storage.
    Existing credentials for the user are replaced.

    **Security Note**: Passwords are NEVER logged or returned in responses.
    """
    user_id = UUID(current_user["id"])

    try:
        credentials = await use_case.create_or_update_credentials(
            user_id=user_id,
            ims_url=request.ims_url,
            username=request.username,
            password=request.password
        )

        return CredentialsResponse(
            id=str(credentials.id),
            user_id=str(credentials.user_id),
            ims_url=credentials.ims_base_url,
            is_validated=credentials.is_validated,
            last_validated_at=credentials.last_validated_at.isoformat() if credentials.last_validated_at else None,
            validation_error=credentials.validation_error,
            created_at=credentials.created_at.isoformat(),
            updated_at=credentials.updated_at.isoformat()
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {str(e)}"
        )


@router.get("/", response_model=CredentialsResponse)
async def get_credentials(
    current_user: dict = Depends(get_current_user),
    use_case: ManageCredentialsUseCase = Depends(get_manage_credentials_use_case)
):
    """
    Get IMS credentials status for the current user.

    Returns credential metadata (validation status, timestamps) but NOT the actual credentials.
    """
    user_id = UUID(current_user["id"])

    credentials = await use_case.get_credentials(user_id)

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credentials not found. Please set up your IMS credentials first."
        )

    return CredentialsResponse(
        id=str(credentials.id),
        user_id=str(credentials.user_id),
        ims_url=credentials.ims_base_url,
        is_validated=credentials.is_validated,
        last_validated_at=credentials.last_validated_at.isoformat() if credentials.last_validated_at else None,
        validation_error=credentials.validation_error,
        created_at=credentials.created_at.isoformat(),
        updated_at=credentials.updated_at.isoformat()
    )


@router.post("/validate", response_model=ValidationResponse)
async def validate_credentials(
    current_user: dict = Depends(get_current_user),
    use_case: ManageCredentialsUseCase = Depends(get_manage_credentials_use_case)
):
    """
    Validate IMS credentials by attempting authentication.

    Tests stored credentials against the IMS system.
    Updates validation status in the database.
    """
    user_id = UUID(current_user["id"])

    is_valid, error_message = await use_case.validate_credentials(user_id)

    if is_valid:
        return ValidationResponse(
            is_valid=True,
            message="Credentials validated successfully",
            validated_at=None  # Will be fetched from DB if needed
        )
    else:
        return ValidationResponse(
            is_valid=False,
            message=error_message or "Validation failed",
            validated_at=None
        )


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(
    current_user: dict = Depends(get_current_user),
    use_case: ManageCredentialsUseCase = Depends(get_manage_credentials_use_case)
):
    """
    Delete IMS credentials for the current user.

    Permanently removes all stored credentials.
    This action cannot be undone.
    """
    user_id = UUID(current_user["id"])

    await use_case.delete_credentials(user_id)

    return None
