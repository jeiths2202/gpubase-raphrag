"""Dataset quality validation."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List, Tuple

import numpy as np

from .config import GenerationConfig
from .models import CPTChunk, DPORecord, DatasetStats, SFTRecord

logger = logging.getLogger(__name__)


class Validator:
    """Validate dataset quality."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def validate_all(
        self,
        sft_records: List[SFTRecord],
        dpo_records: List[DPORecord],
    ) -> Tuple[bool, List[str]]:
        """Run all validation checks."""
        errors: List[str] = []

        errors.extend(self.check_format(sft_records))
        errors.extend(self.check_dpo_format(dpo_records))

        token_errors = self.check_token_lengths(sft_records)
        errors.extend(token_errors)

        errors.extend(self.check_distribution(sft_records))
        errors.extend(self.check_min_counts(sft_records, dpo_records))

        passed = len(errors) == 0
        if passed:
            logger.info("Validation PASSED: all checks OK")
        else:
            logger.warning("Validation FAILED: %d errors", len(errors))
            for e in errors:
                logger.warning("  - %s", e)

        return passed, errors

    def check_format(self, records: List[SFTRecord]) -> List[str]:
        """Validate JSON structure of every SFT record."""
        errors: List[str] = []
        valid_roles = {"system", "user", "assistant"}

        for i, rec in enumerate(records):
            if not rec.messages:
                errors.append(f"SFT[{i}]: empty messages")
                continue

            # Must have at least system + user + assistant
            if len(rec.messages) < 3:
                errors.append(
                    f"SFT[{i}]: messages has {len(rec.messages)} entries (need >= 3)"
                )

            for j, msg in enumerate(rec.messages):
                if "role" not in msg:
                    errors.append(f"SFT[{i}].messages[{j}]: missing 'role'")
                elif msg["role"] not in valid_roles:
                    errors.append(
                        f"SFT[{i}].messages[{j}]: invalid role '{msg['role']}'"
                    )

                if "content" not in msg:
                    errors.append(f"SFT[{i}].messages[{j}]: missing 'content'")
                elif not msg["content"].strip():
                    errors.append(
                        f"SFT[{i}].messages[{j}]: empty content (role={msg.get('role', '?')})"
                    )

            if len(errors) > 100:
                errors.append("... truncated (too many format errors)")
                break

        return errors

    def check_dpo_format(self, records: List[DPORecord]) -> List[str]:
        """Validate DPO record structure."""
        errors: List[str] = []

        for i, rec in enumerate(records):
            if not rec.prompt.strip():
                errors.append(f"DPO[{i}]: empty prompt")
            if not rec.chosen.strip():
                errors.append(f"DPO[{i}]: empty chosen")
            if not rec.rejected.strip():
                errors.append(f"DPO[{i}]: empty rejected")
            if rec.chosen == rec.rejected:
                errors.append(f"DPO[{i}]: chosen == rejected")

            if len(errors) > 100:
                errors.append("... truncated")
                break

        return errors

    def check_token_lengths(self, records: List[SFTRecord]) -> List[str]:
        """Compute token length distribution and flag violations."""
        errors: List[str] = []
        if not records:
            return errors

        # Approximate token count (chars / 3 for CJK, / 4 for English)
        lengths = []
        for rec in records:
            total_chars = sum(len(m.get("content", "")) for m in rec.messages)
            # Rough token estimate (CJK-heavy content)
            estimated_tokens = total_chars // 3
            lengths.append(estimated_tokens)

        arr = np.array(lengths)
        p50 = int(np.percentile(arr, 50))
        p95 = int(np.percentile(arr, 95))
        p99 = int(np.percentile(arr, 99))
        max_len = int(arr.max())

        logger.info(
            "Token lengths: p50=%d, p95=%d, p99=%d, max=%d",
            p50, p95, p99, max_len,
        )

        over_limit = int(np.sum(arr > self.config.max_token_length))
        if over_limit > 0:
            pct = over_limit / len(records) * 100
            if pct > 5.0:
                errors.append(
                    f"Token length: {over_limit} records ({pct:.1f}%) exceed "
                    f"max_token_length={self.config.max_token_length}"
                )

        return errors

    def check_distribution(self, records: List[SFTRecord]) -> List[str]:
        """Check category and language distribution balance."""
        errors: List[str] = []
        if not records:
            return errors

        # Category distribution
        cat_counts = Counter(r.category.value for r in records)
        total = len(records)
        for cat, count in cat_counts.items():
            pct = count / total
            if pct < 0.005:
                errors.append(
                    f"Distribution: category '{cat}' is only {pct:.1%} "
                    f"({count}/{total})"
                )
            elif pct < 0.02:
                logger.warning(
                    "Distribution: category '%s' is low at %s (%d/%d)",
                    cat, f"{pct:.1%}", count, total,
                )

        # Product distribution
        prod_counts = Counter(r.product for r in records)
        if len(prod_counts) < 5:
            errors.append(
                f"Distribution: only {len(prod_counts)} products represented"
            )

        # Check for extreme product imbalance
        if prod_counts:
            max_prod_pct = max(prod_counts.values()) / total
            if max_prod_pct > 0.5:
                top_product = prod_counts.most_common(1)[0][0]
                errors.append(
                    f"Distribution: product '{top_product}' dominates at {max_prod_pct:.1%}"
                )

        return errors

    def check_min_counts(
        self,
        sft_records: List[SFTRecord],
        dpo_records: List[DPORecord],
    ) -> List[str]:
        """Check minimum count thresholds."""
        errors: List[str] = []

        sft_min = self.config.target_sft_size * 0.5  # Allow 50% of target
        if len(sft_records) < sft_min:
            errors.append(
                f"SFT count {len(sft_records)} is below minimum "
                f"threshold {sft_min:.0f} (50% of target {self.config.target_sft_size})"
            )

        dpo_min = self.config.target_dpo_size * 0.5
        if len(dpo_records) < dpo_min:
            errors.append(
                f"DPO count {len(dpo_records)} is below minimum "
                f"threshold {dpo_min:.0f} (50% of target {self.config.target_dpo_size})"
            )

        return errors

    def compute_stats(
        self,
        sft_records: List[SFTRecord],
        dpo_records: List[DPORecord],
        cpt_chunks: List[CPTChunk],
        dedup_removed: int = 0,
        scaling_added: int = 0,
    ) -> DatasetStats:
        """Compute comprehensive dataset statistics."""
        stats = DatasetStats()

        # SFT stats
        stats.sft_total = len(sft_records)
        stats.sft_by_category = dict(
            Counter(r.category.value for r in sft_records)
        )
        stats.sft_by_product = dict(
            Counter(r.product for r in sft_records)
        )
        stats.sft_by_language = dict(
            Counter(r.language.value for r in sft_records)
        )
        stats.sft_by_type = dict(
            Counter(r.item_type.value for r in sft_records)
        )

        # Train/eval split
        split_idx = int(len(sft_records) * self.config.train_eval_split)
        stats.sft_train = split_idx
        stats.sft_eval = len(sft_records) - split_idx

        # DPO stats
        stats.dpo_total = len(dpo_records)
        stats.dpo_by_strategy = dict(
            Counter(r.strategy.value for r in dpo_records)
        )
        dpo_split = int(len(dpo_records) * self.config.train_eval_split)
        stats.dpo_train = dpo_split
        stats.dpo_eval = len(dpo_records) - dpo_split

        # CPT stats
        stats.cpt_chunks = len(cpt_chunks)
        stats.cpt_total_tokens = sum(c.estimated_tokens for c in cpt_chunks)

        # Quality stats
        stats.dedup_removed = dedup_removed
        stats.scaling_added = scaling_added

        # Token length percentiles
        if sft_records:
            lengths = []
            for rec in sft_records:
                total_chars = sum(len(m.get("content", "")) for m in rec.messages)
                lengths.append(total_chars // 3)
            arr = np.array(lengths)
            stats.token_length_p50 = int(np.percentile(arr, 50))
            stats.token_length_p95 = int(np.percentile(arr, 95))
            stats.token_length_p99 = int(np.percentile(arr, 99))

        return stats
