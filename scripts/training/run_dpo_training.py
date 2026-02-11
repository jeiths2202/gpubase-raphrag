#!/usr/bin/env python3
"""
Phase 3: Direct Preference Optimization (DPO) Training Script

SFT 완료 후 모델의 응답 품질을 preference pair로 정렬합니다.
Hallucination(환각)을 억제하고 정확한 답변을 선호하도록 학습합니다.

Usage:
    python scripts/training/run_dpo_training.py \
        --base-model models/qwen2.5-7b-openframe-sft \
        --dpo-data uploads/training_text/dpo_pairs.json \
        --output-dir models/dpo_openframe_v1 \
        --gpu 5

    # Dry run
    python scripts/training/run_dpo_training.py \
        --dpo-data uploads/training_text/dpo_pairs.json --dry-run

Requirements:
    pip install transformers peft datasets accelerate bitsandbytes trl
"""

import os
import sys
import json
import math
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import DPOTrainer, DPOConfig as TRLDPOConfig
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================
# Configuration
# ============================================

@dataclass
class DPOTrainConfig:
    """DPO 학습 설정"""

    # Model (SFT 병합 모델)
    base_model: str = "models/qwen2.5-7b-openframe-sft"

    # QLoRA 4-bit
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True

    # LoRA (DPO - 낮은 rank)
    lora_r: int = 32
    lora_alpha: int = 64
    lora_dropout: float = 0.05
    lora_target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])

    # DPO 전용
    beta: float = 0.1  # KL penalty coefficient
    max_prompt_length: int = 512
    max_length: int = 2048

    # Training
    learning_rate: float = 5e-6  # 매우 낮음 (alignment, not learning)
    num_epochs: int = 2
    batch_size: int = 1
    gradient_accumulation_steps: int = 4
    warmup_ratio: float = 0.1
    weight_decay: float = 0.05
    max_grad_norm: float = 1.0

    # Scheduler
    lr_scheduler_type: str = "cosine"
    optim: str = "paged_adamw_32bit"
    bf16: bool = True
    gradient_checkpointing: bool = True

    # Eval/Save
    eval_ratio: float = 0.1
    eval_steps: int = 50
    save_steps: int = 100
    save_total_limit: int = 2
    logging_steps: int = 10

    # Paths
    dpo_data: str = "uploads/training_text/dpo_pairs.json"
    output_dir: str = "models/dpo_openframe_v1"

    # GPU
    gpu: str = "0"


# ============================================
# Data Loading
# ============================================

def load_dpo_dataset(data_path: str, eval_ratio: float = 0.1):
    """DPO pair JSON → HuggingFace Dataset"""
    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(
            f"DPO 데이터 없음: {path}\n"
            "먼저 generate_dpo_data.py를 실행하세요."
        )

    pairs = json.loads(path.read_text(encoding="utf-8"))
    logger.info(f"DPO pairs 로드: {len(pairs)}개")

    # DPOTrainer 형식으로 변환
    formatted = []
    for pair in pairs:
        if not pair.get("prompt") or not pair.get("chosen") or not pair.get("rejected"):
            continue
        formatted.append({
            "prompt": pair["prompt"],
            "chosen": pair["chosen"],
            "rejected": pair["rejected"],
        })

    if not formatted:
        raise ValueError("유효한 DPO pair가 없습니다")

    # Train/Eval 분할
    import random
    random.seed(42)
    random.shuffle(formatted)

    eval_size = max(1, int(len(formatted) * eval_ratio))
    train_data = formatted[eval_size:]
    eval_data = formatted[:eval_size]

    train_dataset = Dataset.from_list(train_data)
    eval_dataset = Dataset.from_list(eval_data)

    logger.info(f"Train: {len(train_data)}, Eval: {len(eval_data)}")
    return train_dataset, eval_dataset


# ============================================
# Model Setup
# ============================================

def setup_dpo_model(config: DPOTrainConfig):
    """4-bit 양자화 모델 + DPO용 LoRA 설정"""
    logger.info(f"모델 로드: {config.base_model}")

    compute_dtype = getattr(torch, config.bnb_4bit_compute_dtype)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
    )

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map={"": int(config.gpu)},
        trust_remote_code=True,
        torch_dtype=compute_dtype,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model,
        trust_remote_code=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        model.config.pad_token_id = tokenizer.eos_token_id

    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=config.gradient_checkpointing
    )

    # LoRA (DPO용 - 낮은 rank)
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.lora_target_modules,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# ============================================
# Training
# ============================================

