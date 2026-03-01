#!/usr/bin/env python3
"""
Phase 1: Continued Pre-Training (CPT) Script

도메인 plain text로 next-token prediction 학습을 수행하여
LLM에 OpenFrame 제품 매뉴얼의 전문 지식을 주입합니다.

핵심 차이점 (SFT 대비):
- ChatML 템플릿 없이 순수 텍스트 학습 (Trainer, not SFTTrainer)
- 높은 LoRA rank (r=128 vs SFT r=64)
- 낮은 Learning Rate (2e-5 vs SFT 2e-4)
- embed_tokens + lm_head 포함 (도메인 어휘 적응)
- Dual Learning Rate (임베딩: main LR의 1/10)

Usage:
    python scripts/training/run_cpt_training.py \
        --train-data uploads/training_text/mixed_corpus.txt \
        --output-dir models/cpt_openframe_v1 \
        --gpu 5

    # Dry run (설정 확인만)
    python scripts/training/run_cpt_training.py \
        --train-data uploads/training_text/mixed_corpus.txt --dry-run

Requirements:
    pip install transformers peft datasets accelerate bitsandbytes torch
"""

import os
import sys
import json
import math
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
from torch.utils.data import Dataset as TorchDataset
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
    DataCollatorForLanguageModeling,
)
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
# Special Token Resolution
# ============================================
# Qwen2.5: eos=<|im_end|>(151645), <|endoftext|>(151643) は別 special token
# Qwen3:   eos=<|endoftext|> に変更 (im_end→endoftext)
# → ハードコーディングではなく tokenizer から動的に取得する
QWEN_ENDOFTEXT_TOKEN = "<|endoftext|>"
# Fallback IDs (Qwen2.5 default — tokenizer 取得失敗時のみ使用)
_FALLBACK_ENDOFTEXT_ID = 151643


def resolve_endoftext_id(tokenizer) -> int:
    """tokenizer から <|endoftext|> の token ID を動的に取得する。
    Qwen2.5 と Qwen3 の両方に対応。"""
    try:
        token_id = tokenizer.convert_tokens_to_ids(QWEN_ENDOFTEXT_TOKEN)
        if token_id is not None and token_id != tokenizer.unk_token_id:
            return token_id
    except Exception:
        pass
    logger.warning(
        f"<|endoftext|> token ID をtokenizerから取得できませんでした。"
        f"Fallback ID={_FALLBACK_ENDOFTEXT_ID} を使用します。"
    )
    return _FALLBACK_ENDOFTEXT_ID


# ============================================
# Configuration
# ============================================

@dataclass
class CPTConfig:
    """CPT 학습 설정"""

    # Model
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # QLoRA 4-bit quantization
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True

    # LoRA (CPT용 - SFT보다 높은 rank)
    lora_r: int = 128
    lora_alpha: int = 256
    lora_dropout: float = 0.05
    lora_target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])
    # embed_tokens, lm_head는 modules_to_save로 처리 (full copy)
    modules_to_save: List[str] = field(default_factory=lambda: [
        "embed_tokens", "lm_head",
    ])

    # Training
    learning_rate: float = 2e-5
    embed_lr: float = 2e-6  # embed_tokens/lm_head용 (main LR의 1/10)
    num_epochs: int = 3
    max_seq_length: int = 4096
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    warmup_ratio: float = 0.05
    weight_decay: float = 0.1
    max_grad_norm: float = 1.0

    # Scheduler
    lr_scheduler_type: str = "cosine"
    optim: str = "paged_adamw_32bit"
    bf16: bool = True
    gradient_checkpointing: bool = True

    # Eval
    eval_ratio: float = 0.05
    eval_steps: int = 50
    save_steps: int = 200
    save_total_limit: int = 3
    logging_steps: int = 10

    # Paths
    train_data: str = "uploads/training_text/mixed_corpus.txt"
    output_dir: str = "models/cpt_openframe_v1"

    # GPU
    gpu: str = "0"


# ============================================
# Text Packing Dataset
# ============================================

