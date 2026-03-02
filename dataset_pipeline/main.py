"""Qwen3 32B QLoRA Dataset Pipeline — CLI entry point.

Usage:
    python -m dataset_pipeline.main build [--config CONFIG_PATH]
    python -m dataset_pipeline.main build --dry-run
    python -m dataset_pipeline.main validate --config CONFIG_PATH
    python -m dataset_pipeline.main augment-sft [--ratio 0.15]
    python -m dataset_pipeline.main fix-alignment
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

from .pipeline.config import GenerationConfig
from .pipeline.dataset_builder import DatasetBuilder
from .pipeline.general_knowledge_generator import GeneralKnowledgeGenerator
from .pipeline.models import SFTCategory


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    # Quiet noisy libraries
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)


def cmd_build(args: argparse.Namespace) -> int:
    """Run the full build pipeline."""
    config = _load_config(args.config)

    # Validate config
    errors = config.validate()
    if errors:
        for e in errors:
            logging.error("Config error: %s", e)
        return 1

    if args.dry_run:
        logging.info("Dry run - config validated successfully")
        logging.info("  Target SFT: %d", config.target_sft_size)
        logging.info("  Target DPO: %d", config.target_dpo_size)
        logging.info("  Manuals dir: %s", config.manuals_dir)
        logging.info("  Output dir: %s", config.output_dir)
        logging.info("  Languages: %s", config.all_languages)
        return 0

    builder = DatasetBuilder(config)
    stats = builder.build()

    if not stats.validation_passed:
        logging.warning("Pipeline completed with validation errors")
        return 1

    return 0


def cmd_augment_sft(args: argparse.Namespace) -> int:
    """Read existing SFT files, scale to CPT-relative target, mix in GK, rewrite."""
    config = _load_config(args.config)
    output_dir = Path(config.output_dir)
    gk_ratio = args.ratio
    cpt_ratio = args.cpt_ratio

    sft_train_path = output_dir / "sft_train.jsonl"
    sft_eval_path = output_dir / "sft_eval.jsonl"
    cpt_path = output_dir / "cpt_corpus.txt"

    # Use .bak (original domain-only) if available, else current files
    sft_train_source = sft_train_path.with_suffix(".jsonl.bak")
    sft_eval_source = sft_eval_path.with_suffix(".jsonl.bak")
    if not sft_train_source.exists():
        sft_train_source = sft_train_path
    if not sft_eval_source.exists():
        sft_eval_source = sft_eval_path

    if not sft_train_source.exists():
        logging.error("SFT source file not found: %s", sft_train_source)
        return 1

    # ── Step 1: Determine target SFT size from CPT ──
    if cpt_path.exists() and cpt_ratio > 0:
        cpt_text_len = cpt_path.stat().st_size
        # UTF-8 CJK average ~3 bytes/char, ~2 chars/token → ~6 bytes/token
        cpt_tokens_est = cpt_text_len // 6
        logging.info("CPT corpus: %.1f MB, ~%d tokens (estimated)",
                     cpt_text_len / 1024 / 1024, cpt_tokens_est)
    else:
        logging.warning("CPT corpus not found at %s, using record-count mode", cpt_path)
        cpt_tokens_est = 0

    # ── Step 2: Read domain SFT (strip previous GK) ──
    logging.info("Reading domain SFT data from %s ...", sft_train_source.name)
    all_domain = _read_jsonl(sft_train_source) + (
        _read_jsonl(sft_eval_source) if sft_eval_source.exists() else []
    )
    all_domain = [r for r in all_domain
                  if r.get("metadata", {}).get("category") != "general_knowledge"]
    logging.info("  Domain records available: %d", len(all_domain))

    # Estimate avg tokens per record
    sample = all_domain[:500]
    total_sample_tokens = sum(
        sum(len(m.get("content", "")) for m in r.get("messages", []))
        // 2  # char → token rough estimate
        for r in sample
    )
    avg_tokens = total_sample_tokens // len(sample) if sample else 800
    logging.info("  Avg tokens/record (sampled): %d", avg_tokens)

    # ── Step 3: Calculate target record count ──
    if cpt_tokens_est > 0:
        target_sft_tokens = int(cpt_tokens_est * cpt_ratio)
        target_total = target_sft_tokens // avg_tokens
    else:
        target_total = len(all_domain)  # fallback: keep as-is

    domain_target = int(target_total * (1.0 - gk_ratio))
    gk_target = target_total - domain_target

    logging.info("  Target: total=%d (domain=%d, gk=%d) [CPT×%.0f%%]",
                 target_total, domain_target, gk_target, cpt_ratio * 100)

    # ── Step 4: Stratified downsample domain records ──
    domain_sampled = _stratified_sample(all_domain, domain_target)
    logging.info("  Domain sampled: %d (from %d)", len(domain_sampled), len(all_domain))

    # ── Step 5: Generate general knowledge ──
    gk_gen = GeneralKnowledgeGenerator(config)
    gk_all = gk_gen.generate(gk_target)
    gk_jsonl = [r.to_jsonl() for r in gk_all]

    # ── Step 6: Split train/eval, interleave ──
    split = config.train_eval_split
    random.shuffle(domain_sampled)
    d_split = int(len(domain_sampled) * split)
    domain_train, domain_eval = domain_sampled[:d_split], domain_sampled[d_split:]

    random.shuffle(gk_jsonl)
    g_split = int(len(gk_jsonl) * split)
    gk_train, gk_eval = gk_jsonl[:g_split], gk_jsonl[g_split:]

    train_mixed = _interleave(domain_train, gk_train)
    eval_mixed = _interleave(domain_eval, gk_eval)

    # ── Step 7: Backup & write ──
    _backup_file(sft_train_path)
    if sft_eval_path.exists():
        _backup_file(sft_eval_path)

    _write_jsonl(sft_train_path, train_mixed)
    _write_jsonl(sft_eval_path, eval_mixed)

    # ── Summary ──
    new_total = len(train_mixed) + len(eval_mixed)
    actual_gk = len(gk_train) + len(gk_eval)
    est_tokens = new_total * avg_tokens
    logging.info("\n" + "=" * 60)
    logging.info("SFT Augmentation Complete!")
    logging.info("  Train: %d (domain=%d, gk=%d)", len(train_mixed), len(domain_train), len(gk_train))
    logging.info("  Eval:  %d (domain=%d, gk=%d)", len(eval_mixed), len(domain_eval), len(gk_eval))
    logging.info("  Total: %d → %d", len(all_domain), new_total)
    logging.info("  GK ratio: %.1f%% (target: %.1f%%)",
                 actual_gk / new_total * 100 if new_total else 0, gk_ratio * 100)
    logging.info("  Est. tokens: %s (CPT: %s, ratio: %.1f%%)",
                 f"{est_tokens:,}", f"{cpt_tokens_est:,}",
                 est_tokens / cpt_tokens_est * 100 if cpt_tokens_est else 0)
    logging.info("  Backups: *.bak files created")
    logging.info("=" * 60)

    return 0


# ── Section heading pattern: "1.2.3." or "1.2.3.4." at line start ──
_SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)+\.)\s", re.MULTILINE)


def _fix_answer_alignment(
    toc_title: str, answer: str
) -> tuple[str, str] | None:
    """Trim answer prefix so it starts at the section matching toc_title.

    Returns (fixed_answer, method) or None if unfixable.
    3-tier fallback: exact match → section number → key term.
    """
    toc_norm = toc_title.replace("\xa0", " ").strip()
    ans_norm = answer.replace("\xa0", " ")

    # Tier 1: Exact match of full toc_title in answer
    pos = ans_norm.find(toc_norm)
    if pos != -1:
        return answer[pos:], "exact"

    # Tier 1b: Exact match tolerating line-break whitespace
    # PDF extraction may split toc_title across lines with \n
    toc_collapsed = re.sub(r"\s+", " ", toc_norm)
    ans_collapsed_map: list[int] = []  # maps collapsed idx → original idx
    ans_collapsed_chars: list[str] = []
    i = 0
    while i < len(ans_norm):
        if ans_norm[i] in " \t\n\r":
            # Collapse whitespace run to single space
            ans_collapsed_map.append(i)
            ans_collapsed_chars.append(" ")
            while i < len(ans_norm) and ans_norm[i] in " \t\n\r":
                i += 1
        else:
            ans_collapsed_map.append(i)
            ans_collapsed_chars.append(ans_norm[i])
            i += 1
    ans_collapsed = "".join(ans_collapsed_chars)
    cpos = ans_collapsed.find(toc_collapsed)
    if cpos != -1:
        orig_pos = ans_collapsed_map[cpos]
        return answer[orig_pos:], "exact_ws"

    # Tier 2: Section number prefix (e.g., "2.6.1.") at line start
    sec_match = re.match(r"^([\d.]+\.)\s", toc_norm)
    if sec_match:
        sec_num = sec_match.group(1)
        # Find this section number at a line start in the answer
        pattern = re.compile(r"^" + re.escape(sec_num) + r"\s", re.MULTILINE)
        m = pattern.search(ans_norm)
        if m:
            return answer[m.start():], "section_num"

    # Tier 3: Key term (text after section number)
    if sec_match:
        key_term = toc_norm[sec_match.end():].strip()
    else:
        key_term = toc_norm
    if key_term and len(key_term) >= 3:
        idx = ans_norm.find(key_term)
        if idx != -1:
            # Back up to the start of the line containing this term
            line_start = ans_norm.rfind("\n", 0, idx)
            line_start = line_start + 1 if line_start != -1 else 0
            return answer[line_start:], "key_term"

    return None


def _trim_trailing_sections(answer: str, max_sections: int = 1) -> str:
    """Trim answer to keep at most max_sections additional section headings.

    Finds section headings (e.g., "1.2.3. Title") after the start of the answer
    and cuts at the (max_sections+1)-th heading.
    """
    hits = list(_SECTION_NUM_RE.finditer(answer))
    if len(hits) <= 1 + max_sections:
        return answer
    # The first hit (index 0) is our target section heading.
    # Keep up to max_sections extra headings after it.
    cut_at = hits[1 + max_sections].start()
    trimmed = answer[:cut_at].rstrip()
    return trimmed


def cmd_fix_alignment(args: argparse.Namespace) -> int:
    """Fix SFT answer alignment by trimming prefix content from wrong sections."""
    config = _load_config(args.config)
    output_dir = Path(config.output_dir)
    max_trailing = args.max_trailing_sections

    sft_train_path = output_dir / "sft_train.jsonl"
    sft_eval_path = output_dir / "sft_eval.jsonl"

    # Read from .bak if available (domain-only backup), else current files
    sft_train_source = sft_train_path.with_suffix(".jsonl.bak")
    sft_eval_source = sft_eval_path.with_suffix(".jsonl.bak")
    if not sft_train_source.exists():
        sft_train_source = sft_train_path
    if not sft_eval_source.exists():
        sft_eval_source = sft_eval_path

    if not sft_train_source.exists():
        logging.error("SFT source file not found: %s", sft_train_source)
        return 1

    # ── Step 1: Read all records, separate domain vs GK ──
    all_records = _read_jsonl(sft_train_source) + (
        _read_jsonl(sft_eval_source) if sft_eval_source.exists() else []
    )
    domain = [r for r in all_records
              if r.get("metadata", {}).get("category") != "general_knowledge"]
    logging.info("Loaded %d domain records from %s (+%s)",
                 len(domain), sft_train_source.name, sft_eval_source.name)

    # ── Step 2: Apply alignment fix to each domain record ──
    fixed: list[dict] = []
    stats: dict[str, int] = {"exact": 0, "exact_ws": 0, "section_num": 0,
                              "key_term": 0, "removed": 0, "already_ok": 0}

    for r in domain:
        meta = r.get("metadata", {})
        toc_title = meta.get("toc_title", "")
        if not toc_title:
            fixed.append(r)
            stats["already_ok"] += 1
            continue

        msgs = r.get("messages", [])
        asst_idx = next(
            (i for i, m in enumerate(msgs) if m["role"] == "assistant"), None
        )
        if asst_idx is None:
            fixed.append(r)
            stats["already_ok"] += 1
            continue

        answer = msgs[asst_idx]["content"]

        # Check if already aligned (toc_title found within first 50 chars)
        ans_norm = answer.replace("\xa0", " ")
        toc_norm = toc_title.replace("\xa0", " ").strip()
        early_pos = ans_norm.find(toc_norm)
        if early_pos != -1 and early_pos <= 50:
            # Already aligned — just apply tail trimming
            trimmed = _trim_trailing_sections(answer, max_trailing)
            r_copy = json.loads(json.dumps(r))
            r_copy["messages"][asst_idx]["content"] = trimmed
            fixed.append(r_copy)
            stats["already_ok"] += 1
            continue

        result = _fix_answer_alignment(toc_title, answer)
        if result is None:
            stats["removed"] += 1
            logging.debug("Removed (unfixable): toc=%s", toc_title[:80])
            continue

        fixed_answer, method = result
        # Apply tail trimming
        fixed_answer = _trim_trailing_sections(fixed_answer, max_trailing)

        r_copy = json.loads(json.dumps(r))
        r_copy["messages"][asst_idx]["content"] = fixed_answer
        fixed.append(r_copy)
        stats[method] += 1

    logging.info("Alignment fix results:")
    logging.info("  already_ok: %d", stats["already_ok"])
    logging.info("  exact:      %d", stats["exact"])
    logging.info("  exact_ws:   %d", stats["exact_ws"])
    logging.info("  section_num:%d", stats["section_num"])
    logging.info("  key_term:   %d", stats["key_term"])
    logging.info("  removed:    %d", stats["removed"])
    logging.info("  total fixed: %d → %d domain records", len(domain), len(fixed))

    # ── Step 3: Write fixed domain records as .bak ──
    # Back up current files first, then write fixed domain to .bak
    if sft_train_path.exists() and not sft_train_path.with_suffix(".jsonl.bak").exists():
        _backup_file(sft_train_path)
    if sft_eval_path.exists() and not sft_eval_path.with_suffix(".jsonl.bak").exists():
        _backup_file(sft_eval_path)

    # Split fixed domain back into train/eval proportions
    split_ratio = config.train_eval_split
    random.shuffle(fixed)
    d_split = int(len(fixed) * split_ratio)
    domain_train = fixed[:d_split]
    domain_eval = fixed[d_split:]

    # Write domain-only .bak files (these become the source for augment-sft)
    bak_train = sft_train_path.with_suffix(".jsonl.bak")
    bak_eval = sft_eval_path.with_suffix(".jsonl.bak")
    _write_jsonl(bak_train, domain_train)
    _write_jsonl(bak_eval, domain_eval)

    # ── Step 4: Run augment-sft logic to produce final output ──
    logging.info("Running augment-sft to produce final output with GK...")
    augment_args = argparse.Namespace(
        config=args.config,
        ratio=args.gk_ratio,
        cpt_ratio=args.cpt_ratio,
    )
    return cmd_augment_sft(augment_args)


def _stratified_sample(records: list, target: int) -> list:
    """Downsample records preserving product/language distribution."""
    if len(records) <= target:
        return list(records)

    ratio = target / len(records)

    # Group by (product, language)
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for r in records:
        meta = r.get("metadata", {})
        key = (meta.get("product", "unknown"), meta.get("language", "unknown"))
        groups[key].append(r)

    sampled: list = []
    for key, group in groups.items():
        n = max(1, int(len(group) * ratio))
        random.shuffle(group)
        sampled.extend(group[:n])

    # Adjust to exact target
    if len(sampled) > target:
        random.shuffle(sampled)
        sampled = sampled[:target]
    elif len(sampled) < target:
        # Fill from remaining records
        used = set(id(r) for r in sampled)
        remaining = [r for r in records if id(r) not in used]
        random.shuffle(remaining)
        sampled.extend(remaining[:target - len(sampled)])

    return sampled


def _read_jsonl(path: Path) -> list:
    """Read a JSONL file into a list of dicts."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _interleave(domain: list, general: list) -> list:
    """Interleave general knowledge records evenly throughout domain records."""
    if not general:
        return list(domain)
    if not domain:
        return list(general)

    result = []
    # Calculate spacing: insert 1 GK every N domain records
    spacing = max(1, len(domain) // len(general))
    gk_idx = 0

    for i, record in enumerate(domain):
        result.append(record)
        # Insert a GK record at regular intervals
        if gk_idx < len(general) and (i + 1) % spacing == 0:
            result.append(general[gk_idx])
            gk_idx += 1

    # Append remaining GK records
    while gk_idx < len(general):
        result.append(general[gk_idx])
        gk_idx += 1

    return result


def _backup_file(path: Path) -> None:
    """Create a .bak backup of a file."""
    import shutil
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    logging.info("  Backed up: %s → %s", path.name, bak.name)


def _write_jsonl(path: Path, records: list) -> None:
    """Write a list of dicts to a JSONL file."""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logging.info("  Wrote: %s (%d records)", path, len(records))


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate config file only."""
    config = _load_config(args.config)
    errors = config.validate()

    if errors:
        logging.error("Validation FAILED:")
        for e in errors:
            logging.error("  - %s", e)
        return 1

    logging.info("Config validation PASSED")
    logging.info("  Target SFT: %d", config.target_sft_size)
    logging.info("  Target DPO: %d", config.target_dpo_size)
    logging.info("  SFT ratios: single=%.0f%%, comparison=%.0f%%, architecture=%.0f%%",
                 config.sft_single_product_ratio * 100,
                 config.sft_comparison_ratio * 100,
                 config.sft_architecture_ratio * 100)
    logging.info("  DPO ratios: cross=%.0f%%, fact=%.0f%%, over=%.0f%%, spec=%.0f%%",
                 config.dpo_cross_product_ratio * 100,
                 config.dpo_fact_mutation_ratio * 100,
                 config.dpo_over_claiming_ratio * 100,
                 config.dpo_speculative_ratio * 100)
    return 0


def _load_config(config_path: str | None) -> GenerationConfig:
    """Load config from YAML or use defaults."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            logging.error("Config file not found: %s", path)
            sys.exit(1)
        logging.info("Loading config from: %s", path)
        return GenerationConfig.from_yaml(path)

    # Default config path
    default_path = Path("dataset_pipeline/configs/generation_config.yaml")
    if default_path.exists():
        logging.info("Loading default config: %s", default_path)
        return GenerationConfig.from_yaml(default_path)

    logging.info("Using built-in defaults")
    return GenerationConfig()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Qwen3 32B QLoRA Dataset Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    subparsers = parser.add_subparsers(dest="command", help="Pipeline commands")

    # build
    build_parser = subparsers.add_parser("build", help="Run the full pipeline")
    build_parser.add_argument(
        "--config", type=str, default=None, help="Path to YAML config file"
    )
    build_parser.add_argument(
        "--dry-run", action="store_true", help="Validate config only"
    )

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate config")
    validate_parser.add_argument(
        "--config", type=str, default=None, help="Path to YAML config file"
    )

    # augment-sft
    augment_parser = subparsers.add_parser(
        "augment-sft",
        help="Rebuild SFT dataset scaled to CPT with general knowledge mixed in",
    )
    augment_parser.add_argument(
        "--config", type=str, default=None, help="Path to YAML config file"
    )
    augment_parser.add_argument(
        "--ratio", type=float, default=0.15,
        help="Ratio of general knowledge in total SFT (default: 0.15 = 15%%)",
    )
    augment_parser.add_argument(
        "--cpt-ratio", type=float, default=0.10, dest="cpt_ratio",
        help="SFT size as ratio of CPT tokens (default: 0.10 = 10%%)",
    )

    # fix-alignment
    fix_parser = subparsers.add_parser(
        "fix-alignment",
        help="Fix SFT Q-A alignment by trimming answer prefixes from wrong sections",
    )
    fix_parser.add_argument(
        "--config", type=str, default=None, help="Path to YAML config file"
    )
    fix_parser.add_argument(
        "--max-trailing-sections", type=int, default=1, dest="max_trailing_sections",
        help="Max extra section headings to keep after target (default: 1)",
    )
    fix_parser.add_argument(
        "--gk-ratio", type=float, default=0.15, dest="gk_ratio",
        help="Ratio of general knowledge in final SFT (default: 0.15 = 15%%)",
    )
    fix_parser.add_argument(
        "--cpt-ratio", type=float, default=0.10, dest="cpt_ratio",
        help="SFT size as ratio of CPT tokens (default: 0.10 = 10%%)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "build":
        return cmd_build(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "augment-sft":
        return cmd_augment_sft(args)
    elif args.command == "fix-alignment":
        return cmd_fix_alignment(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
