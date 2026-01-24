#!/usr/bin/env python3
"""
QLoRA Training Script for Smarter RAG System

4-bit 양자화 + LoRA로 Qwen2.5-7B를 효율적으로 파인튜닝합니다.
VRAM ~8GB로 단일 A100에서 학습 가능.

Usage:
    python qlora_trainer.py --batch_id batch_20240125_001
    python qlora_trainer.py --auto  # 자동으로 배치 생성 및 학습
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
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

# ============================================
# Configuration
# ============================================

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

    # Training
    MAX_SEQ_LENGTH = 2048
    BATCH_SIZE = 4
    GRADIENT_ACCUMULATION_STEPS = 4
    LEARNING_RATE = 2e-4
    NUM_EPOCHS = 3
    WARMUP_RATIO = 0.03
    WEIGHT_DECAY = 0.001

    # Paths
    OUTPUT_DIR = Path("/opt/kms/models/qlora_adapters")
    DATA_DIR = Path("/opt/kms/data/training")

    # GPU
    DEVICE_MAP = "auto"


# ============================================
# Data Preparation
# ============================================

def format_instruction(example: Dict[str, Any]) -> str:
    """
    Instruction-tuning 형식으로 변환

    Qwen2.5 chat template:
    <|im_start|>system
    You are a helpful assistant.<|im_end|>
    <|im_start|>user
    {instruction}<|im_end|>
    <|im_start|>assistant
    {output}<|im_end|>
    """
    instruction = example.get("instruction", "")
    input_text = example.get("input", "")
    output = example.get("output", "")

    # Build prompt
    if input_text:
        user_content = f"{instruction}\n\nContext:\n{input_text}"
    else:
        user_content = instruction

    prompt = f"""<|im_start|>system
You are a helpful KMS assistant that provides accurate answers based on verified knowledge.<|im_end|>
<|im_start|>user
{user_content}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""

    return prompt


def prepare_dataset(
    training_data: List[Dict[str, Any]],
    tokenizer,
    max_length: int = 2048
) -> Dataset:
    """데이터셋 준비"""

    def tokenize_function(examples):
        texts = [format_instruction(ex) for ex in examples]

        tokenized = tokenizer(
            texts,
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt"
        )

        # Labels = input_ids (for causal LM)
        tokenized["labels"] = tokenized["input_ids"].clone()

        return tokenized

    # Convert to HuggingFace Dataset
    dataset = Dataset.from_list(training_data)

    # Tokenize
    tokenized_dataset = dataset.map(
        lambda x: tokenize_function([x]),
        remove_columns=dataset.column_names,
        desc="Tokenizing"
    )

    return tokenized_dataset


# ============================================
# Model Setup
# ============================================

def setup_model_and_tokenizer(config: TrainingConfig):
    """모델과 토크나이저 설정"""

    logger.info(f"Loading base model: {config.BASE_MODEL}")

    # BitsAndBytes config for 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.LOAD_IN_4BIT,
        bnb_4bit_compute_dtype=config.BNB_4BIT_COMPUTE_DTYPE,
        bnb_4bit_quant_type=config.BNB_4BIT_QUANT_TYPE,
        bnb_4bit_use_double_quant=config.BNB_4BIT_USE_DOUBLE_QUANT,
    )

    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        config.BASE_MODEL,
        quantization_config=bnb_config,
        device_map=config.DEVICE_MAP,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

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
        padding_side="right"
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer


# ============================================
# Training
# ============================================

def train(
    model,
    tokenizer,
    train_dataset: Dataset,
    eval_dataset: Optional[Dataset],
    output_dir: Path,
    config: TrainingConfig
) -> Dict[str, float]:
    """QLoRA 학습 실행"""

    logger.info(f"Starting training with {len(train_dataset)} samples")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=config.NUM_EPOCHS,
        per_device_train_batch_size=config.BATCH_SIZE,
        gradient_accumulation_steps=config.GRADIENT_ACCUMULATION_STEPS,
        learning_rate=config.LEARNING_RATE,
        warmup_ratio=config.WARMUP_RATIO,
        weight_decay=config.WEIGHT_DECAY,
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        eval_strategy="steps" if eval_dataset else "no",
        eval_steps=100 if eval_dataset else None,
        bf16=True,
        gradient_checkpointing=True,
        optim="paged_adamw_32bit",
        lr_scheduler_type="cosine",
        report_to="none",
        remove_unused_columns=False,
    )

    # Data collator
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        return_tensors="pt"
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
    )

    # Train
    train_result = trainer.train()

    # Save adapter
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Get metrics
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


