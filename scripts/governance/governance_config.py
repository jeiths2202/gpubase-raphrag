#!/usr/bin/env python3
"""
Central Configuration Schema for Governance System.

All thresholds, product definitions, and pipeline settings
are defined here. Supports JSON serialization for CI/CD integration.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum
import json
from pathlib import Path


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class StabilityStatus(str, Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    DIVERGED = "diverged"


class DriftLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ──────────────────────────────────────────────
# Product Registry
# ──────────────────────────────────────────────

PRODUCT_REGISTRY: List[Dict[str, str]] = [
    {"id": "jeus_v2", "name": "JEUS 8.5", "category": "WAS", "lang": "ko"},
    {"id": "tibero7_v2", "name": "Tibero 7", "category": "Database", "lang": "ko"},
    {"id": "ofpli_v2", "name": "OF PL/I Compiler", "category": "Compiler", "lang": "ja"},
    {"id": "openframe_aim_v2", "name": "OF AIM", "category": "OpenFrame", "lang": "ja"},
    {"id": "prosync_v2", "name": "ProSync", "category": "Utility", "lang": "ko"},
    {"id": "protrieve_v2", "name": "Protrieve", "category": "Utility", "lang": "ko"},
    {"id": "openframe_hidb_v2", "name": "OF HiDB", "category": "OpenFrame", "lang": "ja"},
    {"id": "openframe_tacf_v2", "name": "OF TACF", "category": "OpenFrame", "lang": "ko"},
    {"id": "openframe_vos3_v2", "name": "OF VOS3", "category": "OpenFrame", "lang": "ja"},
    {"id": "ofmanager_v2", "name": "OF Manager", "category": "OpenFrame", "lang": "ko"},
    {"id": "openframe_base_v2", "name": "OF Base", "category": "OpenFrame", "lang": "ja"},
    {"id": "ofcobol_v2", "name": "OF COBOL", "category": "Compiler", "lang": "ko"},
    {"id": "openframe_common_v2", "name": "OF Common", "category": "OpenFrame", "lang": "ja"},
    {"id": "webtob_v2", "name": "WebtoB", "category": "WebServer", "lang": "ko"},
    {"id": "openframe_batch_v2", "name": "OF Batch", "category": "OpenFrame", "lang": "ja"},
    {"id": "prosort_v2", "name": "ProSort", "category": "Utility", "lang": "ko"},
    {"id": "openframe_osc_v2", "name": "OF OSC", "category": "OpenFrame", "lang": "ja"},
    {"id": "ofstudio_v2", "name": "OF Studio", "category": "IDE", "lang": "ko"},
    {"id": "openframe_osi_v2", "name": "OF OSI", "category": "OpenFrame", "lang": "ja"},
    {"id": "tmax_v2", "name": "Tmax", "category": "TP Monitor", "lang": "ko"},
    {"id": "ofminer_v2", "name": "OF Miner", "category": "Utility", "lang": "ko"},
    {"id": "openframe_gateway_v2", "name": "OF Gateway", "category": "OpenFrame", "lang": "ja"},
]

ALL_PRODUCT_IDS = [p["id"] for p in PRODUCT_REGISTRY]


# ──────────────────────────────────────────────
# Threshold Configs
# ──────────────────────────────────────────────

@dataclass
class KLThresholds:
    """KL divergence thresholds."""
    warn: float = 5.0
    fail: float = 10.0
    critical: float = 15.0
    max_std: float = 3.0


@dataclass
class HallucinationThresholds:
    """Hallucination detection thresholds."""
    max_rate: float = 0.05           # 5% 이하
    min_citation_ratio: float = 0.8  # 80% 이상 인용 포함
    max_fabrication_score: float = 0.1
    confidence_threshold: float = 0.7


@dataclass
class PerplexityThresholds:
    """Perplexity change thresholds."""
    max_increase_pct: float = 10.0   # 10% 이상 악화 시 fail
    warn_increase_pct: float = 5.0


@dataclass
class DriftThresholds:
    """Drift detection thresholds."""
    z_score_warn: float = 2.0
    z_score_critical: float = 3.0
    moving_avg_window: int = 10
    min_history_points: int = 5


@dataclass
class BetaTuningConfig:
    """DPO beta auto-tuning configuration."""
    initial_beta: float = 0.1
    min_beta: float = 0.01
    max_beta: float = 0.5
    adjustment_step: float = 0.02
    kl_target: float = 5.0
    reward_margin_min: float = 0.5


@dataclass
class QualityGateConfig:
    """Unified quality gate configuration."""
    kl: KLThresholds = field(default_factory=KLThresholds)
    hallucination: HallucinationThresholds = field(default_factory=HallucinationThresholds)
    perplexity: PerplexityThresholds = field(default_factory=PerplexityThresholds)
    drift: DriftThresholds = field(default_factory=DriftThresholds)
    beta_tuning: BetaTuningConfig = field(default_factory=BetaTuningConfig)
    min_task_score: float = 0.7          # 70% 이상
    min_eval_samples: int = 5
    require_all_products_pass: bool = True


@dataclass
class GovernanceConfig:
    """Top-level governance configuration."""
    # Model
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"
    cpt_model: str = "Qwen/Qwen2.5-72B-Instruct"
    # Paths
    adapter_base_dir: str = "/raid/users/ofuser/qlora/outputs"
    dataset_base_dir: str = "uploads/summaries/multi_lora_v9"
    governance_output_dir: str = "/raid/users/ofuser/qlora/governance"
    metrics_db_path: str = "/raid/users/ofuser/qlora/governance/metrics.db"
    # Products
    products: List[str] = field(default_factory=lambda: ALL_PRODUCT_IDS.copy())
    # Gates
    quality_gate: QualityGateConfig = field(default_factory=QualityGateConfig)
    # GPU
    gpu_ids: List[int] = field(default_factory=lambda: [4, 5, 6, 7])
    # Pipeline
    max_retries: int = 2
    parallel_eval: bool = True
    auto_deploy: bool = False  # 수동 승인 필요

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "GovernanceConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        # 중첩 dataclass 복원
        qg = data.pop("quality_gate", {})
        config = cls(**{k: v for k, v in data.items() if k != "quality_gate"})
        config.quality_gate = QualityGateConfig(
            kl=KLThresholds(**qg.get("kl", {})),
            hallucination=HallucinationThresholds(**qg.get("hallucination", {})),
            perplexity=PerplexityThresholds(**qg.get("perplexity", {})),
            drift=DriftThresholds(**qg.get("drift", {})),
            beta_tuning=BetaTuningConfig(**qg.get("beta_tuning", {})),
            min_task_score=qg.get("min_task_score", 0.7),
            min_eval_samples=qg.get("min_eval_samples", 5),
            require_all_products_pass=qg.get("require_all_products_pass", True),
        )
        return config
