#!/usr/bin/env python3
"""
Learning Dataset Quality Filter

저품질 데이터를 필터링하고 고품질 학습 데이터셋을 생성합니다.

Usage:
    python quality_filter.py --input learning_dataset.json --output filtered_dataset.json
    python quality_filter.py --input learning_dataset.json --output filtered_dataset.json --strict
"""
import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FilterStats:
    """필터링 통계"""
    total: int = 0
    passed: int = 0
    filtered: int = 0
    by_reason: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    by_product: Dict[str, int] = field(default_factory=dict)


class QualityFilter:
    """학습 데이터 품질 필터"""

    # 플레이스홀더 패턴 (이런 답변은 학습에 무의미)
    PLACEHOLDER_PATTERNS = [
        r'^.+はOpenFrameシステムの(concept|api|command|config|error|procedure|term)です。$',
        r'^.+はOpenFrameシステムの.+です。$',
        r'^.+は.+システムの(concept|api|command)です。$',
        r'^Unknown$',
        r'^\s*$',
    ]

    # 유효한 제품 목록
    VALID_PRODUCTS = {
        'JEUS', 'Tmax', 'Tibero', 'WebtoB', 'ProSort', 'ProSync', 'ProTrieve',
        'OpenFrame', 'OFManager', 'OFStudio', 'OFMiner', 'OFAsm', 'OFCOBOL', 'OFPLI',
        'OF_Base', 'OF_Batch', 'OF_Common', 'OF_Gateway', 'OF_GW',
        'OF_TACF', 'OF_NDB', 'OF_HiDB', 'OF_OSC', 'OF_OSI', 'OF_AIM', 'OF_VOS3',
        'OF_Batch_MVS', 'OF_Batch_MSP', 'OF_Batch_XSP', 'OF_Batch_VOS3',
        'OF_OSC_MVS', 'OF_OSI_MVS', 'OF_HiDB_MVS',
        'OF_TACF_MVS', 'OF_TACF_MSP', 'OF_TACF_XSP',
        'OF_Common_MVS', 'OF_AIM_MSP', 'OF_AIM_XSP',
    }

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.stats = FilterStats()
        self.placeholder_regex = [re.compile(p) for p in self.PLACEHOLDER_PATTERNS]

    def is_placeholder(self, description: str) -> bool:
        """플레이스홀더 답변인지 확인"""
        if not description:
            return True
        for regex in self.placeholder_regex:
            if regex.match(description.strip()):
                return True
        return False

    def check_quality(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """
        품질 검사
        Returns: (passed, reason)
        """
        name = item.get("name", "")
        description = item.get("description", "")
        item_type = item.get("type", "concept")
        product = item.get("product", "Unknown")
        syntax = item.get("syntax")

        # 1. 이름 필수
        if not name or len(name.strip()) < 2:
            return False, "empty_name"

        # 2. 설명 필수
        if not description:
            return False, "empty_description"

        # 3. 플레이스홀더 필터링
        if self.is_placeholder(description):
            return False, "placeholder_description"

        # 4. 최소 설명 길이 (strict 모드에서 더 엄격)
        min_length = 50 if self.strict else 30
        if len(description) < min_length:
            return False, "short_description"

        # 5. command/api 타입은 syntax 또는 충분한 설명 필요
        if item_type in ["command", "api"]:
            if not syntax and len(description) < 100:
                if self.strict:
                    return False, "missing_syntax"

        # 6. strict 모드: 제품 정보 필수
        if self.strict and product == "Unknown":
            return False, "unknown_product"

        return True, "passed"

    def filter_dataset(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """데이터셋 필터링"""
        filtered_items = []

        for item in items:
            self.stats.total += 1
            passed, reason = self.check_quality(item)

            if passed:
                self.stats.passed += 1
                filtered_items.append(item)

                # 통계 업데이트
                item_type = item.get("type", "concept")
                product = item.get("product", "Unknown")
                self.stats.by_type[item_type] = self.stats.by_type.get(item_type, 0) + 1
                self.stats.by_product[product] = self.stats.by_product.get(product, 0) + 1
            else:
                self.stats.filtered += 1
                self.stats.by_reason[reason] = self.stats.by_reason.get(reason, 0) + 1

        return filtered_items

    def get_stats(self) -> FilterStats:
        return self.stats


def load_dataset(path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """데이터셋 로드"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        return data, {}
    else:
        return data.get("items", []), data.get("metadata", {})


def save_dataset(items: List[Dict[str, Any]], metadata: Dict[str, Any], path: str):
    """데이터셋 저장"""
    output = {
        "metadata": metadata,
        "items": items
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Filter low-quality learning data")
    parser.add_argument("--input", "-i", required=True, help="Input dataset JSON path")
    parser.add_argument("--output", "-o", required=True, help="Output filtered dataset path")
    parser.add_argument("--strict", action="store_true", help="Enable strict filtering mode")
    parser.add_argument("--stats", "-s", help="Output stats JSON path")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    # 데이터셋 로드
    logger.info(f"Loading dataset: {args.input}")
    items, original_metadata = load_dataset(args.input)
    logger.info(f"Loaded {len(items)} items")

    # 필터링 실행
    logger.info(f"Filtering with strict={args.strict}")
    filter_obj = QualityFilter(strict=args.strict)
    filtered_items = filter_obj.filter_dataset(items)
    stats = filter_obj.get_stats()

    # 새 메타데이터 생성
    new_metadata = {
        "total_items": len(filtered_items),
        "type_stats": stats.by_type,
        "product_stats": stats.by_product,
        "filtered_from": args.input,
        "filter_mode": "strict" if args.strict else "normal",
        "created_at": datetime.now().isoformat()
    }

    # 저장
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Saving filtered dataset: {args.output}")
    save_dataset(filtered_items, new_metadata, args.output)

    # 통계 저장
    if args.stats:
        stats_dict = asdict(stats)
        stats_dict["filter_mode"] = "strict" if args.strict else "normal"
        stats_dict["created_at"] = datetime.now().isoformat()
        with open(args.stats, 'w', encoding='utf-8') as f:
            json.dump(stats_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"Stats saved: {args.stats}")

    # 결과 출력
    print("\n" + "=" * 60)
    print("Quality Filter Results")
    print("=" * 60)
    print(f"Total items:    {stats.total:,}")
    print(f"Passed:         {stats.passed:,} ({stats.passed/stats.total*100:.1f}%)")
    print(f"Filtered:       {stats.filtered:,} ({stats.filtered/stats.total*100:.1f}%)")
    print("-" * 60)
    print("Filtered by reason:")
    for reason, count in sorted(stats.by_reason.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count:,}")
    print("-" * 60)
    print("Passed by type:")
    for t, count in sorted(stats.by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count:,}")
    print("-" * 60)
    print("Top 10 products:")
    for p, count in sorted(stats.by_product.items(), key=lambda x: -x[1])[:10]:
        print(f"  {p}: {count:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
