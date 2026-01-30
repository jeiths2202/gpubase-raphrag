#!/usr/bin/env python3
"""
docker-compose.yml 어댑터 등록 업데이트 스크립트
================================================
모든 QLoRA 어댑터를 learning-llm 서비스에 등록합니다.

사용법:
    python update_docker_compose.py --preview   # 변경 미리보기
    python update_docker_compose.py --apply     # 변경 적용
"""

import sys
import re
import argparse
from pathlib import Path
from datetime import datetime
import shutil

DOCKER_COMPOSE_PATH = Path("/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/docker/docker-compose.yml")
ADAPTERS_BASE_PATH = "/home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130"

# 등록할 어댑터 목록
ADAPTERS = {
    "openframe_mvs": "openframe_qlora_adapter",
    "msp_openframe": "qlora_adapters/msp_openframe",
    "vos3_openframe": "qlora_adapters/vos3_openframe",
    "tibero7": "qlora_adapters/tibero7",
    "ofasm": "qlora_adapters/ofasm",
    "ofcobol": "qlora_adapters/ofcobol",
    "xsp_openframe": "qlora_adapters/xsp_openframe",
    "tmax": "qlora_adapters/tmax"
}


def find_latest_adapter_dir(base_path: str, adapter_subdir: str) -> str:
    """최신 어댑터 디렉토리 경로 반환"""
    adapter_dir = Path(base_path) / adapter_subdir

    if not adapter_dir.exists():
        return str(adapter_dir)

    # 타임스탬프 디렉토리 찾기
    subdirs = [d for d in adapter_dir.iterdir() if d.is_dir()]
    if subdirs:
        latest = max(subdirs, key=lambda x: x.stat().st_mtime)
        return str(latest)

    return str(adapter_dir)


def generate_volume_mounts() -> list:
    """볼륨 마운트 설정 생성"""
    mounts = []

    for adapter_name, adapter_subdir in ADAPTERS.items():
        host_path = find_latest_adapter_dir(ADAPTERS_BASE_PATH, adapter_subdir)
        container_path = f"/opt/qlora_adapters/{adapter_name}"
        mounts.append(f"      - {host_path}:{container_path}")

    return mounts


def generate_lora_modules_arg() -> str:
    """--lora-modules 인자 생성"""
    modules = []

    for adapter_name in ADAPTERS.keys():
        container_path = f"/opt/qlora_adapters/{adapter_name}"
        modules.append(f"{adapter_name}={container_path}")

    return " ".join(modules)


def update_docker_compose(preview_only: bool = True):
    """docker-compose.yml 업데이트"""

    if not DOCKER_COMPOSE_PATH.exists():
        print(f"Error: docker-compose.yml not found at {DOCKER_COMPOSE_PATH}")
        return False

    # 원본 읽기
    with open(DOCKER_COMPOSE_PATH, 'r') as f:
        content = f.read()

    # 백업
    if not preview_only:
        backup_path = DOCKER_COMPOSE_PATH.with_suffix(f'.yml.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        shutil.copy(DOCKER_COMPOSE_PATH, backup_path)
        print(f"백업 생성: {backup_path}")

    # 새 설정 생성
    volume_mounts = generate_volume_mounts()
    lora_modules_arg = generate_lora_modules_arg()

    print("\n[생성된 볼륨 마운트]")
    for mount in volume_mounts:
        print(mount)

    print("\n[생성된 --lora-modules 인자]")
    print(f"--lora-modules {lora_modules_arg}")

    # 변경사항 설명
    changes = f"""
=================================================================
docker-compose.yml 변경 안내
=================================================================

learning-llm 서비스의 volumes 섹션에 다음을 추가하세요:

{chr(10).join(volume_mounts)}

learning-llm 서비스의 command 섹션에서 --lora-modules 인자를 수정하세요:

    --lora-modules {lora_modules_arg}

또한 --max-loras 값을 {len(ADAPTERS)}개 이상으로 설정하세요:

    --max-loras 16

=================================================================
"""

    print(changes)

    if preview_only:
        print("미리보기 모드입니다. 변경을 적용하려면 --apply 옵션을 사용하세요.")
        return True

    # 자동 업데이트 시도
    try:
        # volumes 섹션 업데이트를 위한 새 내용 생성
        new_volumes = "\n".join(volume_mounts)

        # lora-modules 업데이트
        new_lora_arg = f"--lora-modules {lora_modules_arg}"

        # 기존 lora-modules 패턴 찾기
        lora_pattern = r'--lora-modules\s+\S+'
        if re.search(lora_pattern, content):
            content = re.sub(lora_pattern, new_lora_arg, content)
            print("--lora-modules 인자 업데이트됨")

        # 파일 저장
        with open(DOCKER_COMPOSE_PATH, 'w') as f:
            f.write(content)

        print(f"\ndocker-compose.yml 업데이트 완료: {DOCKER_COMPOSE_PATH}")
        print("\n수동으로 volumes 섹션에 위의 마운트들을 추가해야 합니다.")
        print("\n컨테이너 재시작:")
        print("  cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/docker")
        print("  docker-compose restart learning-llm")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="docker-compose.yml 어댑터 등록 업데이트")
    parser.add_argument("--preview", action="store_true", help="변경 미리보기만")
    parser.add_argument("--apply", action="store_true", help="변경 적용")

    args = parser.parse_args()

    if not args.apply and not args.preview:
        args.preview = True

    update_docker_compose(preview_only=not args.apply)


if __name__ == "__main__":
    main()