def train(config: DPOTrainConfig):
    """DPO 학습 실행"""

    os.environ["CUDA_VISIBLE_DEVICES"] = config.gpu
    logger.info(f"GPU: {config.gpu}")

    # 모델 + 토크나이저
    model, tokenizer = setup_dpo_model(config)

    # 데이터 로드
    train_dataset, eval_dataset = load_dpo_dataset(
        config.dpo_data, config.eval_ratio
    )

    # 출력 디렉토리
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # DPO Training Config
    dpo_config = TRLDPOConfig(
        output_dir=str(output_dir),
        beta=config.beta,
        max_prompt_length=config.max_prompt_length,
        max_length=config.max_length,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        lr_scheduler_type=config.lr_scheduler_type,
        warmup_ratio=config.warmup_ratio,
        weight_decay=config.weight_decay,
        max_grad_norm=config.max_grad_norm,
        optim=config.optim,
        bf16=config.bf16,
        gradient_checkpointing=config.gradient_checkpointing,
        eval_strategy="steps",
        eval_steps=config.eval_steps,
        save_strategy="steps",
        save_steps=config.save_steps,
        save_total_limit=config.save_total_limit,
        logging_steps=config.logging_steps,
        report_to="none",
        remove_unused_columns=False,
    )

    # DPOTrainer (ref_model=None: PEFT 사용 시 base weights가 reference)
    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=dpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
    )

    logger.info("=" * 60)
    logger.info("DPO 학습 시작")
    logger.info(f"  Base Model: {config.base_model}")
    logger.info(f"  LoRA: r={config.lora_r}, alpha={config.lora_alpha}")
    logger.info(f"  Beta: {config.beta}")
    logger.info(f"  LR: {config.learning_rate}")
    logger.info(f"  Epochs: {config.num_epochs}")
    logger.info(f"  Train pairs: {len(train_dataset)}")
    logger.info(f"  Eval pairs: {len(eval_dataset)}")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    start_time = datetime.now()
    train_result = trainer.train()
    elapsed = datetime.now() - start_time

    # 결과 저장
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Eval
    eval_results = trainer.evaluate()

    # 메타데이터 저장
    metadata = {
        "phase": "dpo",
        "base_model": config.base_model,
        "dpo_data": config.dpo_data,
        "beta": config.beta,
        "lora_r": config.lora_r,
        "learning_rate": config.learning_rate,
        "num_epochs": config.num_epochs,
        "train_pairs": len(train_dataset),
        "eval_pairs": len(eval_dataset),
        "train_loss": train_result.training_loss,
        "eval_results": {k: float(v) for k, v in eval_results.items()},
        "elapsed_seconds": elapsed.total_seconds(),
        "elapsed_formatted": str(elapsed),
        "completed_at": datetime.now().isoformat(),
    }

    meta_path = output_dir / "training_metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("=" * 60)
    logger.info("DPO 학습 완료!")
    logger.info(f"  Train Loss: {train_result.training_loss:.4f}")
    for k, v in eval_results.items():
        logger.info(f"  {k}: {float(v):.4f}")
    logger.info(f"  소요 시간: {elapsed}")
    logger.info(f"  Adapter 저장: {output_dir}")
    logger.info("=" * 60)

    return metadata


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Phase 3: DPO (Direct Preference Optimization)",
    )

    parser.add_argument(
        "--base-model",
        default=DPOTrainConfig.base_model,
        help="SFT 병합 모델 경로",
    )
    parser.add_argument(
        "--dpo-data",
        default=DPOTrainConfig.dpo_data,
        help="DPO preference pair JSON 경로",
    )
    parser.add_argument(
        "--output-dir",
        default=DPOTrainConfig.output_dir,
        help="DPO adapter 출력 디렉토리",
    )

    # DPO
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--max-prompt-length", type=int, default=512)
    parser.add_argument("--max-length", type=int, default=2048)

    # LoRA
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)

    # Training
    parser.add_argument("--learning-rate", type=float, default=5e-6)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)

    # GPU
    parser.add_argument("--gpu", default="0")

    # Misc
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    config = DPOTrainConfig(
        base_model=args.base_model,
        dpo_data=args.dpo_data,
        output_dir=args.output_dir,
        beta=args.beta,
        max_prompt_length=args.max_prompt_length,
        max_length=args.max_length,
        lora_r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        learning_rate=args.learning_rate,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gpu=args.gpu,
    )

    if args.dry_run:
        print("\n=== DPO Config (Dry Run) ===")
        print(f"Base Model: {config.base_model}")
        print(f"DPO Data: {config.dpo_data}")
        print(f"Output Dir: {config.output_dir}")
        print(f"Beta: {config.beta}")
        print(f"LoRA: r={config.lora_r}, alpha={config.lora_alpha}")
        print(f"LR: {config.learning_rate}")
        print(f"Epochs: {config.num_epochs}")
        print(f"GPU: {config.gpu}")

        data_path = Path(config.dpo_data)
        if data_path.exists():
            pairs = json.loads(data_path.read_text(encoding="utf-8"))
            print(f"\nDPO pairs: {len(pairs)}")
        else:
            print(f"\nWARNING: DPO data not found: {data_path}")
        return

    train(config)


if __name__ == "__main__":
    main()
