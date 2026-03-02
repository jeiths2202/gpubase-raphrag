#!/usr/bin/env python3
"""
Multi-LoRA v4 Training Script
QLoRA fine-tuning for 24 TmaxSoft products on cleaned dataset

Usage:
    # Train all products
    python train_multi_lora_v4.py --all

    # Train specific products
    python train_multi_lora_v4.py --products openframe_base_v2,tmax_v2

    # Train Priority 1 products only
    python train_multi_lora_v4.py --priority1

Requirements:
    pip install transformers peft datasets accelerate bitsandbytes trl
"""

import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Qwen2.5 Special Token IDs
QWEN_ENDOFTEXT_ID = 151643   # <|endoftext|> - 패딩용

# Configuration
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
MAX_SEQ_LENGTH = 2048
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05

# Priority 1 products (>60% error rate in original data)
PRIORITY1_PRODUCTS = [
    'tmax_v2', 'tibero7_v2', 'openframe_batch_v2',
    'protrieve_v2', 'ofpli_v2', 'prosort_v2', 'ofcobol_v2'
]


def load_dataset(product_dir: Path) -> Optional[Dataset]:
    """Load training data for a product"""
    train_path = product_dir / 'train.json'
    if not train_path.exists():
        logger.warning(f"No train.json found in {product_dir}")
        return None

    with open(train_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        logger.warning(f"Empty dataset for {product_dir.name}")
        return None

    # Convert to HuggingFace Dataset
    return Dataset.from_list(data)


def setup_model_and_tokenizer(base_model: str):
    """Setup quantized model and tokenizer for QLoRA training"""

    # BitsAndBytes config for 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    # pad_token을 <|endoftext|>로 설정 (eos_token인 <|im_end|>와 분리)
    tokenizer.pad_token = tokenizer.decode([QWEN_ENDOFTEXT_ID])
    tokenizer.pad_token_id = QWEN_ENDOFTEXT_ID

    # Load model with quantization
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    return model, tokenizer


def setup_lora(model, lora_r: int = LORA_R, lora_alpha: int = LORA_ALPHA):
    """Configure LoRA adapters"""

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"]
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model


def train_product(
    product_name: str,
    dataset: Dataset,
    model,
    tokenizer,
    output_dir: Path,
    num_epochs: int = 2,
    batch_size: int = 4,
    learning_rate: float = 1e-4,
):
    """Train LoRA adapter for a single product"""

    product_output = output_dir / product_name
    product_output.mkdir(parents=True, exist_ok=True)

    # Training arguments (optimized to prevent overfitting)
    training_args = TrainingArguments(
        output_dir=str(product_output),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_steps=100,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        fp16=True,
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        report_to="none",  # Disable wandb/tensorboard
        gradient_checkpointing=True,
        max_grad_norm=0.3,
    )

    # Setup trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
    )

    # Train
    logger.info(f"Starting training for {product_name} with {len(dataset)} examples...")
    trainer.train()

    # Save adapter
    trainer.model.save_pretrained(product_output)
    tokenizer.save_pretrained(product_output)

    # Save training info
    info = {
        "product": product_name,
        "base_model": BASE_MODEL,
        "num_examples": len(dataset),
        "num_epochs": num_epochs,
        "learning_rate": learning_rate,
        "lora_r": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "trained_at": datetime.now().isoformat(),
    }
    with open(product_output / "training_info.json", 'w') as f:
        json.dump(info, f, indent=2)

    logger.info(f"Saved adapter to {product_output}")
    return product_output


def main():
    parser = argparse.ArgumentParser(description='Train Multi-LoRA v4 adapters')
    parser.add_argument('--input', '-i', type=Path,
                        default=Path('/raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v4_cleaned'),
                        help='Input directory with cleaned datasets')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('/raid/users/ofuser/qlora/multi_lora_v4'),
                        help='Output directory for trained adapters')
    parser.add_argument('--products', '-p', type=str, default=None,
                        help='Comma-separated product names to train')
    parser.add_argument('--all', action='store_true',
                        help='Train all available products')
    parser.add_argument('--priority1', action='store_true',
                        help='Train Priority 1 products only')
    parser.add_argument('--epochs', '-e', type=int, default=2,
                        help='Number of training epochs')
    parser.add_argument('--batch-size', '-b', type=int, default=4,
                        help='Batch size per device')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='Learning rate')
    parser.add_argument('--base-model', type=str, default=BASE_MODEL,
                        help='Base model for fine-tuning')
    parser.add_argument('--gpu', '-g', type=str, default=None,
                        help='GPU device(s) to use (e.g., "0,1")')

    args = parser.parse_args()

    # Set GPU
    if args.gpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    # Determine products to train
    if args.all:
        products = [d.name for d in args.input.iterdir() if d.is_dir()]
    elif args.priority1:
        products = PRIORITY1_PRODUCTS
    elif args.products:
        products = [p.strip() for p in args.products.split(',')]
    else:
        parser.error("Specify --all, --priority1, or --products")

    logger.info(f"Will train {len(products)} products: {products}")
    logger.info(f"Base model: {args.base_model}")
    logger.info(f"Output: {args.output}")

    # Setup model once (will be reused for all products)
    logger.info("Loading base model...")
    model, tokenizer = setup_model_and_tokenizer(args.base_model)

    # Train each product
    results = []
    for product in products:
        product_dir = args.input / product

        # Load dataset
        dataset = load_dataset(product_dir)
        if dataset is None or len(dataset) == 0:
            logger.warning(f"Skipping {product}: no valid data")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"Training {product} ({len(dataset)} examples)")
        logger.info(f"{'='*60}")

        try:
            # Setup fresh LoRA for this product
            lora_model = setup_lora(model)

            # Train
            output_path = train_product(
                product_name=product,
                dataset=dataset,
                model=lora_model,
                tokenizer=tokenizer,
                output_dir=args.output,
                num_epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.lr,
            )

            results.append({
                "product": product,
                "status": "success",
                "examples": len(dataset),
                "output": str(output_path)
            })

        except Exception as e:
            logger.error(f"Failed to train {product}: {e}")
            results.append({
                "product": product,
                "status": "failed",
                "error": str(e)
            })

    # Summary
    print("\n" + "="*60)
    print("TRAINING SUMMARY")
    print("="*60)

    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]

    print(f"Successful: {len(successful)}/{len(products)}")
    for r in successful:
        print(f"  [OK] {r['product']}: {r['examples']} examples")

    if failed:
        print(f"\nFailed: {len(failed)}/{len(products)}")
        for r in failed:
            print(f"  [FAIL] {r['product']}: {r['error']}")

    # Save results
    results_path = args.output / "training_results.json"
    with open(results_path, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "base_model": args.base_model,
            "total_products": len(products),
            "successful": len(successful),
            "failed": len(failed),
            "results": results
        }, f, indent=2)

    print(f"\nResults saved to: {results_path}")


if __name__ == '__main__':
    main()
