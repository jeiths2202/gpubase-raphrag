"""Dataset builder: orchestrates the full pipeline and writes output."""
from __future__ import annotations

import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple

from .architecture_generator import ArchitectureGenerator
from .comparison_generator import ComparisonGenerator
from .config import GenerationConfig
from .deduplicator import Deduplicator
from .dpo_generator import DPOGenerator
from .general_knowledge_generator import GeneralKnowledgeGenerator
from .knowledge_extractor import KnowledgeExtractor
from .manual_loader import ManualLoader
from .models import (
    CPTChunk,
    DatasetStats,
    DPORecord,
    ManualSection,
    ProductKnowledge,
    SFTCategory,
    SFTRecord,
)
from .qa_generator import QAGenerator
from .scaler import Scaler
from .validator import Validator

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Orchestrate the full pipeline: load, extract, generate, quality, write."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build(self) -> DatasetStats:
        """Run the full pipeline end-to-end."""
        logger.info("=" * 60)
        logger.info("Qwen3 32B QLoRA Dataset Pipeline v1.0")
        logger.info("=" * 60)

        # Phase 1: Load manuals
        logger.info("\n[Phase 1/7] Loading manuals...")
        loader = ManualLoader(self.config)
        sections = loader.load_all()
        logger.info("Loaded %d sections", len(sections))

        if not sections:
            logger.error("No sections loaded. Check manuals_dir: %s", self.config.manuals_dir)
            return DatasetStats()

        # Phase 2: Extract knowledge
        logger.info("\n[Phase 2/7] Extracting knowledge...")
        extractor = KnowledgeExtractor(self.config)
        knowledge = extractor.extract_all(sections)
        total_items = sum(pk.total_items for pk in knowledge.values())
        logger.info("Extracted %d items from %d products", total_items, len(knowledge))

        # Phase 3: Generate SFT
        logger.info("\n[Phase 3/7] Generating SFT records...")
        sft_records = self._generate_sft(knowledge)
        logger.info("Raw SFT: %d records", len(sft_records))

        # Phase 4: Generate DPO
        logger.info("\n[Phase 4/7] Generating DPO records...")
        dpo_gen = DPOGenerator(self.config)
        dpo_records = dpo_gen.generate(knowledge, sft_records)
        logger.info("Raw DPO: %d records", len(dpo_records))

        # Phase 5: Scale + Deduplicate
        logger.info("\n[Phase 5/7] Scaling and deduplicating...")
        sft_records, dpo_records, dedup_removed, scaling_added = (
            self._quality_pipeline(sft_records, dpo_records)
        )

        # Phase 6: Generate CPT + Dedup
        logger.info("\n[Phase 6/7] Generating CPT corpus...")
        cpt_chunks: List[CPTChunk] = []
        cpt_exact_removed = 0
        cpt_boilerplate_removed = 0
        if self.config.include_cpt:
            cpt_chunks = self._generate_cpt(sections)
            logger.info("CPT raw: %d chunks", len(cpt_chunks))
            cpt_chunks, cpt_exact_removed, cpt_boilerplate_removed = (
                self._deduplicate_cpt(cpt_chunks)
            )
            logger.info(
                "CPT after dedup: %d chunks (exact=%d, boilerplate=%d removed)",
                len(cpt_chunks), cpt_exact_removed, cpt_boilerplate_removed,
            )

        # Phase 7: Validate + Write
        logger.info("\n[Phase 7/7] Validating and writing output...")
        validator = Validator(self.config)
        passed, errors = validator.validate_all(sft_records, dpo_records)

        stats = validator.compute_stats(
            sft_records, dpo_records, cpt_chunks, dedup_removed, scaling_added
        )
        stats.validation_passed = passed
        stats.validation_errors = errors
        stats.cpt_dedup_exact_removed = cpt_exact_removed
        stats.cpt_dedup_boilerplate_removed = cpt_boilerplate_removed
        stats.knowledge_items_total = total_items
        stats.knowledge_by_product = {
            p: pk.total_items for p, pk in knowledge.items()
        }

        self._write_output(sft_records, dpo_records, cpt_chunks, stats)

        logger.info("\n" + "=" * 60)
        logger.info("Pipeline complete!")
        logger.info("  SFT: %d (train=%d, val=%d)", stats.sft_total, stats.sft_train, stats.sft_eval)
        logger.info("  DPO: %d (train=%d, val=%d)", stats.dpo_total, stats.dpo_train, stats.dpo_eval)
        logger.info("  CPT: %d chunks (%d tokens)", stats.cpt_chunks, stats.cpt_total_tokens)
        logger.info("  Dedup removed: %d, Scaling added: %d", stats.dedup_removed, stats.scaling_added)
        logger.info("  Validation: %s", "PASSED" if passed else "FAILED (%d errors)" % len(errors))
        logger.info("  Output: %s", self.output_dir)
        logger.info("=" * 60)

        return stats

    # -- SFT Generation (3 categories) --

    def _generate_sft(
        self, knowledge: Dict[str, ProductKnowledge]
    ) -> List[SFTRecord]:
        """Generate all SFT categories including general knowledge."""
        target = self.config.target_sft_size
        gk_ratio = self.config.sft_general_knowledge_ratio

        # Split budget: domain portion vs general knowledge
        domain_budget = int(target * (1.0 - gk_ratio))
        gk_budget = target - domain_budget

        single_budget = int(domain_budget * self.config.sft_single_product_ratio)
        comparison_budget = int(domain_budget * self.config.sft_comparison_ratio)
        architecture_budget = domain_budget - single_budget - comparison_budget

        logger.info(
            "SFT budgets: single=%d, comparison=%d, architecture=%d, general=%d",
            single_budget, comparison_budget, architecture_budget, gk_budget,
        )

        qa_gen = QAGenerator(self.config)
        single_records = qa_gen.generate(knowledge)

        comp_gen = ComparisonGenerator(self.config)
        comparison_records = comp_gen.generate(knowledge)

        arch_gen = ArchitectureGenerator(self.config)
        architecture_records = arch_gen.generate(knowledge)

        # Generate general knowledge records
        gk_records: List[SFTRecord] = []
        if gk_budget > 0:
            gk_gen = GeneralKnowledgeGenerator(self.config)
            gk_records = gk_gen.generate(gk_budget)

        all_records = (
            single_records + comparison_records
            + architecture_records + gk_records
        )
        random.shuffle(all_records)

        return all_records

    # -- Quality Pipeline --

    def _quality_pipeline(
        self,
        sft_records: List[SFTRecord],
        dpo_records: List[DPORecord],
    ) -> Tuple[List[SFTRecord], List[DPORecord], int, int]:
        """Deduplicate first, then scale up to target."""
        # Step 1: Dedup raw records (remove true duplicates)
        dedup = Deduplicator(self.config)
        sft_before = len(sft_records)
        dpo_before = len(dpo_records)

        sft_records = dedup.deduplicate_sft(sft_records)
        dpo_records = dedup.deduplicate_dpo(dpo_records)

        dedup_removed = (sft_before - len(sft_records)) + (dpo_before - len(dpo_records))

        # Step 2: Scale up deduped records to reach targets
        scaler = Scaler(self.config)
        sft_records, sft_added = scaler.scale_sft(sft_records, self.config.target_sft_size)
        dpo_records, dpo_added = scaler.scale_dpo(dpo_records, self.config.target_dpo_size)
        scaling_added = sft_added + dpo_added

        return sft_records, dpo_records, dedup_removed, scaling_added

    # -- CPT Generation --

    def _generate_cpt(self, sections: List[ManualSection]) -> List[CPTChunk]:
        """Generate CPT plain-text chunks from manual sections."""
        chunks: List[CPTChunk] = []
        max_tokens = self.config.cpt_max_chunk_tokens

        for section in sections:
            text = section.content.strip()
            if not text:
                continue

            estimated_tokens = len(text) // 2

            if estimated_tokens <= max_tokens:
                chunks.append(
                    CPTChunk(
                        text=text,
                        product=section.product,
                        language=section.language,
                        source_file=section.source_file,
                        estimated_tokens=estimated_tokens,
                    )
                )
            else:
                paragraphs = text.split("\n\n")
                current = ""
                for para in paragraphs:
                    if len(current) + len(para) > max_tokens * 2:
                        if current:
                            chunks.append(
                                CPTChunk(
                                    text=current.strip(),
                                    product=section.product,
                                    language=section.language,
                                    source_file=section.source_file,
                                    estimated_tokens=len(current) // 2,
                                )
                            )
                        current = para
                    else:
                        current = current + "\n\n" + para if current else para

                if current.strip():
                    chunks.append(
                        CPTChunk(
                            text=current.strip(),
                            product=section.product,
                            language=section.language,
                            source_file=section.source_file,
                            estimated_tokens=len(current) // 2,
                        )
                    )

        return chunks

    # -- CPT Dedup (方案A: 保守的) --

    def _deduplicate_cpt(
        self, chunks: List[CPTChunk]
    ) -> Tuple[List[CPTChunk], int, int]:
        """Remove exact duplicates and low-value boilerplate from CPT chunks.

        Returns:
            (deduplicated_chunks, exact_removed_count, boilerplate_removed_count)
        """
        exact_removed = 0
        boilerplate_removed = 0

        # Step 1: 完全重複除去 (MD5 hash)
        if self.config.cpt_dedup_exact:
            seen: Dict[str, int] = {}
            unique: List[CPTChunk] = []
            for chunk in chunks:
                h = hashlib.md5(chunk.text.encode("utf-8")).hexdigest()
                if h not in seen:
                    seen[h] = 1
                    unique.append(chunk)
                else:
                    exact_removed += 1
            chunks = unique

        # Step 2: LOW価値ボイラープレート除去
        if self.config.cpt_dedup_boilerplate:
            patterns = self.config.cpt_boilerplate_sections
            filtered: List[CPTChunk] = []
            for chunk in chunks:
                first_line = chunk.text.split("\n", 1)[0]
                # ヘッダ形式 "# Product — Manual — Section" のセクション部分を検査
                section = first_line.rsplit(" — ", 1)[-1] if " — " in first_line else ""
                if section in patterns:
                    boilerplate_removed += 1
                    continue
                filtered.append(chunk)
            chunks = filtered

        return chunks, exact_removed, boilerplate_removed

    # -- Output Writers --

    def _write_output(
        self,
        sft_records: List[SFTRecord],
        dpo_records: List[DPORecord],
        cpt_chunks: List[CPTChunk],
        stats: DatasetStats,
    ) -> None:
        """Write all output files."""
        sft_train, sft_val = self._stratified_split(
            sft_records, self.config.train_eval_split
        )
        dpo_split = int(len(dpo_records) * self.config.train_eval_split)
        random.shuffle(dpo_records)
        dpo_train = dpo_records[:dpo_split]
        dpo_val = dpo_records[dpo_split:]

        # SFT
        self._write_jsonl(
            self.output_dir / "sft_train.jsonl",
            [r.to_jsonl() for r in sft_train],
        )
        self._write_jsonl(
            self.output_dir / "sft_eval.jsonl",
            [r.to_jsonl() for r in sft_val],
        )

        # DPO
        self._write_jsonl(
            self.output_dir / "dpo_train.jsonl",
            [r.to_jsonl() for r in dpo_train],
        )
        self._write_jsonl(
            self.output_dir / "dpo_eval.jsonl",
            [r.to_jsonl() for r in dpo_val],
        )

        # CPT
        if cpt_chunks:
            cpt_path = self.output_dir / "cpt_corpus.txt"
            with open(cpt_path, "w", encoding="utf-8") as f:
                for chunk in cpt_chunks:
                    f.write(chunk.text)
                    f.write("\n<|endoftext|>\n")
            logger.info("Wrote CPT: %s (%d chunks)", cpt_path, len(cpt_chunks))

        # Stats
        stats_path = self.output_dir / "pipeline_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("Wrote stats: %s", stats_path)

        logger.info(
            "Output files: sft_train(%d), sft_val(%d), dpo_train(%d), dpo_val(%d)",
            len(sft_train), len(sft_val), len(dpo_train), len(dpo_val),
        )

    @staticmethod
    def _write_jsonl(path: Path, records: List[dict]) -> None:
        """Write a list of dicts to a JSONL file."""
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("Wrote %s (%d records)", path, len(records))

    @staticmethod
    def _stratified_split(
        records: List[SFTRecord], train_ratio: float
    ) -> Tuple[List[SFTRecord], List[SFTRecord]]:
        """Split records maintaining category/product/language distribution."""
        groups: Dict[tuple, List[SFTRecord]] = {}
        for r in records:
            key = (r.product, r.category.value, r.language.value)
            groups.setdefault(key, []).append(r)

        train: List[SFTRecord] = []
        val: List[SFTRecord] = []

        for key, group in groups.items():
            random.shuffle(group)
            split_idx = max(1, int(len(group) * train_ratio))
            train.extend(group[:split_idx])
            val.extend(group[split_idx:])

        random.shuffle(train)
        random.shuffle(val)
        return train, val
