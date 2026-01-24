"""
Verified Knowledge API Router

Smarter RAG 시스템의 Verified Knowledge Store 관리 API:
- 검증된 지식 조회/검색
- 학습 배치 관리
- 통계 조회
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.deps import get_current_user, get_admin_user
from ..services.verified_knowledge_service import get_verified_knowledge_service

router = APIRouter(prefix="/verified-knowledge", tags=["verified-knowledge"])


# ============================================
# Pydantic Schemas
# ============================================

class VerifiedKnowledgeResponse(BaseModel):
    """Verified Knowledge 응답 스키마"""
    id: str
    message_id: str
    conversation_id: str
    question: str
    answer: str
    answer_summary: Optional[str] = None
    feedback_score: float
    thumbs_up_count: int
    thumbs_down_count: int
    confidence_score: float
    usage_count: int
    category: Optional[str] = None
    tags: List[str] = []
    language: str = "ko"
    is_trained: bool = False
    trained_at: Optional[datetime] = None
    training_batch_id: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VerifiedKnowledgeSearchResult(BaseModel):
    """검색 결과 스키마"""
    knowledge: VerifiedKnowledgeResponse
    similarity_score: float


class TrainingBatchResponse(BaseModel):
    """학습 배치 응답 스키마"""
    id: str
    batch_id: str
    total_samples: int
    trained_samples: int
    unlearn_samples: int = 0
    unlearned_samples: int = 0
    min_feedback_score: float
    min_thumbs_up: int
    base_model: str
    adapter_name: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    eval_loss: Optional[float] = None
    eval_accuracy: Optional[float] = None
    eval_perplexity: Optional[float] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VerifiedKnowledgeStats(BaseModel):
    """통계 응답 스키마"""
    total_count: int = 0
    active_count: int = 0
    deprecated_count: int = 0
    trained_count: int = 0
    pending_training_count: int = 0
    unlearn_pending_count: int = 0
    avg_feedback_score: float = 0.0
    avg_usage_count: float = 0.0
    total_usage_count: int = 0
    category_count: int = 0
    last_created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None


class CategoryStats(BaseModel):
    """카테고리 통계 스키마"""
    category: str
    count: int
    avg_score: float
    total_usage: int
    trained_count: int


class DailyStats(BaseModel):
    """일별 통계 스키마"""
    date: str
    new_entries: int
    trained_entries: int
    avg_score: float


class TrainingScheduleResponse(BaseModel):
    """학습 스케줄 응답 스키마"""
    id: str
    cron_expression: str
    is_enabled: bool
    last_run_at: Optional[datetime] = None
    last_batch_id: Optional[str] = None
    last_status: Optional[str] = None
    next_run_at: Optional[datetime] = None
    min_samples_required: int
    auto_deploy: bool


class TrainingScheduleUpdate(BaseModel):
    """학습 스케줄 업데이트 스키마"""
    cron_expression: Optional[str] = None
    is_enabled: Optional[bool] = None
    min_samples_required: Optional[int] = None
    auto_deploy: Optional[bool] = None


class CreateTrainingBatchRequest(BaseModel):
    """학습 배치 생성 요청"""
    min_feedback_score: float = Field(default=0.8, ge=0.0, le=1.0)
    min_thumbs_up: int = Field(default=1, ge=1)
    base_model: str = Field(default="Qwen2.5-7B-Instruct")


class TriggerTrainingRequest(BaseModel):
    """수동 학습 트리거 요청"""
    min_feedback_score: float = Field(default=0.8, ge=0.0, le=1.0)
    min_thumbs_up: int = Field(default=1, ge=1)
    limit: int = Field(default=1000, ge=1, le=10000)
    run_async: bool = Field(default=True, description="비동기 실행 여부")


class UpdateCategoryRequest(BaseModel):
    """카테고리 업데이트 요청"""
    category: str = Field(..., min_length=1, max_length=100)


# ============================================
# Helper Functions
# ============================================

def _entity_to_response(entity) -> VerifiedKnowledgeResponse:
    """Entity를 Response로 변환"""
    return VerifiedKnowledgeResponse(
        id=entity.id,
        message_id=entity.message_id,
        conversation_id=entity.conversation_id,
        question=entity.question,
        answer=entity.answer,
        answer_summary=entity.answer_summary,
        feedback_score=entity.feedback_score,
        thumbs_up_count=entity.thumbs_up_count,
        thumbs_down_count=entity.thumbs_down_count,
        confidence_score=entity.confidence_score,
        usage_count=entity.usage_count,
        category=entity.category,
        tags=entity.tags,
        language=entity.language,
        is_trained=entity.is_trained,
        trained_at=entity.trained_at,
        training_batch_id=entity.training_batch_id,
        status=entity.status,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _batch_to_response(batch) -> TrainingBatchResponse:
    """Batch Entity를 Response로 변환"""
    return TrainingBatchResponse(
        id=batch.id,
        batch_id=batch.batch_id,
        total_samples=batch.total_samples,
        trained_samples=batch.trained_samples,
        min_feedback_score=batch.min_feedback_score,
        min_thumbs_up=batch.min_thumbs_up,
        base_model=batch.base_model,
        adapter_name=batch.adapter_name,
        status=batch.status,
        error_message=batch.error_message,
        eval_loss=batch.eval_loss,
        eval_accuracy=batch.eval_accuracy,
        eval_perplexity=batch.eval_perplexity,
        scheduled_at=batch.scheduled_at,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
        created_at=batch.created_at,
    )


# ============================================
# Search Endpoints
# ============================================

@router.get(
    "/search",
    response_model=List[VerifiedKnowledgeSearchResult],
    summary="검증된 지식 검색",
    description="질문에 대해 검증된 지식을 검색합니다. RAG 파이프라인에서 사용됩니다."
)
async def search_verified_knowledge(
    query: str = Query(..., min_length=2, description="검색 쿼리"),
    limit: int = Query(5, ge=1, le=20, description="최대 결과 수"),
    min_similarity: float = Query(0.7, ge=0.0, le=1.0, description="최소 유사도"),
    language: Optional[str] = Query(None, description="언어 필터 (ko, en, ja)"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    user=Depends(get_current_user),
):
    """검증된 지식 검색"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    results = await service.search(
        query=query,
        limit=limit,
        min_similarity=min_similarity,
        language=language,
        category=category,
    )

    return [
        VerifiedKnowledgeSearchResult(
            knowledge=_entity_to_response(entity),
            similarity_score=score,
        )
        for entity, score in results
    ]


