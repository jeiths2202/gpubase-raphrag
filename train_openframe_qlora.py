#!/usr/bin/env python3
"""
OpenFrame QLoRA Training Script

JSONL 파일에서 직접 학습 데이터를 로드하여 QLoRA 파인튜닝을 수행합니다.
4-bit 양자화 + LoRA로 Qwen2.5-7B를 효율적으로 파인튜닝합니다.

Usage:
    python train_openframe_qlora.py --data combined_ko.jsonl --gpu 6
    python train_openframe_qlora.py --data combined_ko.jsonl --limit 1000 --epochs 1
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTTrainer, SFTConfig
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrainingConfig:
    """학습 설정"""

    # Model
    BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

    # QLoRA 4-bit quantization
    LOAD_IN_4BIT = True
    BNB_4BIT_COMPUTE_DTYPE = torch.bfloat16
    BNB_4BIT_QUANT_TYPE = "nf4"
    BNB_4BIT_USE_DOUBLE_QUANT = True

    # LoRA config
    LORA_R = 64
    LORA_ALPHA = 16
    LORA_DROPOUT = 0.1
    LORA_TARGET_MODULES = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ]

    # Training defaults
    MAX_SEQ_LENGTH = 1024
    BATCH_SIZE = 2
    GRADIENT_ACCUMULATION_STEPS = 8
    LEARNING_RATE = 2e-4
    NUM_EPOCHS = 3
    WARMUP_RATIO = 0.03
    WEIGHT_DECAY = 0.001


def load_jsonl_data(file_path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """JSONL 파일에서 학습 데이터 로드"""
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            data.append(json.loads(line.strip()))
    logger.info(f"Loaded {len(data)} examples from {file_path}")
    return data


def format_instruction(example: Dict[str, Any], language: str = "ko") -> str:
    """
    Instruction-tuning 형식으로 변환 (Qwen2.5 chat template)
    """
    instruction = example.get("instruction", "")
    input_text = example.get("input", "")
    output = example.get("output", "")

    # Build user content
    if input_text:
        user_content = f"{instruction}\n\nContext:\n{input_text}"
    else:
        user_content = instruction

    # System prompts by language
    system_prompts = {
        "ko": "당신은 OpenFrame 기술 지원 어시스턴트입니다. OpenFrame에 관한 질문에 정확하게 답변해 주세요.",
        "ja": "あなたはOpenFrame技術サポートのアシスタントです。OpenFrameに関する質問に正確に回答してください。",
        "en": "You are an OpenFrame technical support assistant. Please answer questions about OpenFrame accurately."
    }

    system_prompt = system_prompts.get(language, system_prompts["ko"])

    prompt = f"""<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{user_content}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""

    return prompt


def prepare_dataset(
    training_data: List[Dict[str, Any]],
    language: str = "ko"
) -> Dataset:
    """데이터셋 준비"""
    formatted_data = []
    for example in training_data:
        text = format_instruction(example, language)
        formatted_data.append({"text": text})

    dataset = Dataset.from_list(formatted_data)
    return dataset


