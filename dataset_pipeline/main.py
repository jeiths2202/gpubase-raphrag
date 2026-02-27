"""Qwen3 32B QLoRA Dataset Pipeline — CLI entry point.

Usage:
    python -m dataset_pipeline.main build [--config CONFIG_PATH]
    python -m dataset_pipeline.main build --dry-run
    python -m dataset_pipeline.main validate --config CONFIG_PATH
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline.config import GenerationConfig
from .pipeline.dataset_builder import DatasetBuilder


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

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "build":
        return cmd_build(args)
    elif args.command == "validate":
        return cmd_validate(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
