#!/usr/bin/env python3
"""
Learning LLM Training Script (All-in-One)

서버에서 바로 실행 가능한 통합 학습 스크립트입니다.
Summaries 데이터에서 Q&A 데이터셋을 생성하고 QLoRA 학습을 수행합니다.

Usage:
    # 전체 파이프라인 실행 (데이터 생성 + 학습)
    python run_learning_llm_training.py --all

    # 데이터 생성만
    python run_learning_llm_training.py --generate-only

    # 학습만 (기존 데이터 사용)
    python run_learning_llm_training.py --train-only --data-path /path/to/data.jsonl

    # 드라이런 (실제 학습 없이 테스트)
    python run_learning_llm_training.py --dry-run

Requirements:
    pip install torch transformers peft bitsandbytes trl datasets accelerate

Environment:
    - GPU with 8GB+ VRAM (RTX 3090, A100, etc.)
    - CUDA 11.8+
    - Python 3.10+
"""

import os
import sys
import json
import re
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

# ============================================================
# Configuration
# ============================================================

@dataclass
class Config:
    """Training configuration"""
    # Paths
    summaries_dir: str = "/opt/kms/uploads/summaries"
    output_dir: str = "/opt/kms/models/qlora_adapters"
    data_dir: str = "/opt/kms/data/training"

    # Model
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # LoRA
    lora_r: int = 64
    lora_alpha: int = 16
    lora_dropout: float = 0.1

    # Training
    num_epochs: int = 3
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03

    # Quantization
    use_4bit: bool = True
    bnb_4bit_compute_dtype: str = "float16"
    bnb_4bit_quant_type: str = "nf4"


# ============================================================
# Logging Setup
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================
# Q&A Templates
# ============================================================

ERROR_QUESTION_TEMPLATES = [
    "에러코드 {code}의 원인은 무엇인가요?",
    "에러 {code} 해결방법을 알려주세요",
    "{name} 에러가 발생했을 때 대처방법은?",
    "{code} 에러 원인과 해결책",
    "エラーコード {code} の原因は何ですか?",
    "{code} エラーの解決方法を教えてください",
]

COMMAND_QUESTION_TEMPLATES = [
    "{cmd} 명령어 사용법은?",
    "{cmd} 명령어의 구문과 옵션을 알려주세요",
    "{cmd} 실행 방법",
    "{product}에서 {cmd} 사용하는 방법",
    "{cmd} コマンドの使い方は?",
    "{cmd} の構文とオプションを教えてください",
]

GLOSSARY_QUESTION_TEMPLATES = [
    "{term}가 무엇인가요?",
    "{term}의 의미와 기능을 설명해주세요",
    "{term} 정의",
    "{term}とは何ですか?",
    "{term}の意味と機能を説明してください",
]


# ============================================================
# Markdown Parsers
# ============================================================

def parse_error_codes_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """Parse error codes from markdown content"""
    errors = []

    # Pattern for table rows: | -XXXX | NAME | Description | Solution |
    table_pattern = r'\|\s*(-?\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'

    for match in re.finditer(table_pattern, content):
        code = match.group(1).strip()
        name = match.group(2).strip()
        description = match.group(3).strip()
        solution = match.group(4).strip() if match.group(4) else ""

        if code and name and code != "Code" and not code.startswith("-"):
            code = f"-{code}" if not code.startswith("-") else code

        if code and name and name != "Name":
            errors.append({
                "type": "error_code",
                "code": code,
                "name": name,
                "description": description,
                "solution": solution,
                "source": source_file,
            })

    # Also try section-based format
    section_pattern = r'##\s*(-?\d+)\s*[-:]\s*([^\n]+)\n([\s\S]*?)(?=\n##|\Z)'
    for match in re.finditer(section_pattern, content):
        code = match.group(1).strip()
        name = match.group(2).strip()
        body = match.group(3).strip()

        if code and name:
            errors.append({
                "type": "error_code",
                "code": f"-{code}" if not code.startswith("-") else code,
                "name": name,
                "description": body[:500],
                "solution": "",
                "source": source_file,
            })

    return errors


