"""
Learning LLM Adapter Package

QLoRA 파인튜닝된 모델을 사용하여 Verified Knowledge 기반 추론을 수행합니다.

Adapter 모드:
- vLLM (권장): VLLMAdapter - 외부 vLLM 컨테이너 연결
- Local: LearningLLMAdapter - 로컬 GPU에서 직접 로딩 (peft 필요)
"""
# Lazy imports to avoid peft dependency when using vLLM
# Import explicitly when needed:
#   from .vllm_adapter import VLLMAdapter
#   from .adapter import LearningLLMAdapter

__all__ = [
    "VLLMAdapter",
    "LearningLLMAdapter",
]


def get_vllm_adapter():
    """Get vLLM adapter (no peft required)"""
    from .vllm_adapter import get_vllm_adapter as _get
    return _get()


def get_learning_llm_adapter():
    """Get local adapter (requires peft)"""
    from .adapter import get_learning_llm_adapter as _get
    return _get()
