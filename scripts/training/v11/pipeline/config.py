"""Pipeline configuration loaded from YAML."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class GenerationConfig:
    """All configurable parameters for the pipeline."""

    # Target sizes
    target_sft_size: int = 150000
    target_dpo_size: int = 15000
    include_cpt: bool = True

    # Chunking
    chunk_size: int = 1200
    max_chunk_size: int = 2000
    min_chunk_size: int = 200
    cpt_max_chunk_tokens: int = 4096

    # SFT distribution
    sft_single_product_ratio: float = 0.50
    sft_comparison_ratio: float = 0.30
    sft_architecture_ratio: float = 0.20

    # QA generation
    qa_variants_per_item: int = 5
    qa_min_answer_length: int = 50
    qa_max_answer_length: int = 3000

    # Cross-product comparison
    comparison_questions_per_pair: int = 100
    comparison_min_shared_features: int = 2
    comparison_cluster_boost: float = 1.5

    # Architecture
    architecture_categories: List[str] = field(
        default_factory=lambda: [
            "ecosystem_overview",
            "shared_components",
            "security_model",
            "integration_strategy",
            "deployment_architecture",
            "performance_tuning",
            "migration_strategy",
        ]
    )

    # DPO strategy ratios
    dpo_cross_product_ratio: float = 0.30
    dpo_fact_mutation_ratio: float = 0.30
    dpo_over_claiming_ratio: float = 0.20
    dpo_speculative_ratio: float = 0.20

    # Quality
    dedup_threshold: float = 0.95
    max_token_length: int = 4096
    train_eval_split: float = 0.80

    # Languages
    primary_language: str = "ja"
    secondary_languages: List[str] = field(default_factory=lambda: ["ko", "en"])

    # Performance
    max_workers: int = 4
    batch_size: int = 1000

    # Paths
    manuals_dir: str = "uploads/manuals"
    output_dir: str = "dataset_pipeline/output"

    # System prompt
    system_prompt_template: str = (
        "You are a professional enterprise product expert "
        "for TmaxSoft products. Answer accurately based on "
        "official product documentation."
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "GenerationConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not (0.0 < self.train_eval_split < 1.0):
            errors.append("train_eval_split must be between 0 and 1")
        sft_sum = (
            self.sft_single_product_ratio
            + self.sft_comparison_ratio
            + self.sft_architecture_ratio
        )
        if abs(sft_sum - 1.0) > 0.01:
            errors.append(f"SFT ratios must sum to 1.0, got {sft_sum:.2f}")
        dpo_sum = (
            self.dpo_cross_product_ratio
            + self.dpo_fact_mutation_ratio
            + self.dpo_over_claiming_ratio
            + self.dpo_speculative_ratio
        )
        if abs(dpo_sum - 1.0) > 0.01:
            errors.append(f"DPO ratios must sum to 1.0, got {dpo_sum:.2f}")
        if not Path(self.manuals_dir).exists():
            errors.append(f"manuals_dir not found: {self.manuals_dir}")
        return errors

    @property
    def all_languages(self) -> List[str]:
        return [self.primary_language] + self.secondary_languages
