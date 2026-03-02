#!/usr/bin/env python3
"""
Learning Dataset Critical Issues Fixer

Critical 이슈 해결:
1. Train/Eval Leakage 수정 (겹치는 질문 제거)
2. 동일질문-다른답변 해결 (질문에 제품명 추가 또는 최선 답변 유지)
3. 잘린/불완전 질문 필터링

Usage:
    python fix_dataset_issues.py --input full_dataset.json --output cleaned/
    python fix_dataset_issues.py --input full_dataset.json --output cleaned/ --strategy disambiguate
    python fix_dataset_issues.py --input full_dataset.json --output cleaned/ --strategy best-answer
"""
import os
import sys
import json
import re
import hashlib
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import Counter, defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FixStats:
    """수정 통계"""
    total_records: int = 0
    unique_questions: int = 0
    duplicate_questions: int = 0
    duplicate_records: int = 0

    # Train/Eval split
    train_count: int = 0
    eval_count: int = 0
    leakage_removed: int = 0

    # Duplicate handling
    disambiguated: int = 0
    best_answer_kept: int = 0

    # Truncated questions
    truncated_removed: int = 0

    # Final counts
    final_train: int = 0
    final_eval: int = 0
    final_total: int = 0


class DatasetFixer:
    """학습 데이터셋 Critical 이슈 수정"""

    # 잘린 질문 패턴
    TRUNCATED_PATTERNS = [
        r'^er\w*の',  # erData, erFile 등 앞부분 잘림
        r'^ation\s',  # ation resources 등 앞부분 잘림
        r'^\w{1,3}の手順',  # 너무 짧은 시작
        r'What are the steps for ation',  # 잘린 영어 질문
        r'^er\w*Data',
        r'@ ?이란',  # 특수문자 포함 질문
    ]

    def __init__(self, strategy: str = "disambiguate"):
        """
        Args:
            strategy: 중복 처리 전략
                - "disambiguate": 질문에 제품명 추가
                - "best-answer": 가장 긴 답변만 유지
                - "first": 첫 번째 레코드만 유지
        """
        self.strategy = strategy
        self.stats = FixStats()
        self.truncated_regex = [re.compile(p) for p in self.TRUNCATED_PATTERNS]

    def extract_question(self, text: str) -> str:
        """ChatML 형식에서 user 질문 추출"""
        match = re.search(r'<\|im_start\|>user\s*\n(.+?)<\|im_end\|>', text, re.DOTALL)
        return match.group(1).strip() if match else ''

    def extract_answer(self, text: str) -> str:
        """ChatML 형식에서 assistant 답변 추출"""
        match = re.search(r'<\|im_start\|>assistant\s*\n(.+?)<\|im_end\|>', text, re.DOTALL)
        return match.group(1).strip() if match else ''

    def extract_system(self, text: str) -> str:
        """ChatML 형식에서 system 프롬프트 추출"""
        match = re.search(r'<\|im_start\|>system\s*\n(.+?)<\|im_end\|>', text, re.DOTALL)
        return match.group(1).strip() if match else ''

    def extract_product(self, text: str) -> str:
        """답변에서 제품명 추출"""
        match = re.search(r'\*\*(?:製品|Product)[^*]*\*\*:\s*(.+?)(?:\n|\*\*|$)', text)
        if match:
            return match.group(1).strip()

        # Source 파일명에서 추론
        source_match = re.search(r'\*\*(?:出典|Source)[^*]*\*\*:\s*(.+?)(?:\n|$)', text)
        if source_match:
            source = source_match.group(1).strip()
            # 파일명에서 제품 추출
            product_patterns = [
                (r'Tibero', 'Tibero'),
                (r'JEUS|Jeus', 'JEUS'),
                (r'Tmax', 'Tmax'),
                (r'WebtoB', 'WebtoB'),
                (r'OF_OSC', 'OF_OSC'),
                (r'OF_Batch', 'OF_Batch'),
                (r'OF_Base', 'OF_Base'),
                (r'OF_Common', 'OF_Common'),
                (r'OF_TACF', 'OF_TACF'),
                (r'OF_AIM', 'OF_AIM'),
                (r'OF_NDB', 'OF_NDB'),
                (r'OF_HiDB', 'OF_HiDB'),
                (r'OF_OSI', 'OF_OSI'),
                (r'OF_Gateway|OF_GW', 'OF_Gateway'),
                (r'OF_VOS3', 'OF_VOS3'),
                (r'OFManager', 'OFManager'),
                (r'OFStudio', 'OFStudio'),
                (r'ProTrieve', 'ProTrieve'),
                (r'ProSort', 'ProSort'),
                (r'ProSync', 'ProSync'),
            ]
            for pattern, product in product_patterns:
                if re.search(pattern, source, re.IGNORECASE):
                    return product

        return "Unknown"

    def is_truncated(self, question: str) -> bool:
        """잘린 질문인지 확인"""
        for regex in self.truncated_regex:
            if regex.search(question):
                return True
        return False

    def rebuild_chatml(self, system: str, question: str, answer: str) -> str:
        """ChatML 형식으로 재구성"""
        return f"""<|im_start|>system
{system}<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{answer}<|im_end|>"""

    def disambiguate_question(self, question: str, product: str) -> str:
        """질문에 제품명 prefix 추가"""
        if product and product != "Unknown":
            # 이미 제품명이 있는지 확인
            if f"[{product}]" in question or product in question:
                return question
            return f"[{product}] {question}"
        return question

    def fix_duplicates(self, records: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """중복 질문 처리"""
        # 질문별로 레코드 그룹화
        question_to_records = defaultdict(list)
        for i, record in enumerate(records):
            question = self.extract_question(record.get('text', ''))
            question_to_records[question].append((i, record))

        self.stats.unique_questions = len(question_to_records)

        # 중복 질문 식별
        duplicates = {q: recs for q, recs in question_to_records.items() if len(recs) > 1}
        self.stats.duplicate_questions = len(duplicates)
        self.stats.duplicate_records = sum(len(recs) for recs in duplicates.values())

        logger.info(f"Found {len(duplicates)} duplicate questions ({self.stats.duplicate_records} records)")

        fixed_records = []
        processed_indices = set()

        for question, recs in question_to_records.items():
            if len(recs) == 1:
                # 단일 레코드는 그대로 유지
                fixed_records.append(recs[0][1])
                processed_indices.add(recs[0][0])
            else:
                # 중복 처리
                if self.strategy == "disambiguate":
                    # 각 레코드에 제품명 추가
                    for idx, record in recs:
                        text = record.get('text', '')
                        system = self.extract_system(text)
                        answer = self.extract_answer(text)
                        product = self.extract_product(answer)

                        new_question = self.disambiguate_question(question, product)
                        new_text = self.rebuild_chatml(system, new_question, answer)

                        fixed_records.append({'text': new_text})
                        processed_indices.add(idx)
                        self.stats.disambiguated += 1

                elif self.strategy == "best-answer":
                    # 가장 긴 답변을 가진 레코드 선택
                    best_record = max(recs, key=lambda x: len(self.extract_answer(x[1].get('text', ''))))
                    fixed_records.append(best_record[1])
                    processed_indices.add(best_record[0])
                    self.stats.best_answer_kept += 1

                else:  # "first"
                    # 첫 번째 레코드만 유지
                    fixed_records.append(recs[0][1])
                    processed_indices.add(recs[0][0])

        return fixed_records

    def remove_truncated(self, records: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """잘린/불완전 질문 제거"""
        clean_records = []
        for record in records:
            question = self.extract_question(record.get('text', ''))
            if self.is_truncated(question):
                self.stats.truncated_removed += 1
                logger.debug(f"Removed truncated question: {question[:50]}")
            else:
                clean_records.append(record)

        logger.info(f"Removed {self.stats.truncated_removed} truncated questions")
        return clean_records

    def split_train_eval(
        self,
        records: List[Dict[str, str]],
        train_ratio: float = 0.8,
        seed: int = 42
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Train/Eval 분할 (Leakage 방지)"""
        import random
        random.seed(seed)

        # 질문 기준으로 분할 (같은 질문이 양쪽에 가지 않도록)
        question_to_records = defaultdict(list)
        for record in records:
            question = self.extract_question(record.get('text', ''))
            question_to_records[question].append(record)

        questions = list(question_to_records.keys())
        random.shuffle(questions)

        split_idx = int(len(questions) * train_ratio)
        train_questions = set(questions[:split_idx])
        eval_questions = set(questions[split_idx:])

        train_records = []
        eval_records = []

        for question, recs in question_to_records.items():
            if question in train_questions:
                train_records.extend(recs)
            else:
                eval_records.extend(recs)

        # 셔플
        random.shuffle(train_records)
        random.shuffle(eval_records)

        self.stats.final_train = len(train_records)
        self.stats.final_eval = len(eval_records)

        # Leakage 검증
        train_q_set = set(self.extract_question(r.get('text', '')) for r in train_records)
        eval_q_set = set(self.extract_question(r.get('text', '')) for r in eval_records)
        overlap = train_q_set & eval_q_set

        if overlap:
            logger.warning(f"Still have {len(overlap)} overlapping questions!")
        else:
            logger.info("No Train/Eval leakage - clean split!")

        return train_records, eval_records

    def fix_existing_split(
        self,
        train_records: List[Dict[str, str]],
        eval_records: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """기존 Train/Eval 분할에서 Leakage 수정"""
        train_questions = set(self.extract_question(r.get('text', '')) for r in train_records)

        clean_eval = []
        for record in eval_records:
            question = self.extract_question(record.get('text', ''))
            if question in train_questions:
                self.stats.leakage_removed += 1
            else:
                clean_eval.append(record)

        logger.info(f"Removed {self.stats.leakage_removed} leaking records from eval")
        return train_records, clean_eval

    def process_full_dataset(
        self,
        input_path: str,
        output_dir: str,
        train_ratio: float = 0.8,
        seed: int = 42
    ) -> FixStats:
        """전체 데이터셋 처리"""
        logger.info(f"Loading dataset: {input_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        records = data if isinstance(data, list) else data.get('items', [])
        self.stats.total_records = len(records)
        logger.info(f"Loaded {len(records)} records")

        # 1. 잘린 질문 제거
        logger.info("Step 1: Removing truncated questions...")
        records = self.remove_truncated(records)

        # 2. 중복 처리
        logger.info(f"Step 2: Fixing duplicates (strategy: {self.strategy})...")
        records = self.fix_duplicates(records)

        # 3. Train/Eval 분할 (Leakage 없이)
        logger.info("Step 3: Splitting train/eval (no leakage)...")
        train_records, eval_records = self.split_train_eval(records, train_ratio, seed)

        self.stats.final_total = len(train_records) + len(eval_records)

        # 저장
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # full_dataset_cleaned.json
        full_path = output_path / "full_dataset_cleaned.json"
        logger.info(f"Saving: {full_path}")
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(train_records + eval_records, f, ensure_ascii=False, indent=2)

        # train_cleaned.json
        train_path = output_path / "train_cleaned.json"
        logger.info(f"Saving: {train_path}")
        with open(train_path, 'w', encoding='utf-8') as f:
            json.dump(train_records, f, ensure_ascii=False, indent=2)

        # eval_cleaned.json
        eval_path = output_path / "eval_cleaned.json"
        logger.info(f"Saving: {eval_path}")
        with open(eval_path, 'w', encoding='utf-8') as f:
            json.dump(eval_records, f, ensure_ascii=False, indent=2)

        # stats
        stats_path = output_path / "fix_stats.json"
        stats_dict = asdict(self.stats)
        stats_dict['strategy'] = self.strategy
        stats_dict['train_ratio'] = train_ratio
        stats_dict['created_at'] = datetime.now().isoformat()
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats_dict, f, ensure_ascii=False, indent=2)

        return self.stats


def main():
    parser = argparse.ArgumentParser(description="Fix critical issues in learning dataset")
    parser.add_argument("--input", "-i", required=True, help="Input dataset JSON path")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument(
        "--strategy", "-s",
        choices=["disambiguate", "best-answer", "first"],
        default="disambiguate",
        help="Duplicate handling strategy (default: disambiguate)"
    )
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train/Eval split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    fixer = DatasetFixer(strategy=args.strategy)
    stats = fixer.process_full_dataset(
        input_path=args.input,
        output_dir=args.output,
        train_ratio=args.train_ratio,
        seed=args.seed
    )

    # 결과 출력
    print("\n" + "=" * 70)
    print("Dataset Critical Issues Fix Results")
    print("=" * 70)
    print(f"Strategy:              {args.strategy}")
    print("-" * 70)
    print(f"Input records:         {stats.total_records:,}")
    print(f"Unique questions:      {stats.unique_questions:,}")
    print(f"Duplicate questions:   {stats.duplicate_questions:,}")
    print(f"Duplicate records:     {stats.duplicate_records:,}")
    print("-" * 70)
    print("Actions taken:")
    print(f"  Truncated removed:   {stats.truncated_removed:,}")
    if args.strategy == "disambiguate":
        print(f"  Disambiguated:       {stats.disambiguated:,}")
    elif args.strategy == "best-answer":
        print(f"  Best answer kept:    {stats.best_answer_kept:,}")
    print(f"  Leakage removed:     {stats.leakage_removed:,}")
    print("-" * 70)
    print("Output:")
    print(f"  Train records:       {stats.final_train:,}")
    print(f"  Eval records:        {stats.final_eval:,}")
    print(f"  Total:               {stats.final_total:,}")
    print("=" * 70)
    print(f"\nOutput saved to: {args.output}/")
    print("  - full_dataset_cleaned.json")
    print("  - train_cleaned.json")
    print("  - eval_cleaned.json")
    print("  - fix_stats.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