# ============================================
# CRUD Endpoints
# ============================================

@router.get(
    "",
    response_model=List[VerifiedKnowledgeResponse],
    summary="검증된 지식 목록",
    description="검증된 지식 목록을 조회합니다."
)
async def list_verified_knowledge(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="상태 필터 (active, deprecated, unlearn_required)"),
    is_trained: Optional[bool] = Query(None, description="학습 완료 여부"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    language: Optional[str] = Query(None, description="언어 필터"),
    min_feedback_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="최소 피드백 점수"),
    user=Depends(get_admin_user),
):
    """검증된 지식 목록 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    entities = await service.list(
        skip=skip,
        limit=limit,
        status=status,
        is_trained=is_trained,
        category=category,
        language=language,
        min_feedback_score=min_feedback_score,
    )

    return [_entity_to_response(e) for e in entities]


@router.get(
    "/{knowledge_id}",
    response_model=VerifiedKnowledgeResponse,
    summary="검증된 지식 상세 조회",
)
async def get_verified_knowledge(
    knowledge_id: str,
    user=Depends(get_admin_user),
):
    """검증된 지식 상세 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    entity = await service.get_by_id(knowledge_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Verified knowledge not found")

    return _entity_to_response(entity)


@router.patch(
    "/{knowledge_id}/category",
    response_model=VerifiedKnowledgeResponse,
    summary="카테고리 업데이트",
)
async def update_category(
    knowledge_id: str,
    request: UpdateCategoryRequest,
    user=Depends(get_admin_user),
):
    """카테고리 업데이트 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    entity = await service.update_category(knowledge_id, request.category)
    if not entity:
        raise HTTPException(status_code=404, detail="Verified knowledge not found")

    return _entity_to_response(entity)


@router.delete(
    "/{knowledge_id}",
    summary="검증된 지식 비활성화",
)
async def deprecate_knowledge(
    knowledge_id: str,
    reason: str = Query(..., min_length=5, description="비활성화 사유"),
    user=Depends(get_admin_user),
):
    """검증된 지식 비활성화 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    success = await service.deprecate(knowledge_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Verified knowledge not found")

    return {"success": True, "message": "Knowledge deprecated successfully"}


# ============================================
# Statistics Endpoints
# ============================================

@router.get(
    "/stats/overview",
    response_model=VerifiedKnowledgeStats,
    summary="전체 통계",
)
async def get_stats(
    user=Depends(get_admin_user),
):
    """전체 통계 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    stats = await service.get_stats()
    return VerifiedKnowledgeStats(**stats)


@router.get(
    "/stats/categories",
    response_model=List[CategoryStats],
    summary="카테고리별 통계",
)
async def get_category_stats(
    user=Depends(get_admin_user),
):
    """카테고리별 통계 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    stats = await service.get_category_stats()
    return [CategoryStats(**s) for s in stats]


@router.get(
    "/stats/daily",
    response_model=List[DailyStats],
    summary="일별 통계",
)
async def get_daily_stats(
    days: int = Query(30, ge=1, le=365, description="조회 기간 (일)"),
    user=Depends(get_admin_user),
):
    """일별 통계 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    stats = await service.get_daily_stats(days=days)
    return [DailyStats(**s) for s in stats]


# ============================================
# Training Management Endpoints
# ============================================

@router.get(
    "/training/batches",
    response_model=List[TrainingBatchResponse],
    summary="학습 배치 목록",
)
async def list_training_batches(
    status: Optional[str] = Query(None, description="상태 필터 (pending, training, completed, failed)"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_admin_user),
):
    """학습 배치 목록 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    batches = await service.get_training_batches(status=status, limit=limit)
    return [_batch_to_response(b) for b in batches]


@router.post(
    "/training/batches",
    response_model=TrainingBatchResponse,
    summary="학습 배치 생성",
    description="새 학습 배치를 생성합니다. 학습 대상 데이터가 없으면 404를 반환합니다."
)
async def create_training_batch(
    request: CreateTrainingBatchRequest,
    user=Depends(get_admin_user),
):
    """학습 배치 생성 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    batch = await service.create_training_batch(
        min_feedback_score=request.min_feedback_score,
        min_thumbs_up=request.min_thumbs_up,
        base_model=request.base_model,
    )

    if not batch:
        raise HTTPException(status_code=404, detail="No samples available for training")

    return _batch_to_response(batch)


@router.get(
    "/training/data",
    summary="학습 데이터 조회",
    description="학습용 데이터를 조회합니다. (Instruction-tuning 형식)"
)
async def get_training_data(
    min_feedback_score: float = Query(0.8, ge=0.0, le=1.0),
    min_thumbs_up: int = Query(1, ge=1),
    limit: int = Query(1000, ge=1, le=10000),
    user=Depends(get_admin_user),
):
    """학습 데이터 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    data = await service.get_training_data(
        min_feedback_score=min_feedback_score,
        min_thumbs_up=min_thumbs_up,
        limit=limit,
    )

    return {
        "count": len(data),
        "data": data,
    }


@router.get(
    "/training/unlearn-data",
    summary="Unlearn 데이터 조회",
    description="제거 대상 데이터를 조회합니다. (👎 받은 학습된 지식)"
)
async def get_unlearn_data(
    limit: int = Query(1000, ge=1, le=10000),
    user=Depends(get_admin_user),
):
    """Unlearn 데이터 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    data = await service.get_unlearn_data(limit=limit)

    return {
        "count": len(data),
        "data": data,
    }


# ============================================
# Training Schedule Endpoints
# ============================================

@router.get(
    "/training/schedule",
    response_model=TrainingScheduleResponse,
    summary="학습 스케줄 조회",
)
async def get_training_schedule(
    user=Depends(get_admin_user),
):
    """학습 스케줄 조회 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    schedule = await service.get_training_schedule()
    if not schedule:
        raise HTTPException(status_code=404, detail="Training schedule not found")

    return TrainingScheduleResponse(**schedule)


@router.patch(
    "/training/schedule",
    response_model=dict,
    summary="학습 스케줄 업데이트",
)
async def update_training_schedule(
    request: TrainingScheduleUpdate,
    user=Depends(get_admin_user),
):
    """학습 스케줄 업데이트 (관리자)"""
    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    success = await service.update_training_schedule(
        cron_expression=request.cron_expression,
        is_enabled=request.is_enabled,
        min_samples_required=request.min_samples_required,
        auto_deploy=request.auto_deploy,
    )

    return {"success": success, "message": "Training schedule updated"}


# ============================================
# Manual Training Trigger (Admin Only)
# ============================================

@router.post(
    "/training/trigger",
    summary="수동 학습 트리거",
    description="관리자가 수동으로 QLoRA 학습을 즉시 시작합니다."
)
async def trigger_training(
    request: TriggerTrainingRequest,
    user=Depends(get_admin_user),
):
    """
    수동 학습 트리거 (관리자 전용)

    - 👍 받은 검증된 지식을 즉시 학습
    - 👎 받은 지식은 모델에서 제거 (unlearn)
    - 비동기 실행 시 바로 응답, 백그라운드에서 학습 진행
    """
    import asyncio
    import subprocess
    from datetime import datetime

    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    # Check available samples
    stats = await service.get_stats()
    training_ready = stats.get("pending_training_count", 0)
    unlearn_pending = stats.get("unlearn_pending_count", 0)

    if training_ready == 0 and unlearn_pending == 0:
        return {
            "success": False,
            "message": "학습할 데이터가 없습니다.",
            "training_ready": training_ready,
            "unlearn_pending": unlearn_pending,
        }

    # Generate batch ID
    batch_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if request.run_async:
        # 비동기 실행: 백그라운드에서 학습 시작
        async def run_training_async():
            try:
                cmd = [
                    "python", "/opt/kms/scripts/training/qlora_trainer.py",
                    "--batch_id", batch_id,
                    "--min_score", str(request.min_feedback_score),
                    "--min_thumbs_up", str(request.min_thumbs_up),
                    "--limit", str(request.limit),
                ]
                subprocess.Popen(
                    cmd,
                    stdout=open(f"/opt/kms/logs/training_{batch_id}.log", "w"),
                    stderr=subprocess.STDOUT,
                    cwd="/opt/kms"
                )
            except Exception as e:
                import logging
                logging.error(f"Failed to start training: {e}")

        asyncio.create_task(run_training_async())

        return {
            "success": True,
            "message": "학습이 백그라운드에서 시작되었습니다.",
            "batch_id": batch_id,
            "training_ready": training_ready,
            "unlearn_pending": unlearn_pending,
            "log_file": f"/opt/kms/logs/training_{batch_id}.log",
            "status": "started",
        }
    else:
        # 동기 실행: 완료될 때까지 대기 (주의: 오래 걸릴 수 있음)
        try:
            batch = await service.create_training_batch(
                min_feedback_score=request.min_feedback_score,
                min_thumbs_up=request.min_thumbs_up,
            )

            return {
                "success": True,
                "message": "학습 배치가 생성되었습니다. 실제 학습은 스케줄러에서 실행됩니다.",
                "batch_id": batch.batch_id if batch else None,
                "training_ready": training_ready,
                "unlearn_pending": unlearn_pending,
                "status": "batch_created",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/training/status/{batch_id}",
    summary="학습 상태 조회",
)
async def get_training_status(
    batch_id: str,
    user=Depends(get_admin_user),
):
    """특정 배치의 학습 상태 조회"""
    import os

    service = get_verified_knowledge_service()
    if not service:
        raise HTTPException(status_code=503, detail="Verified Knowledge service not available")

    # Get batch info from DB
    batches = await service.get_training_batches(limit=100)
    batch = next((b for b in batches if b.batch_id == batch_id), None)

    if not batch:
        raise HTTPException(status_code=404, detail="Training batch not found")

    # Check log file
    log_file = f"/opt/kms/logs/training_{batch_id}.log"
    log_tail = ""
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            log_tail = "".join(lines[-20:])  # Last 20 lines

    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "total_samples": batch.total_samples,
        "trained_samples": batch.trained_samples,
        "adapter_name": batch.adapter_name,
        "started_at": batch.started_at,
        "completed_at": batch.completed_at,
        "error_message": batch.error_message,
        "eval_loss": batch.eval_loss,
        "log_tail": log_tail,
    }


@router.get(
    "/training/logs/{batch_id}",
    summary="학습 로그 조회",
)
async def get_training_logs(
    batch_id: str,
    lines: int = Query(100, ge=1, le=1000),
    user=Depends(get_admin_user),
):
    """학습 로그 파일 조회"""
    import os

    log_file = f"/opt/kms/logs/training_{batch_id}.log"

    if not os.path.exists(log_file):
        raise HTTPException(status_code=404, detail="Log file not found")

    with open(log_file, "r") as f:
        all_lines = f.readlines()
        return {
            "batch_id": batch_id,
            "total_lines": len(all_lines),
            "lines": all_lines[-lines:],
        }


# ============================================
# Learning LLM Endpoints
# ============================================


class LearningLLMGenerateRequest(BaseModel):
    """Learning LLM 생성 요청"""
    question: str = Field(..., description="사용자 질문")
    context: Optional[str] = Field(None, description="추가 컨텍스트")
    max_tokens: int = Field(512, ge=64, le=2048, description="최대 토큰 수")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="샘플링 온도")


