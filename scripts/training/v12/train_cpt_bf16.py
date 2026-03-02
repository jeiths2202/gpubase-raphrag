"""
Qwen3-32B v12 CPT Training — Full bf16 (양자화 없음)

GPU 6,7 모델 병렬 (device_map="auto")로 bf16 full precision 학습.
4-bit 양자화를 사용하지 않으므로 머지 시 rounding error 없음.

Usage:
    CUDA_VISIBLE_DEVICES=6,7 accelerate launch \
        --config_file scripts/training/v12/configs/accelerate_mp_gpu67.yaml \
        scripts/training/v12/train_cpt_bf16.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import SFTConfig, SFTTrainer

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("v12-cpt")

# 루트 디스크 사용 방지
os.environ.setdefault("HF_HOME", "/raid/users/ofuser/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/raid/users/ofuser/.cache/huggingface/hub")
os.environ.setdefault("HF_DATASETS_CACHE", "/raid/users/ofuser/.cache/huggingface/datasets")
os.environ.setdefault("TMPDIR", "/raid/users/ofuser/tmp")

# ── 설정 ─────────────────────────────────────────────────
BASE_MODEL = "/raid/users/ofuser/models/Qwen3-32B"
CORPUS_PATH = os.path.join(os.path.dirname(__file__), "cpt_corpus_dedup.txt")
OUTPUT_BASE = "/raid/users/ofuser/qlora/outputs/v12_qwen3_32b"
OUTPUT_DIR = f"{OUTPUT_BASE}/cpt_adapter"

# LoRA 하이퍼파라미터
LORA_R = 64
LORA_ALPHA = 128
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
LORA_MODULES_TO_SAVE = None  # embed_tokens/lm_head 제외하여 메모리 절감

# 학습 하이퍼파라미터
EPOCHS = 3
BATCH_SIZE = 4
GRAD_ACCUM = 8
LR = 1e-5
MAX_SEQ_LEN = 4096
WARMUP_RATIO = 0.05
WEIGHT_DECAY = 0.01
SAVE_STEPS = 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="설정 검증만")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  Qwen3-32B v12 CPT — Full bf16 (NO quantization)")
    logger.info(f"  Base model: {BASE_MODEL}")
    logger.info(f"  Corpus:     {CORPUS_PATH}")
    logger.info(f"  Output:     {OUTPUT_DIR}")
    logger.info(f"  GPUs:       {torch.cuda.device_count()}")
    logger.info("=" * 60)

    for i in range(torch.cuda.device_count()):
        mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
        logger.info(f"  GPU {i}: {torch.cuda.get_device_name(i)} ({mem:.0f}GB)")

    # ── 데이터 로드 ──────────────────────────────────────
    corpus_file = Path(CORPUS_PATH)
    if not corpus_file.exists():
        logger.error(f"Corpus not found: {corpus_file}")
        sys.exit(1)

    logger.info(f"\nLoading corpus: {corpus_file}")
    with open(corpus_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    sections = [s.strip() for s in raw_text.split("\n\n") if len(s.strip()) > 50]
    logger.info(f"  Corpus sections: {len(sections):,} (from {len(raw_text)/1024/1024:.1f}MB)")

    dataset = Dataset.from_dict({"text": sections})
    dataset = dataset.shuffle(seed=42)

    if args.dry_run:
        logger.info("\n[DRY RUN] 설정 검증 완료. 학습을 시작하지 않습니다.")
        logger.info(f"  Sections: {len(sections):,}")
        logger.info(f"  Est. steps: {len(sections) * EPOCHS // (BATCH_SIZE * GRAD_ACCUM):,}")
        return 0

    # ── 모델 로드 (bf16 full precision, 양자화 없음) ─────
    logger.info(f"\nLoading model in bf16 (NO quantization): {BASE_MODEL}")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True, padding_side="right")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model.enable_input_require_grads()

    elapsed = time.time() - t0
    logger.info(f"  Model loaded in {elapsed:.1f}s, params={model.num_parameters():,}")

    # ── LoRA 설정 ────────────────────────────────────────
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=LORA_TARGET_MODULES,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        modules_to_save=LORA_MODULES_TO_SAVE,
    )
    model = get_peft_model(model, lora_config)

    trainable, total = model.get_nb_trainable_parameters()
    logger.info(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # ── Training 설정 ────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=SAVE_STEPS,
        save_total_limit=3,
        max_length=MAX_SEQ_LEN,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        optim="adamw_torch",
        dataloader_num_workers=2,
        dataset_text_field="text",
        ddp_find_unused_parameters=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    # ── 학습 시작 ────────────────────────────────────────
    logger.info(f"\nStarting CPT training...")
    logger.info(f"  Epochs: {EPOCHS}")
    logger.info(f"  Batch: {BATCH_SIZE} x {GRAD_ACCUM} grad_accum = {BATCH_SIZE * GRAD_ACCUM} effective")
    logger.info(f"  LR: {LR}, Scheduler: cosine")
    logger.info(f"  Optimizer: adamw_torch (full precision, NOT paged_adamw_8bit)")
    logger.info(f"  Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    trainer.train()

    # ── Adapter 저장 ─────────────────────────────────────
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"  CPT adapter saved: {OUTPUT_DIR}")

    # 학습 리포트
    import json
    report = {
        "model": BASE_MODEL,
        "dataset_version": "v12",
        "quantization": "none (bf16 full precision)",
        "phases_completed": ["cpt"],
        "adapter_paths": {"cpt": OUTPUT_DIR},
        "config": {
            "cpt": {
                "r": LORA_R,
                "alpha": LORA_ALPHA,
                "lr": LR,
                "epochs": EPOCHS,
                "optimizer": "adamw_torch",
                "precision": "bf16",
            }
        },
    }
    report_path = os.path.join(OUTPUT_BASE, "training_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"  Report: {report_path}")

    # 메모리 해제
    del model, trainer
    torch.cuda.empty_cache()

    logger.info(f"\n  Training complete: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
