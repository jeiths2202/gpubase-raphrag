#!/usr/bin/env python3
"""
8개 제품 LoRA 어댑터를 vLLM으로 서빙하는 스크립트
GPU 5 사용, 포트 12810
"""

import os
import subprocess
import sys

# GPU 설정
os.environ["CUDA_VISIBLE_DEVICES"] = "5"

# 기본 설정
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
PORT = 12810
MAX_LORAS = 8
MAX_LORA_RANK = 64

# 어댑터 경로 (절대 경로) - /raid 디스크 사용
BASE_PATH = "/raid/users/ofuser/qlora/outputs"

# 8개 제품 어댑터 정의
LORA_ADAPTERS = {
    # OpenFrame MVS (한국어)
    "openframe_mvs": f"{BASE_PATH}/openframe_qlora_adapter/openframe_ko_20260130_150120",
    # 7개 제품 어댑터
    "msp_openframe": f"{BASE_PATH}/qlora_adapters/msp_openframe/openframe_ko_20260131_131057",
    "vos3_openframe": f"{BASE_PATH}/qlora_adapters/vos3_openframe/openframe_ko_20260131_173439",
    "xsp_openframe": f"{BASE_PATH}/qlora_adapters/xsp_openframe/openframe_ko_20260201_092321",
    "tibero7": f"{BASE_PATH}/qlora_adapters/tibero7/openframe_ko_20260131_184925",
    "tmax": f"{BASE_PATH}/qlora_adapters/tmax/openframe_ko_20260201_135130",
    "ofcobol": f"{BASE_PATH}/qlora_adapters/ofcobol/openframe_ko_20260201_085854",
    "ofasm": f"{BASE_PATH}/qlora_adapters/ofasm/openframe_ko_20260201_030623",
}

def check_adapters():
    """어댑터 존재 여부 확인"""
    print("=" * 60)
    print("어댑터 경로 확인")
    print("=" * 60)

    valid_adapters = {}
    for name, path in LORA_ADAPTERS.items():
        adapter_file = os.path.join(path, "adapter_model.safetensors")
        if os.path.exists(adapter_file):
            size_mb = os.path.getsize(adapter_file) / (1024 * 1024)
            print(f"✅ {name}: {path} ({size_mb:.1f} MB)")
            valid_adapters[name] = path
        else:
            print(f"❌ {name}: {path} (없음)")

    print(f"\n유효한 어댑터: {len(valid_adapters)}/8")
    return valid_adapters

def build_lora_modules_arg(adapters: dict) -> str:
    """vLLM --lora-modules 인자 생성"""
    # 형식: name=path,name=path,...
    modules = [f"{name}={path}" for name, path in adapters.items()]
    return " ".join(modules)

def start_vllm_server(adapters: dict):
    """vLLM 서버 시작"""
    print("\n" + "=" * 60)
    print("vLLM 서버 시작")
    print("=" * 60)

    # lora-modules 인자 생성
    lora_modules_args = []
    for name, path in adapters.items():
        lora_modules_args.extend(["--lora-modules", f"{name}={path}"])

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", BASE_MODEL,
        "--port", str(PORT),
        "--enable-lora",
        "--max-loras", str(MAX_LORAS),
        "--max-lora-rank", str(MAX_LORA_RANK),
        "--max-model-len", "8192",
        "--gpu-memory-utilization", "0.9",
        "--trust-remote-code",
    ] + lora_modules_args

    print(f"명령어: {' '.join(cmd[:10])}...")
    print(f"포트: {PORT}")
    print(f"GPU: 5")
    print(f"어댑터 수: {len(adapters)}")
    print("-" * 60)

    # 서버 실행
    subprocess.run(cmd)

def main():
    print("=" * 60)
    print("8개 제품 LoRA 어댑터 vLLM 서빙")
    print("=" * 60)
    print(f"Base Model: {BASE_MODEL}")
    print(f"Port: {PORT}")
    print(f"GPU: 5")
    print()

    # 어댑터 확인
    valid_adapters = check_adapters()

    if not valid_adapters:
        print("\n❌ 유효한 어댑터가 없습니다.")
        return

    # 서버 시작
    start_vllm_server(valid_adapters)

if __name__ == "__main__":
    main()