class LearningLLMReloadRequest(BaseModel):
    """Learning LLM 어댑터 리로드 요청"""
    adapter_name: Optional[str] = Field(None, description="어댑터 이름 (None=최신)")


@router.get(
    "/learning-llm/status",
    summary="Learning LLM 상태 조회",
    description="Learning LLM 서비스의 현재 상태와 로드된 어댑터 정보를 반환합니다.",
)
async def get_learning_llm_status(
    user=Depends(get_current_user),
):
    """Learning LLM 서비스 상태 조회"""
    from ..services.learning_llm_service import get_learning_llm_service

    service = get_learning_llm_service()
    if not service:
        return {
            "enabled": False,
            "message": "Learning LLM service not initialized",
        }

    return service.get_status()


@router.post(
    "/learning-llm/generate",
    summary="Learning LLM 응답 생성",
    description="Learning LLM을 사용하여 응답을 생성합니다 (테스트용).",
)
async def generate_with_learning_llm(
    request: LearningLLMGenerateRequest,
    user=Depends(get_current_user),
):
    """Learning LLM으로 응답 생성"""
    from ..services.learning_llm_service import get_learning_llm_service

    service = get_learning_llm_service()
    if not service or not service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Learning LLM service not available"
        )

    result = await service.generate(
        question=request.question,
        context=request.context,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate response"
        )

    return result