class TextPackingDataset(TorchDataset):
    """
    Plain text를 고정 길이 토큰 청크로 분할하는 데이터셋.

    CPT 학습에서 표준 방식:
    1. 전체 corpus를 tokenize
    2. 모든 토큰을 연결 (concatenate)
    3. max_seq_length 단위로 분할
    4. 각 청크 = 하나의 학습 예제 (input_ids = labels)
    """

    # 지원하는 문서 구분자 포맷
    SEPARATOR_ENDOFTEXT = "<|endoftext|>"
    SEPARATOR_EQUALS = "=" * 80

    def __init__(
        self,
        text_path: Path,
        tokenizer,
        max_seq_length: int = 4096,
        eos_token_id: Optional[int] = None,
    ):
        self.max_seq_length = max_seq_length
        # tokenizer에서 동적으로 <|endoftext|> ID 취득
        self.eos_id = eos_token_id or resolve_endoftext_id(tokenizer)

        logger.info(f"텍스트 로드 및 토크나이즈: {text_path}")
        logger.info(f"문서 구분자 토큰: id={self.eos_id} "
                     f"(token='{tokenizer.decode([self.eos_id])}')")
        text = text_path.read_text(encoding="utf-8")
        logger.info(f"텍스트 크기: {len(text):,} chars")

        # 자동 포맷 감지: <|endoftext|> vs "====...====" 구분자
        separator = self._detect_separator(text)
        logger.info(f"감지된 구분자 포맷: {repr(separator[:30])}")
        documents = text.split(separator)

        all_tokens = []
        skipped = 0
        for doc in documents:
            doc = doc.strip()
            if not doc or doc.startswith("Document:"):
                skipped += 1
                continue
            # 청크 단위로 토크나이즈 (메모리 절약)
            chunk_size = 50000
            for i in range(0, len(doc), chunk_size):
                chunk = doc[i: i + chunk_size]
                tokens = tokenizer.encode(chunk, add_special_tokens=False)
                all_tokens.extend(tokens)
            # 문서 간 <|endoftext|> 삽입 (문서 경계 표시)
            all_tokens.append(self.eos_id)

        logger.info(f"문서 수: {len(documents) - skipped}, 스킵: {skipped}")

        total_tokens = len(all_tokens)
        logger.info(f"총 토큰 수: {total_tokens:,}")

        # 고정 길이 청크로 분할
        self.examples = []
        for i in range(0, total_tokens - max_seq_length, max_seq_length):
            chunk = all_tokens[i: i + max_seq_length]
            self.examples.append(chunk)

        # 마지막 잔여 청크 (50% 이상이면 포함)
        remainder_start = len(self.examples) * max_seq_length
        remainder = all_tokens[remainder_start:]
        if len(remainder) >= max_seq_length // 2:
            # 패딩
            padded = remainder + [self.eos_id] * (max_seq_length - len(remainder))
            self.examples.append(padded)

        logger.info(
            f"학습 예제 수: {len(self.examples)} "
            f"(각 {max_seq_length} tokens)"
        )

    @staticmethod
    def _detect_separator(text: str) -> str:
        """corpus 파일의 문서 구분자를 자동 감지한다.

        - dataset_pipeline 출력: <|endoftext|> (줄 단위)
        - 레거시 mixed_corpus.txt: "=" * 80
        """
        # 처음 10,000자에서 각 구분자 출현 횟수 확인
        sample = text[:10000]
        eot_count = sample.count(TextPackingDataset.SEPARATOR_ENDOFTEXT)
        eq_count = sample.count(TextPackingDataset.SEPARATOR_EQUALS)

        if eot_count > eq_count:
            return TextPackingDataset.SEPARATOR_ENDOFTEXT
        elif eq_count > 0:
            return TextPackingDataset.SEPARATOR_EQUALS
        # fallback: 줄바꿈 2개로 분할 (단일 문서 취급 방지)
        logger.warning("알려진 구분자를 감지하지 못했습니다. <|endoftext|>를 기본값으로 사용합니다.")
        return TextPackingDataset.SEPARATOR_ENDOFTEXT

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        tokens = self.examples[idx]
        input_ids = torch.tensor(tokens, dtype=torch.long)
        return {
            "input_ids": input_ids,
            "labels": input_ids.clone(),
            "attention_mask": torch.ones(len(tokens), dtype=torch.long),
        }


# ============================================
# Custom Trainer with Dual Learning Rate
# ============================================

