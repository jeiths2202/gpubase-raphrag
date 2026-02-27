#!/usr/bin/env python3
"""
모든 QLoRA 어댑터 검증 스크립트
================================
각 제품별로 생성된 QLoRA 어댑터가 올바르게 생성되었는지 검증합니다.

사용법:
    python validate_all_adapters.py
    python validate_all_adapters.py --test-inference
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
import requests
from typing import Dict, List, Optional

# 제품 설정
PRODUCTS = {
    "openframe_mvs": {
        "name": "OpenFrame MVS 7.1",
        "adapter_dir": "openframe_qlora_adapter"
    },
    "msp_openframe": {
        "name": "MSP OpenFrame 7.3",
        "adapter_dir": "qlora_adapters/msp_openframe"
    },
    "vos3_openframe": {
        "name": "VOS3 OpenFrame 2.0",
        "adapter_dir": "qlora_adapters/vos3_openframe"
    },
    "tibero7": {
        "name": "Tibero 7",
        "adapter_dir": "qlora_adapters/tibero7"
    },
    "ofasm": {
        "name": "OpenFrame ASM 4",
        "adapter_dir": "qlora_adapters/ofasm"
    },
    "ofcobol": {
        "name": "OpenFrame COBOL 4",
        "adapter_dir": "qlora_adapters/ofcobol"
    },
    "xsp_openframe": {
        "name": "XSP OpenFrame 7.3",
        "adapter_dir": "qlora_adapters/xsp_openframe"
    },
    "tmax": {
        "name": "Tmax 6.0",
        "adapter_dir": "qlora_adapters/tmax"
    }
}

BASE_DIR = Path("/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130")
LEARNING_LLM_URL = "http://localhost:12804"


def check_adapter_files(adapter_dir: Path) -> Dict:
    """어댑터 디렉토리 파일 검증"""
    result = {
        "exists": False,
        "has_adapter_config": False,
        "has_adapter_model": False,
        "has_tokenizer": False,
        "files": [],
        "total_size_mb": 0
    }

    if not adapter_dir.exists():
        return result

    result["exists"] = True

    # 최신 어댑터 디렉토리 찾기 (타임스탬프가 있는 경우)
    subdirs = [d for d in adapter_dir.iterdir() if d.is_dir()]
    if subdirs:
        # 가장 최근 디렉토리 선택
        latest_dir = max(subdirs, key=lambda x: x.stat().st_mtime)
        adapter_dir = latest_dir

    # 필수 파일 확인
    files = list(adapter_dir.glob("*"))
    result["files"] = [f.name for f in files]

    for f in files:
        if f.name == "adapter_config.json":
            result["has_adapter_config"] = True
        elif f.name.endswith(".safetensors") or f.name == "adapter_model.bin":
            result["has_adapter_model"] = True
        elif f.name in ["tokenizer.json", "tokenizer_config.json"]:
            result["has_tokenizer"] = True

        if f.is_file():
            result["total_size_mb"] += f.stat().st_size / (1024 * 1024)

    result["total_size_mb"] = round(result["total_size_mb"], 2)

    return result


def test_inference(adapter_name: str, product_name: str) -> Dict:
    """어댑터로 추론 테스트"""
    test_prompt = f"{product_name}의 주요 기능을 설명해 주세요."

    try:
        response = requests.post(
            f"{LEARNING_LLM_URL}/v1/chat/completions",
            json={
                "model": adapter_name,
                "messages": [
                    {"role": "user", "content": test_prompt}
                ],
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "response_length": len(content),
                "preview": content[:200] if content else ""
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "learning-llm 서비스에 연결할 수 없습니다."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def check_learning_llm_status() -> Dict:
    """learning-llm 서비스 상태 확인"""
    try:
        response = requests.get(f"{LEARNING_LLM_URL}/health", timeout=10)
        if response.status_code == 200:
            return {"status": "healthy", "url": LEARNING_LLM_URL}
        else:
            return {"status": "unhealthy", "code": response.status_code}
    except requests.exceptions.ConnectionError:
        return {"status": "not_running"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="QLoRA 어댑터 검증")
    parser.add_argument("--test-inference", action="store_true",
                        help="추론 테스트 실행")
    parser.add_argument("--product", type=str, default="all",
                        help="검증할 제품 (all 또는 제품키)")
    args = parser.parse_args()

    print("=" * 70)
    print("QLoRA 어댑터 검증 보고서")
    print(f"생성 시간: {datetime.now().isoformat()}")
    print("=" * 70)

    # learning-llm 상태 확인
    llm_status = check_learning_llm_status()
    print(f"\n[learning-llm 서비스 상태]")
    print(f"  상태: {llm_status.get('status')}")

    # 검증할 제품 결정
    if args.product == "all":
        products_to_check = PRODUCTS
    elif args.product in PRODUCTS:
        products_to_check = {args.product: PRODUCTS[args.product]}
    else:
        print(f"알 수 없는 제품: {args.product}")
        return

    results = {}
    total_valid = 0
    total_invalid = 0

    print("\n[어댑터 파일 검증]")
    print("-" * 70)

    for product_key, product_info in products_to_check.items():
        adapter_dir = BASE_DIR / product_info["adapter_dir"]
        file_check = check_adapter_files(adapter_dir)

        is_valid = (file_check["exists"] and
                    file_check["has_adapter_config"] and
                    file_check["has_adapter_model"])

        if is_valid:
            total_valid += 1
            status = "✓ 유효"
        else:
            total_invalid += 1
            status = "✗ 무효"

        print(f"\n{product_info['name']} ({product_key}):")
        print(f"  상태: {status}")
        print(f"  디렉토리: {adapter_dir}")
        print(f"  존재: {file_check['exists']}")
        if file_check["exists"]:
            print(f"  adapter_config.json: {file_check['has_adapter_config']}")
            print(f"  adapter_model: {file_check['has_adapter_model']}")
            print(f"  tokenizer: {file_check['has_tokenizer']}")
            print(f"  총 크기: {file_check['total_size_mb']} MB")

        results[product_key] = {
            "name": product_info["name"],
            "file_check": file_check,
            "is_valid": is_valid
        }

        # 추론 테스트
        if args.test_inference and is_valid and llm_status.get("status") == "healthy":
            print(f"  추론 테스트 중...")
            inference_result = test_inference(product_key, product_info["name"])
            results[product_key]["inference"] = inference_result

            if inference_result["success"]:
                print(f"  추론 결과: ✓ 성공 ({inference_result['response_length']} chars)")
            else:
                print(f"  추론 결과: ✗ 실패 - {inference_result.get('error', 'Unknown')}")

    # 요약
    print("\n" + "=" * 70)
    print("검증 요약")
    print("=" * 70)
    print(f"  검증된 제품: {len(products_to_check)}")
    print(f"  유효한 어댑터: {total_valid}")
    print(f"  무효한 어댑터: {total_invalid}")

    # 결과 저장
    report_file = BASE_DIR / "adapter_validation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "llm_status": llm_status,
            "summary": {
                "total": len(products_to_check),
                "valid": total_valid,
                "invalid": total_invalid
            },
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n보고서 저장: {report_file}")

    # 종료 코드
    sys.exit(0 if total_invalid == 0 else 1)


if __name__ == "__main__":
    main()
