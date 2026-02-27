"""
OpenFrame LLM Adapters

TRT-LLM NIM 기반 OpenFrame 8제품 전용 LLM 어댑터 모듈
"""
from .trtllm_adapter import (
    TRTLLMAdapter,
    get_trtllm_adapter,
    initialize_trtllm_adapter,
)

__all__ = [
    "TRTLLMAdapter",
    "get_trtllm_adapter",
    "initialize_trtllm_adapter",
]
