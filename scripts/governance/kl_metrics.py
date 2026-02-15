#!/usr/bin/env python3
"""
KL Divergence Calculation Module.

Provides token-level and sequence-level KL divergence measurement
between base and fine-tuned models. GPU-compatible with batch support.

Formula: KL(P||Q) = Σ P(x) log(P(x)/Q(x))

Usage:
    from scripts.governance.kl_metrics import KLMetricsCalculator
    calc = KLMetricsCalculator(device="cuda:4")
    result = calc.compute_from_models(model, ref_model, tokenizer, texts)
"""

import math
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional

import numpy as np
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


@dataclass
class KLResult:
    """KL divergence computation result."""
    mean_kl: float
    max_kl: float
    min_kl: float
    std_kl: float
    median_kl: float
    num_samples: int
    histogram_bins: List[float]
    histogram_counts: List[int]
    per_sample_kl: List[float]
    token_level_stats: Optional[Dict] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        if d["token_level_stats"] is None:
            d["token_level_stats"] = {}
        return d

    @property
    def is_diverged(self) -> bool:
        return self.mean_kl > 10.0

    @property
    def is_unstable(self) -> bool:
        return self.mean_kl > 5.0


class KLMetricsCalculator:
    """GPU-compatible KL divergence calculator with batch support."""

    def __init__(
        self,
        device: str = "cuda",
        max_length: int = 1024,
        batch_size: int = 4,
        num_histogram_bins: int = 50,
    ):
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self.num_histogram_bins = num_histogram_bins

    def compute_token_kl(
        self,
        model_logits: torch.Tensor,
        ref_logits: torch.Tensor,
    ) -> torch.Tensor:
        """
        Token-level KL divergence: KL(model || ref).

        Args:
            model_logits: [batch, seq_len, vocab_size]
            ref_logits:   [batch, seq_len, vocab_size]

        Returns:
            Token-level KL values: [batch, seq_len]
        """
        model_log_probs = F.log_softmax(model_logits, dim=-1)
        ref_log_probs = F.log_softmax(ref_logits, dim=-1)

        # KL(P||Q) = Σ P(x) * (log P(x) - log Q(x))
        model_probs = model_log_probs.exp()
        kl_per_token = (model_probs * (model_log_probs - ref_log_probs)).sum(dim=-1)

        return kl_per_token

    def compute_sequence_kl(
        self,
        model_logits: torch.Tensor,
        ref_logits: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> Tuple[float, Dict]:
        """
        Sequence-level average KL divergence.

        Returns:
            (mean_kl, token_stats_dict)
        """
        token_kl = self.compute_token_kl(model_logits, ref_logits)

        if attention_mask is not None:
            # attention_mask에서 마지막 토큰 제외 (labels shift)
            mask = attention_mask[:, 1:].float()
            if mask.shape[1] > token_kl.shape[1]:
                mask = mask[:, :token_kl.shape[1]]
            elif mask.shape[1] < token_kl.shape[1]:
                token_kl = token_kl[:, :mask.shape[1]]

            masked_kl = token_kl * mask
            seq_kl = masked_kl.sum(dim=-1) / mask.sum(dim=-1).clamp(min=1)
        else:
            seq_kl = token_kl.mean(dim=-1)

        token_stats = {
            "token_kl_mean": float(token_kl.mean().item()),
            "token_kl_max": float(token_kl.max().item()),
            "token_kl_std": float(token_kl.std().item()),
        }

        return float(seq_kl.mean().item()), token_stats

    def compute_from_models(
        self,
        model: torch.nn.Module,
        ref_model: torch.nn.Module,
        tokenizer,
        texts: List[str],
    ) -> KLResult:
        """
        Full KL divergence evaluation between two models on a text corpus.

        Args:
            model: Fine-tuned model (CPT or DPO)
            ref_model: Reference/base model
            tokenizer: Shared tokenizer
            texts: Evaluation texts

        Returns:
            KLResult with all statistics
        """
        model.eval()
        ref_model.eval()

        per_sample_kl = []
        all_token_stats = []

        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i:i + self.batch_size]

                encodings = tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self.max_length,
                    padding=True,
                )
                input_ids = encodings["input_ids"].to(model.device)
                attention_mask = encodings["attention_mask"].to(model.device)

                # 모델 forward
                model_outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                )
                # logits shift: 마지막 토큰 예측 제외
                model_logits = model_outputs.logits[:, :-1, :]

                # 레퍼런스 모델 forward
                ref_input_ids = input_ids.to(ref_model.device)
                ref_mask = attention_mask.to(ref_model.device)
                ref_outputs = ref_model(
                    input_ids=ref_input_ids,
                    attention_mask=ref_mask,
                )
                ref_logits = ref_outputs.logits[:, :-1, :]

                # 디바이스 통일
                if ref_logits.device != model_logits.device:
                    ref_logits = ref_logits.to(model_logits.device)

                # 시퀀스 KL 계산
                token_kl = self.compute_token_kl(model_logits, ref_logits)
                shifted_mask = attention_mask[:, 1:]
                if shifted_mask.shape[1] > token_kl.shape[1]:
                    shifted_mask = shifted_mask[:, :token_kl.shape[1]]

                for j in range(token_kl.shape[0]):
                    valid_mask = shifted_mask[j].bool()
                    valid_kl = token_kl[j][valid_mask[:token_kl.shape[1]]]
                    sample_kl = float(valid_kl.mean().item()) if len(valid_kl) > 0 else 0.0
                    per_sample_kl.append(sample_kl)

                _, token_stats = self.compute_sequence_kl(
                    model_logits, ref_logits, attention_mask
                )
                all_token_stats.append(token_stats)

                if (i // self.batch_size) % 10 == 0:
                    logger.info(
                        f"KL progress: {min(i + self.batch_size, len(texts))}/{len(texts)}"
                    )

        # 집계
        kl_array = np.array(per_sample_kl)
        histogram_counts, histogram_edges = np.histogram(
            kl_array, bins=self.num_histogram_bins
        )

        # 토큰 레벨 통합 통계
        token_level_stats = {}
        if all_token_stats:
            token_level_stats = {
                "token_kl_mean": float(np.mean([s["token_kl_mean"] for s in all_token_stats])),
                "token_kl_max": float(np.max([s["token_kl_max"] for s in all_token_stats])),
                "token_kl_std": float(np.mean([s["token_kl_std"] for s in all_token_stats])),
            }

        return KLResult(
            mean_kl=float(kl_array.mean()),
            max_kl=float(kl_array.max()),
            min_kl=float(kl_array.min()),
            std_kl=float(kl_array.std()),
            median_kl=float(np.median(kl_array)),
            num_samples=len(per_sample_kl),
            histogram_bins=[float(e) for e in histogram_edges.tolist()],
            histogram_counts=[int(c) for c in histogram_counts.tolist()],
            per_sample_kl=[float(k) for k in per_sample_kl],
            token_level_stats=token_level_stats,
        )

    def compute_from_logits_batch(
        self,
        model_logits_list: List[torch.Tensor],
        ref_logits_list: List[torch.Tensor],
    ) -> KLResult:
        """
        Batch KL 계산 (사전 추출된 logits 사용).
        모델 로딩 없이 저장된 logits에서 계산할 때 사용.
        """
        per_sample_kl = []

        for m_logits, r_logits in zip(model_logits_list, ref_logits_list):
            token_kl = self.compute_token_kl(
                m_logits.unsqueeze(0), r_logits.unsqueeze(0)
            )
            per_sample_kl.append(float(token_kl.mean().item()))

        kl_array = np.array(per_sample_kl)
        histogram_counts, histogram_edges = np.histogram(
            kl_array, bins=self.num_histogram_bins
        )

        return KLResult(
            mean_kl=float(kl_array.mean()),
            max_kl=float(kl_array.max()),
            min_kl=float(kl_array.min()),
            std_kl=float(kl_array.std()),
            median_kl=float(np.median(kl_array)),
            num_samples=len(per_sample_kl),
            histogram_bins=[float(e) for e in histogram_edges.tolist()],
            histogram_counts=[int(c) for c in histogram_counts.tolist()],
            per_sample_kl=[float(k) for k in per_sample_kl],
        )
