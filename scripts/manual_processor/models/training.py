"""학습 데이터 모델

SFT (ChatML), CPT (Plain Text), DPO (Preference Pairs) 학습 데이터 구조 정의.
Qwen2.5 ChatML 포맷 호환.

통합 LoRA용 모델 (UnifiedSFTRecord, UnifiedDPORecord) 포함.
제품별 LoRA = 깊이(depth), 통합 LoRA = 관계(relations).
"""

import json
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class TrainingFormat(str, Enum):
    SFT = "sft"
    CPT = "cpt"
    DPO = "dpo"


class DataLanguage(str, Enum):
    JA = "ja"
    KO = "ko"
    EN = "en"


@dataclass
class SFTRecord:
    """SFT 학습 데이터 레코드 (ChatML 포맷)"""
    instruction: str
    response: str
    system_prompt: str
    product: str
    language: DataLanguage
    source_file: str
    source_page: int = 0
    item_type: str = ""  # error/command/config/api/concept

    def to_chatml(self) -> str:
        """Qwen2.5 ChatML 포맷 변환"""
        return (
            f"<|im_start|>system\n{self.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{self.instruction}<|im_end|>\n"
            f"<|im_start|>assistant\n{self.response}<|im_end|>"
        )

    def to_jsonl(self) -> dict:
        return {
            "text": self.to_chatml(),
            "product": self.product,
            "language": self.language.value,
            "source": self.source_file,
            "type": self.item_type,
        }


@dataclass
class DPORecord:
    """DPO 학습 데이터 레코드 (Preference Pair)"""
    prompt: str
    chosen: str
    rejected: str
    product: str
    language: DataLanguage
    strategy: str  # cross_product / fact_mutation / summary_cross

    def to_jsonl(self) -> dict:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "product": self.product,
            "language": self.language.value,
            "strategy": self.strategy,
        }


@dataclass
class UnifiedSFTRecord:
    """통합 LoRA용 SFT 레코드 - 제품 간 관계 Q-A"""
    instruction: str              # 사용자 질문 (2+ 제품 언급)
    response: str                 # 관계를 설명하는 답변
    system_prompt: str            # 통합 시스템 프롬프트
    products_involved: List[str]  # 관련 제품 ID 목록 (2개 이상)
    relation_type: str            # R-01 ~ R-07
    language: DataLanguage
    source: str                   # "pdf_xref" | "relation_table" | "seed"
    source_file: str = ""
    source_page: int = 0

    def to_chatml(self) -> str:
        """Qwen2.5 ChatML 포맷 변환"""
        return (
            f"<|im_start|>system\n{self.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{self.instruction}<|im_end|>\n"
            f"<|im_start|>assistant\n{self.response}<|im_end|>"
        )

    def to_jsonl(self) -> dict:
        return {
            "text": self.to_chatml(),
            "products": self.products_involved,
            "relation_type": self.relation_type,
            "language": self.language.value,
            "source": self.source,
        }


@dataclass
class UnifiedDPORecord:
    """통합 LoRA용 DPO 레코드 - 통합 vs 편향 preference"""
    prompt: str                   # 제품 간 관계 질문
    chosen: str                   # 전체 관계를 설명하는 정확한 답변
    rejected: str                 # 단일 제품만 언급하거나 불완전한 답변
    products_involved: List[str]  # 관련 제품 ID 목록
    relation_type: str            # R-01 ~ R-07
    language: DataLanguage
    strategy: str                 # unified_vs_biased / complete_vs_partial / correct_order_vs_wrong

    def to_jsonl(self) -> dict:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "products": self.products_involved,
            "relation_type": self.relation_type,
            "language": self.language.value,
            "strategy": self.strategy,
        }


@dataclass
class CPTChunk:
    """CPT 학습 데이터 청크 (Plain Text)"""
    text: str
    product: str
    language: DataLanguage
    source_file: str
    token_count: int = 0


@dataclass
class TrainingStats:
    """학습 데이터 생성/검증 통계"""
    total_records: int = 0
    by_format: Dict[str, int] = field(default_factory=dict)
    by_language: Dict[str, int] = field(default_factory=dict)
    by_product: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    train_count: int = 0
    eval_count: int = 0
    quality_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "by_format": self.by_format,
            "by_language": self.by_language,
            "by_product": self.by_product,
            "by_type": self.by_type,
            "train_count": self.train_count,
            "eval_count": self.eval_count,
            "quality_score": self.quality_score,
        }