def parse_commands_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """Parse commands from markdown content"""
    commands = []

    # Extract product name from filename
    product = "OpenFrame"
    if "TJES" in source_file:
        product = "TJES"
    elif "HIDB" in source_file or "HiDB" in source_file:
        product = "HiDB"
    elif "TACF" in source_file:
        product = "TACF"
    elif "OSC" in source_file:
        product = "OSC"

    # Pattern for command sections
    section_pattern = r'###?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\n([\s\S]*?)(?=\n###?|\Z)'

    for match in re.finditer(section_pattern, content):
        cmd_name = match.group(1).strip()
        body = match.group(2).strip()

        # Extract syntax if present
        syntax = ""
        syntax_match = re.search(r'\*\*구문\*\*[:\s]*`([^`]+)`', body)
        if not syntax_match:
            syntax_match = re.search(r'\*\*Syntax\*\*[:\s]*`([^`]+)`', body)
        if syntax_match:
            syntax = syntax_match.group(1)

        # Extract description
        desc_match = re.search(r'\*\*설명\*\*[:\s]*([^\n*]+)', body)
        if not desc_match:
            desc_match = re.search(r'\*\*Description\*\*[:\s]*([^\n*]+)', body)
        description = desc_match.group(1).strip() if desc_match else body[:300]

        if cmd_name and len(cmd_name) > 1:
            commands.append({
                "type": "command",
                "name": cmd_name,
                "product": product,
                "syntax": syntax,
                "description": description,
                "source": source_file,
            })

    return commands


def parse_glossary_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """Parse glossary terms from markdown content"""
    terms = []

    # Pattern for term definitions
    section_pattern = r'###?\s+([A-Za-z][A-Za-z0-9_\-\s]*)\s*\n([\s\S]*?)(?=\n###?|\Z)'

    for match in re.finditer(section_pattern, content):
        term = match.group(1).strip()
        body = match.group(2).strip()

        # Extract full name if present
        full_name = ""
        full_match = re.search(r'\(([^)]+)\)', term)
        if full_match:
            full_name = full_match.group(1)
            term = re.sub(r'\s*\([^)]+\)', '', term).strip()

        if term and len(term) > 1:
            terms.append({
                "type": "glossary",
                "term": term,
                "full_name": full_name,
                "description": body[:500],
                "source": source_file,
            })

    return terms


# ============================================================
# Q&A Dataset Generator
# ============================================================