@router.post(
    "/learning-llm/reload",
    summary="Learning LLM 어댑터 리로드",
    description="새 어댑터를 로드하거나 최신 어댑터로 리로드합니다.",
)
async def reload_learning_llm(
    request: LearningLLMReloadRequest,
    user=Depends(get_admin_user),
):
    """Learning LLM 어댑터 리로드 (관리자 전용)"""
    from ..services.learning_llm_service import get_learning_llm_service

    service = get_learning_llm_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Learning LLM service not initialized"
        )

    success = await service.reload_adapter(request.adapter_name)

    return {
        "success": success,
        "adapter_name": request.adapter_name or "latest",
        "status": service.get_status() if success else None,
    }


@router.post(
    "/learning-llm/unload",
    summary="Learning LLM 언로드",
    description="메모리에서 Learning LLM을 언로드합니다.",
)
async def unload_learning_llm(
    user=Depends(get_admin_user),
):
    """Learning LLM 언로드 (관리자 전용)"""
    from ..services.learning_llm_service import get_learning_llm_service

    service = get_learning_llm_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Learning LLM service not initialized"
        )

    await service.unload()

    return {
        "success": True,
        "message": "Learning LLM unloaded",
    }


@router.post(
    "/learning-llm/can-answer",
    summary="Learning LLM 응답 가능 여부 확인",
    description="해당 질문에 Learning LLM이 응답할 수 있는지 확인합니다.",
)
async def check_can_answer(
    question: str = Query(..., description="확인할 질문"),
    user=Depends(get_current_user),
):
    """Learning LLM 응답 가능 여부 확인"""
    from ..services.learning_llm_service import get_learning_llm_service

    service = get_learning_llm_service()
    if not service or not service.enabled:
        return {
            "can_answer": False,
            "confidence": 0.0,
            "reason": "Learning LLM service not available",
        }

    vk_service = get_verified_knowledge_service()
    can_answer, hint, confidence = await service.can_answer(
        question=question,
        verified_knowledge_service=vk_service,
    )

    return {
        "question": question,
        "can_answer": can_answer,
        "confidence": confidence,
        "has_related_knowledge": hint is not None,
    }


