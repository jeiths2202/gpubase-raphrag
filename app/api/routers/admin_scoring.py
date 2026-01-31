"""
Admin Scoring Configuration Router

Provides API endpoints for managing RAG scoring configuration:
- GET/PUT active configuration
- Configuration history and rollback
- Parameter metadata and validation
- Simulation endpoints

All endpoints require admin authentication.
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..models.scoring_config import (
    ScoringConfig,
    ScoringConfigHistory,
    ParameterMetadata,
    SimulationResult,
    ComparisonResult,
    TestCase,
    BatchTestResult,
)
from ..services.scoring_config_service import (
    get_scoring_config_service,
    ScoringConfigService,
)
from ..services.scoring_simulation_service import (
    get_simulation_service,
    ScoringSimulationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/scoring",
    tags=["Admin - Scoring Configuration"],
)


# Request/Response Models

class ConfigUpdateRequest(BaseModel):
    """Request to update scoring configuration"""
    config: ScoringConfig
    reason: Optional[str] = Field(None, description="Reason for this change")


class ConfigResponse(BaseModel):
    """Scoring configuration response"""
    config: ScoringConfig
    source: str = Field(..., description="Configuration source: runtime, cache, database, or environment")
    last_updated: Optional[datetime] = None
    warnings: List[str] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    """Request for configuration simulation"""
    query: str = Field(..., description="Test query to simulate")
    config: Optional[ScoringConfig] = Field(None, description="Config to test (uses active if not provided)")


class CompareRequest(BaseModel):
    """Request to compare two configurations"""
    query: str = Field(..., description="Test query for comparison")
    config_a: Optional[ScoringConfig] = Field(None, description="First config (uses active if not provided)")
    config_b: ScoringConfig = Field(..., description="Second config to compare against")


class BatchTestRequest(BaseModel):
    """Request for batch testing"""
    test_cases: List[TestCase]
    config: Optional[ScoringConfig] = Field(None, description="Config to test (uses active if not provided)")


# Dependency to get service
async def get_service() -> ScoringConfigService:
    return get_scoring_config_service()


# Dependency to verify admin user
async def require_admin(user: dict = Depends(get_current_user)):
    """Require admin privileges for the endpoint."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    # Check if user has admin role (user is a dict from get_current_user)
    user_role = user.get('role')
    if user_role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


# Endpoints