class QADatasetGenerator:
    """Generate Q&A training data from Summaries"""

    def __init__(self, summaries_dir: str):
        self.summaries_dir = Path(summaries_dir)
        self.error_codes: List[Dict] = []
        self.commands: List[Dict] = []
        self.glossary: List[Dict] = []

    def load_summaries(self) -> Tuple[int, int, int]:
        """Load all summaries from markdown files"""
        logger.info(f"Loading summaries from {self.summaries_dir}")

        # Load error codes
        error_dir = self.summaries_dir / "error_codes"
        if error_dir.exists():
            for md_file in error_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    errors = parse_error_codes_md(content, md_file.name)
                    self.error_codes.extend(errors)
                except Exception as e:
                    logger.warning(f"Failed to parse {md_file}: {e}")

        # Load commands
        cmd_dir = self.summaries_dir / "commands"
        if cmd_dir.exists():
            for md_file in cmd_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    cmds = parse_commands_md(content, md_file.name)
                    self.commands.extend(cmds)
                except Exception as e:
                    logger.warning(f"Failed to parse {md_file}: {e}")

        # Load glossary
        glossary_dir = self.summaries_dir / "glossary"
        if glossary_dir.exists():
            for md_file in glossary_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    terms = parse_glossary_md(content, md_file.name)
                    self.glossary.extend(terms)
                except Exception as e:
                    logger.warning(f"Failed to parse {md_file}: {e}")

        logger.info(f"Loaded: {len(self.error_codes)} errors, {len(self.commands)} commands, {len(self.glossary)} terms")
        return len(self.error_codes), len(self.commands), len(self.glossary)

    def generate_error_code_qa(self) -> List[Dict[str, str]]:
        """Generate Q&A pairs for error codes"""
        qa_pairs = []

        for error in self.error_codes:
            code = error.get("code", "")
            name = error.get("name", "")
            description = error.get("description", "")
            solution = error.get("solution", "")
            source = error.get("source", "")

            # Build answer
            answer_parts = [f"에러 {code} ({name})"]
            if description:
                answer_parts.append(f"\n\n원인: {description}")
            if solution:
                answer_parts.append(f"\n\n해결방법: {solution}")
            answer_parts.append(f"\n\n출처: {source}")

            answer = "".join(answer_parts)

            # Generate Q&A for each template
            for template in ERROR_QUESTION_TEMPLATES:
                try:
                    question = template.format(code=code, name=name)
                    qa_pairs.append({
                        "instruction": question,
                        "output": answer,
                        "type": "error_code",
                        "code": code,
                    })
                except KeyError:
                    continue

        return qa_pairs

    def generate_command_qa(self) -> List[Dict[str, str]]:
        """Generate Q&A pairs for commands"""
        qa_pairs = []

        for cmd in self.commands:
            name = cmd.get("name", "")
            product = cmd.get("product", "OpenFrame")
            syntax = cmd.get("syntax", "")
            description = cmd.get("description", "")
            source = cmd.get("source", "")

            # Build answer
            answer_parts = [f"{name} 명령어"]
            if syntax:
                answer_parts.append(f"\n\n구문: {syntax}")
            if description:
                answer_parts.append(f"\n\n설명: {description}")
            answer_parts.append(f"\n\n제품: {product}")
            answer_parts.append(f"\n출처: {source}")

            answer = "".join(answer_parts)

            # Generate Q&A for each template
            for template in COMMAND_QUESTION_TEMPLATES:
                try:
                    question = template.format(cmd=name, product=product)
                    qa_pairs.append({
                        "instruction": question,
                        "output": answer,
                        "type": "command",
                        "name": name,
                    })
                except KeyError:
                    continue

        return qa_pairs

    def generate_glossary_qa(self) -> List[Dict[str, str]]:
        """Generate Q&A pairs for glossary terms"""
        qa_pairs = []

        for term_data in self.glossary:
            term = term_data.get("term", "")
            full_name = term_data.get("full_name", "")
            description = term_data.get("description", "")
            source = term_data.get("source", "")

            # Build answer
            answer_parts = [term]
            if full_name:
                answer_parts[0] = f"{term} ({full_name})"
            if description:
                answer_parts.append(f"\n\n{description}")
            answer_parts.append(f"\n\n출처: {source}")

            answer = "".join(answer_parts)

            # Generate Q&A for each template
            for template in GLOSSARY_QUESTION_TEMPLATES:
                try:
                    question = template.format(term=term)
                    qa_pairs.append({
                        "instruction": question,
                        "output": answer,
                        "type": "glossary",
                        "term": term,
                    })
                except KeyError:
                    continue

        return qa_pairs

    def generate_all(self) -> List[Dict[str, str]]:
        """Generate all Q&A pairs"""
        all_qa = []

        error_qa = self.generate_error_code_qa()
        logger.info(f"Generated {len(error_qa)} error code Q&A pairs")
        all_qa.extend(error_qa)

        cmd_qa = self.generate_command_qa()
        logger.info(f"Generated {len(cmd_qa)} command Q&A pairs")
        all_qa.extend(cmd_qa)

        glossary_qa = self.generate_glossary_qa()
        logger.info(f"Generated {len(glossary_qa)} glossary Q&A pairs")
        all_qa.extend(glossary_qa)

        logger.info(f"Total Q&A pairs: {len(all_qa)}")
        return all_qa

    def save_dataset(self, output_path: str, qa_pairs: List[Dict]) -> str:
        """Save dataset in JSONL format"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for qa in qa_pairs:
                # Format for training
                training_example = {
                    "instruction": qa["instruction"],
                    "output": qa["output"],
                }
                f.write(json.dumps(training_example, ensure_ascii=False) + "\n")

        logger.info(f"Saved {len(qa_pairs)} examples to {output_path}")
        return str(output_path)


# ============================================================
# QLoRA Trainer
# ============================================================

def run_qlora_training(
    data_path: str,
    config: Config,
    dry_run: bool = False
) -> Optional[str]:
    """Run QLoRA training"""

    if dry_run:
        logger.info("[DRY RUN] Would run training with:")
        logger.info(f"  Data: {data_path}")
        logger.info(f"  Model: {config.base_model}")
        logger.info(f"  Output: {config.output_dir}")
        logger.info(f"  Epochs: {config.num_epochs}")
        logger.info(f"  LoRA R: {config.lora_r}")
        return None

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
        from datasets import load_dataset
    except ImportError as e:
        logger.error(f"Missing required package: {e}")
        logger.error("Install with: pip install torch transformers peft bitsandbytes trl datasets accelerate")
        return None

    logger.info("=" * 60)
    logger.info("Starting QLoRA Training")
    logger.info("=" * 60)

    # Check GPU
    if not torch.cuda.is_available():
        logger.error("CUDA is not available. QLoRA requires GPU.")
        return None

    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
    logger.info(f"GPU: {gpu_name} ({gpu_memory:.1f} GB)")

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(config.output_dir) / f"summaries_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load tokenizer
    logger.info(f"Loading tokenizer: {config.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.use_4bit,
        bnb_4bit_compute_dtype=getattr(torch, config.bnb_4bit_compute_dtype),
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=True,
    )

    # Load model
    logger.info(f"Loading model: {config.base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    model = get_peft_model(model, lora_config)
    trainable_params, all_params = model.get_nb_trainable_parameters()
    logger.info(f"Trainable params: {trainable_params:,} / {all_params:,} ({100 * trainable_params / all_params:.2f}%)")

    # Load dataset
    logger.info(f"Loading dataset: {data_path}")
    dataset = load_dataset("json", data_files=data_path, split="train")
    logger.info(f"Dataset size: {len(dataset)}")

    # Format function
    def format_instruction(example):
        return f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        logging_steps=10,
        save_strategy="epoch",
        fp16=True,
        optim="paged_adamw_8bit",
        report_to="none",
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        tokenizer=tokenizer,
        args=training_args,
        formatting_func=format_instruction,
        max_seq_length=config.max_seq_length,
    )

    # Train
    logger.info("Starting training...")
    trainer.train()

    # Save
    logger.info(f"Saving adapter to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save config
    config_path = output_dir / "training_config.json"
    with open(config_path, "w") as f:
        json.dump({
            "base_model": config.base_model,
            "lora_r": config.lora_r,
            "lora_alpha": config.lora_alpha,
            "num_epochs": config.num_epochs,
            "data_path": data_path,
            "timestamp": timestamp,
        }, f, indent=2)

    logger.info("=" * 60)
    logger.info("Training Complete!")
    logger.info(f"Adapter saved to: {output_dir}")
    logger.info("=" * 60)

    return str(output_dir)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Learning LLM Training Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline (generate data + train)
  python run_learning_llm_training.py --all

  # Generate data only
  python run_learning_llm_training.py --generate-only

  # Train only (with existing data)
  python run_learning_llm_training.py --train-only --data-path /path/to/data.jsonl

  # Dry run (test without training)
  python run_learning_llm_training.py --dry-run
        """
    )

    # Actions
    parser.add_argument("--all", action="store_true", help="Run full pipeline (generate + train)")
    parser.add_argument("--generate-only", action="store_true", help="Only generate Q&A dataset")
    parser.add_argument("--train-only", action="store_true", help="Only run training")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without actual training")

    # Paths
    parser.add_argument("--summaries-dir", type=str, default="/opt/kms/uploads/summaries",
                        help="Path to summaries directory")
    parser.add_argument("--data-path", type=str, help="Path to existing training data (for --train-only)")
    parser.add_argument("--output-dir", type=str, default="/opt/kms/models/qlora_adapters",
                        help="Output directory for trained adapter")
    parser.add_argument("--data-dir", type=str, default="/opt/kms/data/training",
                        help="Directory to save generated training data")

    # Model
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-7B-Instruct",
                        help="Base model to fine-tune")

    # Training params
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size")
    parser.add_argument("--lora-r", type=int, default=64, help="LoRA rank")

    args = parser.parse_args()

    # Default to --all if no action specified
    if not (args.all or args.generate_only or args.train_only or args.dry_run):
        args.all = True

    # Config
    config = Config(
        summaries_dir=args.summaries_dir,
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        base_model=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        lora_r=args.lora_r,
    )

    data_path = args.data_path

    # Step 1: Generate Q&A dataset
    if args.all or args.generate_only or args.dry_run:
        logger.info("=" * 60)
        logger.info("Step 1: Generating Q&A Dataset")
        logger.info("=" * 60)

        generator = QADatasetGenerator(config.summaries_dir)
        num_errors, num_cmds, num_terms = generator.load_summaries()

        if num_errors + num_cmds + num_terms == 0:
            logger.error(f"No summaries found in {config.summaries_dir}")
            logger.error("Make sure the summaries directory exists and contains markdown files.")
            sys.exit(1)

        qa_pairs = generator.generate_all()

        if not qa_pairs:
            logger.error("No Q&A pairs generated")
            sys.exit(1)

        # Save dataset
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_path = f"{config.data_dir}/summaries_qa_{timestamp}.jsonl"
        generator.save_dataset(data_path, qa_pairs)

        # Print statistics
        logger.info("\nDataset Statistics:")
        logger.info(f"  Error Code Q&A: {len([q for q in qa_pairs if q.get('type') == 'error_code'])}")
        logger.info(f"  Command Q&A: {len([q for q in qa_pairs if q.get('type') == 'command'])}")
        logger.info(f"  Glossary Q&A: {len([q for q in qa_pairs if q.get('type') == 'glossary'])}")
        logger.info(f"  Total: {len(qa_pairs)}")

        if args.generate_only:
            logger.info(f"\nDataset saved to: {data_path}")
            logger.info("Run with --train-only --data-path <path> to train")
            return

    # Step 2: Train
    if args.all or args.train_only or args.dry_run:
        if not data_path:
            logger.error("No data path specified. Use --data-path or run with --all")
            sys.exit(1)

        if not Path(data_path).exists():
            logger.error(f"Data file not found: {data_path}")
            sys.exit(1)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 2: QLoRA Training")
        logger.info("=" * 60)

        adapter_path = run_qlora_training(
            data_path=data_path,
            config=config,
            dry_run=args.dry_run,
        )

        if adapter_path:
            logger.info(f"\nTraining complete!")
            logger.info(f"Adapter saved to: {adapter_path}")
            logger.info("\nTo use the adapter, update your .env:")
            logger.info(f"  LEARNING_LLM_ADAPTER_PATH={adapter_path}")


if __name__ == "__main__":
    main()