@router.get(
    "/learning-llm/vllm-test",
    summary="vLLM 서버 연결 테스트",
    description="외부 vLLM 서버(Docker 컨테이너)에 대한 연결을 테스트합니다.",
)
async def test_vllm_connection(
    user=Depends(get_current_user),
):
    """vLLM 서버 연결 테스트"""
    import os
    from ..adapters.learning_llm.vllm_adapter import VLLMAdapter

    base_url = os.getenv("LEARNING_LLM_URL", "http://learning-llm-graphrag:8000/v1")
    model = os.getenv("LEARNING_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")

    adapter = VLLMAdapter(base_url=base_url, model=model)
    health = await adapter.health_check()

    return {
        "vllm_url": base_url,
        "model": model,
        "health": health,
    }


@router.post(
    "/learning-llm/vllm-generate",
    summary="vLLM 서버 응답 생성 테스트",
    description="외부 vLLM 서버를 통해 응답을 생성합니다 (테스트용).",
)
async def test_vllm_generate(
    request: LearningLLMGenerateRequest,
    user=Depends(get_current_user),
):
    """vLLM 서버 응답 생성 테스트"""
    import os
    from ..adapters.learning_llm.vllm_adapter import VLLMAdapter

    base_url = os.getenv("LEARNING_LLM_URL", "http://learning-llm-graphrag:8000/v1")
    model = os.getenv("LEARNING_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")

    adapter = VLLMAdapter(base_url=base_url, model=model)

    # Health check first
    health = await adapter.health_check()
    if health.get("status") != "healthy":
        raise HTTPException(
            status_code=503,
            detail=f"vLLM server not healthy: {health}"
        )

    # Generate response
    response = await adapter.generate(
        question=request.question,
        context=request.context,
        max_new_tokens=request.max_tokens,
        temperature=request.temperature,
    )

    if not response:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate response from vLLM"
        )

    return {
        "answer": response,
        "source": "vllm",
        "model": model,
        "url": base_url,
    }