class CPTTrainer(Trainer):
    """
    Dual Learning Rate를 지원하는 커스텀 Trainer.

    - LoRA params: main learning_rate (2e-5)
    - embed_tokens/lm_head: embed_lr (2e-6, main의 1/10)
    """

    def __init__(self, *args, embed_lr: float = 2e-6, **kwargs):
        self.embed_lr = embed_lr
        super().__init__(*args, **kwargs)

    def create_optimizer(self):
        if self.optimizer is not None:
            return self.optimizer

        embed_params = []
        main_params = []

        for name, param in self.model.named_parameters():
            if not param.requires_grad:
                continue
            if "embed_tokens" in name or "lm_head" in name:
                embed_params.append(param)
            else:
                main_params.append(param)

        logger.info(
            f"Optimizer groups: main={len(main_params)} params, "
            f"embed={len(embed_params)} params"
        )
        logger.info(
            f"Learning rates: main={self.args.learning_rate}, "
            f"embed={self.embed_lr}"
        )

        optimizer_grouped_parameters = [
            {
                "params": main_params,
                "lr": self.args.learning_rate,
                "weight_decay": self.args.weight_decay,
            },
            {
                "params": embed_params,
                "lr": self.embed_lr,
                "weight_decay": self.args.weight_decay,
            },
        ]

        # paged_adamw_32bit
        from transformers.optimization import get_scheduler
        import bitsandbytes as bnb

        self.optimizer = bnb.optim.PagedAdamW32bit(
            optimizer_grouped_parameters,
            lr=self.args.learning_rate,
            betas=(0.9, 0.999),
            eps=1e-8,
        )

        return self.optimizer


# ============================================
# Model Setup
# ============================================

def setup_model_and_tokenizer(config: CPTConfig):
    """4-bit 양자화 모델 + CPT용 LoRA 설정"""

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

    # pad_token を <|endoftext|> に設定
    # Qwen2.5: eos=<|im_end|>, pad=<|endoftext|> (別トークン)
    # Qwen3:   eos=<|endoftext|>, pad も同じ → PAD≠EOS の警告に注意
    endoftext_id = resolve_endoftext_id(tokenizer)
    tokenizer.pad_token = QWEN_ENDOFTEXT_TOKEN
    tokenizer.pad_token_id = endoftext_id
    model.config.pad_token_id = endoftext_id

    # Qwen3 では eos_token == pad_token になる → 学習時 EOS マスク問題に注意
    if tokenizer.eos_token_id == endoftext_id:
        logger.warning(
            "eos_token_id == pad_token_id (Qwen3 パターン). "
            "EOS トークンが PAD マスクで無視される可能性があります。"
        )

    logger.info(f"Special tokens: eos={tokenizer.eos_token}({tokenizer.eos_token_id}), "
                f"pad={tokenizer.pad_token}({tokenizer.pad_token_id}), "
                f"endoftext_id={endoftext_id}")

    # kbit training 준비
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=config.gradient_checkpointing
    )

    # LoRA 설정 (CPT용)
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.lora_target_modules,
        modules_to_save=config.modules_to_save,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# ============================================
# Training
# ============================================

