"""
Long Context Management API Endpoints

Provides endpoints for:
- Context window status and optimization
- Token usage monitoring
- Manual summarization triggers
- Context configuration
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel, Field

from app.api.core.deps import get_current_user
from app.api.models.long_context import (
    LLMContextConfig,
    ContextWindowStatus,
    OptimizeContextRequest,
    OptimizeContextResult,
    CompressionMethod,
    TokenUsageReport,
    TokenBudget,
    get_model_context_limit,
    MODEL_CONTEXT_LIMITS
)
from app.api.services.long_context_service import get_long_context_service

router = APIRouter(prefix="/context", tags=["context-management"])


# ============================================
# Request/Response Models
# ============================================

class ContextConfigRequest(BaseModel):
    """Request to update context configuration"""
    max_tokens: Optional[int] = Field(None, ge=1000, le=200000)
    reserved_for_response: Optional[int] = Field(None, ge=500, le=16000)
    reserved_for_rag: Optional[int] = Field(None, ge=500, le=32000)
    max_recent_turns: Optional[int] = Field(None, ge=1, le=100)
    enable_compression: Optional[bool] = None
    compression_threshold: Optional[float] = Field(None, ge=0.5, le=1.0)


class TokenCountRequest(BaseModel):
    """Request to count tokens in text"""
    text: str = Field(..., max_length=500000)


class TokenCountResponse(BaseModel):
    """Response with token count"""
    text_length: int
    token_count: int
    estimated_cost_ratio: float = Field(description="Approximate cost ratio vs 1K tokens")


class ManualSummarizeRequest(BaseModel):
    """Request to manually trigger summarization"""
    conversation_id: UUID
    preserve_recent_turns: int = Field(default=6, ge=2, le=20)
    target_summary_tokens: int = Field(default=1000, ge=100, le=3000)


class ModelContextInfo(BaseModel):
    """Information about model context limits"""
    model_name: str
    max_context_tokens: int
    recommended_usage: float = 0.75
    recommended_response_reserve: int


# ============================================
# Context Status Endpoints
# ============================================

@router.get(
    "/status/{conversation_id}",
    response_model=ContextWindowStatus,
    summary="컨텍스트 윈도우 상태 조회",
    description="대화의 현재 컨텍스트 윈도우 상태를 조회합니다"
)
async def get_context_status(
    conversation_id: UUID,
    current_user=Depends(get_current_user)
):
    """Get context window status for a conversation"""
    service = get_long_context_service()
    return await service.get_context_status(conversation_id)


@router.get(
    "/usage/{conversation_id}",
    response_model=TokenUsageReport,
    summary="토큰 사용량 리포트",
    description="대화의 상세 토큰 사용량을 조회합니다"
)
async def get_token_usage(
    conversation_id: UUID,
    current_user=Depends(get_current_user)
):
    """Get detailed token usage report"""
    service = get_long_context_service()
    status = await service.get_context_status(conversation_id)

    # Build token budget
    budget = TokenBudget(
        total_budget=status.max_tokens,
        allocated={
            "messages": status.total_tokens - status.summary_token_count,
            "summary": status.summary_token_count
        },
        reserved={
            "response": 4096,
            "system": 1000,
            "rag": 8000
        }
    )

    # Generate recommendations
    recommendations = []
    if status.usage_ratio > 0.9:
        recommendations.append("컨텍스트 사용량이 90%를 초과했습니다. 자동 요약이 권장됩니다.")
    if status.usage_ratio > 0.75 and not status.has_active_summary:
        recommendations.append("요약을 생성하여 토큰 사용량을 줄일 수 있습니다.")
    if status.total_messages > 50:
        recommendations.append("대화가 길어졌습니다. 새 대화를 시작하는 것을 권장합니다.")

    return TokenUsageReport(
        conversation_id=conversation_id,
        timestamp=datetime.utcnow(),
        budget=budget,
        breakdown={
            "messages": status.total_tokens - status.summary_token_count,
            "summary": status.summary_token_count,
            "total": status.total_tokens
        },
        compression_savings=0,
        summarization_savings=status.messages_summarized * 100,  # Rough estimate
        efficiency_score=1.0 - status.usage_ratio,
        recommendations=recommendations
    )


# ============================================
# Context Optimization Endpoints
# ============================================

@router.post(
    "/optimize",
    response_model=OptimizeContextResult,
    summary="컨텍스트 최적화",
    description="컨텍스트 윈도우를 최적화하여 토큰 사용량을 줄입니다"
)
async def optimize_context(
    request: OptimizeContextRequest,
    current_user=Depends(get_current_user)
):
    """Optimize context window to reduce token usage"""
    service = get_long_context_service()
    return await service.optimize_context(request)


@router.post(
    "/summarize",
    summary="수동 요약 실행",
    description="대화의 오래된 메시지를 수동으로 요약합니다"
)
async def manual_summarize(
    request: ManualSummarizeRequest,
    current_user=Depends(get_current_user)
):
    """Manually trigger summarization for a conversation"""
    service = get_long_context_service()

    # Use optimize with summarization
    optimize_request = OptimizeContextRequest(
        conversation_id=request.conversation_id,
        target_usage_ratio=0.5,  # Aggressive optimization
        method=CompressionMethod.SUMMARIZATION,
        preserve_recent_turns=request.preserve_recent_turns
    )

    result = await service.optimize_context(optimize_request)

    return {
        "success": result.success,
        "messages_summarized": result.messages_summarized,
        "tokens_saved": result.tokens_saved,
        "new_usage_ratio": result.new_status.usage_ratio
    }


# ============================================
# Token Counting Endpoints
# ============================================

@router.post(
    "/count-tokens",
    response_model=TokenCountResponse,
    summary="토큰 수 계산",
    description="텍스트의 토큰 수를 계산합니다"
)
async def count_tokens(
    request: TokenCountRequest,
    current_user=Depends(get_current_user)
):
    """Count tokens in provided text"""
    service = get_long_context_service()
    token_count = service.count_tokens(request.text)

    return TokenCountResponse(
        text_length=len(request.text),
        token_count=token_count,
        estimated_cost_ratio=token_count / 1000
    )


@router.get(
    "/estimate-tokens",
    summary="토큰 추정",
    description="텍스트 길이를 기반으로 토큰 수를 추정합니다"
)
async def estimate_tokens(
    text_length: int = Query(..., ge=0, description="텍스트 길이 (문자 수)"),
    language: str = Query("mixed", description="언어 (en, ko, ja, mixed)"),
    current_user=Depends(get_current_user)
):
    """Estimate token count based on text length"""
    # Approximate token ratios by language
    ratios = {
        "en": 4.0,      # ~4 chars per token for English
        "ko": 2.0,      # ~2 chars per token for Korean
        "ja": 1.5,      # ~1.5 chars per token for Japanese
        "mixed": 3.0    # Average for mixed content
    }

    ratio = ratios.get(language, 3.0)
    estimated_tokens = int(text_length / ratio)

    return {
        "text_length": text_length,
        "language": language,
        "estimated_tokens": estimated_tokens,
        "ratio_used": ratio
    }


# ============================================
# Model Information Endpoints
# ============================================

@router.get(
    "/models",
    summary="지원 모델 목록",
    description="지원되는 LLM 모델과 컨텍스트 제한 정보를 조회합니다"
)
async def list_supported_models(
    current_user=Depends(get_current_user)
):
    """List supported models and their context limits"""
    models = []

    for model_name, max_tokens in MODEL_CONTEXT_LIMITS.items():
        if model_name == "default":
            continue

        # Recommended settings
        recommended_response = min(4096, max_tokens // 8)

        models.append(ModelContextInfo(
            model_name=model_name,
            max_context_tokens=max_tokens,
            recommended_usage=0.75,
            recommended_response_reserve=recommended_response
        ))

    return {
        "models": sorted(models, key=lambda m: m.max_context_tokens, reverse=True),
        "default_max_tokens": MODEL_CONTEXT_LIMITS.get("default", 8192)
    }


@router.get(
    "/model/{model_name}",
    response_model=ModelContextInfo,
    summary="모델 컨텍스트 정보",
    description="특정 모델의 컨텍스트 제한 정보를 조회합니다"
)
async def get_model_info(
    model_name: str,
    current_user=Depends(get_current_user)
):
    """Get context limit info for a specific model"""
    max_tokens = get_model_context_limit(model_name)
    recommended_response = min(4096, max_tokens // 8)

    return ModelContextInfo(
        model_name=model_name,
        max_context_tokens=max_tokens,
        recommended_usage=0.75,
        recommended_response_reserve=recommended_response
    )


# ============================================
# Configuration Endpoints
# ============================================

@router.get(
    "/config/default",
    response_model=LLMContextConfig,
    summary="기본 컨텍스트 설정",
    description="현재 기본 컨텍스트 윈도우 설정을 조회합니다"
)
async def get_default_config(
    current_user=Depends(get_current_user)
):
    """Get default context configuration"""
    return LLMContextConfig()


@router.post(
    "/config/calculate",
    summary="컨텍스트 예산 계산",
    description="설정에 따른 사용 가능한 컨텍스트 예산을 계산합니다"
)
async def calculate_context_budget(
    config: LLMContextConfig = Body(...),
    current_user=Depends(get_current_user)
):
    """Calculate available context budget based on configuration"""
    available = config.available_context_tokens

    return {
        "max_context_tokens": config.max_context_tokens,
        "reserved_tokens": {
            "response": config.reserved_for_response,
            "system": config.reserved_for_system,
            "rag": config.reserved_for_rag,
            "tools": config.reserved_for_tools
        },
        "total_reserved": (
            config.reserved_for_response +
            config.reserved_for_system +
            config.reserved_for_rag +
            config.reserved_for_tools
        ),
        "available_for_conversation": available,
        "recommended_message_budget": int(available * 0.7),
        "recommended_summary_budget": int(available * 0.15),
        "buffer": int(available * 0.15)
    }


# ============================================
# Health Check
# ============================================

@router.get(
    "/health",
    summary="컨텍스트 서비스 상태",
    description="컨텍스트 관리 서비스의 상태를 확인합니다"
)
async def context_health_check():
    """Check context management service health"""
    service = get_long_context_service()

    # Test token counting
    test_text = "Hello, this is a test message for token counting."
    token_count = service.count_tokens(test_text)

    return {
        "status": "healthy",
        "tiktoken_available": token_count > 0,
        "default_max_tokens": 32000,
        "supported_models_count": len(MODEL_CONTEXT_LIMITS) - 1  # Exclude 'default'
    }