# ============================================
# Monitoring Endpoints
# ============================================


@router.get(
    "/monitor/metrics",
    summary="Smarter RAG 메트릭 조회",
    description="Smarter RAG 시스템의 현재 메트릭을 반환합니다.",
)
async def get_monitoring_metrics(
    refresh: bool = Query(False, description="캐시 무시하고 새로 수집"),
    user=Depends(get_current_user),
):
    """Smarter RAG 메트릭 조회"""
    from ..services.smarter_rag_monitor import get_smarter_rag_monitor

    monitor = get_smarter_rag_monitor()
    metrics = await monitor.get_metrics(force_refresh=refresh)

    return metrics.to_dict()


@router.get(
    "/monitor/health",
    summary="Smarter RAG 헬스 상태",
    description="Smarter RAG 시스템의 헬스 상태를 반환합니다.",
)
async def get_monitoring_health(
    user=Depends(get_current_user),
):
    """Smarter RAG 헬스 상태 조회"""
    from ..services.smarter_rag_monitor import get_smarter_rag_monitor

    monitor = get_smarter_rag_monitor()
    return await monitor.get_health_status()


@router.get(
    "/monitor/dashboard",
    summary="Smarter RAG 대시보드 데이터",
    description="대시보드에 표시할 Smarter RAG 데이터를 반환합니다.",
)
async def get_monitoring_dashboard(
    user=Depends(get_current_user),
):
    """대시보드용 데이터 조회"""
    from ..services.smarter_rag_monitor import get_smarter_rag_monitor

    monitor = get_smarter_rag_monitor()
    return await monitor.get_dashboard_data()