@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get active scoring configuration",
    description="Returns the currently active scoring configuration with its source and any validation warnings."
)
async def get_config(
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> ConfigResponse:
    """Get the currently active scoring configuration."""
    config = await service.get_active_config()
    warnings = service.validate_config(config)

    # Determine source
    if service._runtime_override:
        source = "runtime"
    elif service._cached_config:
        source = "cache"
    else:
        source = "environment"

    return ConfigResponse(
        config=config,
        source=source,
        warnings=warnings,
    )


@router.put(
    "/config",
    response_model=ConfigResponse,
    summary="Update scoring configuration",
    description="Updates the active scoring configuration. Changes are persisted and take effect immediately."
)
async def update_config(
    request: ConfigUpdateRequest,
    service: ScoringConfigService = Depends(get_service),
    admin = Depends(require_admin),
) -> ConfigResponse:
    """Update the scoring configuration."""
    # Validate before updating
    warnings = service.validate_config(request.config)

    # Get user ID from admin context
    user_id = getattr(admin, 'id', None)

    updated = await service.update_config(
        new_config=request.config,
        user_id=user_id,
        reason=request.reason,
    )

    logger.info(f"Scoring config updated by admin {user_id}: {request.reason}")

    return ConfigResponse(
        config=updated,
        source="runtime",
        last_updated=datetime.utcnow(),
        warnings=warnings,
    )


@router.post(
    "/config/reset",
    response_model=ConfigResponse,
    summary="Reset to default configuration",
    description="Clears runtime override and reverts to environment/database configuration."
)
async def reset_config(
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> ConfigResponse:
    """Reset configuration to defaults."""
    service.clear_runtime_override()
    config = await service.get_active_config()
    warnings = service.validate_config(config)

    return ConfigResponse(
        config=config,
        source="environment",
        warnings=warnings,
    )


@router.get(
    "/config/history",
    response_model=List[ScoringConfigHistory],
    summary="Get configuration change history",
    description="Returns the history of configuration changes for auditing purposes."
)
async def get_config_history(
    limit: int = 20,
    offset: int = 0,
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> List[ScoringConfigHistory]:
    """Get configuration change history."""
    return await service.get_config_history(limit=limit, offset=offset)


@router.get(
    "/parameters",
    response_model=Dict[str, ParameterMetadata],
    summary="Get parameter metadata",
    description="Returns metadata for all configurable parameters including descriptions, ranges, effects, and trade-offs."
)
async def get_parameters(
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> Dict[str, ParameterMetadata]:
    """Get metadata for all configurable parameters."""
    return service.get_parameter_metadata()


@router.post(
    "/validate",
    response_model=List[str],
    summary="Validate configuration",
    description="Validates a configuration and returns any warnings or issues found."
)
async def validate_config(
    config: ScoringConfig,
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> List[str]:
    """Validate a configuration without applying it."""
    return service.validate_config(config)


@router.post(
    "/simulate",
    response_model=SimulationResult,
    summary="Simulate search with configuration",
    description="Runs a search simulation with the specified configuration and returns detailed scoring breakdown."
)
async def simulate_search(
    request: SimulationRequest,
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> SimulationResult:
    """
    Simulate a search with the given configuration.

    This endpoint runs the full search pipeline in simulation mode,
    returning detailed information about each scoring step.
    """
    simulation_service = get_simulation_service()
    config = request.config or await service.get_active_config()

    return await simulation_service.simulate(
        query=request.query,
        config=config
    )


@router.post(
    "/compare",
    response_model=ComparisonResult,
    summary="Compare two configurations",
    description="Compares search results between two configurations and shows ranking differences."
)
async def compare_configs(
    request: CompareRequest,
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> ComparisonResult:
    """
    Compare search results between two configurations.

    Shows which documents moved up/down in ranking and score differences.
    """
    simulation_service = get_simulation_service()
    config_a = request.config_a or await service.get_active_config()

    return await simulation_service.compare(
        query=request.query,
        config_a=config_a,
        config_b=request.config_b
    )


@router.post(
    "/batch-test",
    response_model=BatchTestResult,
    summary="Run batch tests",
    description="Runs multiple test cases against a configuration and reports pass/fail results."
)
async def batch_test(
    request: BatchTestRequest,
    service: ScoringConfigService = Depends(get_service),
    _admin = Depends(require_admin),
) -> BatchTestResult:
    """
    Run batch tests against a configuration.

    Each test case specifies expected documents and the test passes/fails
    based on whether the configuration produces the expected results.
    """
    simulation_service = get_simulation_service()
    config = request.config or await service.get_active_config()

    return await simulation_service.batch_test(
        test_cases=request.test_cases,
        config=config
    )


@router.post(
    "/config/rollback/{history_id}",
    response_model=ConfigResponse,
    summary="Rollback to previous configuration",
    description="Rollback to a specific configuration version from history."
)
async def rollback_config(
    history_id: UUID,
    service: ScoringConfigService = Depends(get_service),
    admin = Depends(require_admin),
) -> ConfigResponse:
    """
    Rollback to a previous configuration version.

    Restores the configuration from a history entry and records the rollback.
    """
    try:
        user_id = getattr(admin, 'id', None)
        config = await service.rollback_config(history_id, user_id)

        return ConfigResponse(
            config=config,
            source="rollback",
            last_updated=datetime.utcnow(),
            warnings=service.validate_config(config),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e)
        )


# Quick adjustment endpoints for common operations

@router.patch(
    "/config/rrf-k",
    response_model=ConfigResponse,
    summary="Quick adjust RRF k parameter",
    description="Quickly adjusts the RRF k parameter without updating the full configuration."
)
async def adjust_rrf_k(
    k: int = Query(..., ge=1, le=1000, description="RRF k parameter value"),
    service: ScoringConfigService = Depends(get_service),
    admin = Depends(require_admin),
) -> ConfigResponse:
    """Quick adjust RRF k parameter."""
    config = await service.get_active_config()
    config.rrf.k = k

    user_id = getattr(admin, 'id', None)
    updated = await service.update_config(
        new_config=config,
        user_id=user_id,
        reason=f"Quick adjust: RRF k = {k}",
    )

    return ConfigResponse(
        config=updated,
        source="runtime",
        last_updated=datetime.utcnow(),
        warnings=service.validate_config(updated),
    )


@router.patch(
    "/config/boost/error-code",
    response_model=ConfigResponse,
    summary="Quick adjust error code boost",
    description="Quickly adjusts the error code boost parameter."
)
async def adjust_error_code_boost(
    boost: float = Query(..., ge=1.0, le=3.0, description="Error code boost multiplier"),
    service: ScoringConfigService = Depends(get_service),
    admin = Depends(require_admin),
) -> ConfigResponse:
    """Quick adjust error code boost."""
    config = await service.get_active_config()
    config.boost.error_code_boost = boost

    user_id = getattr(admin, 'id', None)
    updated = await service.update_config(
        new_config=config,
        user_id=user_id,
        reason=f"Quick adjust: error_code_boost = {boost}",
    )

    return ConfigResponse(
        config=updated,
        source="runtime",
        last_updated=datetime.utcnow(),
        warnings=service.validate_config(updated),
    )


@router.patch(
    "/config/confidence",
    response_model=ConfigResponse,
    summary="Quick adjust confidence thresholds",
    description="Quickly adjusts confidence level thresholds."
)
async def adjust_confidence_thresholds(
    high: Optional[float] = Query(None, ge=0.0, le=1.0, description="High confidence threshold"),
    medium: Optional[float] = Query(None, ge=0.0, le=1.0, description="Medium confidence threshold"),
    low: Optional[float] = Query(None, ge=0.0, le=1.0, description="Low confidence threshold"),
    service: ScoringConfigService = Depends(get_service),
    admin = Depends(require_admin),
) -> ConfigResponse:
    """Quick adjust confidence thresholds."""
    config = await service.get_active_config()

    if high is not None:
        config.confidence.high_threshold = high
    if medium is not None:
        config.confidence.medium_threshold = medium
    if low is not None:
        config.confidence.low_threshold = low

    user_id = getattr(admin, 'id', None)
    updated = await service.update_config(
        new_config=config,
        user_id=user_id,
        reason=f"Quick adjust: confidence thresholds",
    )

    return ConfigResponse(
        config=updated,
        source="runtime",
        last_updated=datetime.utcnow(),
        warnings=service.validate_config(updated),
    )
