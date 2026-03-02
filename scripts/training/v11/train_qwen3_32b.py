"""
Qwen3-32B QLoRA 3-Phase Training Pipeline (v11)
Phase 1: CPT  — Continued Pre-Training (domain corpus)
Phase 2: SFT  — Supervised Fine-Tuning (Q&A pairs)
Phase 3: DPO  — Direct Preference Optimization (alignment)

Usage:
    # 전체 파이프라인 (CPT → SFT → DPO)
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase all

    # 개별 Phase 실행
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase cpt
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase sft
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase dpo

    # SFT만 (CPT adapter 로드)
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase sft --cpt-adapter /path/to/cpt_adapter

    # DPO만 (SFT adapter 로드)
    accelerate launch --config_file configs/accelerate_2gpu.yaml train_qwen3_32b.py --phase dpo --sft-adapter /path/to/sft_adapter
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("v11-trainer")

# ── 환경 변수 (루트 디스크 사용 방지) ──────────────────────
os.environ.setdefault("HF_HOME", "/raid/users/ofuser/.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/raid/users/ofuser/.cache/huggingface/hub")
os.environ.setdefault("HF_DATASETS_CACHE", "/raid/users/ofuser/.cache/huggingface/datasets")
os.environ.setdefault("TMPDIR", "/raid/users/ofuser/tmp")


# ── Config ────────────────────────────────────────────────
@dataclass
class TrainConfig:
    # 모델
    model_name: str = "/raid/users/ofuser/models/Qwen3-32B"

    # 데이터 경로
    data_dir: str = "scripts/training/v11/output"
    cpt_corpus: str = "cpt_corpus.txt"
    sft_train: str = "sft_train.jsonl"
    sft_eval: str = "sft_eval.jsonl"
    dpo_train: str = "dpo_train.jsonl"
    dpo_eval: str = "dpo_eval.jsonl"

    # 출력 경로
    output_base: str = "/raid/users/ofuser/qlora/outputs/v11_qwen3_32b"

    # 양자화
    quant_bits: int = 4
    quant_type: str = "nf4"
    double_quant: bool = True
    compute_dtype: str = "bfloat16"

    # LoRA 공통
    lora_target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])
    lora_dropout: float = 0.05

    # ── Phase 1: CPT ─────────────
    cpt_lora_r: int = 64
    cpt_lora_alpha: int = 128
    cpt_lr: float = 1e-5
    cpt_epochs: int = 2
    cpt_batch_size: int = 1
    cpt_grad_accum: int = 8
    cpt_max_seq_len: int = 4096
    cpt_warmup_ratio: float = 0.05
    cpt_weight_decay: float = 0.01
    cpt_save_steps: int = 500
    cpt_modules_to_save: list = field(default_factory=lambda: ["embed_tokens", "lm_head"])

    # ── Phase 2: SFT ─────────────
    sft_lora_r: int = 64
    sft_lora_alpha: int = 128
    sft_lr: float = 2e-5
    sft_epochs: int = 3
    sft_batch_size: int = 1
    sft_grad_accum: int = 8
    sft_max_seq_len: int = 2048
    sft_warmup_ratio: float = 0.05
    sft_weight_decay: float = 0.01
    sft_save_steps: int = 500

    # ── Phase 3: DPO ─────────────
    dpo_lora_r: int = 32
    dpo_lora_alpha: int = 64
    dpo_lr: float = 5e-6
    dpo_beta: float = 0.1
    dpo_epochs: int = 2
    dpo_batch_size: int = 1
    dpo_grad_accum: int = 4
    dpo_max_seq_len: int = 2048
    dpo_warmup_ratio: float = 0.1
    dpo_weight_decay: float = 0.01
    dpo_save_steps: int = 200


# ── 유틸 함수 ────────────────────────────────────────────

def get_bnb_config(cfg: TrainConfig) -> BitsAndBytesConfig:
    """4-bit NF4 양자화 설정"""
    compute_dtype = getattr(torch, cfg.compute_dtype)
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=cfg.quant_type,
        bnb_4bit_use_double_quant=cfg.double_quant,
        bnb_4bit_compute_dtype=compute_dtype,
    )


def _get_device_map():
    """DDP vs 단일 프로세스 환경에 따라 device_map 결정"""
    local_rank = int(os.environ.get("LOCAL_RANK", -1))
    if local_rank >= 0:
        # DDP 모드: 각 프로세스가 자기 GPU에 로드
        return {"": local_rank}
    else:
        # 단일 프로세스: 여러 GPU에 모델 분산 (모델 병렬)
        num_gpus = torch.cuda.device_count()
        if num_gpus > 1:
            logger.info(f"  Model parallelism: device_map='auto' across {num_gpus} GPUs")
            return "auto"
        return {"": 0}


def load_base_model(cfg: TrainConfig, device_map=None):
    """Qwen3-32B 모델 + 토크나이저 로드 (4-bit 양자화)"""
    logger.info(f"Loading model: {cfg.model_name}")

    if device_map is None:
        device_map = _get_device_map()

    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model_name,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    bnb_config = get_bnb_config(cfg)
    model = AutoModelForCausalLM.from_pretrained(
        cfg.model_name,
        quantization_config=bnb_config,
        device_map=device_map,
        dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    logger.info(f"Model loaded: {model.dtype}, params={model.num_parameters():,}")
    return model, tokenizer


def load_model_with_adapter(cfg: TrainConfig, adapter_path: str, device_map=None):
    """기존 adapter 로드하여 merged 모델 반환 (다음 Phase용)"""
    logger.info(f"Loading base model + adapter: {adapter_path}")

    if device_map is None:
        device_map = _get_device_map()

    tokenizer = AutoTokenizer.from_pretrained(
        cfg.model_name,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    bnb_config = get_bnb_config(cfg)
    model = AutoModelForCausalLM.from_pretrained(
        cfg.model_name,
        quantization_config=bnb_config,
        device_map=device_map,
        dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False

    # 기존 adapter 로드 후 merge
    model = PeftModel.from_pretrained(model, adapter_path)
    model = model.merge_and_unload()
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    logger.info(f"Model with merged adapter loaded, params={model.num_parameters():,}")
    return model, tokenizer


def resolve_data_path(cfg: TrainConfig, filename: str) -> str:
    """프로젝트 루트 기준 데이터 경로 resolve"""
    # 절대 경로이면 그대로 사용
    p = Path(filename)
    if p.is_absolute() and p.exists():
        return str(p)

    # data_dir 기준
    p = Path(cfg.data_dir) / filename
    if p.exists():
        return str(p)

    # 현재 스크립트 디렉토리 기준
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent  # scripts/training/v11 → project root
    p = project_root / cfg.data_dir / filename
    if p.exists():
        return str(p)

    raise FileNotFoundError(f"Data file not found: {filename} (tried {cfg.data_dir}/{filename})")


# ── Phase 1: CPT ─────────────────────────────────────────

def run_cpt(cfg: TrainConfig) -> str:
    """Continued Pre-Training: 도메인 텍스트 코퍼스 학습"""
    output_dir = os.path.join(cfg.output_base, "cpt_adapter")
    logger.info("=" * 60)
    logger.info("Phase 1: CPT (Continued Pre-Training)")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    model, tokenizer = load_base_model(cfg)

    # LoRA 설정 (CPT: embed_tokens, lm_head 포함)
    lora_config = LoraConfig(
        r=cfg.cpt_lora_r,
        lora_alpha=cfg.cpt_lora_alpha,
        target_modules=cfg.lora_target_modules,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        modules_to_save=cfg.cpt_modules_to_save,
    )
    model = get_peft_model(model, lora_config)
    trainable, total = model.get_nb_trainable_parameters()
    logger.info(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # 데이터 로드
    corpus_path = resolve_data_path(cfg, cfg.cpt_corpus)
    logger.info(f"  Loading CPT corpus: {corpus_path}")

    # 텍스트 파일을 섹션별로 분할
    with open(corpus_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    sections = [s.strip() for s in raw_text.split("\n\n") if len(s.strip()) > 50]
    logger.info(f"  Corpus sections: {len(sections):,}")

    dataset = Dataset.from_dict({"text": sections})
    dataset = dataset.shuffle(seed=42)

    # Training 설정
    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=cfg.cpt_epochs,
        per_device_train_batch_size=cfg.cpt_batch_size,
        gradient_accumulation_steps=cfg.cpt_grad_accum,
        learning_rate=cfg.cpt_lr,
        lr_scheduler_type="cosine",
        warmup_ratio=cfg.cpt_warmup_ratio,
        weight_decay=cfg.cpt_weight_decay,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",
        save_steps=cfg.cpt_save_steps,
        save_total_limit=3,
        max_length=cfg.cpt_max_seq_len,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        optim="paged_adamw_8bit",
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

    logger.info("  Starting CPT training...")
    trainer.train()

    # Adapter 저장
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"  CPT adapter saved: {output_dir}")

    # 메모리 해제
    del model, trainer
    torch.cuda.empty_cache()

    return output_dir


# ── Phase 2: SFT ─────────────────────────────────────────

def run_sft(cfg: TrainConfig, cpt_adapter: Optional[str] = None) -> str:
    """Supervised Fine-Tuning: Q&A 쌍 학습"""
    output_dir = os.path.join(cfg.output_base, "sft_adapter")
    logger.info("=" * 60)
    logger.info("Phase 2: SFT (Supervised Fine-Tuning)")
    logger.info(f"  CPT adapter: {cpt_adapter or 'None (fresh base model)'}")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    # 모델 로드 (CPT adapter 있으면 merge)
    if cpt_adapter and os.path.exists(cpt_adapter):
        model, tokenizer = load_model_with_adapter(cfg, cpt_adapter)
    else:
        model, tokenizer = load_base_model(cfg)

    # LoRA 설정 (SFT: embed 제외)
    lora_config = LoraConfig(
        r=cfg.sft_lora_r,
        lora_alpha=cfg.sft_lora_alpha,
        target_modules=cfg.lora_target_modules,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    trainable, total = model.get_nb_trainable_parameters()
    logger.info(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # 데이터 로드
    train_path = resolve_data_path(cfg, cfg.sft_train)
    eval_path = resolve_data_path(cfg, cfg.sft_eval)
    logger.info(f"  Train: {train_path}")
    logger.info(f"  Eval:  {eval_path}")

    train_dataset = load_dataset("json", data_files=train_path, split="train")
    eval_dataset = load_dataset("json", data_files=eval_path, split="train")
    logger.info(f"  Train samples: {len(train_dataset):,}, Eval samples: {len(eval_dataset):,}")

    # Training 설정
    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=cfg.sft_epochs,
        per_device_train_batch_size=cfg.sft_batch_size,
        per_device_eval_batch_size=cfg.sft_batch_size,
        gradient_accumulation_steps=cfg.sft_grad_accum,
        learning_rate=cfg.sft_lr,
        lr_scheduler_type="cosine",
        warmup_ratio=cfg.sft_warmup_ratio,
        weight_decay=cfg.sft_weight_decay,
        bf16=True,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=cfg.sft_save_steps,
        save_strategy="steps",
        save_steps=cfg.sft_save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        max_length=cfg.sft_max_seq_len,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        optim="paged_adamw_8bit",
        dataloader_num_workers=2,
        ddp_find_unused_parameters=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    logger.info("  Starting SFT training...")
    trainer.train()

    # Adapter 저장
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"  SFT adapter saved: {output_dir}")

    # 메모리 해제
    del model, trainer
    torch.cuda.empty_cache()

    return output_dir


# ── Phase 3: DPO ─────────────────────────────────────────

def run_dpo(cfg: TrainConfig, sft_adapter: Optional[str] = None) -> str:
    """Direct Preference Optimization: 선호도 기반 정렬"""
    output_dir = os.path.join(cfg.output_base, "dpo_adapter")
    logger.info("=" * 60)
    logger.info("Phase 3: DPO (Direct Preference Optimization)")
    logger.info(f"  SFT adapter: {sft_adapter or 'None (fresh base model)'}")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    # 모델 로드 (SFT adapter 있으면 merge)
    if sft_adapter and os.path.exists(sft_adapter):
        model, tokenizer = load_model_with_adapter(cfg, sft_adapter)
    else:
        model, tokenizer = load_base_model(cfg)

    # LoRA 설정 (DPO: 작은 rank)
    lora_config = LoraConfig(
        r=cfg.dpo_lora_r,
        lora_alpha=cfg.dpo_lora_alpha,
        target_modules=cfg.lora_target_modules,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    trainable, total = model.get_nb_trainable_parameters()
    logger.info(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # 데이터 로드
    train_path = resolve_data_path(cfg, cfg.dpo_train)
    eval_path = resolve_data_path(cfg, cfg.dpo_eval)
    logger.info(f"  Train: {train_path}")
    logger.info(f"  Eval:  {eval_path}")

    train_dataset = load_dataset("json", data_files=train_path, split="train")
    eval_dataset = load_dataset("json", data_files=eval_path, split="train")
    logger.info(f"  Train samples: {len(train_dataset):,}, Eval samples: {len(eval_dataset):,}")

    # metadata 컬럼 제거 (DPOTrainer는 prompt/chosen/rejected만 필요)
    cols_to_remove = [c for c in train_dataset.column_names if c not in ("prompt", "chosen", "rejected")]
    if cols_to_remove:
        train_dataset = train_dataset.remove_columns(cols_to_remove)
        eval_dataset = eval_dataset.remove_columns(cols_to_remove)

    # DPO Training 설정
    training_args = DPOConfig(
        output_dir=output_dir,
        num_train_epochs=cfg.dpo_epochs,
        per_device_train_batch_size=cfg.dpo_batch_size,
        per_device_eval_batch_size=cfg.dpo_batch_size,
        gradient_accumulation_steps=cfg.dpo_grad_accum,
        learning_rate=cfg.dpo_lr,
        lr_scheduler_type="cosine",
        warmup_ratio=cfg.dpo_warmup_ratio,
        weight_decay=cfg.dpo_weight_decay,
        beta=cfg.dpo_beta,
        bf16=True,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=cfg.dpo_save_steps,
        save_strategy="steps",
        save_steps=cfg.dpo_save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        max_length=cfg.dpo_max_seq_len,
        max_prompt_length=cfg.dpo_max_seq_len // 2,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        optim="paged_adamw_8bit",
        dataloader_num_workers=2,
        ddp_find_unused_parameters=False,
    )

    # DPOTrainer에는 ref_model이 필요하지만 PEFT 사용 시 자동 처리
    trainer = DPOTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    logger.info("  Starting DPO training...")
    trainer.train()

    # Adapter 저장
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"  DPO adapter saved: {output_dir}")

    # 메모리 해제
    del model, trainer
    torch.cuda.empty_cache()

    return output_dir


# ── 메인 ─────────────────────────────────────────────────

def save_training_report(cfg: TrainConfig, phases_completed: list, adapter_paths: dict):
    """학습 완료 보고서 저장"""
    report = {
        "model": cfg.model_name,
        "dataset_version": "v11",
        "phases_completed": phases_completed,
        "adapter_paths": adapter_paths,
        "config": {
            "cpt": {"r": cfg.cpt_lora_r, "alpha": cfg.cpt_lora_alpha, "lr": cfg.cpt_lr, "epochs": cfg.cpt_epochs},
            "sft": {"r": cfg.sft_lora_r, "alpha": cfg.sft_lora_alpha, "lr": cfg.sft_lr, "epochs": cfg.sft_epochs},
            "dpo": {"r": cfg.dpo_lora_r, "alpha": cfg.dpo_lora_alpha, "lr": cfg.dpo_lr, "epochs": cfg.dpo_epochs, "beta": cfg.dpo_beta},
        },
    }
    report_path = os.path.join(cfg.output_base, "training_report.json")
    os.makedirs(cfg.output_base, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Training report saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Qwen3-32B v11 QLoRA Training Pipeline")
    parser.add_argument(
        "--phase", type=str, required=True,
        choices=["cpt", "sft", "dpo", "all", "sft-dpo"],
        help="Training phase: cpt, sft, dpo, sft-dpo, all (CPT→SFT→DPO)",
    )
    parser.add_argument("--cpt-adapter", type=str, default=None, help="Path to CPT adapter (for SFT phase)")
    parser.add_argument("--sft-adapter", type=str, default=None, help="Path to SFT adapter (for DPO phase)")
    parser.add_argument("--output-base", type=str, default=None, help="Override output base directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and data only")
    args = parser.parse_args()

    cfg = TrainConfig()
    if args.output_base:
        cfg.output_base = args.output_base

    os.makedirs(cfg.output_base, exist_ok=True)

    # Dry run: 설정 & 데이터 검증만
    if args.dry_run:
        logger.info("=== DRY RUN: Validating configuration ===")
        logger.info(f"Model: {cfg.model_name}")
        logger.info(f"Output: {cfg.output_base}")

        for name, filename in [
            ("CPT corpus", cfg.cpt_corpus),
            ("SFT train", cfg.sft_train),
            ("SFT eval", cfg.sft_eval),
            ("DPO train", cfg.dpo_train),
            ("DPO eval", cfg.dpo_eval),
        ]:
            try:
                path = resolve_data_path(cfg, filename)
                size = os.path.getsize(path)
                logger.info(f"  {name}: {path} ({size:,} bytes)")
            except FileNotFoundError as e:
                logger.error(f"  {name}: NOT FOUND - {e}")

        logger.info("=== Dry run complete ===")
        return 0

    phases_completed = []
    adapter_paths = {}

    if args.phase in ("cpt", "all"):
        cpt_path = run_cpt(cfg)
        phases_completed.append("cpt")
        adapter_paths["cpt"] = cpt_path
    else:
        cpt_path = args.cpt_adapter

    if args.phase in ("sft", "sft-dpo", "all"):
        if args.phase == "all":
            sft_path = run_sft(cfg, cpt_adapter=cpt_path)
        else:
            sft_path = run_sft(cfg, cpt_adapter=args.cpt_adapter)
        phases_completed.append("sft")
        adapter_paths["sft"] = sft_path
    else:
        sft_path = args.sft_adapter

    if args.phase in ("dpo", "sft-dpo", "all"):
        if args.phase in ("all", "sft-dpo"):
            dpo_path = run_dpo(cfg, sft_adapter=sft_path)
        else:
            dpo_path = run_dpo(cfg, sft_adapter=args.sft_adapter)
        phases_completed.append("dpo")
        adapter_paths["dpo"] = dpo_path

    save_training_report(cfg, phases_completed, adapter_paths)
    logger.info("=" * 60)
    logger.info("All phases complete!")
    for phase, path in adapter_paths.items():
        logger.info(f"  {phase.upper()}: {path}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
