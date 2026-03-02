"""
Qwen3-32B v11 Adapter Merge Script

순차적으로 CPT → SFT → DPO adapter를 base model에 merge하여
vLLM에서 바로 로드할 수 있는 full model을 생성합니다.

Usage:
    # GPU 6,7 사용 (기본값)
    CUDA_VISIBLE_DEVICES=6,7 python merge_adapters.py --variant cpt
    CUDA_VISIBLE_DEVICES=6,7 python merge_adapters.py --variant cpt-sft
    CUDA_VISIBLE_DEVICES=6,7 python merge_adapters.py --variant cpt-sft-dpo
    CUDA_VISIBLE_DEVICES=6,7 python merge_adapters.py --variant all  # 3개 모두 (효율적)

Output:
    /raid/users/ofuser/models/Qwen3-32B-v11-cpt/
    /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft/
    /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft-dpo/
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("v11-merge")

# 루트 디스크 사용 방지
os.environ.setdefault("HF_HOME", "/raid/users/ofuser/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/raid/users/ofuser/.cache/huggingface/hub")
os.environ.setdefault("TMPDIR", "/raid/users/ofuser/tmp")

# ── 경로 설정 ─────────────────────────────────────────────
BASE_MODEL = "/raid/users/ofuser/models/Qwen3-32B"
ADAPTER_BASE = "/raid/users/ofuser/qlora/outputs/v11_qwen3_32b"
OUTPUT_BASE = "/raid/users/ofuser/models"

ADAPTERS = {
    "cpt": f"{ADAPTER_BASE}/cpt_adapter",
    "sft": f"{ADAPTER_BASE}/sft_adapter",
    "dpo": f"{ADAPTER_BASE}/dpo_adapter",
}

# 각 variant에 적용할 adapter 순서
VARIANT_ADAPTERS = {
    "cpt": ["cpt"],
    "cpt-sft": ["cpt", "sft"],
    "cpt-sft-dpo": ["cpt", "sft", "dpo"],
}


def output_dir_for(variant: str) -> str:
    return f"{OUTPUT_BASE}/Qwen3-32B-v11-{variant}"


def load_base_model():
    """Base model을 bf16으로 로드 (양자화 없이 full precision)"""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info(f"Loading base model: {BASE_MODEL}")
    logger.info(f"  GPUs available: {torch.cuda.device_count()}")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    elapsed = time.time() - t0
    logger.info(f"  Base model loaded in {elapsed:.1f}s, params={model.num_parameters():,}")
    return model, tokenizer


def apply_and_merge(model, adapter_path: str, adapter_name: str):
    """LoRA adapter를 적용하고 merge"""
    from peft import PeftModel

    logger.info(f"  Applying {adapter_name} adapter: {adapter_path}")
    t0 = time.time()

    model = PeftModel.from_pretrained(model, adapter_path)
    model = model.merge_and_unload()

    elapsed = time.time() - t0
    logger.info(f"  {adapter_name} merged in {elapsed:.1f}s")
    return model


def save_merged_model(model, tokenizer, output_dir: str):
    """Merged model 저장"""
    logger.info(f"  Saving to: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()

    model.save_pretrained(output_dir, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(output_dir)

    # 머지 메타데이터 기록
    meta = {
        "base_model": BASE_MODEL,
        "merge_type": "sequential_lora_merge",
        "adapters_applied": [],
        "merged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = os.path.join(output_dir, "merge_info.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    size_gb = sum(f.stat().st_size for f in Path(output_dir).glob("*.safetensors")) / (1024**3)
    logger.info(f"  Saved in {elapsed:.1f}s, model size: {size_gb:.1f}GB")
    return output_dir


def merge_single_variant(variant: str, force: bool = False) -> str:
    """단일 variant 머지 (매번 base model 새로 로드)"""
    output_dir = output_dir_for(variant)
    adapters_to_apply = VARIANT_ADAPTERS[variant]

    if os.path.exists(output_dir) and not force:
        config_path = os.path.join(output_dir, "config.json")
        if os.path.exists(config_path):
            logger.info(f"Already exists: {output_dir} (use --force to overwrite)")
            return output_dir

    logger.info("=" * 60)
    logger.info(f"Merging variant: {variant}")
    logger.info(f"  Adapters: {' → '.join(adapters_to_apply)}")
    logger.info(f"  Output:   {output_dir}")
    logger.info("=" * 60)

    # 기존 adapter 검증
    for name in adapters_to_apply:
        path = ADAPTERS[name]
        if not os.path.exists(os.path.join(path, "adapter_config.json")):
            logger.error(f"Adapter not found: {path}")
            sys.exit(1)

    model, tokenizer = load_base_model()

    for name in adapters_to_apply:
        model = apply_and_merge(model, ADAPTERS[name], name.upper())

    save_merged_model(model, tokenizer, output_dir)

    # merge_info 업데이트
    meta_path = os.path.join(output_dir, "merge_info.json")
    with open(meta_path, "r+", encoding="utf-8") as f:
        meta = json.load(f)
        meta["adapters_applied"] = [
            {"name": n, "path": ADAPTERS[n]} for n in adapters_to_apply
        ]
        f.seek(0)
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.truncate()

    # GPU 메모리 해제
    del model
    torch.cuda.empty_cache()

    logger.info(f"Variant '{variant}' merge complete: {output_dir}")
    return output_dir


def merge_all(force: bool = False) -> dict[str, str]:
    """3개 variant를 효율적으로 머지 (base model 1회만 로드)"""
    results = {}

    # 전부 이미 존재하는지 체크
    all_exist = True
    for variant in VARIANT_ADAPTERS:
        out = output_dir_for(variant)
        if not os.path.exists(os.path.join(out, "config.json")):
            all_exist = False
            break

    if all_exist and not force:
        logger.info("All 3 variants already exist. Use --force to overwrite.")
        for variant in VARIANT_ADAPTERS:
            results[variant] = output_dir_for(variant)
        return results

    logger.info("=" * 60)
    logger.info("Merging ALL variants (efficient: single model load)")
    logger.info("=" * 60)

    # 모든 adapter 검증
    for name, path in ADAPTERS.items():
        if not os.path.exists(os.path.join(path, "adapter_config.json")):
            logger.error(f"Adapter not found: {path}")
            sys.exit(1)

    model, tokenizer = load_base_model()

    # 1) Base + CPT → save cpt
    model = apply_and_merge(model, ADAPTERS["cpt"], "CPT")
    out_cpt = output_dir_for("cpt")
    if force or not os.path.exists(os.path.join(out_cpt, "config.json")):
        save_merged_model(model, tokenizer, out_cpt)
        _write_merge_info(out_cpt, ["cpt"])
    else:
        logger.info(f"  Skipping save (exists): {out_cpt}")
    results["cpt"] = out_cpt

    # 2) + SFT → save cpt-sft
    model = apply_and_merge(model, ADAPTERS["sft"], "SFT")
    out_sft = output_dir_for("cpt-sft")
    if force or not os.path.exists(os.path.join(out_sft, "config.json")):
        save_merged_model(model, tokenizer, out_sft)
        _write_merge_info(out_sft, ["cpt", "sft"])
    else:
        logger.info(f"  Skipping save (exists): {out_sft}")
    results["cpt-sft"] = out_sft

    # 3) + DPO → save cpt-sft-dpo
    model = apply_and_merge(model, ADAPTERS["dpo"], "DPO")
    out_dpo = output_dir_for("cpt-sft-dpo")
    if force or not os.path.exists(os.path.join(out_dpo, "config.json")):
        save_merged_model(model, tokenizer, out_dpo)
        _write_merge_info(out_dpo, ["cpt", "sft", "dpo"])
    else:
        logger.info(f"  Skipping save (exists): {out_dpo}")
    results["cpt-sft-dpo"] = out_dpo

    # GPU 메모리 해제
    del model
    torch.cuda.empty_cache()

    logger.info("=" * 60)
    logger.info("All variants merged:")
    for v, p in results.items():
        logger.info(f"  {v}: {p}")
    logger.info("=" * 60)

    return results


def _write_merge_info(output_dir: str, adapter_names: list[str]):
    meta_path = os.path.join(output_dir, "merge_info.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r+", encoding="utf-8") as f:
            meta = json.load(f)
            meta["adapters_applied"] = [
                {"name": n, "path": ADAPTERS[n]} for n in adapter_names
            ]
            f.seek(0)
            json.dump(meta, f, ensure_ascii=False, indent=2)
            f.truncate()


def main():
    parser = argparse.ArgumentParser(description="Qwen3-32B v11 Adapter Merge")
    parser.add_argument(
        "--variant", type=str, required=True,
        choices=["cpt", "cpt-sft", "cpt-sft-dpo", "all"],
        help="Merge variant: cpt, cpt-sft, cpt-sft-dpo, all",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing merged models")
    args = parser.parse_args()

    logger.info(f"GPU count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
        logger.info(f"  GPU {i}: {torch.cuda.get_device_name(i)} ({mem:.0f}GB)")

    if args.variant == "all":
        merge_all(force=args.force)
    else:
        merge_single_variant(args.variant, force=args.force)

    return 0


if __name__ == "__main__":
    sys.exit(main())
