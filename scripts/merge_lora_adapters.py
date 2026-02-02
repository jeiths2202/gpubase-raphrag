#!/usr/bin/env python3
"""
QLoRA 어댑터를 베이스 모델과 병합하여 독립 모델 생성
TensorRT-LLM 최적화 준비를 위한 스크립트

Usage:
    python merge_lora_adapters.py --adapter tibero7 --output /raid/users/ofuser/qlora/merged_models
    python merge_lora_adapters.py --all --output /raid/users/ofuser/qlora/merged_models
"""

import os
import sys
import argparse
import torch
from pathlib import Path

# 환경 설정
os.environ["HF_HUB_OFFLINE"] = "1"

# 어댑터 설정
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ADAPTERS_BASE = "/raid/users/ofuser/qlora/outputs"

ADAPTERS = {
    "openframe_mvs": f"{ADAPTERS_BASE}/openframe_qlora_adapter/openframe_ko_20260130_150120",
    "msp_openframe": f"{ADAPTERS_BASE}/qlora_adapters/msp_openframe/openframe_ko_20260131_131057",
    "vos3_openframe": f"{ADAPTERS_BASE}/qlora_adapters/vos3_openframe/openframe_ko_20260131_173439",
    "xsp_openframe": f"{ADAPTERS_BASE}/qlora_adapters/xsp_openframe/openframe_ko_20260201_092321",
    "tibero7": f"{ADAPTERS_BASE}/qlora_adapters/tibero7/openframe_ko_20260131_184925",
    "tmax": f"{ADAPTERS_BASE}/qlora_adapters/tmax/openframe_ko_20260201_135130",
    "ofcobol": f"{ADAPTERS_BASE}/qlora_adapters/ofcobol/openframe_ko_20260201_085854",
    "ofasm": f"{ADAPTERS_BASE}/qlora_adapters/ofasm/openframe_ko_20260201_030623",
}


def merge_adapter(adapter_name: str, output_dir: str, gpu_id: int = 5):
    """단일 어댑터를 베이스 모델과 병합"""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    if adapter_name not in ADAPTERS:
        print(f"❌ Unknown adapter: {adapter_name}")
        print(f"Available: {list(ADAPTERS.keys())}")
        return False

    adapter_path = ADAPTERS[adapter_name]
    output_path = Path(output_dir) / f"qwen2.5-7b-{adapter_name}"

    if not os.path.exists(f"{adapter_path}/adapter_model.safetensors"):
        print(f"❌ Adapter not found: {adapter_path}")
        return False

    if output_path.exists():
        print(f"⚠️  Output already exists: {output_path}")
        response = input("Overwrite? [y/N]: ")
        if response.lower() != 'y':
            return False

    print(f"\n{'='*60}")
    print(f"Merging: {adapter_name}")
    print(f"{'='*60}")
    print(f"Base Model: {BASE_MODEL}")
    print(f"Adapter: {adapter_path}")
    print(f"Output: {output_path}")
    print(f"GPU: {gpu_id}")

    # GPU 설정
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    device = f"cuda:0"

    try:
        # 1. 베이스 모델 로드 (float16으로 로드)
        print("\n1. Loading base model...")
        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )

        tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

        # 2. LoRA 어댑터 로드
        print("2. Loading LoRA adapter...")
        model = PeftModel.from_pretrained(base_model, adapter_path)

        # 3. 어댑터 병합
        print("3. Merging adapter into base model...")
        merged_model = model.merge_and_unload()

        # 4. 저장
        print(f"4. Saving merged model to {output_path}...")
        output_path.mkdir(parents=True, exist_ok=True)

        merged_model.save_pretrained(
            output_path,
            safe_serialization=True,
            max_shard_size="5GB"
        )
        tokenizer.save_pretrained(output_path)

        # 5. 모델 설정 복사
        print("5. Copying model configuration...")

        # 메모리 정리
        del merged_model
        del model
        del base_model
        torch.cuda.empty_cache()

        print(f"\n✅ Successfully merged: {adapter_name}")
        print(f"   Output: {output_path}")

        # 출력 크기 확인
        total_size = sum(f.stat().st_size for f in output_path.rglob('*') if f.is_file())
        print(f"   Size: {total_size / (1024**3):.2f} GB")

        return True

    except Exception as e:
        print(f"\n❌ Error merging {adapter_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Merge QLoRA adapters with base model")
    parser.add_argument("--adapter", type=str, help="Adapter name to merge")
    parser.add_argument("--all", action="store_true", help="Merge all adapters")
    parser.add_argument("--output", type=str, default="/raid/users/ofuser/qlora/merged_models",
                        help="Output directory")
    parser.add_argument("--gpu", type=int, default=5, help="GPU ID to use")
    parser.add_argument("--list", action="store_true", help="List available adapters")

    args = parser.parse_args()

    if args.list:
        print("Available adapters:")
        for name, path in ADAPTERS.items():
            exists = "✅" if os.path.exists(f"{path}/adapter_model.safetensors") else "❌"
            print(f"  {exists} {name}: {path}")
        return

    if not args.adapter and not args.all:
        parser.print_help()
        return

    # 출력 디렉토리 생성
    os.makedirs(args.output, exist_ok=True)

    if args.all:
        # 모든 어댑터 병합
        print(f"Merging all {len(ADAPTERS)} adapters...")
        results = {}
        for name in ADAPTERS.keys():
            success = merge_adapter(name, args.output, args.gpu)
            results[name] = "✅" if success else "❌"

        print(f"\n{'='*60}")
        print("Summary:")
        print(f"{'='*60}")
        for name, status in results.items():
            print(f"  {status} {name}")
    else:
        # 단일 어댑터 병합
        merge_adapter(args.adapter, args.output, args.gpu)


if __name__ == "__main__":
    main()
