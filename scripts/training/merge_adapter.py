#!/usr/bin/env python3
"""
PEFT Adapter Merge Utility

LoRA/PEFT adapter를 base model에 병합하여 독립적인 모델을 생성합니다.
CPT→SFT, SFT→DPO 단계 전환 시 사용됩니다.

Usage:
    # CPT adapter 병합
    python scripts/training/merge_adapter.py \
        --base-model Qwen/Qwen2.5-7B-Instruct \
        --adapter models/cpt_openframe_v1 \
        --output models/qwen2.5-7b-openframe-cpt

    # 병합 후 생성 테스트
    python scripts/training/merge_adapter.py \
        --base-model Qwen/Qwen2.5-7B-Instruct \
        --adapter models/cpt_openframe_v1 \
        --output models/qwen2.5-7b-openframe-cpt \
        --verify

Requirements:
    pip install transformers peft torch accelerate
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def merge_adapter(
    base_model_path: str,
    adapter_path: str,
    output_dir: str,
    torch_dtype: str = "float16",
    device_map: str = "auto",
) -> Path:
    """
    PEFT adapter를 base model에 병합.

    - LoRA layers: W_merged = W_base + (alpha/r) * BA
    - modules_to_save (embed_tokens, lm_head): 직접 교체
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    dtype = getattr(torch, torch_dtype)

    logger.info(f"Base model 로드: {base_model_path}")
    model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=dtype,
        device_map=device_map,
        trust_remote_code=True,
    )

    logger.info(f"Adapter 로드: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)

    logger.info("Adapter 병합 (merge_and_unload)...")
    model = model.merge_and_unload()

    logger.info(f"병합 모델 저장: {output}")
    model.save_pretrained(output)

    # 토크나이저 복사
    tokenizer = AutoTokenizer.from_pretrained(
        base_model_path, trust_remote_code=True
    )
    tokenizer.save_pretrained(output)

    # 메타데이터 저장
    metadata = {
        "base_model": base_model_path,
        "adapter_path": adapter_path,
        "torch_dtype": torch_dtype,
        "merged_at": datetime.now().isoformat(),
    }
    (output / "merge_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("병합 완료!")
    return output


def verify_merge(model_path: str, test_prompt: str = "OpenFrameとは") -> str:
    """병합 모델로 간단한 생성 테스트"""
    logger.info(f"생성 테스트: '{test_prompt}'")

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    inputs = tokenizer(test_prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
        )

    generated = tokenizer.decode(outputs[0], skip_special_tokens=True)
    logger.info(f"생성 결과:\n{generated}")
    return generated


def main():
    parser = argparse.ArgumentParser(
        description="PEFT Adapter를 Base Model에 병합",
    )
    parser.add_argument(
        "--base-model",
        required=True,
        help="Base model 경로 또는 HuggingFace ID",
    )
    parser.add_argument(
        "--adapter",
        required=True,
        help="PEFT adapter 디렉토리 경로",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="병합 모델 출력 디렉토리",
    )
    parser.add_argument(
        "--dtype",
        default="float16",
        choices=["float16", "bfloat16", "float32"],
        help="저장 dtype",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="병합 후 생성 테스트 실행",
    )
    parser.add_argument(
        "--verify-prompt",
        default="OpenFrameとは",
        help="생성 테스트 프롬프트",
    )

    args = parser.parse_args()

    # Adapter 경로 검증
    adapter_path = Path(args.adapter)
    if not adapter_path.exists():
        logger.error(f"Adapter 경로 없음: {adapter_path}")
        sys.exit(1)

    # 필수 파일 확인
    adapter_config = adapter_path / "adapter_config.json"
    if not adapter_config.exists():
        logger.error(f"adapter_config.json 없음: {adapter_path}")
        sys.exit(1)

    output = merge_adapter(
        base_model_path=args.base_model,
        adapter_path=str(adapter_path),
        output_dir=args.output,
        torch_dtype=args.dtype,
    )

    if args.verify:
        verify_merge(str(output), args.verify_prompt)


if __name__ == "__main__":
    main()
