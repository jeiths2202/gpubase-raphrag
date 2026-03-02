"""
Qwen3-32B v11 Safe Adapter Merge Script

순차 머지 시 peft_config 잔여 문제를 회피하기 위해
각 단계마다 저장→재로드 방식으로 안전하게 머지합니다.

이미 검증된 CPT 머지 모델(Qwen3-32B-v11-cpt)을 시작점으로 사용합니다.

Usage:
    CUDA_VISIBLE_DEVICES=6,7 python merge_adapters_safe.py
"""
from __future__ import annotations

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
logger = logging.getLogger("v11-merge-safe")

# 루트 디스크 사용 방지
os.environ.setdefault("HF_HOME", "/raid/users/ofuser/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/raid/users/ofuser/.cache/huggingface/hub")
os.environ.setdefault("TMPDIR", "/raid/users/ofuser/tmp")

# ── 경로 설정 ─────────────────────────────────────────────
ADAPTER_BASE = "/raid/users/ofuser/qlora/outputs/v11_qwen3_32b"
OUTPUT_BASE = "/raid/users/ofuser/models"

# 이미 검증된 CPT 머지 모델을 시작점으로 사용
CPT_MERGED = f"{OUTPUT_BASE}/Qwen3-32B-v11-cpt"
SFT_ADAPTER = f"{ADAPTER_BASE}/sft_adapter"
DPO_ADAPTER = f"{ADAPTER_BASE}/dpo_adapter"

OUTPUT_SFT = f"{OUTPUT_BASE}/Qwen3-32B-v11-cpt-sft"
OUTPUT_FULL = f"{OUTPUT_BASE}/Qwen3-32B-v11-cpt-sft-dpo"


def load_model(model_path: str):
    """모델을 bf16으로 로드"""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info(f"Loading model: {model_path}")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    elapsed = time.time() - t0
    logger.info(f"  Loaded in {elapsed:.1f}s, params={model.num_parameters():,}")
    return model, tokenizer


def apply_adapter_and_merge(model, adapter_path: str, adapter_name: str):
    """LoRA adapter 적용 후 merge + peft 상태 완전 정리"""
    from peft import PeftModel

    logger.info(f"  Applying {adapter_name} adapter: {adapter_path}")
    t0 = time.time()

    peft_model = PeftModel.from_pretrained(model, adapter_path)
    merged = peft_model.merge_and_unload()

    # peft 잔여 속성 완전 정리 (torch.nn.Module은 delattr이 까다로움)
    for attr in ["peft_config", "peft_type", "active_adapter"]:
        try:
            if hasattr(merged, attr):
                object.__delattr__(merged, attr)
        except (AttributeError, TypeError):
            pass

    elapsed = time.time() - t0
    logger.info(f"  {adapter_name} merged in {elapsed:.1f}s")
    return merged


def save_model(model, tokenizer, output_dir: str, adapters_applied: list[dict]):
    """모델 저장 + merge_info 기록"""
    logger.info(f"  Saving to: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()

    model.save_pretrained(output_dir, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(output_dir)

    meta = {
        "base_model": "/raid/users/ofuser/models/Qwen3-32B",
        "merge_type": "sequential_lora_merge_safe",
        "adapters_applied": adapters_applied,
        "merged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(output_dir, "merge_info.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    size_gb = sum(p.stat().st_size for p in Path(output_dir).glob("*.safetensors")) / (1024**3)
    logger.info(f"  Saved in {elapsed:.1f}s, model size: {size_gb:.1f}GB")


def main():
    logger.info(f"GPU count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
        logger.info(f"  GPU {i}: {torch.cuda.get_device_name(i)} ({mem:.0f}GB)")

    # ── 사전 검증 ──────────────────────────────────
    for path, name in [(CPT_MERGED, "CPT merged model"), (SFT_ADAPTER, "SFT adapter"), (DPO_ADAPTER, "DPO adapter")]:
        check = os.path.join(path, "config.json" if name.startswith("CPT") else "adapter_config.json")
        if not os.path.exists(check):
            logger.error(f"{name} not found: {path}")
            sys.exit(1)
        logger.info(f"✓ {name}: {path}")

    # ── Step 1: CPT merged model + SFT adapter → cpt-sft ──
    logger.info("=" * 60)
    logger.info("Step 1: CPT model + SFT adapter → cpt-sft")
    logger.info("=" * 60)

    model, tokenizer = load_model(CPT_MERGED)
    model = apply_adapter_and_merge(model, SFT_ADAPTER, "SFT")
    save_model(model, tokenizer, OUTPUT_SFT, [
        {"name": "cpt", "path": f"{ADAPTER_BASE}/cpt_adapter"},
        {"name": "sft", "path": SFT_ADAPTER},
    ])

    # 메모리 해제
    del model, tokenizer
    torch.cuda.empty_cache()
    logger.info("  GPU memory released")

    # ── Step 2: cpt-sft model (재로드) + DPO adapter → cpt-sft-dpo ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 2: cpt-sft model + DPO adapter → cpt-sft-dpo")
    logger.info("=" * 60)

    model, tokenizer = load_model(OUTPUT_SFT)
    model = apply_adapter_and_merge(model, DPO_ADAPTER, "DPO")

    # 기존 실패한 full 모델 삭제
    if os.path.exists(OUTPUT_FULL):
        import shutil
        backup = f"{OUTPUT_FULL}.broken.{int(time.time())}"
        logger.info(f"  기존 full 모델 백업: {backup}")
        shutil.move(OUTPUT_FULL, backup)

    save_model(model, tokenizer, OUTPUT_FULL, [
        {"name": "cpt", "path": f"{ADAPTER_BASE}/cpt_adapter"},
        {"name": "sft", "path": SFT_ADAPTER},
        {"name": "dpo", "path": DPO_ADAPTER},
    ])

    del model, tokenizer
    torch.cuda.empty_cache()

    logger.info("")
    logger.info("=" * 60)
    logger.info("All merges complete!")
    logger.info(f"  cpt-sft:     {OUTPUT_SFT}")
    logger.info(f"  cpt-sft-dpo: {OUTPUT_FULL}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
