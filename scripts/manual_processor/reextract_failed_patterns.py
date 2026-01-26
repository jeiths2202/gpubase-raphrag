#!/usr/bin/env python3
"""
실패 패턴 대상 재추출 스크립트

개선된 프롬프트를 사용하여 실패한 패턴(EXEC, ABEND 등)이 포함된
매뉴얼만 선택적으로 재추출합니다.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import asdict

# LLM 파서 임포트
import importlib.util
spec = importlib.util.spec_from_file_location(
    "llm_parser",
    Path(__file__).parent / "parsers" / "llm_parser.py"
)
llm_parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(llm_parser_module)
LLMParser = llm_parser_module.LLMParser
ExtractedItem = llm_parser_module.ExtractedItem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/kms/scripts/manual_processor/reextract.log')
    ]
)
logger = logging.getLogger(__name__)


# 실패 패턴별 대상 파일 패턴
FAILED_PATTERN_TARGETS = {
    "EXEC_CICS_SQL": {
        "description": "EXEC CICS/SQL 명령어",
        "file_patterns": [
            "Developer",
            "COBOL",
            "CICS",
        ],
        "priority": "critical",
    },
    "ABEND_CODES": {
        "description": "ABEND 코드 (Sxxx, Uxxxx)",
        "file_patterns": [
            "Error",
        ],
        "priority": "critical",
    },
    "MODULE_ERROR_NAMES": {
        "description": "모듈별 에러명 (DSALC_ERR_xxx)",
        "file_patterns": [
            "Error",
        ],
        "priority": "high",
    },
    "SHUTDOWN_COMMANDS": {
        "description": "종료/다운 명령어",
        "file_patterns": [
            "Administrator",
            "Command",
            "Tool",
        ],
        "priority": "critical",
    },
    "COMPILER_COMMANDS": {
        "description": "컴파일러/번역기 명령어",
        "file_patterns": [
            "COBOL",
            "PLI",
            "ASM",
            "Compiler",
        ],
        "priority": "medium",
    },
    "ENV_VARIABLES": {
        "description": "환경 변수 ($OPENFRAME_HOME)",
        "file_patterns": [
            "Configuration",
            "Installation",
            "Getting",
        ],
        "priority": "medium",
    },
}


def find_target_files(manuals_dir: Path, patterns: list) -> list:
    """패턴에 맞는 대상 파일 찾기"""
    all_pdfs = list(manuals_dir.rglob("*.pdf"))
    target_files = []

    for pdf in all_pdfs:
        filename = pdf.name
        for pattern in patterns:
            if pattern.lower() in filename.lower():
                target_files.append(pdf)
                break

    return target_files


def merge_items(existing_items: list, new_items: list) -> list:
    """기존 항목과 새 항목 병합 (중복 제거, 더 긴 설명 유지)"""
    seen = {}

    # 기존 항목 먼저 추가
    for item in existing_items:
        if isinstance(item, dict):
            key = (item.get("name", "").lower(), item.get("item_type", ""), item.get("product", ""))
            seen[key] = item

    # 새 항목 추가 (더 긴 설명이면 대체)
    for item in new_items:
        if isinstance(item, ExtractedItem):
            item_dict = asdict(item)
        else:
            item_dict = item

        key = (item_dict.get("name", "").lower(), item_dict.get("item_type", ""), item_dict.get("product", ""))

        if key not in seen:
            seen[key] = item_dict
        else:
            existing_desc = seen[key].get("description", "")
            new_desc = item_dict.get("description", "")
            if len(new_desc) > len(existing_desc):
                seen[key] = item_dict

    return list(seen.values())


async def reextract_for_pattern(
    parser: LLMParser,
    pattern_name: str,
    pattern_config: dict,
    manuals_dir: Path
) -> list:
    """특정 패턴에 대한 재추출"""
    logger.info(f"\n{'='*60}")
    logger.info(f"패턴: {pattern_name}")
    logger.info(f"설명: {pattern_config['description']}")
    logger.info(f"우선순위: {pattern_config['priority']}")
    logger.info(f"{'='*60}")

    # 대상 파일 찾기
    target_files = find_target_files(manuals_dir, pattern_config["file_patterns"])
    logger.info(f"대상 파일: {len(target_files)}개")

    if not target_files:
        logger.warning("대상 파일 없음")
        return []

    for f in target_files[:5]:
        logger.info(f"  - {f.name}")
    if len(target_files) > 5:
        logger.info(f"  ... 외 {len(target_files) - 5}개")

    # 추출 실행
    all_items = []
    for i, pdf_path in enumerate(target_files, 1):
        logger.info(f"\n[{i}/{len(target_files)}] {pdf_path.name}")
        try:
            items = await parser.parse_pdf(pdf_path)
            all_items.extend(items)
            logger.info(f"  → {len(items)} items")
        except Exception as e:
            logger.error(f"  → 오류: {e}")

    logger.info(f"\n{pattern_name} 완료: {len(all_items)} items")
    return all_items


async def main():
    """메인 실행"""
    import argparse

    arg_parser = argparse.ArgumentParser(description="실패 패턴 대상 재추출")
    arg_parser.add_argument(
        "--manuals-dir",
        type=Path,
        default=Path("/opt/kms/uploads/manuals"),
        help="매뉴얼 디렉토리"
    )
    arg_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/opt/kms/uploads/summaries"),
        help="출력 디렉토리"
    )
    arg_parser.add_argument(
        "--pattern",
        type=str,
        choices=list(FAILED_PATTERN_TARGETS.keys()) + ["all", "critical"],
        default="critical",
        help="재추출할 패턴 (기본: critical)"
    )
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 추출 없이 대상 파일만 확인"
    )

    args = arg_parser.parse_args()

    logger.info("=" * 70)
    logger.info("실패 패턴 대상 재추출")
    logger.info(f"시간: {datetime.now().isoformat()}")
    logger.info(f"매뉴얼 디렉토리: {args.manuals_dir}")
    logger.info(f"출력 디렉토리: {args.output_dir}")
    logger.info(f"패턴: {args.pattern}")
    logger.info("=" * 70)

    # 대상 패턴 선택
    if args.pattern == "all":
        target_patterns = FAILED_PATTERN_TARGETS
    elif args.pattern == "critical":
        target_patterns = {
            k: v for k, v in FAILED_PATTERN_TARGETS.items()
            if v["priority"] == "critical"
        }
    else:
        target_patterns = {args.pattern: FAILED_PATTERN_TARGETS[args.pattern]}

    logger.info(f"\n대상 패턴: {len(target_patterns)}개")
    for name, config in target_patterns.items():
        logger.info(f"  - {name}: {config['description']}")

    # Dry run 모드
    if args.dry_run:
        logger.info("\n[DRY RUN] 대상 파일 확인만 수행")
        for pattern_name, pattern_config in target_patterns.items():
            target_files = find_target_files(args.manuals_dir, pattern_config["file_patterns"])
            logger.info(f"\n{pattern_name}: {len(target_files)}개 파일")
            for f in target_files[:10]:
                logger.info(f"  - {f.name}")
        return

    # LLM 파서 초기화
    parser = LLMParser(args.manuals_dir)

    # 기존 추출 결과 로드
    existing_items = []
    extracted_json = args.output_dir / "extracted_items.json"
    if extracted_json.exists():
        try:
            data = json.loads(extracted_json.read_text(encoding="utf-8"))
            existing_items = data.get("items", [])
            logger.info(f"\n기존 추출 결과: {len(existing_items)}개 항목")
        except Exception as e:
            logger.warning(f"기존 결과 로드 실패: {e}")

    # 각 패턴별 재추출
    new_items = []
    for pattern_name, pattern_config in target_patterns.items():
        items = await reextract_for_pattern(
            parser, pattern_name, pattern_config, args.manuals_dir
        )
        new_items.extend(items)

    # 결과 병합
    logger.info(f"\n{'='*60}")
    logger.info("결과 병합")
    logger.info(f"{'='*60}")
    logger.info(f"기존 항목: {len(existing_items)}개")
    logger.info(f"새 항목: {len(new_items)}개")

    merged_items = merge_items(existing_items, [asdict(i) if isinstance(i, ExtractedItem) else i for i in new_items])
    logger.info(f"병합 후: {len(merged_items)}개")

    # 저장
    output_data = {
        "extracted_at": datetime.now().isoformat(),
        "total_items": len(merged_items),
        "reextracted_patterns": list(target_patterns.keys()),
        "items": merged_items
    }

    backup_path = args.output_dir / f"extracted_items_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if extracted_json.exists():
        import shutil
        shutil.copy(extracted_json, backup_path)
        logger.info(f"백업 저장: {backup_path}")

    extracted_json.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"결과 저장: {extracted_json}")

    # 통계 출력
    by_type = defaultdict(int)
    for item in merged_items:
        by_type[item.get("item_type", "unknown")] += 1

    logger.info(f"\n타입별 통계:")
    for item_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        logger.info(f"  {item_type}: {count}")

    logger.info("\n완료!")


if __name__ == "__main__":
    asyncio.run(main())
