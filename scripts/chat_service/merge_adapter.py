#!/usr/bin/env python3
"""
CPT LoRA Adapter를 Base Model에 Merge (CPU bf16)

RAM에서 bf16으로 로드 → LoRA merge → safetensors 저장
결과 모델은 vLLM에서 바로 서빙 가능 (LoRA 불필요)

Usage:
    python3 scripts/chat_service/merge_adapter.py
"""
import os
import sys
import json
import logging
from datetime import datetime

os.environ["HF_HOME"] = "/raid/users/ofuser/.cache/huggingface"
os.environ["TRANSFORMERS_CACHE"] = "/raid/users/ofuser/.cache/huggingface/hub"
os.environ["TMPDIR"] = "/raid/users/ofuser/tmp"
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # CPU only

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_MODEL = "Qwen/Qwen2.5-72B-Instruct"
CPT_ADAPTER = "/raid/users/ofuser/qlora/outputs/parallel_pipeline/cpt_70b_adapter"
OUTPUT_DIR = "/raid/users/ofuser/qlora/outputs/merged_cpt_72b"


def merge():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"Base: {BASE_MODEL}")
    logger.info(f"Adapter: {CPT_ADAPTER}")
    logger.info(f"Output: {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # CPU bf16으로 로드 (~144GB RAM)
    logger.info("Loading base model on CPU (bf16)... ~3-5min")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    logger.info("Base model loaded")

    # CPT adapter 적용
    logger.info("Applying CPT adapter...")
    model = PeftModel.from_pretrained(
        model, CPT_ADAPTER, torch_dtype=torch.bfloat16
    )
    logger.info("CPT adapter applied")

    # Merge & unload
    logger.info("Merging weights...")
    model = model.merge_and_unload()
    logger.info("Merge complete")

    # bf16 safetensors로 저장
    logger.info(f"Saving to {OUTPUT_DIR}... ~5min")
    model.save_pretrained(
        OUTPUT_DIR,
        safe_serialization=True,
        max_shard_size="5GB",
    )
    tokenizer.save_pretrained(OUTPUT_DIR)

    metadata = {
        "base_model": BASE_MODEL,
        "cpt_adapter": CPT_ADAPTER,
        "merged_at": datetime.now().isoformat(),
        "dtype": "bfloat16",
    }
    with open(os.path.join(OUTPUT_DIR, "merge_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info("완료!")


if __name__ == "__main__":
    start = datetime.now()
    merge()
    logger.info(f"총 소요: {datetime.now() - start}")