def setup_model_and_tokenizer(config: TrainingConfig, gpu_ids: str = "0"):
    """모델과 토크나이저 설정"""

    logger.info(f"Loading base model: {config.BASE_MODEL} on GPU(s) {gpu_ids}")

    # BitsAndBytes config for 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.LOAD_IN_4BIT,
        bnb_4bit_compute_dtype=config.BNB_4BIT_COMPUTE_DTYPE,
        bnb_4bit_quant_type=config.BNB_4BIT_QUANT_TYPE,
        bnb_4bit_use_double_quant=config.BNB_4BIT_USE_DOUBLE_QUANT,
    )

    # Device map - use "auto" for multi-GPU
    if "," in gpu_ids:
        device_map = "auto"
    else:
        device_map = {"": 0}

    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        config.BASE_MODEL,
        quantization_config=bnb_config,
        device_map=device_map,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        use_cache=False,
        local_files_only=True,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)

    # LoRA config
    lora_config = LoraConfig(
        r=config.LORA_R,
        lora_alpha=config.LORA_ALPHA,
        lora_dropout=config.LORA_DROPOUT,
        target_modules=config.LORA_TARGET_MODULES,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        config.BASE_MODEL,
        trust_remote_code=True,
        padding_side="right",
        local_files_only=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer


def train(
    model,
    tokenizer,
    train_dataset: Dataset,
    eval_dataset: Optional[Dataset],
    output_dir: Path,
    config: TrainingConfig,
    num_epochs: int
) -> Dict[str, float]:
    """QLoRA 학습 실행"""

    logger.info(f"Starting training with {len(train_dataset)} samples for {num_epochs} epochs")

    # SFT Config
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=config.BATCH_SIZE,
        gradient_accumulation_steps=config.GRADIENT_ACCUMULATION_STEPS,
        learning_rate=config.LEARNING_RATE,
        warmup_ratio=config.WARMUP_RATIO,
        weight_decay=config.WEIGHT_DECAY,
        logging_steps=10,
        save_steps=500,
        save_total_limit=3,
        eval_strategy="steps" if eval_dataset else "no",
        eval_steps=500 if eval_dataset else None,
        bf16=True,
        fp16=False,
        optim="paged_adamw_32bit",
        lr_scheduler_type="cosine",
        report_to="none",
        max_length=config.MAX_SEQ_LENGTH,
        packing=False,
        dataset_text_field="text",
        gradient_checkpointing=False,
    )

    # SFTTrainer
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    # Train
    train_result = trainer.train()

    # Save adapter
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Metrics
    metrics = {
        "train_loss": train_result.training_loss,
        "train_runtime": train_result.metrics.get("train_runtime", 0),
        "train_samples_per_second": train_result.metrics.get("train_samples_per_second", 0),
    }

    if eval_dataset:
        eval_result = trainer.evaluate()
        metrics["eval_loss"] = eval_result.get("eval_loss", 0)

    logger.info(f"Training completed. Metrics: {metrics}")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="OpenFrame QLoRA Training")
    parser.add_argument("--data", type=str, required=True, help="Path to JSONL training data")
    parser.add_argument("--output", type=str, default="./openframe_qlora_adapter", help="Output directory for adapter")
    parser.add_argument("--gpu", type=str, default="6", help="GPU ID(s) to use, e.g., '6' or '5,6' (default: 6)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of training examples")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=2, help="Batch size")
    parser.add_argument("--language", type=str, default="ko", choices=["ko", "ja", "en"], help="Language for system prompt")
    parser.add_argument("--eval_split", type=float, default=0.1, help="Evaluation split ratio")

    args = parser.parse_args()

    # Set GPU (support multiple GPUs like "5,6")
    gpu_str = str(args.gpu)
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_str

    config = TrainingConfig()
    config.BATCH_SIZE = args.batch_size

    # Load data
    training_data = load_jsonl_data(args.data, args.limit)

    if not training_data:
        logger.error("No training data loaded. Exiting.")
        return

    # Setup model
    logger.info(f"Using GPU(s) {args.gpu}")
    model, tokenizer = setup_model_and_tokenizer(config, gpu_ids=gpu_str)

    # Prepare dataset
    dataset = prepare_dataset(training_data, args.language)

    # Split for evaluation
    eval_dataset = None
    train_dataset = dataset
    if args.eval_split > 0 and len(dataset) > 20:
        split = dataset.train_test_split(test_size=args.eval_split)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        logger.info(f"Split: {len(train_dataset)} train, {len(eval_dataset)} eval")

    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) / f"openframe_{args.language}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Output directory: {output_dir}")

    # Train
    metrics = train(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        output_dir=output_dir,
        config=config,
        num_epochs=args.epochs
    )

    # Save training info
    info = {
        "data_file": args.data,
        "language": args.language,
        "total_examples": len(training_data),
        "train_examples": len(train_dataset),
        "eval_examples": len(eval_dataset) if eval_dataset else 0,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "gpu": args.gpu,
        "metrics": metrics,
        "completed_at": datetime.now().isoformat()
    }

    with open(output_dir / "training_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    logger.info(f"Training completed! Adapter saved to: {output_dir}")
    print(f"\n{'='*60}")
    print(f"Training completed successfully!")
    print(f"Adapter saved to: {output_dir}")
    print(f"Total examples: {len(training_data)}")
    print(f"Train loss: {metrics.get('train_loss', 'N/A'):.4f}")
    if 'eval_loss' in metrics:
        print(f"Eval loss: {metrics['eval_loss']:.4f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