def train(config: CPTConfig):
    """CPT 학습 실행"""

    # GPU 설정
    os.environ["CUDA_VISIBLE_DEVICES"] = config.gpu
    logger.info(f"GPU: {config.gpu}")

    # 모델 + 토크나이저
    model, tokenizer = setup_model_and_tokenizer(config)

    # 데이터 로드
    train_path = Path(config.train_data)
    if not train_path.exists():
        raise FileNotFoundError(
            f"학습 데이터 없음: {train_path}\n"
            "먼저 prepare_mixing_data.py를 실행하세요."
        )

    dataset = TextPackingDataset(
        train_path,
        tokenizer,
        max_seq_length=config.max_seq_length,
    )

    # Train/Eval 분할
    total = len(dataset)
    eval_size = max(1, int(total * config.eval_ratio))
    train_size = total - eval_size

    train_dataset = torch.utils.data.Subset(dataset, range(train_size))
    eval_dataset = torch.utils.data.Subset(dataset, range(train_size, total))

    logger.info(f"Train: {train_size} examples, Eval: {eval_size} examples")

    # 출력 디렉토리
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Training Arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
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
        dataloader_pin_memory=False,
    )

    # Trainer (Dual LR)
    trainer = CPTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        embed_lr=config.embed_lr,
    )

    # 학습 시작
    logger.info("=" * 60)
    logger.info("CPT 학습 시작")
    logger.info(f"  Base Model: {config.base_model}")
    logger.info(f"  LoRA r={config.lora_r}, alpha={config.lora_alpha}")
    logger.info(f"  LR: main={config.learning_rate}, embed={config.embed_lr}")
    logger.info(f"  Epochs: {config.num_epochs}")
    logger.info(f"  Effective batch: {config.batch_size * config.gradient_accumulation_steps}")
    logger.info(f"  Max seq length: {config.max_seq_length}")
    logger.info(f"  Train examples: {train_size}")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    start_time = datetime.now()
    train_result = trainer.train()
    elapsed = datetime.now() - start_time

    # 결과 저장
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Eval perplexity
    eval_results = trainer.evaluate()
    eval_loss = eval_results.get("eval_loss", 0)
    perplexity = math.exp(eval_loss) if eval_loss < 100 else float("inf")

    # 메타데이터 저장
    metadata = {
        "phase": "cpt",
        "base_model": config.base_model,
        "train_data": config.train_data,
        "lora_r": config.lora_r,
        "lora_alpha": config.lora_alpha,
        "learning_rate": config.learning_rate,
        "embed_lr": config.embed_lr,
        "num_epochs": config.num_epochs,
        "max_seq_length": config.max_seq_length,
        "train_examples": train_size,
        "eval_examples": eval_size,
        "train_loss": train_result.training_loss,
        "eval_loss": eval_loss,
        "eval_perplexity": perplexity,
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
    logger.info("CPT 학습 완료!")
    logger.info(f"  Train Loss: {train_result.training_loss:.4f}")
    logger.info(f"  Eval Loss: {eval_loss:.4f}")
    logger.info(f"  Eval Perplexity: {perplexity:.2f}")
    logger.info(f"  소요 시간: {elapsed}")
    logger.info(f"  Adapter 저장: {output_dir}")
    logger.info("=" * 60)

    return metadata


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Continued Pre-Training (CPT)",
    )

    # Model
    parser.add_argument(
        "--base-model",
        default=CPTConfig.base_model,
        help="Base model 경로 또는 HuggingFace ID",
    )

    # Data
    parser.add_argument(
        "--train-data",
        default=CPTConfig.train_data,
        help="학습 데이터 경로 (plain text)",
    )
    parser.add_argument(
        "--output-dir",
        default=CPTConfig.output_dir,
        help="Adapter 출력 디렉토리",
    )

    # LoRA
    parser.add_argument("--lora-rank", type=int, default=128)
    parser.add_argument("--lora-alpha", type=int, default=256)
    parser.add_argument("--lora-dropout", type=float, default=0.05)

    # Training
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--embed-lr", type=float, default=2e-6)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--warmup-ratio", type=float, default=0.05)
    parser.add_argument("--weight-decay", type=float, default=0.1)

    # GPU
    parser.add_argument("--gpu", default="0", help="CUDA device index")

    # Misc
    parser.add_argument("--dry-run", action="store_true", help="설정 확인만")

    args = parser.parse_args()

    config = CPTConfig(
        base_model=args.base_model,
        train_data=args.train_data,
        output_dir=args.output_dir,
        lora_r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        learning_rate=args.learning_rate,
        embed_lr=args.embed_lr,
        num_epochs=args.epochs,
        max_seq_length=args.max_seq_length,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        gpu=args.gpu,
    )

    if args.dry_run:
        print("\n=== CPT Config (Dry Run) ===")
        print(f"Base Model: {config.base_model}")
        print(f"Train Data: {config.train_data}")
        print(f"Output Dir: {config.output_dir}")
        print(f"LoRA: r={config.lora_r}, alpha={config.lora_alpha}, dropout={config.lora_dropout}")
        print(f"Modules to save: {config.modules_to_save}")
        print(f"LR: main={config.learning_rate}, embed={config.embed_lr}")
        print(f"Epochs: {config.num_epochs}, Max Seq: {config.max_seq_length}")
        print(f"Batch: {config.batch_size} x {config.gradient_accumulation_steps} = {config.batch_size * config.gradient_accumulation_steps}")
        print(f"GPU: {config.gpu}")

        # 데이터 크기 확인
        data_path = Path(config.train_data)
        if data_path.exists():
            size = data_path.stat().st_size
            print(f"\nData size: {size / 1024 / 1024:.1f} MB")
            estimated_examples = size // (config.max_seq_length * 2)
            print(f"Estimated examples: ~{estimated_examples}")
            total_steps = (estimated_examples // (config.batch_size * config.gradient_accumulation_steps)) * config.num_epochs
            print(f"Estimated total steps: ~{total_steps}")
        else:
            print(f"\nWARNING: Train data not found: {data_path}")
        return

    train(config)


if __name__ == "__main__":
    main()