# ============================================
# Database Integration
# ============================================

async def fetch_training_data_from_db(
    batch_id: Optional[str] = None,
    min_feedback_score: float = 0.8,
    min_thumbs_up: int = 1,
    limit: int = 1000
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    PostgreSQL에서 학습 데이터 가져오기

    Returns:
        (training_data, unlearn_data, batch_id)
    """
    import asyncpg
    from dotenv import load_dotenv

    load_dotenv("/opt/kms/.env")

    dsn = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

    conn = await asyncpg.connect(dsn)

    try:
        # Generate batch_id if not provided
        if not batch_id:
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Fetch training data (active, not trained, high score)
        training_rows = await conn.fetch("""
            SELECT id, question, answer, category, language, feedback_score, thumbs_up_count
            FROM verified_knowledge
            WHERE status = 'active'
              AND is_trained = FALSE
              AND feedback_score >= $1
              AND thumbs_up_count >= $2
            ORDER BY feedback_score DESC, thumbs_up_count DESC
            LIMIT $3
        """, min_feedback_score, min_thumbs_up, limit)

        training_data = [
            {
                "id": str(row["id"]),
                "instruction": row["question"],
                "input": "",
                "output": row["answer"],
                "metadata": {
                    "category": row["category"],
                    "language": row["language"],
                    "feedback_score": float(row["feedback_score"]),
                }
            }
            for row in training_rows
        ]

        # Fetch unlearn data (marked for removal)
        unlearn_rows = await conn.fetch("""
            SELECT id, question, answer, training_batch_id
            FROM verified_knowledge
            WHERE status = 'unlearn_required'
              AND is_trained = TRUE
              AND unlearn_completed_at IS NULL
            LIMIT $1
        """, limit)

        unlearn_data = [
            {
                "id": str(row["id"]),
                "instruction": row["question"],
                "output": row["answer"],
                "training_batch_id": row["training_batch_id"],
            }
            for row in unlearn_rows
        ]

        # Create training batch record
        await conn.execute("""
            INSERT INTO training_batches (
                batch_id, total_samples, unlearn_samples,
                min_feedback_score, min_thumbs_up, status, scheduled_at
            ) VALUES ($1, $2, $3, $4, $5, 'collecting', NOW())
            ON CONFLICT (batch_id) DO UPDATE SET
                total_samples = $2,
                unlearn_samples = $3,
                status = 'collecting'
        """, batch_id, len(training_data), len(unlearn_data),
            min_feedback_score, min_thumbs_up)

        logger.info(f"Fetched {len(training_data)} training samples, {len(unlearn_data)} unlearn samples")

        return training_data, unlearn_data, batch_id

    finally:
        await conn.close()


async def update_training_status(
    batch_id: str,
    status: str,
    trained_ids: Optional[List[str]] = None,
    unlearned_ids: Optional[List[str]] = None,
    adapter_name: Optional[str] = None,
    metrics: Optional[Dict[str, float]] = None,
    error_message: Optional[str] = None
):
    """학습 상태 업데이트"""
    import asyncpg
    from dotenv import load_dotenv

    load_dotenv("/opt/kms/.env")

    dsn = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

    conn = await asyncpg.connect(dsn)

    try:
        # Update batch status
        if status == "training":
            await conn.execute("""
                UPDATE training_batches SET
                    status = 'training',
                    started_at = NOW()
                WHERE batch_id = $1
            """, batch_id)

        elif status == "completed":
            await conn.execute("""
                UPDATE training_batches SET
                    status = 'completed',
                    completed_at = NOW(),
                    trained_samples = $2,
                    unlearned_samples = $3,
                    adapter_name = $4,
                    eval_loss = $5
                WHERE batch_id = $1
            """, batch_id,
                len(trained_ids) if trained_ids else 0,
                len(unlearned_ids) if unlearned_ids else 0,
                adapter_name,
                metrics.get("eval_loss") if metrics else None)

            # Mark trained samples
            if trained_ids:
                # Get next training version
                version = await conn.fetchval("""
                    SELECT COALESCE(MAX(training_version), 0) + 1
                    FROM verified_knowledge
                """)

                await conn.execute("""
                    UPDATE verified_knowledge SET
                        is_trained = TRUE,
                        trained_at = NOW(),
                        training_batch_id = $1,
                        training_version = $2
                    WHERE id = ANY($3::uuid[])
                """, batch_id, version, trained_ids)

            # Mark unlearned samples
            if unlearned_ids:
                await conn.execute("""
                    UPDATE verified_knowledge SET
                        status = 'deprecated',
                        unlearn_completed_at = NOW(),
                        unlearn_batch_id = $1
                    WHERE id = ANY($2::uuid[])
                """, batch_id, unlearned_ids)

        elif status == "failed":
            await conn.execute("""
                UPDATE training_batches SET
                    status = 'failed',
                    completed_at = NOW(),
                    error_message = $2
                WHERE batch_id = $1
            """, batch_id, error_message)

        logger.info(f"Updated batch {batch_id} status to {status}")

    finally:
        await conn.close()


# ============================================
# Main
# ============================================

async def main_async(args):
    """비동기 메인 함수"""

    config = TrainingConfig()

    # Ensure directories exist
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch data from database
    training_data, unlearn_data, batch_id = await fetch_training_data_from_db(
        batch_id=args.batch_id,
        min_feedback_score=args.min_score,
        min_thumbs_up=args.min_thumbs_up,
        limit=args.limit
    )

    if not training_data:
        logger.info("No training data available. Exiting.")
        return

    # Save training data for reference
    data_file = config.DATA_DIR / f"{batch_id}.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump({
            "batch_id": batch_id,
            "training_data": training_data,
            "unlearn_data": unlearn_data,
            "created_at": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved training data to {data_file}")

    try:
        # Update status to training
        await update_training_status(batch_id, "training")

        # Setup model
        model, tokenizer = setup_model_and_tokenizer(config)

        # Prepare dataset
        train_dataset = prepare_dataset(training_data, tokenizer, config.MAX_SEQ_LENGTH)

        # Split for evaluation (10%)
        eval_dataset = None
        if len(train_dataset) > 20:
            split = train_dataset.train_test_split(test_size=0.1)
            train_dataset = split["train"]
            eval_dataset = split["test"]

        # Output directory for this batch
        adapter_name = f"qlora_{batch_id}"
        output_dir = config.OUTPUT_DIR / adapter_name

        # Train
        metrics = train(model, tokenizer, train_dataset, eval_dataset, output_dir, config)

        # Update status to completed
        trained_ids = [item["id"] for item in training_data]
        unlearned_ids = [item["id"] for item in unlearn_data]

        await update_training_status(
            batch_id=batch_id,
            status="completed",
            trained_ids=trained_ids,
            unlearned_ids=unlearned_ids,
            adapter_name=adapter_name,
            metrics=metrics
        )

        logger.info(f"Training completed successfully! Adapter saved to: {output_dir}")

    except Exception as e:
        logger.error(f"Training failed: {e}")
        await update_training_status(batch_id, "failed", error_message=str(e))
        raise


def main():
    parser = argparse.ArgumentParser(description="QLoRA Training for Smarter RAG")
    parser.add_argument("--batch_id", type=str, help="Training batch ID")
    parser.add_argument("--auto", action="store_true", help="Auto-generate batch ID")
    parser.add_argument("--min_score", type=float, default=0.8, help="Minimum feedback score")
    parser.add_argument("--min_thumbs_up", type=int, default=1, help="Minimum thumbs up count")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum samples")

    args = parser.parse_args()

    if not args.batch_id and not args.auto:
        parser.error("Either --batch_id or --auto must be specified")

    import asyncio
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
